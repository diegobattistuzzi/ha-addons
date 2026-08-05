import json
from typing import Any, Dict, List, Optional

# Funzioni pure: non toccano il DB (i dati arrivano gia' estratti dal
# chiamante in server.py, stesso motivo di _build_ai_prompt in categorize.py)
# cosi' restano facili da testare e non duplicano l'accesso alla visibilita'
# per persona, che resta responsabilita' di chi chiama.


def _fmt(amount: Optional[float]) -> str:
    if amount is None:
        return 'n/d'
    return f'{amount:.2f} EUR'


def build_narrative_prompt(
    month: str,
    summary: Dict[str, Any],
    trend: List[Dict[str, Any]],
    top_merchants: List[Dict[str, Any]],
    subscriptions: List[Dict[str, Any]],
) -> str:
    """Prompt per il riepilogo narrativo mensile: passa solo i dati gia'
    aggregati dal backend (mai transazioni singole/dettagli non necessari),
    coerente con l'idea di limitare cosa l'AI vede rispetto a cosa serve."""
    categories_lines = '\n'.join(
        f"- {c['name']}: {_fmt(c['spent'])}" + (f" (budget mensile {_fmt(c['budget_monthly'])})" if c.get('budget_monthly') else '')
        for c in (summary.get('byCategory') or [])
        if c.get('spent')
    ) or '(nessuna spesa nel mese)'
    trend_lines = '\n'.join(
        f"- {t['month']}: entrate {_fmt(t['income'])}, spese famiglia {_fmt(t['family'])}, spese personali {_fmt(t['personal'])}"
        for t in trend
    ) or '(nessuno storico disponibile)'
    merchants_lines = '\n'.join(
        f"- {m['merchant_name']}: {_fmt(m['total'])} ({m['occurrences']} transazioni)"
        for m in top_merchants
    ) or '(nessun merchant ricorrente)'
    subs_lines = '\n'.join(
        f"- {s['merchant_name']}: {_fmt(s['amount'])}/mese"
        for s in subscriptions
    ) or '(nessun abbonamento rilevato)'

    return f'''Sei un assistente finanziario personale. Scrivi un riepilogo in italiano,
in formato Markdown, breve (max 200 parole), commentando i dati del mese {month}
qui sotto. Evidenzia: la categoria con la spesa piu' alta, variazioni rilevanti
rispetto ai mesi precedenti, ed eventuali abbonamenti ricorrenti significativi.
Non inventare numeri: usa solo quelli forniti. Non ripetere pedissequamente
tutti i dati, sintetizza gli aspetti piu' rilevanti.

Totale spese del mese: {_fmt(summary.get('total_expenses'))}
Totale entrate del mese: {_fmt(summary.get('total_income'))}

Spese per categoria:
{categories_lines}

Andamento ultimi mesi:
{trend_lines}

Merchant piu' frequenti nel mese:
{merchants_lines}

Abbonamenti ricorrenti attivi:
{subs_lines}
'''


def detect_anomalies(
    current_by_category: List[Dict[str, Any]],
    historical_avg_by_category: Dict[Any, float],
    current_merchants: List[Dict[str, Any]],
    known_merchants: set,
    threshold_ratio: float = 1.5,
) -> List[Dict[str, Any]]:
    """Rilevazione anomalie deterministica (nessuna chiamata AI qui): una
    categoria e' anomala se la spesa del mese supera la media storica di
    threshold_ratio, un merchant e' anomalo se non compare mai nello storico
    recente. Piu' affidabile di chiedere all'AI di "indovinare" delle soglie
    su una tabella di numeri."""
    anomalies: List[Dict[str, Any]] = []
    for cat in current_by_category:
        spent = cat.get('spent') or 0
        if not spent:
            continue
        avg = historical_avg_by_category.get(cat['id'], 0)
        if avg > 0 and spent > avg * threshold_ratio:
            anomalies.append({
                'type': 'category_spike',
                'category': cat['name'],
                'amount': spent,
                'historicalAverage': avg,
                'severity': 'high' if spent > avg * 2 else 'medium',
            })
    for m in current_merchants:
        name = m.get('merchant_name')
        if name and name not in known_merchants:
            anomalies.append({
                'type': 'new_merchant',
                'merchant': name,
                'amount': m.get('total'),
                'severity': 'low',
            })
    return anomalies


def build_anomaly_explanation_prompt(anomalies: List[Dict[str, Any]]) -> str:
    items = '\n'.join(f"- {json.dumps(a, ensure_ascii=False)}" for a in anomalies)
    return f'''Le seguenti anomalie di spesa sono state rilevate automaticamente (dati gia'
calcolati, non inventare numeri). Per ciascuna scrivi UNA frase in italiano,
chiara e diretta, che la spieghi a chi legge il proprio riepilogo finanziario.
Rispondi SOLO con un array JSON di stringhe nello stesso ordine degli elementi,
es. ["frase 1", "frase 2"].

Anomalie:
{items}
'''


_DIMENSIONS_HELP = "category, account, person, destination, month, day, merchant"
_METRICS_HELP = "sum, count, avg"


def build_query_intent_prompt(question: str, month: Optional[str]) -> str:
    """Traduce una domanda in linguaggio naturale in una query-config nello
    stesso formato gia' usato da ReportBuilder/_REPORT_DIMENSIONS: l'AI sceglie
    solo tra chiavi note, non genera mai SQL."""
    month_hint = f"Il mese corrente di riferimento (se la domanda non specifica un periodo) e' {month}." if month else ''
    return f'''Traduci la domanda dell'utente in un oggetto JSON con questa forma esatta:
{{"dimensions": [...], "metric": "...", "absolute": true|false, "filters": {{...}}}}

Regole:
- "dimensions": array di 1 o 2 valori tra: {_DIMENSIONS_HELP}
- "metric": uno tra: {_METRICS_HELP}
- "absolute": true se la domanda riguarda spese (importi in valore assoluto), false per saldi/entrate
- "filters": oggetto opzionale con chiavi tra: dateFrom, dateTo (YYYY-MM-DD), accountId, categoryId,
  personId, destination (family|personal|split), type (expense|income), confirmedOnly (bool)
{month_hint}
Rispondi SOLO con l'oggetto JSON, nessun testo aggiuntivo.

Domanda: "{question}"
'''


def build_chat_answer_prompt(question: str, query_config: Dict[str, Any], rows: List[Dict[str, Any]]) -> str:
    rows_json = json.dumps(rows, ensure_ascii=False)
    return f'''Rispondi in italiano alla domanda dell'utente sulle sue finanze personali,
usando SOLO i dati numerici qui sotto (risultato gia' calcolato dal backend,
non inventare numeri, non fare ulteriori calcoli che non siano gia' nei dati).
Rispondi in modo diretto e conciso (1-4 frasi), in Markdown semplice.

Domanda: "{question}"
Query eseguita: {json.dumps(query_config, ensure_ascii=False)}
Risultato: {rows_json}
'''

import json
import re
from typing import Any, Dict, List, Optional

from . import ai_client, db

# Vedi lo stesso pattern in pdf_import.py: [ \t]? opzionale prima di ogni
# carattere, per riconoscere anche un IBAN scritto staccato in gruppi (es.
# "IT72 S010 0512 5000 0000 0052 76") dentro la causale di un bonifico.
_IBAN_RE = re.compile(r'\b([A-Za-z]{2}[ \t]?\d{2}(?:[ \t]?[A-Za-z0-9]{1,4}){2,7})\b')


def _fetchall(query: str, args: tuple = ()) -> List[Dict[str, Any]]:
    cursor = db.conn.execute(query, args)
    return [{k: row[k] for k in row.keys()} for row in cursor.fetchall()]


def _own_account_iban_match(text: str, own_ibans: set) -> bool:
    """Vero se la causale cita l'IBAN di uno dei conti gia' censiti: quasi
    certamente un giroconto tra conti propri (bonifico interno), non una spesa
    o un'entrata reale. A differenza di pdf_import._extract_iban non serve
    validare qui la lunghezza del candidato: deve corrispondere ESATTAMENTE a
    uno dei pochi IBAN gia' censiti in own_ibans (tutti di lunghezza valida),
    quindi un candidato troppo corto o lungo semplicemente non trova match."""
    for m in _IBAN_RE.finditer(text):
        if re.sub(r'\s+', '', m.group(1)).upper() in own_ibans:
            return True
    return False


def _load_keywords(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    try:
        return [str(k).lower() for k in json.loads(raw) if k]
    except (json.JSONDecodeError, TypeError):
        return []


def _contains_keyword(text: str, keyword: str) -> bool:
    """Match sull'intera parola/frase (confini di parola), non substring: senza
    questo, keyword corte come "tari" (TARI, la tassa rifiuti) matcherebbero
    dentro parole del tutto estranee come "alimentari"."""
    return re.search(rf'\b{re.escape(keyword)}\b', text) is not None


def _keyword_match(text: str, categories: List[Dict[str, Any]]) -> Optional[int]:
    for cat in categories:
        if any(_contains_keyword(text, kw) for kw in cat['keywords']):
            return cat['id']
    return None


def _rule_matches(rule: Dict[str, Any], text: str, amount: float) -> bool:
    if rule['sign'] == 'negative' and amount >= 0:
        return False
    if rule['sign'] == 'positive' and amount <= 0:
        return False
    if rule['is_regex']:
        try:
            return re.search(rule['pattern'], text, re.IGNORECASE) is not None
        except re.error:
            return False
    return rule['pattern'].lower() in text


def _apply_rule(tx_id: int, rule: Dict[str, Any]) -> None:
    """Applica una regola utente (vedi import_rules): a differenza del
    keyword/AI match sotto, conferma subito la transazione (is_confirmed=1) e
    puo' impostare anche destinazione/persona, non solo la categoria - e' una
    scelta esplicita dell'utente, non un suggerimento da rivedere."""
    fields = ['category_id = ?', 'is_confirmed = 1']
    args: List[Any] = [rule['category_id']]
    if rule.get('destination'):
        fields.append('destination = ?')
        args.append(rule['destination'])
        if rule['destination'] == 'split':
            if rule.get('split_person_id'):
                fields.append('split_person_id = ?')
                args.append(rule['split_person_id'])
            if rule.get('split_ratio') is not None:
                fields.append('split_ratio = ?')
                args.append(rule['split_ratio'])
    if rule.get('paid_by_person_id'):
        fields.append('paid_by_person_id = ?')
        args.append(rule['paid_by_person_id'])
    args.append(tx_id)
    db.conn.execute(f"UPDATE transactions SET {', '.join(fields)} WHERE id = ?", tuple(args))


def _load_rules() -> List[Dict[str, Any]]:
    """Regole attive, valutate in ordine di priorita' decrescente (a parita'
    di priorita', le piu' vecchie prima): la prima che matcha vince, le
    successive non vengono nemmeno provate."""
    return _fetchall('SELECT * FROM import_rules WHERE is_active = 1 ORDER BY priority DESC, id ASC')


def _build_ai_prompt(pending: List[Dict[str, Any]], categories: List[Dict[str, Any]]) -> str:
    cats_text = '\n'.join(f"- id={c['id']}: {c['name']}" for c in categories)
    txs_text = '\n'.join(f"- id={t['id']}: {t['description']}" for t in pending)
    return f"""Sei un assistente che categorizza le spese di una famiglia italiana in base alla causale bancaria.

Categorie disponibili (usa solo questi id, non inventarne altri):
{cats_text}

Transazioni da categorizzare:
{txs_text}

Per ciascuna transazione scegli la categoria piu' probabile. Se nessuna e' plausibile, usa null per categoryId.

Rispondi SOLO con un array JSON valido (nessun testo extra, nessun blocco markdown), un elemento per transazione:
[{{"id": 123, "categoryId": 45, "confidence": 0.8}}]"""


# Con batch molto grandi la risposta rischia di superare il limite di token
# per la singola chiamata: si processa a gruppi di questa dimensione.
_AI_CHUNK_SIZE = 40


def categorize_batch(batch_id: str) -> int:
    """Categorizza le transazioni appena importate (stesso import_batch_id).
    Vedi _categorize_rows per la logica di categorizzazione vera e propria."""
    transactions = _fetchall(
        'SELECT id, description_raw, merchant_name, amount FROM transactions '
        'WHERE import_batch_id = ? AND category_id IS NULL AND ai_category_id IS NULL',
        (batch_id,),
    )
    return _categorize_rows(transactions)


def categorize_selected(ids: List[int]) -> Dict[str, int]:
    """Come categorize_batch, ma su un elenco di transazioni scelto a mano
    dall'utente in un momento qualunque (bottone "Riconosci categoria (AI)"
    sulla lista transazioni), non legato a un batch di import. Salta le
    transazioni che hanno gia' una categoria confermata o un suggerimento AI
    ancora da rivedere (stessa precondizione di categorize_batch): rilanciare
    l'AI su una transazione gia' categorizzata sovrascriverebbe silenziosamente
    una scelta (dell'utente o di un run precedente) invece di limitarsi a
    riempire le lacune. Restituisce {'categorized': N, 'skipped': M}."""
    if not ids:
        return {'categorized': 0, 'skipped': 0}
    placeholders = ','.join('?' * len(ids))
    transactions = _fetchall(
        f'SELECT id, description_raw, merchant_name, amount FROM transactions '
        f'WHERE id IN ({placeholders}) AND category_id IS NULL AND ai_category_id IS NULL',
        tuple(ids),
    )
    categorized = _categorize_rows(transactions)
    return {'categorized': categorized, 'skipped': len(ids) - categorized}


def _categorize_rows(transactions: List[Dict[str, Any]]) -> int:
    """Logica di categorizzazione condivisa da categorize_batch e
    categorize_selected: prima riconosce i giroconti verso conti propri
    (causale con l'IBAN di un altro conto gia' censito -> categoria
    'Trasferimenti'), poi un match deterministico e gratuito sulle parole
    chiave di ogni categoria (categories.ai_keywords), infine -solo per quelle
    rimaste senza match- una chiamata AI (a gruppi, non una per transazione).
    Imposta ai_category_id/ai_confidence lasciando is_confirmed=0: l'utente
    conferma dal banner "categorizzate da AI" gia' presente nel frontend.

    Restituisce il numero di transazioni a cui e' stata assegnata una
    categoria suggerita."""
    if not transactions:
        return 0

    rules = _load_rules()
    categories = [
        {'id': c['id'], 'name': c['name'], 'keywords': _load_keywords(c['ai_keywords'])}
        for c in _fetchall("SELECT id, name, ai_keywords FROM categories WHERE is_active = 1 AND type != 'transfer'")
    ]
    transfer_category = _fetchall("SELECT id FROM categories WHERE is_active = 1 AND type = 'transfer' LIMIT 1")
    transfer_category_id = transfer_category[0]['id'] if transfer_category else None
    own_ibans = {
        re.sub(r'\s+', '', row['iban']).upper()
        for row in _fetchall("SELECT iban FROM accounts WHERE iban IS NOT NULL AND iban != ''")
    }

    categorized = 0
    remaining = []
    for tx in transactions:
        text = f"{tx['description_raw'] or ''} {tx['merchant_name'] or ''}".lower()
        amount = tx.get('amount') or 0
        matched_rule = next((r for r in rules if _rule_matches(r, text, amount)), None)
        if matched_rule is not None:
            _apply_rule(tx['id'], matched_rule)
            categorized += 1
            continue
        if transfer_category_id is not None and own_ibans and _own_account_iban_match(text, own_ibans):
            db.conn.execute(
                'UPDATE transactions SET ai_category_id = ?, ai_confidence = ? WHERE id = ?',
                (transfer_category_id, 1.0, tx['id']),
            )
            categorized += 1
            continue
        category_id = _keyword_match(text, categories)
        if category_id is None:
            remaining.append({'id': tx['id'], 'description': tx['description_raw'] or tx['merchant_name'] or ''})
            continue
        db.conn.execute(
            'UPDATE transactions SET ai_category_id = ?, ai_confidence = ? WHERE id = ?',
            (category_id, 1.0, tx['id']),
        )
        categorized += 1
    db.conn.commit()

    if remaining and categories:
        valid_ids = {c['id'] for c in categories}
        for i in range(0, len(remaining), _AI_CHUNK_SIZE):
            chunk = remaining[i:i + _AI_CHUNK_SIZE]
            try:
                content = ai_client.ask_ai(_build_ai_prompt(chunk, categories), task_name='casaspese_categorize', max_tokens=2000)
                results = ai_client.parse_json_array(content)
            except ValueError as e:
                print(f'[categorize] categorizzazione AI fallita per {len(chunk)} transazioni: {e}', flush=True)
                continue
            for r in results:
                if not isinstance(r, dict):
                    continue
                category_id = r.get('categoryId')
                if r.get('id') is None or category_id not in valid_ids:
                    continue
                confidence = r.get('confidence')
                db.conn.execute(
                    'UPDATE transactions SET ai_category_id = ?, ai_confidence = ? WHERE id = ?',
                    (category_id, float(confidence) if isinstance(confidence, (int, float)) else 0.5, r['id']),
                )
                categorized += 1
            db.conn.commit()

    return categorized

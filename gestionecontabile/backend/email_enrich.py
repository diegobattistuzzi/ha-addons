from datetime import timedelta
from typing import Any, Dict, Optional

from dateutil.parser import parse as parse_date

from . import ai_client, db


def _fetchone(query: str, args: tuple = ()) -> Optional[Dict[str, Any]]:
    cursor = db.conn.execute(query, args)
    row = cursor.fetchone()
    return {k: row[k] for k in row.keys()} if row is not None else None


def _fetchall(query: str, args: tuple = ()) -> list:
    cursor = db.conn.execute(query, args)
    return [{k: row[k] for k in row.keys()} for row in cursor.fetchall()]


def extract_receipt_info(sender: str, subject: str, body: str, received_date: Optional[str] = None) -> Dict[str, Any]:
    """Chiede all'AI di estrarre venditore/importo/data/oggetto da una mail di
    conferma acquisto/pagamento (PayPal, Amazon, altri negozi online).

    received_date (se noto, dall'header IMAP 'Date' del messaggio) va passato
    esplicitamente: l'AI non ha altrimenti alcun modo di sapere quando la mail
    e' arrivata (prima non le veniva detto, e per mail senza una data esplicita
    nel corpo poteva "indovinare" una data qualsiasi, es. quella odierna,
    abbinando poi la ricevuta alla transazione sbagliata - vedi process_incoming_email
    per il controllo di coerenza aggiuntivo)."""
    truncated = (body or '')[:6000]
    received_line = f'Data di ricezione della mail: {received_date}\n' if received_date else ''
    prompt = f"""Sei un assistente che estrae informazioni da mail di conferma acquisto o pagamento
(es. PayPal, Amazon, altri negozi online).

Mittente: {sender}
Oggetto: {subject}
{received_line}
Corpo:
{truncated}

Rispondi SOLO con un oggetto JSON valido (nessun testo extra, nessun blocco markdown):
{{"merchant": "nome del venditore/negozio reale, o null se non individuabile", "amount": 42.50, "date": "YYYY-MM-DD", "description": "cosa e' stato acquistato se indicato, altrimenti null"}}

Regole:
- amount sempre un numero positivo (nessun segno)
- date nel formato YYYY-MM-DD: usa la data indicata nel corpo SOLO se la mail la dichiara esplicitamente come data dell'operazione; altrimenti usa la data di ricezione indicata sopra. Non inventare mai una data che non compare in uno dei due
- se non riesci a determinare con sicurezza un campo, usa null per quel campo"""

    content = ai_client.ask_ai(prompt, task_name='casaspese_email_receipt', max_tokens=500)
    return ai_client.parse_json_object(content)


# Stessa tolleranza usata da find_matching_transaction (abbinamento in tempo
# reale all'arrivo della mail) e dalle funzioni di ri-abbinamento sotto, cosi'
# il criterio "quanti giorni di distanza sono accettabili" e' UNO solo in
# tutto il modulo invece di poter divergere per caso tra i vari percorsi.
_MATCH_TOLERANCE_DAYS = 5


def find_matching_transaction(amount: Optional[float], date_str: Optional[str], tolerance_days: int = _MATCH_TOLERANCE_DAYS) -> Optional[Dict[str, Any]]:
    """Cerca una transazione importata (non manuale) non ancora arricchita, con
    importo praticamente identico e data vicina a quella della mail."""
    if amount is None or not date_str:
        return None
    try:
        center = parse_date(date_str).date()
    except (ValueError, TypeError):
        return None
    start = (center - timedelta(days=tolerance_days)).isoformat()
    end = (center + timedelta(days=tolerance_days)).isoformat()
    return _fetchone(
        "SELECT * FROM transactions WHERE amount < 0 AND ABS(ABS(amount) - ?) < 0.01 "
        "AND date BETWEEN ? AND ? AND import_source != 'manual' AND merchant_enriched = 0 "
        "ORDER BY ABS(julianday(date) - julianday(?)) LIMIT 1",
        (amount, start, end, center.isoformat()),
    )


def enrich_transaction(transaction_id: int, merchant: Optional[str], description: Optional[str]) -> None:
    tx = _fetchone('SELECT notes FROM transactions WHERE id = ?', (transaction_id,))
    if tx is None:
        return
    note_parts = [tx['notes']] if tx['notes'] else []
    if description:
        note_parts.append(f'Da email: {description}')
    new_notes = ' | '.join(note_parts) if note_parts else None
    db.conn.execute(
        'UPDATE transactions SET merchant_name = COALESCE(?, merchant_name), notes = ?, merchant_enriched = 1 WHERE id = ?',
        (merchant, new_notes, transaction_id),
    )
    db.conn.commit()


def process_incoming_email(sender: str, subject: str, body: str, received_date: Optional[str] = None) -> Dict[str, Any]:
    """Estrae i dati dalla mail, li salva come ricevuta e prova subito ad
    abbinarla a una transazione gia' importata. Se non trova nulla, la ricevuta
    resta in attesa: verra' ritentata al prossimo import di estratto conto
    (vedi match_pending_receipts_for_batch)."""
    info = extract_receipt_info(sender, subject, body, received_date)
    merchant = info.get('merchant')
    amount = info.get('amount')
    date = info.get('date')
    description = info.get('description')

    # Rete di sicurezza indipendente dal prompt: una ricevuta di
    # conferma acquisto/pagamento arriva per definizione a ridosso
    # dell'operazione, mai mesi/anni dopo. Se l'AI restituisce una data
    # troppo lontana da quella reale di ricezione (mail senza data esplicita
    # nel corpo -> l'AI puo' aver "indovinato"), si preferisce quella certa
    # invece di rischiare un abbinamento con la transazione sbagliata.
    if received_date:
        if not date:
            date = received_date
        else:
            try:
                if abs((parse_date(date).date() - parse_date(received_date).date()).days) > 60:
                    date = received_date
            except (ValueError, TypeError):
                date = received_date

    cursor = db.conn.execute(
        'INSERT INTO email_receipts (sender, subject, merchant, amount, date, item_description) VALUES (?, ?, ?, ?, ?, ?)',
        (sender, subject, merchant, amount, date, description),
    )
    receipt_id = cursor.lastrowid
    db.conn.commit()

    match = find_matching_transaction(amount, date)
    if match:
        enrich_transaction(match['id'], merchant, description)
        db.conn.execute('UPDATE email_receipts SET matched_transaction_id = ? WHERE id = ?', (match['id'], receipt_id))
        db.conn.commit()

    return {
        'receiptId': receipt_id,
        'merchant': merchant,
        'amount': amount,
        'date': date,
        'description': description,
        'matchedTransactionId': match['id'] if match else None,
    }


def _match_receipts_against(pending: list, pool: list) -> int:
    """Abbina ogni ricevuta email (senza match ancora) alla MIGLIOR
    transazione candidata nel pool dato: stesso importo (tolleranza 0.01) e
    data entro _MATCH_TOLERANCE_DAYS giorni, scegliendo tra i candidati quello
    con la data piu' vicina - non il primo che capita. Bug reale corretto qui:
    la versione precedente di match_pending_receipts_for_batch controllava
    SOLO l'importo, senza nessun vincolo di vicinanza nel tempo, e prendeva il
    primo candidato nell'ordine restituito dalla query - con due spese dello
    stesso importo nello stesso batch (es. due pizze da 11 euro in giorni
    diversi) poteva abbinare la ricevuta alla transazione sbagliata anche se
    l'altra era molto piu' vicina come data. Rimuove dal pool la transazione
    appena abbinata cosi' la stessa transazione non viene riusata per due
    ricevute diverse."""
    matched = 0
    for receipt in pending:
        if receipt['amount'] is None or not receipt['date']:
            continue
        try:
            receipt_date = parse_date(receipt['date']).date()
        except (ValueError, TypeError):
            continue
        best = None
        best_diff = None
        for tx in pool:
            if abs(abs(tx['amount']) - receipt['amount']) >= 0.01:
                continue
            try:
                tx_date = parse_date(tx['date']).date()
            except (ValueError, TypeError):
                continue
            diff = abs((tx_date - receipt_date).days)
            if diff > _MATCH_TOLERANCE_DAYS:
                continue
            if best is None or diff < best_diff:
                best, best_diff = tx, diff
        if best is None:
            continue
        enrich_transaction(best['id'], receipt['merchant'], receipt['item_description'])
        db.conn.execute('UPDATE email_receipts SET matched_transaction_id = ? WHERE id = ?', (best['id'], receipt['id']))
        db.conn.commit()
        pool.remove(best)
        matched += 1
        if not pool:
            break
    return matched


def match_pending_receipts_for_batch(batch_id: str) -> int:
    """Da chiamare dopo un import di estratto conto: prova ad abbinare le
    transazioni appena importate alle ricevute email ancora in attesa."""
    pending = _fetchall('SELECT * FROM email_receipts WHERE matched_transaction_id IS NULL')
    if not pending:
        return 0
    batch_txs = _fetchall(
        "SELECT * FROM transactions WHERE import_batch_id = ? AND amount < 0 AND merchant_enriched = 0",
        (batch_id,),
    )
    if not batch_txs:
        return 0
    return _match_receipts_against(pending, batch_txs)


def rematch_all_pending_receipts() -> int:
    """Ritenta l'abbinamento di TUTTE le ricevute email ancora in attesa
    contro TUTTE le transazioni non manuali non ancora arricchite, non solo
    quelle di un batch di import appena fatto (vedi match_pending_receipts_
    for_batch, limitato al batch corrente). Da richiamare a mano con il
    bottone "Riabbina mail": utile per ricevute rimaste in sospeso perche' la
    transazione e' stata importata in un momento diverso, o perche' un bug di
    matching precedente (vedi _match_receipts_against) le aveva scartate."""
    pending = _fetchall('SELECT * FROM email_receipts WHERE matched_transaction_id IS NULL')
    if not pending:
        return 0
    pool = _fetchall(
        "SELECT * FROM transactions WHERE amount < 0 AND import_source != 'manual' AND merchant_enriched = 0",
    )
    if not pool:
        return 0
    return _match_receipts_against(pending, pool)

import difflib
import hashlib
import json
import re
import uuid
import zipfile
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from dateutil.parser import parse as parse_date
from fastapi import APIRouter, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse

from .. import access, ai_client, categorize, config, db, email_enrich, pdf_import
from ..db import execute, fetchall, fetchone
from ..statement_parsing import (
    looks_like_cbi,
    looks_like_meal_voucher_export,
    parse_rows_from_cbi,
    parse_rows_from_csv,
    parse_rows_from_meal_voucher,
    parse_rows_from_xlsx,
)
from ..util import ensure_int
from .accounts import _opening_balance_category_id

router = APIRouter()


@router.get('/api/transactions')
def list_transactions(request: Request, response: Response):
    params = request.query_params
    current_person = access.get_current_person(request)
    filters = []
    args: List[Any] = []
    if month := params.get('month'):
        filters.append('date LIKE ?')
        args.append(f'{month}%')
    if account_id := ensure_int(params.get('accountId')):
        filters.append('account_id = ?')
        args.append(account_id)
    if category_id := ensure_int(params.get('categoryId')):
        filters.append('category_id = ?')
        args.append(category_id)
    if destination := params.get('destination'):
        filters.append('destination = ?')
        args.append(destination)
    if person_id := ensure_int(params.get('personId')):
        filters.append('paid_by_person_id = ?')
        args.append(person_id)
    if params.get('unconfirmed') == 'true':
        filters.append('is_confirmed = 0')
    elif params.get('confirmed') == 'true':
        filters.append('is_confirmed = 1')
    if reimbursable := params.get('reimbursable'):
        if reimbursable == 'pending':
            filters.append('is_reimbursable = 1 AND reimbursed_at IS NULL')
        elif reimbursable == 'reimbursed':
            filters.append('is_reimbursable = 1 AND reimbursed_at IS NOT NULL')
        elif reimbursable == 'all':
            filters.append('is_reimbursable = 1')
    if search := params.get('search'):
        filters.append('(merchant_name LIKE ? OR description_raw LIKE ? OR notes LIKE ?)')
        needle = f'%{search}%'
        args.extend([needle, needle, needle])
    vis_clause, vis_args = access.transaction_visibility(current_person)
    filters.append(vis_clause)
    args.extend(vis_args)
    where_sql = (' WHERE ' + ' AND '.join(filters)) if filters else ''

    total = fetchone(f'SELECT COUNT(*) AS c FROM transactions{where_sql}', tuple(args))['c']
    response.headers['X-Total-Count'] = str(total)

    sql = (
        'SELECT transactions.*, '
        '(SELECT COUNT(*) FROM documents WHERE documents.transaction_id = transactions.id) AS attachment_count, '
        '(SELECT id FROM email_receipts WHERE email_receipts.matched_transaction_id = transactions.id LIMIT 1) AS email_receipt_id '
        'FROM transactions' + where_sql + ' ORDER BY date DESC'
    )
    limit = ensure_int(params.get('limit')) or 200
    sql += ' LIMIT ?'
    args.append(limit)
    if offset := ensure_int(params.get('offset')):
        sql += ' OFFSET ?'
        args.append(offset)
    return fetchall(sql, tuple(args))


@router.get('/api/transactions/pending-ai')
def pending_ai(request: Request):
    current_person = access.get_current_person(request)
    vis_clause, vis_args = access.transaction_visibility(current_person)
    return fetchall(
        f'SELECT * FROM transactions WHERE is_confirmed = 0 AND ai_category_id IS NOT NULL AND {vis_clause} '
        'ORDER BY date DESC LIMIT 100',
        vis_args,
    )


@router.get('/api/transactions/duplicates')
def find_duplicate_transactions(request: Request):
    """Coppie di transazioni potenzialmente duplicate: stesso conto, stesso
    importo esatto, e date compatibili - a differenza di import_hash (che
    scarta solo duplicati esatti tra file importati con lo stesso hash, vedi
    _transaction_import_hash), copre anche una transazione inserita a mano
    che duplica una gia' importata, o due import da fonti diverse con lo
    stesso periodo. Date compatibili significa: un incrocio esatto tra
    date/value_date delle due transazioni (es. la data operazione dell'una
    coincide con la data valuta dell'altra), oppure - solo quando una delle
    due non ha una data valuta nota (import che non la fornisce, o inserimento
    manuale) - la vecchia finestra euristica di +/-3 giorni. Quando invece
    entrambe le transazioni hanno una data valuta ma nessuna combinazione
    coincide, non le consideriamo duplicate: avendo il dato piu' preciso non
    serve piu' la finestra larga. La somiglianza testuale NON e' un filtro
    rigido (solo un punteggio informativo restituito al client): due
    commissioni bancarie identiche nello stesso giorno per bonifici diversi
    sono un caso limite reale che va comunque mostrato all'utente, non
    nascosto perche' il testo combacia troppo bene."""
    current_person = access.get_current_person(request)
    vis_clause_a, vis_args_a = access.transaction_visibility(current_person, alias='t1')
    vis_clause_b, vis_args_b = access.transaction_visibility(current_person, alias='t2')
    saldo_init_id = _opening_balance_category_id()
    exclude_clause = ''
    exclude_args: tuple = ()
    if saldo_init_id is not None:
        exclude_clause = ' AND (t1.category_id IS NULL OR t1.category_id != ?) AND (t2.category_id IS NULL OR t2.category_id != ?)'
        exclude_args = (saldo_init_id, saldo_init_id)
    date_match_clause = (
        '('
        '  t1.date = t2.date OR t1.date = t2.value_date OR t1.value_date = t2.date'
        '  OR (t1.value_date IS NOT NULL AND t2.value_date IS NOT NULL AND t1.value_date = t2.value_date)'
        '  OR ('
        '    (t1.value_date IS NULL OR t2.value_date IS NULL)'
        '    AND ABS(julianday(t1.date) - julianday(t2.date)) <= 3'
        '  )'
        ')'
    )
    pairs = fetchall(
        'SELECT t1.id AS id_a, t2.id AS id_b '
        'FROM transactions t1 JOIN transactions t2 '
        '  ON t1.account_id = t2.account_id AND t1.amount = t2.amount AND t1.id < t2.id '
        f' AND {date_match_clause} '
        'LEFT JOIN transaction_dedup_dismissals d '
        '  ON d.transaction_id_a = t1.id AND d.transaction_id_b = t2.id '
        f'WHERE d.id IS NULL AND {vis_clause_a} AND {vis_clause_b}{exclude_clause} '
        'ORDER BY t1.date DESC LIMIT 200',
        vis_args_a + vis_args_b + exclude_args,
    )
    if not pairs:
        return []
    ids = {tx_id for pair in pairs for tx_id in (pair['id_a'], pair['id_b'])}
    placeholders = ','.join('?' * len(ids))
    rows = fetchall(f'SELECT * FROM transactions WHERE id IN ({placeholders})', tuple(ids))
    by_id = {row['id']: row for row in rows}

    def normalized(tx: Dict[str, Any]) -> str:
        text = tx.get('merchant_name') or tx.get('description_raw') or ''
        return re.sub(r'\s+', ' ', text).strip().lower()

    results = []
    for pair in pairs:
        tx_a, tx_b = by_id.get(pair['id_a']), by_id.get(pair['id_b'])
        if tx_a is None or tx_b is None:
            continue
        similarity = difflib.SequenceMatcher(None, normalized(tx_a), normalized(tx_b)).ratio()
        results.append({'a': tx_a, 'b': tx_b, 'similarity': round(similarity, 2)})
    results.sort(key=lambda r: r['similarity'], reverse=True)
    return results


@router.post('/api/transactions/duplicates/dismiss')
def dismiss_duplicate(payload: Dict[str, Any]):
    id_a, id_b = ensure_int(payload.get('transactionIdA')), ensure_int(payload.get('transactionIdB'))
    if id_a is None or id_b is None:
        raise HTTPException(status_code=400, detail='transactionIdA e transactionIdB obbligatori')
    lo, hi = (id_a, id_b) if id_a < id_b else (id_b, id_a)
    execute(
        'INSERT OR IGNORE INTO transaction_dedup_dismissals (transaction_id_a, transaction_id_b) VALUES (?, ?)',
        (lo, hi),
    )
    return {'dismissed': True}


@router.get('/api/transactions/{transaction_id}')
def get_transaction(transaction_id: int, request: Request):
    tx = fetchone('SELECT * FROM transactions WHERE id = ?', (transaction_id,))
    if tx is None or not access.can_see_transaction(tx, access.get_current_person(request)):
        raise HTTPException(status_code=404, detail='Not found')
    return tx


def _insert_transaction(payload: Dict[str, Any], import_source: str = 'manual') -> Dict[str, Any]:
    """Inserisce una transazione a partire da un payload gia' risolto (stessi
    campi di POST /api/transactions). Condivisa con /api/ha/add-expense, che
    risolve nomi (conto/categoria/persona) in id prima di chiamarla e passa
    import_source='ha-service' per tracciare il canale di provenienza."""
    is_reimbursable = bool(payload.get('isReimbursable', False))
    cursor = db.conn.execute(
        'INSERT INTO transactions (date, value_date, amount, currency, description_raw, merchant_name, category_id, account_id, '
        'destination, paid_by_person_id, split_person_id, split_ratio, is_cash, is_confirmed, import_source, notes, '
        'is_reimbursable, reimbursement_amount) '
        'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
        (
            payload['date'],
            payload.get('valueDate') or None,
            float(payload['amount']),
            payload.get('currency', 'EUR'),
            payload['description'],
            payload.get('merchantName') or payload['description'],
            ensure_int(payload.get('categoryId')),
            ensure_int(payload.get('accountId')),
            payload.get('destination', 'family'),
            ensure_int(payload.get('paidByPersonId')),
            ensure_int(payload.get('splitPersonId')),
            float(payload['splitRatio']) if payload.get('splitRatio') not in (None, '') else 0.5,
            int(bool(payload.get('isCash', False))),
            1,
            import_source,
            payload.get('notes'),
            int(is_reimbursable),
            float(payload['reimbursementAmount']) if is_reimbursable and payload.get('reimbursementAmount') not in (None, '') else None,
        ),
    )
    db.conn.commit()
    return fetchone('SELECT * FROM transactions WHERE id = ?', (cursor.lastrowid,))


@router.post('/api/transactions')
def create_transaction(payload: Dict[str, Any]):
    if not payload.get('date') or payload.get('amount') is None or not payload.get('description') or not ensure_int(payload.get('accountId')):
        raise HTTPException(status_code=400, detail='Campi obbligatori mancanti')
    return JSONResponse(status_code=201, content=_insert_transaction(payload))


@router.post('/api/transactions/ai-parse')
def ai_parse_transaction(payload: Dict[str, Any]):
    """Trasforma una spesa descritta in linguaggio naturale (es. '23€ pizza ieri
    sera con amex') in una bozza da precompilare nel form di inserimento
    manuale: l'utente la rivede e la conferma sempre a mano (stesso principio
    delle categorie suggerite dall'AI sugli import, mai un inserimento alla
    cieca) - questo endpoint non scrive nulla su transactions."""
    text = (payload.get('text') or '').strip()
    if not text:
        raise HTTPException(status_code=400, detail='Testo mancante')

    categories = fetchall("SELECT id, name FROM categories WHERE is_active = 1 AND type = 'expense' ORDER BY sort_order")
    accounts = fetchall('SELECT id, name FROM accounts WHERE is_active = 1')
    today = datetime.utcnow().strftime('%Y-%m-%d')
    cats_text = '\n'.join(f"- id={c['id']}: {c['name']}" for c in categories)
    accs_text = '\n'.join(f"- id={a['id']}: {a['name']}" for a in accounts)
    prompt = f"""Sei un assistente che trasforma la descrizione informale di una spesa in dati strutturati, per una famiglia italiana.

Data di oggi: {today}

Categorie disponibili (usa solo questi id, o null se nessuna e' plausibile):
{cats_text}

Conti disponibili (usa solo questi id, o null se il conto non e' menzionato o non lo riconosci):
{accs_text}

Testo della spesa: "{text}"

Rispondi SOLO con un oggetto JSON valido (nessun testo extra, nessun blocco markdown):
{{"amount": 23.50, "description": "descrizione sintetica della spesa", "date": "YYYY-MM-DD", "categoryId": 12, "accountId": 3}}

Regole:
- amount sempre un numero positivo
- date: risolvi riferimenti relativi ("ieri", "oggi", "lunedi' scorso") rispetto alla data di oggi indicata sopra, formato YYYY-MM-DD
- se un campo non e' determinabile con sicurezza, usa null per quel campo"""

    try:
        content = ai_client.ask_ai(prompt, task_name='casaspese_quick_add', max_tokens=300)
        data = ai_client.parse_json_object(content)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    return {
        'amount': data.get('amount'),
        'description': data.get('description'),
        'date': data.get('date'),
        'categoryId': ensure_int(data.get('categoryId')),
        'accountId': ensure_int(data.get('accountId')),
    }


@router.post('/api/transactions/ai-parse-receipt')
async def ai_parse_receipt(file: UploadFile = File(...)):
    """Come /api/transactions/ai-parse ma partendo da una foto di scontrino
    invece che da un testo libero: usata dalla schermata mobile di scansione.
    Come ai-parse, non scrive nulla - restituisce solo una bozza da rivedere."""
    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail='Immagine mancante')

    categories = fetchall("SELECT id, name FROM categories WHERE is_active = 1 AND type = 'expense' ORDER BY sort_order")
    today = datetime.utcnow().strftime('%Y-%m-%d')
    cats_text = '\n'.join(f"- id={c['id']}: {c['name']}" for c in categories)
    prompt = f"""Sei un assistente che legge una foto di uno scontrino/ricevuta italiana e ne estrae i dati.

Data di oggi (usala solo se sullo scontrino non compare una data leggibile): {today}

Categorie disponibili (usa solo questi id, o null se nessuna e' plausibile):
{cats_text}

Rispondi SOLO con un oggetto JSON valido (nessun testo extra, nessun blocco markdown):
{{"amount": 23.50, "merchantName": "nome esercente", "date": "YYYY-MM-DD", "categoryId": 12}}

Regole:
- amount e' il totale pagato (numero positivo)
- date nel formato YYYY-MM-DD
- se un campo non e' leggibile con sicurezza, usa null per quel campo"""

    try:
        content = ai_client.ask_ai_with_image(prompt, image_bytes, file.filename or 'scontrino.jpg')
        data = ai_client.parse_json_object(content)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    return {
        'amount': data.get('amount'),
        'merchantName': data.get('merchantName'),
        'date': data.get('date'),
        'categoryId': ensure_int(data.get('categoryId')),
    }


@router.put('/api/transactions/{transaction_id}')
def update_transaction(transaction_id: int, payload: Dict[str, Any], request: Request):
    tx = fetchone('SELECT * FROM transactions WHERE id = ?', (transaction_id,))
    if tx is None or not access.can_see_transaction(tx, access.get_current_person(request)):
        raise HTTPException(status_code=404, detail='Not found')
    # Il form di modifica non ha un campo merchantName separato: se l'utente
    # cambia la descrizione, aggiorna anche il nome visualizzato (merchant_name),
    # a meno che non sia gia' stato arricchito esplicitamente via merchantName.
    merchant_name = payload.get('merchantName', payload.get('description', tx['merchant_name']))
    is_reimbursable = bool(payload.get('isReimbursable', tx['is_reimbursable']))
    if not is_reimbursable:
        reimbursement_amount = None
    elif 'reimbursementAmount' in payload:
        reimbursement_amount = float(payload['reimbursementAmount']) if payload.get('reimbursementAmount') not in (None, '') else None
    else:
        reimbursement_amount = tx['reimbursement_amount']
    execute(
        'UPDATE transactions SET date = ?, value_date = ?, amount = ?, description_raw = ?, merchant_name = ?, category_id = ?, '
        'account_id = ?, destination = ?, paid_by_person_id = ?, split_person_id = ?, split_ratio = ?, is_cash = ?, '
        "is_confirmed = ?, notes = ?, is_reimbursable = ?, reimbursement_amount = ?, updated_at = (datetime('now')) WHERE id = ?",
        (
            payload.get('date', tx['date']),
            payload.get('valueDate', tx['value_date']) or None,
            float(payload['amount']) if payload.get('amount') not in (None, '') else tx['amount'],
            payload.get('description', tx['description_raw']),
            merchant_name,
            ensure_int(payload['categoryId']) if 'categoryId' in payload else tx['category_id'],
            ensure_int(payload['accountId']) if 'accountId' in payload else tx['account_id'],
            payload.get('destination', tx['destination']),
            ensure_int(payload['paidByPersonId']) if 'paidByPersonId' in payload else tx['paid_by_person_id'],
            ensure_int(payload['splitPersonId']) if 'splitPersonId' in payload else tx['split_person_id'],
            float(payload['splitRatio']) if payload.get('splitRatio') not in (None, '') else tx['split_ratio'],
            int(bool(payload.get('isCash', tx['is_cash']))),
            int(bool(payload.get('isConfirmed', tx['is_confirmed']))),
            payload.get('notes', tx['notes']),
            int(is_reimbursable),
            reimbursement_amount,
            transaction_id,
        ),
    )
    return fetchone('SELECT * FROM transactions WHERE id = ?', (transaction_id,))


@router.post('/api/transactions/{transaction_id}/toggle-reimbursed')
def toggle_reimbursed(transaction_id: int, request: Request):
    """Segna/riapre una spesa 'da rimborsare' quando l'azienda accredita (o
    smentisce) il rimborso. reimbursed_at NULL = ancora in attesa."""
    tx = fetchone('SELECT * FROM transactions WHERE id = ?', (transaction_id,))
    if tx is None or not access.can_see_transaction(tx, access.get_current_person(request)):
        raise HTTPException(status_code=404, detail='Not found')
    if not tx['is_reimbursable']:
        raise HTTPException(status_code=400, detail="La transazione non e' marcata come da rimborsare")
    new_value = None if tx['reimbursed_at'] else db.conn.execute("SELECT datetime('now')").fetchone()[0]
    execute('UPDATE transactions SET reimbursed_at = ? WHERE id = ?', (new_value, transaction_id))
    return fetchone('SELECT * FROM transactions WHERE id = ?', (transaction_id,))


@router.delete('/api/transactions/{transaction_id}')
def delete_transaction(transaction_id: int, request: Request):
    tx = fetchone('SELECT * FROM transactions WHERE id = ?', (transaction_id,))
    if tx is None or not access.can_see_transaction(tx, access.get_current_person(request)):
        raise HTTPException(status_code=404, detail='Not found')
    execute('DELETE FROM transactions WHERE id = ?', (transaction_id,))
    return JSONResponse(status_code=204, content=None)


def _confirm_transaction_ids(ids: List[int], current_person: Optional[Dict[str, Any]]) -> int:
    """Conferma la categoria AI suggerita per una lista di id (stessa logica
    di POST /api/transactions/confirm-bulk), condivisa con
    POST /api/ha/approve-pending."""
    confirmed = 0
    for tx_id in ids:
        tx = fetchone('SELECT * FROM transactions WHERE id = ?', (tx_id,))
        if tx is None or not access.can_see_transaction(tx, current_person):
            continue
        if tx['ai_category_id'] is not None:
            execute('UPDATE transactions SET category_id = ?, is_confirmed = 1 WHERE id = ?', (tx['ai_category_id'], tx_id))
            confirmed += 1
    return confirmed


@router.post('/api/transactions/confirm-bulk')
def confirm_bulk(payload: Dict[str, Any], request: Request):
    ids = [ensure_int(x) for x in payload.get('ids', []) if ensure_int(x) is not None]
    current_person = access.get_current_person(request)
    return {'confirmed': _confirm_transaction_ids(ids, current_person)}


@router.post('/api/transactions/reject-ai-bulk')
def reject_ai_bulk(payload: Dict[str, Any], request: Request):
    """Scarta il suggerimento AI (categoria + confidenza) senza confermare ne'
    eliminare la transazione: torna semplicemente 'da categorizzare a mano'."""
    ids = [ensure_int(x) for x in payload.get('ids', []) if ensure_int(x) is not None]
    current_person = access.get_current_person(request)
    rejected = 0
    for tx_id in ids:
        tx = fetchone('SELECT * FROM transactions WHERE id = ?', (tx_id,))
        if tx is None or tx['is_confirmed'] or not access.can_see_transaction(tx, current_person):
            continue
        execute('UPDATE transactions SET ai_category_id = NULL, ai_confidence = NULL WHERE id = ?', (tx_id,))
        rejected += 1
    return {'rejected': rejected}


@router.post('/api/transactions/bulk-update')
def bulk_update_transactions(payload: Dict[str, Any], request: Request):
    """Sposta in blocco una lista di transazioni su categoria/conto/destinazione/
    pagato da/stato conferma. Applica solo i campi presenti nel payload,
    lasciando invariati gli altri (stesso comportamento di update_transaction)."""
    ids = [ensure_int(x) for x in payload.get('ids', []) if ensure_int(x) is not None]
    if not ids:
        return {'updated': 0, 'skipped': 0}
    current_person = access.get_current_person(request)
    updated = 0
    for tx_id in ids:
        tx = fetchone('SELECT * FROM transactions WHERE id = ?', (tx_id,))
        if tx is None or not access.can_see_transaction(tx, current_person):
            continue
        if 'categoryId' in payload:
            category_id = ensure_int(payload['categoryId'])
        elif payload.get('isConfirmed') and tx['category_id'] is None and tx['ai_category_id'] is not None:
            # Confermare in blocco senza scegliere esplicitamente una categoria
            # (es. pulsante "Conferma" della barra di selezione) deve accettare
            # la proposta AI come per la conferma singola/da banner, non
            # lasciare la transazione "confermata" ma senza categoria - bug
            # reale: prima qui restava category_id NULL nonostante ai_category_id
            # gia' presente.
            category_id = tx['ai_category_id']
        else:
            category_id = tx['category_id']
        execute(
            'UPDATE transactions SET category_id = ?, account_id = ?, destination = ?, paid_by_person_id = ?, '
            "is_confirmed = ?, is_reimbursable = ?, updated_at = (datetime('now')) WHERE id = ?",
            (
                category_id,
                ensure_int(payload['accountId']) if 'accountId' in payload else tx['account_id'],
                payload.get('destination', tx['destination']),
                ensure_int(payload['paidByPersonId']) if 'paidByPersonId' in payload else tx['paid_by_person_id'],
                int(bool(payload.get('isConfirmed', tx['is_confirmed']))),
                int(bool(payload.get('isReimbursable', tx['is_reimbursable']))),
                tx_id,
            ),
        )
        updated += 1
    return {'updated': updated, 'skipped': len(ids) - updated}


@router.post('/api/transactions/categorize-ai')
def categorize_ai_bulk(payload: Dict[str, Any]):
    """Rilancia a mano il riconoscimento AI della categoria su una lista di
    transazioni scelte dall'utente in un momento qualunque (non legate a un
    import appena fatto) - es. spese inserite manualmente o importate prima
    che questa categoria esistesse. Vedi categorize.categorize_selected per
    la logica (salta quelle gia' categorizzate/con suggerimento pendente)."""
    ids = [ensure_int(x) for x in payload.get('ids', []) if ensure_int(x) is not None]
    return categorize.categorize_selected(ids)


@router.post('/api/transactions/bulk-flip-sign')
def bulk_flip_sign_transactions(payload: Dict[str, Any], request: Request):
    """Inverte il segno dell'importo di una lista di transazioni, es. per
    correggere import/inserimenti in cui entrate e uscite sono state registrate
    con il segno sbagliato."""
    ids = [ensure_int(x) for x in payload.get('ids', []) if ensure_int(x) is not None]
    if not ids:
        return {'updated': 0, 'skipped': 0}
    current_person = access.get_current_person(request)
    updated = 0
    for tx_id in ids:
        tx = fetchone('SELECT * FROM transactions WHERE id = ?', (tx_id,))
        if tx is None or not access.can_see_transaction(tx, current_person):
            continue
        execute(
            "UPDATE transactions SET amount = -amount, updated_at = (datetime('now')) WHERE id = ?",
            (tx_id,),
        )
        updated += 1
    return {'updated': updated, 'skipped': len(ids) - updated}


@router.post('/api/transactions/bulk-delete')
def bulk_delete_transactions(payload: Dict[str, Any], request: Request):
    """Elimina in blocco una lista di transazioni, es. per ripulire un import
    sbagliato (conto/segno errato) prima di reimportare."""
    ids = [ensure_int(x) for x in payload.get('ids', []) if ensure_int(x) is not None]
    if not ids:
        return {'deleted': 0, 'skipped': 0}
    current_person = access.get_current_person(request)
    deleted = 0
    for tx_id in ids:
        tx = fetchone('SELECT * FROM transactions WHERE id = ?', (tx_id,))
        if tx is None or not access.can_see_transaction(tx, current_person):
            continue
        execute('DELETE FROM transactions WHERE id = ?', (tx_id,))
        deleted += 1
    return {'deleted': deleted, 'skipped': len(ids) - deleted}


def _match_account_by_iban(account_info: Optional[Dict[str, Any]]) -> Optional[int]:
    """Cerca un conto gia' censito con lo stesso IBAN individuato dall'AI
    nell'intestazione dell'estratto conto, per suggerire/selezionare il conto
    automaticamente quando l'utente non ne ha scelto uno."""
    if not account_info or not account_info.get('iban'):
        return None
    iban = str(account_info['iban']).replace(' ', '').upper()
    match = fetchone("SELECT id FROM accounts WHERE REPLACE(UPPER(iban), ' ', '') = ?", (iban,))
    return match['id'] if match else None


def _transaction_import_hash(account_id: Optional[int], date: str, amount: float, description: str) -> str:
    """Impronta deterministica di una transazione importata (stesso conto,
    data, importo arrotondato al centesimo, descrizione normalizzata): usata
    con il vincolo UNIQUE su transactions.import_hash per scartare i
    duplicati. La colonna esisteva gia' nello schema (pensata per un futuro
    sync bancario automatico, mai realizzato) ma
    _finalize_import non la calcolava mai, quindi il vincolo UNIQUE non
    scartava nulla (piu' righe con import_hash NULL non sono in conflitto tra
    loro in SQLite) - bug reale: reimportare lo stesso estratto, o importare
    due estratti con periodi che si sovrappongono, duplicava silenziosamente
    ogni transazione. Normalizziamo la descrizione (minuscolo, spazi
    collassati) perche' la stessa causale puo' arrivare con spaziatura/maiuscole
    leggermente diverse tra un tentativo di import e l'altro (es. una ricetta
    regex diversa generata dall'AI la seconda volta)."""
    normalized_description = re.sub(r'\s+', ' ', description or '').strip().lower()
    raw = f'{account_id}|{date}|{round(float(amount), 2)}|{normalized_description}'
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def _reconciliation_pool(account_id: Optional[int]) -> List[Dict[str, Any]]:
    """Transazioni inserite a mano su questo conto e non ancora legate a nessun
    estratto conto (import_batch_id NULL): candidate a essere riconciliate con
    le righe dell'import appena caricato invece di restare duplicate come riga
    separata (vedi _find_reconciliation_candidate)."""
    return fetchall(
        "SELECT * FROM transactions WHERE account_id = ? AND import_source = 'manual' AND import_batch_id IS NULL",
        (account_id,),
    )


def _dates_compatible(bank_date: str, bank_value_date: Optional[str], manual_date: str, manual_value_date: Optional[str]) -> bool:
    bank_dates = {bank_date} | ({bank_value_date} if bank_value_date else set())
    manual_dates = {manual_date} | ({manual_value_date} if manual_value_date else set())
    if bank_dates & manual_dates:
        return True
    try:
        return abs((parse_date(bank_date).date() - parse_date(manual_date).date()).days) <= 3
    except (ValueError, TypeError):
        return False


def _find_reconciliation_candidate(pool: List[Dict[str, Any]], tx: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Sceglie, tra le transazioni manuali candidate sullo stesso conto, quella
    con importo uguale (tolleranza di arrotondamento) e data compatibile piu'
    vicina alla riga bancaria - stessa logica di /api/transactions/duplicates
    (incrocio esatto date/value_date, o finestra di 3 giorni), applicata qui
    in fase di import invece che lasciata a un controllo manuale successivo."""
    best, best_diff = None, None
    for candidate in pool:
        if abs(float(candidate['amount']) - float(tx['amount'])) >= 0.01:
            continue
        if not _dates_compatible(tx['date'], tx.get('value_date'), candidate['date'], candidate.get('value_date')):
            continue
        try:
            diff = abs((parse_date(tx['date']).date() - parse_date(candidate['date']).date()).days)
        except (ValueError, TypeError):
            diff = 0
        if best is None or diff < best_diff:
            best, best_diff = candidate, diff
    return best


def _reconcile_transaction(candidate_id: int, tx: Dict[str, Any], document_id: int, batch_id: str, import_hash: str) -> None:
    """Lega la transazione manuale gia' esistente all'estratto conto appena
    importato invece di inserirne una seconda: aggiorna solo i campi che
    provano/precisano il movimento bancario (data valuta, riferimento al
    documento e al batch), senza toccare categoria/note/destinazione/importo
    gia' scelti a mano dall'utente."""
    db.conn.execute(
        'UPDATE transactions SET value_date = COALESCE(value_date, ?), document_id = ?, import_batch_id = ?, import_hash = COALESCE(import_hash, ?) WHERE id = ?',
        (tx.get('value_date'), document_id, batch_id, import_hash, candidate_id),
    )


def _finalize_import(
    parsed: List[Dict[str, Any]],
    data: bytes,
    filename: str,
    content_type: Optional[str],
    account_id: Optional[int],
    import_source: str,
    used_ai: bool,
    detected_account: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Salva il file, inserisce le transazioni parsate e prova gli arricchimenti
    automatici (carta di credito collegata, ricevute email in attesa). Condivisa
    da import CSV/XLSX (sincrono) e import PDF (streaming).

    detected_account e' quanto l'AI ha individuato nell'intestazione del PDF
    (bankName/iban/cardNumber): solo informativo, non influisce sul conto gia'
    risolto in account_id (la selezione dell'account tramite IBAN avviene
    prima di chiamare questa funzione, vedi _match_account_by_iban)."""
    account = fetchone('SELECT ownership, owner_id FROM accounts WHERE id = ?', (account_id,)) if account_id else None
    # Un conto personale segrega le sue transazioni come spesa personale del suo
    # intestatario: non devono comparire tra le spese comuni. Vedi access.py.
    is_personal_account = bool(account and account['ownership'] == 'personal')
    destination = 'personal' if is_personal_account else 'family'
    paid_by_person_id = account['owner_id'] if is_personal_account else None

    batch_id = uuid.uuid4().hex
    safe_name = filename.replace('/', '_').replace('\\', '_')
    stored_path = config.DOCUMENTS_DIR / f'{batch_id}_{safe_name}'
    stored_path.write_bytes(data)
    doc_cursor = db.conn.execute(
        'INSERT INTO documents (filename, stored_path, mime_type, size_bytes, account_id, import_batch_id) VALUES (?, ?, ?, ?, ?, ?)',
        (filename, str(stored_path), content_type, len(data), account_id, batch_id),
    )
    document_id = doc_cursor.lastrowid

    # Riga di pagamento saldo carta rilevata da pdf_import (isCardSettlement,
    # vedi _CARD_SETTLEMENT_RE): e' strutturalmente un trasferimento interno
    # (non una spesa/entrata da categorizzare), quindi le assegnamo subito la
    # categoria Trasferimenti con la stessa confidenza 1.0 usata per i
    # giroconti riconosciuti per IBAN in categorize.categorize_batch, invece
    # di lasciarla passare per il matching a parole chiave.
    transfer_category = fetchone("SELECT id FROM categories WHERE is_active = 1 AND type = 'transfer' LIMIT 1")
    transfer_category_id = transfer_category['id'] if transfer_category else None

    reconciliation_pool = _reconciliation_pool(account_id)
    reconciled = []
    imported = 0
    duplicates = 0
    for tx in parsed:
        try:
            candidate = _find_reconciliation_candidate(reconciliation_pool, tx)
            if candidate is not None:
                reconciliation_pool.remove(candidate)
                import_hash = _transaction_import_hash(account_id, tx['date'], tx['amount'], tx['description'])
                _reconcile_transaction(candidate['id'], tx, document_id, batch_id, import_hash)
                reconciled.append({
                    'transactionId': candidate['id'],
                    'description': candidate['description_raw'],
                    'amount': candidate['amount'],
                    'date': candidate['date'],
                })
                continue
            is_card_settlement = bool(tx.get('isCardSettlement')) and transfer_category_id is not None
            import_hash = _transaction_import_hash(account_id, tx['date'], tx['amount'], tx['description'])
            cursor = db.conn.execute(
                'INSERT OR IGNORE INTO transactions (date, value_date, amount, description_raw, merchant_name, account_id, destination, paid_by_person_id, is_confirmed, import_source, import_batch_id, notes, document_id, ai_category_id, ai_confidence, import_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                (
                    tx['date'],
                    tx.get('value_date'),
                    float(tx['amount']),
                    tx['description'],
                    tx['description'],
                    account_id,
                    destination,
                    paid_by_person_id,
                    0,
                    import_source,
                    batch_id,
                    None,
                    document_id,
                    transfer_category_id if is_card_settlement else None,
                    1.0 if is_card_settlement else None,
                    import_hash,
                ),
            )
            if cursor.rowcount:
                imported += 1
            else:
                duplicates += 1
        except Exception:
            continue
    db.conn.commit()

    # Se questo conto e' il conto di appoggio di una carta di credito, prova a
    # riconoscere l'addebito riepilogativo mensile per evitare la doppia conta
    # (spesa gia' registrata sulla carta + addebito unico sul c/c).
    suggested_transfers = []
    if account_id:
        linked_cards = fetchall('SELECT id, name FROM accounts WHERE settlement_account_id = ?', (account_id,))
        if linked_cards:
            batch_txs = fetchall(
                'SELECT id, date, amount, description_raw FROM transactions WHERE import_batch_id = ? AND amount < 0',
                (batch_id,),
            )
            for card in linked_cards:
                for candidate in batch_txs:
                    window_start = (parse_date(candidate['date']) - timedelta(days=45)).date().isoformat()
                    card_total = fetchone(
                        'SELECT COALESCE(SUM(ABS(amount)),0) AS total FROM transactions '
                        'WHERE account_id = ? AND amount < 0 AND date > ? AND date <= ?',
                        (card['id'], window_start, candidate['date']),
                    )['total']
                    if card_total <= 0:
                        continue
                    tolerance = max(card_total * 0.02, 3.0)
                    if abs(card_total - abs(candidate['amount'])) <= tolerance:
                        suggested_transfers.append({
                            'transactionId': candidate['id'],
                            'description': candidate['description_raw'],
                            'amount': candidate['amount'],
                            'date': candidate['date'],
                            'cardAccountId': card['id'],
                            'cardAccountName': card['name'],
                            'matchedCardTotal': round(card_total, 2),
                        })

    # Riprova ad abbinare le ricevute email (PayPal/Amazon/...) ancora in attesa
    # alle transazioni appena importate (es. l'estratto conto arriva dopo la mail).
    enriched_from_email = email_enrich.match_pending_receipts_for_batch(batch_id)

    # Suggerisce una categoria (parole chiave, poi AI solo per il resto) per le
    # transazioni appena importate: restano da confermare (is_confirmed=0), il
    # banner "categorizzate da AI" del frontend le mostra per l'approvazione.
    ai_categorized = categorize.categorize_batch(batch_id)

    return {
        'count': imported,
        'total': len(parsed),
        'duplicates': duplicates,
        'reconciled': len(reconciled),
        'reconciledTransactions': reconciled,
        'usedAi': used_ai,
        'bank': (detected_account or {}).get('bankName'),
        'signWarning': (detected_account or {}).get('signWarning'),
        'reconciliationWarning': (detected_account or {}).get('reconciliationWarning'),
        'detectedAccount': detected_account,
        'accountId': account_id,
        'filename': filename,
        'preview': parsed[:5],
        'suggestedTransfers': suggested_transfers,
        'enrichedFromEmail': enriched_from_email,
        'aiCategorized': ai_categorized,
    }


@router.post('/api/transactions/import')
def import_transactions(file: UploadFile = File(...), accountId: Optional[str] = Form(None)):
    data = file.file.read()
    name = file.filename.lower()
    used_ai = False
    detected_account = None
    account_id = ensure_int(accountId)
    # Il conto e' gia' noto qui solo se l'utente lo ha selezionato prima di
    # caricare il file (per PDF/CBI viene invece dedotto dopo il parsing via
    # IBAN, quindi per quei formati resta sull'euristica automatica). Vedi
    # accounts.amount_sign_mode: consente di correggere per-conto i casi in
    # cui l'euristica sul testo del preambolo sbaglia (es. American Express).
    sign_mode = 'auto'
    if account_id:
        account_row = fetchone('SELECT amount_sign_mode FROM accounts WHERE id = ?', (account_id,))
        if account_row and account_row['amount_sign_mode']:
            sign_mode = account_row['amount_sign_mode']
    if name.endswith('.pdf'):
        text = pdf_import.extract_pdf_text(data)
        if not text.strip():
            raise HTTPException(
                status_code=400,
                detail='PDF non leggibile o vuoto. Assicurati che il PDF non sia scansionato come immagine.',
            )
        try:
            detected_account, parsed = pdf_import.ai_extract_transactions_from_pdf(text, file.filename, data)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        used_ai = True
        import_source = 'pdf'
        account_id = account_id or _match_account_by_iban(detected_account)
    elif (name.endswith('.xlsx') or name.endswith('.xls')) and looks_like_meal_voucher_export(data):
        parsed = parse_rows_from_meal_voucher(data)
        import_source = 'meal_voucher'
    elif name.endswith('.xlsx') or name.endswith('.xls'):
        try:
            parsed = parse_rows_from_xlsx(data, sign_mode)
            import_source = 'excel'
        except zipfile.BadZipFile:
            # Alcune banche esportano un file .xlsx che in realta' e' un testo
            # CSV rinominato (non uno zip/xlsx vero) - bug reale trovato su un
            # export reale che openpyxl rifiutava con BadZipFile.
            try:
                parsed = parse_rows_from_csv(data, sign_mode)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))
            import_source = 'csv'
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    elif looks_like_cbi(data):
        detected_account, parsed = parse_rows_from_cbi(data)
        import_source = 'cbi'
        account_id = account_id or _match_account_by_iban(detected_account)
    else:
        try:
            parsed = parse_rows_from_csv(data, sign_mode)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        import_source = 'csv'
    if not parsed:
        raise HTTPException(status_code=422, detail='Nessuna transazione trovata nel file')

    return _finalize_import(
        parsed, data, file.filename, file.content_type, account_id, import_source, used_ai, detected_account,
    )


@router.post('/api/transactions/import-pdf-stream')
def import_pdf_stream(file: UploadFile = File(...), accountId: Optional[str] = Form(None)):
    """Come /api/transactions/import per i PDF, ma risponde con un flusso SSE a
    fasi (estrazione testo -> analisi formato con AI -> pattern applicato in
    locale) invece che con un'unica risposta: utile perche' la chiamata AI, pur
    piccola (analizza solo un campione per ricavare il pattern di estrazione),
    puo' comunque richiedere qualche secondo. Evento finale 'done' con lo
    stesso payload di /api/transactions/import, oppure 'error'."""
    data = file.file.read()
    filename = file.filename
    content_type = file.content_type
    account_id = ensure_int(accountId)

    def sse(event: str, payload: Dict[str, Any]) -> str:
        return f'event: {event}\ndata: {json.dumps(payload)}\n\n'

    def event_stream():
        text = pdf_import.extract_pdf_text(data)
        if not text.strip():
            yield sse('error', {'detail': 'PDF non leggibile o vuoto. Assicurati che il PDF non sia scansionato come immagine.'})
            return
        yield sse('stage', {'message': "Testo estratto dal PDF, analisi del formato con l'AI..."})

        try:
            detected_account, parsed = pdf_import.ai_extract_transactions_from_pdf(text, filename, data)
        except ValueError as e:
            yield sse('error', {'detail': str(e)})
            return

        if detected_account:
            yield sse('account', detected_account)
        yield sse('progress', {'count': len(parsed)})

        resolved_account_id = account_id or _match_account_by_iban(detected_account)
        result = _finalize_import(parsed, data, filename, content_type, resolved_account_id, 'pdf', True, detected_account)
        yield sse('done', result)

    return StreamingResponse(event_stream(), media_type='text/event-stream')

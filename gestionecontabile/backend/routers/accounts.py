import json
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from .. import access, db
from ..db import execute, fetchall, fetchone
from ..util import ensure_int

router = APIRouter()


def _opening_balance_category_id() -> Optional[int]:
    row = fetchone("SELECT id FROM categories WHERE code = 'SALDO_INIT'")
    return row['id'] if row else None


def _compute_account_balances() -> Dict[int, float]:
    """Saldo di ogni conto = importo dell'ultimo checkpoint 'saldo iniziale'
    (per data, vedi POST /api/accounts/{id}/opening-balance) + la somma di
    tutti i movimenti (esclusi altri checkpoint) datati dopo quel checkpoint.
    Un conto senza alcun checkpoint somma semplicemente tutto lo storico
    (comportamento invariato per i conti creati prima di questa funzionalita').
    Due query per TUTTI i conti invece di un ciclo per-conto."""
    cat_id = _opening_balance_category_id()
    if cat_id is None:
        return {}
    checkpoints = fetchall(
        '''SELECT account_id, cp_date, cp_amount FROM (
             SELECT account_id, date AS cp_date, amount AS cp_amount,
                    ROW_NUMBER() OVER (PARTITION BY account_id ORDER BY date DESC, id DESC) AS rn
             FROM transactions WHERE category_id = ?
           ) WHERE rn = 1''',
        (cat_id,),
    )
    cp_by_account = {row['account_id']: (row['cp_date'], row['cp_amount']) for row in checkpoints}
    sums_after = fetchall(
        '''SELECT t.account_id AS account_id, COALESCE(SUM(t.amount),0) AS total
           FROM transactions t
           LEFT JOIN (
             SELECT account_id, date AS cp_date,
                    ROW_NUMBER() OVER (PARTITION BY account_id ORDER BY date DESC, id DESC) AS rn
             FROM transactions WHERE category_id = ?
           ) cp ON cp.account_id = t.account_id AND cp.rn = 1
           WHERE (t.category_id IS NULL OR t.category_id != ?) AND t.date > COALESCE(cp.cp_date, '0000-00-00')
           GROUP BY t.account_id''',
        (cat_id, cat_id),
    )
    sum_by_account = {row['account_id']: row['total'] for row in sums_after}
    account_ids = set(cp_by_account) | set(sum_by_account)
    return {
        account_id: cp_by_account.get(account_id, (None, 0.0))[1] + sum_by_account.get(account_id, 0.0)
        for account_id in account_ids
    }


def _with_computed_balance(row: Optional[Dict[str, Any]], balances: Optional[Dict[int, float]] = None) -> Optional[Dict[str, Any]]:
    if row is None:
        return None
    if balances is None:
        balances = _compute_account_balances()
    row['balance'] = round(balances.get(row['id'], 0.0), 2)
    return row


@router.get('/api/accounts')
def list_accounts(request: Request):
    current_person = access.get_current_person(request)
    vis_clause, vis_args = access.account_visibility(current_person)
    rows = fetchall(f'SELECT * FROM accounts WHERE is_active = 1 AND {vis_clause} ORDER BY id', vis_args)
    balances = _compute_account_balances()
    return [_with_computed_balance(row, balances) for row in rows]


@router.get('/api/accounts/{account_id}')
def get_account(account_id: int, request: Request):
    account = fetchone('SELECT * FROM accounts WHERE id = ?', (account_id,))
    if account is None or not access.can_see_account(account, access.get_current_person(request)):
        raise HTTPException(status_code=404, detail='Not found')
    return _with_computed_balance(account)


@router.get('/api/accounts/{account_id}/running-balances')
def account_running_balances(account_id: int, request: Request):
    """Saldo progressivo dopo ciascuna transazione del conto: stessa logica di
    _compute_account_balances (checkpoint 'saldo iniziale' + somma movimenti
    successivi) ma per singola riga, cosi' la vista Transazioni puo' mostrare
    una colonna 'Progressivo' filtrando su un conto solo. Calcolato sempre
    sull'intero storico del conto, indipendente da eventuali altri filtri
    applicati in UI (categoria, testo, ...): quelli nasconderebbero movimenti
    intermedi e falserebbero il progressivo se venisse ricalcolato lato client
    solo sulle righe visibili."""
    account = fetchone('SELECT * FROM accounts WHERE id = ?', (account_id,))
    if account is None or not access.can_see_account(account, access.get_current_person(request)):
        raise HTTPException(status_code=404, detail='Not found')
    cat_id = _opening_balance_category_id()
    checkpoint = None
    if cat_id is not None:
        checkpoint = fetchone(
            'SELECT date AS cp_date, amount AS cp_amount FROM transactions '
            'WHERE account_id = ? AND category_id = ? ORDER BY date DESC, id DESC LIMIT 1',
            (account_id, cat_id),
        )
    cp_date = checkpoint['cp_date'] if checkpoint else '0000-00-00'
    running = checkpoint['cp_amount'] if checkpoint else 0.0
    if cat_id is not None:
        rows = fetchall(
            'SELECT id, amount FROM transactions '
            'WHERE account_id = ? AND (category_id IS NULL OR category_id != ?) AND date > ? '
            'ORDER BY date ASC, id ASC',
            (account_id, cat_id, cp_date),
        )
    else:
        rows = fetchall(
            'SELECT id, amount FROM transactions WHERE account_id = ? AND date > ? ORDER BY date ASC, id ASC',
            (account_id, cp_date),
        )
    result = {}
    for row in rows:
        running += row['amount']
        result[row['id']] = round(running, 2)
    return result


@router.post('/api/accounts')
def create_account(payload: Dict[str, Any]):
    if not payload.get('name', '').strip():
        raise HTTPException(status_code=400, detail='Nome obbligatorio')
    cursor = db.conn.execute(
        'INSERT INTO accounts (name, bank, type, ownership, owner_id, co_owners, iban, color, balance, settlement_account_id, card_number, amount_sign_mode) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
        (
            payload['name'].strip(),
            payload.get('bank', 'other'),
            payload.get('type', 'checking'),
            payload.get('ownership', 'shared'),
            ensure_int(payload.get('ownerId')),
            json.dumps(payload.get('coOwners')) if payload.get('coOwners') is not None else None,
            payload.get('iban'),
            payload.get('color'),
            float(payload['balance']) if payload.get('balance') not in (None, '') else None,
            ensure_int(payload.get('settlementAccountId')),
            payload.get('cardNumber'),
            payload.get('amountSignMode', 'auto'),
        ),
    )
    db.conn.commit()
    created = fetchone('SELECT * FROM accounts WHERE id = ?', (cursor.lastrowid,))
    return JSONResponse(status_code=201, content=_with_computed_balance(created))


@router.put('/api/accounts/{account_id}')
def update_account(account_id: int, payload: Dict[str, Any]):
    account = fetchone('SELECT * FROM accounts WHERE id = ?', (account_id,))
    if account is None:
        raise HTTPException(status_code=404, detail='Not found')
    if payload.get('name') is not None and not payload['name'].strip():
        raise HTTPException(status_code=400, detail='Nome obbligatorio')
    execute(
        'UPDATE accounts SET name = ?, bank = ?, type = ?, ownership = ?, owner_id = ?, co_owners = ?, iban = ?, color = ?, balance = ?, is_active = ?, settlement_account_id = ?, card_number = ?, amount_sign_mode = ? WHERE id = ?',
        (
            payload.get('name', account['name']).strip(),
            payload.get('bank', account['bank']),
            payload.get('type', account['type']),
            payload.get('ownership', account['ownership']),
            ensure_int(payload['ownerId']) if 'ownerId' in payload else account['owner_id'],
            json.dumps(payload['coOwners']) if 'coOwners' in payload and payload['coOwners'] is not None else account['co_owners'],
            payload.get('iban', account['iban']),
            payload.get('color', account['color']),
            float(payload['balance']) if payload.get('balance') not in (None, '') else None,
            int(bool(payload.get('isActive', account['is_active']))),
            ensure_int(payload['settlementAccountId']) if 'settlementAccountId' in payload else account['settlement_account_id'],
            payload.get('cardNumber', account['card_number']),
            payload.get('amountSignMode', account['amount_sign_mode']),
            account_id,
        ),
    )
    return _with_computed_balance(fetchone('SELECT * FROM accounts WHERE id = ?', (account_id,)))


@router.delete('/api/accounts/{account_id}')
def delete_account(account_id: int):
    execute('DELETE FROM accounts WHERE id = ?', (account_id,))
    return JSONResponse(status_code=204, content=None)


@router.get('/api/accounts/{account_id}/opening-balance')
def list_opening_balances(account_id: int):
    cat_id = _opening_balance_category_id()
    if cat_id is None:
        return []
    return fetchall(
        'SELECT * FROM transactions WHERE account_id = ? AND category_id = ? ORDER BY date DESC',
        (account_id, cat_id),
    )


@router.post('/api/accounts/{account_id}/opening-balance')
def set_opening_balance(account_id: int, payload: Dict[str, Any]):
    """Crea o aggiorna (upsert per anno solare) il checkpoint 'saldo iniziale'
    di un conto: vedi _compute_account_balances per come viene poi usato nel
    calcolo del saldo mostrato all'utente."""
    account = fetchone('SELECT * FROM accounts WHERE id = ?', (account_id,))
    if account is None:
        raise HTTPException(status_code=404, detail='Not found')
    date = payload.get('date')
    if not date:
        raise HTTPException(status_code=400, detail='Data obbligatoria')
    try:
        amount = float(payload['amount'])
    except (KeyError, TypeError, ValueError):
        raise HTTPException(status_code=400, detail='Importo non valido')
    cat_id = _opening_balance_category_id()
    if cat_id is None:
        raise HTTPException(status_code=500, detail="Categoria di sistema 'Saldo iniziale' non trovata")
    year = date[:4]
    is_personal_account = account['ownership'] == 'personal'
    destination = 'personal' if is_personal_account else 'family'
    paid_by_person_id = account['owner_id'] if is_personal_account else None
    existing = fetchone(
        "SELECT id FROM transactions WHERE account_id = ? AND category_id = ? AND strftime('%Y', date) = ?",
        (account_id, cat_id, year),
    )
    if existing:
        execute(
            "UPDATE transactions SET date = ?, amount = ?, updated_at = (datetime('now')) WHERE id = ?",
            (date, amount, existing['id']),
        )
        transaction_id = existing['id']
    else:
        cursor = db.conn.execute(
            'INSERT INTO transactions (date, amount, description_raw, merchant_name, category_id, account_id, '
            'destination, paid_by_person_id, is_confirmed, import_source) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?)',
            (date, amount, 'Saldo iniziale', 'Saldo iniziale', cat_id, account_id, destination, paid_by_person_id, 'manual'),
        )
        db.conn.commit()
        transaction_id = cursor.lastrowid
    return fetchone('SELECT * FROM transactions WHERE id = ?', (transaction_id,))

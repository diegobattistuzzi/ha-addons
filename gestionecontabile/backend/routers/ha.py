import json
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from .. import config, db, email_enrich, email_poller
from ..db import fetchall, fetchone
from ..util import ensure_int
from .accounts import _compute_account_balances
from .reports import _NON_SPEND_TYPES_SQL
from .transactions import _confirm_transaction_ids, _insert_transaction

router = APIRouter()


@router.get('/api/ha/whoami')
def ha_whoami(request: Request):
    ha_user_id = request.headers.get('x-remote-user-id')
    ha_user_name = request.headers.get('x-remote-user-name')
    ha_display_name = request.headers.get('x-remote-user-display-name')
    matched = fetchone('SELECT * FROM persons WHERE ha_user_id = ?', (ha_user_id,)) if ha_user_id else None
    return {
        'haUserId': ha_user_id,
        'haUserName': ha_user_name,
        'haUserDisplayName': ha_display_name,
        'matchedPersonId': matched['id'] if matched else None,
    }


def compute_sensor_data() -> Dict[str, Any]:
    month = datetime.utcnow().strftime('%Y-%m')
    today = datetime.utcnow().strftime('%Y-%m-%d')
    expenses = fetchone(
        "SELECT COALESCE(SUM(ABS(t.amount)),0) AS total FROM transactions t LEFT JOIN categories c ON c.id = t.category_id "
        f"WHERE t.date LIKE ? AND t.amount<0 AND t.is_confirmed=1 AND {_NON_SPEND_TYPES_SQL}",
        (f'{month}%',),
    )['total']
    today_total = fetchone(
        "SELECT COALESCE(SUM(ABS(t.amount)),0) AS total FROM transactions t LEFT JOIN categories c ON c.id = t.category_id "
        f"WHERE t.date = ? AND t.amount<0 AND t.is_confirmed=1 AND {_NON_SPEND_TYPES_SQL}",
        (today,),
    )['total']
    shared_account_ids = {row['id'] for row in fetchall(
        'SELECT id FROM accounts WHERE ownership = ? AND is_active = 1', ('shared',),
    )}
    account_balances = _compute_account_balances()
    balance = sum(v for k, v in account_balances.items() if k in shared_account_ids)
    pending = fetchone('SELECT COUNT(*) AS count FROM transactions WHERE is_confirmed = 0')['count']
    year_pattern = f'{month[:4]}%'
    expenses_year = fetchone(
        "SELECT COALESCE(SUM(ABS(t.amount)),0) AS total FROM transactions t LEFT JOIN categories c ON c.id = t.category_id "
        f"WHERE t.date LIKE ? AND t.amount<0 AND t.is_confirmed=1 AND {_NON_SPEND_TYPES_SQL}",
        (year_pattern,),
    )['total']
    over_budget = fetchall(
        'SELECT c.name FROM categories c WHERE c.budget_monthly IS NOT NULL AND c.is_active = 1 AND (SELECT COALESCE(SUM(ABS(t.amount)),0) FROM transactions t WHERE t.category_id=c.id AND t.date LIKE ? AND t.amount<0) > c.budget_monthly',
        (f'{month}%',),
    )
    over_budget_annual = fetchall(
        'SELECT c.name FROM categories c WHERE c.budget_annual IS NOT NULL AND c.is_active = 1 AND (SELECT COALESCE(SUM(ABS(t.amount)),0) FROM transactions t WHERE t.category_id=c.id AND t.date LIKE ? AND t.amount<0) > c.budget_annual',
        (year_pattern,),
    )
    return {
        'spese_mese': round(expenses, 2),
        'spese_oggi': round(today_total, 2),
        'spese_anno': round(expenses_year, 2),
        'saldo_comuni': round(balance, 2),
        'pending_review': pending,
        'budget_ok': len(over_budget) == 0,
        'over_budget': [row['name'] for row in over_budget],
        'budget_ok_annual': len(over_budget_annual) == 0,
        'over_budget_annual': [row['name'] for row in over_budget_annual],
        'month': month,
    }


@router.get('/api/ha/sensors')
def ha_sensors():
    return compute_sensor_data()


@router.post('/api/ha/sync-persons')
def ha_sync_persons():
    if not config.SUPERVISOR_TOKEN:
        raise HTTPException(status_code=503, detail='SUPERVISOR_TOKEN non disponibile — funzione attiva solo dentro Home Assistant')
    try:
        response = httpx.get(
            'http://supervisor/core/api/states',
            headers={'Authorization': f'Bearer {config.SUPERVISOR_TOKEN}', 'Content-Type': 'application/json'},
            timeout=30.0,
        )
    except httpx.HTTPError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Impossibile raggiungere l'API di Home Assistant ({e}). Verifica che l'addon abbia il permesso "
            "'homeassistant_api: true' in config.yaml e riavvialo.",
        )
    if response.status_code == 403:
        raise HTTPException(
            status_code=502,
            detail="Accesso negato dall'API di Home Assistant. Aggiungi 'homeassistant_api: true' in config.yaml "
            "e riavvia l'addon.",
        )
    if response.status_code != 200:
        raise HTTPException(status_code=502, detail=f'HA API error ({response.status_code})')
    states = response.json()
    persons = [s for s in states if s.get('entity_id', '').startswith('person.')]
    existing = fetchall('SELECT name FROM persons')
    existing_names = {item['name'].lower() for item in existing}
    imported = 0
    for entity in persons:
        name = entity.get('attributes', {}).get('friendly_name') or entity.get('entity_id', '').split('.')[-1]
        if name.lower() in existing_names:
            continue
        db.conn.execute('INSERT INTO persons (name, email, color, is_primary) VALUES (?, ?, ?, ?)', (name, None, '#1D3557', 0))
        imported += 1
    db.conn.commit()
    return {'imported': imported, 'total': len(persons)}


def _resolve_by_name(table: str, name: Optional[str]) -> Optional[int]:
    if not name or not str(name).strip():
        return None
    row = fetchone(f'SELECT id FROM {table} WHERE LOWER(name) = LOWER(?)', (str(name).strip(),))
    return row['id'] if row else None


def _default_account_id() -> Optional[int]:
    """Conto da usare per casaspese.add_expense quando l'utente non ne indica
    uno per nome: prima l'eventuale preferenza salvata in Impostazioni
    (settings.ha_default_account_id), altrimenti il primo conto condiviso
    attivo (stessa nozione di 'shared_account_ids' usata in
    compute_sensor_data per il saldo comune)."""
    setting = fetchone("SELECT value FROM settings WHERE key = 'ha_default_account_id'")
    if setting:
        try:
            account_id = ensure_int(json.loads(setting['value']))
        except (TypeError, ValueError):
            account_id = None
        if account_id:
            return account_id
    row = fetchone("SELECT id FROM accounts WHERE ownership = 'shared' AND is_active = 1 ORDER BY id LIMIT 1")
    return row['id'] if row else None


@router.post('/api/ha/sync')
def ha_sync():
    """Servizio HA 'casaspese.sync': non esiste un vero sync bancario in
    questa versione (vedi ha_notifier.py/README), quindi forza subito un giro
    di controllo email (email_poller) e di verifica notifiche (ha_notifier),
    invece dei loro normali intervalli programmati."""
    from .. import ha_notifier
    email_checked = email_poller.poll_all_now()
    sensors = ha_notifier.run_check_now()
    return {'emailAccountsChecked': email_checked, 'sensors': sensors}


@router.post('/api/ha/add-expense')
def ha_add_expense(payload: Dict[str, Any]):
    """Servizio HA 'casaspese.add_expense': a differenza di POST
    /api/transactions (pensato per il form del frontend, che gia' conosce gli
    id interni) risolve conto/categoria/persona per NOME, cosi' un'automazione
    o un comando vocale HA puo' passare testo libero invece di dover conoscere
    gli id del database."""
    if payload.get('amount') is None or not payload.get('description'):
        raise HTTPException(status_code=400, detail="Campi obbligatori mancanti: 'amount' e 'description'")
    account_id = _resolve_by_name('accounts', payload.get('account')) or _default_account_id()
    if not account_id:
        raise HTTPException(
            status_code=400,
            detail="Nessun conto risolvibile: indica 'account' con un nome valido, oppure configura un conto "
            'condiviso attivo o una preferenza in Impostazioni.',
        )
    category_id = _resolve_by_name('categories', payload.get('category'))
    paid_by_person_id = _resolve_by_name('persons', payload.get('paidBy'))
    amount = float(payload['amount'])
    tx_payload = {
        'date': payload.get('date') or datetime.utcnow().strftime('%Y-%m-%d'),
        'amount': -abs(amount),
        'description': payload['description'],
        'accountId': account_id,
        'categoryId': category_id,
        'paidByPersonId': paid_by_person_id,
        'isCash': bool(payload.get('isCash', False)),
        'notes': payload.get('notes'),
    }
    return JSONResponse(status_code=201, content=_insert_transaction(tx_payload, import_source='ha-service'))


@router.post('/api/ha/approve-pending')
def ha_approve_pending(payload: Optional[Dict[str, Any]] = None):
    """Servizio HA 'casaspese.approve_pending': con 'ids' assente/vuoto,
    conferma TUTTE le transazioni attualmente in attesa di revisione AI
    (stessa query di GET /api/transactions/pending-ai)."""
    payload = payload or {}
    ids: List[int] = [ensure_int(x) for x in payload.get('ids', []) if ensure_int(x) is not None]
    if not ids:
        pending = fetchall('SELECT id FROM transactions WHERE is_confirmed = 0 AND ai_category_id IS NOT NULL')
        ids = [row['id'] for row in pending]
    confirmed = _confirm_transaction_ids(ids, current_person=None)
    return {'confirmed': confirmed}


@router.post('/api/ha/webhook')
def ha_webhook(payload: Dict[str, Any]):
    # Automazione HA (integrazione IMAP) che inoltra mail di conferma
    # acquisto/pagamento (PayPal, Amazon, ...) da arricchire via AI.
    if payload.get('sender') and (payload.get('subject') or payload.get('body')):
        try:
            result = email_enrich.process_incoming_email(
                payload.get('sender', ''), payload.get('subject', ''), payload.get('body', '')
            )
            return {'received': True, 'emailReceipt': result}
        except ValueError as e:
            return JSONResponse(status_code=422, content={'received': True, 'error': str(e)})
    print('HA webhook', payload)
    return {'received': True}

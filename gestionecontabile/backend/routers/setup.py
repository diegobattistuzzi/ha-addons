import json
from typing import Any, Dict

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from .. import db
from ..db import execute, fetchone
from ..util import ensure_int
from .persons import _sanitize_person

router = APIRouter()


@router.get('/api/setup/status')
def setup_status():
    setting = fetchone("SELECT value FROM settings WHERE key='setup_completed'")
    completed = json.loads(setting['value']) if setting else False
    person_count = fetchone('SELECT COUNT(*) AS c FROM persons')['c']
    account_count = fetchone('SELECT COUNT(*) AS c FROM accounts')['c']
    step = 1
    if person_count > 0:
        step = 2
    if account_count > 0:
        step = 3
    if completed:
        step = 4
    return {'completed': completed, 'step': step, 'personCount': person_count, 'accountCount': account_count}


@router.post('/api/setup/persons')
def setup_persons(payload: Dict[str, Any]):
    created = []
    for person in payload.get('persons', []):
        if person.get('name', '').strip():
            cursor = db.conn.execute(
                'INSERT INTO persons (name, email, color, is_primary) VALUES (?, ?, ?, ?)',
                (person['name'].strip(), person.get('email'), person.get('color', '#1D3557'), int(bool(person.get('isPrimary', False))))
            )
            db.conn.commit()
            created.append(_sanitize_person(fetchone('SELECT * FROM persons WHERE id = ?', (cursor.lastrowid,))))
    return JSONResponse(status_code=201, content=created)


@router.post('/api/setup/accounts')
def setup_accounts(payload: Dict[str, Any]):
    created = []
    for account in payload.get('accounts', []):
        if account.get('name', '').strip():
            cursor = db.conn.execute(
                'INSERT INTO accounts (name, bank, type, ownership, owner_id, co_owners, iban, color, balance) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
                (
                    account['name'].strip(),
                    account.get('bank', 'other'),
                    account.get('type', 'checking'),
                    account.get('ownership', 'shared'),
                    ensure_int(account.get('ownerId')),
                    json.dumps(account.get('coOwners')) if account.get('coOwners') is not None else None,
                    account.get('iban'),
                    account.get('color'),
                    float(account['balance']) if account.get('balance') not in (None, '') else None,
                ),
            )
            db.conn.commit()
            created.append(fetchone('SELECT * FROM accounts WHERE id = ?', (cursor.lastrowid,)))
    return JSONResponse(status_code=201, content=created)


@router.post('/api/setup/categories')
def setup_categories(payload: Dict[str, Any]):
    budgets = payload.get('budgets', [])
    for budget in budgets:
        execute('UPDATE categories SET budget_monthly = ? WHERE id = ?', (budget.get('amount'), ensure_int(budget.get('categoryId'))))
    return {'updated': len(budgets)}


@router.get('/api/settings')
def get_settings():
    """Impostazioni persistite in tabella settings che il frontend deve poter
    rileggere al caricamento (a differenza delle altre chiavi setup_complete,
    finora scritte solo "al buio" senza un modo per recuperarle)."""
    ai_provider = fetchone("SELECT value FROM settings WHERE key = 'ai_provider'")
    visibility_level = fetchone("SELECT value FROM settings WHERE key = 'visibility_level'")
    return {
        'aiProvider': json.loads(ai_provider['value']) if ai_provider else 'openai',
        'visibilityLevel': json.loads(visibility_level['value']) if visibility_level else 'segregated',
    }


@router.post('/api/setup/complete')
def setup_complete(payload: Dict[str, Any]):
    if payload.get('aiProvider'):
        execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', ('ai_provider', json.dumps(payload['aiProvider'])))
    if payload.get('visibilityLevel') in ('open', 'accounts_only', 'segregated'):
        execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', ('visibility_level', json.dumps(payload['visibilityLevel'])))
    if payload.get('aiModel'):
        execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', ('ai_model', json.dumps(payload['aiModel'])))
    if payload.get('syncIntervalMinutes') is not None:
        execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', ('sync_interval_minutes', json.dumps(payload['syncIntervalMinutes'])))
    execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', ('setup_completed', json.dumps(True)))
    return {'completed': True}

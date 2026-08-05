from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from .. import db
from ..db import execute, fetchall, fetchone
from ..util import ensure_int

router = APIRouter()


@router.get('/api/rules')
def list_rules():
    return fetchall('SELECT * FROM import_rules ORDER BY priority DESC, id ASC')


@router.post('/api/rules')
def create_rule(payload: Dict[str, Any]):
    if not payload.get('pattern', '').strip():
        raise HTTPException(status_code=400, detail='Il pattern e\' obbligatorio')
    if not payload.get('categoryId'):
        raise HTTPException(status_code=400, detail='La categoria e\' obbligatoria')
    cursor = db.conn.execute(
        'INSERT INTO import_rules (pattern, is_regex, sign, category_id, destination, paid_by_person_id, '
        'split_person_id, split_ratio, priority, is_active) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
        (
            payload['pattern'].strip(),
            int(bool(payload.get('isRegex'))),
            payload.get('sign') or None,
            ensure_int(payload['categoryId']),
            payload.get('destination') or None,
            ensure_int(payload.get('paidByPersonId')),
            ensure_int(payload.get('splitPersonId')),
            float(payload['splitRatio']) if payload.get('splitRatio') not in (None, '') else None,
            ensure_int(payload.get('priority')) or 0,
            int(bool(payload.get('isActive', True))),
        ),
    )
    db.conn.commit()
    return JSONResponse(status_code=201, content=fetchone('SELECT * FROM import_rules WHERE id = ?', (cursor.lastrowid,)))


@router.put('/api/rules/{rule_id}')
def update_rule(rule_id: int, payload: Dict[str, Any]):
    rule = fetchone('SELECT * FROM import_rules WHERE id = ?', (rule_id,))
    if rule is None:
        raise HTTPException(status_code=404, detail='Not found')
    if payload.get('pattern') is not None and not payload['pattern'].strip():
        raise HTTPException(status_code=400, detail='Il pattern e\' obbligatorio')
    if 'splitRatio' in payload:
        split_ratio = float(payload['splitRatio']) if payload['splitRatio'] not in (None, '') else None
    else:
        split_ratio = rule['split_ratio']
    execute(
        'UPDATE import_rules SET pattern = ?, is_regex = ?, sign = ?, category_id = ?, destination = ?, '
        'paid_by_person_id = ?, split_person_id = ?, split_ratio = ?, priority = ?, is_active = ? WHERE id = ?',
        (
            payload.get('pattern', rule['pattern']).strip(),
            int(bool(payload.get('isRegex', rule['is_regex']))),
            payload.get('sign', rule['sign']) or None,
            ensure_int(payload['categoryId']) if 'categoryId' in payload else rule['category_id'],
            payload.get('destination', rule['destination']) or None,
            ensure_int(payload['paidByPersonId']) if 'paidByPersonId' in payload else rule['paid_by_person_id'],
            ensure_int(payload['splitPersonId']) if 'splitPersonId' in payload else rule['split_person_id'],
            split_ratio,
            ensure_int(payload['priority']) if 'priority' in payload else rule['priority'],
            int(bool(payload.get('isActive', rule['is_active']))),
            rule_id,
        ),
    )
    return fetchone('SELECT * FROM import_rules WHERE id = ?', (rule_id,))


@router.delete('/api/rules/{rule_id}')
def delete_rule(rule_id: int):
    execute('DELETE FROM import_rules WHERE id = ?', (rule_id,))
    return JSONResponse(status_code=204, content=None)

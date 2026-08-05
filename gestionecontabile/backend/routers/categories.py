from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from .. import db
from ..db import execute, fetchall, fetchone
from ..util import ensure_int

router = APIRouter()


@router.get('/api/categories')
def list_categories():
    return fetchall('SELECT * FROM categories ORDER BY sort_order')


@router.get('/api/categories/defaults')
def list_category_defaults():
    return fetchall('SELECT * FROM categories ORDER BY sort_order')


@router.get('/api/categories/{category_id}')
def get_category(category_id: int):
    category = fetchone('SELECT * FROM categories WHERE id = ?', (category_id,))
    if category is None:
        raise HTTPException(status_code=404, detail='Not found')
    return category


def _validate_category_parent(category_id: Optional[int], parent_id: Optional[int]) -> None:
    """La gerarchia e' volutamente limitata a 2 livelli (categoria -> sotto-
    categoria), per tenere il modello semplice: niente sotto-categorie di
    sotto-categorie. Vedi Categories.vue per la UI ad albero costruita su
    questo stesso vincolo."""
    if parent_id is None:
        return
    if parent_id == category_id:
        raise HTTPException(status_code=400, detail='Una categoria non puo\' essere genitore di se stessa')
    parent = fetchone('SELECT id, parent_id FROM categories WHERE id = ?', (parent_id,))
    if parent is None:
        raise HTTPException(status_code=400, detail='Categoria padre non trovata')
    if parent['parent_id'] is not None:
        raise HTTPException(status_code=400, detail='Una sotto-categoria non puo\' avere a sua volta sotto-categorie')
    if category_id is not None:
        has_children = fetchone('SELECT id FROM categories WHERE parent_id = ? LIMIT 1', (category_id,))
        if has_children is not None:
            raise HTTPException(status_code=400, detail='Questa categoria ha gia\' delle sotto-categorie: spostale o rimuovile prima di assegnarle un genitore')


@router.post('/api/categories')
def create_category(payload: Dict[str, Any]):
    if not payload.get('name', '').strip():
        raise HTTPException(status_code=400, detail='Nome obbligatorio')
    parent_id = ensure_int(payload.get('parentId'))
    _validate_category_parent(None, parent_id)
    cursor = db.conn.execute(
        'INSERT INTO categories (code, name, icon, color, type, budget_monthly, budget_annual, ai_keywords, parent_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
        (
            payload.get('code'),
            payload['name'].strip(),
            payload.get('icon'),
            payload.get('color'),
            payload.get('type', 'expense'),
            float(payload['budgetMonthly']) if payload.get('budgetMonthly') not in (None, '') else None,
            float(payload['budgetAnnual']) if payload.get('budgetAnnual') not in (None, '') else None,
            payload.get('aiKeywords'),
            parent_id,
        ),
    )
    db.conn.commit()
    return JSONResponse(status_code=201, content=fetchone('SELECT * FROM categories WHERE id = ?', (cursor.lastrowid,)))


@router.put('/api/categories/{category_id}')
def update_category(category_id: int, payload: Dict[str, Any]):
    category = fetchone('SELECT * FROM categories WHERE id = ?', (category_id,))
    if category is None:
        raise HTTPException(status_code=404, detail='Not found')
    if payload.get('name') is not None and not payload['name'].strip():
        raise HTTPException(status_code=400, detail='Nome obbligatorio')

    def budget_value(key, current):
        if key not in payload:
            return current
        return float(payload[key]) if payload[key] not in (None, '') else None

    parent_id = ensure_int(payload['parentId']) if 'parentId' in payload else category['parent_id']
    if parent_id != category['parent_id']:
        _validate_category_parent(category_id, parent_id)

    execute(
        'UPDATE categories SET code = ?, name = ?, icon = ?, color = ?, type = ?, budget_monthly = ?, budget_annual = ?, is_active = ?, ai_keywords = ?, parent_id = ? WHERE id = ?',
        (
            payload.get('code', category['code']),
            payload.get('name', category['name']).strip() if payload.get('name') is not None else category['name'],
            payload.get('icon', category['icon']),
            payload.get('color', category['color']),
            payload.get('type', category['type']),
            budget_value('budgetMonthly', category['budget_monthly']),
            budget_value('budgetAnnual', category['budget_annual']),
            int(bool(payload.get('isActive', category['is_active']))),
            payload.get('aiKeywords', category['ai_keywords']),
            parent_id,
            category_id,
        ),
    )
    return fetchone('SELECT * FROM categories WHERE id = ?', (category_id,))


@router.delete('/api/categories/{category_id}')
def delete_category(category_id: int):
    """Elimina davvero la categoria (non solo un disattiva): le transazioni che
    la usavano restano, ma senza categoria (da ricategorizzare manualmente).
    Le sotto-categorie restano invece invariate (non cancellate a cascata), ma
    tornano categorie di primo livello, altrimenti resterebbero con un
    parent_id orfano che punta a una riga non piu' esistente."""
    execute('UPDATE categories SET parent_id = NULL WHERE parent_id = ?', (category_id,))
    execute('UPDATE transactions SET category_id = NULL WHERE category_id = ?', (category_id,))
    execute('UPDATE transactions SET ai_category_id = NULL WHERE ai_category_id = ?', (category_id,))
    execute('DELETE FROM budgets WHERE category_id = ?', (category_id,))
    execute('DELETE FROM categories WHERE id = ?', (category_id,))
    return JSONResponse(status_code=204, content=None)

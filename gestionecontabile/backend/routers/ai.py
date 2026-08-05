import json
from datetime import datetime
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from .. import access, ai_client, ai_reports, db
from ..db import execute, fetchall, fetchone
from ..util import ensure_int
from .reports import (
    _NON_SPEND_TYPES_SQL,
    _report_summary_data,
    _report_top_merchants_data,
    _report_trend_data,
    _run_report_query,
    report_subscriptions,
)

router = APIRouter()

# ---------------------------------------------------------------------------
# Assistente AI: riepilogo narrativo, anomalie, chat sui dati finanziari.
# L'AI non genera mai SQL/accede mai al DB direttamente: riceve solo dati gia'
# aggregati (riepilogo) o propone una query-config validata contro le stesse
# whitelist di report_query (chat), che il backend esegue in modo sicuro.
# ---------------------------------------------------------------------------


@router.post('/api/ai/summary')
def ai_summary(payload: Dict[str, Any], request: Request):
    month = payload.get('month') or datetime.utcnow().strftime('%Y-%m')
    account_id = ensure_int(payload.get('accountId'))
    summary = _report_summary_data(request, month, account_id)
    trend = _report_trend_data(request, 6, account_id)
    top_merchants = _report_top_merchants_data(request, month, 5, account_id)
    subscriptions = report_subscriptions(request).get('subscriptions', [])
    prompt = ai_reports.build_narrative_prompt(month, summary, trend, top_merchants, subscriptions)
    try:
        text = ai_client.ask_ai(prompt, task_name='casaspese_ai_summary', max_tokens=1200)
    except ValueError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return {'text': text}


@router.post('/api/ai/anomalies')
def ai_anomalies(payload: Dict[str, Any], request: Request):
    month = payload.get('month') or datetime.utcnow().strftime('%Y-%m')
    account_id = ensure_int(payload.get('accountId'))
    summary = _report_summary_data(request, month, account_id)
    current_by_category = summary.get('byCategory') or []

    year_n, month_n = int(month[:4]), int(month[5:7])
    history_months = []
    y, m = year_n, month_n
    for _ in range(6):
        m -= 1
        if m == 0:
            m, y = 12, y - 1
        history_months.append(f'{y:04d}-{m:02d}')

    vis_clause_t, vis_args_t = access.transaction_visibility(access.get_current_person(request), alias='t')
    account_clause = ' AND t.account_id = ?' if account_id else ''
    account_args = (account_id,) if account_id else ()
    history_rows = fetchall(
        'SELECT c.id, COALESCE(SUM(ABS(t.amount)),0) AS spent, COUNT(DISTINCT SUBSTR(t.date,1,7)) AS months_present '
        'FROM transactions t JOIN categories c ON c.id = t.category_id '
        f"WHERE SUBSTR(t.date,1,7) IN ({','.join('?' for _ in history_months)}) AND t.amount<0 AND t.is_confirmed=1 "
        f"AND {_NON_SPEND_TYPES_SQL} AND {vis_clause_t}{account_clause} "
        'GROUP BY c.id',
        tuple(history_months) + vis_args_t + account_args,
    )
    historical_avg = {row['id']: row['spent'] / len(history_months) for row in history_rows}

    known_merchants_rows = fetchall(
        'SELECT DISTINCT t.merchant_name FROM transactions t '
        f"WHERE SUBSTR(t.date,1,7) IN ({','.join('?' for _ in history_months)}) AND t.merchant_name IS NOT NULL "
        f"AND {vis_clause_t}{account_clause}",
        tuple(history_months) + vis_args_t + account_args,
    )
    known_merchants = {row['merchant_name'] for row in known_merchants_rows}
    current_merchants = _report_top_merchants_data(request, month, 50, account_id)

    anomalies = ai_reports.detect_anomalies(current_by_category, historical_avg, current_merchants, known_merchants)
    if not anomalies:
        return {'anomalies': []}

    try:
        explanations = ai_client.parse_json_array(
            ai_client.ask_ai(ai_reports.build_anomaly_explanation_prompt(anomalies), task_name='casaspese_ai_anomalies', max_tokens=800)
        )
    except ValueError:
        explanations = []

    for i, a in enumerate(anomalies):
        a['message'] = explanations[i] if i < len(explanations) else None
    return {'anomalies': anomalies}


@router.post('/api/ai/chat')
def ai_chat(payload: Dict[str, Any], request: Request):
    message = (payload.get('message') or '').strip()
    if not message:
        raise HTTPException(status_code=400, detail='Messaggio obbligatorio')
    month = payload.get('month')
    current_person = access.get_current_person(request)
    person_id = current_person['id'] if current_person else None

    conversation_id = ensure_int(payload.get('conversationId'))
    if not conversation_id:
        cursor = db.conn.execute(
            'INSERT INTO ai_conversations (person_id, title) VALUES (?, ?)',
            (person_id, message[:60]),
        )
        db.conn.commit()
        conversation_id = cursor.lastrowid
    else:
        existing = fetchone('SELECT id FROM ai_conversations WHERE id = ?', (conversation_id,))
        if existing is None:
            raise HTTPException(status_code=404, detail='Conversazione non trovata')

    db.conn.execute(
        'INSERT INTO ai_messages (conversation_id, role, content) VALUES (?, ?, ?)',
        (conversation_id, 'user', message),
    )
    db.conn.commit()

    query_config = None
    rows: List[Dict[str, Any]] = []
    try:
        intent_raw = ai_client.ask_ai(ai_reports.build_query_intent_prompt(message, month), task_name='casaspese_ai_chat_intent', max_tokens=400)
        query_config = ai_client.parse_json_object(intent_raw)
        rows = _run_report_query(query_config, request)
    except (ValueError, HTTPException):
        query_config = None
        rows = []

    answer_prompt = ai_reports.build_chat_answer_prompt(message, query_config or {}, rows)
    try:
        reply = ai_client.ask_ai(answer_prompt, task_name='casaspese_ai_chat', max_tokens=600)
    except ValueError as e:
        raise HTTPException(status_code=502, detail=str(e))

    db.conn.execute(
        'INSERT INTO ai_messages (conversation_id, role, content, query_config_json) VALUES (?, ?, ?, ?)',
        (conversation_id, 'assistant', reply, json.dumps(query_config) if query_config else None),
    )
    db.conn.execute("UPDATE ai_conversations SET updated_at = (datetime('now')) WHERE id = ?", (conversation_id,))
    db.conn.commit()

    return {'conversationId': conversation_id, 'reply': reply, 'queryConfig': query_config}


@router.get('/api/ai/conversations')
def list_ai_conversations(request: Request):
    current_person = access.get_current_person(request)
    person_id = current_person['id'] if current_person else None
    return fetchall(
        'SELECT * FROM ai_conversations WHERE person_id = ? OR person_id IS NULL ORDER BY updated_at DESC',
        (person_id,),
    )


@router.get('/api/ai/conversations/{conversation_id}/messages')
def list_ai_messages(conversation_id: int):
    rows = fetchall('SELECT * FROM ai_messages WHERE conversation_id = ? ORDER BY id ASC', (conversation_id,))
    for row in rows:
        if row.get('query_config_json'):
            row['queryConfig'] = json.loads(row.pop('query_config_json'))
        else:
            row.pop('query_config_json', None)
            row['queryConfig'] = None
    return rows


@router.delete('/api/ai/conversations/{conversation_id}')
def delete_ai_conversation(conversation_id: int):
    execute('DELETE FROM ai_messages WHERE conversation_id = ?', (conversation_id,))
    execute('DELETE FROM ai_conversations WHERE id = ?', (conversation_id,))
    return JSONResponse(status_code=204, content=None)

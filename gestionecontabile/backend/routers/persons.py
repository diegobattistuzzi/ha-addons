import json
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from .. import access, config, db, email_backfill, email_poller
from ..db import execute, fetchall, fetchone
from ..util import ensure_int

router = APIRouter()


def _sanitize_person(person: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Non restituire mai la password IMAP al client: la sostituisce con un
    booleano che indica solo se e' stata impostata."""
    if person is None:
        return None
    person = dict(person)
    person['imap_password_set'] = bool(person.get('imap_password'))
    person.pop('imap_password', None)
    return person


@router.get('/api/persons')
def list_persons():
    return [_sanitize_person(p) for p in fetchall('SELECT * FROM persons ORDER BY id')]


@router.get('/api/persons/{person_id}')
def get_person(person_id: int):
    person = fetchone('SELECT * FROM persons WHERE id = ?', (person_id,))
    if person is None:
        raise HTTPException(status_code=404, detail='Not found')
    return _sanitize_person(person)


@router.post('/api/persons')
def create_person(payload: Dict[str, Any]):
    if not payload.get('name', '').strip():
        raise HTTPException(status_code=400, detail='Nome obbligatorio')
    cursor = db.conn.execute(
        'INSERT INTO persons (name, email, color, is_primary, ha_user_id, imap_host, imap_port, imap_username, '
        'imap_password, imap_use_ssl, imap_folder) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
        (
            payload['name'].strip(),
            payload.get('email'),
            payload.get('color', '#1D3557'),
            int(bool(payload.get('isPrimary', False))),
            payload.get('haUserId'),
            payload.get('imapHost'),
            ensure_int(payload.get('imapPort')),
            payload.get('imapUsername'),
            payload.get('imapPassword'),
            int(bool(payload.get('imapUseSsl', True))),
            payload.get('imapFolder') or 'INBOX',
        ),
    )
    db.conn.commit()
    return JSONResponse(
        status_code=201,
        content=_sanitize_person(fetchone('SELECT * FROM persons WHERE id = ?', (cursor.lastrowid,))),
    )


@router.put('/api/persons/{person_id}')
def update_person(person_id: int, payload: Dict[str, Any]):
    if payload.get('name') is not None and not payload['name'].strip():
        raise HTTPException(status_code=400, detail='Nome obbligatorio')
    person = fetchone('SELECT * FROM persons WHERE id = ?', (person_id,))
    if person is None:
        raise HTTPException(status_code=404, detail='Not found')
    execute(
        'UPDATE persons SET name = ?, email = ?, color = ?, is_primary = ?, ha_user_id = ?, imap_host = ?, '
        'imap_port = ?, imap_username = ?, imap_password = ?, imap_use_ssl = ?, imap_folder = ? WHERE id = ?',
        (
            payload.get('name', person['name']).strip(),
            payload.get('email', person['email']),
            payload.get('color', person['color']),
            int(bool(payload.get('isPrimary', person['is_primary']))),
            payload.get('haUserId', person['ha_user_id']),
            payload.get('imapHost', person['imap_host']),
            ensure_int(payload['imapPort']) if 'imapPort' in payload else person['imap_port'],
            payload.get('imapUsername', person['imap_username']),
            payload.get('imapPassword', person['imap_password']),
            int(bool(payload.get('imapUseSsl', person['imap_use_ssl']))),
            payload.get('imapFolder', person['imap_folder']),
            person_id,
        ),
    )
    return _sanitize_person(fetchone('SELECT * FROM persons WHERE id = ?', (person_id,)))


@router.delete('/api/persons/{person_id}')
def delete_person(person_id: int):
    execute('DELETE FROM persons WHERE id = ?', (person_id,))
    return JSONResponse(status_code=204, content=None)


def _sanitize_mobile_token(token: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in token.items() if k != 'token_hash'}


@router.get('/api/mobile-tokens')
def list_mobile_tokens(request: Request):
    params = request.query_params
    sql = 'SELECT * FROM mobile_tokens'
    args: tuple = ()
    if person_id := ensure_int(params.get('personId')):
        sql += ' WHERE person_id = ?'
        args = (person_id,)
    sql += ' ORDER BY id DESC'
    return [_sanitize_mobile_token(t) for t in fetchall(sql, args)]


@router.post('/api/mobile-tokens')
def create_mobile_token(payload: Dict[str, Any]):
    person_id = ensure_int(payload.get('personId'))
    if not person_id:
        raise HTTPException(status_code=400, detail='personId obbligatorio')
    person = fetchone('SELECT * FROM persons WHERE id = ?', (person_id,))
    if person is None:
        raise HTTPException(status_code=404, detail='Persona non trovata')
    raw_token = access.generate_mobile_token()
    cursor = db.conn.execute(
        'INSERT INTO mobile_tokens (person_id, token_hash, label) VALUES (?, ?, ?)',
        (person_id, access.hash_mobile_token(raw_token), payload.get('label')),
    )
    db.conn.commit()
    if not config.PUBLIC_URL:
        url = None
    else:
        url = f'{config.PUBLIC_URL}/#/mobile/link?token={raw_token}'
    return JSONResponse(
        status_code=201,
        content={
            **_sanitize_mobile_token(fetchone('SELECT * FROM mobile_tokens WHERE id = ?', (cursor.lastrowid,))),
            'token': raw_token,
            'url': url,
        },
    )


@router.delete('/api/mobile-tokens/{token_id}')
def revoke_mobile_token(token_id: int):
    execute("UPDATE mobile_tokens SET revoked_at = datetime('now') WHERE id = ? AND revoked_at IS NULL", (token_id,))
    return JSONResponse(status_code=204, content=None)


@router.get('/api/mobile/me')
def mobile_me(request: Request):
    """Chi sta usando la PWA in questo momento (via token Bearer) - usata dalla
    schermata di scansione scontrino per salutare l'utente e preselezionare la
    persona come pagatore, senza dover ripetere la risoluzione lato client."""
    person = access.get_current_person(request)
    if person is None:
        raise HTTPException(status_code=401, detail='Nessuna persona riconosciuta')
    return _sanitize_person(person)


@router.post('/api/persons/{person_id}/email-backfill')
def email_backfill_endpoint(person_id: int, payload: Dict[str, Any]):
    person = fetchone('SELECT * FROM persons WHERE id = ?', (person_id,))
    if person is None:
        raise HTTPException(status_code=404, detail='Not found')
    senders = payload.get('senders') or ['paypal.com', 'amazon.it', 'amazon.com']
    subject_keywords = payload.get('subjectKeywords') or email_backfill.DEFAULT_SUBJECT_KEYWORDS
    try:
        result = email_backfill.run_backfill(
            person,
            senders=senders,
            date_from=payload.get('dateFrom'),
            date_to=payload.get('dateTo'),
            subject_keywords=subject_keywords,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return result


@router.post('/api/persons/{person_id}/email-backfill-stream')
def email_backfill_stream(person_id: int, payload: Dict[str, Any]):
    """Come /email-backfill ma risponde con un flusso SSE (stage/progress/done)
    invece di un'unica risposta: la scansione IMAP di una casella con molte mail
    puo' richiedere svariati secondi e senza feedback il frontend sembra bloccato."""
    person = fetchone('SELECT * FROM persons WHERE id = ?', (person_id,))
    if person is None:
        raise HTTPException(status_code=404, detail='Not found')
    senders = payload.get('senders') or ['paypal.com', 'amazon.it', 'amazon.com']
    subject_keywords = payload.get('subjectKeywords') or email_backfill.DEFAULT_SUBJECT_KEYWORDS

    def sse(event: str, data: Dict[str, Any]) -> str:
        return f'event: {event}\ndata: {json.dumps(data)}\n\n'

    def event_stream():
        try:
            for update in email_backfill.run_backfill_iter(
                person,
                senders=senders,
                date_from=payload.get('dateFrom'),
                date_to=payload.get('dateTo'),
                subject_keywords=subject_keywords,
            ):
                if update.get('done'):
                    yield sse('done', update)
                else:
                    yield sse('progress', update)
        except ValueError as e:
            yield sse('error', {'detail': str(e)})

    return StreamingResponse(event_stream(), media_type='text/event-stream')


@router.post('/api/persons/{person_id}/email-poll-now')
def email_poll_now(person_id: int):
    """Forza subito un controllo IMAP incrementale (solo mail nuove, vedi
    email_backfill.run_incremental_poll) invece di aspettare il prossimo giro
    automatico di email_poller - utile appena configurate le credenziali per
    verificare che funzionino senza aspettare fino a sync_interval_minutes."""
    person = fetchone('SELECT * FROM persons WHERE id = ?', (person_id,))
    if person is None:
        raise HTTPException(status_code=404, detail='Not found')
    try:
        result = email_backfill.run_incremental_poll(
            person, senders=email_poller.DEFAULT_SENDERS, subject_keywords=email_backfill.DEFAULT_SUBJECT_KEYWORDS,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    execute(
        "UPDATE persons SET imap_last_uid = ?, imap_uidvalidity = ?, imap_last_checked_at = datetime('now') WHERE id = ?",
        (result['newLastUid'], result['newUidValidity'], person_id),
    )
    return result

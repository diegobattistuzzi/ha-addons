import hashlib
import json
import secrets
from typing import Any, Dict, Optional, Tuple

from fastapi import Request

from . import config, db

_VISIBILITY_LEVELS = ('open', 'accounts_only', 'segregated')


def _fetchone(query: str, args: tuple = ()) -> Optional[Dict[str, Any]]:
    cursor = db.conn.execute(query, args)
    row = cursor.fetchone()
    return {k: row[k] for k in row.keys()} if row is not None else None


def visibility_level() -> str:
    """Livello globale di segregazione dei dati personali (impostazione in
    Impostazioni, tabella settings chiave 'visibility_level'):
    - 'open': nessuna segregazione, tutti vedono conti e transazioni di tutti;
    - 'accounts_only': i conti personali sono visibili a tutti (es. saldo),
      ma le loro transazioni restano riservate a proprietario/co_owners;
    - 'segregated' (default): comportamento storico, conti e transazioni
      'personal' visibili solo al proprietario e a chi e' in co_owners.
    """
    row = _fetchone("SELECT value FROM settings WHERE key = 'visibility_level'")
    if row and row.get('value'):
        try:
            level = json.loads(row['value'])
        except (TypeError, ValueError):
            level = None
        if level in _VISIBILITY_LEVELS:
            return level
    return 'segregated'


def _is_co_owner(co_owners_json: Optional[str], person_id: Any) -> bool:
    if not co_owners_json:
        return False
    try:
        return person_id in json.loads(co_owners_json)
    except (TypeError, ValueError):
        return False


def hash_mobile_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode('utf-8')).hexdigest()


def generate_mobile_token() -> str:
    return secrets.token_urlsafe(32)


def get_person_for_mobile_token(raw_token: str) -> Optional[Dict[str, Any]]:
    """Risolve la persona da un token mobile (Bearer), se valido e non revocato."""
    token_hash = hash_mobile_token(raw_token)
    row = _fetchone(
        'SELECT * FROM mobile_tokens WHERE token_hash = ? AND revoked_at IS NULL',
        (token_hash,),
    )
    if not row:
        return None
    db.conn.execute(
        "UPDATE mobile_tokens SET last_used_at = datetime('now') WHERE id = ?",
        (row['id'],),
    )
    db.conn.commit()
    return _fetchone('SELECT * FROM persons WHERE id = ?', (row['person_id'],))


def get_person_from_bearer(request: Request) -> Optional[Dict[str, Any]]:
    """Risolve la persona SOLO dal token mobile (Bearer) - a differenza di
    get_current_person, ignora deliberatamente X-Remote-User-Id/X-Person-Id:
    serve al gate di sicurezza in server.py, dove questi due header non
    costituiscono prova di provenienza da un percorso fidato."""
    authorization = request.headers.get('authorization', '')
    if authorization.lower().startswith('bearer '):
        raw_token = authorization[7:].strip()
        if raw_token:
            return get_person_for_mobile_token(raw_token)
    return None


def is_valid_ha_token(request: Request) -> bool:
    """Vero se la richiesta porta l'header 'X-Casaspese-Token' con lo stesso
    valore dell'opzione add-on 'ha_token' (config.HA_TOKEN). E' la credenziale
    usata dall'integrazione Home Assistant custom_components/casaspese (che
    chiama l'API da fuori l'Ingress, sulla rete interna del Supervisor) per
    autenticarsi verso /api/ha/sync, /api/ha/add-expense e
    /api/ha/approve-pending - vedi server.py:enforce_public_gateway_auth.

    Usa un header dedicato invece di riutilizzare 'Authorization: Bearer'
    (gia' usato da get_person_from_bearer per i token mobile) per non far
    convivere due spazi di segreti diversi sullo stesso header. Se HA_TOKEN
    non e' configurato (stringa vuota, default di config.yaml), questo
    controllo non puo' mai avere successo: un header vuoto non deve
    "autenticarsi" contro un default non impostato.
    """
    if not config.HA_TOKEN:
        return False
    provided = request.headers.get('x-casaspese-token', '')
    return bool(provided) and secrets.compare_digest(provided, config.HA_TOKEN)


def get_current_person(request: Request) -> Optional[Dict[str, Any]]:
    """Risolve la persona che sta effettuando la richiesta.

    Prova, in ordine:
    1. un token mobile (header 'Authorization: Bearer <token>'), usato dalla
       PWA installata su un dispositivo esterno alla rete HA;
    2. l'utente HA autenticato via Ingress (header impostato dal Supervisor,
       affidabile solo se ogni persona ha un account HA separato);
    3. l'header inviato dal frontend quando l'utente ha scelto manualmente
       il proprio profilo (selettore lato client, persistito sul dispositivo).

    ATTENZIONE: (2) e (3) sono fidati solo perche' il traffico che li porta
    arriva da un percorso di rete che il backend non controlla direttamente
    (Ingress di HA, o rete locale). Se l'app viene esposta anche su una porta
    pubblica per l'uso mobile, quella porta deve essere raggiungibile SOLO
    tramite un reverse proxy (nginx) che rimuove/sovrascrive questi due
    header in ingresso - altrimenti chiunque su internet potrebbe
    impersonare qualunque persona semplicemente inviandoli. Il backend non
    puo' distinguere da solo l'origine della richiesta per QUESTI due header
    - per questo il gate reale (vedi server.py enforce_public_gateway_auth)
    non si basa su di essi, ma solo su get_person_from_bearer.
    """
    person = get_person_from_bearer(request)
    if person:
        return person

    ha_user_id = request.headers.get('x-remote-user-id')
    if ha_user_id:
        person = _fetchone('SELECT * FROM persons WHERE ha_user_id = ?', (ha_user_id,))
        if person:
            return person

    person_id = request.headers.get('x-person-id')
    if person_id:
        person = _fetchone('SELECT * FROM persons WHERE id = ?', (person_id,))
        if person:
            return person

    return None


def transaction_visibility(current_person: Optional[Dict[str, Any]], alias: str = '') -> Tuple[str, tuple]:
    """Clausola SQL che nasconde le transazioni 'personal' altrui.

    NOTA: in SQL "colonna != 'x'" e' NULL (non TRUE) quando colonna e' NULL, quindi
    va sempre gestito esplicitamente il caso IS NULL per non nascondere righe con
    destination non valorizzata.

    Rispetta il livello globale (vedi visibility_level()): con 'open' non
    filtra nulla; con 'accounts_only'/'segregated' filtra come sempre, ma fa
    eccezione anche per chi e' elencato in co_owners del conto della
    transazione (non solo il proprietario), tramite json_each su
    accounts.co_owners.
    """
    prefix = f'{alias}.' if alias else ''
    if visibility_level() == 'open':
        return '1=1', ()
    if current_person:
        clause = (
            f"({prefix}destination IS NULL OR {prefix}destination != 'personal' OR {prefix}paid_by_person_id = ? "
            f"OR {prefix}paid_by_person_id IS NULL "
            'OR EXISTS ('
            f'SELECT 1 FROM accounts _vis_acc, json_each(COALESCE(_vis_acc.co_owners, \'[]\')) _vis_co '
            f'WHERE _vis_acc.id = {prefix}account_id AND _vis_co.value = ?'
            '))'
        )
        return clause, (current_person['id'], current_person['id'])
    return f"({prefix}destination IS NULL OR {prefix}destination != 'personal')", ()


def account_visibility(current_person: Optional[Dict[str, Any]], alias: str = '') -> Tuple[str, tuple]:
    """Clausola SQL che nasconde i conti 'personal' altrui.

    Con livello 'open' o 'accounts_only' i conti sono visibili a tutti (la
    segregazione a quel punto riguarda solo le transazioni, vedi
    transaction_visibility). Con 'segregated' fa eccezione anche per chi e'
    elencato in co_owners, oltre al proprietario.
    """
    prefix = f'{alias}.' if alias else ''
    if visibility_level() in ('open', 'accounts_only'):
        return '1=1', ()
    if current_person:
        clause = (
            f"({prefix}ownership != 'personal' OR {prefix}owner_id = ? OR {prefix}owner_id IS NULL "
            'OR EXISTS ('
            f'SELECT 1 FROM json_each(COALESCE({prefix}co_owners, \'[]\')) _vis_co WHERE _vis_co.value = ?'
            '))'
        )
        return clause, (current_person['id'], current_person['id'])
    return f"{prefix}ownership != 'personal'", ()


def can_see_transaction(tx: Dict[str, Any], current_person: Optional[Dict[str, Any]]) -> bool:
    if visibility_level() == 'open':
        return True
    if tx.get('destination') != 'personal':
        return True
    if not current_person:
        return False
    if tx.get('paid_by_person_id') == current_person['id']:
        return True
    account = _fetchone('SELECT co_owners FROM accounts WHERE id = ?', (tx.get('account_id'),))
    return bool(account) and _is_co_owner(account.get('co_owners'), current_person['id'])


def can_see_account(account: Dict[str, Any], current_person: Optional[Dict[str, Any]]) -> bool:
    if visibility_level() in ('open', 'accounts_only'):
        return True
    if account.get('ownership') != 'personal':
        return True
    if not current_person:
        return False
    if account.get('owner_id') == current_person['id']:
        return True
    return _is_co_owner(account.get('co_owners'), current_person['id'])

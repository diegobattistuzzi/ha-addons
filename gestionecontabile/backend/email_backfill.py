import email as email_lib
import html
import imaplib
import re
from datetime import datetime
from email.header import decode_header
from email.utils import parsedate_to_datetime
from typing import Any, Dict, List, Optional

from . import email_enrich

MAX_MESSAGES = 20000  # valvola di sicurezza anti-runaway, non un limite "normale": la ricerca e' gia' filtrata per mittente lato server IMAP, quindi con un uso tipico non si avvicina neanche lontanamente a questa soglia

# Intercetta ricevute anche di negozi non elencati esplicitamente tra i mittenti,
# cercando anche per oggetto tipico di una mail di conferma acquisto/pagamento.
DEFAULT_SUBJECT_KEYWORDS = [
    'conferma ordine', 'ordine confermato', 'ricevuta', 'fattura', 'pagamento effettuato',
    'hai pagato', 'order confirmation', 'payment receipt', 'your receipt', 'invoice',
]


def _or_chain(keys: List[str]) -> str:
    """Combina piu' criteri IMAP in OR annidato: IMAP accetta solo OR binario
    (due operandi), quindi per N mittenti serve annidare: OR a OR b OR c d."""
    if len(keys) == 1:
        return keys[0]
    return f'OR {keys[0]} {_or_chain(keys[1:])}'


_IMAP_MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']


def _imap_date(value: str) -> str:
    """Converte 'YYYY-MM-DD' nel formato IMAP 'DD-Mon-YYYY' (es. 12-Jul-2026).
    Il mese va scritto letteralmente in inglese: niente strftime('%b'), che e'
    legato al locale di sistema e con un locale non inglese (es. it_IT) produce
    abbreviazioni ('lug' invece di 'Jul') che il server IMAP non riconosce,
    facendo cadere silenziosamente il filtro data invece di dare errore."""
    d = datetime.strptime(value, '%Y-%m-%d')
    return f'{d.day:02d}-{_IMAP_MONTHS[d.month - 1]}-{d.year}'


def _parse_received_date(raw: Optional[str]) -> Optional[str]:
    """Converte l'header 'Date' del messaggio (formato RFC 2822) in 'YYYY-MM-DD',
    da usare come data certa dell'operazione quando la mail stessa non ne
    dichiara una esplicita (vedi email_enrich.process_incoming_email)."""
    if not raw:
        return None
    try:
        return parsedate_to_datetime(raw).date().isoformat()
    except (TypeError, ValueError):
        return None


def _decode_header_value(raw: Optional[str]) -> str:
    if not raw:
        return ''
    parts = decode_header(raw)
    decoded = []
    for text, charset in parts:
        if isinstance(text, bytes):
            decoded.append(text.decode(charset or 'utf-8', errors='replace'))
        else:
            decoded.append(text)
    return ''.join(decoded)


def _html_to_text(raw_html: str) -> str:
    text = re.sub(r'<(script|style)[^>]*>[\s\S]*?</\1>', ' ', raw_html, flags=re.IGNORECASE)
    text = re.sub(r'<br\s*/?>|</p>|</div>|</tr>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', ' ', text)
    return html.unescape(re.sub(r'[ \t]+', ' ', text)).strip()


def _extract_body(msg) -> str:
    if msg.is_multipart():
        plain, htmlpart = None, None
        for part in msg.walk():
            content_type = part.get_content_type()
            disposition = str(part.get('Content-Disposition') or '')
            if 'attachment' in disposition:
                continue
            try:
                payload = part.get_payload(decode=True)
            except Exception:
                continue
            if payload is None:
                continue
            charset = part.get_content_charset() or 'utf-8'
            try:
                text = payload.decode(charset, errors='replace')
            except (LookupError, ValueError):
                text = payload.decode('utf-8', errors='replace')
            if content_type == 'text/plain' and plain is None:
                plain = text
            elif content_type == 'text/html' and htmlpart is None:
                htmlpart = text
        if plain:
            return plain
        if htmlpart:
            return _html_to_text(htmlpart)
        return ''
    try:
        payload = msg.get_payload(decode=True)
    except Exception:
        return ''
    if payload is None:
        return ''
    charset = msg.get_content_charset() or 'utf-8'
    text = payload.decode(charset, errors='replace')
    return _html_to_text(text) if msg.get_content_type() == 'text/html' else text


def run_backfill_iter(
    person: Dict[str, Any],
    senders: List[str],
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    subject_keywords: Optional[List[str]] = None,
):
    """Generator che avanza la scansione IMAP passo passo, per poter riportare
    progresso (utile perche' su caselle grandi puo' richiedere svariati secondi).
    Ogni yield e' un dict di stato; l'ultimo ha 'done': True col risultato finale."""
    if not person.get('imap_host') or not person.get('imap_username') or not person.get('imap_password'):
        raise ValueError('Credenziali IMAP non configurate per questa persona')

    port = person.get('imap_port') or (993 if person.get('imap_use_ssl', 1) else 143)
    if person.get('imap_use_ssl', 1):
        conn = imaplib.IMAP4_SSL(person['imap_host'], port)
    else:
        conn = imaplib.IMAP4(person['imap_host'], port)

    try:
        yield {'stage': 'connecting'}
        try:
            conn.login(person['imap_username'], person['imap_password'])
        except imaplib.IMAP4.error as e:
            raise ValueError(f'Accesso IMAP fallito: {e}')

        folder = person.get('imap_folder') or 'INBOX'
        status, _ = conn.select(folder, readonly=True)
        if status != 'OK':
            raise ValueError(f'Cartella "{folder}" non trovata')

        senders_lower = [s.strip().lower() for s in senders if s.strip()]
        keywords_lower = [k.strip().lower() for k in (subject_keywords or []) if k.strip()]

        criteria = []
        if date_from:
            criteria.append(f'SINCE "{_imap_date(date_from)}"')
        if date_to:
            criteria.append(f'BEFORE "{_imap_date(date_to)}"')
        # Filtra per mittente e/o parole chiave nell'oggetto direttamente nella
        # query IMAP (server-side): senza questo, la scansione prendeva gli
        # ultimi N messaggi della cartella (qualsiasi mittente/oggetto) e SOLO
        # DOPO scartava quelli non pertinenti, perdendo mail piu' vecchie se la
        # cartella ha molto altro traffico. Un match su uno qualsiasi dei due
        # criteri (mittente noto O oggetto tipico di una ricevuta) e' sufficiente
        # a intercettare anche negozi non elencati esplicitamente nei mittenti.
        match_keys = [f'FROM "{s}"' for s in senders_lower] + [f'SUBJECT "{k}"' for k in keywords_lower]
        if match_keys:
            criteria.append(_or_chain(match_keys))
        search_query = ' '.join(criteria) if criteria else 'ALL'

        yield {'stage': 'searching'}
        status, data = conn.search(None, search_query)
        if status != 'OK':
            raise ValueError('Ricerca IMAP fallita')
        uids = data[0].split()
        total_found = len(uids)
        truncated = total_found > MAX_MESSAGES
        if truncated:
            uids = uids[-MAX_MESSAGES:]

        total = len(uids)
        found = 0
        matched = 0
        pending = 0
        errors: List[str] = []

        for i, uid in enumerate(uids, start=1):
            status, msg_data = conn.fetch(uid, '(RFC822)')
            if status == 'OK' and msg_data and msg_data[0] is not None:
                raw_email = msg_data[0][1]
                msg = email_lib.message_from_bytes(raw_email)
                sender = _decode_header_value(msg.get('From'))
                subject = _decode_header_value(msg.get('Subject'))
                received_date = _parse_received_date(msg.get('Date'))
                no_filter = not senders_lower and not keywords_lower
                sender_ok = bool(senders_lower) and any(s in sender.lower() for s in senders_lower)
                subject_ok = bool(keywords_lower) and any(k in subject.lower() for k in keywords_lower)
                if no_filter or sender_ok or subject_ok:
                    body = _extract_body(msg)
                    found += 1
                    try:
                        result = email_enrich.process_incoming_email(sender, subject, body, received_date)
                        if result.get('matchedTransactionId'):
                            matched += 1
                        else:
                            pending += 1
                    except ValueError as e:
                        errors.append(str(e))

            yield {'stage': 'scanning', 'scanned': i, 'total': total, 'found': found, 'matched': matched}

        yield {
            'done': True,
            'scanned': total,
            'found': found,
            'matched': matched,
            'pending': pending,
            'errors': errors[:5],
            'truncated': truncated,
            'totalFound': total_found,
        }
    finally:
        try:
            conn.close()
        except Exception:
            pass
        try:
            conn.logout()
        except Exception:
            pass


def run_incremental_poll(
    person: Dict[str, Any],
    senders: List[str],
    subject_keywords: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Controllo periodico automatico (vedi email_poller.py): a differenza di
    run_backfill_iter (che riscansiona un intero intervallo di date ogni
    volta, pensato per un uso manuale una tantum), qui leggiamo SOLO i
    messaggi con UID maggiore dell'ultimo gia' processato
    (person['imap_last_uid']) - un controllo che gira ogni pochi minuti non
    puo' ririscansionare l'intera casella ogni volta, e farlo per data
    (SINCE oggi) riprocesserebbe piu' volte le stesse mail dello stesso
    giorno, creando ricevute duplicate (email_enrich.process_incoming_email
    non deduplica, inserisce sempre una nuova riga).

    Se person['imap_last_uid'] e' None, o se UIDVALIDITY e' cambiata (il
    server ha "ricreato" la cartella, i vecchi UID non hanno piu' lo stesso
    significato), NON processiamo nulla a ritroso - la storia la copre gia'
    il backfill manuale ("Importa storico email") - ci limitiamo a fissare da
    qui in poi una nuova baseline sull'UID piu' alto attualmente presente.

    Restituisce {'checked', 'matched', 'pending', 'newLastUid',
    'newUidValidity', 'baseline', 'errors'}: il chiamante deve salvare
    newLastUid/newUidValidity su persons per il prossimo giro."""
    if not person.get('imap_host') or not person.get('imap_username') or not person.get('imap_password'):
        raise ValueError('Credenziali IMAP non configurate per questa persona')

    port = person.get('imap_port') or (993 if person.get('imap_use_ssl', 1) else 143)
    if person.get('imap_use_ssl', 1):
        conn = imaplib.IMAP4_SSL(person['imap_host'], port)
    else:
        conn = imaplib.IMAP4(person['imap_host'], port)

    try:
        try:
            conn.login(person['imap_username'], person['imap_password'])
        except imaplib.IMAP4.error as e:
            raise ValueError(f'Accesso IMAP fallito: {e}')

        folder = person.get('imap_folder') or 'INBOX'
        status, _ = conn.select(folder, readonly=True)
        if status != 'OK':
            raise ValueError(f'Cartella "{folder}" non trovata')

        status, status_data = conn.status(folder, '(UIDVALIDITY)')
        uidvalidity = None
        if status == 'OK' and status_data and status_data[0]:
            m = re.search(rb'UIDVALIDITY (\d+)', status_data[0])
            if m:
                uidvalidity = int(m.group(1))

        last_uid = person.get('imap_last_uid')
        stored_uidvalidity = person.get('imap_uidvalidity')

        if last_uid is None or stored_uidvalidity != uidvalidity:
            status, search_data = conn.uid('search', None, 'ALL')
            uids = search_data[0].split() if status == 'OK' and search_data and search_data[0] else []
            new_last_uid = int(uids[-1]) if uids else 0
            return {
                'checked': 0, 'matched': 0, 'pending': 0, 'errors': [],
                'newLastUid': new_last_uid, 'newUidValidity': uidvalidity, 'baseline': True,
            }

        senders_lower = [s.strip().lower() for s in senders if s.strip()]
        keywords_lower = [k.strip().lower() for k in (subject_keywords or []) if k.strip()]

        status, search_data = conn.uid('search', None, f'UID {last_uid + 1}:*')
        raw_uids = search_data[0].split() if status == 'OK' and search_data and search_data[0] else []
        # "UID x:*" restituisce comunque l'ultimo messaggio esistente anche
        # quando x e' oltre l'ultimo UID reale (nessun messaggio nuovo): senza
        # questo filtro riprocesseremmo quello stesso messaggio ad ogni giro.
        uids = [u for u in raw_uids if int(u) > last_uid]

        checked = matched = pending = 0
        errors: List[str] = []
        max_uid = last_uid
        for uid in uids:
            max_uid = max(max_uid, int(uid))
            status, msg_data = conn.uid('fetch', uid, '(RFC822)')
            if status != 'OK' or not msg_data or msg_data[0] is None:
                continue
            raw_email = msg_data[0][1]
            msg = email_lib.message_from_bytes(raw_email)
            sender = _decode_header_value(msg.get('From'))
            subject = _decode_header_value(msg.get('Subject'))
            received_date = _parse_received_date(msg.get('Date'))
            no_filter = not senders_lower and not keywords_lower
            sender_ok = bool(senders_lower) and any(s in sender.lower() for s in senders_lower)
            subject_ok = bool(keywords_lower) and any(k in subject.lower() for k in keywords_lower)
            if not (no_filter or sender_ok or subject_ok):
                continue
            body = _extract_body(msg)
            checked += 1
            try:
                result = email_enrich.process_incoming_email(sender, subject, body, received_date)
                if result.get('matchedTransactionId'):
                    matched += 1
                else:
                    pending += 1
            except ValueError as e:
                errors.append(str(e))

        return {
            'checked': checked, 'matched': matched, 'pending': pending, 'errors': errors[:5],
            'newLastUid': max_uid, 'newUidValidity': uidvalidity, 'baseline': False,
        }
    finally:
        try:
            conn.close()
        except Exception:
            pass
        try:
            conn.logout()
        except Exception:
            pass


def run_backfill(
    person: Dict[str, Any],
    senders: List[str],
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    subject_keywords: Optional[List[str]] = None,
) -> Dict[str, Any]:
    result = None
    for update in run_backfill_iter(person, senders, date_from, date_to, subject_keywords):
        if update.get('done'):
            result = update
    return result

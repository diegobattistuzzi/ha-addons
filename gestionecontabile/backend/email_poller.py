import json
import threading
import time
from typing import Any, Dict, List

from . import config, db, email_backfill

# Stessi mittenti di default usati dall'endpoint manuale (/api/persons/{id}/
# email-backfill): il controllo periodico non ha un modo per farsi passare
# mittenti diversi ad ogni giro, quindi usa la stessa lista.
DEFAULT_SENDERS = ['paypal.com', 'amazon.it', 'amazon.com']

# Il ciclo si sveglia spesso (ogni minuto) ma controlla ogni persona solo se
# e' passato il suo intervallo configurato (_poll_interval_minutes): un
# risveglio breve serve solo a reagire in fretta se l'utente ha appena
# cambiato l'intervallo in Impostazioni, non per interrogare l'IMAP ogni minuto.
_LOOP_TICK_SECONDS = 60

_last_run_monotonic: Dict[int, float] = {}


def _fetchall(query: str, args: tuple = ()) -> List[Dict[str, Any]]:
    cursor = db.conn.execute(query, args)
    return [db.row_to_dict(row) for row in cursor.fetchall()]


def _poll_interval_minutes() -> int:
    """Legge l'intervallo da settings (impostato dall'utente in Setup, vedi
    /api/setup/complete syncIntervalMinutes) se presente, altrimenti il
    default dell'addon in config.yaml. Letto ad ogni giro (non una volta sola
    all'avvio) cosi' un cambio in Impostazioni ha effetto senza riavviare."""
    row = db.conn.execute("SELECT value FROM settings WHERE key = 'sync_interval_minutes'").fetchone()
    if row is not None:
        try:
            return max(5, int(json.loads(row['value'])))
        except (TypeError, ValueError, json.JSONDecodeError):
            pass
    return max(5, config.SYNC_INTERVAL_MINUTES)


def _poll_person(person: Dict[str, Any]) -> None:
    try:
        result = email_backfill.run_incremental_poll(
            person, senders=DEFAULT_SENDERS, subject_keywords=email_backfill.DEFAULT_SUBJECT_KEYWORDS,
        )
    except ValueError as e:
        print(f"[email_poller] controllo IMAP fallito per {person.get('name')}: {e}", flush=True)
        return
    db.conn.execute(
        "UPDATE persons SET imap_last_uid = ?, imap_uidvalidity = ?, imap_last_checked_at = datetime('now') WHERE id = ?",
        (result['newLastUid'], result['newUidValidity'], person['id']),
    )
    db.conn.commit()
    if result.get('baseline'):
        print(f"[email_poller] {person.get('name')}: primo controllo, baseline fissata (nessuna mail vecchia riprocessata)", flush=True)
    elif result.get('checked') or result.get('errors'):
        print(
            f"[email_poller] {person.get('name')}: {result.get('checked', 0)} mail nuove controllate, "
            f"{result.get('matched', 0)} abbinate, {result.get('pending', 0)} in attesa"
            + (f", errori: {result['errors']}" if result.get('errors') else ''),
            flush=True,
        )


def _poll_loop() -> None:
    while True:
        try:
            interval_seconds = _poll_interval_minutes() * 60
            persons = _fetchall(
                "SELECT * FROM persons WHERE imap_host IS NOT NULL AND imap_host != '' "
                "AND imap_username IS NOT NULL AND imap_username != '' "
                "AND imap_password IS NOT NULL AND imap_password != ''"
            )
            now = time.monotonic()
            for person in persons:
                last_run = _last_run_monotonic.get(person['id'], 0.0)
                if now - last_run < interval_seconds:
                    continue
                _last_run_monotonic[person['id']] = now
                _poll_person(person)
        except Exception as e:
            # Un errore su una persona/giro non deve fermare il polling per
            # sempre (l'addon gira in background, nessuno lo rilancerebbe a
            # mano se il thread muore silenziosamente).
            print(f'[email_poller] errore nel ciclo di controllo: {e}', flush=True)
        time.sleep(_LOOP_TICK_SECONDS)


def start_background_poller() -> None:
    """Avvia il controllo periodico IMAP in un thread daemon, da chiamare una
    sola volta all'avvio del server (vedi server.py, evento 'startup'). Ogni
    persona con credenziali IMAP configurate viene ricontrollata al proprio
    intervallo (indipendente dalle altre persone), leggendo solo i messaggi
    nuovi via UID (vedi email_backfill.run_incremental_poll) invece di
    riscansionare l'intera casella ad ogni giro."""
    thread = threading.Thread(target=_poll_loop, daemon=True, name='email-poller')
    thread.start()
    print(f'[email_poller] controllo periodico avviato (ogni {_poll_interval_minutes()} minuti)', flush=True)

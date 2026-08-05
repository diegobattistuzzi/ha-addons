import json
import threading
import time
from typing import Any

import httpx

from . import config, db
from .routers.ha import compute_sensor_data

# Il ciclo si sveglia spesso (ogni minuto) ma agisce solo se e' passato
# l'intervallo configurato (_notify_interval_minutes), stesso ragionamento di
# email_poller.py: una veglia breve serve solo a reagire in fretta se
# l'utente ha appena cambiato l'intervallo in Impostazioni.
_LOOP_TICK_SECONDS = 60

_last_run_monotonic = 0.0


def _setting(key: str, default: Any) -> Any:
    row = db.fetchone('SELECT value FROM settings WHERE key = ?', (key,))
    if row is None:
        return default
    try:
        return json.loads(row['value'])
    except (TypeError, ValueError):
        return default


def _set_setting(key: str, value: Any) -> None:
    db.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', (key, json.dumps(value)))


def _notify_enabled() -> bool:
    return bool(_setting('ha_notify_enabled', config.HA_NOTIFY_ENABLED))


def _notify_service() -> str:
    return str(_setting('ha_notify_service', config.HA_NOTIFY_SERVICE) or '')


def _notify_interval_minutes() -> int:
    try:
        return max(5, int(_setting('ha_notify_interval_minutes', config.HA_NOTIFY_INTERVAL_MINUTES)))
    except (TypeError, ValueError):
        return max(5, config.HA_NOTIFY_INTERVAL_MINUTES)


def _send_notification(title: str, message: str) -> None:
    if not config.SUPERVISOR_TOKEN:
        print(f'[ha_notifier] SUPERVISOR_TOKEN assente, notifica non inviata: {title}', flush=True)
        return
    service = _notify_service()
    if '.' not in service:
        print(f"[ha_notifier] 'ha_notify_service' non configurato correttamente ({service!r}), notifica non inviata: {title}", flush=True)
        return
    domain, service_name = service.split('.', 1)
    try:
        response = httpx.post(
            f'http://supervisor/core/api/services/{domain}/{service_name}',
            headers={'Authorization': f'Bearer {config.SUPERVISOR_TOKEN}', 'Content-Type': 'application/json'},
            json={'title': title, 'message': message},
            timeout=10.0,
        )
        if response.status_code >= 300:
            print(f'[ha_notifier] servizio {service} ha risposto {response.status_code}: {response.text}', flush=True)
    except httpx.HTTPError as e:
        print(f'[ha_notifier] impossibile chiamare {service}: {e}', flush=True)


def _check_over_budget(sensors: dict) -> None:
    """Notifica solo le categorie che sono ENTRATE in sforamento da
    l'ultimo giro (non ri-notifica ad ogni ciclo le stesse gia' segnalate), e
    dimentica lo stato ad ogni cambio di mese/anno cosi' un nuovo mese
    riparte pulito invece di restare "gia' notificato" per sempre."""
    month = sensors['month']
    year = month[:4]

    last_month = _setting('ha_notify_state_month', None)
    already_monthly = set(_setting('ha_notify_state_over_budget_monthly', [])) if last_month == month else set()
    current_monthly = set(sensors['over_budget'])
    new_monthly = current_monthly - already_monthly
    if new_monthly and _notify_enabled():
        _send_notification('Spese di casa - Budget sforato', 'Categorie oltre il budget mensile: ' + ', '.join(sorted(new_monthly)))
    _set_setting('ha_notify_state_month', month)
    _set_setting('ha_notify_state_over_budget_monthly', sorted(current_monthly))

    last_year = _setting('ha_notify_state_year', None)
    already_annual = set(_setting('ha_notify_state_over_budget_annual', [])) if last_year == year else set()
    current_annual = set(sensors['over_budget_annual'])
    new_annual = current_annual - already_annual
    if new_annual and _notify_enabled():
        _send_notification('Spese di casa - Budget annuale sforato', 'Categorie oltre il budget annuale: ' + ', '.join(sorted(new_annual)))
    _set_setting('ha_notify_state_year', year)
    _set_setting('ha_notify_state_over_budget_annual', sorted(current_annual))


def _check_pending_review(sensors: dict) -> None:
    """Notifica solo quando compaiono NUOVE transazioni pending rispetto
    all'ultimo giro (il conteggio sale): se l'utente le revisiona e il
    conteggio scende, aggiorna lo stato senza notificare, cosi' il prossimo
    arrivo torna a far scattare la notifica invece di restare "gia' avvisato"
    per sempre a un conteggio piu' basso."""
    pending = sensors['pending_review']
    last_notified = _setting('ha_notify_state_pending_count', 0)
    if pending > last_notified and _notify_enabled():
        _send_notification('Spese di casa - Transazioni da revisionare', f'{pending} transazioni categorizzate dall\'AI sono in attesa di conferma.')
    _set_setting('ha_notify_state_pending_count', pending)


def run_check_now() -> dict:
    """Esegue un giro di controllo immediato (usato sia dal loop periodico
    che da POST /api/ha/sync per un check on-demand)."""
    sensors = compute_sensor_data()
    _check_over_budget(sensors)
    _check_pending_review(sensors)
    return sensors


def _poll_loop() -> None:
    global _last_run_monotonic
    while True:
        try:
            interval_seconds = _notify_interval_minutes() * 60
            now = time.monotonic()
            if now - _last_run_monotonic >= interval_seconds:
                _last_run_monotonic = now
                run_check_now()
        except Exception as e:
            # Un errore in un giro non deve fermare per sempre il thread di
            # notifica (nessuno lo rilancerebbe a mano, vedi email_poller.py).
            print(f'[ha_notifier] errore nel ciclo di controllo: {e}', flush=True)
        time.sleep(_LOOP_TICK_SECONDS)


def start_background_notifier() -> None:
    thread = threading.Thread(target=_poll_loop, daemon=True, name='ha-notifier')
    thread.start()
    print(f'[ha_notifier] controllo periodico avviato (ogni {_notify_interval_minutes()} minuti)', flush=True)

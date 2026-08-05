import json
import os
from pathlib import Path

DATA_DIR = Path(os.getenv('DATA_DIR', Path.cwd() / 'data'))
DATA_DIR.mkdir(parents=True, exist_ok=True)

PORT = int(os.getenv('PORT', '8099'))
DB_PATH = DATA_DIR / 'casaspese.db'

DOCUMENTS_DIR = DATA_DIR / 'documents'
DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)

SUPERVISOR_TOKEN = os.getenv('SUPERVISOR_TOKEN', '')
HA_BASE_URL = os.getenv('HA_BASE_URL', 'http://homeassistant:8123')

# HA scrive le opzioni configurate dall'utente nell'addon (config.yaml -> options)
# in /data/options.json. In sviluppo locale si puo' creare a mano da options.json.example.
_OPTIONS_PATH = DATA_DIR / 'options.json'
try:
    _options = json.loads(_OPTIONS_PATH.read_text(encoding='utf-8')) if _OPTIONS_PATH.exists() else {}
except (json.JSONDecodeError, OSError):
    _options = {}


def _option(key: str, env_name: str, default: str = '') -> str:
    value = _options.get(key)
    if value not in (None, ''):
        return value
    return os.getenv(env_name, default)


AI_PROVIDER = _option('ai_provider', 'AI_PROVIDER', 'openai')
AI_MODEL = _option('ai_model', 'AI_MODEL', 'gpt-4o-mini')
OPENAI_API_KEY = _option('openai_api_key', 'OPENAI_API_KEY', '')
ANTHROPIC_API_KEY = _option('anthropic_api_key', 'ANTHROPIC_API_KEY', '')
HA_TOKEN = _option('ha_token', 'HA_TOKEN', '')

# URL pubblico (https, dietro il reverse proxy nginx) usato solo per comporre
# il link/QR di accesso mobile - vedi POST /api/mobile-tokens in server.py.
PUBLIC_URL = _option('public_url', 'PUBLIC_URL', '').rstrip('/')

# Default per email_poller.py se l'utente non ha ancora salvato una propria
# preferenza in settings.sync_interval_minutes (via Setup): _option puo'
# restituire un int gia' pronto da options.json o una stringa dall'env, da qui
# il fallback esplicito invece di fidarsi del tipo.
try:
    SYNC_INTERVAL_MINUTES = int(_option('sync_interval_minutes', 'SYNC_INTERVAL_MINUTES', '30'))
except (TypeError, ValueError):
    SYNC_INTERVAL_MINUTES = 30

# Notifiche verso Home Assistant (via Supervisor API, vedi ha_notifier.py):
# solo default di bootstrap, l'utente puo' sovrascriverli da Impostazioni
# (tabella settings, stesso schema di sync_interval_minutes) senza riavviare.
HA_NOTIFY_ENABLED = str(_option('ha_notify_enabled', 'HA_NOTIFY_ENABLED', 'false')).lower() in ('1', 'true', 'yes')
HA_NOTIFY_SERVICE = _option('ha_notify_service', 'HA_NOTIFY_SERVICE', '')
try:
    HA_NOTIFY_INTERVAL_MINUTES = int(_option('ha_notify_interval_minutes', 'HA_NOTIFY_INTERVAL_MINUTES', '15'))
except (TypeError, ValueError):
    HA_NOTIFY_INTERVAL_MINUTES = 15

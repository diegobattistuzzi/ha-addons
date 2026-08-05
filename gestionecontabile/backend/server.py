from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import access, config, email_poller, ha_notifier
from .mcp_server import AuthForwardingMiddleware
from .mcp_server import mcp as mcp_server
from .migrate import run_migrations
from .routers import (
    accounts,
    ai,
    categories,
    documents,
    email_receipts,
    ha,
    persons,
    reports,
    rules,
    setup,
    system,
    transactions,
)

BASE_DIR = Path(__file__).resolve().parent
PUBLIC_DIR = BASE_DIR / 'public'


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        run_migrations()
    except Exception as e:
        print(f'[startup] ERRORE migrazione: {e}', flush=True)
        raise
    email_poller.start_background_poller()
    ha_notifier.start_background_notifier()
    # Il session manager del server MCP montato su /mcp (vedi sotto) va avviato
    # esplicitamente qui: Starlette non propaga gli eventi di lifespan alle
    # sotto-app montate con app.mount(), quindi senza questo 'async with' i tool
    # MCP risponderebbero con un errore di sessione non inizializzata.
    async with mcp_server.session_manager.run():
        yield


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_methods=['*'],
    allow_headers=['*'],
    expose_headers=['X-Total-Count'],
)
app.mount('/mcp', AuthForwardingMiddleware(mcp_server.streamable_http_app()))


@app.middleware('http')
async def enforce_public_gateway_auth(request: Request, call_next):
    """Chiude l'accesso anonimo alle API (incluso il connettore MCP su /mcp,
    vedi mcp_server.py) quando gira come add-on HA (unica situazione in cui
    puo' esistere una porta pubblica per l'uso mobile).

    L'Ingress di HA e' l'UNICO percorso fidato senza token: il Supervisor
    inietta l'header 'X-Ingress-Path' quando fa da proxy, un client esterno
    che raggiunge l'add-on da un'altra strada (es. la porta pubblica dietro
    nginx per la PWA mobile) non puo' impostarlo lui stesso SE nginx lo
    rimuove dagli header in ingresso (vedi README.md) - per questo motivo
    NON e' sufficiente controllare X-Remote-User-Id/X-Person-Id (quelli si
    possono spedire da chiunque): qui serve o l'Ingress genuino, un token
    mobile valido, o il token dell'add-on (vedi access.is_valid_ha_token,
    usato dall'integrazione HA custom_components/casaspese per chiamare
    /api/ha/* dalla rete interna del Supervisor, fuori dall'Ingress),
    altrimenti chiunque su internet leggerebbe conti e spese condivise senza
    autenticarsi. In sviluppo locale (fuori da HA, niente SUPERVISOR_TOKEN)
    il controllo resta disattivato.
    """
    if config.SUPERVISOR_TOKEN and (request.url.path.startswith('/api') or request.url.path.startswith('/mcp')):
        if not request.headers.get('x-ingress-path'):
            if access.get_person_from_bearer(request) is None and not access.is_valid_ha_token(request):
                return JSONResponse(status_code=401, content={'detail': 'Autenticazione richiesta'})
    return await call_next(request)


@app.exception_handler(StarletteHTTPException)
async def custom_http_exception_handler(request: Request, exc: StarletteHTTPException):
    index_file = PUBLIC_DIR / 'index.html'
    if exc.status_code == 404 and not request.url.path.startswith('/api') and index_file.exists():
        return FileResponse(str(index_file), media_type='text/html')
    return JSONResponse({'error': exc.detail}, status_code=exc.status_code)


for _router_module in (
    system,
    setup,
    persons,
    accounts,
    categories,
    rules,
    documents,
    reports,
    ai,
    ha,
    email_receipts,
    transactions,
):
    app.include_router(_router_module.router)


# SPA fallback: montato DOPO tutte le route API così non le intercetta
if PUBLIC_DIR.exists():
    app.mount('/', StaticFiles(directory=str(PUBLIC_DIR)), name='public')

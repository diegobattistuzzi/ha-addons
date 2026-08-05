"""Server MCP (Model Context Protocol) - espone in sola lettura conti,
transazioni e report a client MCP (es. Claude), montato come sotto-app ASGI
sotto /mcp nella stessa app FastAPI (vedi server.py: app.mount('/mcp', ...)).

Ogni tool NON riscrive la logica di query/visibilita': chiama in-process gli
stessi endpoint REST di server.py via ASGITransport, cosi' riusa esattamente
le stesse regole di access.py (segregazione conti/transazioni personali) e
non rischia di divergere da esse nel tempo.

Autenticazione: il client MCP deve passare lo stesso Bearer token mobile
usato dalla PWA (vedi POST /api/mobile-tokens in server.py) nell'header
Authorization della richiesta HTTP verso /mcp. La sotto-app FastMCP non ha
un modo diretto per leggere quell'header dentro ai tool (dipende dalla
versione della SDK mcp), quindi lo si cattura con un middleware ASGI
minimale (vedi AuthForwardingMiddleware sotto) che lo mette in una
contextvar leggibile da ogni tool. Senza Authorization valido, le chiamate
verso l'API interna arrivano comunque soggette al gate di
enforce_public_gateway_auth in server.py (nessun bypass).
"""

from contextvars import ContextVar
from typing import Any, Dict, Optional

import httpx
from mcp.server.fastmcp import FastMCP
from starlette.types import ASGIApp, Receive, Scope, Send

_current_authorization: ContextVar[Optional[str]] = ContextVar('_current_authorization', default=None)

mcp = FastMCP(
    name='gestionecontabile',
    instructions=(
        'Strumenti in sola lettura su conti, transazioni e report di gestione spese familiari/condivise. '
        "Gli importi sono in euro. Le date sono in formato ISO 'YYYY-MM-DD'."
    ),
    # Di default FastMCP serve se stesso su '/mcp': dato che server.py monta gia'
    # questa sotto-app sotto il prefisso /mcp (app.mount('/mcp', ...)), lasciare il
    # default risulterebbe in /mcp/mcp. Qui si vuole che risponda alla radice della
    # sotto-app, cioe' esattamente a /mcp.
    streamable_http_path='/',
)


class AuthForwardingMiddleware:
    """Cattura l'header Authorization della richiesta HTTP verso /mcp e lo
    espone ai tool tramite contextvar. ASGI puro (non BaseHTTPMiddleware) per
    non bufferizzare lo streaming SSE usato dal transport streamable-http."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope['type'] != 'http':
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get('headers') or [])
        auth = headers.get(b'authorization')
        token = _current_authorization.set(auth.decode('latin-1') if auth else None)
        try:
            await self.app(scope, receive, send)
        finally:
            _current_authorization.reset(token)


async def _api_get(path: str, params: Optional[Dict[str, Any]] = None) -> Any:
    """Chiama in-process un endpoint GET dell'app FastAPI principale,
    inoltrando l'Authorization catturato da AuthForwardingMiddleware."""
    from .server import app as fastapi_app  # import ritardato: evita import circolare a modulo caricato

    headers = {}
    auth = _current_authorization.get()
    if auth:
        headers['authorization'] = auth

    transport = httpx.ASGITransport(app=fastapi_app)
    async with httpx.AsyncClient(transport=transport, base_url='http://mcp-internal') as client:
        response = await client.get(path, params=params or {}, headers=headers)
        response.raise_for_status()
        return response.json()


@mcp.tool()
async def list_accounts() -> Any:
    """Elenca i conti attivi con saldo corrente."""
    return await _api_get('/api/accounts')


@mcp.tool()
async def get_account_balance_history(account_id: int) -> Any:
    """Andamento del saldo progressivo di un conto, transazione per transazione."""
    return await _api_get(f'/api/accounts/{account_id}/running-balances')


@mcp.tool()
async def list_transactions(
    month: Optional[str] = None,
    account_id: Optional[int] = None,
    category_id: Optional[int] = None,
    person_id: Optional[int] = None,
    destination: Optional[str] = None,
    confirmed: Optional[bool] = None,
    limit: Optional[int] = None,
) -> Any:
    """Elenca le transazioni, filtrabili per mese (YYYY-MM), conto, categoria, persona,
    destinazione ('family'/'personal') e stato di conferma."""
    params = {
        'month': month,
        'accountId': account_id,
        'categoryId': category_id,
        'personId': person_id,
        'destination': destination,
        'limit': limit,
    }
    if confirmed is not None:
        params['confirmed' if confirmed else 'unconfirmed'] = 'true'
    return await _api_get('/api/transactions', {k: v for k, v in params.items() if v is not None})


@mcp.tool()
async def get_transaction(transaction_id: int) -> Any:
    """Dettaglio di una singola transazione."""
    return await _api_get(f'/api/transactions/{transaction_id}')


@mcp.tool()
async def list_categories() -> Any:
    """Elenca le categorie di spesa/entrata disponibili."""
    return await _api_get('/api/categories')


@mcp.tool()
async def list_rules() -> Any:
    """Elenca le regole di categorizzazione automatica configurate."""
    return await _api_get('/api/rules')


@mcp.tool()
async def get_summary_report(month: Optional[str] = None, account_id: Optional[int] = None) -> Any:
    """Riepilogo entrate/uscite per categoria di un mese (YYYY-MM, default mese corrente),
    con confronto verso il mese precedente e lo stesso mese dell'anno prima."""
    params = {'month': month, 'accountId': account_id}
    return await _api_get('/api/reports/summary', {k: v for k, v in params.items() if v is not None})


@mcp.tool()
async def get_trend_report(months: Optional[int] = None, account_id: Optional[int] = None) -> Any:
    """Andamento mensile di spese familiari/personali ed entrate sugli ultimi N mesi (default 6)."""
    params = {'months': months, 'accountId': account_id}
    return await _api_get('/api/reports/trend', {k: v for k, v in params.items() if v is not None})


@mcp.tool()
async def get_top_merchants(month: Optional[str] = None, limit: Optional[int] = None, account_id: Optional[int] = None) -> Any:
    """Esercenti/controparti con la spesa maggiore in un mese (YYYY-MM, default mese corrente)."""
    params = {'month': month, 'limit': limit, 'accountId': account_id}
    return await _api_get('/api/reports/top-merchants', {k: v for k, v in params.items() if v is not None})


@mcp.tool()
async def get_pivot_report(months: Optional[int] = None, account_id: Optional[int] = None) -> Any:
    """Tabella incrociata categoria/mese delle spese sugli ultimi N mesi (default 6)."""
    params = {'months': months, 'accountId': account_id}
    return await _api_get('/api/reports/pivot', {k: v for k, v in params.items() if v is not None})


@mcp.tool()
async def get_balance_report(month: Optional[str] = None, period: Optional[str] = None) -> Any:
    """Saldi ed eventuali rimborsi dovuti tra persone per le spese condivise. `month` in
    formato YYYY-MM (default mese corrente); `period='all'` considera tutto lo storico."""
    params = {'month': month, 'period': period}
    return await _api_get('/api/reports/balance', {k: v for k, v in params.items() if v is not None})


@mcp.tool()
async def list_subscriptions() -> Any:
    """Elenca gli abbonamenti/spese ricorrenti rilevati automaticamente."""
    return await _api_get('/api/reports/subscriptions')


@mcp.tool()
async def list_pending_ai_transactions() -> Any:
    """Elenca le transazioni proposte dall'AI ancora da confermare."""
    return await _api_get('/api/transactions/pending-ai')


@mcp.tool()
async def list_duplicate_transactions() -> Any:
    """Elenca le possibili transazioni duplicate da revisionare."""
    return await _api_get('/api/transactions/duplicates')

import json
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from .. import access, db
from ..db import execute, fetchall, fetchone
from ..util import ensure_int

router = APIRouter()

# Frammento SQL riusato in tutti i report/aggregati spese-entrate: esclude i
# 'transfer' (gia' cosi' prima) e i checkpoint 'opening_balance' (saldo
# iniziale annuale, vedi accounts._compute_account_balances) - ne' gli uni ne'
# gli altri sono spese/entrate reali. Sicuro anche quando la join su categories
# e' una LEFT JOIN (c.type puo' essere NULL) o una JOIN normale (mai NULL, il
# ramo IS NULL resta innocuo).
_NON_SPEND_TYPES_SQL = "(c.type IS NULL OR c.type NOT IN ('transfer', 'opening_balance'))"


def _period_expense_income(pattern: str, vis_clause_t: str, vis_args_t: tuple, account_clause: str = '', account_args: tuple = ()) -> Dict[str, float]:
    """Totali spese/entrate per un periodo (usato per il confronto mese/anno
    precedente): stessa logica di calcolo di report_summary (esclude i
    'transfer' e rispetta la visibilita' personale/famiglia), ma senza il
    dettaglio per categoria - qui serve solo il totale."""
    row = fetchone(
        'SELECT '
        'COALESCE(SUM(CASE WHEN t.amount<0 THEN ABS(t.amount) ELSE 0 END),0) AS total_expenses, '
        'COALESCE(SUM(CASE WHEN t.amount>0 THEN t.amount ELSE 0 END),0) AS total_income '
        'FROM transactions t LEFT JOIN categories c ON c.id = t.category_id '
        f"WHERE t.date LIKE ? AND t.is_confirmed=1 AND {_NON_SPEND_TYPES_SQL} AND {vis_clause_t}{account_clause}",
        (pattern,) + vis_args_t + account_args,
    )
    return {'total_expenses': row['total_expenses'], 'total_income': row['total_income']}


@router.get('/api/reports/summary')
def report_summary(request: Request):
    month = request.query_params.get('month') or datetime.utcnow().strftime('%Y-%m')
    account_id = ensure_int(request.query_params.get('accountId'))
    return _report_summary_data(request, month, account_id)


def _report_summary_data(request: Request, month: str, account_id: Optional[int]) -> Dict[str, Any]:
    """Dati aggregati del riepilogo mensile: estratta da report_summary cosi'
    puo' essere richiamata anche da /api/ai/summary con un month/accountId
    che arrivano dal body invece che dalla query string."""
    pattern = f'{month}%'
    year_pattern = f'{month[:4]}%'
    current_person = access.get_current_person(request)
    vis_clause_t, vis_args_t = access.transaction_visibility(current_person, alias='t')
    account_clause = ' AND t.account_id = ?' if account_id else ''
    account_args = (account_id,) if account_id else ()
    # Mese precedente: sottrarre un giorno dal primo del mese corrente da'
    # sempre l'ultimo giorno del mese precedente, gestendo correttamente anche
    # il cambio di anno (es. gennaio -> dicembre dell'anno prima) senza dover
    # calcolare a mano i giorni per ogni mese.
    year_n, month_n = int(month[:4]), int(month[5:7])
    previous_month_str = (datetime(year_n, month_n, 1) - timedelta(days=1)).strftime('%Y-%m')
    previous_year_month_str = f'{year_n - 1}-{month[5:7]}'
    previous_month = _period_expense_income(f'{previous_month_str}%', vis_clause_t, vis_args_t, account_clause, account_args)
    previous_year_same_month = _period_expense_income(f'{previous_year_month_str}%', vis_clause_t, vis_args_t, account_clause, account_args)
    # Le transazioni categoria 'transfer' (es. pagamento carta di credito verso il
    # conto di appoggio) non sono spese reali: la spesa e' gia' contata sulla carta.
    totals = fetchone(
        'SELECT '
        'COALESCE(SUM(CASE WHEN t.date LIKE ? AND t.amount<0 THEN ABS(t.amount) ELSE 0 END),0) AS total_expenses, '
        'COALESCE(SUM(CASE WHEN t.date LIKE ? AND t.amount>0 THEN t.amount ELSE 0 END),0) AS total_income, '
        'COALESCE(SUM(CASE WHEN t.amount<0 THEN ABS(t.amount) ELSE 0 END),0) AS total_expenses_year, '
        'COALESCE(SUM(CASE WHEN t.amount>0 THEN t.amount ELSE 0 END),0) AS total_income_year '
        'FROM transactions t LEFT JOIN categories c ON c.id = t.category_id '
        f"WHERE t.date LIKE ? AND t.is_confirmed=1 AND {_NON_SPEND_TYPES_SQL} AND {vis_clause_t}{account_clause}",
        (pattern, pattern, year_pattern) + vis_args_t + account_args,
    )
    by_category = fetchall(
        'SELECT c.id, c.name, c.icon, c.color, c.budget_monthly, c.budget_annual, '
        'COALESCE(SUM(CASE WHEN t.date LIKE ? THEN ABS(t.amount) ELSE 0 END),0) AS spent, '
        'COALESCE(SUM(ABS(t.amount)),0) AS spent_year '
        'FROM transactions t JOIN categories c ON c.id = t.category_id '
        f"WHERE t.date LIKE ? AND t.amount<0 AND t.is_confirmed=1 AND {_NON_SPEND_TYPES_SQL} AND {vis_clause_t}{account_clause} "
        'GROUP BY c.id ORDER BY spent DESC',
        (pattern, year_pattern) + vis_args_t + account_args,
    )
    by_destination = fetchall(
        'SELECT t.destination, COALESCE(SUM(ABS(t.amount)),0) AS total FROM transactions t '
        'LEFT JOIN categories c ON c.id = t.category_id '
        f"WHERE t.date LIKE ? AND t.amount<0 AND t.is_confirmed=1 AND {_NON_SPEND_TYPES_SQL} AND {vis_clause_t}{account_clause} "
        'GROUP BY t.destination',
        (pattern,) + vis_args_t + account_args,
    )
    return {
        'month': month,
        'total_expenses': totals['total_expenses'],
        'total_income': totals['total_income'],
        'total_expenses_year': totals['total_expenses_year'],
        'total_income_year': totals['total_income_year'],
        'byCategory': by_category,
        'byDestination': by_destination,
        'previousMonth': previous_month,
        'previousYearSameMonth': previous_year_same_month,
    }


@router.get('/api/reports/top-merchants')
def report_top_merchants(request: Request):
    month = request.query_params.get('month') or datetime.utcnow().strftime('%Y-%m')
    limit = ensure_int(request.query_params.get('limit')) or 10
    account_id = ensure_int(request.query_params.get('accountId'))
    return _report_top_merchants_data(request, month, limit, account_id)


def _report_top_merchants_data(request: Request, month: str, limit: int, account_id: Optional[int]) -> List[Dict[str, Any]]:
    pattern = f'{month}%'
    vis_clause_t, vis_args_t = access.transaction_visibility(access.get_current_person(request), alias='t')
    account_clause = ' AND t.account_id = ?' if account_id else ''
    account_args = (account_id,) if account_id else ()
    rows = fetchall(
        'SELECT t.merchant_name, COUNT(*) AS occurrences, COALESCE(SUM(ABS(t.amount)),0) AS total '
        'FROM transactions t LEFT JOIN categories c ON c.id = t.category_id '
        f"WHERE t.date LIKE ? AND t.amount<0 AND t.is_confirmed=1 AND t.merchant_name IS NOT NULL "
        f"AND {_NON_SPEND_TYPES_SQL} AND {vis_clause_t}{account_clause} "
        'GROUP BY t.merchant_name ORDER BY total DESC LIMIT ?',
        (pattern,) + vis_args_t + account_args + (limit,),
    )
    return rows


@router.get('/api/reports/trend')
def report_trend(request: Request):
    months = ensure_int(request.query_params.get('months')) or 6
    account_id = ensure_int(request.query_params.get('accountId'))
    return _report_trend_data(request, months, account_id)


def _report_trend_data(request: Request, months: int, account_id: Optional[int]) -> List[Dict[str, Any]]:
    vis_clause_t, vis_args_t = access.transaction_visibility(access.get_current_person(request), alias='t')
    account_clause = ' AND t.account_id = ?' if account_id else ''
    account_args = (account_id,) if account_id else ()
    rows = fetchall(
        "SELECT strftime('%Y-%m', t.date) AS month, "
        "COALESCE(SUM(CASE WHEN t.amount<0 AND t.destination='family' THEN ABS(t.amount) ELSE 0 END),0) AS family, "
        "COALESCE(SUM(CASE WHEN t.amount<0 AND t.destination!='family' THEN ABS(t.amount) ELSE 0 END),0) AS personal, "
        "COALESCE(SUM(CASE WHEN t.amount>0 THEN t.amount ELSE 0 END),0) AS income "
        "FROM transactions t LEFT JOIN categories c ON c.id = t.category_id "
        f"WHERE t.is_confirmed=1 AND {_NON_SPEND_TYPES_SQL} AND {vis_clause_t}{account_clause} "
        "GROUP BY strftime('%Y-%m', t.date) ORDER BY month DESC LIMIT ?",
        vis_args_t + account_args + (months,),
    )
    return list(reversed(rows))


@router.get('/api/reports/pivot')
def report_pivot(request: Request):
    """Pivot categoria x mese per la tabella pivot in Report: righe = categorie
    di spesa, colonne = ultimi N mesi, celle = totale speso in quel mese per
    quella categoria. Endpoint separato da report_trend (che aggrega per
    destinazione family/personal, non per categoria)."""
    months_n = ensure_int(request.query_params.get('months')) or 6
    vis_clause_t, vis_args_t = access.transaction_visibility(access.get_current_person(request), alias='t')
    account_id = ensure_int(request.query_params.get('accountId'))
    account_clause = ' AND t.account_id = ?' if account_id else ''
    account_args = (account_id,) if account_id else ()

    # Elenco fisso degli ultimi N mesi (piu' vecchio per primo): serve per
    # avere colonne stabili anche per i mesi senza spese in una data
    # categoria, che la GROUP BY sotto altrimenti ometterebbe del tutto.
    today = datetime.utcnow()
    month_list = []
    y, m = today.year, today.month
    for _ in range(months_n):
        month_list.append(f'{y:04d}-{m:02d}')
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    month_list.reverse()
    earliest = f'{month_list[0]}-01'

    rows = fetchall(
        "SELECT c.id, c.name, c.icon, c.color, strftime('%Y-%m', t.date) AS month, "
        'COALESCE(SUM(ABS(t.amount)),0) AS total '
        'FROM transactions t JOIN categories c ON c.id = t.category_id '
        f"WHERE t.amount<0 AND t.is_confirmed=1 AND {_NON_SPEND_TYPES_SQL} AND t.date >= ? AND {vis_clause_t}{account_clause} "
        "GROUP BY c.id, month",
        (earliest,) + vis_args_t + account_args,
    )

    by_category: Dict[int, Dict[str, Any]] = {}
    for r in rows:
        cat = by_category.setdefault(r['id'], {
            'id': r['id'], 'name': r['name'], 'icon': r['icon'], 'color': r['color'],
            'totals': {mo: 0.0 for mo in month_list}, 'total': 0.0,
        })
        cat['totals'][r['month']] = r['total']
        cat['total'] += r['total']

    result_rows = sorted(by_category.values(), key=lambda c: c['total'], reverse=True)
    return {'months': month_list, 'rows': result_rows}


@router.get('/api/reports/balance')
def report_balance(request: Request):
    month = request.query_params.get('month') or datetime.utcnow().strftime('%Y-%m')
    period = request.query_params.get('period') or 'month'
    pattern = '%' if period == 'all' else f'{month}%'
    persons = fetchall('SELECT id, name, color FROM persons ORDER BY id')
    if not persons:
        return {'month': month, 'period': period, 'persons': [], 'debt': None}
    tx_rows = fetchall(
        'SELECT t.paid_by_person_id, t.split_person_id, t.amount, t.destination, t.split_ratio, '
        'c.type AS cat_type, a.ownership '
        'FROM transactions t LEFT JOIN categories c ON c.id = t.category_id LEFT JOIN accounts a ON a.id = t.account_id '
        'WHERE t.date LIKE ? AND t.is_confirmed=1',
        (pattern,),
    )
    stats = {p['id']: {'id': p['id'], 'name': p['name'], 'color': p['color'], 'contributed': 0.0, 'personalSpent': 0.0, 'familySpent': 0.0} for p in persons}
    num_persons = max(len(persons), 2)
    for tx in tx_rows:
        pid = tx['paid_by_person_id']
        amount = tx['amount'] or 0
        dest = tx['destination']
        cat_type = tx['cat_type']
        ownership = tx['ownership']
        if amount > 0:
            # Un trasferimento 'transfer' in entrata su un conto condiviso,
            # attribuito a una persona (paid_by_person_id valorizzato a mano
            # in Transazioni), e' un versamento al fondo comune: va accreditato
            # come contributo esattamente come un'entrata normale. Va escluso
            # dai report di spesa/entrata (vedi _NON_SPEND_TYPES_SQL) ma NON da
            # qui, altrimenti chi versa nel conto comune non risulta mai
            # aver contribuito.
            if ownership == 'shared' and pid and pid in stats:
                stats[pid]['contributed'] += amount
        else:
            # Il lato in uscita di un trasferimento (es. addebito riepilogativo
            # carta di credito verso il conto di appoggio, o il prelievo dal
            # conto personale che alimenta il versamento sopra) non e' mai una
            # spesa: la spesa vera e' gia' contata altrove (sulla carta, o non
            # e' affatto una spesa se e' solo redistribuzione di soldi propri).
            if cat_type == 'transfer':
                continue
            abs_amount = abs(amount)
            if dest == 'personal':
                # Una spesa personale pesa sul bilancio comune solo se pagata
                # con soldi del conto condiviso (ha eroso il fondo comune).
                # Se pagata da un conto personale, sono soldi gia' suoi: non
                # deve incidere su quanto deve/e' dovuto tra le persone.
                if ownership == 'shared' and pid and pid in stats:
                    stats[pid]['personalSpent'] += abs_amount
            elif dest == 'split' and tx['split_person_id'] and tx['split_person_id'] in stats:
                # Spesa divisa solo tra chi ha pagato e la persona indicata,
                # secondo split_ratio (quota di chi ha pagato), non tra tutti.
                # Chi ha pagato ha anticipato l'intera cifra: va accreditato per
                # il totale (come un versamento), non solo per la propria quota,
                # altrimenti risulterebbe lui il debitore invece del creditore.
                ratio = tx['split_ratio'] if tx['split_ratio'] is not None else 0.5
                other_pid = tx['split_person_id']
                if pid and pid in stats:
                    stats[pid]['contributed'] += abs_amount
                    stats[pid]['familySpent'] += abs_amount * ratio
                stats[other_pid]['familySpent'] += abs_amount * (1 - ratio)
            else:
                share = abs_amount / num_persons
                for p in persons:
                    stats[p['id']]['familySpent'] += share
    result = []
    for s in stats.values():
        net = s['contributed'] - s['personalSpent'] - s['familySpent']
        result.append({
            **s,
            'contributed': round(s['contributed'], 2),
            'personalSpent': round(s['personalSpent'], 2),
            'familySpent': round(s['familySpent'], 2),
            'net': round(net, 2),
        })
    debt = None
    if len(result) == 2:
        a, b = result[0], result[1]
        diff = round((a['net'] - b['net']), 2)
        if abs(diff) > 0.01:
            debtor, creditor = (a, b) if diff < 0 else (b, a)
            debt = {'debtor': debtor['name'], 'creditor': creditor['name'], 'amount': round(abs(diff) / 2, 2)}
    # Il calcolo del debito sopra usa il dettaglio (contributed/personalSpent/
    # familySpent) di TUTTE le persone - e' necessario per essere corretto (le
    # spese personali pagate dal conto comune incidono sul fondo comune anche
    # se non sono "tue"). Ma quel dettaglio riga per riga di un'altra persona
    # e' esattamente cio' che non deve essere visibile (bug reale segnalato
    # dall'utente): nella risposta esponiamo solo la card della persona
    # corrente, il banner "chi deve cosa" (gia' senza dettagli) resta invariato
    # per tutti.
    current_person = access.get_current_person(request)
    visible_persons = [p for p in result if p['id'] == current_person['id']] if current_person else result
    return {'month': month, 'period': period, 'persons': visible_persons, 'debt': debt}


@router.get('/api/reports/subscriptions')
def report_subscriptions(request: Request):
    vis_clause_t, vis_args_t = access.transaction_visibility(access.get_current_person(request), alias='t')
    rows = fetchall(
        'SELECT t.merchant_name, ABS(t.amount) AS amount, COUNT(*) AS occurrences, MAX(t.date) AS last_date '
        'FROM transactions t LEFT JOIN categories c ON c.id = t.category_id '
        f"WHERE t.amount<0 AND t.is_confirmed=1 AND t.merchant_name IS NOT NULL "
        f"AND {_NON_SPEND_TYPES_SQL} AND {vis_clause_t} "
        'GROUP BY t.merchant_name, ROUND(ABS(t.amount),0) HAVING occurrences>=2 ORDER BY amount DESC',
        vis_args_t,
    )
    total_monthly = sum(row['amount'] for row in rows)
    return {'subscriptions': rows, 'totalMonthly': total_monthly}


@router.post('/api/reports/balance/{month}/settle')
def report_balance_settle(month: str):
    return {'settled': True, 'month': month}


# Dimensioni disponibili nel report builder: 'select' e' anche l'espressione di
# GROUP BY (deve restare l'espressione grezza, non l'alias, perche' SQLite non
# accetta sempre un alias di SELECT dentro GROUP BY in presenza di funzioni
# come strftime). 'join' e' vuoto per le dimensioni gia' su transactions.
_REPORT_DIMENSIONS = {
    'category': {
        'select': "COALESCE(categories.name, 'Senza categoria')",
        'join': 'LEFT JOIN categories ON categories.id = transactions.category_id',
    },
    'account': {
        'select': 'accounts.name',
        'join': 'JOIN accounts ON accounts.id = transactions.account_id',
    },
    'person': {
        'select': "COALESCE(persons.name, 'Non specificato')",
        'join': 'LEFT JOIN persons ON persons.id = transactions.paid_by_person_id',
    },
    'destination': {
        'select': 'transactions.destination',
        'join': '',
    },
    'month': {
        'select': "strftime('%Y-%m', transactions.date)",
        'join': '',
    },
    'day': {
        'select': 'transactions.date',
        'join': '',
    },
    'merchant': {
        'select': "COALESCE(transactions.merchant_name, transactions.description_raw, 'Sconosciuto')",
        'join': '',
    },
}
_REPORT_METRICS = {'sum', 'count', 'avg'}


@router.post('/api/reports/query')
def report_query(payload: Dict[str, Any], request: Request):
    """Query generica per il report builder: dimensioni/filtri/metrica arrivano
    dal frontend, ma solo come CHIAVI whitelisted in _REPORT_DIMENSIONS/
    _REPORT_METRICS - i valori concreti (date, id, destination) restano sempre
    parametri bind, mai concatenati nella query. Max 2 dimensioni: oltre non
    aggiunge leggibilita' a una tabella/grafico pensato per essere letto a
    colpo d'occhio."""
    return _run_report_query(payload, request)


def _run_report_query(payload: Dict[str, Any], request: Request) -> List[Dict[str, Any]]:
    """Nucleo di report_query, estratto perche' riusato anche da /api/ai/chat:
    l'AI propone dimensions/metric/filters (sempre validati contro le stesse
    whitelist), non genera mai SQL direttamente (vedi ai_reports.build_query_intent_prompt)."""
    dimensions = [d for d in (payload.get('dimensions') or []) if d in _REPORT_DIMENSIONS][:2]
    if not dimensions:
        raise HTTPException(status_code=400, detail='Serve almeno una dimensione valida')
    metric = payload.get('metric') if payload.get('metric') in _REPORT_METRICS else 'sum'
    absolute = bool(payload.get('absolute'))
    filters_in = payload.get('filters') or {}

    joins = []
    for dim in dimensions:
        join = _REPORT_DIMENSIONS[dim]['join']
        if join and join not in joins:
            joins.append(join)

    where = []
    args: List[Any] = []
    if date_from := filters_in.get('dateFrom'):
        where.append('transactions.date >= ?')
        args.append(date_from)
    if date_to := filters_in.get('dateTo'):
        where.append('transactions.date <= ?')
        args.append(date_to)
    if account_id := ensure_int(filters_in.get('accountId')):
        where.append('transactions.account_id = ?')
        args.append(account_id)
    if category_id := ensure_int(filters_in.get('categoryId')):
        where.append('transactions.category_id = ?')
        args.append(category_id)
    if person_id := ensure_int(filters_in.get('personId')):
        where.append('transactions.paid_by_person_id = ?')
        args.append(person_id)
    if destination := filters_in.get('destination'):
        where.append('transactions.destination = ?')
        args.append(destination)
    tx_type = filters_in.get('type')
    if tx_type == 'expense':
        where.append('transactions.amount < 0')
    elif tx_type == 'income':
        where.append('transactions.amount > 0')
    if filters_in.get('confirmedOnly'):
        where.append('transactions.is_confirmed = 1')

    vis_clause, vis_args = access.transaction_visibility(access.get_current_person(request), alias='transactions')
    where.append(vis_clause)
    args.extend(vis_args)

    select_exprs = [f"{_REPORT_DIMENSIONS[d]['select']} AS dim{i}" for i, d in enumerate(dimensions)]
    group_exprs = [_REPORT_DIMENSIONS[d]['select'] for d in dimensions]
    amount_expr = 'ABS(transactions.amount)' if absolute else 'transactions.amount'
    metric_expr = {
        'sum': f'COALESCE(SUM({amount_expr}),0)',
        'count': 'COUNT(*)',
        'avg': f'COALESCE(AVG({amount_expr}),0)',
    }[metric]

    sql = f"SELECT {', '.join(select_exprs)}, {metric_expr} AS value FROM transactions " + ' '.join(joins)
    if where:
        sql += ' WHERE ' + ' AND '.join(where)
    sql += f" GROUP BY {', '.join(group_exprs)} ORDER BY value DESC"

    rows = fetchall(sql, tuple(args))
    return [
        {**{f'dim{i}': row[f'dim{i}'] for i in range(len(dimensions))}, 'value': row['value']}
        for row in rows
    ]


@router.get('/api/reports/custom')
def list_saved_reports():
    rows = fetchall('SELECT * FROM saved_reports ORDER BY updated_at DESC')
    for row in rows:
        row['config'] = json.loads(row.pop('config_json'))
    return rows


@router.post('/api/reports/custom')
def create_saved_report(payload: Dict[str, Any]):
    name = (payload.get('name') or '').strip()
    if not name:
        raise HTTPException(status_code=400, detail='Nome obbligatorio')
    cursor = db.conn.execute(
        'INSERT INTO saved_reports (name, config_json) VALUES (?, ?)',
        (name, json.dumps(payload.get('config') or {})),
    )
    db.conn.commit()
    row = fetchone('SELECT * FROM saved_reports WHERE id = ?', (cursor.lastrowid,))
    row['config'] = json.loads(row.pop('config_json'))
    return JSONResponse(status_code=201, content=row)


@router.put('/api/reports/custom/{report_id}')
def update_saved_report(report_id: int, payload: Dict[str, Any]):
    existing = fetchone('SELECT * FROM saved_reports WHERE id = ?', (report_id,))
    if existing is None:
        raise HTTPException(status_code=404, detail='Not found')
    name = (payload.get('name') or existing['name']).strip()
    config = payload.get('config') if 'config' in payload else json.loads(existing['config_json'])
    execute(
        "UPDATE saved_reports SET name = ?, config_json = ?, updated_at = (datetime('now')) WHERE id = ?",
        (name, json.dumps(config), report_id),
    )
    row = fetchone('SELECT * FROM saved_reports WHERE id = ?', (report_id,))
    row['config'] = json.loads(row.pop('config_json'))
    return row


@router.delete('/api/reports/custom/{report_id}')
def delete_saved_report(report_id: int):
    execute('DELETE FROM saved_reports WHERE id = ?', (report_id,))
    return JSONResponse(status_code=204, content=None)

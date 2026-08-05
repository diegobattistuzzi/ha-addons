from typing import Any, List

from fastapi import APIRouter, HTTPException, Request

from .. import access, email_enrich
from ..db import execute, fetchall, fetchone
from ..util import ensure_int

router = APIRouter()


@router.get('/api/email-receipts')
def list_email_receipts(request: Request):
    """Elenca le ricevute email. Filtri opzionali: 'id' (una ricevuta precisa,
    usato per "vai alla mail" da una transazione anche se e' oltre il limite
    delle ultime 100) e 'transactionId' (la ricevuta abbinata a quella
    transazione, se esiste). La visibilita' segue quella della transazione
    abbinata (una ricevuta legata a una spesa personale altrui non deve
    comparire, stessa regola di access.transaction_visibility usata ovunque
    per le transazioni) - una ricevuta senza transazione abbinata (LEFT JOIN
    NULL) resta sempre visibile, non c'e' nulla di personale da nascondere."""
    params = request.query_params
    vis_clause, vis_args = access.transaction_visibility(access.get_current_person(request), alias='t')
    filters = [vis_clause]
    args: List[Any] = list(vis_args)
    if receipt_id := ensure_int(params.get('id')):
        filters.append('e.id = ?')
        args.append(receipt_id)
    if tx_id := ensure_int(params.get('transactionId')):
        filters.append('e.matched_transaction_id = ?')
        args.append(tx_id)
    if not receipt_id and not tx_id:
        # Nell'elenco generale interessano solo le mail da cui l'AI e' riuscita
        # a estrarre un importo (le altre sono rumore, es. notifiche di
        # spedizione senza ricevuta di pagamento) - una ricerca puntuale per id
        # o per transazione invece va sempre trovata, anche senza importo.
        filters.append('e.amount IS NOT NULL')
    sql = (
        'SELECT e.* FROM email_receipts e LEFT JOIN transactions t ON t.id = e.matched_transaction_id '
        'WHERE ' + ' AND '.join(filters) + ' ORDER BY e.received_at DESC LIMIT 100'
    )
    return fetchall(sql, tuple(args))


@router.post('/api/email-receipts/rematch')
def rematch_email_receipts():
    """Bottone "Riabbina mail": ritenta a mano l'abbinamento di tutte le
    ricevute email ancora in attesa, non solo quelle di un batch di import
    appena fatto (vedi email_enrich.rematch_all_pending_receipts)."""
    return {'matched': email_enrich.rematch_all_pending_receipts()}


@router.post('/api/email-receipts/{receipt_id}/unmatch')
def unmatch_email_receipt(receipt_id: int):
    """Slega una ricevuta da un abbinamento sbagliato (es. mail vecchia
    abbinata a una transazione recente per una data indovinata male dall'AI -
    vedi email_enrich.process_incoming_email). Riporta anche la transazione a
    merchant_enriched=0, altrimenti resterebbe esclusa per sempre dal pool di
    rematch_all_pending_receipts/_match_receipts_against e non potrebbe mai
    essere riabbinata alla ricevuta giusta."""
    receipt = fetchone('SELECT * FROM email_receipts WHERE id = ?', (receipt_id,))
    if receipt is None:
        raise HTTPException(status_code=404, detail='Not found')
    tx_id = receipt['matched_transaction_id']
    execute('UPDATE email_receipts SET matched_transaction_id = NULL WHERE id = ?', (receipt_id,))
    if tx_id:
        execute('UPDATE transactions SET merchant_enriched = 0 WHERE id = ?', (tx_id,))
    return {'unmatched': True}

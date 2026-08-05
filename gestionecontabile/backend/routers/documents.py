import uuid
from pathlib import Path
from typing import Any, List

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from .. import access, config, db
from ..db import execute, fetchall, fetchone
from ..util import ensure_int

router = APIRouter()


@router.get('/api/documents')
def list_documents(request: Request):
    params = request.query_params
    filters = []
    args: List[Any] = []
    if account_id := ensure_int(params.get('accountId')):
        filters.append('d.account_id = ?')
        args.append(account_id)
    if transaction_id := ensure_int(params.get('transactionId')):
        filters.append('d.transaction_id = ?')
        args.append(transaction_id)
    # period_start/period_end/tx_count vengono dalle transazioni vere legate al
    # documento (document_id), non da un periodo dichiarato nel nome del file o
    # nel PDF (che l'addon non riparsa dopo l'import): e' il dato oggettivo di
    # quali date sono state DAVVERO importate, utile per la vista di copertura
    # per conto (vedi getAccountCoverage nel frontend) che mostra da-a-a per
    # ogni documento e i buchi tra un estratto e il successivo.
    sql = (
        'SELECT d.id, d.filename, d.mime_type, d.size_bytes, d.account_id, d.import_batch_id, d.transaction_id, d.uploaded_at, '
        'MIN(t.date) AS period_start, MAX(t.date) AS period_end, COUNT(t.id) AS tx_count '
        'FROM documents d LEFT JOIN transactions t ON t.document_id = d.id'
    )
    if filters:
        sql += ' WHERE ' + ' AND '.join(filters)
    sql += ' GROUP BY d.id ORDER BY d.uploaded_at DESC'
    return fetchall(sql, tuple(args))


@router.post('/api/transactions/{transaction_id}/documents')
def upload_transaction_document(transaction_id: int, request: Request, file: UploadFile = File(...)):
    """Allega manualmente un file (es. foto di uno scontrino) a una transazione
    specifica: a differenza del documento sorgente di un import (1 documento -> N
    transazioni), qui la relazione e' 1 transazione -> N allegati."""
    tx = fetchone('SELECT * FROM transactions WHERE id = ?', (transaction_id,))
    if tx is None or not access.can_see_transaction(tx, access.get_current_person(request)):
        raise HTTPException(status_code=404, detail='Not found')
    data = file.file.read()
    safe_name = file.filename.replace('/', '_').replace('\\', '_')
    stored_path = config.DOCUMENTS_DIR / f'{uuid.uuid4().hex}_{safe_name}'
    stored_path.write_bytes(data)
    cursor = db.conn.execute(
        'INSERT INTO documents (filename, stored_path, mime_type, size_bytes, account_id, transaction_id) VALUES (?, ?, ?, ?, ?, ?)',
        (file.filename, str(stored_path), file.content_type, len(data), tx['account_id'], transaction_id),
    )
    db.conn.commit()
    return JSONResponse(status_code=201, content=fetchone('SELECT id, filename, mime_type, size_bytes, account_id, import_batch_id, transaction_id, uploaded_at FROM documents WHERE id = ?', (cursor.lastrowid,)))


@router.get('/api/documents/{document_id}/download')
def download_document(document_id: int):
    doc = fetchone('SELECT * FROM documents WHERE id = ?', (document_id,))
    if doc is None:
        raise HTTPException(status_code=404, detail='Not found')
    path = Path(doc['stored_path'])
    if not path.exists():
        raise HTTPException(status_code=404, detail='File non trovato su disco')
    return FileResponse(str(path), filename=doc['filename'], media_type=doc['mime_type'] or 'application/octet-stream')


@router.delete('/api/documents/{document_id}')
def delete_document(document_id: int):
    doc = fetchone('SELECT * FROM documents WHERE id = ?', (document_id,))
    if doc is None:
        raise HTTPException(status_code=404, detail='Not found')
    path = Path(doc['stored_path'])
    if path.exists():
        path.unlink()
    execute('DELETE FROM documents WHERE id = ?', (document_id,))
    return JSONResponse(status_code=204, content=None)

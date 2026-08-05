import io
from datetime import datetime

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from .. import backup
from ..db import execute, fetchone

router = APIRouter()


@router.get('/health')
def health():
    return {'status': 'ok', 'version': '1.0.0'}


@router.get('/api/backup/export')
def export_backup():
    wb = backup.build_backup_workbook()
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    filename = f"casaspese_backup_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return StreamingResponse(
        buf,
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'},
    )


@router.post('/api/backup/import')
def import_backup(file: UploadFile = File(...)):
    data = file.file.read()
    try:
        summary = backup.import_backup_workbook(data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f'File di backup non valido: {e}')
    return summary


@router.post('/api/admin/cleanup')
def cleanup():
    deleted_persons = execute("DELETE FROM persons WHERE name IS NULL OR trim(name)='' OR name='undefined'")
    deleted_accounts = execute("DELETE FROM accounts WHERE name IS NULL OR trim(name)='' OR name='undefined' OR name='..'")
    stats = fetchone(
        "SELECT (SELECT COUNT(*) FROM persons) AS persons, (SELECT COUNT(*) FROM accounts) AS accounts, "
        "(SELECT COUNT(*) FROM categories) AS categories, (SELECT COUNT(*) FROM transactions) AS transactions"
    )
    return {
        'deleted': {'persons': deleted_persons, 'accounts': deleted_accounts},
        'db': stats,
    }

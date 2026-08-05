import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import DB_PATH

Path(DB_PATH.parent).mkdir(parents=True, exist_ok=True)

conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
conn.row_factory = sqlite3.Row
conn.execute('PRAGMA journal_mode=WAL')
conn.execute('PRAGMA synchronous=NORMAL')


def row_to_dict(row: sqlite3.Row):
    if row is None:
        return None
    return {k: row[k] for k in row.keys()}


def fetchall(query: str, args: tuple = ()) -> List[Dict[str, Any]]:
    cursor = conn.execute(query, args)
    return [row_to_dict(row) for row in cursor.fetchall()]


def fetchone(query: str, args: tuple = ()) -> Optional[Dict[str, Any]]:
    cursor = conn.execute(query, args)
    return row_to_dict(cursor.fetchone())


def execute(query: str, args: tuple = ()) -> int:
    cursor = conn.execute(query, args)
    conn.commit()
    return cursor.rowcount

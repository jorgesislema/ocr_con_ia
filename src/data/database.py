"""ORM ligero / helpers para SQLite y logging de consumos.
"""
from __future__ import annotations
import sqlite3

DB_PATH = "data.db"

def get_connection(path: str | None = None) -> sqlite3.Connection:
    return sqlite3.connect(path or DB_PATH)

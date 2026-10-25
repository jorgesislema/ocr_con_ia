"""Trazabilidad de auditoría para extracciones OCR.

Registra en ``~/.ocr_audit.db`` (SQLite) cada extracción realizada:
hash SHA-256 del documento, modelo, campos extraídos (sin PII en claro),
confianza y timestamp.

API pública
-----------
    from src.core.audit import log_extraction, query_audit

    log_extraction(
        job_id   = "abc-123",
        doc_path = "/ruta/factura.pdf",
        result   = {"text": "...", "confidence": 0.92, "status": "Procesado"},
        model    = "glm-4v-flash",
        extra    = {"content_type": "table_heavy"},
    )

    records = query_audit(limit=50)     # list[dict]
    records = query_audit(job_id="abc-123")

El módulo es **sin dependencias externas**: usa sólo stdlib.
Si la DB no puede crearse (permiso denegado, etc.) el módulo actúa en
modo "silent no-op" para no interrumpir el pipeline OCR.
"""
from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_log = logging.getLogger("ocr.audit")

# ── Ruta de la base de datos ──────────────────────────────────────────────────

def _default_db_path() -> Path:
    return Path.home() / ".ocr_audit.db"


# ── Inicialización única ──────────────────────────────────────────────────────

_LOCK = threading.Lock()
_INIT_DONE: set[str] = set()


_DDL = """
CREATE TABLE IF NOT EXISTS audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id      TEXT    NOT NULL DEFAULT '',
    doc_path    TEXT    NOT NULL,
    doc_hash    TEXT    NOT NULL,      -- SHA-256 del archivo
    model       TEXT    NOT NULL DEFAULT '',
    content_type TEXT   NOT NULL DEFAULT 'unknown',
    confidence  REAL    NOT NULL DEFAULT 0.0,
    status      TEXT    NOT NULL DEFAULT '',
    field_count INTEGER NOT NULL DEFAULT 0,
    extra_json  TEXT    NOT NULL DEFAULT '{}',
    created_at  TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_job    ON audit_log(job_id);
CREATE INDEX IF NOT EXISTS idx_audit_hash   ON audit_log(doc_hash);
CREATE INDEX IF NOT EXISTS idx_audit_date   ON audit_log(created_at);
"""


def _get_conn(db_path: str | Path) -> sqlite3.Connection:
    db = Path(db_path)
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db), check_same_thread=False, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def _ensure_schema(db_path: str | Path) -> None:
    key = str(db_path)
    if key in _INIT_DONE:
        return
    with _LOCK:
        if key in _INIT_DONE:
            return
        try:
            conn = _get_conn(db_path)
            conn.executescript(_DDL)
            conn.commit()
            conn.close()
            _INIT_DONE.add(key)
            _log.debug("audit: esquema inicializado en %s", db_path)
        except Exception as exc:
            _log.warning("audit: no se pudo inicializar DB: %s", exc)


# ── Hash de documento ─────────────────────────────────────────────────────────

def _sha256_file(path: str | Path, chunk: int = 65536) -> str:
    """SHA-256 del archivo en disco; '' si no se puede leer."""
    try:
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            while True:
                buf = fh.read(chunk)
                if not buf:
                    break
                h.update(buf)
        return h.hexdigest()
    except Exception as exc:
        _log.debug("audit: hash fallido para '%s': %s", path, exc)
        return ""


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ── API pública ───────────────────────────────────────────────────────────────

def log_extraction(
    job_id:   str,
    doc_path: str | Path,
    result:   dict,
    model:    str = "",
    extra:    dict | None = None,
    db_path:  str | Path | None = None,
) -> bool:
    """Registra una extracción en la tabla ``audit_log``.

    Parámetros
    ----------
    job_id   : identificador del lote / tarea (puede ser '').
    doc_path : ruta del documento procesado.
    result   : dict de resultado (claves esperadas: confidence, status, text).
    model    : nombre del modelo utilizado.
    extra    : dict con metadatos adicionales (content_type, router info, etc.).
    db_path  : ruta explícita de la DB; si None usa ``~/.ocr_audit.db``.

    Devuelve
    --------
    True si se insertó correctamente, False en caso de error.
    """
    db = db_path or _default_db_path()
    try:
        _ensure_schema(db)
    except Exception:
        return False

    try:
        doc_hash     = _sha256_file(doc_path)
        confidence   = float(result.get("confidence") or 0.0)
        status       = str(result.get("status") or "")
        text         = str(result.get("text") or "")
        content_type = str((extra or {}).get("content_type") or "unknown")

        # Contar campos extraídos (claves de segundo nivel si el texto es JSON)
        field_count = 0
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                field_count = len(parsed)
            elif isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
                field_count = len(parsed[0])
        except Exception:
            field_count = len(text.split("\n")) if text else 0

        extra_clean = {k: v for k, v in (extra or {}).items()
                       if isinstance(v, (str, int, float, bool, type(None)))}

        now = datetime.now(timezone.utc).isoformat()

        conn = _get_conn(db)
        with _LOCK:
            conn.execute(
                """INSERT INTO audit_log
                   (job_id, doc_path, doc_hash, model, content_type,
                    confidence, status, field_count, extra_json, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    str(job_id or ""),
                    str(doc_path),
                    doc_hash,
                    str(model or ""),
                    content_type,
                    confidence,
                    status,
                    field_count,
                    json.dumps(extra_clean, ensure_ascii=False),
                    now,
                ),
            )
            conn.commit()
        conn.close()
        _log.debug(
            "audit: %s | job=%s | conf=%.2f | hash=%s…",
            status, job_id, confidence, doc_hash[:12],
        )
        return True

    except Exception as exc:
        _log.warning("audit: log_extraction falló: %s", exc)
        return False


def query_audit(
    job_id:  str | None = None,
    status:  str | None = None,
    limit:   int = 200,
    db_path: str | Path | None = None,
) -> list[dict]:
    """Consulta entradas del log de auditoría.

    Parámetros
    ----------
    job_id  : filtrar por job_id exacto.
    status  : filtrar por status ('Procesado', 'Error', etc.).
    limit   : máximo de filas devueltas.
    db_path : ruta de la DB; None → ``~/.ocr_audit.db``.

    Devuelve
    --------
    list[dict]: cada dict tiene todas las columnas de ``audit_log``.
    """
    db = db_path or _default_db_path()
    try:
        _ensure_schema(db)
    except Exception:
        return []

    try:
        wheres = []
        params: list = []
        if job_id is not None:
            wheres.append("job_id = ?")
            params.append(job_id)
        if status is not None:
            wheres.append("status = ?")
            params.append(status)
        where_clause = ("WHERE " + " AND ".join(wheres)) if wheres else ""
        sql = (
            f"SELECT * FROM audit_log {where_clause} "
            f"ORDER BY id DESC LIMIT ?"
        )
        params.append(limit)
        conn = _get_conn(db)
        rows = conn.execute(sql, params).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as exc:
        _log.warning("audit: query_audit falló: %s", exc)
        return []


def get_audit_summary(db_path: str | Path | None = None) -> dict:
    """Devuelve un resumen estadístico del log de auditoría."""
    db = db_path or _default_db_path()
    try:
        _ensure_schema(db)
        conn = _get_conn(db)
        total  = conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
        errors = conn.execute("SELECT COUNT(*) FROM audit_log WHERE status='Error'").fetchone()[0]
        avg    = conn.execute("SELECT AVG(confidence) FROM audit_log").fetchone()[0] or 0.0
        conn.close()
        return {"total": total, "errors": errors, "avg_confidence": round(avg, 3)}
    except Exception:
        return {"total": 0, "errors": 0, "avg_confidence": 0.0}

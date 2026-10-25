"""Cola de trabajos persistente en SQLite para el pipeline OCR.

Reemplaza el mecanismo de checkpoint json (.ocr_state.json) con una base de datos
SQLite en modo WAL para mayor robustez ante cierres súbitos.

Uso típico en OcrWorker::

    jq = JobQueue(Path(output_dir) / ".ocr_jobs.db")
    jq.enqueue_batch(files, profile, backend)
    while (job := jq.next_pending()) is not None:
        ...procesar...
        jq.mark_done(job["id"], result_dict)
"""
from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_log = logging.getLogger("ocr.job_queue")

# Rutas por defecto (resolución tardía para no fallar en import)
_DEFAULT_DB = Path.home() / ".ocr_jobs.db"


class JobQueue:
    """Cola FIFO persistente respaldada por SQLite (modo WAL).

    Todos los métodos son seguros para llamar desde un único hilo de escritura
    (OcrWorker QThread). Lecturas concurrentes son seguras gracias a WAL.

    Parámetros
    ----------
    db_path :
        Ruta al archivo SQLite. Por defecto ``~/.ocr_jobs.db``.
        También se acepta ``Path(output_dir) / ".ocr_jobs.db"`` para
        mantener la DB junto al lote actual.
    """

    _CREATE_TABLE = """
    CREATE TABLE IF NOT EXISTS jobs (
        id          TEXT PRIMARY KEY,
        batch_id    TEXT NOT NULL,
        filename    TEXT NOT NULL,
        filepath    TEXT NOT NULL,
        status      TEXT NOT NULL DEFAULT 'pending',
        retries     INTEGER NOT NULL DEFAULT 0,
        max_retries INTEGER NOT NULL DEFAULT 3,
        payload     TEXT,
        result      TEXT,
        error       TEXT,
        profile     TEXT,
        backend     TEXT,
        created_at  TEXT NOT NULL,
        updated_at  TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_jobs_batch_status ON jobs(batch_id, status);
    
    CREATE TABLE IF NOT EXISTS batches (
        id TEXT PRIMARY KEY,
        batch_number INTEGER NOT NULL,
        total_batches INTEGER NOT NULL,
        batch_id TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        batch_size INTEGER NOT NULL DEFAULT 0,
        total_in_batch INTEGER NOT NULL DEFAULT 0,
        started_at TEXT,
        completed_at TEXT,
        avg_confidence REAL,
        error_count INTEGER DEFAULT 0
    );
    CREATE INDEX IF NOT EXISTS idx_batches_status ON batches(status);
    """

    def __init__(self, db_path: Path | str | None = None) -> None:
        self._db_path = Path(db_path) if db_path else _DEFAULT_DB
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = self._open_conn()
        self._init_schema()
        _log.info("JobQueue inicializada: %s", self._db_path)

    # ── Conexión ──────────────────────────────────────────────────────────────

    def _open_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        conn.commit()
        return conn

    def _init_schema(self) -> None:
        try:
            self._conn.executescript(self._CREATE_TABLE)
            self._conn.commit()
        except sqlite3.Error as exc:
            _log.error("Error inicializando esquema JobQueue: %s", exc)
            raise

    # ── API pública ───────────────────────────────────────────────────────────

    def enqueue_batch(
        self,
        files: list[str],
        profile: str = "",
        backend: str = "glm",
        batch_id: str | None = None,
        max_retries: int = 3,
    ) -> str:
        """Encola un lote de archivos como trabajos *pending*.

        Si ya existe un lote incompleto con los mismos archivos **en el mismo
        directorio** se reutiliza ese ``batch_id`` (reanudación).

        Retorna el ``batch_id`` del lote (nuevo o reanudado).
        """
        # Intentar reanudación: buscar lote incompleto con la misma lista de rutas
        existing = self._find_resumable_batch(files, profile, backend)
        if existing:
            _log.info(
                "Reanudando lote existente batch_id=%s (%d pendientes)",
                existing, self._count_pending(existing),
            )
            return existing

        bid = batch_id or str(uuid.uuid4())
        now = _now_iso()
        rows = [
            (
                str(uuid.uuid4()),  # id
                bid,                # batch_id
                Path(fp).name,      # filename
                fp,                 # filepath
                "pending",          # status
                0,                  # retries
                max_retries,        # max_retries
                None,               # payload
                None,               # result
                None,               # error
                profile,            # profile
                backend,            # backend
                now,                # created_at
                now,                # updated_at
            )
            for fp in files
        ]
        self._conn.executemany(
            """INSERT INTO jobs (id, batch_id, filename, filepath, status, retries,
               max_retries, payload, result, error, profile, backend, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            rows,
        )
        self._conn.commit()
        _log.info("Lote encolado batch_id=%s, %d archivos", bid, len(rows))
        return bid

    # ── Batch level helpers ─────────────────────────────────────────────────
    def create_batches(self, files: list[str], batch_size: int = 100, profile: str = "", backend: str = "glm", max_retries: int = 3) -> list[dict]:
        """Divide la lista `files` en batches de `batch_size` y registra
        metadatos en la tabla `batches`. Retorna lista de dicts con info.
        """
        if batch_size <= 0:
            batch_size = 100
        total = len(files)
        chunks = [files[i:i+batch_size] for i in range(0, total, batch_size)]
        total_batches = len(chunks)
        out = []
        now = _now_iso()
        for idx, chunk in enumerate(chunks, start=1):
            bid = str(uuid.uuid4())
            info = {
                "id": bid,
                "batch_number": idx,
                "total_batches": total_batches,
                "batch_id": bid,
                "status": "pending",
                "batch_size": batch_size,
                "total_in_batch": len(chunk),
                "started_at": None,
                "completed_at": None,
                "avg_confidence": None,
                "error_count": 0,
            }
            self._conn.execute(
                "INSERT INTO batches (id, batch_number, total_batches, batch_id, status, batch_size, total_in_batch, started_at, completed_at, avg_confidence, error_count) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    info["id"], info["batch_number"], info["total_batches"], info["batch_id"],
                    info["status"], info["batch_size"], info["total_in_batch"], None, None, None, 0
                ),
            )
            # Insert jobs for this chunk if they don't already exist
            now = _now_iso()
            rows = []
            for fp in chunk:
                # avoid duplicate job for same filepath
                cur = self._conn.execute("SELECT COUNT(*) as cnt FROM jobs WHERE filepath=?", (fp,))
                if cur.fetchone()[0] > 0:
                    continue
                rows.append(
                    (
                        str(uuid.uuid4()),  # id
                        info["batch_id"],   # batch_id
                        Path(fp).name,
                        fp,
                        "pending",
                        0,
                        max_retries,
                        None,
                        None,
                        None,
                        profile,
                        backend,
                        now,
                        now,
                    )
                )
            if rows:
                self._conn.executemany(
                    "INSERT INTO jobs (id, batch_id, filename, filepath, status, retries, max_retries, payload, result, error, profile, backend, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    rows,
                )
            out.append(info)
        self._conn.commit()
        return out

    def get_pending_batches(self) -> list[dict]:
        cur = self._conn.execute("SELECT * FROM batches WHERE status IN ('pending','processing') ORDER BY batch_number ASC")
        rows = []
        for r in cur.fetchall():
            rows.append(dict(r))
        return rows

    def mark_batch_completed(self, batch_id: str, stats: dict) -> None:
        now = _now_iso()
        avg = stats.get('avg_confidence') if isinstance(stats, dict) else None
        err = stats.get('errors', 0) if isinstance(stats, dict) else 0
        try:
            self._conn.execute(
                "UPDATE batches SET status='completed', completed_at=?, avg_confidence=?, error_count=? WHERE batch_id=?",
                (now, avg, err, batch_id),
            )
            self._conn.commit()
        except Exception as exc:
            _log.warning("mark_batch_completed failed: %s", exc)

    def get_progress_summary(self) -> dict:
        cur = self._conn.execute("SELECT COUNT(*) as total_jobs, SUM(CASE WHEN status='done' THEN 1 ELSE 0 END) as done_jobs FROM jobs")
        row = cur.fetchone()
        total = row[0] if row else 0
        done = row[1] if row else 0
        cur2 = self._conn.execute("SELECT COUNT(*) as total_batches, SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) as completed_batches FROM batches")
        row2 = cur2.fetchone()
        total_b = row2[0] if row2 else 0
        done_b = row2[1] if row2 else 0
        pct = (done / total * 100.0) if total else 0.0
        return {
            "total_files": total,
            "processed": done,
            "total_batches": total_b,
            "completed_batches": done_b,
            "percent": pct,
        }

    def enqueue(self, filepath: str, profile: str = "", backend: str = "glm",
                batch_id: str | None = None, max_retries: int = 3) -> str:
        """Encola un único archivo. Retorna el job id."""
        bid = batch_id or str(uuid.uuid4())
        jid = str(uuid.uuid4())
        now = _now_iso()
        self._conn.execute(
            """INSERT INTO jobs (id, batch_id, filename, filepath, status, retries,
               max_retries, payload, result, error, profile, backend, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (jid, bid, Path(filepath).name, filepath, "pending", 0,
             max_retries, None, None, None, profile, backend, now, now),
        )
        self._conn.commit()
        return jid

    def next_pending(self, batch_id: str | None = None) -> dict[str, Any] | None:
        """Devuelve el siguiente trabajo *pending* del lote (o de toda la DB).

        Marca el trabajo como ``running`` de forma atómica.
        Retorna ``None`` si no hay trabajos pendientes.
        """
        where = "batch_id = ? AND " if batch_id else ""
        params = [batch_id] if batch_id else []
        params.append("pending")

        cur = self._conn.execute(
            f"SELECT * FROM jobs WHERE {where}status = ? ORDER BY created_at ASC LIMIT 1",
            params,
        )
        row = cur.fetchone()
        if row is None:
            return None

        now = _now_iso()
        self._conn.execute(
            "UPDATE jobs SET status='running', updated_at=? WHERE id=?",
            (now, row["id"]),
        )
        self._conn.commit()
        return dict(row)

    def mark_done(self, job_id: str, result: dict[str, Any] | None = None) -> None:
        """Marca un trabajo como *done* y persiste el resultado."""
        try:
            result_json = json.dumps(result, ensure_ascii=False) if result else None
        except Exception:
            result_json = str(result)
        self._conn.execute(
            "UPDATE jobs SET status='done', result=?, updated_at=? WHERE id=?",
            (result_json, _now_iso(), job_id),
        )
        self._conn.commit()
        _log.debug("Job %s marcado como done", job_id)

    def mark_failed(self, job_id: str, error: str) -> None:
        """Marca un trabajo como *failed* o lo re-encola si quedan reintentos."""
        cur = self._conn.execute(
            "SELECT retries, max_retries FROM jobs WHERE id=?", (job_id,)
        )
        row = cur.fetchone()
        if row is None:
            _log.warning("mark_failed: job %s no encontrado", job_id)
            return

        retries, max_retries = row["retries"], row["max_retries"]
        new_retries = retries + 1
        if new_retries < max_retries:
            self._conn.execute(
                "UPDATE jobs SET status='pending', retries=?, error=?, updated_at=? WHERE id=?",
                (new_retries, error, _now_iso(), job_id),
            )
            _log.info("Job %s re-encolado (intento %d/%d): %s", job_id, new_retries, max_retries, error)
        else:
            self._conn.execute(
                "UPDATE jobs SET status='failed', retries=?, error=?, updated_at=? WHERE id=?",
                (new_retries, error, _now_iso(), job_id),
            )
            _log.warning("Job %s marcado como failed tras %d intentos: %s", job_id, new_retries, error)
        self._conn.commit()

    def get_checkpoint(self, batch_id: str) -> dict[str, Any]:
        """Resumen del estado del lote: conteos por status y lista de done jobs."""
        cur = self._conn.execute(
            """SELECT status, COUNT(*) as cnt FROM jobs WHERE batch_id=?
               GROUP BY status""",
            (batch_id,),
        )
        counts = {row["status"]: row["cnt"] for row in cur.fetchall()}

        cur2 = self._conn.execute(
            "SELECT id, filepath, result FROM jobs WHERE batch_id=? AND status='done'",
            (batch_id,),
        )
        done_jobs = []
        for row in cur2.fetchall():
            result = None
            try:
                result = json.loads(row["result"]) if row["result"] else None
            except Exception:
                pass
            done_jobs.append({"id": row["id"], "filepath": row["filepath"], "result": result})

        return {
            "batch_id":   batch_id,
            "counts":     counts,
            "done_jobs":  done_jobs,
            "pending":    counts.get("pending", 0),
            "running":    counts.get("running", 0),
            "done":       counts.get("done", 0),
            "failed":     counts.get("failed", 0),
        }

    def reset_stalled(self, batch_id: str | None = None) -> int:
        """Re-encola trabajos en estado *running* (dejados por un cierre inesperado)."""
        where = "batch_id = ? AND " if batch_id else ""
        params = ([batch_id] if batch_id else []) + [_now_iso(), "pending"]
        cur = self._conn.execute(
            f"UPDATE jobs SET status=?, updated_at=? WHERE {where}status='running'",
            list(reversed(params[:2])) + params[2:],
        )
        # Reordenar parámetros para la query real
        if batch_id:
            cur = self._conn.execute(
                "UPDATE jobs SET status='pending', updated_at=? WHERE batch_id=? AND status='running'",
                (_now_iso(), batch_id),
            )
        else:
            cur = self._conn.execute(
                "UPDATE jobs SET status='pending', updated_at=? WHERE status='running'",
                (_now_iso(),),
            )
        n = cur.rowcount
        self._conn.commit()
        if n:
            _log.info("reset_stalled: %d trabajos re-encolados", n)
        return n

    def all_done(self, batch_id: str) -> bool:
        """True si todos los trabajos del lote están en estado *done* o *failed*."""
        cur = self._conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE batch_id=? AND status IN ('pending','running')",
            (batch_id,),
        )
        return cur.fetchone()[0] == 0

    def close(self) -> None:
        """Cierra la conexión SQLite limpiamente."""
        try:
            self._conn.close()
        except Exception:
            pass

    # ── Helpers privados ──────────────────────────────────────────────────────

    def _find_resumable_batch(self, files: list[str], profile: str, backend: str) -> str | None:
        """Busca un batch incompleto con exactamente los mismos archivos."""
        # Obtener todos los batch_id con trabajos pendientes o en progreso
        cur = self._conn.execute(
            """SELECT DISTINCT batch_id FROM jobs
               WHERE status IN ('pending', 'running', 'failed')
               AND profile=? AND backend=?""",
            (profile, backend),
        )
        candidates = [r["batch_id"] for r in cur.fetchall()]
        if not candidates:
            return None

        filepaths_set = set(files)
        for bid in candidates:
            cur2 = self._conn.execute(
                "SELECT filepath FROM jobs WHERE batch_id=?", (bid,)
            )
            db_files = {r["filepath"] for r in cur2.fetchall()}
            if db_files == filepaths_set:
                return bid
        return None

    def _count_pending(self, batch_id: str) -> int:
        cur = self._conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE batch_id=? AND status='pending'",
            (batch_id,),
        )
        return cur.fetchone()[0]


# ── Utilidades ────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()

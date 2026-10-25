"""API REST Local — FASE 6.

Servidor FastAPI que escucha en ``http://localhost:8080`` y permite encolar
trabajos OCR desde sistemas externos (ERP, escáneres, robótica de proceso).

Endpoints
---------
GET  /health
    Devuelve estado del servicio y del CircuitBreaker.

POST /ocr/process
    Encola uno o varios archivos para procesamiento OCR.
    Body JSON::

        {
          "files": ["/ruta/factura.pdf", "/ruta/recibo.png"],
          "api_key": "sk-...",        // opcional si hay clave default
          "profile": "Facturas/Contable",
          "backend": "glm",
          "output_dir": "/tmp/salida"
        }

GET  /ocr/status/{job_id}
    Devuelve el estado de un trabajo encolado.

GET  /ocr/results
    Lista los últimos N resultados procesados.

DELETE /ocr/queue
    Vacía la cola de trabajos pendientes.

Arranque
--------
    # Desde la CLI del proyecto:
    python -m uvicorn src.api.server:app --host 0.0.0.0 --port 8080 --reload

    # Desde código Python (hilo de fondo):
    from src.api.server import start_server_thread
    start_server_thread(port=8080)

Seguridad
---------
- La clave de API externa se pasa en el header ``X-API-Key``.
- En modo desarrollo se puede deshabilitar con ``API_KEY_DISABLE=1`` env var.
- No exponer en Internet sin TLS y autenticación adicional.
"""
from __future__ import annotations

import logging
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_log = logging.getLogger("ocr.api")

# ── Importación condicional de FastAPI ────────────────────────────────────────
try:
    from fastapi import FastAPI, HTTPException, Header, Depends  # type: ignore
    from fastapi.middleware.cors import CORSMiddleware           # type: ignore
    from pydantic import BaseModel, Field                        # type: ignore
    _FASTAPI_AVAILABLE = True
except ImportError:
    _FASTAPI_AVAILABLE = False
    FastAPI = None  # type: ignore
    _log.warning(
        "FastAPI no está instalada.  Instala con: pip install fastapi uvicorn[standard]"
    )

# ── Cola en memoria thread-safe ───────────────────────────────────────────────
import queue as _queue

_job_store: dict[str, dict] = {}          # job_id → {status, result, ...}
_pending_queue: _queue.Queue = _queue.Queue()   # jobs pendientes para el procesador


# ── Modelos Pydantic ──────────────────────────────────────────────────────────

if _FASTAPI_AVAILABLE:
    class ProcessRequest(BaseModel):
        files: list[str] = Field(..., description="Lista de rutas absolutas a procesar")
        api_key: str | None = Field(None, description="Clave de API del motor OCR")
        profile: str = Field("Facturas/Contable", description="Perfil de extracción")
        backend: str = Field("glm", description="Backend OCR")
        output_dir: str | None = Field(None, description="Directorio de salida")
        priority: int = Field(0, ge=0, le=10, description="Prioridad (0=normal, 10=urgente)")

    class JobStatus(BaseModel):
        job_id: str
        status: str               # "pending" | "processing" | "done" | "error"
        files: list[str]
        created_at: str
        finished_at: str | None
        result_summary: dict | None

# ── Seguridad: X-API-Key ──────────────────────────────────────────────────────

_SERVER_API_KEY: str | None = os.environ.get("OCR_SERVER_API_KEY")   # None = sin autenticación en dev

def _verify_api_key(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> None:
    """Dependencia FastAPI: valida el header X-API-Key si está configurado."""
    if os.environ.get("API_KEY_DISABLE", "").lower() in ("1", "true", "yes"):
        return
    if _SERVER_API_KEY and x_api_key != _SERVER_API_KEY:
        raise HTTPException(status_code=401, detail="X-API-Key inválida o ausente.")


# ── Aplicación FastAPI ────────────────────────────────────────────────────────

def _build_app() -> Any:
    if not _FASTAPI_AVAILABLE:
        raise RuntimeError("FastAPI no está instalada.  pip install fastapi uvicorn[standard]")

    app = FastAPI(
        title="OCR Enterprise API",
        description="API REST para encolar trabajos OCR y consultar resultados.",
        version="6.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost", "http://127.0.0.1"],
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["*"],
    )

    # ── GET /health ───────────────────────────────────────────────────────────

    @app.get("/health", tags=["sistema"])
    def health():
        breaker_status = "unknown"
        try:
            from src.core.circuit_breaker import get_breaker
            cb = get_breaker("API")
            breaker_status = cb.status_text()
        except Exception:
            pass

        return {
            "status":          "ok",
            "timestamp":       datetime.now(timezone.utc).isoformat(),
            "pending_jobs":    _pending_queue.qsize(),
            "total_jobs":      len(_job_store),
            "circuit_breaker": breaker_status,
        }

    # ── POST /ocr/process ─────────────────────────────────────────────────────

    @app.post("/ocr/process", tags=["ocr"], status_code=202,
              dependencies=[Depends(_verify_api_key)])
    def process(req: ProcessRequest):
        # Validar archivos
        missing = [f for f in req.files if not Path(f).exists()]
        if missing:
            raise HTTPException(
                status_code=422,
                detail=f"Archivos no encontrados: {missing[:5]}",
            )

        # Verificar circuit breaker
        try:
            from src.core.circuit_breaker import get_breaker, CircuitOpenError
            cb = get_breaker(req.backend or "API")
            if cb.is_open():
                raise HTTPException(
                    status_code=503,
                    detail=cb.status_text(),
                )
        except HTTPException:
            raise
        except Exception:
            pass

        job_id = str(uuid.uuid4())
        job: dict = {
            "job_id":       job_id,
            "status":       "pending",
            "files":        list(req.files),
            "api_key":      req.api_key,
            "profile":      req.profile,
            "backend":      req.backend,
            "output_dir":   req.output_dir or str(Path.home() / "Desktop"),
            "priority":     req.priority,
            "created_at":   datetime.now(timezone.utc).isoformat(),
            "finished_at":  None,
            "result_summary": None,
        }
        _job_store[job_id] = job
        _pending_queue.put(job)
        _log.info("Job encolado vía API: %s (%d archivos)", job_id, len(req.files))
        return {"job_id": job_id, "status": "pending", "files_count": len(req.files)}

    # ── GET /ocr/status/{job_id} ──────────────────────────────────────────────

    @app.get("/ocr/status/{job_id}", tags=["ocr"],
             dependencies=[Depends(_verify_api_key)])
    def job_status(job_id: str):
        job = _job_store.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job no encontrado.")
        return JobStatus(**{k: job[k] for k in JobStatus.model_fields})

    # ── GET /ocr/results ──────────────────────────────────────────────────────

    @app.get("/ocr/results", tags=["ocr"],
             dependencies=[Depends(_verify_api_key)])
    def list_results(limit: int = 50):
        done = [j for j in _job_store.values() if j["status"] == "done"]
        done.sort(key=lambda j: j.get("finished_at") or "", reverse=True)
        return done[:limit]

    # ── DELETE /ocr/queue ─────────────────────────────────────────────────────

    @app.delete("/ocr/queue", tags=["ocr"],
                dependencies=[Depends(_verify_api_key)])
    def clear_queue():
        cleared = 0
        while not _pending_queue.empty():
            try:
                job = _pending_queue.get_nowait()
                job["status"] = "cancelled"
                cleared += 1
            except Exception:
                break
        return {"cleared": cleared}

    return app


# Instancia de la app (importable por uvicorn)
try:
    app = _build_app()
except Exception as _build_exc:
    _log.warning("No se pudo construir la app FastAPI: %s", _build_exc)
    app = None  # type: ignore


# ── Arranque en hilo de fondo (desde main_window) ────────────────────────────

def start_server_thread(host: str = "127.0.0.1", port: int = 8080) -> threading.Thread | None:
    """Arranca uvicorn en un daemon thread.  Devuelve el hilo o None si falla."""
    if not _FASTAPI_AVAILABLE:
        _log.warning("start_server_thread: FastAPI no disponible")
        return None
    if app is None:
        return None

    def _run() -> None:
        try:
            import uvicorn  # type: ignore
            uvicorn.run(app, host=host, port=port, log_level="warning", access_log=False)
        except ImportError:
            _log.error("uvicorn no está instalado.  pip install uvicorn[standard]")
        except Exception as exc:
            _log.error("Error en servidor API: %s", exc)

    t = threading.Thread(target=_run, name="OCR-API-Server", daemon=True)
    t.start()
    _log.info("Servidor API iniciado en http://%s:%d", host, port)
    return t


def get_pending_job() -> dict | None:
    """Extrae el siguiente job pendiente de la cola (uso en el procesador interno)."""
    try:
        return _pending_queue.get_nowait()
    except _queue.Empty:
        return None


def mark_job_done(job_id: str, result_summary: dict) -> None:
    """Actualiza el estado de un job a 'done' con su resumen."""
    if job_id in _job_store:
        _job_store[job_id]["status"] = "done"
        _job_store[job_id]["finished_at"] = datetime.now(timezone.utc).isoformat()
        _job_store[job_id]["result_summary"] = result_summary


def mark_job_error(job_id: str, error_msg: str) -> None:
    """Actualiza el estado de un job a 'error'."""
    if job_id in _job_store:
        _job_store[job_id]["status"] = "error"
        _job_store[job_id]["finished_at"] = datetime.now(timezone.utc).isoformat()
        _job_store[job_id]["result_summary"] = {"error": error_msg}

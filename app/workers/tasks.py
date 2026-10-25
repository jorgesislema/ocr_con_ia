"""Tarea asíncrona de extracción — regla #5 + TAREA 4 (resiliencia).

Pipeline ejecutado por el worker Celery:
    1. Marca la tarea en PROCESSING.
    2. Elige proveedor vía Factory (config del usuario / dificultad).
    3. Extrae por página (PDF multipágina) o de una vez (imagen/1 página).
    4. Si hay varias páginas → consolidador (regla #4).
    5. Valida matemáticamente (regla #4) → NEEDS_REVIEW si falla.
    6. Guarda el JSON canónico en la BD.

TAREA 4 — el worker JAMÁS se cae:
    * Las excepciones del LLM (timeout, JSON malformado, respuesta fuera de
      esquema, credenciales ausentes…) se atrapan SIEMPRE.
    * Se marca la tarea como ``failed`` con un mensaje AMIGABLE para el
      usuario final (persistido en su propia transacción, inmune a reintentos).
    * Las excepciones TRANSITORIAS (timeout/conexión/respuesta del proveedor)
      reintentan con broker real; las permanentes terminan limpio.

Estados resultantes: COMPLETED | NEEDS_REVIEW | FAILED.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from celery.exceptions import SoftTimeLimitExceeded
from pydantic import ValidationError

from app.core.config import get_settings
from app.core.db.models import ExtractionTask, TaskStatus
from app.core.schemas.invoice import InvoiceSchema, PageMeta
from app.workers.celery_app import celery

_log = logging.getLogger("ocr.workers")

# MIME types aceptados por los proveedores multimodales.
SUPPORTED_MIME = {"application/pdf", "image/png", "image/jpeg", "image/tiff", "image/webp"}

# ── TAREA 4: excepción → mensaje amigable ────────────────────────────────────
_FRIENDLY_ERRORS: tuple[tuple[type[Exception], str], ...] = (
    (SoftTimeLimitExceeded,
     "El documento tardó demasiado en procesarse (tiempo límite del worker). "
     "Intenta de nuevo o divide el PDF en partes más pequeñas."),
    (TimeoutError,
     "Se agotó el tiempo de espera del proveedor de IA. Reintenta en unos momentos."),
    # Import perezoso dentro de _friendly_message para excepciones aún no importadas
    (ConnectionError,
     "No se pudo conectar con el proveedor de IA (red o credenciales). Reintenta en unos momentos."),
    (ValidationError,
     "La IA devolvió datos que no cumplen el esquema canónico. "
     "Reintenta; si persiste, prueba con otro proveedor de IA."),
)


def _friendly_message(exc: Exception) -> str:
    """Traduce una excepción técnica a un mensaje útil para el usuario final."""
    from app.ai.base import AIProviderError
    from app.core.config import SecretNotFoundError

    mapping: tuple[tuple[type[Exception], str], ...] = _FRIENDLY_ERRORS + (
        (AIProviderError,
         "El proveedor de IA devolvió una respuesta inválida o falló. "
         "Se reintentará automáticamente si es transitorio."),
        (SecretNotFoundError,
         "Falta la API key del proveedor de IA. Configúrala en el .env (desarrollo) "
         "o en el gestor de secretos (producción)."),
    )
    for exc_type, message in mapping:
        if isinstance(exc, exc_type):
            return f"{message} [{type(exc).__name__}: {exc}]"
    return f"Error inesperado procesando el documento. [{type(exc).__name__}: {exc}]"


# Transitorias: con broker real vale la pena reintentar (Celery lo gestiona).
_RETRYABLE = (SoftTimeLimitExceeded, TimeoutError, ConnectionError)


def _mark_failed(task_id: str, friendly_message: str) -> None:
    """Persiste el estado FAILED en SU PROPIA transacción.

    Así un ``self.retry()`` posterior (o la caída del worker) nunca deshace
    el registro del fallo: el usuario siempre ve el mensaje amigable.
    """
    from app.core.db.base import session_scope
    from app.core.db.models import ExtractionTask

    with session_scope() as db:
        task = db.get(ExtractionTask, task_id)
        if task is not None:
            task.status = TaskStatus.FAILED
            task.error_message = friendly_message
            task.finished_at = datetime.now(timezone.utc)


def _page_count(file_path: str, mime: str) -> int:
    """Número de páginas (1 para imágenes)."""
    if mime != "application/pdf":
        return 1
    import fitz  # PyMuPDF

    with fitz.open(file_path) as pdf:
        return pdf.page_count


def run_extraction(task_id: str,
                   pais: str | None = None,
                   columnas: list[str] | None = None) -> dict:
    """Pipeline completo de extracción — función PLANA, sin dependencia de Celery.

    Es el núcleo que ambos backends de cola ejecutan (TAREA 3.2):
        * BackgroundTasks de FastAPI cuando no hay Redis (despliegue costo cero).
        * La tarea Celery ``process_document`` cuando hay Redis/volumen alto.

    Args:
        task_id: id de la fila ExtractionTask.
        pais: código ISO para la normativa del prompt (TAREA 1); vacío → "Genérica".
        columnas: campos prioritarios pedidos por el cliente (TAREA 1).

    Returns:
        dict con estado final; incluye ``retryable`` si el fallo fue transitorio.
    """
    from app.core.db.base import session_scope
    from app.core.db.models import Document

    settings = get_settings()
    with session_scope() as db:
        task = db.get(ExtractionTask, task_id)
        if task is None:
            _log.error("Tarea %s no encontrada", task_id)
            return {"status": "failed", "error": "Tarea no encontrada."}
        doc = db.get(Document, task.document_id)

        task.status = TaskStatus.PROCESSING
        task.attempts += 1
        task.started_at = task.started_at or datetime.now(timezone.utc)
        task.error_message = None  # limpia fallos de intentos anteriores

        try:
            # ── 1) Elegir proveedor (Factory, regla #1) ─────────────────────
            from app.ai.base import ExtractionInput
            from app.ai.factory import get_provider

            provider_pref = None
            if doc.user and doc.user.preferred_provider != "auto":
                provider_pref = doc.user.preferred_provider

            file_input = ExtractionInput(
                file_path=Path(doc.storage_path),
                mime_type=doc.mime_type,
                hint="invoice",
                # Normativa por país + columnas prioritarias (TAREA 1)
                pais=(pais or "").strip(),
                columnas_solicitadas=list(columnas or []),
                # Dificultad heurística: PDFs grandes y escaneados son más complejos
                difficulty=7 if doc.page_count and doc.page_count > 1 else 5,
                split_pages=(doc.mime_type == "application/pdf" and (doc.page_count or 1) > 1),
            )
            provider = get_provider(preferred=provider_pref, file=file_input)

            # ── 2) Extracción (página a página o completa) ─────────────────
            from app.validation.consolidator import consolidate_pages
            from app.validation.validator import validate_invoice

            if file_input.split_pages:
                page_dicts = [
                    provider.extract_page(file_input, page_no)
                    for page_no in range(1, (doc.page_count or 1) + 1)
                ]
                # Cada página se normaliza a InvoiceSchema parcial
                page_invoices = [InvoiceSchema.model_validate(pd) for pd in page_dicts]
                # Marca metadatos de página con el proveedor usado
                for idx, pinv in enumerate(page_invoices, start=1):
                    pinv.pages = [PageMeta(page_number=idx, provider=provider.name)]
                invoice = consolidate_pages(page_invoices)
            else:
                result = provider.extract_data(file_input)
                invoice = InvoiceSchema.model_validate(result.data)
                invoice.pages = [PageMeta(page_number=1, provider=provider.name)]

            # ── 3) Validación determinista (regla #4) ──────────────────────
            report = validate_invoice(invoice)
            invoice.validation = report

            task.extracted_data = invoice.model_dump(mode="json")
            task.validation_report = report.model_dump(mode="json")
            task.provider_used = provider.name
            task.model_used = getattr(provider, "_model", None) or settings.mistral_llm_model
            task.status = (
                TaskStatus.COMPLETED if report.is_valid else TaskStatus.NEEDS_REVIEW
            )
            task.finished_at = datetime.now(timezone.utc)

            # TAREA 1.5: el documento se procesó con éxito → consume cuota.
            if doc.user is not None:
                doc.user.documents_used += 1

            _log.info("Tarea %s terminada: %s (issues=%d)", task_id, task.status,
                      len(report.issues))
            return {
                "status": task.status.value,
                "is_valid": report.is_valid,
                "issues": len(report.issues),
            }

        except Exception as exc:  # noqa: BLE001 — TAREA 4: el worker NUNCA muere
            friendly = _friendly_message(exc)
            _log.exception("Error procesando tarea %s", task_id)
            _mark_failed(task_id, friendly)  # transacción propia: inmune a reintentos
            return {
                "status": "failed",
                "error": friendly,
                "retryable": isinstance(exc, _RETRYABLE),
            }


@celery.task(name="process_document", bind=True, max_retries=2, default_retry_delay=10)
def process_document(self, task_id: str,
                     pais: str | None = None,
                     columnas: list[str] | None = None) -> dict:
    """Tarea Celery: envuelve run_extraction con reintentos ante fallos transitorios."""
    result = run_extraction(task_id, pais, columnas)
    settings = get_settings()
    if (result.get("retryable")
            and not settings.celery_eager
            and self.request.retries < self.max_retries):
        raise self.retry(exc=RuntimeError(result.get("error", "fallo transitorio")))
    return result

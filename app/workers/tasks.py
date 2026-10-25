"""Tarea asíncrona de extracción — regla arquitectónica #5.

Pipeline completo ejecutado por el worker Celery:
    1. Marca la tarea en PROCESSING.
    2. Elige proveedor vía Factory (config del usuario / dificultad).
    3. Extrae por página (PDF multipágina) o de una vez (imagen/1 página).
    4. Si hay varias páginas → consolidador (regla #4).
    5. Valida matemáticamente (regla #4) → NEEDS_REVIEW si falla.
    6. Guarda el JSON canónico en la BD.

Estados resultantes: COMPLETED (válido) | NEEDS_REVIEW (inválido) | FAILED.
"""
from __future__ import annotations

import logging

from app.core.config import get_settings
from app.core.db.models import ExtractionTask, TaskStatus
from app.core.schemas.invoice import InvoiceSchema, PageMeta
from app.workers.celery_app import celery

_log = logging.getLogger("ocr.workers")

# MIME types aceptados por los proveedores multimodales.
SUPPORTED_MIME = {"application/pdf", "image/png", "image/jpeg", "image/tiff", "image/webp"}


def _page_count(file_path: str, mime: str) -> int:
    """Número de páginas (1 para imágenes)."""
    if mime != "application/pdf":
        return 1
    import fitz  # PyMuPDF

    with fitz.open(file_path) as pdf:
        return pdf.page_count


@celery.task(name="process_document", bind=True, max_retries=2, default_retry_delay=10)
def process_document(self, task_id: str) -> dict:
    """Extrae, consolida y valida un documento. Devuelve resumen de estado."""
    from app.core.db.base import session_scope
    from app.core.db.models import Document

    settings = get_settings()
    with session_scope() as db:
        task = db.get(ExtractionTask, task_id)
        if task is None:
            _log.error("Tarea %s no encontrada", task_id)
            return {"status": "failed", "error": "task not found"}
        doc = db.get(Document, task.document_id)

        task.status = TaskStatus.PROCESSING
        task.attempts += 1
        task.started_at = task.started_at or __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        )

        try:
            # ── 1) Elegir proveedor (Factory, regla #1) ─────────────────────
            from app.ai.base import ExtractionInput
            from app.ai.factory import get_provider

            provider_pref = None
            if doc.user and doc.user.preferred_provider != "auto":
                provider_pref = doc.user.preferred_provider

            file_input = ExtractionInput(
                file_path=__import__("pathlib").Path(doc.storage_path),
                mime_type=doc.mime_type,
                hint="invoice",
                # Dificultad heurística: PDFs grandes y escaneados son más complejos
                difficulty=7 if doc.page_count and doc.page_count > 1 else 5,
                split_pages=(doc.mime_type == "application/pdf" and (doc.page_count or 1) > 1),
            )
            provider = get_provider(preferred=provider_pref, file=file_input)

            # ── 2) Extracción (página a página o completa) ─────────────────
            from app.validation.consolidator import consolidate_pages
            from app.validation.validator import validate_invoice

            if file_input.split_pages:
                page_dicts = []
                for page_no in range(1, (doc.page_count or 1) + 1):
                    page_dicts.append(provider.extract_page(file_input, page_no))
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
            task.finished_at = __import__("datetime").datetime.now(
                __import__("datetime").timezone.utc
            )
            _log.info("Tarea %s terminada: %s (issues=%d)", task_id, task.status,
                      len(report.issues))
            return {
                "status": task.status.value,
                "is_valid": report.is_valid,
                "issues": len(report.issues),
            }

        except Exception as exc:  # noqa: BLE001 — el worker nunca debe morir en silencio
            _log.exception("Error procesando tarea %s", task_id)
            task.status = TaskStatus.FAILED
            task.error_message = f"{type(exc).__name__}: {exc}"
            task.finished_at = __import__("datetime").datetime.now(
                __import__("datetime").timezone.utc
            )
            # Reintento automático (Celery) salvo que ya agotemos.
            if self.request.retries < self.max_retries and settings.celery_eager is False:
                raise self.retry(exc=exc)
            return {"status": "failed", "error": str(exc)}

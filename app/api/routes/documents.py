"""Rutas de documentos y tareas — regla arquitectónica #5.

El endpoint de subida SOLO: valida el archivo, lo persiste, crea la tarea
y la encola. Devuelve ``task_id`` inmediatamente (HTTP 202). Nada de IA
en el ciclo request/response.

    POST   /api/v1/documents              → sube y encola (→ task_id)
    GET    /api/v1/tasks/{task_id}        → estado + resultado canónico
    PATCH  /api/v1/tasks/{task_id}        → guarda correcciones humanas
    POST   /api/v1/tasks/{task_id}/export → genera xlsx/csv/docx/pdf
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.db.base import get_db
from app.core.db.models import (
    Document,
    ExportFile,
    ExportFormat,
    ExtractionTask,
    TaskStatus,
    User,
)
from app.core.schemas.invoice import InvoiceSchema

_log = logging.getLogger("ocr.api.routes")
router = APIRouter(prefix="/api/v1", tags=["documents"])

ALLOWED_MIME = {"application/pdf", "image/png", "image/jpeg", "image/tiff", "image/webp"}


class TaskOut(BaseModel):
    """Resumen de tarea para el cliente (flujo de 4 pasos del frontend)."""

    task_id: str
    status: TaskStatus
    provider_used: str | None
    model_used: str | None
    is_valid: bool | None
    issues: list[dict] | None
    extracted_data: dict | None
    error_message: str | None
    document_filename: str

    class Config:
        from_attributes = True


def _task_to_out(task: ExtractionTask) -> TaskOut:
    return TaskOut(
        task_id=task.id,
        status=task.status,
        provider_used=task.provider_used,
        model_used=task.model_used,
        is_valid=(task.validation_report or {}).get("is_valid"),
        issues=(task.validation_report or {}).get("issues"),
        extracted_data=task.extracted_data,
        error_message=task.error_message,
        document_filename=task.document.filename if task.document else "?",
    )


# ── POST /documents: subir y encolar ─────────────────────────────────────────

@router.post("/documents", status_code=202)
async def upload_document(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Recibe el archivo, lo almacena y encola la extracción asíncrona.

    Returns:
        ``{"task_id": …, "status": "queued"}`` — el frontend hace polling
        de ``GET /tasks/{task_id}``.
    """
    settings = get_settings()
    if file.content_type not in ALLOWED_MIME:
        raise HTTPException(415, f"Tipo no soportado: {file.content_type}. "
                                 f"Permitidos: {sorted(ALLOWED_MIME)}")

    content = await file.read()
    if len(content) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, f"Archivo > {settings.max_upload_mb} MB.")

    # Duplicidad/auditoría por SHA-256
    sha256 = hashlib.sha256(content).hexdigest()

    storage_dir = settings.upload_dir / user.id
    storage_dir.mkdir(parents=True, exist_ok=True)
    doc_id_safe = sha256[:12]
    storage_path = storage_dir / f"{doc_id_safe}_{Path(file.filename or 'doc').name}"
    storage_path.write_bytes(content)

    # Conteo de páginas (PDF) — decide extracción multipágina en el worker
    page_count = 1
    if file.content_type == "application/pdf":
        import fitz

        with fitz.open(stream=content, filetype="pdf") as pdf:
            page_count = pdf.page_count

    document = Document(
        user_id=user.id,
        filename=file.filename or "documento",
        mime_type=file.content_type,
        size_bytes=len(content),
        sha256=sha256,
        storage_path=str(storage_path),
        page_count=page_count,
    )
    db.add(document)
    db.flush()  # asigna document.id

    task = ExtractionTask(document_id=document.id)
    db.add(task)
    db.commit()

    # ── Encolado (regla #5): eager en dev, Redis/Celery en prod ────────────
    from app.workers.tasks import process_document

    process_document.delay(task.id)
    _log.info("Tarea %s encolada (%s, %d pág.)", task.id, document.filename, page_count)

    return {"task_id": task.id, "status": "queued", "page_count": page_count}


# ── GET /tasks/{task_id}: estado y resultado ─────────────────────────────────

@router.get("/tasks/{task_id}", response_model=TaskOut)
def get_task(task_id: str,
             user: User = Depends(get_current_user),
             db: Session = Depends(get_db)) -> TaskOut:
    """Polling del frontend (paso 2: progreso → paso 3: revisión)."""
    task = db.get(ExtractionTask, task_id)
    if task is None or (task.document and task.document.user_id != user.id):
        raise HTTPException(404, "Tarea no encontrada.")
    return _task_to_out(task)


# ── PATCH /tasks/{task_id}: revisión humana (paso 3 del flujo) ───────────────

class HumanReview(BaseModel):
    """Correcciones del revisor sobre la extracción de la IA."""

    extracted_data: dict          # InvoiceSchema corregido (tabla editable UI)
    approve: bool = True          # True → marca COMPLETED; False → NEEDS_REVIEW


@router.patch("/tasks/{task_id}", response_model=TaskOut)
def review_task(task_id: str, review: HumanReview,
                user: User = Depends(get_current_user),
                db: Session = Depends(get_db)) -> TaskOut:
    """Guarda las correcciones humanas y RE-valida matemáticamente.

    La IA propuso, el humano corrigió, y Python vuelve a validar (regla #4):
    si el humano introduce una factura que no cuadra, la tarea vuelve a
    NEEDS_REVIEW aunque apruebe.
    """
    task = db.get(ExtractionTask, task_id)
    if task is None or (task.document and task.document.user_id != user.id):
        raise HTTPException(404, "Tarea no encontrada.")
    if task.status not in (TaskStatus.NEEDS_REVIEW, TaskStatus.COMPLETED):
        raise HTTPException(409, f"Tarea en estado {task.status.value}; aún no revisable.")

    try:
        corrected = InvoiceSchema.model_validate(review.extracted_data)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(422, f"El JSON corregido no cumple el esquema canónico: {exc}")

    from app.validation.validator import validate_invoice

    report = validate_invoice(corrected)
    corrected.validation = report

    task.extracted_data = corrected.model_dump(mode="json")
    task.validation_report = report.model_dump(mode="json")
    task.human_overridden = True
    task.status = (
        TaskStatus.COMPLETED if (review.approve and report.is_valid) else TaskStatus.NEEDS_REVIEW
    )
    task.finished_at = datetime.now(timezone.utc)
    db.commit()
    return _task_to_out(task)


# ── POST /tasks/{task_id}/export: exportación (paso 4 del flujo) ─────────────

class ExportRequest(BaseModel):
    format: ExportFormat = ExportFormat.XLSX


@router.post("/tasks/{task_id}/export")
def export_task(task_id: str, body: ExportRequest,
                user: User = Depends(get_current_user),
                db: Session = Depends(get_db)) -> FileResponse:
    """Genera el fichero (Excel/CSV/Word/PDF) desde el JSON canónico final."""
    task = db.get(ExtractionTask, task_id)
    if task is None or (task.document and task.document.user_id != user.id):
        raise HTTPException(404, "Tarea no encontrada.")
    if task.extracted_data is None:
        raise HTTPException(409, "La tarea aún no tiene datos extraídos.")

    from app.services.exporter import MIME_TYPES, export_invoice

    invoice = InvoiceSchema.model_validate(task.extracted_data)
    fmt = body.format.value
    base_name = f"{task_id[:8]}_{(task.document.filename or 'documento').rsplit('.', 1)[0]}"
    try:
        out_path = export_invoice(invoice, fmt, get_settings().export_dir, base_name)
    except ValueError as exc:
        raise HTTPException(400, str(exc))

    db.add(ExportFile(task_id=task.id, format=body.format, file_path=str(out_path)))
    db.commit()

    return FileResponse(
        path=out_path,
        media_type=MIME_TYPES[fmt],
        filename=out_path.name,
    )

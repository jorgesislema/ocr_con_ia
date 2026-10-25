"""Modelos SQLAlchemy (2.0) del SaaS.

Tablas principales:
    * ``users``            — tenants con API key propia.
    * ``documents``        — archivos subidos (PDF/imagen) con hash SHA-256.
    * ``extraction_tasks`` — tareas asíncronas de la cola (regla #5).
    * ``exports``          — ficheros generados (Excel/CSV/Word/PDF).
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Enum as SAEnum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """Base declarativa común a todos los modelos."""


class TaskStatus(str, enum.Enum):
    """Ciclo de vida de una extracción asíncrona."""

    QUEUED = "queued"                # encolada, devuelve task_id al cliente
    PROCESSING = "processing"        # el worker la está extrayendo con IA
    NEEDS_REVIEW = "needs_review"    # extraída pero con errores de validación → revisión humana
    COMPLETED = "completed"          # extraída y validada OK
    FAILED = "failed"                # error irrecuperable del proveedor o del pipeline


class ExportFormat(str, enum.Enum):
    XLSX = "xlsx"
    CSV = "csv"
    DOCX = "docx"
    PDF = "pdf"


class User(Base):
    """Tenant del SaaS. Autenticación por API key (header ``X-API-Key``)."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    api_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    plan: Mapped[str] = mapped_column(String(20), default="free")  # free | pro | enterprise
    # Proveedor preferido del usuario: "auto" | "gemini" | "mistral"
    preferred_provider: Mapped[str] = mapped_column(String(20), default="auto")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    documents: Mapped[list["Document"]] = relationship(back_populates="user", cascade="all, delete")


class Document(Base):
    """Archivo fuente subido por un usuario."""

    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    filename: Mapped[str] = mapped_column(String(512))
    mime_type: Mapped[str] = mapped_column(String(128))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64), index=True)  # deduplicación / auditoría
    storage_path: Mapped[str] = mapped_column(Text)              # ruta en disco/blob
    page_count: Mapped[int | None] = mapped_column(Integer, default=None)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    user: Mapped[User] = relationship(back_populates="documents")
    tasks: Mapped[list["ExtractionTask"]] = relationship(
        back_populates="document", cascade="all, delete"
    )


class ExtractionTask(Base):
    """Una extracción asíncrona sobre un documento (regla arquitectónica #5).

    El endpoint FastAPI solo crea esta fila y encola; el worker Celery
    actualiza el estado y guarda el resultado canónico aquí.
    """

    __tablename__ = "extraction_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), index=True)

    status: Mapped[TaskStatus] = mapped_column(
        SAEnum(TaskStatus, name="task_status", native_enum=False),
        default=TaskStatus.QUEUED,
        index=True,
    )
    provider_used: Mapped[str | None] = mapped_column(String(30))   # gemini | mistral
    model_used: Mapped[str | None] = mapped_column(String(80))

    # Resultado canónico JSON (InvoiceSchema) + informe de validación
    extracted_data: Mapped[dict | None] = mapped_column(JSON, default=None)
    validation_report: Mapped[dict | None] = mapped_column(JSON, default=None)
    # Correcciones humanas aplicadas en la revisión (paso 3 del flujo UI)
    human_overridden: Mapped[bool] = mapped_column(default=False)

    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    document: Mapped[Document] = relationship(back_populates="tasks")
    exports: Mapped[list["ExportFile"]] = relationship(
        back_populates="task", cascade="all, delete"
    )


class ExportFile(Base):
    """Fichero exportado a partir de una tarea completada/revisada."""

    __tablename__ = "exports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    task_id: Mapped[str] = mapped_column(ForeignKey("extraction_tasks.id"), index=True)
    format: Mapped[ExportFormat] = mapped_column(
        SAEnum(ExportFormat, name="export_format", native_enum=False)
    )
    file_path: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    task: Mapped[ExtractionTask] = relationship(back_populates="exports")

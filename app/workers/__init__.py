"""Workers Celery del SaaS (regla arquitectónica #5)."""

from app.workers.celery_app import celery
from app.workers.tasks import process_document

__all__ = ["celery", "process_document"]

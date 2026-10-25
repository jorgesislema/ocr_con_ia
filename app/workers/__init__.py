"""Workers del SaaS (regla arquitectónica #5).

Dos backends de cola según despliegue (TAREA 3.2):
    * ``run_extraction`` — función plana para BackgroundTasks de FastAPI
      (despliegue costo cero, sin Redis).
    * ``process_document`` — tarea Celery (con Redis / mayor volumen).
"""

from app.workers.celery_app import celery
from app.workers.tasks import process_document, run_extraction

__all__ = ["celery", "process_document", "run_extraction"]

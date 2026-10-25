"""Configuración de Celery — regla arquitectónica #5 (flujo asíncrono).

Producción:   broker y backend = Redis (OCR_REDIS_URL).
Desarrollo:   si ``OCR_CELERY_EAGER=true`` (por defecto) las tareas se
              ejecutan en el MISMO proceso de la API (modo eager) para no
              exigir Redis en local. El contrato (task_id + estados) es
              idéntico: cambiar a Redis real es solo una variable de entorno.

Arrancar worker real:
    celery -A app.workers.celery_app:celery worker --loglevel=info
"""
from __future__ import annotations

from celery import Celery

from app.core.config import get_settings

settings = get_settings()

# En modo eager (dev sin Redis) usamos el transporte "memory://": Celery 5.x
# aún abre un producer en apply_async, y con redis:// exigiría el paquete redis.
_eager = settings.celery_eager
_broker = "memory://" if _eager else settings.redis_url

celery = Celery(
    "ocr_saas",
    broker=_broker,
    backend="cache+memory://" if _eager else settings.redis_url,
    include=["app.workers.tasks"],
)

celery.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    task_track_started=True,               # permite estado STARTED en progreso UI
    task_acks_late=True,                   # reintento si el worker muere a mitad
    worker_prefetch_multiplier=1,          # reparto justo entre workers
    task_time_limit=600,                   # 10 min máx. por documento
    task_soft_time_limit=540,
)

# Modo desarrollo sin Redis: ejecución síncrona en proceso.
if settings.celery_eager:
    celery.conf.task_always_eager = True
    celery.conf.task_eager_propagates = False

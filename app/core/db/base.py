"""Sesión de base de datos (SQLAlchemy 2.0, sync engine).

Uso en FastAPI:
    def endpoint(db: Session = Depends(get_db)): ...

Uso en workers Celery:
    with session_scope() as db: ...
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.db.models import Base

settings = get_settings()

# check_same_thread=False → SQLite soporta hilos del worker y de la API.
engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {},
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db() -> None:
    """Crea las tablas si no existen (dev). En producción usar Alembic."""
    Base.metadata.create_all(bind=engine)


def get_db() -> Iterator[Session]:
    """Dependency FastAPI: sesión por request, siempre cerrada al final."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Context manager para workers: commit/rollback automático."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

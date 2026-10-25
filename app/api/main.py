"""Aplicación FastAPI principal del SaaS.

Arranque (desarrollo):
    uvicorn app.api.main:app --reload --port 8000
    → UI web en http://localhost:8000/  ·  docs en /docs

Responsabilidades:
    * Montar los routers versionados (/api/v1).
    * Servir el frontend SPA (app/frontend) en /.
    * CORS para desarrollo (Vite u otro dev server).
    * init_db + usuario demo en el arranque (dev).
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import BASE_DIR, get_settings

_log = logging.getLogger("ocr.api")

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Crea tablas y usuario demo al arrancar (solo dev; prod usa Alembic)."""
    from app.core.config import get_settings
    from app.core.db.base import SessionLocal, init_db
    from app.core.db.models import User
    from app.api.deps import generate_api_key

    settings = get_settings()
    init_db()
    if settings.environment == "development":
        with SessionLocal() as db:
            if not db.query(User).filter(User.email == "demo@ocr.local").first():
                db.add(User(email="demo@ocr.local",
                            api_key=generate_api_key(),
                            plan="free"))
                db.commit()
                _log.info("Usuario demo creado: demo@ocr.local (X-API-Key en BD)")
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        description=(
            "SaaS de extracción de documentos con IA (facturas LatAm/Europa, "
            "manuscritos, multipágina) → Excel / CSV / Word / PDF."
        ),
        version="1.0.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173",
                       "http://localhost:8000", "http://127.0.0.1:8000"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Rutas de negocio
    from app.api.routes.documents import router as documents_router

    app.include_router(documents_router)

    # Health check sin auth (para load balancers)
    @app.get("/health", tags=["sistema"])
    def health() -> dict:
        return {"status": "ok", "version": app.version}

    # Frontend SPA (Paso 5) — se monta al final para no pisar /api ni /docs
    if (FRONTEND_DIR / "index.html").exists():
        app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")

    return app


app = create_app()

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
    from app.api.deps import generate_api_key, hash_password

    settings = get_settings()
    init_db()
    if settings.environment == "development":
        with SessionLocal() as db:
            if not db.query(User).filter(User.email == "demo@ocr.local").first():
                # Cuenta demo con credenciales conocidas para probar el flujo
                # JWT en local (login con demo@ocr.local / demo1234).
                db.add(User(
                    email="demo@ocr.local",
                    hashed_password=hash_password("demo1234"),
                    api_key=generate_api_key(),
                    plan="free",
                    max_documents=50,
                ))
                db.commit()
                _log.info("Usuario demo creado: demo@ocr.local / demo1234 (solo dev)")
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        description=(
            "SaaS de extracción de documentos con IA (facturas LatAm/Europa, "
            "manuscritos, multipágina) → Excel / CSV / Word / PDF."
        ),
        version="1.1.0",
        lifespan=lifespan,
    )

    # ── CORS (TAREA 3.3): dominios del frontend por variable de entorno ────
    # CORS_ORIGINS="https://mi-dominio.com,https://otro.com" + regex para
    # previews de Vercel/Netlify (subdominios dinámicos).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
        allow_origin_regex=settings.cors_origin_regex or None,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Rutas de negocio
    from app.api.routes.auth import router as auth_router
    from app.api.routes.documents import router as documents_router

    app.include_router(auth_router)
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

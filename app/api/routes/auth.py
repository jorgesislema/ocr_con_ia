"""Autenticación y gestión de planes — TAREA 1.

Modelo comercial "On-Demand" (freelance → una empresa, sin pasarela):
    * El cliente paga por transferencia.
    * NOSOTROS creamos la cuenta con ``POST /auth/register``, protegido por
      la clave de administrador (``X-Admin-Key`` == ``ADMIN_KEY`` del .env).
    * El cliente entra con ``POST /auth/login`` y recibe un JWT.
    * El JWT se usa como ``Authorization: Bearer <token>`` en el resto de
      la API; el límite del plan se aplica al subir documentos.

Endpoints:
    POST /auth/register  (admin) → crea la cuenta del cliente
    POST /auth/login            → devuelve {access_token, token_type, ...}
    GET  /auth/me               → datos para la navbar (email, plan, uso)
"""
from __future__ import annotations

import logging
import secrets
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.api.deps import (
    create_access_token,
    generate_api_key,
    get_current_user,
    hash_password,
    verify_password,
)
from app.core.config import get_settings
from app.core.db.base import get_db
from app.core.db.models import User

_log = logging.getLogger("ocr.auth")

router = APIRouter(prefix="/auth", tags=["auth"])

# Cuotas por defecto del plan (TAREA 1.3).
PLAN_LIMITS = {"free": 50, "pro": 0}  # 0 = ilimitado


def _require_admin(x_admin_key: str | None) -> None:
    """Protege el registro: solo el operador crea cuentas.

    * Con ``ADMIN_KEY`` configurada → debe coincidir con el header.
    * Sin ``ADMIN_KEY`` en desarrollo → se permite (comodidad de dev, se
      registra warning). En producción sin clave → deshabilitado.
    """
    settings = get_settings()
    if settings.admin_key:
        if not x_admin_key or not secrets.compare_digest(x_admin_key, settings.admin_key):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "X-Admin-Key inválida.")
        return
    if settings.environment == "development":
        _log.warning("ADMIN_KEY no configurada: registro abierto solo en desarrollo.")
        return
    raise HTTPException(
        status.HTTP_403_FORBIDDEN,
        "Registro deshabilitado: configura ADMIN_KEY en el servidor.",
    )


class RegisterRequest(BaseModel):
    """Cuenta que el operador crea para un cliente tras recibir el pago."""

    email: EmailStr
    password: str = Field(min_length=8, description="Contraseña inicial del cliente")
    plan: Literal["free", "pro"] = "free"
    # Override manual de la cuota (0 = ilimitado). None → según el plan.
    max_documents: int | None = Field(default=None, ge=0)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


@router.post("/register", status_code=201)
def register(body: RegisterRequest,
             x_admin_key: str | None = Header(default=None, alias="X-Admin-Key"),
             db: Session = Depends(get_db)) -> dict:
    """Crea la cuenta de un cliente (solo operador, con X-Admin-Key)."""
    _require_admin(x_admin_key)

    email = body.email.lower().strip()
    if db.query(User).filter(User.email == email).first() is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"El email {email} ya está registrado.")

    user = User(
        email=email,
        hashed_password=hash_password(body.password),
        api_key=generate_api_key(),
        plan=body.plan,
        # Override manual o cuota del plan (pro → 0 = ilimitado)
        max_documents=(
            body.max_documents if body.max_documents is not None
            else PLAN_LIMITS.get(body.plan, 50)
        ),
        documents_used=0,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    _log.info("Cuenta creada: %s (plan=%s, max=%d)", email, user.plan, user.max_documents)
    return {
        "id": user.id,
        "email": user.email,
        "plan": user.plan,
        "max_documents": user.max_documents,
        "api_key": user.api_key,  # se entrega al cliente para integraciones
    }


@router.post("/login")
def login(body: LoginRequest, db: Session = Depends(get_db)) -> dict:
    """Autentica al cliente y emite su JWT."""
    user = db.query(User).filter(User.email == body.email.lower().strip()).first()
    if user is None or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Credenciales inválidas.")

    return {
        "access_token": create_access_token(user),
        "token_type": "bearer",
        "email": user.email,
        "plan": user.plan,
        "max_documents": user.max_documents,
        "documents_used": user.documents_used,
    }


@router.get("/me")
def me(user: User = Depends(get_current_user)) -> dict:
    """Datos de sesión para la navbar (TAREA 2: Hola, email | Plan | Uso)."""
    return {
        "email": user.email,
        "plan": user.plan,
        "documents_used": user.documents_used,
        "max_documents": user.max_documents,
        "api_key": user.api_key,
        "preferred_provider": user.preferred_provider,
    }

"""Dependencias comunes de la API — TAREA 1: autenticación JWT real.

Autenticación con doble canal:
    1. ``Authorization: Bearer <JWT>`` — el canal principal (frontend web).
    2. ``X-API-Key`` — canal secundario para integraciones programáticas
       del cliente (ERP, scripts), sin degradar a quien ya lo usaba.

Contraseñas hasheadas con passlib (PBKDF2-SHA256, sin dependencias nativas)
y tokens JWT firmados con python-jose (HS256, secreto vía get_secret/env).
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Depends, Header, HTTPException, status
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db.base import get_db
from app.core.db.models import User

# PBKDF2-SHA256: puro Python (sin bcrypt nativo), adecuado y portable.
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


def hash_password(plain: str) -> str:
    """Hashea una contraseña en texto plano."""
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str | None) -> bool:
    """Verifica una contraseña contra su hash (False si no hay hash)."""
    if not hashed:
        return False
    return pwd_context.verify(plain, hashed)


def create_access_token(user: User) -> str:
    """Genera un JWT firmado con la identidad y el plan del usuario."""
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {
        "sub": user.id,
        "email": user.email,
        "plan": user.plan,
        "exp": expire,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict | None:
    """Decodifica y valida un JWT. None si es inválido o expiró."""
    settings = get_settings()
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError:
        return None


def get_current_user(
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    db: Session = Depends(get_db),
) -> User:
    """Resuelve el usuario desde Bearer JWT o X-API-Key."""
    # 1) JWT Bearer (frontend)
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        payload = decode_token(token)
        if payload is None:
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                "Token inválido o expirado. Inicia sesión de nuevo.",
            )
        user = db.get(User, payload.get("sub"))
        if user is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Usuario no encontrado.")
        return user

    # 2) API key (integraciones)
    if x_api_key:
        user = db.query(User).filter(User.api_key == x_api_key).first()
        if user is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "X-API-Key inválida.")
        return user

    raise HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        "No autenticado: envía 'Authorization: Bearer <token>' o 'X-API-Key'.",
    )


def generate_api_key() -> str:
    """Genera una API key criptográficamente segura para nuevos tenants."""
    return "ocr_" + secrets.token_urlsafe(32)

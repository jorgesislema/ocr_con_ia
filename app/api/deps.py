"""Dependencias comunes de la API: autenticación por API key.

Cada usuario (tenant) tiene una ``api_key``; se envía en el header
``X-API-Key``. En modo desarrollo, si la petición no lleva header, se
usa el usuario demo creado por ``bootstrap_demo_user``.
"""
from __future__ import annotations

import secrets

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.db.models import User
from app.core.db.base import get_db


def get_current_user(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    db: Session = Depends(get_db),
) -> User:
    """Resuelve el usuario a partir del header X-API-Key."""
    if x_api_key:
        user = db.query(User).filter(User.api_key == x_api_key).first()
        if user is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "X-API-Key inválida.")
        return user
    # Dev: usuario demo para poder probar sin configurar nada.
    demo = db.query(User).filter(User.email == "demo@ocr.local").first()
    if demo is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Falta el header X-API-Key y no existe usuario demo. Arranca la API "
            "(init_db + bootstrap_demo_user) o envía tu X-API-Key.",
        )
    return demo


def generate_api_key() -> str:
    """Genera una API key criptográficamente segura para nuevos tenants."""
    return "ocr_" + secrets.token_urlsafe(32)

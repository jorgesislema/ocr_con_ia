"""Sistema RBAC de usuarios — FASE 6.

Gestión mínima de usuarios con tres roles:
  - admin    : acceso completo (exportar, borrar auditorías, gestionar usuarios)
  - operator : puede procesar documentos y exportar a ERP
  - auditor  : solo lectura (ver logs y resultados, sin exportar ni borrar)

Persistencia en SQLite (hashed con SHA-256 + sal).
No usa librerías externas: solo stdlib.

Uso típico
----------
    from src.core.user_manager import UserManager, AuthError

    mgr = UserManager()
    mgr.create_user("admin", "secreto123", role="admin")
    session = mgr.login("admin", "secreto123")  # devuelve UserSession
    mgr.require_permission(session, "export_erp")  # lanza AuthError si no puede
"""
from __future__ import annotations

import hashlib
import logging
import os
import secrets
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

_log = logging.getLogger("ocr.user_manager")

_DEFAULT_DB = Path(__file__).resolve().parent.parent.parent / "data" / "users.db"

Role = Literal["admin", "operator", "auditor"]

# Permisos por rol
_ROLE_PERMISSIONS: dict[str, set[str]] = {
    "admin": {
        "export_erp",
        "delete_audit",
        "manage_users",
        "process_ocr",
        "view_results",
        "watch_folder",
        "circuit_reset",
    },
    "operator": {
        "export_erp",
        "process_ocr",
        "view_results",
        "watch_folder",
    },
    "auditor": {
        "view_results",
    },
}


class AuthError(PermissionError):
    """Excepción para fallos de autenticación o autorización."""


@dataclass
class UserSession:
    username: str
    role: str
    token: str = field(default_factory=lambda: secrets.token_hex(16))
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def can(self, permission: str) -> bool:
        return permission in _ROLE_PERMISSIONS.get(self.role, set())


class UserManager:
    """Gestión de usuarios con hash de contraseña y sesiones en memoria.

    Parámetros
    ----------
    db_path :
        Ruta al archivo SQLite de usuarios.
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._db_path = Path(db_path or _DEFAULT_DB)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = self._connect()
        self._init_schema()
        self._sessions: dict[str, UserSession] = {}   # token → session
        self._ensure_default_admin()

    # ── Conexión ──────────────────────────────────────────────────────────────

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                username   TEXT PRIMARY KEY,
                role       TEXT NOT NULL DEFAULT 'operator',
                salt       TEXT NOT NULL,
                pwd_hash   TEXT NOT NULL,
                active     INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                last_login TEXT
            );
            """
        )
        self._conn.commit()

    def _ensure_default_admin(self) -> None:
        """Crea el usuario admin por defecto si la tabla está vacía."""
        row = self._conn.execute("SELECT COUNT(*) as n FROM users").fetchone()
        if row["n"] == 0:
            self.create_user("admin", "admin1234", role="admin")
            _log.warning(
                "Usuario admin creado con contraseña por defecto 'admin1234'. "
                "Cámbiala inmediatamente desde la configuración."
            )

    # ── Hash ──────────────────────────────────────────────────────────────────

    @staticmethod
    def _hash(password: str, salt: str) -> str:
        key = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            iterations=260_000,
        )
        return key.hex()

    # ── API pública ───────────────────────────────────────────────────────────

    def create_user(
        self,
        username: str,
        password: str,
        role: Role = "operator",
    ) -> None:
        """Crea un nuevo usuario.  Lanza ValueError si ya existe."""
        if role not in _ROLE_PERMISSIONS:
            raise ValueError(f"Rol desconocido: {role!r}.  Usa: {list(_ROLE_PERMISSIONS)}")
        if len(password) < 6:
            raise ValueError("La contraseña debe tener al menos 6 caracteres.")
        salt      = secrets.token_hex(16)
        pwd_hash  = self._hash(password, salt)
        try:
            self._conn.execute(
                "INSERT INTO users (username, role, salt, pwd_hash) VALUES (?,?,?,?)",
                (username.strip().lower(), role, salt, pwd_hash),
            )
            self._conn.commit()
            _log.info("Usuario creado: %s (%s)", username, role)
        except sqlite3.IntegrityError:
            raise ValueError(f"El usuario '{username}' ya existe.")

    def change_password(self, username: str, new_password: str) -> None:
        """Cambia la contraseña de un usuario existente."""
        if len(new_password) < 6:
            raise ValueError("La contraseña debe tener al menos 6 caracteres.")
        salt     = secrets.token_hex(16)
        pwd_hash = self._hash(new_password, salt)
        cur = self._conn.execute(
            "UPDATE users SET salt=?, pwd_hash=? WHERE username=?",
            (salt, pwd_hash, username.strip().lower()),
        )
        if cur.rowcount == 0:
            raise ValueError(f"Usuario '{username}' no encontrado.")
        self._conn.commit()

    def set_role(self, username: str, role: Role) -> None:
        """Cambia el rol de un usuario (requiere permiso 'manage_users')."""
        if role not in _ROLE_PERMISSIONS:
            raise ValueError(f"Rol desconocido: {role!r}")
        cur = self._conn.execute(
            "UPDATE users SET role=? WHERE username=?",
            (role, username.strip().lower()),
        )
        if cur.rowcount == 0:
            raise ValueError(f"Usuario '{username}' no encontrado.")
        self._conn.commit()

    def deactivate_user(self, username: str) -> None:
        self._conn.execute(
            "UPDATE users SET active=0 WHERE username=?",
            (username.strip().lower(),),
        )
        self._conn.commit()

    def login(self, username: str, password: str) -> UserSession:
        """Autentica al usuario y devuelve una sesión activa."""
        uname = username.strip().lower()
        row = self._conn.execute(
            "SELECT * FROM users WHERE username=? AND active=1", (uname,)
        ).fetchone()
        if row is None:
            raise AuthError("Usuario no encontrado o desactivado.")
        expected = self._hash(password, row["salt"])
        if not secrets.compare_digest(expected, row["pwd_hash"]):
            raise AuthError("Contraseña incorrecta.")
        self._conn.execute(
            "UPDATE users SET last_login=datetime('now') WHERE username=?", (uname,)
        )
        self._conn.commit()
        session = UserSession(username=uname, role=row["role"])
        self._sessions[session.token] = session
        _log.info("Login: %s (%s)", uname, row["role"])
        return session

    def logout(self, token: str) -> None:
        self._sessions.pop(token, None)

    def session_from_token(self, token: str) -> UserSession | None:
        return self._sessions.get(token)

    def require_permission(self, session: UserSession | None, permission: str) -> None:
        """Lanza AuthError si la sesión no tiene el permiso requerido."""
        if session is None:
            raise AuthError("No hay sesión activa.  Inicia sesión primero.")
        if not session.can(permission):
            raise AuthError(
                f"El rol '{session.role}' no tiene permiso para '{permission}'."
            )

    def list_users(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT username, role, active, created_at, last_login FROM users"
        ).fetchall()
        return [dict(r) for r in rows]

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:
            pass

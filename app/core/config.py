"""Configuración central y gestión de secretos del SaaS.

Regla arquitectónica #3 (manejo de secretos):
-------------------------------------------------
Las API Keys NUNCA se leen directamente de variables sueltas en el código.
Todo acceso pasa por ``get_secret(key)``, que en producción conecta con
Infisical o HashiCorp Vault, y en desarrollo lee del archivo ``.env``.

Para añadir un proveedor nuevo de secretos basta implementar otro backend
en ``_load_from_remote`` sin tocar ningún módulo de negocio.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Raíz del proyecto (…/ocr_con_ia)
BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    """Ajustes del SaaS, sobreescribibles por variables de entorno.

    Convención de nombres: las plataformas cloud (Render/Supabase/Railway)
    inyectan ``DATABASE_URL`` y ``REDIS_URL`` sin prefijo, por lo que ambas
    se aceptan con y sin el prefijo ``OCR_``.
    """

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        env_prefix="OCR_",
        extra="ignore",
    )

    # ── Aplicación ────────────────────────────────────────────────────────
    app_name: str = "OCR Con IA — SaaS"
    environment: str = Field(default="development")  # development | production
    upload_dir: Path = Field(default=BASE_DIR / "storage" / "uploads")
    export_dir: Path = Field(default=BASE_DIR / "storage" / "exports")
    max_upload_mb: int = 25

    # ── Base de datos (TAREA 3.1) ─────────────────────────────────────────
    # Prod: DATABASE_URL (PostgreSQL de Supabase/Render). Dev: vacío → SQLite.
    database_url: str = Field(
        default="",
        validation_alias=AliasChoices("DATABASE_URL", "OCR_DATABASE_URL"),
    )

    # ── Cola asíncrona (TAREA 3.2) ────────────────────────────────────────
    # Sin REDIS_URL → BackgroundTasks de FastAPI (despliegue costo cero).
    # Con REDIS_URL → Celery + Redis (mayor volumen).
    redis_url: str = Field(
        default="",
        validation_alias=AliasChoices("REDIS_URL", "OCR_REDIS_URL"),
    )
    queue_backend: str = Field(
        default="auto",
        validation_alias=AliasChoices("QUEUE_BACKEND", "OCR_QUEUE_BACKEND"),
    )  # auto | background | celery
    celery_eager: bool = Field(default=True)

    # ── Autenticación JWT (TAREA 1) ───────────────────────────────────────
    jwt_secret: str = Field(
        default="dev-only-secret-cambiar-en-produccion",
        validation_alias=AliasChoices("JWT_SECRET", "OCR_JWT_SECRET"),
    )
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = Field(
        default=1440,
        validation_alias=AliasChoices("JWT_EXPIRE_MINUTES", "OCR_JWT_EXPIRE_MINUTES"),
    )
    # Clave de administrador para crear cuentas (modelo sin pasarela de pago:
    # el cliente paga por transferencia y habilitamos la cuenta a mano).
    admin_key: str = Field(
        default="",
        validation_alias=AliasChoices("ADMIN_KEY", "OCR_ADMIN_KEY"),
    )

    # ── Selección de proveedor IA (regla arquitectónica #1) ───────────────
    # "auto"  → el sistema elige según la dificultad del documento.
    # "gemini" | "mistral" → fuerza el proveedor (configuración del usuario).
    default_ai_provider: str = Field(default="auto")
    gemini_model: str = Field(default="gemini-2.0-flash")
    mistral_ocr_model: str = Field(default="mistral-ocr-latest")
    mistral_llm_model: str = Field(default="mistral-large-latest")

    # Tolerancia monetaria del validador determinista (unidades de moneda).
    validation_tolerance: float = 0.02

    # ── CORS (TAREA 3.3): dominios del frontend (Vercel/Netlify) ──────────
    cors_origins: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173,"
                "http://localhost:8000,http://127.0.0.1:8000",
        validation_alias=AliasChoices("CORS_ORIGINS", "OCR_CORS_ORIGINS"),
    )
    # Regex para previews de Vercel/Netlify (subdominios dinámicos).
    cors_origin_regex: str = Field(
        default=r"https://.*\.(vercel\.app|netlify\.app)",
        validation_alias=AliasChoices("CORS_ORIGIN_REGEX", "OCR_CORS_ORIGIN_REGEX"),
    )

    def resolved_database_url(self) -> str:
        """DATABASE_URL efectiva: PostgreSQL prod o SQLite dev.

        Normaliza el esquema ``postgres://`` (legacy de Supabase/Heroku) al
        driver psycopg que espera SQLAlchemy.
        """
        url = self.database_url
        if not url:
            return f"sqlite:///{BASE_DIR / 'storage' / 'saas.db'}"
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+psycopg://", 1)
        return url

    @property
    def use_background_tasks(self) -> bool:
        """True si la cola debe resolverse con BackgroundTasks (sin Redis)."""
        return self.queue_backend == "background" or (
            self.queue_backend == "auto" and not self.redis_url
        )


@lru_cache
def get_settings() -> Settings:
    """Devuelve la configuración singleton (cacheada por proceso)."""
    settings = Settings()
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    settings.export_dir.mkdir(parents=True, exist_ok=True)
    return settings


# ═══════════════════════════════════════════════════════════════════════════
#  Gestión de secretos  —  única puerta de entrada para credenciales
# ═══════════════════════════════════════════════════════════════════════════

class SecretNotFoundError(KeyError):
    """La clave solicitada no existe en ningún backend de secretos."""


def _load_dotenv_manually() -> dict[str, str]:
    """Carga mínima de ``.env`` sin dependencia externa.

    Solo se usa si ``python-dotenv`` no está instalado; mantiene ``.env``
    como mecanismo estándar de desarrollo.
    """
    env_path = BASE_DIR / ".env"
    values: dict[str, str] = {}
    if not env_path.exists():
        return values
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _load_from_remote(key: str) -> str | None:
    """Lee el secreto del backend remoto (Infisical / Vault).

    En producción, definir ``SECRET_BACKEND`` y las credenciales del
    backend. Devuelve ``None`` si no hay backend configurado — el caller
    hace fallback a ``.env`` para desarrollo.
    """
    backend = os.environ.get("SECRET_BACKEND", "").lower()
    if backend == "infisical":
        try:
            from infisical_sdk import InfisicalSDKClient  # type: ignore

            client = InfisicalSDKClient(host=os.environ["INFISICAL_HOST"])
            client.auth.universal_auth.login(
                client_id=os.environ["INFISICAL_CLIENT_ID"],
                client_secret=os.environ["INFISICAL_CLIENT_SECRET"],
            )
            secret = client.secrets.get_secret(
                secret_name=key,
                project_id=os.environ["INFISICAL_PROJECT_ID"],
                environment_slug=os.environ.get("INFISICAL_ENV", "prod"),
            )
            return secret.secretValue
        except Exception:  # noqa: BLE001 — un fallo de Vault no debe tumbar la app
            return None
    if backend == "vault":
        try:
            import hvac  # type: ignore

            client = hvac.Client(url=os.environ["VAULT_ADDR"], token=os.environ["VAULT_TOKEN"])
            read = client.secrets.kv.v2.read_secret_version(
                path=key.lower(), mount_point=os.environ.get("VAULT_MOUNT", "secret")
            )
            return read["data"]["data"].get(key)
        except Exception:  # noqa: BLE001
            return None
    return None


def get_secret(key: str) -> str:
    """Obtiene un secreto por nombre (p. ej. ``GEMINI_API_KEY``).

    Orden de resolución:
        1. Backend remoto (Infisical / Vault) — solo en producción.
        2. Variable de entorno ya exportada en el proceso.
        3. Archivo ``.env`` (desarrollo).

    Raises:
        SecretNotFoundError: si la clave no existe en ningún backend.
    """
    # 1) Backend remoto (producción)
    remote = _load_from_remote(key)
    if remote:
        return remote

    # 2) Variable de entorno
    value = os.environ.get(key)
    if value:
        return value

    # 3) .env de desarrollo (cacheado por clave por proceso)
    try:
        from dotenv import dotenv_values  # type: ignore

        value = dotenv_values(BASE_DIR / ".env").get(key)
    except ImportError:
        value = _load_dotenv_manually().get(key)
    if value:
        return value

    raise SecretNotFoundError(
        f"Secreto '{key}' no encontrado. Define SECRET_BACKEND (prod) o añádelo al .env (dev)."
    )

"""Factory de proveedores IA — regla arquitectónica #1.

El sistema elige el proveedor según:
    1. La configuración explícita del usuario (``preferred_provider``).
    2. La dificultad estimada del documento (modo ``auto``):
       tablas densas / escaneos de baja calidad → Mistral (precisión en tablas);
       documentos estándar / manuscritos → Gemini (gratuito, multimodal).

Añadir un proveedor nuevo = crear una clase que herede ``BaseAIProvider``
y registrarla en ``_PROVIDER_CLASSES``. Nada más.
"""
from __future__ import annotations

import logging

from app.ai.base import AIProviderError, BaseAIProvider, ExtractionInput

_log = logging.getLogger("ocr.ai.factory")

# Umbral de dificultad (0-10) a partir del cual pagamos por Mistral.
MISTRAL_DIFFICULTY_THRESHOLD = 7

# Registro de proveedores: nombre → clase. Punto único de extensión.
_PROVIDER_CLASSES: dict[str, type[BaseAIProvider]] = {}


def register_provider(cls: type[BaseAIProvider]) -> type[BaseAIProvider]:
    """Decorador para registrar clases de proveedores en el Factory."""
    _PROVIDER_CLASSES[cls.name] = cls
    return cls


# Se importan al final para que el decorador se ejecute con el registro listo.
from app.ai.gemini_provider import GeminiProvider   # noqa: E402
from app.ai.mistral_provider import MistralProvider  # noqa: E402

register_provider(GeminiProvider)
register_provider(MistralProvider)


def _auto_select(file: ExtractionInput) -> str:
    """Elige proveedor por dificultad del documento (modo ``auto``).

    Heurística inicial (mejorable con content_router del proyecto original):
        * difficulty >= 7            → mistral (tablas densas, escaneos sucios)
        * resto (manuscritos, OCR estándar) → gemini (tier gratuito)
    """
    if file.difficulty >= MISTRAL_DIFFICULTY_THRESHOLD:
        return "mistral"
    return "gemini"


def get_provider(preferred: str | None = None,
                 file: ExtractionInput | None = None) -> BaseAIProvider:
    """Devuelve una instancia lista para usar del proveedor elegido.

    Args:
        preferred: "gemini" | "mistral" | "auto" | None (usa settings del usuario).
        file: contexto del documento (necesario para el modo ``auto``).

    Raises:
        AIProviderError: si el proveedor solicitado no existe o no está
        disponible (falta la API key en get_secret).
    """
    from app.core.config import get_settings

    choice = (preferred or get_settings().default_ai_provider or "auto").lower()
    if choice == "auto":
        choice = _auto_select(file) if file else "gemini"

    cls = _PROVIDER_CLASSES.get(choice)
    if cls is None:
        raise AIProviderError(
            f"Proveedor '{choice}' desconocido. Disponibles: {sorted(_PROVIDER_CLASSES)}"
        )
    provider = cls()
    if not provider.available():
        # Si el preferido no está configurado y era "auto", intenta el otro.
        fallbacks = [n for n in _PROVIDER_CLASSES if n != choice]
        for fb in fallbacks:
            candidate = _PROVIDER_CLASSES[fb]()
            if candidate.available():
                _log.warning("Proveedor '%s' no disponible; fallback → '%s'", choice, fb)
                return candidate
        raise AIProviderError(
            f"Proveedor '{choice}' sin credenciales (usa get_secret en .env) y sin fallback."
        )
    return provider

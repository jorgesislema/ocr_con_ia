"""Capa de IA — patrón Factory de proveedores (regla arquitectónica #1)."""

from app.ai.base import AIProviderError, BaseAIProvider, ExtractionInput, ExtractionResult
from app.ai.factory import get_provider, register_provider
from app.ai.gemini_provider import GeminiProvider
from app.ai.mistral_provider import MistralProvider

__all__ = [
    "AIProviderError",
    "BaseAIProvider",
    "ExtractionInput",
    "ExtractionResult",
    "GeminiProvider",
    "MistralProvider",
    "get_provider",
    "register_provider",
]

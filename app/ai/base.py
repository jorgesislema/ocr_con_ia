"""Interfaz abstracta de proveedores IA — regla arquitectónica #1.

Todo proveedor (Gemini, Mistral, y los que se añadan en el futuro)
implementa :pyclass:`BaseAIProvider` y devuelve SIEMPRE un dict compatible
con :pyclass:`app.core.schemas.invoice.InvoiceSchema`. El resto del sistema
nunca conoce detalles del proveedor concreto (desacoplamiento total).
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ExtractionInput:
    """Entrada normalizada hacia el proveedor."""

    file_path: Path
    mime_type: str                     # application/pdf | image/png | ...
    hint: str = "invoice"              # invoice | receipt | music_score | generic
    # País del documento (ISO-3166 alpha-2, p. ej. "EC", "MX", "ES").
    # Determina la normativa fiscal inyectada en el prompt (TAREA 1).
    pais: str = ""
    # Columnas solicitadas por el cliente — la IA prioriza estos campos.
    columnas_solicitadas: list[str] = field(default_factory=list)
    # Pista de dificultad para el enrutado del Factory (0=fácil, 10=complejo)
    difficulty: int = 5
    # Por documento multipágina: extraer por separado cada página (regla #4)
    split_pages: bool = False


@dataclass
class ExtractionResult:
    """Salida normalizada del proveedor.

    ``data`` debe validar contra InvoiceSchema (se valida en el worker,
    no aquí, para que los proveedores sigan siendo livianos).
    """

    data: dict
    provider: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    confidence: float | None = None
    raw_response: str | None = None    # respuesta cruda para auditoría/debug
    page_results: list[dict] = field(default_factory=list)  # extracción por página


class AIProviderError(RuntimeError):
    """Error de extracción del proveedor (timeout, quota, respuesta inválida…)."""


class BaseAIProvider(abc.ABC):
    """Contrato común de todos los proveedores IA.

    Métodos:
        extract_data(input)      → extracción completa del documento.
        extract_page(...)        → extracción página a página (multipágina).
        estimate_difficulty(...) → heurística opcional del proveedor.
    """

    name: str = "base"

    @abc.abstractmethod
    def extract_data(self, file: ExtractionInput) -> ExtractionResult:
        """Extrae datos del documento y los devuelve como dict canónico.

        Raises:
            AIProviderError: si el proveedor falla o la respuesta no es
            JSON parseable hacia el esquema canónico.
        """

    @abc.abstractmethod
    def extract_page(self, file: ExtractionInput, page_number: int) -> dict:
        """Extrae una sola página (usado por el consolidador multipágina)."""

    @abc.abstractmethod
    def available(self) -> bool:
        """True si el proveedor tiene credenciales y SDK configurados."""

    def estimate_difficulty(self, file: ExtractionInput) -> int:
        """Estimación opcional de dificultad (0-10). Por defecto, la de entrada."""
        return file.difficulty

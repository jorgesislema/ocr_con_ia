"""Proveedor Gemini — opción gratuita/económica, multimodal.

Regla arquitectónica #1: implementación concreta de ``BaseAIProvider``.
Gemini se usa como proveedor por defecto por su tier gratuito y su buen
rendimiento multimodal (PDF e imágenes, incluidos manuscritos).
"""
from __future__ import annotations

import json
import logging

from app.ai.base import AIProviderError, BaseAIProvider, ExtractionInput, ExtractionResult
from app.ai.prompts import SYSTEM_PROMPT, build_extraction_prompt
from app.core.config import get_secret

_log = logging.getLogger("ocr.ai.gemini")

_PROVIDER = "gemini"


class GeminiProvider(BaseAIProvider):
    """Extracción vía Google Gemini (google-genai SDK).

    * Multimodal nativo: PDFs (hasta N páginas) e imágenes.
    * Entrada por bytes — no requiere subir el archivo a Storage.
    * Usa structured output (``response_mime_type="application/json"``)
      para forzar JSON parseable.
    """

    name = _PROVIDER

    def __init__(self, model: str | None = None) -> None:
        from google import genai  # import perezoso: solo si se usa este proveedor
        from google.genai import types as genai_types

        self._genai_types = genai_types
        self._model = model or get_settings_model()
        # La API key SIEMPRE llega por get_secret (regla #3) — nunca hardcode.
        self._client = genai.Client(api_key=get_secret("GEMINI_API_KEY"))

    def available(self) -> bool:
        try:
            get_secret("GEMINI_API_KEY")
            return True
        except Exception:  # noqa: BLE001 — secreto ausente ⇒ no disponible
            return False

    def extract_data(self, file: ExtractionInput) -> ExtractionResult:
        """Envía el documento completo (PDF/imagen) y devuelve el dict canónico."""
        prompt = build_extraction_prompt(hint=file.hint, region_hint=file.region_hint)
        response = self._client.models.generate_content(
            model=self._model,
            contents=[
                self._genai_types.Part.from_bytes(
                    data=file.file_path.read_bytes(), mime_type=file.mime_type
                ),
                prompt,
            ],
            config=self._genai_types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=0.0,          # determinismo en extracción
                response_mime_type="application/json",
            ),
        )
        raw = response.text or ""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise AIProviderError(f"Gemini devolvió JSON inválido: {exc}") from exc

        usage = getattr(response, "usage_metadata", None)
        return ExtractionResult(
            data=data,
            provider=self.name,
            model=self._model,
            prompt_tokens=getattr(usage, "prompt_token_count", 0) or 0,
            completion_tokens=getattr(usage, "candidates_token_count", 0) or 0,
            raw_response=raw,
        )

    def extract_page(self, file: ExtractionInput, page_number: int) -> dict:
        """Extrae una página concreta del PDF (para el consolidador multipágina)."""
        import fitz  # PyMuPDF

        pdf = fitz.open(file.file_path)
        if page_number < 1 or page_number > pdf.page_count:
            raise AIProviderError(f"Página {page_number} fuera de rango (1-{pdf.page_count})")
        page = pdf[page_number - 1]
        png_bytes = page.get_pixmap(dpi=200).tobytes("png")

        prompt = build_extraction_prompt(hint=file.hint, region_hint=file.region_hint,
                                         is_single_page=False)
        response = self._client.models.generate_content(
            model=self._model,
            contents=[
                self._genai_types.Part.from_bytes(data=png_bytes, mime_type="image/png"),
                prompt,
            ],
            config=self._genai_types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=0.0,
                response_mime_type="application/json",
            ),
        )
        try:
            return json.loads(response.text or "{}")
        except json.JSONDecodeError as exc:
            raise AIProviderError(f"Gemini (pág. {page_number}) JSON inválido: {exc}") from exc


def get_settings_model() -> str:
    """Modelo Gemini configurado (settings/env)."""
    from app.core.config import get_settings

    return get_settings().gemini_model

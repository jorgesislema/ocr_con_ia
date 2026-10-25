"""Proveedor Mistral — opción de pago con alta precisión en tablas.

Regla arquitectónica #1: implementación concreta de ``BaseAIProvider``.
Mistral se usa cuando el documento es complejo (tablas densas, PDFs
escaneados de baja calidad, facturas europeas multipágina) gracias a
``mistral-ocr-latest``, que devuelve Markdown con tablas fielmente
reconstruidas, seguido de un LLM Mistral que estructuriza a JSON canónico.
"""
from __future__ import annotations

import base64
import json
import logging
from pathlib import Path

from app.ai.base import AIProviderError, BaseAIProvider, ExtractionInput, ExtractionResult
from app.ai.prompts import SYSTEM_PROMPT, build_extraction_prompt
from app.core.config import get_secret

_log = logging.getLogger("ocr.ai.mistral")

_PROVIDER = "mistral"


class MistralProvider(BaseAIProvider):
    """Extracción vía Mistral OCR + LLM (SDK oficial ``mistralai``).

    Pipeline en dos etapas:
        1. ``ocr.process`` con ``mistral-ocr-latest`` → Markdown (tablas precisas).
        2. ``chat.complete`` con LLM Mistral → JSON canónico desde el Markdown.
    """

    name = _PROVIDER

    def __init__(self) -> None:
        from mistralai import Mistral  # import perezoso

        # API key vía get_secret (regla #3).
        self._client = Mistral(api_key=get_secret("MISTRAL_API_KEY"))
        from app.core.config import get_settings

        settings = get_settings()
        self._ocr_model = settings.mistral_ocr_model
        self._llm_model = settings.mistral_llm_model

    def available(self) -> bool:
        try:
            get_secret("MISTRAL_API_KEY")
            return True
        except Exception:  # noqa: BLE001
            return False

    # ── Etapa 1: OCR a Markdown ───────────────────────────────────────────
    def _ocr_markdown(self, file: ExtractionInput, pages: list[int] | None = None) -> str:
        from mistralai.extra import document_image_chunk  # noqa: F401  (side-effect import)

        file_bytes = file.file_path.read_bytes()
        b64 = base64.b64encode(file_bytes).decode()
        filename = Path(file.file_path).name

        if file.mime_type == "application/pdf":
            document = {"type": "document_url",
                        "document_url": f"data:application/pdf;base64,{b64}"}
        else:
            document = {"type": "image_url", "image_url": f"data:{file.mime_type};base64,{b64}"}

        kwargs: dict = {"model": self._ocr_model, "document": document}
        if pages:
            kwargs["pages"] = pages  # extracción parcial multipágina
        response = self._client.ocr.process(**kwargs)
        return "\n\n".join(page.markdown for page in response.pages)

    # ── Etapa 2: Markdown → JSON canónico ─────────────────────────────────
    def _structure(self, markdown: str, pais: str, columnas: list[str],
                   is_single_page: bool = True) -> dict:
        prompt = build_extraction_prompt(
            pais=pais,
            columnas_solicitadas=columnas,
            is_single_page=is_single_page,
        )
        chat = self._client.chat.complete(
            model=self._llm_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"{prompt}\n\nDocumento OCR (Markdown):\n{markdown}"},
            ],
            temperature=0.0,
            response_format={"type": "json_object"},
        )
        raw = chat.choices[0].message.content or ""
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise AIProviderError(f"Mistral LLM devolvió JSON inválido: {exc}") from exc

    # ── BaseAIProvider ────────────────────────────────────────────────────
    def extract_data(self, file: ExtractionInput) -> ExtractionResult:
        """OCR completo del documento + estructurización a JSON canónico."""
        markdown = self._ocr_markdown(file)
        data = self._structure(markdown, file.pais, file.columnas_solicitadas)
        return ExtractionResult(
            data=data,
            provider=self.name,
            model=self._llm_model,
            raw_response=markdown,   # el Markdown crudo queda auditado
        )

    def extract_page(self, file: ExtractionInput, page_number: int) -> dict:
        """OCR de una sola página + estructurización parcial (multipágina)."""
        markdown = self._ocr_markdown(file, pages=[page_number])
        return self._structure(markdown, file.pais, file.columnas_solicitadas,
                               is_single_page=False)

from __future__ import annotations

import os
import json
import logging
from pathlib import Path
from typing import Optional, Tuple

_log = logging.getLogger("ocr.mistral")

_MISTRAL_MODEL = "mistral-ocr-latest"
_COST_PER_PAGE = {
    "batch": 0.01,            # Lote >1000 páginas
    "standard": 0.02,         # Estándar
    "with_annotations": 0.03, # Con Anotaciones
}
_COST_DEFAULT = 0.02


class MistralOCRBackend:
    """Backend OCR basado en Mistral OCR (mistral-ocr-latest).

    Usa el SDK oficial ``mistralai`` >= 2.0 a través del endpoint /v1/ocr.

    Configuración de API key (en orden de prioridad):
      1. Variable de entorno ``MISTRAL_API_KEY``
      2. Clave ``mistral_api_key`` en ``~/.ocr_glm_config.json``

    Coste: $0.001 por página procesada ($1 / 1000 páginas).
    """

    name = "mistral-ocr-latest"

    def __init__(self) -> None:
        # 1) Variable de entorno
        self.api_key = os.getenv("MISTRAL_API_KEY", "").strip()

        # 2) Fichero de configuración local
        if not self.api_key:
            try:
                cfg_path = Path.home() / ".ocr_glm_config.json"
                if cfg_path.exists():
                    data = json.loads(cfg_path.read_text(encoding="utf-8"))
                    self.api_key = (data.get("mistral_api_key") or "").strip()
            except Exception:
                pass

        if not self.api_key:
            raise RuntimeError(
                "Mistral OCR requiere una API Key.\n"
                "Introdúcela en la pestaña 'Credenciales IA' y pulsa Validar, "
                "o define la variable de entorno MISTRAL_API_KEY."
            )

        from mistralai.client import Mistral  # type: ignore

        self._client = Mistral(api_key=self.api_key)
        self.last_cost: float = 0.0
        self.last_structured: Optional[dict] = None
        self.last_error: str | None = None

    def process_base64(
        self, b64: str, mode: str = "standard"
    ) -> Tuple[str, int, int, float, Optional[dict]]:
        """Envía la imagen (JPEG base64) a Mistral OCR y devuelve
        ``(texto, páginas_procesadas, 0, coste_usd, None)``.

        El parámetro ``mode`` se acepta por compatibilidad con la firma
        estándar del motor, pero Mistral OCR 3 no lo usa.
        """
        image_url = f"data:image/jpeg;base64,{b64}"
        _log.debug(
            "Llamando a Mistral OCR model=%s, longitud image_url=%d",
            _MISTRAL_MODEL,
            len(image_url),
        )

        def _parse_mistral_markdown(pages_obj) -> tuple[str, int, dict]:
            """Convierte la respuesta de Mistral (pages) a texto plano y metadatos.

            Retorna (texto_concat, pages_count, structured_dict)
            structured_dict mínimo: {"text": str, "pages": int, "confidence": float}
            """
            parts: list[str] = []
            pages_count = 0
            for page in pages_obj or []:
                try:
                    md = (getattr(page, "markdown", None) or "").strip()
                except Exception:
                    md = ""
                if md:
                    parts.append(md)
                pages_count += 1
            text = "\n\n".join(parts)
            structured = {
                "text": text,
                "pages": max(pages_count, 1),
                "confidence": 0.0,
            }
            return text or "", max(pages_count, 1), structured

        try:
            response = self._client.ocr.process(
                model=_MISTRAL_MODEL,
                document={"type": "image_url", "image_url": image_url},
            )
        except Exception as exc:
            _log.error("Error en la petición Mistral OCR: %s", exc, exc_info=True)
            err_msg = str(exc)
            if "Status 401" in err_msg or "Unauthorized" in err_msg:
                err_msg = "Mistral OCR respondió 401 Unauthorized. Verifica la API key MISTRAL_API_KEY/mistral_api_key."
            self.last_error = err_msg
            self.last_cost = 0.0
            self.last_structured = {"text": "", "pages": 1, "confidence": 0.0, "error": err_msg}
            # No propagar excepción para que el motor pueda seguir con fallback
            return "", 1, 0, 0.0, {"text": "", "pages": 1, "confidence": 0.0, "error": err_msg}

        # Extraer texto de las páginas devueltas
        try:
            pages = getattr(response, "pages", None) or []
            text, pages_processed, structured = _parse_mistral_markdown(pages)
        except Exception as exc:
            _log.error("Error parseando respuesta Mistral OCR: %s", exc, exc_info=True)
            err_msg = f"Error parseando respuesta Mistral OCR: {exc}"
            self.last_error = err_msg
            self.last_cost = 0.0
            self.last_structured = {"text": "", "pages": 1, "confidence": 0.0, "error": err_msg}
            return "", 1, 0, 0.0, {"text": "", "pages": 1, "confidence": 0.0, "error": err_msg}

        # Coste por página según modo
        try:
            usage_info = getattr(response, "usage_info", None)
            pages_from_usage = int(getattr(usage_info, "pages_processed", None) or pages_processed)
        except Exception:
            pages_from_usage = pages_processed
        cost_per_page = _COST_PER_PAGE.get(mode or "standard", _COST_DEFAULT)
        cost = cost_per_page * max(pages_from_usage, 1)
        self.last_error = None
        self.last_cost = cost
        self.last_structured = structured

        _log.debug(
            "Mistral OCR OK: páginas=%d, caracteres=%d, coste=$%.4f",
            pages_from_usage,
            len(text),
            cost,
        )

        # pt = páginas procesadas (no tokens), ct = 0 (Mistral OCR no usa tokens)
        return text or "", pages_from_usage, 0, cost, structured


# Registrar backend automáticamente bajo el nombre 'mistral-ocr-latest'
try:
    from src.core.ocr_backends import register_backend

    register_backend("mistral-ocr-latest", lambda: MistralOCRBackend())
except Exception:
    # No romper la importación del módulo si el registro falla
    pass

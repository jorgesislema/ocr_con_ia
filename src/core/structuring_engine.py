"""Motor LLM de estructuración — paso 2 del pipeline Mistral OCR.

Convierte texto markdown/plano extraído por OCR en JSON estructurado
usando un LLM configurable por el usuario. Soporta:
- OpenAI GPT-4o / GPT-4
- DeepSeek
- Google Gemini (via endpoint OpenAI-compatible)
- Qwen (Alibaba Cloud DashScope)
- Mistral Large / Mistral chat
- OpenRouter (cualquier modelo disponible)
- Anthropic Claude (via OpenRouter o endpoint propio si instala 'anthropic')
- GLM-4 de ZhipuAI
- Ollama (local)
- LM Studio (local)
- Cualquier endpoint OpenAI-compatible con base_url personalizada

Todos los proveedores OpenAI-compatibles usan el mismo cliente openai.OpenAI
con base_url diferente, lo que minimiza dependencias.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

_log = logging.getLogger("ocr.structuring")

# ── Mapa proveedor → (base_url, default_model) ──────────────────────────────
# Los textos de proveedor coinciden con las opciones de reason_provider_cb en config_panel.
_PROVIDER_DEFAULTS: dict[str, tuple[str, str]] = {
    "openai gpt-4o":                ("https://api.openai.com/v1",                              "gpt-4o"),
    "openai":                       ("https://api.openai.com/v1",                              "gpt-4o"),
    "google gemini flash (gratuito)": ("https://generativelanguage.googleapis.com/v1beta/openai", "gemini-2.0-flash"),
    "google gemini pro":            ("https://generativelanguage.googleapis.com/v1beta/openai", "gemini-2.5-pro-exp-03-25"),
    "gemini":                       ("https://generativelanguage.googleapis.com/v1beta/openai", "gemini-2.0-flash"),
    "deepseek":                     ("https://api.deepseek.com/v1",                            "deepseek-v4-flash"),
    "qwen (alibaba cloud)":         ("https://dashscope.aliyuncs.com/compatible-mode/v1",      "qwen-max"),
    "qwen":                         ("https://dashscope.aliyuncs.com/compatible-mode/v1",      "qwen-max"),
    "mistral large":                ("https://api.mistral.ai/v1",                              "mistral-large-latest"),
    "mistral":                      ("https://api.mistral.ai/v1",                              "mistral-large-latest"),
    "openrouter":                   ("https://openrouter.ai/api/v1",                           "openai/gpt-4o"),
    "anthropic (claude 3.5)":       ("https://openrouter.ai/api/v1",                          "anthropic/claude-3.5-sonnet"),
    "anthropic":                    ("https://openrouter.ai/api/v1",                          "anthropic/claude-3.5-sonnet"),
    "glm-4 (zhipuai)":              ("https://open.bigmodel.cn/api/paas/v4",                   "glm-4"),
    "glm":                          ("https://open.bigmodel.cn/api/paas/v4",                   "glm-4"),
    "ollama (local)":               ("http://localhost:11434/v1",                              "llama3"),
    "ollama":                       ("http://localhost:11434/v1",                              "llama3"),
    "lm studio (local)":            ("http://localhost:1234/v1",                               "local-model"),
    "lm studio":                    ("http://localhost:1234/v1",                               "local-model"),
    "azure openai":                 ("",                                                       "gpt-4o"),  # requiere base_url
}

# Nombre de variables de entorno por proveedor (para auto-detección de keys)
_PROVIDER_ENV: dict[str, str] = {
    "openai gpt-4o":                "OPENAI_API_KEY",
    "openai":                       "OPENAI_API_KEY",
    "google gemini flash (gratuito)": "GEMINI_API_KEY",
    "google gemini pro":            "GEMINI_API_KEY",
    "gemini":                       "GEMINI_API_KEY",
    "deepseek":                     "DEEPSEEK_API_KEY",
    "qwen (alibaba cloud)":         "DASHSCOPE_API_KEY",
    "qwen":                         "DASHSCOPE_API_KEY",
    "mistral large":                "MISTRAL_API_KEY",
    "mistral":                      "MISTRAL_API_KEY",
    "openrouter":                   "OPENROUTER_API_KEY",
    "anthropic (claude 3.5)":       "OPENROUTER_API_KEY",
    "anthropic":                    "OPENROUTER_API_KEY",
    "glm-4 (zhipuai)":              "ZHIPUAI_API_KEY",
    "glm":                          "ZHIPUAI_API_KEY",
    "ollama (local)":               "",
    "ollama":                       "",
    "lm studio (local)":            "",
    "lm studio":                    "",
    "azure openai":                 "AZURE_OPENAI_API_KEY",
}


def _load_env_key(provider_lower: str) -> str:
    """Intenta obtener la API key del entorno o del archivo de configuración."""
    env_var = _PROVIDER_ENV.get(provider_lower, "")
    if env_var:
        key = os.environ.get(env_var, "").strip()
        if key:
            return key
    # Fallback: leer ~/.ocr_glm_config.json
    try:
        cfg_path = Path.home() / ".ocr_glm_config.json"
        if cfg_path.exists():
            data = json.loads(cfg_path.read_text(encoding="utf-8"))
            # Mapear provider → config key
            _cfg_keys = {
                "openai gpt-4o":                "openai_api_key",
                "openai":                       "openai_api_key",
                "google gemini flash (gratuito)": "gemini_api_key",
                "google gemini pro":            "gemini_api_key",
                "gemini":                       "gemini_api_key",
                "deepseek":                     "deepseek_api_key",
                "qwen (alibaba cloud)":         "qwen_api_key",
                "qwen":                         "qwen_api_key",
                "mistral large":                "mistral_api_key",
                "mistral":                      "mistral_api_key",
                "openrouter":                   "openrouter_api_key",
                "anthropic (claude 3.5)":       "openrouter_api_key",
                "anthropic":                    "openrouter_api_key",
                "glm-4 (zhipuai)":              "zhipuai_api_key",
                "glm":                          "zhipuai_api_key",
                "azure openai":                 "azure_openai_api_key",
            }
            cfg_key = _cfg_keys.get(provider_lower, "")
            if cfg_key:
                return (data.get(cfg_key) or "").strip()
    except Exception:
        pass
    return ""


class StructuringEngine:
    """Motor de estructuración de texto OCR mediante LLM.

    Uso::

        engine = StructuringEngine(
            provider="DeepSeek",
            api_key="sk-...",            # opcional si está en entorno
            model="deepseek-v4-flash",       # opcional; usa default del proveedor
            base_url=None,               # opcional; sobreescribe la URL por defecto
        )
        json_text = engine.structure(raw_ocr_text, prompt_with_schema)
    """

    def __init__(
        self,
        provider: str = "DeepSeek",
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self._provider = (provider or "").strip()
        p_lower = self._provider.lower()

        # Resolver base_url y default_model desde el mapa
        default_base, default_model = _PROVIDER_DEFAULTS.get(p_lower, ("", "gpt-4o"))

        self._base_url = (base_url or "").strip() or default_base
        self._model = (model or "").strip() or default_model

        # Resolver API key
        self._api_key = (api_key or "").strip() or _load_env_key(p_lower)

        # Para proveedores locales (Ollama, LM Studio) no se requiere API key
        _local_providers = {"ollama (local)", "ollama", "lm studio (local)", "lm studio"}
        self._requires_key = p_lower not in _local_providers

        if self._requires_key and not self._api_key:
            raise ValueError(
                f"El proveedor '{self._provider}' requiere una API Key para estructuración.\n"
                "Configúrala en la pestaña 'Modelos IA' → 'IA para Razonamiento / Post-procesado'."
            )

        # Crear cliente openai-compatible
        self._client = None
        self._http_fallback = False
        self._init_client()

    def _init_client(self) -> None:
        """Inicializa el cliente OpenAI-compatible."""
        try:
            from openai import OpenAI  # type: ignore
            kwargs: dict = {"api_key": self._api_key or "nokey"}
            if self._base_url:
                kwargs["base_url"] = self._base_url
            self._client = OpenAI(**kwargs)
            self._http_fallback = False
            _log.debug(
                "StructuringEngine: cliente inicializado — proveedor=%s modelo=%s base_url=%s",
                self._provider, self._model, self._base_url,
            )
        except ImportError:
            _log.warning(
                "openai SDK no disponible — usando fallback HTTP para proveedor=%s",
                self._provider,
            )
            self._client = None
            self._http_fallback = True

    def _call_openai_compatible_http(self, system_msg: str, user_msg: str) -> tuple[str, int, int]:
        """Fallback HTTP directo para endpoints OpenAI-compatible."""
        try:
            import requests
        except Exception as exc:
            _log.error("StructuringEngine: requests no disponible para fallback HTTP: %s", exc)
            return "", 0, 0

        base = (self._base_url or "").rstrip("/")
        if not base:
            _log.error("StructuringEngine: base_url vacío para fallback HTTP")
            return "", 0, 0

        url = f"{base}/chat/completions"
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
            "temperature": 0,
        }

        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=90)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            # Loguear el cuerpo de respuesta en errores 4xx para diagnóstico
            body = ""
            try:
                # exc.response puede no existir; intentar usar la respuesta si está
                resp_text = None
                if hasattr(exc, 'response') and getattr(exc, 'response') is not None:
                    try:
                        resp_text = exc.response.text  # type: ignore[attr-defined]
                    except Exception:
                        resp_text = None
                if resp_text is None and 'resp' in locals() and resp is not None:
                    try:
                        resp_text = resp.text
                    except Exception:
                        resp_text = None
                if resp_text:
                    body = resp_text[:1000]
            except Exception:
                body = ""

            # Mensajes y reintentos inteligentes para hints comunes
            extra_hint = ""
            _retry_ok = False
            try:
                low = (body or "").lower()
                if 'model not exist' in low:
                    extra_hint = (
                        " -- respuesta del proveedor indica 'Model Not Exist'. "
                        "Intentando reintentar con el modelo por defecto del proveedor."
                    )
                    # Intentar reintentar con el modelo por defecto si existe y es distinto
                    try:
                        p_lower = (self._provider or "").lower()
                        default_model = _PROVIDER_DEFAULTS.get(p_lower, (None, None))[1]
                        if default_model and default_model != self._model:
                            _log.info("StructuringEngine: reintentando con modelo por defecto '%s' para %s", default_model, self._provider)
                            payload["model"] = default_model
                            try:
                                resp2 = requests.post(url, headers=headers, json=payload, timeout=90)
                                resp2.raise_for_status()
                                data = resp2.json()
                                # actualizar uso del modelo para que el caller lo conozca
                                self._model = default_model
                                _retry_ok = True  # reintento exitoso — usar data del retry
                            except Exception as exc2:
                                # si el reintento falla, registrar y continuar con el error original
                                _log.error("StructuringEngine fallback HTTP reintento falló (%s): %s | body: %s", self._provider, exc2, getattr(exc2, 'response', None) and getattr(exc2.response, 'text', ''))
                    except Exception:
                        pass
                # Mensaje claro si la respuesta indica clave inválida
                if 'incorrect api key' in low or 'invalid_api_key' in low or 'incorrect api key provided' in low:
                    extra_hint = (
                        " -- respuesta del proveedor indica clave API inválida. "
                        "Verifica que la API Key de 'Modelos IA' sea correcta y que el plan del proveedor permita el modelo solicitado."
                    )
            except Exception:
                extra_hint = ""

            if not _retry_ok:
                _log.error(
                    "StructuringEngine fallback HTTP error (%s): %s%s",
                    self._provider,
                    exc,
                    f" | body: {body}" if body else "",
                )
                if extra_hint:
                    _log.error(extra_hint)
                return "", 0, 0
            _log.info("StructuringEngine: reintento exitoso con modelo '%s' para %s — procesando respuesta", self._model, self._provider)

        try:
            message = ((data.get("choices") or [{}])[0] or {}).get("message") or {}
            content = message.get("content") or ""
            if isinstance(content, list):
                parts = []
                for item in content:
                    if isinstance(item, dict):
                        txt = item.get("text")
                        if txt:
                            parts.append(str(txt))
                content = "\n".join(parts)
            result = str(content or "").strip()
            usage = data.get("usage") or {}
            # Fallbacks: DeepSeek/OpenAI-compatible vendors may return different keys
            pt = int(usage.get("prompt_tokens", 0) or 0)
            ct = int(usage.get("completion_tokens", 0) or 0)
            if pt == 0 and ct == 0:
                # try total_tokens fallback
                total = int(usage.get("total_tokens", 0) or 0)
                if total:
                    ct = total
            return result, pt, ct
        except Exception as exc:
            _log.error("StructuringEngine fallback HTTP parse error: %s", exc)
            return "", 0, 0

    def structure(self, raw_text: str, prompt: str) -> tuple[str, int, int]:
        """Envía texto OCR al LLM y devuelve JSON estructurado.

        Returns
        -------
        tuple[str, int, int]
            (texto_json, prompt_tokens, completion_tokens)
        """
        if not raw_text or not raw_text.strip():
            return "", 0, 0

        # Truncar texto excesivamente largo para no superar límites de contexto
        # La mayoría de modelos admiten hasta ~32k tokens; 12k chars ≈ safe limit
        _MAX_CHARS = 12_000
        if len(raw_text) > _MAX_CHARS:
            _log.warning(
                "StructuringEngine: texto truncado de %d a %d chars para %s",
                len(raw_text), _MAX_CHARS, self._provider,
            )
            raw_text = raw_text[:_MAX_CHARS]

        system_msg = (
            "Eres un motor de extracción de datos estructurados. "
            "Solo devuelves el objeto JSON solicitado, sin explicaciones, "
            "sin texto adicional, sin bloques de código markdown."
        )

        # Si el prompt incluye un placeholder para el texto OCR, sustitúyelo en su lugar.
        # Soporta: {markdown_content}, {{ markdown_content }}, {ocr_text}, {text}, {markdown}
        import re as _re
        _PLACEHOLDER_RE = _re.compile(
            r'\{\{?\s*(?:markdown_content|ocr_text|ocr|text|markdown)\s*\}?\}',
            _re.IGNORECASE,
        )
        if _PLACEHOLDER_RE.search(prompt):
            # Reemplazar el placeholder con el texto OCR real
            user_msg = _PLACEHOLDER_RE.sub(raw_text, prompt)
            _log.debug("StructuringEngine: placeholder OCR sustituido en prompt (%d chars)", len(user_msg))
        elif '===BEGIN_OCR===' in prompt:
            # El prompt usa marcadores ===BEGIN_OCR=== / ===END_OCR===
            # Insertar el texto OCR entre esos marcadores al final del prompt
            user_msg = (
                f"{prompt}\n\n"
                f"===BEGIN_OCR===\n{raw_text}\n===END_OCR==="
            )
            _log.debug("StructuringEngine: OCR text wrapped in BEGIN/END markers (%d chars)", len(user_msg))
        else:
            # Comportamiento legado: añadir el texto al final del prompt
            user_msg = (
                f"{prompt}\n\n"
                "El siguiente texto fue extraído por OCR. "
                "Devuelve ÚNICAMENTE el objeto JSON estructurado:\n\n"
                f"{raw_text}"
            )

        try:
            if self._client is not None:
                response = self._client.chat.completions.create(
                    model=self._model,
                    messages=[
                        {"role": "system", "content": system_msg},
                        {"role": "user",   "content": user_msg},
                    ],
                    temperature=0,
                )
                # extraer texto del response
                try:
                    result = (response.choices[0].message.content or "").strip()
                except Exception:
                    try:
                        # fallback a dict-like
                        resp_d = response.to_dict() if hasattr(response, 'to_dict') else None
                        if resp_d:
                            result = str(((resp_d.get('choices') or [{}])[0] or {}).get('message', {}).get('content') or "").strip()
                        else:
                            result = str(getattr(response, 'text', '') or "").strip()
                    except Exception:
                        result = ""

                # intentar extraer usage de varias formas
                pt = 0
                ct = 0
                try:
                    usage = getattr(response, 'usage', None)
                    if usage is None:
                        # try nested in choices
                        try:
                            ch0 = (getattr(response, 'choices', None) or [None])[0]
                            usage = getattr(ch0, 'usage', None) if ch0 is not None else None
                        except Exception:
                            usage = None
                    if usage is not None:
                        pt = int(getattr(usage, 'prompt_tokens', 0) or 0)
                        ct = int(getattr(usage, 'completion_tokens', 0) or 0)
                except Exception:
                    pt = 0
                    ct = 0

                if pt == 0 and ct == 0:
                    # try to_dict/json fallback
                    try:
                        rd = None
                        if hasattr(response, 'to_dict'):
                            rd = response.to_dict()
                        else:
                            try:
                                rd = json.loads(str(response))
                            except Exception:
                                rd = None
                        if isinstance(rd, dict):
                            u = rd.get('usage') or {}
                            pt = int(u.get('prompt_tokens', 0) or 0)
                            ct = int(u.get('completion_tokens', 0) or 0)
                            if pt == 0 and ct == 0:
                                total = int(u.get('total_tokens', 0) or 0)
                                if total:
                                    ct = total
                    except Exception:
                        pass
            elif self._http_fallback:
                result, pt, ct = self._call_openai_compatible_http(system_msg, user_msg)
            else:
                _log.error("StructuringEngine: sin cliente y sin fallback HTTP")
                return "", 0, 0

            if not result:
                return "", 0, 0

            # Quitar bloques ```json ... ``` si el modelo los añade igualmente
            if result.startswith("```"):
                lines = result.splitlines()
                result = "\n".join(
                    ln for ln in lines
                    if not ln.strip().startswith("```")
                ).strip()
            _log.debug(
                "StructuringEngine: OK → %d chars (pt=%d ct=%d)",
                len(result), pt, ct,
            )
            return result, pt, ct
        except Exception as exc:
            _log.error("StructuringEngine: error llamando a %s: %s", self._provider, exc)
            return "", 0, 0

    # ── Métodos de utilidad ──────────────────────────────────────────────────

    @staticmethod
    def from_config(cfg_dict: dict) -> "StructuringEngine | None":
        """Construye un StructuringEngine desde un dict de configuración.

        Devuelve None si no hay proveedor configurado o si falla la inicialización.

        El dict espera las claves::

            {
                "reason_provider": "DeepSeek",
                "reason_api_key":  "sk-...",
                "reason_model":    "deepseek-v4-flash",   # opcional
                "reason_base_url": "",                 # opcional
            }
        """
        provider = (cfg_dict.get("reason_provider") or "").strip()
        if not provider:
            return None
        try:
            return StructuringEngine(
                provider=provider,
                api_key=cfg_dict.get("reason_api_key") or cfg_dict.get("reason_token") or "",
                model=cfg_dict.get("reason_model") or "",
                base_url=cfg_dict.get("reason_base_url") or "",
            )
        except Exception as exc:
            _log.warning("StructuringEngine.from_config: no se pudo crear engine: %s", exc)
            return None

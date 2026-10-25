"""Motor OCR basado en GLM-4V (ZhipuAI).

Lee imágenes (JPEG, PNG, TIFF, BMP) y PDFs, los convierte a base64
y llama a la API vision de GLM para extraer texto estructurado.
"""
from __future__ import annotations

import base64
import io
import json
from pathlib import Path

from PIL import Image
from src.core.prompt_manager import load_render_prompt
import logging

_SUPPORTED_IMAGES = {".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp", ".webp"}

_PROMPT_FACTURAS = (
    "Eres un experto en OCR contable. Extrae los datos de esta factura y devuelve "
    "ÚNICAMENTE un objeto JSON válido con este esquema exacto, sin texto adicional:\n"
    '{"fecha": "", "numero_factura": "", "emisor": "", "identificacion_emisor": "", '
    '"subtotal": 0.0, "impuestos": 0.0, "total": 0.0}\n'
    "Usa null para campos no encontrados. Los valores monetarios deben ser float."
)

_PROMPT_CONTRATOS = (
    "Eres un experto en análisis de documentos legales. "
    "Extrae TODO el texto de este contrato de forma precisa y estructurada. "
    "Preserva párrafos, numeraciones y cláusulas. "
    "Devuelve ÚNICAMENTE el texto extraído, sin explicaciones."
)

_PROMPT_MANUSCRITO = (
    "Eres un experto en reconocimiento de texto manuscrito (HTR). "
    "Transcribe con la mayor fidelidad posible todo el texto escrito a mano en esta imagen. "
    "Indica con [ilegible] las palabras que no puedas reconocer. "
    "Devuelve ÚNICAMENTE la transcripción, sin comentarios."
)

_PROMPT_FOTO_LIBRE = (
    "Eres un experto en OCR. "
    "Extrae TODO el texto visible en esta imagen de forma precisa y completa. "
    "Si hay tablas, represéntalas usando | como separador de columnas. "
    "Si hay campos clave-valor, mantenlos en formato 'Campo: Valor'. "
    "Devuelve ÚNICAMENTE el texto extraído, sin explicaciones."
)

_PROMPT_HISTORICO = (
    "Eres un experto en catalogación de documentos históricos, libros antiguos e ilustraciones. "
    "Analiza la imagen y, según su contenido: "
    "(1) si hay texto impreso o manuscrito, transcríbelo fielmente; "
    "(2) si es una ilustración o lámina artística, descríbela brevemente (personajes, colores, escena); "
    "(3) si la página está completamente en blanco o no contiene información relevante, responde solo: [PÁGINA EN BLANCO]. "
    "Devuelve únicamente el resultado, sin explicaciones adicionales."
)

_PROFILE_PROMPTS: dict[str, str] = {
    "Facturas/Contable":      _PROMPT_FACTURAS,
    "Contratos/Texto":        _PROMPT_CONTRATOS,
    "Manuscrito (HTR)":       _PROMPT_MANUSCRITO,
    "Foto Libre":             _PROMPT_FOTO_LIBRE,
    "Doc. Histórico / Arte":  _PROMPT_HISTORICO,
}

# logger para este módulo
_log = logging.getLogger("ocr.engine")

import os

# límite máximo por lado antes de enviar a la API (puede sobreescribirse con OCR_MAX_PX)
try:
    _MAX_PX = int(os.environ.get('OCR_MAX_PX', '1024'))
except Exception:
    _MAX_PX = 1024


def _pil_to_b64(
    img: Image.Image,
    max_px: int | None = None,
    quality: int | None = None,
) -> str:
    """Convierte una imagen PIL a JPEG base64.

    ``max_px`` y ``quality`` permiten sobreescribir los valores por defecto
    (útil para backends que soportan imágenes de mayor resolución, como Mistral OCR).
    """
    w, h = img.size
    # Prioridad: parámetro explícito > variable de entorno > constante
    if max_px is None:
        try:
            max_px = int(os.environ.get('OCR_MAX_PX', str(_MAX_PX)))
        except Exception:
            max_px = _MAX_PX
    if max(w, h) > max_px:
        scale = max_px / max(w, h)
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    img = img.convert("RGB")
    buf = io.BytesIO()
    q = quality if quality is not None else 60
    img.save(buf, format="JPEG", quality=q)
    # Si el payload supera 150 KB, recomprimir con calidad más baja
    if buf.tell() > 150_000 and q > 35:
        for fallback_q in (45, 30):
            buf2 = io.BytesIO()
            img.save(buf2, format="JPEG", quality=fallback_q)
            if buf2.tell() <= 150_000:
                buf = buf2
                q = fallback_q
                break
    b64_data = base64.b64encode(buf.getvalue()).decode()
    _log.debug("_pil_to_b64: image %dx%d -> JPEG q=%d %d bytes -> b64 %d chars",
               img.size[0], img.size[1], q, buf.tell(), len(b64_data))
    return b64_data


class OCREngine:
    """Motor OCR semántico usando el modelo GLM-4V de ZhipuAI."""

    GLM_MODEL = "glm-4v-flash"

    def __init__(
        self,
        api_key: str,
        profile: str = "Foto Libre",
        expected_keys: list[str] | None = None,
        backend: str | None = None,
        mode: str | None = None,
        use_preprocessor: bool = True,
        upscale: int | None = 1,
        use_cache: bool = True,
        local_conf_threshold: float = 0.8,
        prefer_local: bool = True,
        prompt_template: str | None = None,
        light_mode: bool = False,
        # ── Parámetros para el motor de estructuración (paso 2 del pipeline) ──
        structuring_provider: str | None = None,
        structuring_api_key: str | None = None,
        structuring_model: str | None = None,
        structuring_base_url: str | None = None,
        output_mode: str | None = None,
    ) -> None:
        _LOCAL_BACKENDS = {"ocr-local", "paddle", "paddleocr", "easyocr"}
        _is_local = backend and (
            backend.lower() in _LOCAL_BACKENDS
            or backend.lower().startswith(("paddle", "easyocr"))
        )
        # Backends que tienen su propia gestión de credenciales (no GLM)
        _CLOUD_BACKENDS_NO_GLM = {"mistral-ocr-latest", "google-vision", "google-docs", "openrouter"}
        _needs_glm_key = not _is_local and (backend or "").lower() not in _CLOUD_BACKENDS_NO_GLM
        if not api_key and _needs_glm_key:
            raise ValueError("Se requiere una API Key de ZhipuAI para usar GLM-4V.")
        # Cargar .env si MISTRAL_API_KEY aún no está en el entorno
        if (backend or "").lower() == "mistral-ocr-latest" and not os.environ.get("MISTRAL_API_KEY"):
            try:
                import pathlib as _pl
                _env_path = _pl.Path(__file__).resolve().parent.parent.parent / ".env"
                if _env_path.exists():
                    from dotenv import load_dotenv as _load_dotenv
                    _load_dotenv(dotenv_path=_env_path, override=False)
            except Exception:
                pass
        # Propagar clave Mistral al entorno si el usuario la pasó como api_key
        if api_key and (backend or "").lower() == "mistral-ocr-latest":
            if not os.environ.get("MISTRAL_API_KEY"):
                os.environ["MISTRAL_API_KEY"] = api_key
        # ── Motor de estructuración (segunda IA, texto→JSON) ──────────────────
        self._structuring_engine = None
        if structuring_provider:
            try:
                from src.core.structuring_engine import StructuringEngine
                self._structuring_engine = StructuringEngine(
                    provider=structuring_provider,
                    api_key=structuring_api_key or "",
                    model=structuring_model or "",
                    base_url=structuring_base_url or "",
                )
                _log.debug(
                    "OCREngine: motor de estructuración configurado → %s (%s)",
                    structuring_provider, structuring_model or "default",
                )
            except Exception as _se_exc:
                _log.warning("OCREngine: no se pudo crear StructuringEngine: %s", _se_exc)
                self._structuring_engine = None

        # Mantener compatibilidad con Zhipu GLM y backends pluggables
        self._client = None
        self._backend_name = backend
        self._backend = None
        self._output_mode = str(output_mode or "JSON").strip().lower()
        if backend:
            try:
                from src.core.ocr_backends import get_backend

                # get_backend devuelve una instancia con process_base64(b64)
                self._backend = get_backend(backend)
            except KeyError as _ke:
                _log.error("Backend '%s' no registrado: %s", backend, _ke)
                self._backend = None
            except RuntimeError as _re:
                _log.error("Error al inicializar backend '%s': %s", backend, _re)
                self._backend = None
            except Exception as _exc:
                _log.error("Error inesperado inicializando backend '%s': %s", backend, _exc, exc_info=True)
                self._backend = None
        # Solo crear cliente GLM si el backend seleccionado NO es un cloud propio
        _selected_is_cloud_no_glm = (backend or "").lower() in _CLOUD_BACKENDS_NO_GLM
        if self._backend is None and not _is_local and not _selected_is_cloud_no_glm:
            # Solo instanciar cliente GLM si no es backend local
            try:
                from zhipuai import ZhipuAI
                self._client = ZhipuAI(api_key=api_key, timeout=60.0)
            except Exception as e:
                _log.warning("No se pudo crear cliente ZhipuAI con timeout, reintentando sin: %s", e)
                try:
                    self._client = ZhipuAI(api_key=api_key)
                except Exception:
                    self._client = None

        # Si el usuario definió un esquema dinámico, el prompt se construye
        # a partir de las claves seleccionadas (siempre tiene precedencia sobre
        # el perfil estático).
        if expected_keys:
            _FLOAT_HINTS = {"subtotal", "descuento", "impuestos", "total"}
            # Detectar si el esquema es de tipo histórico/arte
            _ARTE_KEYS = {
                "titulo", "autor", "anio_publicacion", "editorial_imprenta",
                "lugar_publicacion", "descripcion_ilustracion", "texto_visible",
                "dedicatoria", "estado_conservacion", "notas_adicionales",
            }
            is_arte = bool(set(expected_keys) & _ARTE_KEYS)

            if is_arte:
                # Prompt especializado para documentos históricos / arte
                campos_str = ", ".join(expected_keys)
                self._prompt = (
                    "Eres un experto en catalogación de documentos históricos, libros antiguos e ilustraciones. "
                    "Analiza la imagen y extrae los siguientes campos: "
                    f"{campos_str}. "
                    "Devuelve ÚNICAMENTE un objeto JSON válido con esos campos. "
                    "Para 'descripcion_ilustracion' describe lo que ves en la imagen (personajes, colores, escena). "
                    "Para 'texto_visible' transcribe fielmente cualquier texto impreso o manuscrito. "
                    "Si un campo no aplica a esta página, usa null. "
                    "Si la página está en blanco, devuelve {\"texto_visible\": null, \"descripcion_ilustracion\": \"[PÁGINA EN BLANCO]\"}."
                )
            else:
                # Esquema contable/estructurado (comportamiento original)
                json_schema = {
                    k: ("float" if k in _FLOAT_HINTS else "string")
                    for k in expected_keys
                }
                schema_str = json.dumps(json_schema, ensure_ascii=False)
                self._prompt = (
                    "Eres un motor OCR experto en facturas y documentos contables. "
                    "Extrae los campos solicitados de la imagen y devuelve ÚNICAMENTE "
                    "un objeto JSON válido con este esquema exacto, sin texto adicional:\n"
                    f"{schema_str}\n"
                    "Usa null para campos no encontrados. "
                    "Los campos de tipo float deben ser números, no strings. "
                    "No incluyas campos adicionales fuera del esquema."
                )
        else:
            self._prompt = _PROFILE_PROMPTS.get(profile, _PROMPT_FOTO_LIBRE)

        # Si el llamante pasó una plantilla/render ya procesada en `prompt_template`, úsala.
        # Puede ser: (a) el nombre de una plantilla en prompts/, (b) el contenido ya renderizado,
        # o None. Si es nombre de plantilla, intentamos cargarla con `load_render_prompt`.
        try:
            if prompt_template:
                # Si parece contenido (tiene saltos de línea o curlys), lo usamos directamente
                if "\n" in prompt_template or "{" in prompt_template:
                    self._prompt = prompt_template
                    self._prompt_template = "(inline)"
                    _log.debug("OCREngine: usando prompt_template inline (longitud=%d)", len(str(prompt_template)))
                else:
                    # Intentar cargar plantilla por nombre desde prompts/
                    try:
                        rendered, used_name, checksum = load_render_prompt([prompt_template], {})
                        if rendered:
                            self._prompt = rendered
                            self._prompt_template = used_name
                            self._prompt_checksum = checksum
                            _log.debug("OCREngine: cargada plantilla prompt '%s' checksum=%s", used_name, checksum)
                    except Exception:
                        # Si no se encontró la plantilla, mantener el prompt por defecto
                        pass
        except Exception:
            pass

        # ── Opciones de preprocesamiento (siempre presentes, independiente del perfil) ──
        self._use_preprocessor = bool(use_preprocessor)
        self._light_mode       = bool(light_mode)
        try:
            self._upscale = int(upscale or 1)
            if self._upscale < 1:
                self._upscale = 1
        except Exception:
            self._upscale = 1

        # Intentar cargar plantilla desde prompts/ por perfil (si existe)
        # Si se pasó un `prompt_template` explícito al creador, no intentamos
        # cargar plantillas por perfil desde `prompts/` para no sobrescribir
        # lo que el usuario ha pegado en la UI.
        if not prompt_template:
            try:
                # Candidates: specific mapping for known profiles
                profile_key = profile or "default"
                # map known profiles to friendly template names
                profile_map = {
                    "Facturas/Contable": "invoice.tpl",
                    "Contratos/Texto": "contract.tpl",
                }
                tpl_name = profile_map.get(profile_key)
                # fallback to normalized name
                if tpl_name is None:
                    tpl_name = profile_key.lower().replace("/", "_").replace(" ", "_") + ".tpl"
                candidates = [tpl_name, "default.tpl"]
                # context available to templates
                tpl_ctx = {
                    "profile": profile_key,
                    "mode": self._mode or "",
                }
                rendered, used_name, checksum = load_render_prompt(candidates, tpl_ctx)
                # If rendering succeeded, override self._prompt
                if rendered:
                    self._prompt = rendered
                    # store metadata for auditing
                    self._prompt_template = used_name
                    self._prompt_checksum = checksum
            except Exception:
                # silently skip template system if missing or fails
                self._prompt_template = None
                self._prompt_checksum = None
        # modo especial para una única factura
        self._mode = mode or None
        # Cache y política local
        self._CACHE_DIR = Path.home() / ".ocr_glm_cache"
        try:
            self._CACHE_DIR.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        self._use_cache = bool(use_cache)
        try:
            self._local_conf_threshold = float(local_conf_threshold)
        except Exception:
            self._local_conf_threshold = 0.8
        self._prefer_local = bool(prefer_local)
        # Leer modo Mistral desde config de usuario si existe
        try:
            cfg_path = Path.home() / ".ocr_glm_config.json"
            if cfg_path.exists():
                cfg_data = json.loads(cfg_path.read_text(encoding="utf-8"))
                self._mistral_mode = cfg_data.get("mistral_mode", "standard")
            else:
                self._mistral_mode = "standard"
        except Exception:
            self._mistral_mode = "standard"

        # DEBUG: mostrar un preview del prompt usado para depuración (primeros 200 caracteres)
        try:
            if hasattr(self, '_prompt') and self._prompt:
                preview = self._prompt
                if len(preview) > 200:
                    preview = preview[:200] + '...'
                # Reemplazar saltos de línea por \n para que quede en una sola línea de log
                _log.debug("OCREngine prompt preview: %s", preview.replace('\n', '\\n'))
        except Exception:
            pass

    # ── Interfaz pública ──────────────────────────────────────────────────────

    def process_file(self, path: str, mistral_mode: str | None = None) -> tuple[str, int, int, int, float]:
        """Procesa un archivo. Devuelve ``(texto, páginas, prompt_tokens, completion_tokens, confidence)``.

        `mistral_mode` (opcional) permite forzar el modo usado por un backend Mistral
        para este llamado ('standard' o 'with_annotations'). Si se suministra, sobreescribe
        el modo leído desde la configuración del usuario para la llamada concreta.
        """
        ext = Path(path).suffix.lower()
        # optionally override mistral mode for this call
        if mistral_mode is not None:
            try:
                self._mistral_mode = mistral_mode
            except Exception:
                pass

        if ext == ".pdf":
            text, pages, pt, ct, conf = self._process_pdf(path)
            text = self._post_normalize(text)
            return text, pages, pt, ct, conf
        if ext in _SUPPORTED_IMAGES:
            text, pt, ct, conf = self._process_image(path)
            text = self._post_normalize(text)
            return text, 1, pt, ct, conf
        raise ValueError(f"Formato no soportado: {ext}")

    def _parse_invoice_payload(self, text: str) -> dict:
        """Parsea texto de factura a JSON usando el parser adecuado según backend."""
        try:
            backend_name = str(getattr(self, "_backend_name", "") or "").lower()
            if "mistral" in backend_name:
                from src.core.mistral_markdown_parser import MistralMarkdownParser

                parsed = MistralMarkdownParser().parse_invoice(text, country_hint="auto")
                if isinstance(parsed, dict) and parsed:
                    return parsed
        except Exception:
            pass

        try:
            from src.core.invoice_parser import parse_invoice_text

            parsed = parse_invoice_text(text)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def _post_normalize(text: str) -> str:
        """Normalización post-OCR: fechas, monedas y espacios en blanco.

        No lanza excepciones; devuelve el texto original si algo falla.
        """
        try:
            from src.core.post_ocr_normalizer import normalize_text
            return normalize_text(text)
        except Exception:
            try:
                from core.post_ocr_normalizer import normalize_text
                return normalize_text(text)
            except Exception:
                return text

    # ── Internos ──────────────────────────────────────────────────────────────

    def _process_image(self, path: str) -> tuple[str, int, int, float]:
        """Devuelve (texto, prompt_tokens, completion_tokens, confidence)."""
        is_mistral_backend = "mistral" in str(getattr(self, "_backend_name", "") or "").lower()
        img = Image.open(path)
        # Aplicar preprocesado si está habilitado
        try:
            if getattr(self, "_use_preprocessor", False):
                img = self._preprocess_image(img)
        except Exception:
            pass
        # Mistral OCR soporta imágenes de hasta 5 MB → mayor resolución y calidad
        if getattr(self, "_backend_name", "") == "mistral-ocr-latest":
            b64 = _pil_to_b64(img, max_px=2048, quality=85)
        else:
            b64 = _pil_to_b64(img)
        # Si hay backend pluggable (ej. Mistral OCR), usarlo
        if getattr(self, "_backend", None):
            try:
                # Call backend; if it's a Mistral adapter it may accept a mode parameter
                try:
                    _log.debug("Calling backend.process_base64 for image (mode=%s)", getattr(self, '_mistral_mode', 'standard'))
                    try:
                        res = self._backend.process_base64(b64, getattr(self, '_mistral_mode', 'standard'))
                    except TypeError:
                        # older adapters may not accept mode
                        res = self._backend.process_base64(b64)
                    _log.debug("[DEBUG] backend.process_base64 returned for image: %r", res)
                except Exception as e:
                    _log.error("Exception while calling backend.process_base64 for image: %s", e, exc_info=True)
                    res = None

                # Flexible unpacking: support (text, pt, ct) or (text, pt, ct, cost, structured)
                if res is None:
                    _log.error("[ERROR] backend returned None for image, substituting safe empty result")
                    try:
                        print(f"[OCR-DEBUG] backend returned None for image {path}; substituting empty result")
                    except Exception:
                        pass
                    # Garantizar que nunca devolvemos None al código llamante: estructura mínima
                    res = ("", 1, 0, 0.0, {"text": "", "pages": 1, "confidence": 0.0})
                elif isinstance(res, (list, tuple)) and len(res) >= 3:
                    text = res[0]
                    pt = int(res[1] or 0)
                    ct = int(res[2] or 0)
                    # optional cost/structured metadata
                    try:
                        cost = float(res[3]) if len(res) >= 4 else 0.0
                    except Exception:
                        cost = 0.0
                    try:
                        structured = res[4] if len(res) >= 5 else None
                    except Exception:
                        structured = None
                    # expose metadata on backend instance for callers
                    try:
                        setattr(self._backend, 'last_cost', cost)
                        setattr(self._backend, 'last_structured', structured)
                        setattr(self._backend, 'last_mode', getattr(self, '_mistral_mode', 'standard'))
                    except Exception:
                        pass
                # Marcar el backend realmente usado (si la instancia expone `name`)
                try:
                    self._backend_name = getattr(self._backend, "name", self._backend_name) or self._backend_name
                except Exception:
                    pass
                # Si estamos en modo single_invoice, intentar parsear a JSON
                if getattr(self, "_mode", None) == "single_invoice":
                    # Requisito industrial: con Mistral conservar markdown/texto crudo.
                    if is_mistral_backend:
                        return text, pt, ct, 1.0
                    if str(getattr(self, "_output_mode", "json")).startswith("markdown"):
                        return text, pt, ct, 1.0
                    try:
                        parsed = self._parse_invoice_payload(text)
                        return json.dumps(parsed, ensure_ascii=False), pt, ct, 1.0
                    except Exception:
                        return text, pt, ct, 1.0
                # Caso normal: si el prompt espera JSON y el texto no lo contiene,
                # hacer una segunda llamada a GLM para estructurar el texto extraído.
                if is_mistral_backend:
                    return text, pt, ct, 1.0
                structured, spt, sct = self._structure_text_via_glm(text)
                return structured, pt + spt, ct + sct, 1.0
            except Exception:
                    # Si el backend falla, solo usar GLM como fallback si no es un
                    # backend cloud que no usa GLM (Mistral, Google, OpenRouter)
                _is_cloud_backend = (getattr(self, "_backend_name", "") or "").lower() in {
                    "mistral-ocr-latest", "google-vision", "google-docs", "openrouter"
                }
                if _is_cloud_backend:
                    _log.error(
                        "Backend cloud '%s' falló para %s — sin fallback a GLM",
                        getattr(self, "_backend_name", "?"), path,
                    )
                    return "", 0, 0, 0.0
                try:
                    _log.debug("Falling back to GLM for image")
                    text, pt, ct = self._call_glm(b64)
                    _log.debug("[DEBUG] GLM returned for image: text_len=%d, pt=%s, ct=%s", len(text or ""), pt, ct)
                    self._backend_name = "glm"
                    if getattr(self, "_mode", None) == "single_invoice":
                        if str(getattr(self, "_output_mode", "json")).startswith("markdown"):
                            return text, pt, ct, 1.0
                        try:
                            parsed = self._parse_invoice_payload(text)
                            return json.dumps(parsed, ensure_ascii=False), pt, ct, 1.0
                        except Exception:
                            return text, pt, ct, 1.0
                    return text, pt, ct, 1.0
                except Exception:
                    _log.error("GLM fallback also failed for image", exc_info=True)
                    try:
                        print(f"[OCR-DEBUG] GLM fallback failed for image {path}")
                    except Exception:
                        pass
                    # Re-lanzar la excepción original si GLM también falla
                    raise

        # Si no hay backend pluggable pero sí cliente GLM, llamar directamente.
        # Nunca llamar GLM si el backend seleccionado es un proveedor cloud sin GLM.
        _is_cloud_no_glm_direct = (getattr(self, "_backend_name", "") or "").lower() in {
            "mistral-ocr-latest", "google-vision", "google-docs", "openrouter"
        }
        if not _is_cloud_no_glm_direct and getattr(self, "_client", None):
            try:
                _log.debug("No backend pluggable, llamando _call_glm directamente para %s", path)
                t, p, c = self._call_glm(b64)
                return t, p, c, 1.0
            except Exception as e:
                _log.error("GLM directo falló para %s: %s", path, e, exc_info=True)

        # Fallback seguro: si por alguna razón el flujo arriba no devolvió nada,
        # evitar que la función retorne None y provoque un TypeError al desempaquetar.
        _log.warning("_process_image: ningún backend pudo procesar %s — devolviendo vacío", path)
        return "", 0, 0, 0.0

    @staticmethod
    def _is_blank_page(page) -> bool:  # type: ignore[override]
        """Devuelve True si la página no tiene texto ni contenido visual significativo.

        Se considera en blanco cuando:
        - No tiene texto extraíble con PyMuPDF, Y
        - La imagen renderizada tiene varianza de píxeles < 50 (casi uniforme).
        """
        import numpy as np
        # Import fitz locally to ensure name is defined even if callers import
        # PyMuPDF inside other methods (imports inside functions are local).
        try:
            import fitz  # pymupdf
        except Exception:
            # If PyMuPDF not available, assume page is not blank to avoid false skips
            return False

        # Check for extractable text first
        try:
            text = page.get_text("text") or ""
            if text.strip():
                return False
        except Exception:
            # If text extraction fails, fall back to image variance check
            pass

        # Renderizar a baja resolución solo para comprobar varianza
        try:
            pix = page.get_pixmap(matrix=fitz.Matrix(0.25, 0.25))
            arr = np.frombuffer(pix.samples, dtype=np.uint8)
            return float(arr.var()) < 50.0
        except Exception:
            # Si el renderizado falla, consideramos que la página no está en blanco
            return False

    def _preprocess_image(self, pil_img: Image.Image) -> Image.Image:
        """Preprocesamiento adaptativo: delega en preprocessor.adaptive_preprocess.

        Construye el dict ``config`` a partir de los atributos de la instancia para
        que el pipeline decida qué filtros aplicar:
        - ``upscale``     → factor forzado por el usuario (upscale_cb).
        - ``light_mode``  → salta el denoise (modo rápido).
        El pipeline aplica deskew, denoise, clahe/gamma y upscale inteligente solo
        cuando los umbrales de calidad lo requieren.
        """
        try:
            from src.core.preprocessor import adaptive_preprocess
        except Exception:
            try:
                from core.preprocessor import adaptive_preprocess
            except Exception:
                return pil_img

        config = {
            "upscale":    getattr(self, "_upscale", 1) or 1,
            "light_mode": getattr(self, "_light_mode", False),
        }
        try:
            return adaptive_preprocess(pil_img, config)
        except Exception:
            return pil_img

    def _local_ocr(self, pil_img: Image.Image) -> tuple[str, int, int]:
        """Intentar OCR local con PaddleOCR o EasyOCR según `self._backend_name`.

        Retorna (texto, prompt_tokens, completion_tokens, avg_confidence).
        """
        try:
            import numpy as _np
        except Exception:
            return "", 0, 0, 0.0

        np_img = _np.array(pil_img.convert("RGB"))[:, :, ::-1]
        txt = ""
        confidences: list[float] = []
        try:
            if (getattr(self, "_backend_name", "") or "").lower().startswith("paddle"):
                try:
                    from paddleocr import PaddleOCR
                    # Inicializar OCR (idioma autodetectable, usar ang/esp según disponibilidad)
                    ocr = PaddleOCR(use_angle_cls=True, lang="en")
                    res = ocr.ocr(np_img, cls=True)
                    lines = []
                    for seg in res:
                        for line in seg:
                            try:
                                # line[1] may be (text, confidence)
                                t = line[1][0] if isinstance(line[1], (list, tuple)) else str(line[1])
                                lines.append(t)
                                try:
                                    score = float(line[1][1])
                                    confidences.append(score)
                                except Exception:
                                    pass
                            except Exception:
                                pass
                    txt = "\n".join(lines)
                except Exception:
                    txt = ""
            elif (getattr(self, "_backend_name", "") or "").lower().startswith("easyocr"):
                try:
                    import easyocr
                    reader = easyocr.Reader(["en"], gpu=False)
                    res = reader.readtext(np_img)
                    lines = []
                    for r in res:
                        try:
                            # r -> (bbox, text, confidence)
                            lines.append(r[1])
                            try:
                                confidences.append(float(r[2]))
                            except Exception:
                                pass
                        except Exception:
                            pass
                    txt = "\n".join(lines)
                except Exception:
                    txt = ""
        except Exception:
            txt = ""

        if not txt:
            return "", 0, 0, 0.0
        # Estimar tokens aproximados
        prompt_tokens = max(1, len(txt) // 4)
        completion_tokens = 0
        avg_conf = float(sum(confidences) / len(confidences)) if confidences else 0.75
        return txt, prompt_tokens, completion_tokens, avg_conf

    def _checksum_image(self, pil_img: Image.Image) -> str:
        try:
            import hashlib

            buf = io.BytesIO()
            pil_img.convert("RGB").save(buf, format="JPEG", quality=85)
            h = hashlib.sha256(buf.getvalue()).hexdigest()
            return h
        except Exception:
            return ""

    def _cache_get(self, checksum: str) -> dict | None:
        try:
            if not checksum:
                return None
            path = self._CACHE_DIR / f"{checksum}.json"
            if not path.exists():
                return None
            with open(path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            return None

    def _cache_set(self, checksum: str, data: dict) -> None:
        try:
            if not checksum:
                return
            path = self._CACHE_DIR / f"{checksum}.json"
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False)
        except Exception:
            pass

    def _process_pdf(self, path: str) -> tuple[str, int, int, int]:
        """Devuelve (texto, páginas, prompt_tokens, completion_tokens)."""
        is_mistral_backend = "mistral" in str(getattr(self, "_backend_name", "") or "").lower()
        try:
            import fitz  # pymupdf
        except Exception:
            raise RuntimeError("PyMuPDF (fitz) no está disponible para procesar PDFs")

        pages_text: list[str] = []
        total_prompt = 0
        total_completion = 0
        confidences: list[float] = []

        doc = fitz.open(path)
        try:
            for i, page in enumerate(doc):
                # 1) Intentar usar texto embebido en la página (si existe) — evita OCR y costes
                try:
                    page_text = (page.get_text("text") or "").strip()
                except Exception:
                    page_text = ""

                if page_text and len(page_text) > 30:
                    pages_text.append(f"--- Página {i + 1} (texto embebido) ---\n{page_text}")
                    continue

                # ── Omitir páginas en blanco (ahorra tokens)
                if self._is_blank_page(page):
                    pages_text.append(f"--- Página {i + 1} ---\n[PÁGINA EN BLANCO — omitida]")
                    continue

                # Convertir cada página a PNG a 300 DPI y guardarla en carpeta junto al PDF
                try:
                    dpi = 300
                    scale = dpi / 72.0
                    mat = fitz.Matrix(scale, scale)
                    images_dir = Path(path).parent / (Path(path).stem + "_images")
                    images_dir.mkdir(parents=True, exist_ok=True)
                    pix = page.get_pixmap(matrix=mat, alpha=False)
                    png_path = images_dir / f"page_{i+1:04d}.png"
                    try:
                        pix.save(str(png_path))
                    except Exception:
                        pass
                except Exception:
                    mat = fitz.Matrix(2.0, 2.0)
                    pix = page.get_pixmap(matrix=mat)

                # Crear PIL Image desde pixmap
                try:
                    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                except Exception:
                    buf = io.BytesIO(pix.tobytes())
                    img = Image.open(buf).convert("RGB")
                # Aplicar preprocesado si está habilitado
                try:
                    if getattr(self, "_use_preprocessor", False):
                        img = self._preprocess_image(img)
                except Exception:
                    pass

                # Mayor calidad para Mistral OCR
                if getattr(self, "_backend_name", "") == "mistral-ocr-latest":
                    b64 = _pil_to_b64(img, max_px=2048, quality=85)
                else:
                    b64 = _pil_to_b64(img)
                # Intentar usar cache por checksum
                checksum = self._checksum_image(img)
                cached = None
                if getattr(self, "_use_cache", False):
                    try:
                        cached = self._cache_get(checksum)
                    except Exception:
                        cached = None

                if cached:
                    text = cached.get("text", "")
                    pt = int(cached.get("prompt_tokens", 0) or 0)
                    ct = int(cached.get("completion_tokens", 0) or 0)
                    # marcar backend usado si está en cache
                    try:
                        self._backend_name = cached.get("backend", self._backend_name)
                    except Exception:
                        pass
                    try:
                        conf = float(cached.get("confidence", 1.0) or 1.0)
                    except Exception:
                        conf = 1.0
                    confidences.append(conf)
                else:
                    # Preferir backend registrado, con fallback a GLM
                    if getattr(self, "_backend", None):
                        try:
                            # algunos adaptadores aceptan un modo (p.ej. Mistral); manejar firma antigua
                            try:
                                _log.debug("Calling backend.process_base64 for PDF page (mode=%s)", getattr(self, '_mistral_mode', 'standard'))
                                try:
                                    res = self._backend.process_base64(b64, getattr(self, '_mistral_mode', 'standard'))
                                except TypeError:
                                    res = self._backend.process_base64(b64)
                                _log.debug("[DEBUG] backend.process_base64 returned for PDF page: %r", res)
                            except Exception:
                                _log.error("Exception while calling backend.process_base64 for PDF page", exc_info=True)
                                res = None

                            # Si el backend devolvió None o un valor inesperado, fallback a GLM
                            if res is None:
                                _log.error("[ERROR] backend returned None for PDF page, substituting safe empty result")
                                res = ("", 1, 0, 0.0, {"text": "", "pages": 1, "confidence": 0.0})
                            # soportar tanto (text, pt, ct) como (text, pt, ct, cost, structured)
                            if isinstance(res, (list, tuple)) and len(res) >= 3:
                                text = res[0]
                                pt = int(res[1] or 0)
                                ct = int(res[2] or 0)
                                try:
                                    self._backend_name = getattr(self._backend, "name", self._backend_name) or self._backend_name
                                except Exception:
                                    pass
                            else:
                                # no es iterable esperado: intentar llamar a GLM
                                _log.debug("Backend response unexpected for PDF page, falling back to GLM")
                                _log.debug("Falling back to GLM for PDF page")
                                text, pt, ct = self._call_glm(b64)
                                _log.debug("[DEBUG] GLM returned for PDF page: text_len=%d, pt=%s, ct=%s", len(text or ""), pt, ct)
                                self._backend_name = "glm"
                        except Exception:
                            text, pt, ct = self._call_glm(b64)
                            self._backend_name = "glm"
                    else:
                        # Si se seleccionó un backend local como paddle-ocr o easyocr, intentar OCR local
                        if (getattr(self, "_backend_name", None) or "").lower().startswith("paddle") or (
                            (getattr(self, "_backend_name", None) or "").lower().startswith("easyocr")
                        ):
                            text, pt, ct, conf = self._local_ocr(img)
                            # si el resultado local es insuficiente, fallback a GLM
                            try:
                                if not text:
                                    raise RuntimeError("empty local result")
                                accept_local = False
                                if conf >= getattr(self, "_local_conf_threshold", 0.8):
                                    accept_local = True
                                elif getattr(self, "_prefer_local", False) and conf >= max(0.5, getattr(self, "_local_conf_threshold", 0.8) - 0.15):
                                    accept_local = True
                                if accept_local:
                                    try:
                                        self._backend_name = (self._backend_name or "local")
                                    except Exception:
                                        pass
                                else:
                                    text, pt, ct = self._call_glm(b64)
                                    self._backend_name = "glm"
                            except Exception:
                                text, pt, ct = self._call_glm(b64)
                                self._backend_name = "glm"
                            # registrar confianza de la página
                            try:
                                confidences.append(float(conf or 0.0))
                            except Exception:
                                pass
                        else:
                            text, pt, ct = self._call_glm(b64)

                    # Guardar en cache si corresponde
                    try:
                        if getattr(self, "_use_cache", False) and checksum:
                            self._cache_set(checksum, {
                                "text": text,
                                "prompt_tokens": int(pt or 0),
                                "completion_tokens": int(ct or 0),
                                "backend": getattr(self, "_backend_name", "glm"),
                                "confidence": float(conf if 'conf' in locals() else 1.0),
                            })
                    except Exception:
                        pass

                total_prompt += int(pt or 0)
                total_completion += int(ct or 0)
                pages_text.append(f"--- Página {i + 1} ---\n{text}")
                # si no añadimos confianza de la página antes, intentar inferirla
                try:
                    if 'conf' in locals() and isinstance(conf, (int, float)):
                        confidences.append(float(conf))
                except Exception:
                    pass
        finally:
            try:
                doc.close()
            except Exception:
                pass

        try:
            avg_conf = float(sum(confidences) / len(confidences)) if confidences else 1.0
        except Exception:
            avg_conf = 1.0
        full_text = "\n\n".join(pages_text)

        mode = getattr(self, "_mode", None)
        if mode == "single_invoice":
            if is_mistral_backend:
                return full_text, 1, total_prompt, total_completion, avg_conf
            if str(getattr(self, "_output_mode", "json")).startswith("markdown"):
                return full_text, 1, total_prompt, total_completion, avg_conf
            try:
                parsed = self._parse_invoice_payload(full_text)
                return json.dumps(parsed, ensure_ascii=False), 1, total_prompt, total_completion, avg_conf
            except Exception:
                pass
        if mode == "consolidate_invoices":
            if is_mistral_backend:
                return full_text, 1, total_prompt, total_completion, avg_conf
            try:
                from src.core.invoice_consolidator import consolidate_invoices_text
                parsed = consolidate_invoices_text(full_text)
                return json.dumps(parsed, ensure_ascii=False), 1, total_prompt, total_completion, avg_conf
            except Exception:
                pass

        if is_mistral_backend:
            return full_text, len(pages_text), total_prompt, total_completion, avg_conf
        if str(getattr(self, "_output_mode", "json")).startswith("markdown"):
            return full_text, len(pages_text), total_prompt, total_completion, avg_conf

        # Si el backend extrajo texto plano (ej. Mistral OCR) y el prompt espera JSON,
        # segunda llamada a GLM para estructurar el texto acumulado de todas las páginas.
        structured_text, spt, sct = self._structure_text_via_glm(full_text)
        return structured_text, len(pages_text), total_prompt + spt, total_completion + sct, avg_conf

    def _call_glm(self, b64: str) -> tuple[str, int, int]:
        # Construir mensajes nuevos por llamada (aislamiento de contexto)
        system_prompt = "Eres un motor OCR. Responde solo lo que se pide, sin contexto persistente."
        # El mensaje de usuario contiene primero la imagen y luego el prompt específico
        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                    {"type": "text", "text": self._prompt},
                ],
            },
        ]

        try:
            # Si usamos Zhipu client, llamamos por la vía habitual
            if self._client is None:
                raise RuntimeError("No GLM client available for _call_glm")
            response = self._client.chat.completions.create(
                model=self.GLM_MODEL,
                messages=messages,
            )
            text = response.choices[0].message.content.strip()
            usage = getattr(response, "usage", None) or {}
            prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
            completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
            return text, prompt_tokens, completion_tokens
        finally:
            # Limpiar variables sensibles y de contexto para prevenir "context bleeding"
            try:
                del messages
            except Exception:
                pass
            try:
                del response
            except Exception:
                pass

    def _structure_text_via_glm(self, raw_text: str) -> tuple[str, int, int]:
        """Paso 2 del pipeline: estructurar texto OCR en JSON via LLM configurable.

        Prioridad de motor:
        1. self._structuring_engine  → proveedor configurado por el usuario
           (DeepSeek, GPT-4o, Gemini, Qwen, OpenRouter, Mistral, Ollama…)
        2. Fallback: cliente GLM propio (self._client) si no hay proveedor externo

        Solo actúa si:
        - El prompt activo menciona "JSON".
        - El texto NO contiene ya un JSON parseable.

        Devuelve (texto_resultado, prompt_tokens, completion_tokens).
        """
        # La etapa 2 debe aceptar texto OCR en markdown o JSON y estructurarlo
        # según el prompt del proyecto. No se debe desactivar por output_mode.

        prompt = getattr(self, "_prompt", "") or ""

        # Solo actuar si el prompt espera JSON
        if "JSON" not in prompt and "json" not in prompt.lower():
            return raw_text, 0, 0

        # Si el texto ya contiene un JSON válido, no hace falta estructurar
        if raw_text and "{" in raw_text:
            start = raw_text.find("{")
            try:
                end = raw_text.rfind("}") + 1
                if end > start:
                    json.loads(raw_text[start:end])
                    _log.debug("_structure_text_via_glm: texto ya contiene JSON válido, saltando")
                    return raw_text, 0, 0
            except Exception:
                pass  # JSON malformado → necesita estructuración igualmente

        # ── Opción 1: usar StructuringEngine configurado por el usuario ──────
        se = getattr(self, "_structuring_engine", None)
        if se is not None:
            _log.debug(
                "_structure_text_via_glm: usando StructuringEngine (%s) para %d chars",
                getattr(se, "_provider", "?"), len(raw_text),
            )
            try:
                result, pt, ct = se.structure(raw_text, prompt)
                return result, pt, ct
            except Exception as exc:
                _log.warning("_structure_text_via_glm: StructuringEngine falló: %s — probando GLM fallback", exc)

        # ── Opción 2: fallback a GLM propio si hay cliente disponible ────────
        if not getattr(self, "_client", None):
            _log.debug("_structure_text_via_glm: sin motor de estructuración ni cliente GLM, devolviendo texto original")
            return raw_text, 0, 0

        structuring_content = (
            f"{prompt}\n\n"
            "El siguiente texto fue extraído por OCR. "
            "Devuelve ÚNICAMENTE el JSON estructurado, sin texto adicional:\n\n"
            f"{raw_text}"
        )
        messages = [
            {
                "role": "system",
                "content": (
                    "Eres un motor de estructuración OCR. "
                    "Solo devuelves el objeto JSON solicitado, sin explicaciones."
                ),
            },
            {"role": "user", "content": structuring_content},
        ]
        try:
            _log.debug(
                "_structure_text_via_glm: fallback GLM para estructurar %d chars",
                len(raw_text),
            )
            response = self._client.chat.completions.create(
                model=self.GLM_MODEL,
                messages=messages,
            )
            structured = response.choices[0].message.content.strip()
            usage = getattr(response, "usage", None) or {}
            pt = int(getattr(usage, "prompt_tokens", 0) or 0)
            ct = int(getattr(usage, "completion_tokens", 0) or 0)
            _log.debug(
                "_structure_text_via_glm: GLM fallback OK → %d chars (pt=%d ct=%d)",
                len(structured), pt, ct,
            )
            return structured, pt, ct
        except Exception as exc:
            _log.error("_structure_text_via_glm: GLM fallback también falló: %s", exc)
            return raw_text, 0, 0
        finally:
            try:
                del messages
            except Exception:
                pass


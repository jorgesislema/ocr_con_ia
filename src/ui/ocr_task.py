"""OcrTask — QRunnable para procesamiento paralelo de un documento OCR.

Diseñado para ejecutarse en QThreadPool (máx 3 concurrentes).
Comunica resultados de vuelta al OcrWorker a través de una cola thread-safe,
evitando el uso de pyqtSignal cross-thread (que requeriría QObject + moveToThread).

Garantías de diseño
-------------------
* Siempre deposita exactamente 1 resultado en *result_queue*, incluso en error.
* Respeta *pause_event* antes de comenzar el trabajo pesado.
* Comprueba *stop_flag* antes de iniciar y durante la espera de rate-limit.
* Crea un OCREngine propio (aislamiento de hilo, sin estado compartido).
"""
from __future__ import annotations

import json
import logging
import os
import queue
import threading
from pathlib import Path

from PyQt6.QtCore import QRunnable

_log = logging.getLogger("ocr.task")


class OcrTask(QRunnable):
    """Procesa un único archivo OCR y deposita el resultado en *result_queue*."""

    def __init__(
        self,
        index: int,
        path: str,
        engine_config: dict,
        result_queue: queue.Queue,
        stop_flag: list,          # [bool] — mutable ref compartida con OcrWorker
        pause_event: threading.Event,
        include_images: bool,
        output_dir: str,
        expected_keys: list | None = None,
    ) -> None:
        super().__init__()
        self.setAutoDelete(True)
        self._index = index
        self._path = path
        self._engine_config = engine_config
        self._result_queue = result_queue
        self._stop_flag = stop_flag
        self._pause_event = pause_event
        self._include_images = include_images
        self._output_dir = output_dir
        self._expected_keys = list(expected_keys or [])

    # ── QRunnable entry point ──────────────────────────────────────────────────

    def run(self) -> None:  # noqa: PLR0912, PLR0915
        idx = self._index
        path = self._path
        filename = os.path.basename(path)

        # 1. Respetar pausa antes de iniciar trabajo pesado —————————————————
        #    Si el pool tiene 3 threads y todos bloquean aquí, ninguna nueva
        #    tarea puede arrancar: el efecto pause es correcto y limpio.
        self._pause_event.wait()

        if self._stop_flag[0]:
            self._result_queue.put(self._make_cancelled(idx, filename))
            return

        # 2a. Enrutamiento IA opcional (smart_routing) ———————————————————————
        _routing: dict = {}
        if self._engine_config.get("smart_routing", False):
            try:
                from src.core.content_router import route_content
                _routing = route_content(
                    doc_hint=filename,
                    path=path,
                    override_backend=self._engine_config.get("backend"),
                    override_upscale=self._engine_config.get("upscale"),
                )
                _log.info(
                    "[Router] %s → %s (conf=%.2f) backend=%s upscale=%s",
                    filename,
                    _routing.get("content_type", "?"),
                    _routing.get("confidence", 0.0),
                    _routing.get("backend", "?"),
                    _routing.get("upscale", "?"),
                )
            except Exception as _re:
                _log.warning("content_router falló (%s) — usando config base", _re)

        # 2b. Construir motor OCR (un engine por tarea = seguridad de hilo) ——
        try:
            engine = self._build_engine(_routing)
        except Exception as exc:
            _log.error("No se pudo crear OCREngine para '%s': %s", filename, exc)
            self._result_queue.put({
                "index": idx, "filename": filename, "status": "Error",
                "text": f"[ERROR motor] {exc}", "pages": 0, "confidence": 0.0,
                "prompt_tokens": 0, "completion_tokens": 0, "images": [],
                "backend": self._engine_config.get("backend", "glm"),
            })
            return

        # 3. Extraer imágenes asociadas (PDF→PNG / copiar imagen) ————————————
        images_for_doc: list[str] = []
        try:
            images_for_doc = self._extract_images(path)
        except Exception as exc:
            _log.warning("Error extrayendo imágenes de '%s': %s", filename, exc)

        # 4. OCR con rate-limiter y fallback local — robust logging y validación
        text: str = ""
        pages: int = 0
        pt: int = 0
        ct: int = 0
        confidence: float = 0.0
        status: str = "Error"

        try:
            # usar wrapper para capturar y mostrar el resultado devuelto por el engine
            try:
                result = self._call_ocr(engine, path)
            except Exception as exc:
                _log.error("Error llamando al motor para '%s': %s", filename, exc, exc_info=True)
                raise

            _log.debug("[DEBUG] engine.process_file result for %s: %r", filename, result)
            # comprobar None o formato inesperado
            if result is None:
                _log.error("[ERROR] engine.process_file returned None for %s", filename)
                raise RuntimeError(f"process_file returned None for {filename}")

            # aceptar tuplas/lists de longitud 5 o 4 (imagen vs pdf)
            if isinstance(result, (list, tuple)):
                if len(result) == 5:
                    text, pages, pt, ct, confidence = result
                elif len(result) == 4:
                    # (text, pt, ct, confidence) → imagen única
                    text, pt, ct, confidence = result
                    pages = 1
                else:
                    _log.error("[ERROR] Unexpected result shape from engine for %s: %r", filename, result)
                    raise RuntimeError("Unexpected result shape from engine")
            else:
                _log.error("[ERROR] engine.process_file returned non-iterable for %s: %r", filename, result)
                raise RuntimeError("engine.process_file returned non-iterable result")

            status = "Procesado"
        except Exception as exc:
            _log.error("Error procesando '%s': %s", filename, exc, exc_info=True)
            text = f"[ERROR] {exc}"

        # Determinar el backend efectivo (se usa para auditoría y para QA relajado)
        backend_name = (
            getattr(engine, "_backend_name", None)
            or self._engine_config.get("backend", "glm")
        )

        # Si no se extrajo texto, marcar el documento como Error con mensaje útil.
        try:
            if status == "Procesado" and not str(text or "").strip():
                backend_err = ""
                try:
                    _be = getattr(engine, "_backend", None)
                    backend_err = str(getattr(_be, "last_error", "") or "").strip()
                except Exception:
                    backend_err = ""

                status = "Error"
                if backend_err:
                    text = f"[ERROR OCR] {backend_err}"
                else:
                    text = f"[ERROR OCR] No se extrajo texto del documento ({backend_name})."
        except Exception:
            pass

        # 5. QA pre-exportación (no interrumpe el flujo si falla) ————————————
        if status == "Procesado" and "mistral" in str(backend_name).lower():
            text = self._try_parse_mistral_markdown(engine, text)

        if status == "Procesado":
            try:
                from src.core.qa_checker import validate_extraction
                vr = validate_extraction(
                    {"text": text, "filename": filename, "status": status, "backend": backend_name},
                    self._expected_keys or None,
                )
                for w in vr.get("warnings", []):
                    _log.warning("[QA] %s: %s", filename, w)
                for e in vr.get("errors", []):
                    _log.error("[QA] %s: %s", filename, e)
            except Exception:
                pass

        backend_name = (
            getattr(engine, "_backend_name", None)
            or self._engine_config.get("backend", "glm")
        )

        # 6. Auditoría de trazabilidad ————————————————————————————————————————
        try:
            from src.core.audit import log_extraction
            log_extraction(
                job_id=str(getattr(self, "_job_id", "") or ""),
                doc_path=path,
                result={"text": text, "confidence": confidence, "status": status},
                model=backend_name,
                extra={
                    "content_type": _routing.get("content_type", "unknown"),
                    "router_conf":  _routing.get("confidence", 0.0),
                    "pages":        pages,
                },
            )
        except Exception as _ae:
            _log.debug("audit.log_extraction falló: %s", _ae)

        # collect optional backend billing/structured metadata if present
        cost_usd = None
        mode = None
        structured = None
        try:
            be = getattr(engine, '_backend', None)
            if be is not None:
                cost_usd = getattr(be, 'last_cost', None)
                mode = getattr(be, 'last_mode', None)
                structured = getattr(be, 'last_structured', None)
        except Exception:
            pass

        payload = {
            "index":             idx,
            "filename":          filename,
            "status":            status,
            "text":              text,
            "pages":             pages,
            "confidence":        confidence,
            "prompt_tokens":     pt,
            "completion_tokens": ct,
            "images":            images_for_doc,
            "backend":           backend_name,
            "content_type":      _routing.get("content_type", ""),
        }
        if cost_usd is not None:
            try:
                payload["cost_usd"] = float(cost_usd)
            except Exception:
                payload["cost_usd"] = cost_usd
        if mode is not None:
            payload["mode"] = mode
        if structured is not None:
            payload["structured"] = structured

        self._result_queue.put(payload)

    def _try_parse_mistral_markdown(self, engine, markdown_text: str) -> str:
        """Intenta estructurar markdown de Mistral a JSON con parser especializado.

        Si el parser no logra `numero_factura`, usa fallback al estructurador LLM.
        """
        # Requisito industrial: con Mistral no convertir a JSON en esta etapa.
        return markdown_text

    def _call_structurer_llm(self, engine, markdown_text: str) -> dict:
        """Fallback de estructuración usando el motor configurado en OCREngine."""
        try:
            if hasattr(engine, "_structure_text_via_glm"):
                structured_text, _pt, _ct = engine._structure_text_via_glm(markdown_text)
            else:
                return {}

            if not structured_text:
                return {}

            start = structured_text.find("{")
            end = structured_text.rfind("}") + 1
            if start >= 0 and end > start:
                parsed = json.loads(structured_text[start:end])
                return parsed if isinstance(parsed, dict) else {}
        except Exception as exc:
            _log.warning("Fallback estructurador LLM falló para '%s': %s", self._path, exc)
        return {}

    # ── Engine creation ────────────────────────────────────────────────────────

    def _build_engine(self, routing: dict | None = None):
        from src.core.ocr_engine import OCREngine
        cfg = self._engine_config
        r = routing or {}
        # Valores del router tienen precedencia si smart_routing activo
        # Permitir forzar Mistral mediante config: `force_mistral: True`
        if cfg.get("force_mistral", False):
            backend = "mistral"
        else:
            backend = r.get("backend") or cfg.get("backend", "glm")
        upscale    = r.get("upscale")    if r.get("upscale") is not None else cfg.get("upscale", 1)
        preprocess = r.get("preprocess") if "preprocess" in r else cfg.get("use_preprocessor", True)
        light      = r.get("light_mode") if "light_mode" in r else cfg.get("light_mode", False)
        prompt     = cfg.get("prompt_template")
        if r.get("prompt_key") and not prompt:
            # Intentar cargar desde prompt_manager si hay clave de router
            try:
                from src.core.prompt_manager import auto_select_prompt
                prompt = auto_select_prompt(r["prompt_key"])
            except Exception:
                pass
        return OCREngine(
            cfg["api_key"],
            profile=cfg.get("profile", "Facturas/Contable"),
            expected_keys=self._expected_keys or None,
            backend=backend,
            mode=cfg.get("mode"),
            use_preprocessor=bool(preprocess),
            upscale=int(upscale or 1),
            use_cache=cfg.get("use_cache", True),
            local_conf_threshold=cfg.get("local_conf_threshold", 0.8),
            prefer_local=cfg.get("prefer_local", True),
            light_mode=bool(light),
            prompt_template=prompt,
            structuring_provider=cfg.get("structuring_provider") or None,
            structuring_api_key=cfg.get("structuring_api_key") or None,
            structuring_model=cfg.get("structuring_model") or None,
            structuring_base_url=cfg.get("structuring_base_url") or None,
            output_mode=cfg.get("ocr_output_mode") or "JSON",
        )

    def _build_local_engine(self):
        """Engine de backup cuando la API expira cuota (fallback 429)."""
        from src.core.ocr_engine import OCREngine
        cfg = self._engine_config
        return OCREngine(
            cfg["api_key"],
            profile=cfg.get("profile", "Facturas/Contable"),
            expected_keys=self._expected_keys or None,
            backend="ocr-local",
            use_preprocessor=cfg.get("use_preprocessor", True),
            upscale=cfg.get("upscale", 1),
            use_cache=cfg.get("use_cache", True),
        )

    # ── OCR call with rate-limiter ─────────────────────────────────────────────

    def _call_ocr(self, engine, path: str) -> tuple:
        """Llama a engine.process_file con retry exponencial y fallback local."""
        try:
            from src.core.rate_limiter import RateLimiter
        except ImportError:
            return engine.process_file(path)

        rl = RateLimiter(
            local_conf_threshold=self._engine_config.get("local_conf_threshold", 0.8),
        )

        # Fallback: crear engine local de forma lazy (solo si se necesita)
        _local: list = []

        def _local_fallback(p: str):
            if not _local:
                _local.append(self._build_local_engine())
            return _local[0].process_file(p)

        return rl.call_with_retry(
            engine.process_file,
            path,
            stop_flag_ref=self._stop_flag,
            fallback_fn=_local_fallback,
        )

    # ── Image extraction ───────────────────────────────────────────────────────

    def _extract_images(self, path: str) -> list[str]:
        if not self._include_images:
            return []
        ext = Path(path).suffix.lower()
        images_dir = Path(self._output_dir) / "_images"
        images_dir.mkdir(parents=True, exist_ok=True)
        images: list[str] = []

        if ext == ".pdf":
            import fitz  # type: ignore
            doc = fitz.open(path)
            for pg_idx, page in enumerate(doc, start=1):
                mat = fitz.Matrix(2.0, 2.0)
                pix = page.get_pixmap(matrix=mat)
                img_path = images_dir / f"{Path(path).stem}_p{pg_idx}.png"
                pix.save(str(img_path))
                images.append(str(img_path))
            doc.close()
        elif ext in (".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp", ".webp"):
            import shutil
            dst = images_dir / Path(path).name
            try:
                shutil.copy2(path, dst)
                images.append(str(dst))
            except Exception:
                images.append(path)
        return images

    # ── Helpers ────────────────────────────────────────────────────────────────

    @staticmethod
    def _make_cancelled(idx: int, filename: str) -> dict:
        return {
            "index": idx, "filename": filename, "status": "Cancelado",
            "text": "", "pages": 0, "confidence": 0.0,
            "prompt_tokens": 0, "completion_tokens": 0,
            "images": [], "backend": "—",
        }

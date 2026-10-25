from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

_log = logging.getLogger("ocr.worker")

# Silenciar loggers muy ruidosos en tiempo de ejecución de lotes
for _noisy in ("matplotlib", "matplotlib.font_manager", "httpcore", "httpx", "urllib3"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)


class OcrWorker(QThread):
    """QThread que procesa archivos con GLM-4V y exporta los resultados.

    Signals
    -------
    document_done(int, str, float)  — row_index, status, confidence 0-1
    progress(int, int)              — current, total
    export_done(str)                — ruta del archivo exportado
    finished()                      — siempre al terminar (éxito o parada)
    error(str)                      — descripción del error si algo falla
    """

    document_done = pyqtSignal(int, str, float)
    document_qa   = pyqtSignal(int, bool, float)
    progress      = pyqtSignal(int, int)
    tokens_used   = pyqtSignal(int, int, str)   # prompt_tokens, completion_tokens, backend
    export_done      = pyqtSignal(str)
    qa_report        = pyqtSignal(str, dict)
    metrics_updated  = pyqtSignal(str)   # resumen de métricas de confianza por lote
    document_payload = pyqtSignal(str, str, float, object)  # filename, status, confidence, payload
    # New batch-level signals
    batch_started = pyqtSignal(int, int)       # batch_num, total_batches
    batch_completed = pyqtSignal(int, dict)    # batch_num, stats
    batch_review_requested = pyqtSignal(int)    # batch_num
    finished         = pyqtSignal()
    error            = pyqtSignal(str)

    def __init__(
        self,
        files: list[str],
        api_key: str,
        output_dir: str,
        output_format: str = "XLSX",
        merge: bool = True,
        profile: str = "Facturas/Contable",
        include_images: bool = True,
        expected_keys: list[str] | None = None,
        export_profile: str | None = None,
        vendor_master_path: str | None = None,
        backend: str | None = None,
        parent=None,
        image_upscale: int | None = None,
        prompt_template: str | None = None,
        use_preprocessor: bool = True,
        use_cache: bool = True,
        local_conf_threshold: float | None = 0.8,
        prefer_local: bool = True,
        # ── Proveedor de estructuración (segundo LLM, texto→JSON) ────────
        structuring_provider: str | None = None,
        structuring_api_key: str | None = None,
        structuring_model: str | None = None,
        structuring_base_url: str | None = None,
        ocr_output_mode: str | None = None,
    ) -> None:
        super().__init__(parent)
        self._files = list(files)
        self._api_key = api_key
        self._output_dir = output_dir or str(Path.home() / "Desktop")
        self._output_format = output_format
        self._merge = merge
        self._profile = profile
        self._include_images = include_images
        self._expected_keys = expected_keys or []
        self._export_profile = export_profile or "Exportación Estándar"
        self._vendor_master_path = vendor_master_path or ""
        self._pause_event = threading.Event()
        self._pause_event.set()
        self._stop_flag = False
        self._backend = backend or "glm"
        self._prompt_template = prompt_template
        self._image_upscale = image_upscale or 1
        self._use_preprocessor = use_preprocessor
        self._use_cache = bool(use_cache)
        self._structuring_provider = structuring_provider or ""
        self._structuring_api_key  = structuring_api_key or ""
        self._structuring_model    = structuring_model or ""
        self._structuring_base_url = structuring_base_url or ""
        self._ocr_output_mode = (ocr_output_mode or "JSON").strip()
        try:
            self._local_conf_threshold = float(local_conf_threshold or 0.8)
        except Exception:
            self._local_conf_threshold = 0.8
        self._prefer_local = bool(prefer_local)
        # Batch control
        self._batch_size = 100
        self._max_docs = 0
        self._review_after_batch = False

    def set_batch_params(self, batch_size: int = 100, max_docs: int = 0, review_after_batch: bool = False) -> None:
        try:
            self._batch_size = int(batch_size)
        except Exception:
            self._batch_size = 100
        try:
            self._max_docs = int(max_docs)
        except Exception:
            self._max_docs = 0
        self._review_after_batch = bool(review_after_batch)

    # ── Control ───────────────────────────────────────────────────────────────

    def pause(self) -> None:
        try:
            print("[OcrWorker] pause() called")
        except Exception:
            pass
        self._pause_event.clear()

    def resume(self) -> None:
        try:
            print("[OcrWorker] resume() called")
        except Exception:
            pass
        self._pause_event.set()

    def stop(self) -> None:
        try:
            print("[OcrWorker] stop() called")
        except Exception:
            pass
        self._stop_flag = True
        self._pause_event.set()

    # ── Checkpointing ─────────────────────────────────────────────────────────

    def _checkpoint_path(self) -> Path:
        return Path(self._output_dir) / ".ocr_state.json"

    def _save_checkpoint(self, done_indices: set, results: list) -> None:
        """Persiste el estado actual del lote para poder reanudarlo tras un cierre."""
        try:
            data = {
                "files": self._files,
                "profile": self._profile,
                "backend": self._backend,
                "done_indices": sorted(done_indices),
                "results": [
                    {k: v for k, v in r.items() if k != "images"}
                    for r in results
                ],
            }
            cp = self._checkpoint_path()
            cp.parent.mkdir(parents=True, exist_ok=True)
            cp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            _log.debug("Checkpoint guardado: %s (%d/%d)", cp, len(done_indices), len(self._files))
        except Exception as exc:
            _log.warning("No se pudo guardar checkpoint: %s", exc)

    def _load_checkpoint(self) -> tuple:
        """Devuelve (done_indices: set, results: list) desde el checkpoint si existe y es válido."""
        try:
            cp = self._checkpoint_path()
            if not cp.exists():
                return set(), []
            data = json.loads(cp.read_text(encoding="utf-8"))
            if data.get("files") != self._files:
                _log.warning("Checkpoint no coincide con los archivos actuales — ignorando")
                return set(), []
            done = set(data.get("done_indices", []))
            res  = data.get("results", [])
            _log.info("Checkpoint cargado: %d/%d archivos ya procesados", len(done), len(self._files))
            return done, res
        except Exception as exc:
            _log.warning("No se pudo leer checkpoint: %s", exc)
            return set(), []

    def _clear_checkpoint(self) -> None:
        """Elimina el checkpoint al completar exitosamente el lote."""
        try:
            cp = self._checkpoint_path()
            if cp.exists():
                cp.unlink()
                _log.debug("Checkpoint eliminado: %s", cp)
        except Exception as exc:
            _log.warning("No se pudo eliminar checkpoint: %s", exc)

    # ── Main loop ─────────────────────────────────────────────────────────────

    def run(self) -> None:
        try:
            self._run_inner()
        except Exception as exc:
            self.error.emit(f"Error inesperado: {exc}")
        finally:
            try:
                self.finished.emit()
            except Exception:
                pass

    def _run_inner(self) -> None:  # noqa: PLR0912, PLR0915
        print(f"[WORKER] _run_inner arrancado — {len(self._files)} archivos, stop_flag={self._stop_flag}")
        import queue as _queue
        from PyQt6.QtCore import QThreadPool
        from src.core.exporter import export_results
        from src.ui.ocr_task import OcrTask

        # ── Preflight: validar config del motor antes de lanzar tareas ────────
        try:
            _mode = None
            if isinstance(self._profile, str) and self._profile.lower().startswith("factura"):
                _mode = "single_invoice"
            from src.core.ocr_engine import OCREngine as _OCREngine
            _test = _OCREngine(
                self._api_key,
                profile=self._profile,
                expected_keys=self._expected_keys or None,
                backend=self._backend,
                mode=_mode,
                use_preprocessor=self._use_preprocessor,
                upscale=self._image_upscale,
                use_cache=self._use_cache,
                local_conf_threshold=self._local_conf_threshold,
                prefer_local=self._prefer_local,
            )
            del _test
        except Exception as exc:
            self.error.emit(str(exc))
            return  # finished se emite en run() via finally

        # Config que cada OcrTask usa para construir su propio engine ──────────
        engine_config = {
            "api_key":             self._api_key,
            "profile":             self._profile,
            "backend":             self._backend,
            "mode":                _mode,
            "use_preprocessor":    self._use_preprocessor,
            "upscale":             self._image_upscale,
            "use_cache":           self._use_cache,
            "local_conf_threshold": self._local_conf_threshold,
            "prefer_local":        self._prefer_local,
            "light_mode":          False,
            "prompt_template":     self._prompt_template,
            # Motor de estructuración (2.º LLM: texto → JSON)
            "structuring_provider": self._structuring_provider,
            "structuring_api_key":  self._structuring_api_key,
            "structuring_model":    self._structuring_model,
            "structuring_base_url": self._structuring_base_url,
            "ocr_output_mode":      self._ocr_output_mode,
            # FASE 4: enrutamiento IA y auditoría
            "smart_routing":       getattr(self, "_smart_routing", False),
            "audit_enabled":       getattr(self, "_audit_enabled", True),
        }

        total_requested = len(self._files)
        # Apply max_docs limit if set
        if getattr(self, '_max_docs', 0) and self._max_docs > 0:
            files_to_process = self._files[: self._max_docs]
        else:
            files_to_process = list(self._files)
        total = len(files_to_process)
        _log.info(
            "[WORKER] Iniciando procesamiento de %d documentos (solicitados=%d)",
            total,
            total_requested,
        )
        results: list[dict] = []
        total_prompt     = 0
        total_completion = 0

        # ── Reanudar desde checkpoint SQLite si existe (archivo-based)
        _done_indices, _resumed_results = self._load_checkpoint()
        if _resumed_results:
            results = list(_resumed_results)
            _log.info("Reanudando lote SQLite: %d/%d archivos ya procesados", len(_done_indices), total)

        # ── Prepare batches (chunking) ───────────────────────────────────────
        try:
            from src.core.job_queue import JobQueue
            _db_path = Path(self._output_dir) / ".ocr_jobs.db"
            # Eliminar la DB de ejecuciones anteriores para que no mezcle
            # resultados de proyectos distintos. Cada ejecución empieza limpia.
            if _db_path.exists():
                try:
                    _db_path.unlink()
                    _log.info("JobQueue: DB anterior eliminada para nueva ejecución (%s)", _db_path)
                except Exception as _del_exc:
                    _log.warning("No se pudo eliminar DB anterior: %s", _del_exc)
            jq = JobQueue(_db_path)
            # Register batches in DB
            chunks = [files_to_process[i:i+self._batch_size] for i in range(0, len(files_to_process), self._batch_size)]
            total_batches = len(chunks)
            # create_batches expects full file list; we only register batches for files_to_process
            jq.create_batches(files_to_process, batch_size=self._batch_size)
        except Exception:
            jq = None
            chunks = [files_to_process[i:i+100] for i in range(0, len(files_to_process), 100)]
            total_batches = len(chunks)

        # ── Pool con máximo 3 hilos concurrentes ──────────────────────────────
        # Cada OcrTask bloquea en pause_event.wait() al inicio, lo que:
        #  1. Pause → hasta 3 hilos se bloquean → ninguna nueva tarea arranca.
        #  2. Stop  → tareas aún no iniciadas detectan el flag y emiten "Cancelado".
        result_queue: _queue.Queue = _queue.Queue()
        _task_stop: list[bool] = [False]   # mutable ref compartida con los tasks

        pool = QThreadPool()
        pool.setMaxThreadCount(3)
        _log.info("Pool OCR iniciado: máx 3 hilos concurrentes")
        _job_ids: dict[int, str | None] = {}   # file_index → job_id

        # ── Enviar tareas por batch ───────────────────────────────────────────
        submitted = 0
        batch_index_offset = 0
        completed = len(_done_indices)   # cuántos están ya listos (checkpoint)
        try:
            from src.core.confidence_tracker import ConfidenceTracker
            _tracker = ConfidenceTracker()
        except Exception:
            _tracker = None
        for bnum, chunk in enumerate(chunks, start=1):
            if self._stop_flag:
                break
            # Emitir batch_started
            try:
                self.batch_started.emit(bnum, total_batches)
            except Exception:
                pass
            completed_in_batch = 0
            errors_in_batch = 0
            conf_acc = 0.0
            tokens_prompt = 0
            tokens_completion = 0
            # Launch tasks for this chunk
            _submitted_in_batch = 0
            for path in chunk:
                if self._stop_flag:
                    _task_stop[0] = True
                    break
                # global index
                try:
                    i = self._files.index(path)
                except Exception:
                    i = batch_index_offset
                if i in _done_indices:
                    continue
                filename = Path(path).name
                _log.info("[WORKER] Procesando %d/%d: %s", i + 1, total, filename)
                try:
                    task = OcrTask(
                        index=i,
                        path=path,
                        engine_config=engine_config,
                        result_queue=result_queue,
                        stop_flag=_task_stop,
                        pause_event=self._pause_event,
                        include_images=self._include_images,
                        output_dir=self._output_dir,
                        expected_keys=self._expected_keys,
                    )
                    # Obtain job id from JobQueue if available
                    try:
                        if jq is not None:
                            _cur = jq._conn.execute(
                                "SELECT id FROM jobs WHERE filepath=? LIMIT 1",
                                (path,)
                            )
                            _row = _cur.fetchone()
                            task._job_id = _row["id"] if _row else None  # type: ignore[attr-defined]
                        else:
                            task._job_id = None
                    except Exception as _jq_exc:
                        _log.warning("JobQueue: no se pudo obtener job_id para '%s': %s", os.path.basename(path), _jq_exc)
                        task._job_id = None
                    _job_ids[i] = task._job_id  # type: ignore[attr-defined]
                    self.document_done.emit(i, "Procesando...", 0.0)
                    pool.start(task)
                    submitted += 1
                    _submitted_in_batch += 1
                    _log.debug("Tarea enviada al pool (batch %d) %s", bnum, os.path.basename(path))
                except Exception as _doc_exc:
                    _log.error("Error procesando archivo '%s': %s", filename, _doc_exc, exc_info=True)
                    completed += 1
                    errors_in_batch += 1
                    self.document_done.emit(i, "Error", 0.0)
                    self.progress.emit(completed, total)
                    _log.info("[WORKER] Completado %s: Error", filename)
                    try:
                        self.document_payload.emit(filename, "Error", 0.0, {
                            "filename": filename,
                            "status": "Error",
                            "text": str(_doc_exc),
                            "backend": str(self._backend or ""),
                        })
                    except Exception:
                        pass
                    continue

            # ── Recoger resultados para este batch ─────────────────────────
            for _ in range(_submitted_in_batch):
                if self._stop_flag:
                    _task_stop[0] = True
                    break
                result = None
                while result is None:
                    if self._stop_flag:
                        _task_stop[0] = True
                        break
                    try:
                        result = result_queue.get(timeout=0.5)
                    except Exception:
                        continue
                if result is None:
                    break

                try:
                    completed += 1
                    idx        = int(result.get("index", -1))
                    status     = str(result.get("status", "Error"))
                    filename   = str(result.get("filename", ""))

                    if status == "Cancelado":
                        self.progress.emit(completed, total)
                        _log.debug("Tarea cancelada: %s", filename)
                        continue

                    confidence   = float(result.get("confidence", 0.0) or 0.0)
                    text         = str(result.get("text", ""))
                    pages        = int(result.get("pages", 0) or 0)
                    pt           = int(result.get("prompt_tokens", 0) or 0)
                    ct           = int(result.get("completion_tokens", 0) or 0)
                    backend_name = result.get("backend", self._backend) or self._backend or "glm"
                    images       = result.get("images", [])

                    if status == "Error":
                        self.error.emit(f"{filename}: {text}")
                        errors_in_batch += 1

                    total_prompt     += pt
                    total_completion += ct
                    tokens_prompt += pt
                    tokens_completion += ct

                    results.append({
                        "id":         idx + 1,
                        "filename":   filename,
                        "pages":      pages,
                        "confidence": confidence,
                        "status":     status,
                        "text":       text,
                        "images":     images,
                        "backend":    backend_name,
                        "mode":       result.get("mode"),
                        "cost_usd":   result.get("cost_usd"),
                    })

                    _done_indices.add(idx)
                    self._save_checkpoint(_done_indices, results)

                    # Persistir resultado en JobQueue SQLite ————————————————————
                    _job_id = _job_ids.get(idx)
                    try:
                        if jq is not None:
                            if status == "Error":
                                jq.mark_failed(_job_id or "", text)
                            else:
                                _result_payload = {
                                    "id": idx + 1, "filename": filename, "pages": pages,
                                    "confidence": confidence, "status": status, "text": text,
                                }
                                jq.mark_done(_job_id or "", _result_payload)
                    except Exception as _jq_exc:
                        _log.warning("JobQueue.mark_done/failed falló para '%s': %s", filename, _jq_exc)

                    self.document_done.emit(idx, status, confidence)
                    _log.info("[WORKER] Completado %s: %s", filename, status)
                    try:
                        self.document_payload.emit(filename, status, confidence, dict(results[-1]))
                    except Exception:
                        pass
                    self.progress.emit(completed, total)
                    self.tokens_used.emit(total_prompt, total_completion, backend_name)

                    # metrics
                    try:
                        if _tracker is not None:
                            _tracker.record("default", self._profile, confidence, status)
                            summary = _tracker.summary_text("default", self._profile)
                            self.metrics_updated.emit(summary)
                    except Exception as _mt_exc:
                        _log.warning("ConfidenceTracker.record falló: %s", _mt_exc)

                    completed_in_batch += 1
                    conf_acc += float(confidence or 0.0)
                except Exception as _result_exc:
                    _log.error("Error manejando resultado de tarea OCR: %s", _result_exc, exc_info=True)
                    safe_idx = -1
                    try:
                        safe_idx = int(result.get("index", -1))
                    except Exception:
                        pass
                    self.document_done.emit(safe_idx, f"Error: {_result_exc}", 0.0)
                    if safe_idx >= 0:
                        _safe_name = str(result.get("filename") or f"doc_{safe_idx + 1}")
                        _log.info("[WORKER] Completado %s: Error", _safe_name)
                    self.progress.emit(completed, total)
                    try:
                        self.document_payload.emit(str(result.get("filename") or ""), "Error", 0.0, {
                            "filename": result.get("filename"),
                            "status": "Error",
                            "text": str(_result_exc),
                            "backend": str(result.get("backend") or ""),
                        })
                    except Exception:
                        pass
                    errors_in_batch += 1
                    continue

            # Fin de batch: emitir batch_completed y registrar en jq
            avg_conf = (conf_acc / completed_in_batch) if completed_in_batch else 0.0
            stats = {
                "processed": completed_in_batch,
                "errors": errors_in_batch,
                "avg_confidence": avg_conf,
                "tokens": {"prompt": tokens_prompt, "completion": tokens_completion},
            }
            try:
                self.batch_completed.emit(bnum, stats)
            except Exception:
                pass
            try:
                if jq is not None:
                    # Mark first matching batch_id as completed (best-effort)
                    cur = jq._conn.execute("SELECT batch_id FROM batches WHERE batch_number=? LIMIT 1", (bnum,))
                    r = cur.fetchone()
                    if r:
                        jq.mark_batch_completed(r[0], stats)
            except Exception:
                pass

            # If review requested, emit and wait for resume
            if getattr(self, '_review_after_batch', False):
                try:
                    self.batch_review_requested.emit(bnum)
                except Exception:
                    pass
                # block until resume called externally
                self._pause_event.clear()
                self._pause_event.wait()
            batch_index_offset += len(chunk)

        # Asegurar que el pool termina limpiamente antes de exportar ─────────
        # Timeout de 30 s: si algún hilo cuelga no bloqueamos la UI para siempre
        _pool_timeout_ms = 30_000
        _pool_done = pool.waitForDone(_pool_timeout_ms)
        if not _pool_done:
            _log.warning(
                "Pool no finalizó en %d s — algunos hilos pueden seguir corriendo.",
                _pool_timeout_ms // 1000,
            )
        else:
            _log.info("Pool finalizado. Resultados recogidos: %d/%d", completed, total)

        # ── Exportar si hay resultados ────────────────────────────────────────
        if results and not self._stop_flag:
            try:
                _extra_export_kwargs = {
                    "structuring_provider": self._structuring_provider or None,
                    "structuring_api_key": self._structuring_api_key or None,
                    "structuring_model": self._structuring_model or None,
                    "structuring_base_url": self._structuring_base_url or None,
                    "prompt_template": self._prompt_template or None,
                }
                paths = export_results(
                    results,
                    self._output_dir,
                    self._output_format,
                    self._merge,
                    include_images=self._include_images,
                    expected_keys=self._expected_keys or None,
                    export_profile=self._export_profile,
                    vendor_master_path=self._vendor_master_path,
                    **_extra_export_kwargs,
                )
                out_path = paths[0] if paths else ""
                # Ejecutar QA comparando JSON vs el Excel/CSV generado
                try:
                    from src.core.qa_checker import compare_invoices_json_vs_excel
                    msgs, stats = compare_invoices_json_vs_excel(results, out_path)
                    # Guardar metadatos QA al lado del archivo exportado
                    try:
                        import json as _json
                        from pathlib import Path as _P

                        meta_path = _P(out_path).with_suffix(_P(out_path).suffix + ".qa.json")
                        meta = {"qa_stats": stats, "qa_messages": msgs}
                        # prompt_template/checksum no disponible en contexto paralelo
                        try:
                            meta["prompt_template"] = engine_config.get("prompt_template")
                            meta["prompt_checksum"] = None
                        except Exception:
                            pass
                        # Incluir salidas raw de Mistral (markdown) para depuración
                        try:
                            raw_map = {}
                            for r in results:
                                be = str(r.get("backend") or "").lower()
                                if "mistral" in be:
                                    fname = r.get("filename") or r.get("index")
                                    raw_map[str(fname)] = r.get("text") or ""
                            if raw_map:
                                meta["raw_mistral"] = raw_map
                        except Exception as _raw_exc:
                            _log.debug("No se pudo adjuntar raw_mistral: %s", _raw_exc)
                        with meta_path.open("w", encoding="utf-8") as mf:
                            _json.dump(meta, mf, ensure_ascii=False, indent=2)
                    except Exception as _meta_exc:
                        _log.warning("No se pudo guardar metadatos QA: %s", _meta_exc)
                    # Emitir señales
                    self.qa_report.emit(out_path, stats or {})
                    # Emitir QA por documento si hay per-invoice stats
                    try:
                        per = stats.get("per_invoice", {}) if isinstance(stats, dict) else {}
                        for key, info in per.items():
                            # key expected to be invoice id as string; buscar resultado con matching id
                            try:
                                iid = int(key)
                            except Exception:
                                iid = None
                            row_idx = None
                            if iid is not None:
                                for r_idx, res in enumerate(results):
                                    if int(res.get("id") or -1) == iid:
                                        row_idx = r_idx
                                        break
                            if row_idx is None:
                                # fallback: try to match by filename containing key
                                for r_idx, res in enumerate(results):
                                    if key and key in (res.get("filename") or ""):
                                        row_idx = r_idx
                                        break
                            if row_idx is not None:
                                diffs = info.get("diffs", 0) if isinstance(info, dict) else 0
                                passed = info.get("passed", False) if isinstance(info, dict) else (diffs == 0)
                                # Simple accuracy estimate
                                accuracy = 100.0 if passed else max(0.0, 100.0 - min(100.0, diffs * 33.33))
                                self.document_qa.emit(row_idx, bool(passed), float(accuracy))
                    except Exception as _per_exc:
                        _log.warning("QA per-invoice emit falló: %s", _per_exc)
                except Exception as _qa_exc:
                    _log.warning("QA compare_invoices_json_vs_excel falló: %s", _qa_exc)
                self._clear_checkpoint()

                # ── Reconciliación contable opcional ──────────────────────
                if getattr(self, "_accounting_validation", False):
                    try:
                        try:
                            from src.core.qa_checker import run_accounting_validation
                        except Exception:
                            from core.qa_checker import run_accounting_validation  # type: ignore[no-redef]
                        acct_report = run_accounting_validation(
                            results,
                            tolerance_pct=2.0,
                            enabled=True,
                        )
                        self.qa_report.emit("accounting", acct_report)
                        if not acct_report.get("clean"):
                            _log.warning(
                                "Reconciliación contable: %d error(es), %d warning(s)",
                                acct_report.get("error_count", 0),
                                acct_report.get("warning_count", 0),
                            )
                    except Exception as _acct_exc:
                        _log.warning("run_accounting_validation falló: %s", _acct_exc)

                self.export_done.emit(out_path)
            except Exception as exc:
                _log.error("Error al exportar resultados: %s", exc, exc_info=True)
                self.error.emit(f"Error al exportar: {exc}")
        # finished se emite en run() via finally


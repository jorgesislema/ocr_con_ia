from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QGroupBox, QLabel, QComboBox, QLineEdit, QPushButton, QHBoxLayout, QMessageBox, QCheckBox
)
from PyQt6.QtCore import pyqtSignal
import threading

_CONFIG_PATH = Path.home() / '.ocr_glm_config.json'


class AICredentialsPanel(QWidget):
    api_validated = pyqtSignal(bool)
    validation_completed = pyqtSignal(str, bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
        self._load()
        self.validation_completed.connect(self._on_validation_completed)

    def _build_ui(self) -> None:
        lay = QVBoxLayout()
        lay.setSpacing(8)

        # Motor de OCR
        gb_ocr = QGroupBox("Motor de OCR (Extracción)")
        gbl = QVBoxLayout()
        gbl.setContentsMargins(12, 8, 12, 8)
        self.ocr_model_cb = QComboBox()
        self.ocr_model_cb.addItems([
            "GLM-4V (ZhipuAI)", "Mistral OCR", "Google Vision", "Google Docs",
            "ocr-local", "PaddleOCR", "EasyOCR"
        ])
        gbl.addWidget(self.ocr_model_cb)

        self.ocr_token_input = QLineEdit()
        self.ocr_token_input.setPlaceholderText("API Key")
        self.ocr_token_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.ocr_token_input.setFixedHeight(30)
        gbl.addWidget(self.ocr_token_input)
        # JSON service account input + browse
        ojson_row = QHBoxLayout()
        self.ocr_json_input = QLineEdit()
        self.ocr_json_input.setPlaceholderText("Ruta JSON cuenta de servicio (opcional)")
        self.ocr_json_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.ocr_json_input.setFixedHeight(30)
        ojson_row.addWidget(self.ocr_json_input, 1)
        self.ocr_json_browse = QPushButton("Examinar")
        self.ocr_json_browse.setFixedHeight(30)
        def _browse_ocr_json():
            try:
                from PyQt6.QtWidgets import QFileDialog
                path, _ = QFileDialog.getOpenFileName(self, "Seleccionar JSON de cuenta de servicio", "", "JSON Files (*.json);;All Files (*)")
                if path:
                    self.ocr_json_input.setText(path)
            except Exception:
                pass
        self.ocr_json_browse.clicked.connect(_browse_ocr_json)
        ojson_row.addWidget(self.ocr_json_browse)
        gbl.addLayout(ojson_row)

        # Google Documents processor id (for custom Document AI processors)
        self.google_processor_input = QLineEdit()
        self.google_processor_input.setPlaceholderText("Processor resource (projects/.../locations/.../processors/...) (opcional)")
        self.google_processor_input.setFixedHeight(30)
        self.google_processor_input.setToolTip("Indicar el processor_id si usa Google Document AI (p. ej. projects/PROJ/locations/us/processors/PROC)")
        gbl.addWidget(self.google_processor_input)

        row = QHBoxLayout()
        self.ocr_show_btn = QPushButton("👁️ Mostrar")
        self.ocr_show_btn.setCheckable(True)
        self.ocr_show_btn.toggled.connect(self._toggle_ocr_visibility)
        row.addWidget(self.ocr_show_btn)
        self.ocr_validate_btn = QPushButton("✔ Validar")
        self.ocr_validate_btn.clicked.connect(self._validate_ocr)
        row.addWidget(self.ocr_validate_btn)
        self.ocr_status_lbl = QLabel("● Desconectado")
        self.ocr_status_lbl.setObjectName("statusDisconnected")
        row.addWidget(self.ocr_status_lbl)
        # ensure spacing to avoid overlap
        row.setSpacing(12)
        gbl.addLayout(row)

        gb_ocr.setLayout(gbl)
        lay.addWidget(gb_ocr)

        # Post-OCR
        gb_post = QGroupBox("IA de Post-Procesado / Pensamiento")
        pgl = QVBoxLayout()
        pgl.setContentsMargins(12, 8, 12, 8)
        self.use_postocr_chk = QCheckBox("Usar IA para ordenar/corregir/razonar resultados")
        pgl.addWidget(self.use_postocr_chk)
        self.postocr_model_cb = QComboBox()
        # full list of available post-OCR models
        self._postocr_models_all = [
            "gpt-4o-mini", "gpt-4o", "claude-3-haiku", "local-ner",
            "deep seek", "qwen", "mistral", "google", "open router"
        ]
        self.postocr_model_cb.addItems(self._postocr_models_all)
        pgl.addWidget(self.postocr_model_cb)
        # Option to force only free models for Post-OCR
        self.postocr_free_only_chk = QCheckBox("Usar sólo modelos gratuitos")
        self.postocr_free_only_chk.setToolTip("Mostrar sólo modelos gratuitos en la lista de Post-OCR y forzar su uso cuando esté activado.")
        self.postocr_free_only_chk.toggled.connect(self._on_postocr_free_only_toggled)
        pgl.addWidget(self.postocr_free_only_chk)
        self.postocr_token_input = QLineEdit()
        self.postocr_token_input.setPlaceholderText("API Key Post-OCR")
        self.postocr_token_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.postocr_token_input.setFixedHeight(30)
        pgl.addWidget(self.postocr_token_input)
        # JSON input + browse for post-OCR
        pjson_row = QHBoxLayout()
        self.postocr_json_input = QLineEdit()
        self.postocr_json_input.setPlaceholderText("Ruta JSON cuenta servicio (opcional)")
        self.postocr_json_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.postocr_json_input.setFixedHeight(30)
        pjson_row.addWidget(self.postocr_json_input, 1)
        self.postocr_json_browse = QPushButton("Examinar")
        self.postocr_json_browse.setFixedHeight(30)
        def _browse_postocr_json():
            try:
                from PyQt6.QtWidgets import QFileDialog
                path, _ = QFileDialog.getOpenFileName(self, "Seleccionar JSON de cuenta de servicio", "", "JSON Files (*.json);;All Files (*)")
                if path:
                    self.postocr_json_input.setText(path)
            except Exception:
                pass
        self.postocr_json_browse.clicked.connect(_browse_postocr_json)
        pjson_row.addWidget(self.postocr_json_browse)
        pgl.addLayout(pjson_row)
        prow = QHBoxLayout()
        self.postocr_show_btn = QPushButton("👁️ Mostrar")
        self.postocr_show_btn.setCheckable(True)
        self.postocr_show_btn.toggled.connect(self._toggle_postocr_visibility)
        prow.addWidget(self.postocr_show_btn)
        self.postocr_validate_btn = QPushButton("✔ Validar Post-OCR")
        self.postocr_validate_btn.clicked.connect(self._validate_postocr)
        prow.addWidget(self.postocr_validate_btn)
        self.postocr_status_lbl = QLabel("● Desconectado")
        self.postocr_status_lbl.setObjectName("statusDisconnected")
        prow.addWidget(self.postocr_status_lbl)
        prow.setSpacing(12)
        pgl.addLayout(prow)
        gb_post.setLayout(pgl)
        lay.addWidget(gb_post)

        # ensure initial enabled/disabled state
        self._on_postocr_free_only_toggled(self.postocr_free_only_chk.isChecked())

        # Footer buttons
        footer = QHBoxLayout()
        self.save_btn = QPushButton("💾 Guardar Credenciales")
        self.save_btn.clicked.connect(self._save)
        footer.addWidget(self.save_btn)
        self.clear_btn = QPushButton("🗑 Borrar Credenciales")
        self.clear_btn.clicked.connect(self._clear)
        footer.addWidget(self.clear_btn)
        self.confirm_lbl = QLabel("")
        footer.addWidget(self.confirm_lbl)
        footer.addStretch(1)
        lay.addLayout(footer)

        self.setLayout(lay)

        # Signals
        self.ocr_model_cb.currentTextChanged.connect(self._on_ocr_model_changed)
        self.use_postocr_chk.toggled.connect(lambda v: self.postocr_model_cb.setEnabled(v))
        self.postocr_model_cb.setEnabled(False)

    def _on_ocr_model_changed(self, txt: str) -> None:
        n = txt.lower()
        if n.startswith("ocr-local") or n in ("paddleocr", "paddleocr", "easyocr", "ocr-local"):
            # modo local
            self.ocr_token_input.setEnabled(False)
            self.ocr_json_input.setEnabled(False)
            self.ocr_status_lbl.setText("✅ Funcionando sin conexión / Sin API Key requerida")
            self.ocr_status_lbl.setObjectName("statusConnected")
        else:
            self.ocr_token_input.setEnabled(True)
            self.ocr_json_input.setEnabled(True)
            # enable google processor input if user selected Google Documents
            if "google" in n and "doc" in n:
                self.google_processor_input.setEnabled(True)
            else:
                self.google_processor_input.setEnabled(False)
            self.ocr_status_lbl.setText("● Desconectado")
            self.ocr_status_lbl.setObjectName("statusDisconnected")

    def _toggle_ocr_visibility(self, show: bool) -> None:
        if show:
            self.ocr_token_input.setEchoMode(QLineEdit.EchoMode.Normal)
            self.ocr_json_input.setEchoMode(QLineEdit.EchoMode.Normal)
            self.ocr_show_btn.setText("🙈 Ocultar")
        else:
            self.ocr_token_input.setEchoMode(QLineEdit.EchoMode.Password)
            self.ocr_json_input.setEchoMode(QLineEdit.EchoMode.Password)
            self.ocr_show_btn.setText("👁️ Mostrar")

    def _toggle_postocr_visibility(self, show: bool) -> None:
        if show:
            self.postocr_token_input.setEchoMode(QLineEdit.EchoMode.Normal)
            self.postocr_json_input.setEchoMode(QLineEdit.EchoMode.Normal)
            self.postocr_show_btn.setText("🙈 Ocultar")
        else:
            self.postocr_token_input.setEchoMode(QLineEdit.EchoMode.Password)
            self.postocr_json_input.setEchoMode(QLineEdit.EchoMode.Password)
            self.postocr_show_btn.setText("👁️ Mostrar")

    def _validate_ocr(self) -> None:
        # Validación no bloqueante para evitar congelar la UI.
        txt = self.ocr_model_cb.currentText().lower()
        if txt.startswith("ocr-local"):
            self.ocr_status_lbl.setText("● Conectado")
            self.ocr_status_lbl.setObjectName("statusConnected")
            self.api_validated.emit(True)
            return

        # mostrar estado de validando y deshabilitar botón
        self.ocr_status_lbl.setText("● Validando...")
        self.ocr_validate_btn.setEnabled(False)

        def _worker():
            try:
                key = self.ocr_token_input.text().strip()
                jsonp = self.ocr_json_input.text().strip()
                ok = bool(key or jsonp)

                # Validación real para Mistral: comprobar auth contra /v1/models.
                if "mistral" in txt and key:
                    try:
                        import requests

                        resp = requests.get(
                            "https://api.mistral.ai/v1/models",
                            headers={"Authorization": f"Bearer {key}"},
                            timeout=15,
                        )
                        ok = bool(resp.status_code == 200)
                    except Exception:
                        ok = False
            except Exception:
                ok = False
            # emitir resultado de validación (slot en hilo principal)
            try:
                self.validation_completed.emit('ocr', ok)
            except Exception:
                pass

        threading.Thread(target=_worker, daemon=True).start()

    def _validate_postocr(self) -> None:
        # Validación no bloqueante: intenta crear un StructuringEngine y
        # realizar una llamada mínima al endpoint para verificar credenciales.
        self.postocr_status_lbl.setText("● Validando...")
        self.postocr_validate_btn.setEnabled(False)

        def _worker():
            try:
                model_text = (self.postocr_model_cb.currentText() or "").strip()
                token = (self.postocr_token_input.text() or "").strip()
                jsonp = (self.postocr_json_input.text() or "").strip()

                # Mapear texto de modelo a proveedor
                m = model_text.lower()
                if "deep" in m:
                    provider = "DeepSeek"
                elif "google" in m or "gemini" in m:
                    provider = "Google Gemini Flash (gratuito)"
                elif "gpt" in m or "openai" in m:
                    provider = "OpenAI GPT-4o"
                elif "qwen" in m:
                    provider = "Qwen (Alibaba Cloud)"
                elif "mistral" in m:
                    provider = "Mistral Large"
                elif "openrouter" in m or "open router" in m:
                    provider = "OpenRouter"
                elif "claude" in m or "anthropic" in m:
                    provider = "Anthropic (Claude 3.5)"
                else:
                    provider = model_text or "DeepSeek"

                api_key = token or ""
                # intentar leer key desde JSON si se indicó ruta
                if not api_key and jsonp:
                    try:
                        import json as _json
                        from pathlib import Path as _P
                        _d = _json.loads(_P(jsonp).read_text(encoding='utf-8'))
                        for _cand in ("api_key", "key", "token", "access_token"):
                            _v = str((_d or {}).get(_cand, "") or "").strip()
                            if _v:
                                api_key = _v
                                break
                    except Exception:
                        pass

                ok = False
                details = ""
                if not api_key and provider.lower() not in {"ollama (local)", "lm studio (local)"}:
                    details = "No API key disponible"
                else:
                    try:
                        # Mapear texto de UI a nombre de modelo real
                        _model_mappings = {
                            "deep seek": None,
                            "mistral": None,
                            "qwen": None,
                            "google": None,
                            "open router": None,
                            "openrouter": None,
                            "gpt-4o-mini": "gpt-4o-mini",
                            "gpt-4o": "gpt-4o",
                            "gpt-4o-realtime": "gpt-4o-realtime",
                            "local-ner": "local-ner",
                            "claude-3-haiku": "claude-3-haiku",
                        }
                        mapped_model = _model_mappings.get(model_text.lower().strip())
                        if mapped_model is None and model_text.lower().strip() not in _model_mappings:
                            mapped_model = model_text.strip() or None

                        # Usar StructuringEngine del proyecto para probar la conexión
                        from src.core.structuring_engine import StructuringEngine

                        engine = StructuringEngine(
                            provider=provider,
                            api_key=api_key,
                            model=mapped_model,
                        )
                        # llamada mínima de prueba
                        res, pt, ct = engine.structure("Prueba conexión: responde OK", "Responde solo OK")
                        details = f"reply={str(res)[:300]} pt={pt} ct={ct}"
                        ok = bool(res and str(res).strip())
                    except Exception as _ex:
                        details = str(_ex)

                # emitir resultado para actualizar labels/estado en el hilo principal
                try:
                    self.validation_completed.emit('postocr', bool(ok))
                except Exception:
                    pass

                # Mostrar popup con detalle usando QTimer.singleShot para ejecutar en hilo GUI
                try:
                    from PyQt6.QtCore import QTimer

                    def _show():
                        try:
                            if ok:
                                QMessageBox.information(self, "Validación Post‑OCR", f"Conectado:\n{details}")
                            else:
                                QMessageBox.warning(self, "Validación Post‑OCR", f"No conectado:\n{details}")
                        except Exception:
                            pass

                    QTimer.singleShot(0, _show)
                except Exception:
                    pass
            finally:
                try:
                    from PyQt6.QtCore import QTimer
                    QTimer.singleShot(0, lambda: self.postocr_validate_btn.setEnabled(True))
                except Exception:
                    try:
                        self.postocr_validate_btn.setEnabled(True)
                    except Exception:
                        pass

        threading.Thread(target=_worker, daemon=True).start()

    def _save(self) -> None:
        try:
            # usar security si está disponible
            try:
                from src.core.security import save_credentials
                ok = save_credentials(
                    ocr_token=self.ocr_token_input.text().strip(),
                    ocr_json=self.ocr_json_input.text().strip(),
                    postocr_token=self.postocr_token_input.text().strip(),
                    postocr_json=self.postocr_json_input.text().strip(),
                    google_processor_id=self.google_processor_input.text().strip(),
                    postocr_free_only=bool(self.postocr_free_only_chk.isChecked()),
                )
                if ok:
                    self.confirm_lbl.setText("✅ Credenciales guardadas localmente")
                    return
            except Exception:
                pass
            # fallback: guardar en el config JSON sin cifrar
            data = {
                "ocr_model": self.ocr_model_cb.currentText(),
                "ocr_token": self.ocr_token_input.text().strip(),
                "ocr_json": self.ocr_json_input.text().strip(),
                "google_processor_id": self.google_processor_input.text().strip(),
                "postocr_free_only": bool(self.postocr_free_only_chk.isChecked()),
                "use_postocr": bool(self.use_postocr_chk.isChecked()),
                "postocr_model": self.postocr_model_cb.currentText(),
                "postocr_token": self.postocr_token_input.text().strip(),
                "postocr_json": self.postocr_json_input.text().strip(),
            }
            with open(_CONFIG_PATH, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            self.confirm_lbl.setText("✅ Credenciales guardadas localmente")
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"No se pudo guardar: {exc}")

    def _clear(self) -> None:
        try:
            self.ocr_token_input.clear()
            self.ocr_json_input.clear()
            self.postocr_token_input.clear()
            self.postocr_json_input.clear()
            # eliminar archivo cifrado si existe
            try:
                from src.core.security import delete_credentials
                delete_credentials()
            except Exception:
                if _CONFIG_PATH.exists():
                    _CONFIG_PATH.unlink()
            self.confirm_lbl.setText("")
        except Exception:
            pass

    def _on_validation_completed(self, kind: str, ok: bool) -> None:
        # actualiza la UI tras la validación asíncrona
        if kind == 'ocr':
            self.ocr_validate_btn.setEnabled(True)
            if ok:
                self.ocr_status_lbl.setText("● Conectado")
                self.ocr_status_lbl.setObjectName("statusConnected")
            else:
                self.ocr_status_lbl.setText("● Desconectado")
                self.ocr_status_lbl.setObjectName("statusDisconnected")
            self.api_validated.emit(ok)
        elif kind == 'postocr':
            self.postocr_validate_btn.setEnabled(True)
            if ok:
                self.postocr_status_lbl.setText("● Conectado")
                self.postocr_status_lbl.setObjectName("statusConnected")
            else:
                self.postocr_status_lbl.setText("● Desconectado")
                self.postocr_status_lbl.setObjectName("statusDisconnected")

    def _load(self) -> None:
        # intentar cargar credenciales cifradas
        try:
            from src.core.security import load_credentials
            data = load_credentials() or {}
        except Exception:
            data = {}
        # fallback a archivo JSON plano
        if not data and _CONFIG_PATH.exists():
            try:
                with open(_CONFIG_PATH, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except Exception:
                data = {}
        try:
            self.ocr_model_cb.setCurrentText(data.get('ocr_model', self.ocr_model_cb.currentText()))
            self.ocr_token_input.setText(data.get('ocr_token','') or '')
            self.ocr_json_input.setText(data.get('ocr_json','') or '')
            self.google_processor_input.setText(data.get('google_processor_id','') or '')
            # postocr free-only flag
            try:
                self.postocr_free_only_chk.setChecked(bool(data.get('postocr_free_only', False)))
            except Exception:
                self.postocr_free_only_chk.setChecked(False)
            self.use_postocr_chk.setChecked(bool(data.get('use_postocr', False)))
            self.postocr_model_cb.setCurrentText(data.get('postocr_model', self.postocr_model_cb.currentText()))
            self.postocr_token_input.setText(data.get('postocr_token','') or '')
            self.postocr_json_input.setText(data.get('postocr_json','') or '')
        except Exception:
            pass

    def _on_postocr_google_only_toggled(self, checked: bool) -> None:
        # legacy handler removed
        pass

    def _on_postocr_free_only_toggled(self, checked: bool) -> None:
        # Filter postocr_model_cb to show only free models when checked.
        try:
            free_models = [m for m in self._postocr_models_all if m in ("local-ner", "google")]
            current = self.postocr_model_cb.currentText()
            self.postocr_model_cb.clear()
            if checked:
                self.postocr_model_cb.addItems(free_models)
                # if current not in free list, pick first
                if current not in free_models:
                    self.postocr_model_cb.setCurrentIndex(0)
            else:
                self.postocr_model_cb.addItems(self._postocr_models_all)
                # restore previous if present
                try:
                    self.postocr_model_cb.setCurrentText(current)
                except Exception:
                    pass
        except Exception:
            pass

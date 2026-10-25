from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from PyQt6.QtWidgets import (
    QFrame,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QComboBox,
    QCheckBox,
    QWidget,
    QFileDialog,
    QSizePolicy,
        QScrollArea,
    QTabWidget,
    QGroupBox,
    QRadioButton,
    QButtonGroup,
    QSpinBox,
    QDoubleSpinBox,
    QMessageBox,
    QInputDialog,
)
from PyQt6.QtWidgets import QTextEdit
from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtGui import QIcon
import sys
import subprocess
from PyQt6.QtWidgets import QApplication

import matplotlib
matplotlib.use("QtAgg")
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from .schema_panel import SchemaPanel
from .erp_panel import ErpPanel

# PromptSelector se define en su propio módulo y se importa aquí para que el
# código de ConfigPanel que la instancia directamente siga funcionando sin
# cambios, y para que sea importable desde ambas rutas:
#   from src.ui.config_panel import PromptSelector   (compatibilidad)
#   from src.ui.prompt_selector import PromptSelector (preferida)
from .prompt_selector import PromptSelector  # noqa: F401


class ConfigPanel(QFrame):
    api_validated = pyqtSignal(bool)
    tab_changed = pyqtSignal(int)

    PROFILES = [
        "Facturas/Contable",
        "Factura (Ecuador/Europa)",
        "Contratos/Texto",
        "Manuscrito (HTR)",
        "Foto Libre",
    ]
    # Archivo de configuración del usuario (persistente)
    _CONFIG_FILE = Path.home() / ".ocr_glm_config.json"

    def _wrap_in_scroll(self, widget: QWidget) -> QScrollArea:
        area = QScrollArea()
        area.setWidgetResizable(True)
        # ensure the widget has no parent when reparenting into the scroll area
        try:
            widget.setParent(None)
        except Exception:
            pass
        area.setWidget(widget)
        return area

    def _enable_paddleocr(self) -> None:
        """Intenta importar PaddleOCR y registrar un backend local."""
        try:
            from src.core.ocr_backends import register_backend
        except Exception:
            QMessageBox.warning(self, "Backend local", "No se pudo acceder al registrador de backends.")
            return

        # intentar importar; si falla, ofrecer instalación
        try:
            import base64
            from PIL import Image
            import io
            import numpy as _np
            import paddleocr
        except Exception as imp_exc:
            ans = QMessageBox.question(
                self,
                "PaddleOCR no encontrado",
                "PaddleOCR no está instalado. ¿Deseas intentar instalarlo ahora? (requiere internet)",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if ans == QMessageBox.StandardButton.Yes:
                try:
                    subprocess.check_call([sys.executable, "-m", "pip", "install", "paddleocr"])
                except Exception as pip_exc:
                    QMessageBox.warning(self, "Instalación Fallida", f"No se pudo instalar PaddleOCR: {pip_exc}")
                    return
                # reintentar import
                try:
                    import paddleocr
                    import base64
                    from PIL import Image
                    import io
                    import numpy as _np
                except Exception as imp_exc2:
                    QMessageBox.warning(self, "PaddleOCR", f"Import tras instalación falló: {imp_exc2}")
                    return
            else:
                return

        # si llegamos aquí, el paquete está disponible
        try:
            from paddleocr import PaddleOCR

            class _PaddleAdapter:
                def __init__(self) -> None:
                    # lazy init: no crear el OCR hasta el primer uso
                    self._ocr = None

                def _ensure_init(self) -> None:
                    if self._ocr is None:
                        # Forzar uso en CPU
                        self._ocr = PaddleOCR(use_angle_cls=True, lang="en", use_gpu=False)

                def process_base64(self, b64: str):
                    try:
                        self._ensure_init()
                        data = base64.b64decode(b64)
                        img = Image.open(io.BytesIO(data)).convert("RGB")
                        arr = _np.array(img)[:, :, ::-1]
                        res = self._ocr.ocr(arr, cls=True)
                        lines = []
                        confidences = []
                        for seg in res:
                            for line in seg:
                                try:
                                    t = line[1][0] if isinstance(line[1], (list, tuple)) else str(line[1])
                                    lines.append(t)
                                    try:
                                        confidences.append(float(line[1][1]))
                                    except Exception:
                                        pass
                                except Exception:
                                    pass
                        text = "\n".join(lines)
                        pt = max(1, len(text) // 4)
                        ct = 0
                        return text, pt, ct
                    except Exception as exc:
                        raise RuntimeError(f"PaddleOCR error: {exc}")

            register_backend("paddle-ocr", lambda: _PaddleAdapter())
            QMessageBox.information(self, "PaddleOCR", "PaddleOCR registrado como backend 'paddle-ocr'.")
            try:
                self._refresh_backend_list()
            except Exception:
                pass
            try:
                self.paddle_btn.setEnabled(False)
                self.paddle_btn.setText("PaddleOCR: Activado")
            except Exception:
                pass
        except Exception as exc:
            QMessageBox.warning(self, "PaddleOCR", f"No se pudo activar PaddleOCR: {exc}")

    def _enable_easyocr(self) -> None:
        """Intenta importar EasyOCR y registrar un backend local."""
        try:
            from src.core.ocr_backends import register_backend
        except Exception:
            QMessageBox.warning(self, "Backend local", "No se pudo acceder al registrador de backends.")
            return

        # intentar importar; si falla, ofrecer instalación
        try:
            import base64
            from PIL import Image
            import io
            import numpy as _np
            import easyocr
        except Exception:
            ans = QMessageBox.question(
                self,
                "EasyOCR no encontrado",
                "EasyOCR no está instalado. ¿Deseas intentar instalarlo ahora? (requiere internet)",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if ans == QMessageBox.StandardButton.Yes:
                try:
                    subprocess.check_call([sys.executable, "-m", "pip", "install", "easyocr"])
                except Exception as pip_exc:
                    QMessageBox.warning(self, "Instalación Fallida", f"No se pudo instalar EasyOCR: {pip_exc}")
                    return
                try:
                    import easyocr
                    import base64
                    from PIL import Image
                    import io
                    import numpy as _np
                except Exception as imp_exc2:
                    QMessageBox.warning(self, "EasyOCR", f"Import tras instalación falló: {imp_exc2}")
                    return
            else:
                return

        try:
            class _EasyAdapter:
                def __init__(self) -> None:
                    # lazy init reader
                    self._reader = None

                def _ensure_init(self) -> None:
                    if self._reader is None:
                        self._reader = easyocr.Reader(["en"], gpu=False)

                def process_base64(self, b64: str):
                    try:
                        self._ensure_init()
                        data = base64.b64decode(b64)
                        img = Image.open(io.BytesIO(data)).convert("RGB")
                        arr = _np.array(img)[:, :, ::-1]
                        res = self._reader.readtext(arr)
                        lines = []
                        confidences = []
                        for r in res:
                            try:
                                lines.append(r[1])
                                try:
                                    confidences.append(float(r[2]))
                                except Exception:
                                    pass
                            except Exception:
                                pass
                        text = "\n".join(lines)
                        pt = max(1, len(text) // 4)
                        ct = 0
                        return text, pt, ct
                    except Exception as exc:
                        raise RuntimeError(f"EasyOCR error: {exc}")

            register_backend("easyocr", lambda: _EasyAdapter())
            QMessageBox.information(self, "EasyOCR", "EasyOCR registrado como backend 'easyocr'.")
            try:
                self._refresh_backend_list()
            except Exception:
                pass
            try:
                self.easyocr_btn.setEnabled(False)
                self.easyocr_btn.setText("EasyOCR: Activado")
            except Exception:
                pass
        except Exception as exc:
            QMessageBox.warning(self, "EasyOCR", f"No se pudo activar EasyOCR: {exc}")

    def _refresh_backend_list(self) -> None:
        """Refresca las opciones del combo `backend_cb` desde el registry de backends."""
        try:
            from src.core.ocr_backends import available_backends
        except Exception:
            return
        try:
            current = self.backend_cb.currentText() if getattr(self, 'backend_cb', None) else None
            backends = available_backends() or []
            # añadir alternativas por defecto si no hay ninguno
            if not backends:
                backends = ["glm", "mistral-ocr-latest", "google-vision", "google-docs", "ocr-local"]
            # actualizar combo conservando selección si es posible
            self.backend_cb.blockSignals(True)
            self.backend_cb.clear()
            self.backend_cb.addItems(sorted(backends))
            if current and current in backends:
                idx = self.backend_cb.findText(current)
                if idx >= 0:
                    self.backend_cb.setCurrentIndex(idx)
            self.backend_cb.blockSignals(False)
        except Exception:
            pass

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("configPanel")
        # storage for backend KPI labels
        self._backend_kpis = {}

        root = QVBoxLayout()
        # Pestañas principales
        self._tabs = QTabWidget()

        # Pestaña Operación (contenedor básico)
        tab_op = QWidget()
        op_lay = QVBoxLayout()
        op_lay.setSpacing(12)
        op_lay.setContentsMargins(12, 12, 12, 12)
        # dejar un poco de respiro alrededor de las pestañas y secciones
        tpl_row = QWidget()
        tpl_vlay = QVBoxLayout()
        tpl_vlay.setContentsMargins(0, 0, 0, 0)
        tpl_vlay.setSpacing(10)
        label_row = QWidget()
        label_lay = QHBoxLayout()
        label_lay.setContentsMargins(0, 0, 0, 0)
        label_lay.setSpacing(8)
        label_lay.addWidget(QLabel("Plantilla Prompt:"))
        self.prompt_template_cb = QComboBox()
        self._load_prompt_templates()
        self.prompt_template_cb.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        label_lay.addWidget(self.prompt_template_cb, stretch=1)
        label_row.setLayout(label_lay)
        tpl_vlay.addWidget(label_row)

        # Reemplazar las 3 acciones por un desplegable de acciones + botón ejecutar
        actions_row = QWidget()
        actions_lay = QHBoxLayout()
        actions_lay.setContentsMargins(0, 0, 0, 0)
        actions_lay.setSpacing(8)
        self.tpl_actions_cb = QComboBox()
        self.tpl_actions_cb.addItems(["Refrescar", "Editar", "Usar como predet."])
        self.tpl_actions_cb.setFixedWidth(220)
        self.tpl_execute_btn = QPushButton("Ejecutar")
        self.tpl_execute_btn.setFixedHeight(36)
        try:
            app = QApplication.instance()
            if app is not None:
                style = app.style()
                self.tpl_execute_btn.setIcon(style.standardIcon(getattr(style, 'SP_ArrowRight')))
        except Exception:
            pass
        def _exec_tpl_action():
            act = self.tpl_actions_cb.currentText()
            if act == "Refrescar":
                self._load_prompt_templates()
            elif act == "Editar":
                self._open_template_editor()
            elif act == "Usar como predet.":
                self._set_selected_as_default()

        self.tpl_execute_btn.clicked.connect(_exec_tpl_action)
        actions_lay.addWidget(self.tpl_actions_cb)
        actions_lay.addWidget(self.tpl_execute_btn)
        actions_row.setLayout(actions_lay)
        tpl_vlay.addWidget(actions_row)

        tpl_row.setLayout(tpl_vlay)
        op_lay.addWidget(tpl_row)
        # Prompt del usuario — SIEMPRE VISIBLE, NUNCA GUARDADO
        # El prompt es específico de cada proyecto/sesión. No se persiste
        # entre ejecuciones: el cliente lo pega cada vez que abre el programa.
        try:
            # Etiqueta informativa
            prompt_label = QLabel("Prompt de extracción (obligatorio — no se guarda al cerrar):")
            prompt_label.setStyleSheet("font-weight: bold; color: #cc6600;")
            op_lay.addWidget(prompt_label)

            self.custom_prompt_input = QTextEdit()
            self.custom_prompt_input.setPlaceholderText(
                "Pega aquí tu prompt completo. El programa lo usará tal cual.\n"
                "Este campo se borra al cerrar — deberás pegarlo de nuevo en cada sesión."
            )
            self.custom_prompt_input.setFixedHeight(180)
            self.custom_prompt_input.setVisible(True)
            # Atributo de compatibilidad (el código legacy comprueba este checkbox)
            self.use_custom_prompt_chk = None

            custom_actions_row = QWidget()
            custom_actions_lay = QHBoxLayout()
            custom_actions_lay.setContentsMargins(0, 0, 0, 0)
            custom_actions_lay.setSpacing(8)
            self.load_custom_prompt_btn = QPushButton("Cargar prompt desde archivo...")
            self.clear_custom_prompt_btn = QPushButton("Limpiar")
            self.load_custom_prompt_btn.setFixedHeight(32)
            self.clear_custom_prompt_btn.setFixedHeight(32)
            self.load_custom_prompt_btn.clicked.connect(self._load_custom_prompt_from_file)
            self.clear_custom_prompt_btn.clicked.connect(self._clear_custom_prompt)
            custom_actions_lay.addWidget(self.load_custom_prompt_btn)
            custom_actions_lay.addWidget(self.clear_custom_prompt_btn)
            custom_actions_lay.addStretch()
            custom_actions_row.setLayout(custom_actions_lay)
            op_lay.addWidget(custom_actions_row)

            op_lay.addWidget(self.custom_prompt_input)
            # NO conectar textChanged a _persist — el prompt nunca se guarda
        except Exception:
            try:
                self.use_custom_prompt_chk = None
                self.custom_prompt_input = QTextEdit()
            except Exception:
                pass
        self.format_cb = QComboBox()
        self.format_cb.addItems(["XLSX", "CSV", "DOCX", "TXT"])
        op_lay.addWidget(self.format_cb)
        self.format_cb.currentTextChanged.connect(lambda _txt: self._persist_prompt_export_settings())
        # Selector de formato de salida
        self.format_cb.setToolTip("Formato de salida: XLSX, CSV, DOCX, TXT")
        # Selector de formato para visualizar resultados OCR en Revisión Visual
        self.ocr_output_cb = QComboBox()
        self.ocr_output_cb.addItems(["JSON", "Markdown"])
        self.ocr_output_cb.setFixedWidth(120)
        self.ocr_output_cb.setToolTip("Formato para visualizar resultados OCR en Revisión Visual")
        op_lay.addWidget(self.ocr_output_cb)
        self.ocr_output_cb.currentTextChanged.connect(lambda _txt: self._persist_prompt_export_settings())

        # Opción: abrir previsualizador automáticamente tras completar lote
        try:
            self.preview_on_batch_chk = QCheckBox("Abrir Previsualizador tras lote")
            # leer valor por defecto desde configuración de usuario
            try:
                cfg = self._load_user_config() or {}
                self.preview_on_batch_chk.setChecked(bool(cfg.get('preview_on_batch', False)))
            except Exception:
                try:
                    self.preview_on_batch_chk.setChecked(False)
                except Exception:
                    pass
            self.preview_on_batch_chk.setToolTip("Si está activado, la aplicación cambiará automáticamente a la pestaña Previsualizador tras cada lote (si corresponde).")
            op_lay.addWidget(self.preview_on_batch_chk)
            # persistir al cambiar
            def _on_toggle_preview_on_batch(checked: bool) -> None:
                try:
                    cfg = self._load_user_config() or {}
                    cfg['preview_on_batch'] = bool(checked)
                    self._save_user_config(cfg)
                except Exception:
                    pass
            self.preview_on_batch_chk.toggled.connect(_on_toggle_preview_on_batch)
        except Exception:
            try:
                self.preview_on_batch_chk = QCheckBox("Abrir Previsualizador tras lote")
            except Exception:
                pass

        # Carpeta / archivo de salida: campo + botón Examinar
        out_row = QWidget()
        out_lay = QHBoxLayout()
        out_lay.setContentsMargins(0, 0, 0, 0)
        out_lay.setSpacing(8)
        out_lay.addWidget(QLabel("Carpeta destino:"))
        self.dst_input = QLineEdit()
        self.dst_input.setPlaceholderText("Selecciona carpeta de salida (ej. C:\\Users\\...)")
        out_lay.addWidget(self.dst_input)
        self.browse_dst_btn = QPushButton("Examinar...")
        self.browse_dst_btn.setFixedHeight(30)
        self.browse_dst_btn.clicked.connect(self._on_select_output_dir)
        out_lay.addWidget(self.browse_dst_btn)
        out_row.setLayout(out_lay)
        op_lay.addWidget(out_row)

        # KPI summary row (tokens current batch, breakdown, monthly total, month cost)
        try:
            kpi_row = QWidget()
            kpi_lay = QHBoxLayout()
            kpi_lay.setContentsMargins(0, 0, 0, 0)
            kpi_lay.setSpacing(12)
            kpi_lay.addWidget(self._make_kpi("Tokens (lote)", "0", "tokensToday"))
            kpi_lay.addWidget(self._make_kpi("Detalle tokens", "0 / 0", "tokenBreakdown"))
            kpi_lay.addWidget(self._make_kpi("Total mes", "0", "monthlyTotal"))
            kpi_lay.addWidget(self._make_kpi("Coste mes", "$0.0000", "monthCost"))
            kpi_row.setLayout(kpi_lay)
            op_lay.addWidget(kpi_row)
        except Exception:
            pass

        # Small monthly chart canvas for tokens summary
        try:
            self._figure = Figure(figsize=(6, 2.2), tight_layout=True)
            self._canvas = FigureCanvasQTAgg(self._figure)
            self._canvas.setMinimumHeight(160)
            op_lay.addWidget(self._canvas)
        except Exception:
            # ensure attributes exist to avoid AttributeError in _refresh_chart
            try:
                self._figure = Figure()
                self._canvas = None
            except Exception:
                self._figure = None
                self._canvas = None

        # Configuraciones guardadas: selector + guardar/cargar
        cfg_row = QWidget()
        cfg_lay = QHBoxLayout()
        cfg_lay.setContentsMargins(0, 0, 0, 0)
        cfg_lay.setSpacing(8)
        cfg_lay.addWidget(QLabel("Configuración guardada:"))
        self.saved_cfg_cb = QComboBox()
        self.saved_cfg_cb.setFixedWidth(220)
        cfg_lay.addWidget(self.saved_cfg_cb)
        self.save_cfg_btn = QPushButton("Guardar configuración...")
        self.save_cfg_btn.setFixedHeight(34)
        self.save_cfg_btn.clicked.connect(self._on_save_named_config_btn)
        cfg_lay.addWidget(self.save_cfg_btn)
        self.load_cfg_btn = QPushButton("Cargar")
        self.load_cfg_btn.setFixedHeight(34)
        self.load_cfg_btn.clicked.connect(self._on_load_named_config_btn)
        cfg_lay.addWidget(self.load_cfg_btn)
        cfg_row.setLayout(cfg_lay)
        op_lay.addWidget(cfg_row)

        # Perfil de Exportación (plantillas ERP / perfiles)
        op_lay.addWidget(QLabel("Perfil de Exportación"))
        self.export_profile_cb = QComboBox()
        self.export_profile_cb.addItems([
            "Exportación Estándar",
            "Plantilla Diario Odoo",
            "Plantilla Facturas Xero",
        ])
        op_lay.addWidget(self.export_profile_cb)

        self.merge_chk = QCheckBox("Unificar en un solo archivo")
        op_lay.addWidget(self.merge_chk)
        # Opción para incluir imágenes en DOCX
        self.include_images_chk = QCheckBox("Incluir imágenes en DOCX")
        self.include_images_chk.setChecked(True)
        op_lay.addWidget(self.include_images_chk)

        # — Perfil de Extracción
        profile_box = QGroupBox("Perfil de Extracción")
        profile_box.setObjectName("profileGroup")
        profile_lay = QVBoxLayout()
        profile_lay.setSpacing(10)
        profile_lay.setContentsMargins(12, 10, 12, 10)
        self._profile_group = QButtonGroup(self)
        for i, name in enumerate(self.PROFILES):
            rb = QRadioButton(name)
            rb.setObjectName("profileRadio")
            if i == 0:
                rb.setChecked(True)
            self._profile_group.addButton(rb, i)
            profile_lay.addWidget(rb)
        profile_box.setLayout(profile_lay)
        op_lay.addWidget(profile_box)

        op_lay.addStretch()
        tab_op.setLayout(op_lay)
        self._tabs.addTab(self._wrap_in_scroll(tab_op), "Operación")

        # ─────────────────────── Pestaña 2: Seguridad ───────────────────────
        tab_sec = QWidget()
        sec_lay = QVBoxLayout()
        sec_lay.setSpacing(18)
        sec_lay.setContentsMargins(18, 18, 18, 18)

        lbl_sec = QLabel("SEGURIDAD Y CREDENCIALES")
        lbl_sec.setObjectName("cardTitle")
        sec_lay.addWidget(lbl_sec)

        # Token + validación — organizados en dos columnas
        token_row = QWidget()
        token_lay = QHBoxLayout()
        token_lay.setContentsMargins(0, 0, 0, 0)
        token_lay.setSpacing(12)
        self.token_input = QLineEdit()
        self.token_input.setPlaceholderText("Introduce tu API Key…")
        self.token_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.token_input.setFixedHeight(36)
        self.show_btn = QPushButton("Mostrar")
        self.show_btn.setFixedWidth(88)
        self.show_btn.setFixedHeight(32)
        self.show_btn.setCheckable(True)
        self.show_btn.toggled.connect(self._toggle_show)
        token_lay.addWidget(self.token_input)
        token_lay.addWidget(self.show_btn)
        token_row.setLayout(token_lay)

        self.validate_btn = QPushButton("✔  Validar API Key")
        self.validate_btn.setObjectName("validateBtn")
        self.validate_btn.setFixedHeight(44)
        self.validate_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.validate_btn.clicked.connect(self.validate_api_key)
        try:
            app = QApplication.instance()
            if app is not None:
                style = app.style()
                self.validate_btn.setIcon(style.standardIcon(getattr(style, 'SP_DialogApplyButton')))
        except Exception:
            pass

        self.status_lbl = QLabel("● Estado: Desconectado")
        self.status_lbl.setObjectName("statusLabel")
        self.status_lbl.setStyleSheet("color: #EF4444")

        # Creamos contenedor de 2 columnas para seguridad
        sec_content = QWidget()
        sec_content_lay = QHBoxLayout()
        sec_content_lay.setSpacing(18)
        sec_content_lay.setContentsMargins(0, 0, 0, 0)

        left_col = QVBoxLayout()
        left_col.setSpacing(15)
        right_col = QVBoxLayout()
        right_col.setSpacing(15)

        # Añadir a la columna izquierda: token, validate, borrar, estado
        left_col.addWidget(token_row)
        left_col.addWidget(self.validate_btn)

        # Botón para borrar la credencial guardada
        self.delete_cred_btn = QPushButton("🗑  Borrar credencial guardada")
        self.delete_cred_btn.setObjectName("deleteCredBtn")
        self.delete_cred_btn.setFixedHeight(36)
        self.delete_cred_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.delete_cred_btn.setStyleSheet("color: #EF4444;")
        self.delete_cred_btn.clicked.connect(self._delete_api_key)
        left_col.addWidget(self.delete_cred_btn)
        left_col.addWidget(self.status_lbl)

        # right column placeholder (motor y procesamiento irán allí)
        sec_content_lay.addLayout(left_col, 1)
        sec_content_lay.addLayout(right_col, 1)
        sec_content.setLayout(sec_content_lay)
        sec_lay.addWidget(sec_content)

        # Selector de backend OCR
        backend_row = QWidget()
        backend_lay = QHBoxLayout()
        backend_lay.setContentsMargins(0, 0, 0, 0)
        backend_lay.setSpacing(12)
        backend_lay.addWidget(QLabel("Motor OCR:"))
        self.backend_cb = QComboBox()
        # Descubrir backends registrados (si el módulo está disponible)
        try:
            from src.core.ocr_backends import available_backends

            backends = available_backends()
            if backends:
                self.backend_cb.addItems(sorted(backends))
            else:
                self.backend_cb.addItems(["glm", "mistral-ocr-latest", "google-vision", "google-docs", "openrouter", "ocr-local"])
        except Exception:
            self.backend_cb.addItems(["glm", "mistral-ocr-latest", "google-vision", "google-docs", "openrouter", "ocr-local"])
        self.backend_cb.setFixedWidth(220)
        backend_lay.addWidget(self.backend_cb)
        # Mistral mode selector (visible only when mistral backend chosen)
        self.mistral_mode_cb = QComboBox()
        self.mistral_mode_cb.addItems([
            "Lote >1000 págs ($0.01/pág)",
            "Estándar ($0.02/pág)",
            "Con Anotaciones ($0.03/pág)",
        ])
        self.mistral_mode_cb.setFixedWidth(260)
        # load persisted mode
        try:
            cfg = self._load_user_config() or {}
            mm = cfg.get("mistral_mode", "standard")
            if mm == "with_annotations":
                self.mistral_mode_cb.setCurrentIndex(2)
            elif mm == "batch":
                self.mistral_mode_cb.setCurrentIndex(0)
            else:
                self.mistral_mode_cb.setCurrentIndex(1)
        except Exception:
            pass
        self.mistral_mode_cb.setVisible((self.backend_cb.currentText() if getattr(self, 'backend_cb', None) else '') == 'mistral-ocr-latest')
        backend_lay.addWidget(self.mistral_mode_cb)
        try:
            def _on_mistral_mode_changed(idx: int) -> None:
                try:
                    cfg = self._load_user_config() or {}
                    if idx == 0:
                        mode = 'batch'
                    elif idx == 2:
                        mode = 'with_annotations'
                    else:
                        mode = 'standard'
                    cfg['mistral_mode'] = mode
                    self._save_user_config(cfg)
                except Exception:
                    pass
            self.mistral_mode_cb.currentIndexChanged.connect(_on_mistral_mode_changed)
        except Exception:
            pass
        backend_row.setLayout(backend_lay)
        right_col.addWidget(backend_row)

        # Botones para activar backends OCR locales (PaddleOCR / EasyOCR)
        local_row = QWidget()
        local_lay = QHBoxLayout()
        local_lay.setContentsMargins(0, 0, 0, 0)
        local_lay.setSpacing(8)
        self.paddle_btn = QPushButton("Habilitar PaddleOCR")
        self.easyocr_btn = QPushButton("Habilitar EasyOCR")
        self.paddle_btn.setFixedHeight(34)
        self.easyocr_btn.setFixedHeight(34)
        local_lay.addWidget(self.paddle_btn)
        local_lay.addWidget(self.easyocr_btn)
        local_row.setLayout(local_lay)
        right_col.addWidget(local_row)

        self.paddle_btn.clicked.connect(self._enable_paddleocr)
        self.easyocr_btn.clicked.connect(self._enable_easyocr)

        # Show/hide mistral mode selector, update placeholder and preload key when backend changes
        try:
            def _on_backend_change(txt: str) -> None:
                try:
                    is_mistral = (txt == 'mistral-ocr-latest')
                    self.mistral_mode_cb.setVisible(is_mistral)
                    _cfg = self._load_user_config() or {}
                    # Mapa backend → (placeholder, clave en cfg, env var)
                    _map = {
                        'mistral-ocr-latest': ("API Key de Mistral…",       "mistral_api_key",      "MISTRAL_API_KEY"),
                        'openrouter':         ("API Key de OpenRouter…",     "openrouter_api_key",   "OPENROUTER_API_KEY"),
                        'openrouter-ocr':     ("API Key de OpenRouter…",     "openrouter_api_key",   "OPENROUTER_API_KEY"),
                        'openai-vision':      ("API Key de OpenAI…",         "openai_api_key",       "OPENAI_API_KEY"),
                        'google-vision':      ("API Key de Google Vision…",  "google_vision_api_key", None),
                        'google-docs':        ("API Key de Google Docs AI…", "google_docs_api_key",  None),
                    }
                    ph, cfg_key, _ = _map.get(txt, ("Introduce tu API Key…", None, None))
                    self.token_input.setPlaceholderText(ph)
                    if not self.token_input.text().strip() and cfg_key:
                        saved = _cfg.get(cfg_key, "")
                        if saved:
                            self.token_input.setText(saved)
                    elif cfg_key is None:
                        # GLM → cargar desde keyring
                        try:
                            if not self.token_input.text().strip():
                                import keyring
                                saved = keyring.get_password("ocr_glm", "api_key") or ""
                                if saved:
                                    self.token_input.setText(saved)
                        except Exception:
                            pass
                except Exception:
                    pass
            self.backend_cb.currentTextChanged.connect(_on_backend_change)
        except Exception:
            pass

        # ── Procesado de Imagen ────────────────────────────────────────────────
        img_group = QGroupBox("Procesado de Imagen")
        img_group.setObjectName("settingsGroup")
        img_grp_lay = QVBoxLayout()
        img_grp_lay.setSpacing(12)
        img_grp_lay.setContentsMargins(12, 16, 12, 12)
        # Distribuir checkboxes en 3 columnas para mejor estética
        from PyQt6.QtWidgets import QGridLayout
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)

        # checkbox shared: use_cache_chk debe existir antes de usarlo en la rejilla
        try:
            self.use_cache_chk
        except Exception:
            self.use_cache_chk = QCheckBox("Activar caché local (evita re-OCR)")
            self.use_cache_chk.setChecked(True)

        self.preprocess_chk = QCheckBox("Preprocesado (OpenCV)")
        self.preprocess_chk.setChecked(True)
        self.use_cache_chk.setToolTip("Activar caché local (evita re-OCR)")
        # preparar otros toggles
        try:
            self.prefer_local_chk
        except Exception:
            self.prefer_local_chk = QCheckBox("Preferir OCR local para documentos fáciles")
            self.prefer_local_chk.setChecked(True)
        self.ocr_local_only_chk = QCheckBox("Forzar OCR local para básicos")
        self.ocr_local_only_chk.setChecked(False)
        # Modo ligero: reduce resolución máxima para limitar uso de RAM
        try:
            import os
        except Exception:
            os = None
        self.light_mode_chk = QCheckBox("Modo ligero (limita uso RAM)")
        self.light_mode_chk.setChecked(True)

        def _toggle_light(checked: bool) -> None:
            if os is None:
                return
            # reducir a 1280px cuando esté en modo ligero
            try:
                os.environ['OCR_MAX_PX'] = '1280' if checked else '1920'
            except Exception:
                pass

        # aplicar valor inicial
        try:
            if os is not None:
                os.environ.setdefault('OCR_MAX_PX', '1280')
        except Exception:
            pass

        self.light_mode_chk.toggled.connect(_toggle_light)

        # ── Toggle validación contable ────────────────────────────────────
        self.accounting_validation_chk = QCheckBox("📊 Validación Contable")
        self.accounting_validation_chk.setChecked(False)
        self.accounting_validation_chk.setToolTip(
            "Activa la reconciliación contable multi-documento tras exportar.\n"
            "Verifica suma de líneas vs total, secuencia de fechas, PO matching y SKUs."
        )

        # ── Toggle enrutamiento IA ─────────────────────────────────────────
        self.smart_routing_chk = QCheckBox("🧠 Enrutamiento IA")
        self.smart_routing_chk.setChecked(False)
        self.smart_routing_chk.setToolTip(
            "Detecta automáticamente el tipo de documento (factura, partitura, \n"
            "matemáticas, legal, etc.) y selecciona el pipeline, modelo y \n"
            "preprocesado óptimos para cada archivo."
        )

        grid.addWidget(self.preprocess_chk, 0, 0)
        grid.addWidget(self.use_cache_chk, 0, 1)
        grid.addWidget(self.prefer_local_chk, 0, 2)
        grid.addWidget(self.ocr_local_only_chk, 1, 0)
        grid.addWidget(self.light_mode_chk, 1, 1)
        grid.addWidget(self.accounting_validation_chk, 1, 2)
        grid.addWidget(self.smart_routing_chk, 2, 0)

        img_grp_lay.addLayout(grid)

        upscale_row = QWidget()
        up_lay = QHBoxLayout()
        up_lay.setContentsMargins(0, 0, 0, 0)
        up_lay.setSpacing(12)
        up_lay.addWidget(QLabel("Escala de imagen:"))
        self.upscale_cb = QComboBox()
        self.upscale_cb.addItems(["Ninguna", "x2", "x3", "x4"])
        self.upscale_cb.setCurrentIndex(0)
        up_lay.addWidget(self.upscale_cb, stretch=1)
        upscale_row.setLayout(up_lay)
        img_grp_lay.addWidget(upscale_row)

        img_group.setLayout(img_grp_lay)
        right_col.addWidget(img_group)

        # Selector de plantilla de prompt
        # Plantilla prompt: combo (full width) + fila de acciones grande
        tpl_row = QWidget()
        tpl_vlay = QVBoxLayout()
        tpl_vlay.setContentsMargins(0, 0, 0, 0)
        tpl_vlay.setSpacing(8)
        label_row = QWidget()
        label_lay = QHBoxLayout()
        label_lay.setContentsMargins(0, 0, 0, 0)
        label_lay.setSpacing(8)
        label_lay.addWidget(QLabel("Plantilla Prompt:"))
        self.prompt_template_cb = QComboBox()
        self._load_prompt_templates()
        self.prompt_template_cb.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        label_lay.addWidget(self.prompt_template_cb, stretch=1)
        label_row.setLayout(label_lay)
        tpl_vlay.addWidget(label_row)

        # Acciones sobre plantilla: combo de acciones + ejecutar
        actions_row = QWidget()
        actions_lay = QHBoxLayout()
        actions_lay.setContentsMargins(0, 0, 0, 0)
        actions_lay.setSpacing(12)
        self.tpl_actions_cb = QComboBox()
        self.tpl_actions_cb.addItems(["Refrescar", "Editar", "Usar como predet."])
        self.tpl_actions_cb.setFixedWidth(220)
        tpl_execute = QPushButton("Ejecutar")
        tpl_execute.setFixedHeight(36)
        tpl_execute.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        try:
            app = QApplication.instance()
            if app is not None:
                style = app.style()
                tpl_execute.setIcon(style.standardIcon(getattr(style, 'SP_ArrowRight')))
        except Exception:
            pass
        def _exec_tpl_action_local():
            act = self.tpl_actions_cb.currentText()
            if act == "Refrescar":
                self._load_prompt_templates()
            elif act == "Editar":
                self._open_template_editor()
            elif act == "Usar como predet.":
                self._set_selected_as_default()
        tpl_execute.clicked.connect(_exec_tpl_action_local)
        actions_lay.addWidget(self.tpl_actions_cb)
        actions_lay.addWidget(tpl_execute)
        actions_row.setLayout(actions_lay)
        tpl_vlay.addWidget(actions_row)

        tpl_row.setLayout(tpl_vlay)
        left_col.addWidget(tpl_row)

        # ── Post‑OCR: elegir mapeo determinista o IA ─────────────────────────
        post_row = QGroupBox("Post‑OCR / Normalización")
        post_row.setObjectName("postocrGroup")
        post_lay = QVBoxLayout()
        post_lay.setSpacing(8)
        post_lay.setContentsMargins(12, 8, 12, 8)

        # Opción: usar IA para extracción/normalización
        self.use_ia_chk = QCheckBox("Usar IA para post‑procesado (extracción/normalización)")
        self.use_ia_chk.setChecked(False)
        self.use_ia_chk.toggled.connect(self._on_toggle_use_ia)
        post_lay.addWidget(self.use_ia_chk)

        model_row = QWidget()
        model_lay = QHBoxLayout()
        model_lay.setContentsMargins(0, 0, 0, 0)
        model_lay.setSpacing(8)
        model_lay.addWidget(QLabel("Modelo IA:"))
        self.postocr_model_cb = QComboBox()
        # proveer opciones por defecto; el usuario podrá configurar otras
        self.postocr_model_cb.addItems([
            "gpt-4o-mini",
            "gpt-4o",
            "gpt-4o-realtime",
            "local-ner",
        ])
        self.postocr_model_cb.setFixedWidth(260)
        self.postocr_model_cb.currentTextChanged.connect(self._on_model_changed)
        model_lay.addWidget(self.postocr_model_cb)
        model_row.setLayout(model_lay)
        post_lay.addWidget(model_row)

        # Botón para probar el pipeline (opera en JSON de ejemplo)
        self.postocr_test_btn = QPushButton("Probar extracción")
        self.postocr_test_btn.setFixedHeight(34)
        self.postocr_test_btn.clicked.connect(self._on_postocr_test)
        post_lay.addWidget(self.postocr_test_btn)

        post_row.setLayout(post_lay)
        left_col.addWidget(post_row)
        # Credenciales Google (archivo JSON de cuenta de servicio)
        # Credenciales Google: input full width + botón guardar en segunda línea
        g_row = QWidget()
        g_vlay = QVBoxLayout()
        g_vlay.setContentsMargins(0, 0, 0, 0)
        g_vlay.setSpacing(6)

        input_row = QWidget()
        input_lay = QHBoxLayout()
        input_lay.setContentsMargins(0, 0, 0, 0)
        input_lay.setSpacing(8)
        input_lay.addWidget(QLabel("Credenciales Google (JSON):"))
        self.google_creds_input = QLineEdit()
        self.google_creds_input.setPlaceholderText("Ruta a JSON de cuenta de servicio…")
        self.google_creds_input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        g_browse = QPushButton("Examinar")
        g_browse.setFixedWidth(100)
        g_browse.setFixedHeight(32)
        g_browse.clicked.connect(self._browse_google_creds)
        input_lay.addWidget(self.google_creds_input)
        input_lay.addWidget(g_browse)
        input_row.setLayout(input_lay)
        g_vlay.addWidget(input_row)

        save_row = QWidget()
        save_lay = QHBoxLayout()
        save_lay.setContentsMargins(0, 0, 0, 0)
        save_lay.setSpacing(8)
        g_save = QPushButton("Guardar credenciales")
        g_save.setObjectName("validateBtn")
        g_save.setFixedHeight(40)
        g_save.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        try:
            app = QApplication.instance()
            if app is not None:
                style = app.style()
                g_save.setIcon(style.standardIcon(getattr(style, 'SP_DialogSaveButton')))
        except Exception:
            pass
        g_save.clicked.connect(self._save_google_creds)
        save_lay.addWidget(g_save)
        save_row.setLayout(save_lay)
        g_vlay.addWidget(save_row)

        g_row.setLayout(g_vlay)
        right_col.addWidget(g_row)

        # ── Caché y OCR Local ─────────────────────────────────────────────────
        cache_group = QGroupBox("Caché y OCR Local")
        cache_group.setObjectName("settingsGroup")
        cg_lay = QVBoxLayout()
        cg_lay.setSpacing(12)
        cg_lay.setContentsMargins(12, 16, 12, 12)

        # use_cache_chk ya fue creada más arriba en caso necesario
        try:
            self.use_cache_chk.setChecked(True)
        except Exception:
            self.use_cache_chk = QCheckBox("Activar caché local (evita re-OCR)")
            self.use_cache_chk.setChecked(True)
        cg_lay.addWidget(self.use_cache_chk)

        conf_row = QWidget()
        conf_lay = QHBoxLayout()
        conf_lay.setContentsMargins(0, 0, 0, 0)
        conf_lay.setSpacing(12)
        conf_lay.addWidget(QLabel("Umbral de confianza:"))
        self.local_conf_spin = QDoubleSpinBox()
        self.local_conf_spin.setRange(0.0, 1.0)
        self.local_conf_spin.setSingleStep(0.05)
        self.local_conf_spin.setValue(0.80)
        self.local_conf_spin.setFixedWidth(80)
        conf_lay.addWidget(self.local_conf_spin)
        conf_lay.addStretch()
        conf_row.setLayout(conf_lay)
        cg_lay.addWidget(conf_row)

        self.prefer_local_chk = QCheckBox("Preferir OCR local para documentos fáciles")
        self.prefer_local_chk.setChecked(True)
        cg_lay.addWidget(self.prefer_local_chk)

        ci_row = QWidget()
        ci_lay = QHBoxLayout()
        ci_lay.setContentsMargins(0, 6, 0, 0)
        ci_lay.setSpacing(10)
        ci_lay.addWidget(QLabel("Cache local:"))
        self.cache_info_lbl = QLabel("Vacía")
        ci_lay.addWidget(self.cache_info_lbl)
        ci_lay.addStretch()
        self.clear_cache_btn = QPushButton("🗑  Limpiar caché")
        self.clear_cache_btn.setObjectName("clearBtn")
        self.clear_cache_btn.setFixedHeight(34)
        self.clear_cache_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.clear_cache_btn.clicked.connect(self._clear_cache_clicked)
        ci_lay.addWidget(self.clear_cache_btn)
        ci_row.setLayout(ci_lay)
        cg_lay.addWidget(ci_row)

        cache_group.setLayout(cg_lay)
        left_col.addWidget(cache_group)

        # Añadir espaciado generoso al final
        sec_lay.addStretch()
        sec_lay.setSpacing(18)
        sec_lay.setContentsMargins(18, 18, 18, 18)
        tab_sec.setLayout(sec_lay)
        self._tabs.addTab(self._wrap_in_scroll(tab_sec), "Seguridad")

        # ─────────────────────── Pestaña: Modelos IA ─────────────────────────
        tab_models = QWidget()
        models_lay = QVBoxLayout()
        models_lay.setSpacing(16)
        models_lay.setContentsMargins(18, 18, 18, 18)

        _lbl_models = QLabel("CONFIGURACIÓN DE MODELOS IA")
        _lbl_models.setObjectName("cardTitle")
        models_lay.addWidget(_lbl_models)

        # ── Sección 1: IA para OCR (Visión) ──────────────────────────────────
        ocr_ia_box = QGroupBox("🔍  IA para OCR / Visión")
        ocr_ia_box.setObjectName("settingsGroup")
        ocr_ia_lay = QVBoxLayout()
        ocr_ia_lay.setSpacing(10)
        ocr_ia_lay.setContentsMargins(14, 14, 14, 14)

        # Proveedor OCR
        _prov_ocr_row = QWidget()
        _prov_ocr_lay = QHBoxLayout()
        _prov_ocr_lay.setContentsMargins(0, 0, 0, 0)
        _prov_ocr_lay.setSpacing(10)
        _prov_ocr_lay.addWidget(QLabel("Proveedor:"))
        self.ocr_provider_cb = QComboBox()
        self.ocr_provider_cb.addItems([
            "Mistral OCR",
            "GLM-4V (ZhipuAI)",
            "Google Vision API",
            "Google Document AI",
            "OpenAI GPT-4o Vision",
            "OpenRouter (Visión)",
            "Azure AI Vision",
            "OCR Local (PaddleOCR)",
            "OCR Local (EasyOCR)",
            "OCR Local (Tesseract)",
        ])
        self.ocr_provider_cb.setFixedWidth(260)
        _prov_ocr_lay.addWidget(self.ocr_provider_cb)
        _prov_ocr_lay.addStretch()
        _prov_ocr_row.setLayout(_prov_ocr_lay)
        ocr_ia_lay.addWidget(_prov_ocr_row)

        # Modelo OCR personalizado
        _model_ocr_row = QWidget()
        _model_ocr_lay = QHBoxLayout()
        _model_ocr_lay.setContentsMargins(0, 0, 0, 0)
        _model_ocr_lay.setSpacing(10)
        _model_ocr_lay.addWidget(QLabel("Modelo/Endpoint:"))
        self.ocr_model_input = QLineEdit()
        self.ocr_model_input.setPlaceholderText("ej. glm-4v-plus, mistral-ocr-latest, gpt-4o …")
        self.ocr_model_input.setFixedHeight(32)
        _model_ocr_lay.addWidget(self.ocr_model_input)
        _model_ocr_row.setLayout(_model_ocr_lay)
        ocr_ia_lay.addWidget(_model_ocr_row)

        # Token / API Key OCR
        _tok_ocr_row = QWidget()
        _tok_ocr_lay = QHBoxLayout()
        _tok_ocr_lay.setContentsMargins(0, 0, 0, 0)
        _tok_ocr_lay.setSpacing(10)
        _tok_ocr_lay.addWidget(QLabel("API Key / Token:"))
        self.ocr_token_input = QLineEdit()
        self.ocr_token_input.setPlaceholderText("API key del proveedor OCR …")
        self.ocr_token_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.ocr_token_input.setFixedHeight(32)
        _show_ocr_tok = QPushButton("👁")
        _show_ocr_tok.setFixedSize(32, 32)
        _show_ocr_tok.setCheckable(True)
        _show_ocr_tok.toggled.connect(
            lambda on: self.ocr_token_input.setEchoMode(
                QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password
            )
        )
        _tok_ocr_lay.addWidget(self.ocr_token_input)
        _tok_ocr_lay.addWidget(_show_ocr_tok)
        _tok_ocr_row.setLayout(_tok_ocr_lay)
        ocr_ia_lay.addWidget(_tok_ocr_row)

        # Archivo JSON de credenciales (Google, Azure, etc.)
        _json_ocr_row = QWidget()
        _json_ocr_lay = QHBoxLayout()
        _json_ocr_lay.setContentsMargins(0, 0, 0, 0)
        _json_ocr_lay.setSpacing(10)
        _json_ocr_lay.addWidget(QLabel("Credenciales JSON:"))
        self.ocr_json_input = QLineEdit()
        self.ocr_json_input.setPlaceholderText("Ruta al archivo .json de credenciales (opcional) …")
        self.ocr_json_input.setFixedHeight(32)
        _browse_ocr_json = QPushButton("Examinar…")
        _browse_ocr_json.setFixedHeight(32)
        def _browse_ocr_creds():
            from PyQt6.QtWidgets import QFileDialog
            path, _ = QFileDialog.getOpenFileName(
                self, "Credenciales OCR", "", "JSON (*.json);;Todos (*)"
            )
            if path:
                self.ocr_json_input.setText(path)
        _browse_ocr_json.clicked.connect(_browse_ocr_creds)
        _json_ocr_lay.addWidget(self.ocr_json_input)
        _json_ocr_lay.addWidget(_browse_ocr_json)
        _json_ocr_row.setLayout(_json_ocr_lay)
        ocr_ia_lay.addWidget(_json_ocr_row)

        ocr_ia_box.setLayout(ocr_ia_lay)
        models_lay.addWidget(ocr_ia_box)

        # ── Sección 2: IA para Razonamiento / Post-procesado ─────────────────
        reason_box = QGroupBox("🧠  IA para Razonamiento / Post-procesado")
        reason_box.setObjectName("settingsGroup")
        reason_lay = QVBoxLayout()
        reason_lay.setSpacing(10)
        reason_lay.setContentsMargins(14, 14, 14, 14)

        # Proveedor razonamiento
        _prov_r_row = QWidget()
        _prov_r_lay = QHBoxLayout()
        _prov_r_lay.setContentsMargins(0, 0, 0, 0)
        _prov_r_lay.setSpacing(10)
        _prov_r_lay.addWidget(QLabel("Proveedor:"))
        self.reason_provider_cb = QComboBox()
        self.reason_provider_cb.addItems([
            "Google Gemini Flash (gratuito)",
            "Google Gemini Pro",
            "OpenAI GPT-4o",
            "Qwen (Alibaba Cloud)",
            "DeepSeek",
            "Mistral Large",
            "OpenRouter",
            "Anthropic (Claude 3.5)",
            "GLM-4 (ZhipuAI)",
            "Azure OpenAI",
            "Ollama (local)",
            "LM Studio (local)",
        ])
        self.reason_provider_cb.setFixedWidth(260)
        _prov_r_lay.addWidget(self.reason_provider_cb)
        _prov_r_lay.addStretch()
        _prov_r_row.setLayout(_prov_r_lay)
        reason_lay.addWidget(_prov_r_row)

        # Modelo razonamiento
        _model_r_row = QWidget()
        _model_r_lay = QHBoxLayout()
        _model_r_lay.setContentsMargins(0, 0, 0, 0)
        _model_r_lay.setSpacing(10)
        _model_r_lay.addWidget(QLabel("Modelo/Endpoint:"))
        self.reason_model_input = QLineEdit()
        self.reason_model_input.setPlaceholderText("ej. deepseek-v4-flash, o3-mini, claude-3-5-sonnet, gemini-2.0-flash …")
        self.reason_model_input.setFixedHeight(32)
        _model_r_lay.addWidget(self.reason_model_input)
        _model_r_row.setLayout(_model_r_lay)
        reason_lay.addWidget(_model_r_row)

        def _sync_reason_model_default(provider_name: str) -> None:
            try:
                current = self.reason_model_input.text().strip()
                if provider_name == "DeepSeek" and not current:
                    self.reason_model_input.setText("deepseek-v4-flash")
            except Exception:
                pass

        self.reason_provider_cb.currentTextChanged.connect(_sync_reason_model_default)

        # Token / API Key razonamiento
        _tok_r_row = QWidget()
        _tok_r_lay = QHBoxLayout()
        _tok_r_lay.setContentsMargins(0, 0, 0, 0)
        _tok_r_lay.setSpacing(10)
        _tok_r_lay.addWidget(QLabel("API Key / Token:"))
        self.reason_token_input = QLineEdit()
        self.reason_token_input.setPlaceholderText("API key del proveedor de razonamiento …")
        self.reason_token_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.reason_token_input.setFixedHeight(32)
        _show_r_tok = QPushButton("👁")
        _show_r_tok.setFixedSize(32, 32)
        _show_r_tok.setCheckable(True)
        _show_r_tok.toggled.connect(
            lambda on: self.reason_token_input.setEchoMode(
                QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password
            )
        )
        _tok_r_lay.addWidget(self.reason_token_input)
        _tok_r_lay.addWidget(_show_r_tok)
        _tok_r_row.setLayout(_tok_r_lay)
        reason_lay.addWidget(_tok_r_row)

        # URL base (para Ollama / LM Studio / Azure)
        _base_r_row = QWidget()
        _base_r_lay = QHBoxLayout()
        _base_r_lay.setContentsMargins(0, 0, 0, 0)
        _base_r_lay.setSpacing(10)
        _base_r_lay.addWidget(QLabel("URL base:"))
        self.reason_base_url_input = QLineEdit()
        self.reason_base_url_input.setPlaceholderText("ej. http://localhost:11434  (vacío = proveedor oficial)")
        self.reason_base_url_input.setFixedHeight(32)
        _base_r_lay.addWidget(self.reason_base_url_input)
        _base_r_row.setLayout(_base_r_lay)
        reason_lay.addWidget(_base_r_row)

        # Archivo JSON de credenciales razonamiento
        _json_r_row = QWidget()
        _json_r_lay = QHBoxLayout()
        _json_r_lay.setContentsMargins(0, 0, 0, 0)
        _json_r_lay.setSpacing(10)
        _json_r_lay.addWidget(QLabel("Credenciales JSON:"))
        self.reason_json_input = QLineEdit()
        self.reason_json_input.setPlaceholderText("Ruta al archivo .json de credenciales (opcional) …")
        self.reason_json_input.setFixedHeight(32)
        _browse_r_json = QPushButton("Examinar…")
        _browse_r_json.setFixedHeight(32)
        def _browse_reason_creds():
            from PyQt6.QtWidgets import QFileDialog
            path, _ = QFileDialog.getOpenFileName(
                self, "Credenciales Razonamiento", "", "JSON (*.json);;Todos (*)"
            )
            if path:
                self.reason_json_input.setText(path)
        _browse_r_json.clicked.connect(_browse_reason_creds)
        _json_r_lay.addWidget(self.reason_json_input)
        _json_r_lay.addWidget(_browse_r_json)
        _json_r_row.setLayout(_json_r_lay)
        reason_lay.addWidget(_json_r_row)

        reason_box.setLayout(reason_lay)
        models_lay.addWidget(reason_box)

        # ── Sección 3: Guardar / Cargar config de modelos ────────────────────
        _save_models_row = QWidget()
        _save_models_lay = QHBoxLayout()
        _save_models_lay.setContentsMargins(0, 0, 0, 0)
        _save_models_lay.setSpacing(10)
        _save_models_btn = QPushButton("💾  Guardar configuración de modelos")
        _save_models_btn.setFixedHeight(36)
        _load_models_btn = QPushButton("📂  Cargar")
        _load_models_btn.setFixedHeight(36)

        def _save_models_cfg():
            cfg_data = self._load_user_config() or {}
            cfg_data["ocr_provider"]    = self.ocr_provider_cb.currentText()
            cfg_data["ocr_model"]       = self.ocr_model_input.text().strip()
            cfg_data["ocr_token"]       = self.ocr_token_input.text().strip()
            cfg_data["ocr_json"]        = self.ocr_json_input.text().strip()
            cfg_data["reason_provider"] = self.reason_provider_cb.currentText()
            cfg_data["reason_model"]    = self.reason_model_input.text().strip()
            cfg_data["reason_token"]    = self.reason_token_input.text().strip()
            cfg_data["reason_base_url"] = self.reason_base_url_input.text().strip()
            cfg_data["reason_json"]     = self.reason_json_input.text().strip()
            try:
                # Validación heurística: si model indicado difiere del default, avisar al usuario
                try:
                    from src.core.structuring_engine import StructuringEngine
                    prov = cfg_data.get("reason_provider", "")
                    mdl = cfg_data.get("reason_model", "")
                    # construir engine mínimamente para comprobar el modelo por defecto
                    try:
                        eng = StructuringEngine(provider=prov, api_key=cfg_data.get("reason_token", ""), model=mdl, base_url=cfg_data.get("reason_base_url", ""))
                        default_model = eng._model
                    except Exception:
                        default_model = None
                except Exception:
                    default_model = None

                self._save_user_config(cfg_data)
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.information(self, "Modelos IA", "Configuración guardada correctamente.")
                # Si hay desajuste entre modelo configurado y default conocido, mostrar aviso no bloqueante
                try:
                    if default_model and cfg_data.get("reason_model") and cfg_data.get("reason_model") != default_model:
                        QMessageBox.information(
                            self,
                            "Atención modelo",
                            f"Has configurado el modelo '{cfg_data.get('reason_model')}', el modelo por defecto para el proveedor es '{default_model}'.\nAsegúrate de que el modelo existe en tu proveedor para evitar errores 'Model Not Exist'.",
                        )
                except Exception:
                    pass
            except Exception as _e:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.warning(self, "Error", str(_e))

        def _load_models_cfg():
            cfg_data = self._load_user_config() or {}
            saved_provider = cfg_data.get("ocr_provider", "")
            # Auto-seleccionar Mistral si hay clave Mistral y no hay clave GLM guardada,
            # o si el proveedor guardado es GLM pero la clave GLM no está disponible.
            _has_mistral_key = bool(cfg_data.get("mistral_api_key", "").strip())
            _has_glm_key = bool(cfg_data.get("api_key", "").strip())
            _provider_is_glm = "glm" in saved_provider.lower() or "zhipu" in saved_provider.lower()
            if _provider_is_glm and _has_mistral_key and not _has_glm_key:
                saved_provider = "Mistral OCR"
            if saved_provider:
                idx = self.ocr_provider_cb.findText(saved_provider)
                if idx >= 0:
                    self.ocr_provider_cb.setCurrentIndex(idx)
            self.ocr_model_input.setText(cfg_data.get("ocr_model", ""))
            self.ocr_token_input.setText(cfg_data.get("ocr_token", ""))
            self.ocr_json_input.setText(cfg_data.get("ocr_json", ""))
            if "reason_provider" in cfg_data:
                idx = self.reason_provider_cb.findText(cfg_data["reason_provider"])
                if idx >= 0:
                    self.reason_provider_cb.setCurrentIndex(idx)
            saved_model = cfg_data.get("reason_model", "")
            # Migrar nombres de modelo antiguos
            _model_migrations = {
                "deepseek-chat": "deepseek-v4-flash",
                "deep seek": "deepseek-v4-flash",
            }
            if saved_model in _model_migrations:
                saved_model = _model_migrations[saved_model]
            if saved_model:
                self.reason_model_input.setText(saved_model)
            self.reason_token_input.setText(cfg_data.get("reason_token", ""))
            self.reason_base_url_input.setText(cfg_data.get("reason_base_url", ""))
            self.reason_json_input.setText(cfg_data.get("reason_json", ""))

        _save_models_btn.clicked.connect(_save_models_cfg)
        _load_models_btn.clicked.connect(_load_models_cfg)
        _save_models_lay.addWidget(_save_models_btn)
        _save_models_lay.addWidget(_load_models_btn)

        _clear_models_btn = QPushButton("🗑  Borrar tokens guardados")
        _clear_models_btn.setFixedHeight(36)
        _clear_models_btn.setStyleSheet("color: #EF4444;")

        def _clear_models_cfg():
            from PyQt6.QtWidgets import QMessageBox
            reply = QMessageBox.question(
                self, "Borrar tokens",
                "¿Borrar los tokens OCR y de razonamiento guardados en el perfil?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            cfg_data = self._load_user_config() or {}
            for k in ("ocr_token", "reason_token", "openrouter_api_key",
                      "openai_api_key", "google_vision_api_key",
                      "google_docs_api_key", "mistral_api_key"):
                cfg_data.pop(k, None)
            self._save_user_config(cfg_data)
            for w in (self.ocr_token_input, self.reason_token_input):
                try:
                    w.clear()
                except Exception:
                    pass
            QMessageBox.information(self, "Tokens borrados", "Tokens eliminados del perfil.")

        _clear_models_btn.clicked.connect(_clear_models_cfg)
        _save_models_lay.addWidget(_clear_models_btn)
        _save_models_row.setLayout(_save_models_lay)
        models_lay.addWidget(_save_models_row)

        models_lay.addStretch()
        tab_models.setLayout(models_lay)
        self._tabs.addTab(self._wrap_in_scroll(tab_models), "🤖 Modelos IA")

        # Cargar valores guardados al abrir
        try:
            _load_models_cfg()
        except Exception:
            pass

        # ───────────────────────── Pestaña 3: Telemetría ─────────────────────
        try:
            from .telemetry_panel import TelemetryPanel
        except Exception:
            from src.ui.telemetry_panel import TelemetryPanel

        self.telemetry_panel = TelemetryPanel()
        try:
            self.telemetry_panel.refresh_requested.connect(lambda: None)
        except Exception:
            pass
        self._tabs.addTab(self._wrap_in_scroll(self.telemetry_panel), "Telemetría")

        # ─────────────────────── Pestaña 4: Esquema de Datos ────────────────
        self.schema_panel = SchemaPanel()
        self._tabs.addTab(self._wrap_in_scroll(self.schema_panel), "Esquema")

        # ───────────────────── Pestaña 5: Integración ERP ───────────────
        self.erp_panel = ErpPanel()
        self._tabs.addTab(self._wrap_in_scroll(self.erp_panel), "Integración ERP")

        # ─────────────────── Pestaña 6: Prompts ──────────────────────────────
        self.prompt_selector = PromptSelector()

        # Fila para seleccionar archivo de prompt externo y carpeta de plantillas
        try:
            select_row = QWidget()
            select_lay = QVBoxLayout()
            select_lay.setContentsMargins(0, 0, 0, 0)
            select_lay.setSpacing(8)

            # Archivo prompt externo
            file_row = QWidget()
            file_lay = QHBoxLayout()
            file_lay.setContentsMargins(0, 0, 0, 0)
            file_lay.setSpacing(8)
            file_lay.addWidget(QLabel("Archivo Prompt (opcional):"))
            self.external_prompt_file_input = QLineEdit()
            self.external_prompt_file_input.setPlaceholderText("Selecciona un archivo .txt/.tpl que contenga el prompt…")
            self.external_prompt_file_input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            file_lay.addWidget(self.external_prompt_file_input)
            browse_prompt_file = QPushButton("Examinar...")
            browse_prompt_file.setFixedWidth(120)
            def _browse_external_prompt():
                p, _ = QFileDialog.getOpenFileName(self, "Seleccionar archivo de prompt", "", "Plantillas (*.tpl *.txt);;Todos (*)")
                if p:
                    self.external_prompt_file_input.setText(p)
                    try:
                        cfg = self._load_user_config() or {}
                        cfg["external_prompt_file"] = p
                        self._save_user_config(cfg)
                        QMessageBox.information(self, "Prompt externo", "Ruta guardada. Este archivo podrá usarse como prompt externo.")
                    except Exception:
                        pass
            browse_prompt_file.clicked.connect(_browse_external_prompt)
            file_lay.addWidget(browse_prompt_file)
            file_row.setLayout(file_lay)
            select_lay.addWidget(file_row)

            # Carpeta de plantillas
            dir_row = QWidget()
            dir_lay = QHBoxLayout()
            dir_lay.setContentsMargins(0, 0, 0, 0)
            dir_lay.setSpacing(8)
            dir_lay.addWidget(QLabel("Carpeta de plantillas (opcional):"))
            self.templates_dir_input = QLineEdit()
            self.templates_dir_input.setPlaceholderText("Selecciona carpeta que contiene plantillas (.tpl/.txt)")
            self.templates_dir_input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            dir_lay.addWidget(self.templates_dir_input)
            browse_templates_dir = QPushButton("Examinar carpeta...")
            browse_templates_dir.setFixedWidth(160)
            def _browse_templates_dir():
                p = QFileDialog.getExistingDirectory(self, "Seleccionar carpeta de plantillas", "")
                if p:
                    self.templates_dir_input.setText(p)
                    try:
                        cfg = self._load_user_config() or {}
                        cfg["prompt_templates_dir"] = p
                        self._save_user_config(cfg)
                        # recargar lista de plantillas desde la nueva carpeta
                        try:
                            self._load_prompt_templates()
                        except Exception:
                            pass
                        QMessageBox.information(self, "Carpeta plantillas", "Carpeta de plantillas guardada y recargada.")
                    except Exception:
                        pass
            browse_templates_dir.clicked.connect(_browse_templates_dir)
            dir_lay.addWidget(browse_templates_dir)
            dir_row.setLayout(dir_lay)
            select_lay.addWidget(dir_row)

            select_row.setLayout(select_lay)
        except Exception:
            select_row = None

        def _on_prompt_selected(rel_path: str) -> None:
            """Sincroniza prompt_template_cb con la selección del árbol."""
            try:
                cb = self.prompt_template_cb
                idx = cb.findText(rel_path)
                if idx < 0:
                    cb.addItem(rel_path)
                    idx = cb.findText(rel_path)
                if idx >= 0:
                    cb.blockSignals(True)
                    cb.setCurrentIndex(idx)
                    cb.blockSignals(False)
                    # Emitir manualmente para que el resto del pipeline lo reciba
                    cb.currentTextChanged.emit(rel_path)
            except Exception:
                pass
            # Persistir perfil activo
            try:
                cfg_data = self._load_user_config() or {}
                cfg_data["active_prompt_profile"] = rel_path
                self._save_user_config(cfg_data)
            except Exception:
                pass

        self.prompt_selector.prompt_selected.connect(_on_prompt_selected)

        # Tab de prompts
        prompts_tab = QWidget()
        pt_lay = QVBoxLayout()
        pt_lay.setContentsMargins(0, 0, 0, 0)
        # añadir selector de archivo/carpeta si fue creado
        try:
            if select_row is not None:
                pt_lay.addWidget(select_row)
        except Exception:
            pass
        pt_lay.addWidget(self.prompt_selector)
        prompts_tab.setLayout(pt_lay)
        self._tabs.addTab(self._wrap_in_scroll(prompts_tab), "Prompts")

        root.addWidget(self._tabs)
        self.setLayout(root)
        # Cargar configuración específica de Post‑OCR
        try:
            self._load_postocr_settings()
        except Exception:
            pass
        try:
            self._refresh_saved_configs()
        except Exception:
            pass
        try:
            self._load_prompt_export_settings()
        except Exception:
            pass
        # Inicializar estado de caché
        try:
            self._update_cache_info()
        except Exception:
            pass
        # Sincronizar PromptSelector con el perfil activo guardado
        try:
            cfg_data = self._load_user_config() or {}
            active_profile = cfg_data.get("active_prompt_profile") or cfg_data.get("default_template")
            if active_profile and getattr(self, "prompt_selector", None):
                self.prompt_selector.select_by_path(active_profile)
            # cargar rutas previas si existen
            try:
                ep = cfg_data.get("external_prompt_file")
                if ep and getattr(self, 'external_prompt_file_input', None):
                    self.external_prompt_file_input.setText(ep)
            except Exception:
                pass
            try:
                td = cfg_data.get("prompt_templates_dir")
                if td and getattr(self, 'templates_dir_input', None):
                    self.templates_dir_input.setText(td)
            except Exception:
                pass
        except Exception:
            pass
    
    def _cache_dir(self) -> Path:
        return Path.home() / ".ocr_glm_cache"

    def _update_cache_info(self) -> None:
        try:
            d = self._cache_dir()
            if not d.exists():
                self.cache_info_lbl.setText("Vacía")
                return
            files = list(d.glob("*.json"))
            total_size = sum(f.stat().st_size for f in files if f.exists())
            kb = total_size / 1024.0
            self.cache_info_lbl.setText(f"{len(files)} archivos, {kb:.1f} KB")
        except Exception:
            self.cache_info_lbl.setText("Error al leer cache")

    def _clear_cache_clicked(self) -> None:
        try:
            d = self._cache_dir()
            if not d.exists():
                QMessageBox.information(self, "Limpiar caché", "La caché ya está vacía.")
                self._update_cache_info()
                return
            # eliminar archivos .json
            removed = 0
            for f in d.glob("*.json"):
                try:
                    f.unlink()
                    removed += 1
                except Exception:
                    pass
            QMessageBox.information(self, "Limpiar caché", f"Se eliminaron {removed} entradas de caché.")
        except Exception as exc:
            QMessageBox.warning(self, "Limpiar caché", f"Error al limpiar caché: {exc}")
        finally:
            try:
                self._update_cache_info()
            except Exception:
                pass

    # -------------------- Post-OCR settings and actions ------------------
    def _save_postocr_settings(self) -> None:
        try:
            cfg = self._load_user_config() or {}
            cfg["use_ia_postocr"] = bool(getattr(self, "use_ia_chk", False) and self.use_ia_chk.isChecked())
            cfg["postocr_model"] = getattr(self, "postocr_model_cb", None) and self.postocr_model_cb.currentText()
            self._save_user_config(cfg)
        except Exception:
            pass

    def _persist_prompt_export_settings(self) -> None:
        try:
            cfg = self._load_user_config() or {}
            # NUNCA guardar el texto del prompt ni el estado del checkbox.
            # El prompt es específico de cada proyecto/sesión y el cliente
            # debe pegarlo de nuevo cada vez. Borrarlo de la config si existía.
            cfg.pop("use_custom_prompt", None)
            cfg.pop("custom_prompt_text", None)
            cfg["output_format"] = getattr(self, "format_cb", None) and self.format_cb.currentText() or "XLSX"
            cfg["ocr_output_mode"] = getattr(self, "ocr_output_cb", None) and self.ocr_output_cb.currentText() or "JSON"
            self._save_user_config(cfg)
        except Exception:
            pass

    def _load_prompt_export_settings(self) -> None:
        try:
            cfg = self._load_user_config() or {}
            # El prompt NUNCA se restaura desde configuración.
            # El campo siempre arranca vacío: el usuario lo pega en cada sesión.
            if getattr(self, "custom_prompt_input", None) is not None:
                self.custom_prompt_input.setPlainText("")  # siempre vacío al arrancar
                self.custom_prompt_input.setVisible(True)
            out_fmt = str(cfg.get("output_format", "") or "").upper()
            if out_fmt and getattr(self, "format_cb", None) is not None:
                idx = self.format_cb.findText(out_fmt)
                if idx >= 0:
                    self.format_cb.setCurrentIndex(idx)
            ocr_mode = str(cfg.get("ocr_output_mode", "") or "")
            if ocr_mode and getattr(self, "ocr_output_cb", None) is not None:
                idx = self.ocr_output_cb.findText(ocr_mode)
                if idx >= 0:
                    self.ocr_output_cb.setCurrentIndex(idx)
        except Exception:
            pass

    def _load_custom_prompt_from_file(self) -> None:
        try:
            from PyQt6.QtWidgets import QFileDialog

            path, _ = QFileDialog.getOpenFileName(
                self,
                "Seleccionar prompt personalizado",
                "",
                "Prompt Files (*.tpl *.txt *.md);;Todos (*)",
            )
            if not path:
                return
            text = Path(path).read_text(encoding="utf-8")
            if getattr(self, "use_custom_prompt_chk", None) is not None:
                self.use_custom_prompt_chk.setChecked(True)
            if getattr(self, "custom_prompt_input", None) is not None:
                self.custom_prompt_input.setPlainText(text)
            self._persist_prompt_export_settings()
        except Exception:
            pass

    def _clear_custom_prompt(self) -> None:
        try:
            if getattr(self, "custom_prompt_input", None) is not None:
                self.custom_prompt_input.clear()
            if getattr(self, "use_custom_prompt_chk", None) is not None:
                self.use_custom_prompt_chk.setChecked(False)
            self._persist_prompt_export_settings()
        except Exception:
            pass

    def _load_postocr_settings(self) -> None:
        try:
            cfg = self._load_user_config() or {}
            if cfg.get("use_ia_postocr"):
                try:
                    self.use_ia_chk.setChecked(True)
                except Exception:
                    pass
            model = cfg.get("postocr_model")
            if model:
                idx = self.postocr_model_cb.findText(model)
                if idx >= 0:
                    self.postocr_model_cb.setCurrentIndex(idx)
        except Exception:
            pass

    def _on_toggle_use_ia(self, checked: bool) -> None:
        try:
            # persistir la opción
            self._save_postocr_settings()
        except Exception:
            pass

    def _on_model_changed(self, txt: str) -> None:
        try:
            self._save_postocr_settings()
        except Exception:
            pass

    def _on_postocr_test(self) -> None:
        """Cargar un JSON de OCR y ejecutar el mapeo determinista mostrando resultados."""
        try:
            from PyQt6.QtWidgets import QFileDialog
            p, _ = QFileDialog.getOpenFileName(self, "Seleccionar JSON OCR de prueba", "", "JSON Files (*.json);;All Files (*)")
            if not p:
                return
            import json
            data = json.loads(Path(p).read_text(encoding="utf-8"))
            # usar mapeo determinista
            try:
                from src.core.postocr import deterministic_map, ia_fallback
            except Exception:
                from core.postocr import deterministic_map, ia_fallback

            mapped = deterministic_map(data)
            # si no hay resultados y el usuario ha activado IA, intentar fallback
            if (not any(mapped.values())) and self.use_ia_chk.isChecked():
                mapped = ia_fallback(data, model=self.postocr_model_cb.currentText()) or mapped

            # mostrar resultados en una caja de texto simple
            import json as _json
            QMessageBox.information(self, "Resultado mapeo", _json.dumps(mapped, ensure_ascii=False, indent=2))
        except Exception as exc:
            QMessageBox.warning(self, "Error prueba Post‑OCR", f"Error al procesar JSON: {exc}")

        # Contadores de sesión (acumulados del lote en curso)
        self._batch_prompt: int = 0
        self._batch_completion: int = 0

        # Inicializar gráfico y total mensual al arrancar
        key = datetime.now().strftime("%Y-%m")
        monthly = self._load_monthly()
        self.monthlyTotal.setText(f"{monthly.get(key, 0):,}")
        self._refresh_chart()

    # ── Properties ──────────────────────────────────────────────────────────

    @property
    def active_schema(self) -> list[str]:
        """Claves de campos marcados; sólo relevante en perfil Facturas/Contable."""
        return self.schema_panel.get_active_schema()

    @property
    def export_profile(self) -> str:
        return self.export_profile_cb.currentText()

    @property
    def vendor_master_path(self) -> str:
        return getattr(self, 'erp_panel', None) and self.erp_panel.vendor_master_path or ""

    @property
    def profile(self) -> str:
        """Devuelve el texto del perfil de extracción seleccionado."""
        btn = self._profile_group.checkedButton()
        return btn.text() if btn else self.PROFILES[0]

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _make_kpi(self, label: str, value: str, attr: str) -> QFrame:
        kpi = QFrame()
        kpi.setObjectName("kpiCard")
        lay = QVBoxLayout()
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(2)
        lbl = QLabel(label)
        lbl.setObjectName("kpiLabel")
        val = QLabel(value)
        val.setObjectName("kpiValue")
        setattr(self, attr, val)
        lay.addWidget(lbl)
        lay.addWidget(val)
        kpi.setLayout(lay)
        return kpi

    def _load_prompt_templates(self) -> None:
        """Carga la lista de templates (raíz + subdirectorios) en el combo."""
        try:
            try:
                from src.core.prompt_manager import load_prompt_tree
            except Exception:
                from core.prompt_manager import load_prompt_tree  # type: ignore[no-redef]

            # permitir carpeta de plantillas personalizada desde la configuración
            cfg = self._load_user_config() or {}
            root_dir = cfg.get("prompt_templates_dir")
            tree_data = load_prompt_tree(root_dir) if root_dir else load_prompt_tree()
            items: list[str] = []
            for entries in tree_data.values():
                for entry in entries:
                    items.append(entry["rel_path"])

            self.prompt_template_cb.clear()
            if items:
                self.prompt_template_cb.addItems(sorted(set(items)))
            else:
                self.prompt_template_cb.addItem("default.tpl")

            # Restaurar selección: active_prompt_profile > default_template
            try:
                cfg = self._load_user_config() or {}
                active = cfg.get("active_prompt_profile") or cfg.get("default_template")
                if active:
                    idx = self.prompt_template_cb.findText(active)
                    if idx >= 0:
                        self.prompt_template_cb.setCurrentIndex(idx)
                # Cargar ruta de credenciales Google si existe
                if cfg.get("google_creds_path"):
                    try:
                        self.google_creds_input.setText(cfg.get("google_creds_path"))
                    except Exception:
                        pass
            except Exception:
                pass
        except Exception:
            try:
                self.prompt_template_cb.clear()
                self.prompt_template_cb.addItem("default.tpl")
            except Exception:
                pass

    def _load_user_config(self) -> dict | None:
        try:
            if self._CONFIG_FILE.exists():
                return json.loads(self._CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
        return None

    def _save_user_config(self, data: dict) -> None:
        try:
            self._CONFIG_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _set_selected_as_default(self) -> None:
        tpl = self.selected_prompt_template
        if not tpl:
            QMessageBox.warning(self, "No seleccionado", "No hay ninguna plantilla seleccionada.")
            return
        cfg = self._load_user_config() or {}
        cfg["default_template"] = tpl
        cfg["active_prompt_profile"] = tpl
        self._save_user_config(cfg)
        # Sincronizar árbol si está disponible
        try:
            if getattr(self, "prompt_selector", None):
                self.prompt_selector.select_by_path(tpl)
        except Exception:
            pass
        QMessageBox.information(self, "Guardado", f"{tpl} establecida como plantilla por defecto.")

    @property
    def selected_prompt_template(self) -> str | None:
        try:
            txt = self.prompt_template_cb.currentText()
            return txt if txt else None
        except Exception:
            return None

    def _open_template_editor(self) -> None:
        try:
            from .template_editor import TemplateEditor
        except Exception:
            try:
                from src.ui.template_editor import TemplateEditor
            except Exception:
                QMessageBox.warning(self, "Editor no disponible", "No se pudo cargar el editor de plantillas.")
                return

        tpl = self.selected_prompt_template or "default.tpl"
        dlg = TemplateEditor(initial_template=tpl, parent=self)
        dlg.exec()
        # after editing, refresh list
        self._load_prompt_templates()

    def get_selected_prompt_name(self) -> str | None:
        try:
            txt = self.prompt_template_cb.currentText()
            return txt if txt else None
        except Exception:
            return None

    def set_active_prompt(self, prompt_name: str) -> None:
        try:
            idx = self.prompt_template_cb.findText(prompt_name)
            if idx >= 0:
                self.prompt_template_cb.setCurrentIndex(idx)
            else:
                # add to combo for convenience
                self.prompt_template_cb.addItem(prompt_name)
                self.prompt_template_cb.setCurrentText(prompt_name)
        except Exception:
            try:
                setattr(self, 'selected_prompt_template', prompt_name)
            except Exception:
                pass

    def update_expected_keys(self, keys: list[str]) -> None:
        """Marca en el `SchemaPanel` las claves indicadas en `keys`.

        Silencioso si no existe `schema_panel`.
        """
        try:
            if getattr(self, 'schema_panel', None) and isinstance(keys, (list, tuple)):
                # limpiar primero
                self.schema_panel.clear_selection()
                for k in keys:
                    try:
                        # marcar checkboxes que coincidan
                        for cb_key, cb in self.schema_panel._checkboxes.items():
                            if cb_key == k:
                                cb.setChecked(True)
                    except Exception:
                        pass
        except Exception:
            pass

    def _browse_google_creds(self) -> None:
        p, _ = QFileDialog.getOpenFileName(self, "Seleccionar JSON de credenciales", "", "JSON Files (*.json);;All Files (*)")
        if p:
            self.google_creds_input.setText(p)

    def _save_google_creds(self) -> None:
        path = self.google_creds_input.text().strip()
        if not path:
            QMessageBox.warning(self, "No seleccionado", "Selecciona primero un archivo JSON válido.")
            return
        cfg = self._load_user_config() or {}
        cfg["google_creds_path"] = path
        self._save_user_config(cfg)
        QMessageBox.information(self, "Guardado", "Ruta de credenciales Google guardada.")

    # -------------------- Saved named configurations ---------------------
    def _configs_dir(self) -> Path:
        d = Path.home() / ".ocr_glm_configs"
        try:
            d.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        return d

    def _refresh_saved_configs(self) -> None:
        try:
            d = self._configs_dir()
            items = [p.stem for p in sorted(d.glob("*.json"))]
            # create combo lazily if not present
            try:
                self.saved_cfg_cb.blockSignals(True)
                self.saved_cfg_cb.clear()
                if items:
                    self.saved_cfg_cb.addItems(items)
                self.saved_cfg_cb.blockSignals(False)
            except Exception:
                pass
        except Exception:
            pass

    def _on_save_named_config_btn(self) -> None:
        try:
            name, ok = QInputDialog.getText(self, "Guardar configuración", "Nombre de la configuración:")
            if not ok or not name.strip():
                return
            name = name.strip()
            cfg = {
                "backend": self.backend_cb.currentText() if getattr(self, 'backend_cb', None) else None,
                "prompt_template": self.prompt_template_cb.currentText() if getattr(self, 'prompt_template_cb', None) else None,
                "active_prompt_profile": getattr(self, 'prompt_selector', None) and self.prompt_selector.current_rel_path() or None,
                "format": self.format_cb.currentText() if getattr(self, 'format_cb', None) else None,
                "ocr_output": self.ocr_output_cb.currentText() if getattr(self, 'ocr_output_cb', None) else None,
                "export_profile": self.export_profile_cb.currentText() if getattr(self, 'export_profile_cb', None) else None,
                "merge": bool(self.merge_chk.isChecked()) if getattr(self, 'merge_chk', None) else False,
                "include_images": bool(self.include_images_chk.isChecked()) if getattr(self, 'include_images_chk', None) else False,
                # image processing flags
                "preprocess": bool(self.preprocess_chk.isChecked()) if getattr(self, 'preprocess_chk', None) else False,
                "use_cache": bool(self.use_cache_chk.isChecked()) if getattr(self, 'use_cache_chk', None) else False,
                "prefer_local": bool(self.prefer_local_chk.isChecked()) if getattr(self, 'prefer_local_chk', None) else False,
                "ocr_local_only": bool(self.ocr_local_only_chk.isChecked()) if getattr(self, 'ocr_local_only_chk', None) else False,
                "light_mode": bool(self.light_mode_chk.isChecked()) if getattr(self, 'light_mode_chk', None) else False,
                "accounting_validation": bool(self.accounting_validation_chk.isChecked()) if getattr(self, 'accounting_validation_chk', None) else False,
                "smart_routing": bool(self.smart_routing_chk.isChecked()) if getattr(self, 'smart_routing_chk', None) else False,
                "upscale": self.upscale_cb.currentText() if getattr(self, 'upscale_cb', None) else None,
                "local_conf": float(self.local_conf_spin.value()) if getattr(self, 'local_conf_spin', None) else None,
                # postocr options
                "use_ia_postocr": bool(getattr(self, "use_ia_chk", None) and self.use_ia_chk.isChecked()),
                "postocr_model": getattr(self, 'postocr_model_cb', None) and self.postocr_model_cb.currentText(),
            }
            import json
            p = self._configs_dir() / f"{name}.json"
            p.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
            QMessageBox.information(self, "Guardado", f"Configuración '{name}' guardada en {p}")
            self._refresh_saved_configs()
        except Exception as exc:
            QMessageBox.warning(self, "Guardar configuración", f"Error guardando configuración: {exc}")

    def _on_load_named_config_btn(self) -> None:
        try:
            name = self.saved_cfg_cb.currentText() if getattr(self, 'saved_cfg_cb', None) else None
            if not name:
                QMessageBox.information(self, "Cargar", "Selecciona primero una configuración guardada.")
                return
            p = self._configs_dir() / f"{name}.json"
            if not p.exists():
                QMessageBox.warning(self, "Cargar", "Archivo de configuración no encontrado.")
                return
            import json
            data = json.loads(p.read_text(encoding="utf-8"))
            # aplicar valores si existen
            try:
                if data.get("backend") and self.backend_cb.findText(data.get("backend")) >= 0:
                    self.backend_cb.setCurrentText(data.get("backend"))
            except Exception:
                pass
            try:
                if data.get("prompt_template") and self.prompt_template_cb.findText(data.get("prompt_template")) >= 0:
                    self.prompt_template_cb.setCurrentText(data.get("prompt_template"))
                # Restaurar en el árbol si hay active_prompt_profile
                active = data.get("active_prompt_profile") or data.get("prompt_template")
                if active and getattr(self, "prompt_selector", None):
                    self.prompt_selector.select_by_path(active)
            except Exception:
                pass
            try:
                if data.get("format") and self.format_cb.findText(data.get("format")) >= 0:
                    self.format_cb.setCurrentText(data.get("format"))
            except Exception:
                pass
            try:
                if data.get("ocr_output") and getattr(self, 'ocr_output_cb', None) and self.ocr_output_cb.findText(data.get("ocr_output")) >= 0:
                    self.ocr_output_cb.setCurrentText(data.get("ocr_output"))
            except Exception:
                pass
            try:
                if data.get("export_profile") and self.export_profile_cb.findText(data.get("export_profile")) >= 0:
                    self.export_profile_cb.setCurrentText(data.get("export_profile"))
            except Exception:
                pass
            # checkboxes & values
            try:
                if "merge" in data and hasattr(self, 'merge_chk'):
                    self.merge_chk.setChecked(bool(data.get("merge")))
                if "include_images" in data and hasattr(self, 'include_images_chk'):
                    self.include_images_chk.setChecked(bool(data.get("include_images")))
                if "preprocess" in data and hasattr(self, 'preprocess_chk'):
                    self.preprocess_chk.setChecked(bool(data.get("preprocess")))
                if "use_cache" in data and hasattr(self, 'use_cache_chk'):
                    self.use_cache_chk.setChecked(bool(data.get("use_cache")))
                if "prefer_local" in data and hasattr(self, 'prefer_local_chk'):
                    self.prefer_local_chk.setChecked(bool(data.get("prefer_local")))
                if "ocr_local_only" in data and hasattr(self, 'ocr_local_only_chk'):
                    self.ocr_local_only_chk.setChecked(bool(data.get("ocr_local_only")))
                if "light_mode" in data and hasattr(self, 'light_mode_chk'):
                    self.light_mode_chk.setChecked(bool(data.get("light_mode")))
                if "accounting_validation" in data and hasattr(self, 'accounting_validation_chk'):
                    self.accounting_validation_chk.setChecked(bool(data.get("accounting_validation")))
                if "smart_routing" in data and hasattr(self, 'smart_routing_chk'):
                    self.smart_routing_chk.setChecked(bool(data.get("smart_routing")))
                if "upscale" in data and hasattr(self, 'upscale_cb') and data.get("upscale"):
                    self.upscale_cb.setCurrentText(data.get("upscale"))
                if "local_conf" in data and hasattr(self, 'local_conf_spin') and data.get("local_conf") is not None:
                    try:
                        self.local_conf_spin.setValue(float(data.get("local_conf")))
                    except Exception:
                        pass
            except Exception:
                pass
            # postocr
            try:
                if data.get("use_ia_postocr"):
                    self.use_ia_chk.setChecked(True)
                else:
                    self.use_ia_chk.setChecked(False)
                if data.get("postocr_model") and self.postocr_model_cb.findText(data.get("postocr_model")) >= 0:
                    self.postocr_model_cb.setCurrentText(data.get("postocr_model"))
            except Exception:
                pass
            QMessageBox.information(self, "Cargar", f"Configuración '{name}' aplicada.")
        except Exception as exc:
            QMessageBox.warning(self, "Cargar configuración", f"Error cargando configuración: {exc}")

    def _init_backend_kpis(self) -> None:
        """Crea widgets QLabel para cada backend conocido y los añade al panel."""
        # Determinar backends desde el combo (o desde la configuración de pricing)
        backends = []
        try:
            backends = [self.backend_cb.itemText(i) for i in range(self.backend_cb.count())]
        except Exception:
            backends = list(self._BACKEND_PRICING.keys())

        # Añadir una línea por backend
        parent_box = None
        for w in self.findChildren(QGroupBox):
            if w.objectName() == "backendGroup":
                parent_box = w
                break
        if parent_box is None:
            return
        layout = parent_box.layout()
        # Limpiar entradas previas
        for i in reversed(range(layout.count())):
            item = layout.itemAt(i)
            if item:
                widget = item.widget()
                if widget:
                    widget.setParent(None)

        for bk in backends:
            row = QWidget()
            rlay = QHBoxLayout()
            rlay.setContentsMargins(0, 0, 0, 0)
            rlay.setSpacing(6)
            lbl = QLabel(bk)
            lbl.setObjectName("backendLabel")
            val = QLabel("0 / 0 (0)")
            val.setObjectName("backendValue")
            rlay.addWidget(lbl)
            rlay.addStretch()
            rlay.addWidget(val)
            row.setLayout(rlay)
            layout.addWidget(row)
            self._backend_kpis[bk] = val
        # Asegurar que el tele_backend_cb contiene las mismas opciones
        try:
            if getattr(self, "tele_backend_cb", None):
                self.tele_backend_cb.clear()
                for b in backends:
                    self.tele_backend_cb.addItem(b)
        except Exception:
            pass

    def _compute_backend_monthly_details(self, raw: dict, month_key: str) -> dict:
        """Devuelve un dict con detalle por backend: prompt, completion, total, cost, free_remaining."""
        # Inicializar conteos
        per = {}
        for day_key, entry in raw.items():
            if not day_key.startswith(month_key):
                continue
            if isinstance(entry, dict):
                for bk, vals in entry.items():
                    if bk not in per:
                        per[bk] = {"prompt": 0, "completion": 0, "calls": 0}
                    if isinstance(vals, dict):
                        per[bk]["prompt"] += vals.get("prompt", 0)
                        per[bk]["completion"] += vals.get("completion", 0)
                        per[bk]["calls"] += vals.get("calls", 0)
                    else:
                        try:
                            v = int(vals)
                            per[bk]["prompt"] += v // 2
                            per[bk]["completion"] += v // 2
                            if v > 0:
                                per[bk]["calls"] += 1
                        except Exception:
                            pass
            else:
                # Unknown shape, attribute to default glm
                bk = "glm"
                if bk not in per:
                    per[bk] = {"prompt": 0, "completion": 0, "calls": 0}
                try:
                    v = int(entry)
                    per[bk]["prompt"] += v // 2
                    per[bk]["completion"] += v // 2
                    if v > 0:
                        per[bk]["calls"] += 1
                except Exception:
                    pass

        # Calcular costes y free_remaining
        result = {}
        for bk, counts in per.items():
            pricing = self._BACKEND_PRICING.get(bk, {"billing": "tokens", "price_per_1k": self._PRICE_PER_1K_USD, "free_per_month": 0})
            billing = pricing.get("billing", "tokens")
            pt = counts.get("prompt", 0)
            ct = counts.get("completion", 0)
            calls = counts.get("calls", 0)
            total = pt + ct
            free = pricing.get("free_per_month", 0) or 0
            if billing == "pages":
                # For pages we treat 'total' as pages (client must record pages into tokens fields)
                pages = total
                chargeable = max(0, pages - free)
                # price_per_1k interpreted as USD per 1000 pages
                price_per_1k = pricing.get("price_per_1k", 0.0)
                cost_usd = (chargeable / 1000.0) * price_per_1k
                free_remaining = max(0, free - pages)
            else:
                chargeable = max(0, total - free)
                price_per_1k = pricing.get("price_per_1k", self._PRICE_PER_1K_USD)
                cost_usd = (chargeable / 1000.0) * price_per_1k
                free_remaining = max(0, free - total)

            result[bk] = {
                "prompt": pt,
                "completion": ct,
                "calls": calls,
                "total": total,
                "cost_usd": cost_usd,
                "free_remaining": free_remaining,
                "billing": billing,
            }
        return result

    def _refresh_backend_kpis(self) -> None:
        """Actualiza los labels KPIs por backend usando los datos del mes actual."""
        month_key = datetime.now().strftime("%Y-%m")
        raw = self._load_raw()
        details = self._compute_backend_monthly_details(raw, month_key)
        # Actualizar widgets
        for bk, widget in getattr(self, "_backend_kpis", {}).items():
            info = details.get(bk, {"prompt": 0, "completion": 0, "calls": 0, "total": 0, "cost_usd": 0.0, "free_remaining": 0})
            widget.setText(f"{info['prompt']:,} / {info['completion']:,} ({info['total']:,})  calls:{info['calls']:,}  ${info['cost_usd']:.4f}")
        # Comprobar alerta de free-tier para backend seleccionado en telemetría
        try:
            sel = self.tele_backend_cb.currentText() if getattr(self, 'tele_backend_cb', None) else None
            if sel and sel in details:
                fr = details[sel].get('free_remaining', 0)
                thresh = getattr(self, 'free_alert_spin', None) and self.free_alert_spin.value() or 0
                if fr <= thresh:
                    # Mostrar mensaje de alerta no modal
                    self.free_alert_lbl.setText(f"ALERTA: Quedan {fr:,} unidades gratuitas en {sel}")
                    self.free_alert_lbl.setVisible(True)
                else:
                    self.free_alert_lbl.setVisible(False)
        except Exception:
            try:
                self.free_alert_lbl.setVisible(False)
            except Exception:
                pass

    # ── Slots ─────────────────────────────────────────────────────────────────

    def browse_src(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Carpeta de origen")
        if path:
            self.src_input.setText(path)

    def browse_dst(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Carpeta de destino")
        if path:
            self.dst_input.setText(path)

    def _on_select_output_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Seleccionar carpeta de salida")
        if path:
            try:
                self.dst_input.setText(path)
            except Exception:
                pass

    # ── Telemetría mensual ──────────────────────────────────────────────────
    #
    # Esquema de almacenamiento (por día):
    #   {
    #     "YYYY-MM-DD": {"prompt": int, "completion": int},
    #     ...
    #   }
    # Formato legacy (un entero por mes "YYYY-MM") se migra automáticamente.

    _TELE_FILE = Path.home() / ".ocr_glm_telemetry.json"
    # Precio GLM-4V-Flash: ~0.007 USD / 1K tokens
    _PRICE_PER_1K_USD = 0.007
    # Precios y reglas por backend
    # billing: 'tokens' or 'pages'
    # price_per_1k: USD per 1000 tokens (if billing=='tokens')
    # free_per_month: free allowance units (tokens or pages) per month
    _BACKEND_PRICING = {
        "glm": {"billing": "tokens", "price_per_1k": 0.007, "free_per_month": 0},
        # Mistral OCR se factura por páginas; referencia estándar: $0.02/página = $20/1K.
        "mistral-ocr-latest": {"billing": "pages", "price_per_1k": 20.0, "free_per_month": 0},
        "google-vision": {"billing": "pages", "price_per_1k": 0.0, "free_per_month": 1000},
    }

    # ── IO bajo nivel ──────────────────────────────────────────────────────

    def _load_raw(self) -> dict:
        """Carga el JSON raw desde disco y migra formato legacy si fuera necesario."""
        raw: dict = {}
        try:
            if self._TELE_FILE.exists():
                raw = json.loads(self._TELE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}

        # Migrar legacy: claves "YYYY-MM" (longitud 7) con valor int → día 01
        # Nuevo formato por día: {"YYYY-MM-DD": {"backend_name": {"prompt":int, "completion":int}}}
        migrated = {}
        needs_migration = False
        for k, v in raw.items():
            if len(k) == 7 and isinstance(v, int):
                migrated[f"{k}-01"] = {"glm": {"prompt": v // 2, "completion": v // 2}}
                needs_migration = True
            else:
                # Si el valor ya es dict con prompt/completion, wrap en 'glm' key
                if isinstance(v, dict) and ("prompt" in v or "completion" in v):
                    migrated[k] = {"glm": {"prompt": v.get("prompt", 0), "completion": v.get("completion", 0)}}
                    needs_migration = True
                else:
                    migrated[k] = v
        if needs_migration:
            self._save_raw(migrated)
        return migrated

    def _save_raw(self, data: dict) -> None:
        try:
            self._TELE_FILE.write_text(
                json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

    # ── Agregaciones ──────────────────────────────────────────────────────

    def _aggregate_monthly(self, raw: dict) -> dict[str, int]:
        """Devuelve {"YYYY-MM": total_tokens} para el gráfico."""
        result: dict[str, int] = {}
        for day_key, entry in raw.items():
            month_key = day_key[:7]  # "YYYY-MM"
            total = 0
            if isinstance(entry, dict):
                # entry expected: {backend: {prompt, completion}, ...}
                for bk, vals in entry.items():
                    if isinstance(vals, dict):
                        total += vals.get("prompt", 0) + vals.get("completion", 0)
                    else:
                        try:
                            total += int(vals)
                        except Exception:
                            pass
            else:
                try:
                    total = int(entry)
                except Exception:
                    total = 0
            result[month_key] = result.get(month_key, 0) + total
        return result

    def _aggregate_month_detail(self, raw: dict, month_key: str) -> dict:
        """Devuelve {"prompt": int, "completion": int, "total": int, "cost_usd": float}
        para el mes indicado (formato "YYYY-MM").
        """
        pt = ct = 0
        for day_key, entry in raw.items():
            if not day_key.startswith(month_key):
                continue
            if isinstance(entry, dict):
                # Sum across backends
                for bk, vals in entry.items():
                    if isinstance(vals, dict):
                        pt += vals.get("prompt", 0)
                        ct += vals.get("completion", 0)
                    else:
                        try:
                            v = int(vals)
                            pt += v // 2
                            ct += v // 2
                        except Exception:
                            pass
            else:
                try:
                    v = int(entry)
                    pt += v // 2
                    ct += v // 2
                except Exception:
                    pass
        total = pt + ct
        return {
            "prompt": pt,
            "completion": ct,
            "total": total,
            "cost_usd": (total / 1000.0) * self._PRICE_PER_1K_USD,
        }

    # ── Compat: devuelve {"YYYY-MM": total} (usado por _refresh_chart) ────

    def _load_monthly(self) -> dict[str, int]:
        return self._aggregate_monthly(self._load_raw())

    # ── Gráfico ───────────────────────────────────────────────────────────

    def _refresh_chart(self) -> None:
        """Redibuja el gráfico de barras con los datos mensuales."""
        monthly = self._load_monthly()
        self._figure.clear()
        ax = self._figure.add_subplot(111)
        ax.set_facecolor("#12121C")
        for spine in ax.spines.values():
            spine.set_edgecolor("#2D2D3D")
        ax.tick_params(colors="#6B7280", labelsize=8)

        if monthly:
            months = sorted(monthly.keys())[-12:]  # últimos 12 meses
            values = [monthly[m] for m in months]
            labels = [m[5:] for m in months]  # mostrar solo MM
            colors = ["#3B82F6"] * len(months)
            if colors:
                colors[-1] = "#10B981"  # mes actual en verde
            bars = ax.bar(labels, values, color=colors, width=0.6)
            ax.yaxis.set_visible(False)
            for bar, val in zip(bars, values):
                label = f"{val//1000}K" if val >= 1000 else str(val)
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + max(values) * 0.02,
                    label,
                    ha="center", va="bottom",
                    color="#C8D0E0", fontsize=7,
                )
        else:
            ax.text(
                0.5, 0.5, "Sin datos aún",
                ha="center", va="center", transform=ax.transAxes,
                color="#6B7280", fontsize=9,
            )
            ax.set_axis_off()

        self._canvas.draw()

    # ── Acciones públicas ────────────────────────────────────────────────

    def _clear_monthly_history(self) -> None:
        res = QMessageBox.question(
            self, "Limpiar historial",
            "¿Borrar todo el historial mensual de tokens?",
        )
        if res == QMessageBox.StandardButton.Yes:
            self._save_raw({})
            self.monthlyTotal.setText("0")
            self._refresh_chart()

    def save_batch_to_monthly(self) -> None:
        """Persiste los tokens del lote actual en el historial diario."""
        pt = getattr(self, "_batch_prompt", 0)
        ct = getattr(self, "_batch_completion", 0)
        calls = getattr(self, "_batch_calls", 0)
        backend = getattr(self, "_batch_backend", "glm")
        if pt + ct == 0 and calls == 0:
            return
        day_key = datetime.now().strftime("%Y-%m-%d")
        month_key = day_key[:7]
        raw = self._load_raw()
        existing = raw.get(day_key, {}) or {}
        if not isinstance(existing, dict):
            existing = {}
        # existing is dict mapping backend -> {prompt, completion}
        bk_vals = existing.get(backend, {"prompt": 0, "completion": 0, "calls": 0})
        if not isinstance(bk_vals, dict):
            bk_vals = {"prompt": 0, "completion": 0, "calls": 0}
        # Compatibilidad con telemetría legacy: puede faltar la clave 'calls'.
        bk_vals["prompt"] = int(bk_vals.get("prompt", 0) or 0) + int(pt or 0)
        bk_vals["completion"] = int(bk_vals.get("completion", 0) or 0) + int(ct or 0)
        bk_vals["calls"] = int(bk_vals.get("calls", 0) or 0) + int(calls or 0)
        existing[backend] = bk_vals
        raw[day_key] = existing
        self._save_raw(raw)

        detail = self._aggregate_month_detail(raw, month_key)
        self.monthlyTotal.setText(f"{detail['total']:,}")
        self.monthCost.setText(f"${detail['cost_usd']:.4f}")
        self._refresh_chart()
        try:
            self._refresh_backend_kpis()
        except Exception:
            pass
        # Resetear contadores para el próximo lote
        self._batch_prompt = 0
        self._batch_completion = 0
        self._batch_calls = 0
        self._last_batch_total = 0
        self._batch_backend = "glm"

    def reset_session_telemetry(self) -> None:
        """Reinicia contadores de sesión al iniciar un nuevo lote."""
        self._batch_prompt = 0
        self._batch_completion = 0
        self._batch_calls = 0
        self._last_batch_total = 0
        self._batch_backend = "glm"
        self.tokensToday.setText("0")
        self.tokenBreakdown.setText("0 / 0")
        # Mostrar coste y total del mes actual (datos ya guardados)
        month_key = datetime.now().strftime("%Y-%m")
        detail = self._aggregate_month_detail(self._load_raw(), month_key)
        self.monthlyTotal.setText(f"{detail['total']:,}")
        self.monthCost.setText(f"${detail['cost_usd']:.4f}")
        self._refresh_chart()
        try:
            self._refresh_backend_kpis()
        except Exception:
            pass

    def update_telemetry(self, prompt_tokens: int, completion_tokens: int, backend: str = "glm") -> None:
        """Actualiza los KPIs en tiempo real con el consumo del lote en curso.

        `backend` indica el motor usado (ej. 'glm', 'mistral-ocr-latest', 'google-vision').
        """
        self._batch_prompt = prompt_tokens
        self._batch_completion = completion_tokens
        self._batch_backend = backend or "glm"
        batch_total = prompt_tokens + completion_tokens
        prev_total = int(getattr(self, "_last_batch_total", 0) or 0)
        if batch_total > prev_total:
            self._batch_calls = int(getattr(self, "_batch_calls", 0) or 0) + 1
        self._last_batch_total = batch_total
        # Mostrar tokens del lote actual
        self.tokensToday.setText(f"{batch_total:,}")
        self.tokenBreakdown.setText(f"{prompt_tokens:,} / {completion_tokens:,}")
        # Coste del mes = acumulado ya guardado + lote en curso
        month_key = datetime.now().strftime("%Y-%m")
        saved_detail = self._aggregate_month_detail(self._load_raw(), month_key)
        month_total_cost = saved_detail["cost_usd"] + (batch_total / 1000.0) * self._PRICE_PER_1K_USD
        self.monthCost.setText(f"${month_total_cost:.4f}")
        try:
            self._refresh_backend_kpis()
        except Exception:
            pass

    def record_mistral_usage(self, mode: str, cost_usd: float) -> None:
        """Registra un documento procesado por Mistral en el histórico mensual.

        Actualiza `~/.ocr_glm_config.json` en la clave `mistral_stats` y
        refresca la tarjeta de Telemetría si existe.
        """
        try:
            cfg = self._load_user_config() or {}
            ms = cfg.get("mistral_stats", {})
            month_key = datetime.now().strftime("%Y-%m")
            cur = ms.get(month_key, {"docs_processed": 0, "total_cost": 0.0, "mode_breakdown": {"standard": {"count": 0, "cost": 0.0}, "with_annotations": {"count": 0, "cost": 0.0}}})
            # increment
            cur["docs_processed"] = int(cur.get("docs_processed", 0)) + 1
            cur["total_cost"] = float(cur.get("total_cost", 0.0)) + float(cost_usd or 0.0)
            mb = cur.get("mode_breakdown") or {}
            if mode not in mb:
                mb[mode] = {"count": 0, "cost": 0.0}
            mb[mode]["count"] = int(mb[mode].get("count", 0)) + 1
            mb[mode]["cost"] = float(mb[mode].get("cost", 0.0)) + float(cost_usd or 0.0)
            cur["mode_breakdown"] = mb
            ms[month_key] = cur
            cfg["mistral_stats"] = ms
            # persist
            self._save_user_config(cfg)

            # Optional: encrypted backup if cryptography available
            try:
                from cryptography.fernet import Fernet
                key = Fernet.generate_key()
                f = Fernet(key)
                secret_path = Path.home() / ".ocr_glm_secrets.enc"
                payload = json.dumps({"mistral_stats": ms}, ensure_ascii=False).encode("utf-8")
                enc = f.encrypt(payload)
                with open(secret_path, "wb") as sf:
                    sf.write(key + b"\n" + enc)
            except Exception:
                # ignore encryption failures
                pass

            # update UI card if available
            try:
                tele = getattr(self, 'telemetry_panel', None)
                if tele is not None:
                    mdata = ms.get(month_key, {})
                    docs = int(mdata.get("docs_processed", 0))
                    total_cost = float(mdata.get("total_cost", 0.0))
                    avg = (total_cost / docs) if docs else 0.0
                    try:
                        tele.update_mistral_stats(docs, total_cost, avg)
                    except Exception:
                        pass
            except Exception:
                pass
        except Exception:
            pass

    def _toggle_show(self, checked: bool) -> None:
        mode = QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
        self.token_input.setEchoMode(mode)
        self.show_btn.setText("Ocultar" if checked else "Mostrar")

    def validate_api_key(self) -> bool:
        token = self.token_input.text().strip()
        if not token:
            self.status_lbl.setText("● Estado: Desconectado")
            self.status_lbl.setStyleSheet("color: #EF4444")
            self.api_validated.emit(False)
            return False
        try:
            backend = self.backend_cb.currentText() if getattr(self, 'backend_cb', None) else ''
            cfg = self._load_user_config() or {}
            import os as _os
            if backend == 'mistral-ocr-latest':
                _os.environ['MISTRAL_API_KEY'] = token
                cfg['mistral_api_key'] = token
            elif backend in ('openrouter', 'openrouter-ocr'):
                _os.environ['OPENROUTER_API_KEY'] = token
                cfg['openrouter_api_key'] = token
            elif backend in ('openai', 'openai-vision'):
                _os.environ['OPENAI_API_KEY'] = token
                cfg['openai_api_key'] = token
            elif backend == 'google-vision':
                cfg['google_vision_api_key'] = token
            elif backend == 'google-docs':
                cfg['google_docs_api_key'] = token
            else:
                import keyring
                keyring.set_password("ocr_glm", "api_key", token)
            self._save_user_config(cfg)
            self.status_lbl.setText("● Estado: Conectado")
            self.status_lbl.setStyleSheet("color: #10B981")
            self.api_validated.emit(True)
            return True
        except Exception:
            self.status_lbl.setText("● Estado: Error al guardar token")
            self.status_lbl.setStyleSheet("color: #EF4444")
            self.api_validated.emit(False)
            return False

    def _delete_api_key(self) -> None:
        """Borra la credencial guardada del backend actualmente seleccionado."""
        from PyQt6.QtWidgets import QMessageBox
        backend = self.backend_cb.currentText() if getattr(self, 'backend_cb', None) else ''
        reply = QMessageBox.question(
            self,
            "Borrar credencial",
            f"¿Seguro que quieres borrar la API Key guardada para «{backend or 'GLM'}»?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            cfg = self._load_user_config() or {}
            if backend == 'mistral-ocr-latest':
                cfg.pop('mistral_api_key', None)
                import os as _os
                _os.environ.pop('MISTRAL_API_KEY', None)
            elif backend == 'google-vision':
                cfg.pop('google_vision_api_key', None)
                cfg.pop('google_creds_path', None)
            elif backend == 'google-docs':
                cfg.pop('google_docs_api_key', None)
                cfg.pop('google_creds_path', None)
            elif backend in ('openrouter', 'openrouter-ocr'):
                cfg.pop('openrouter_api_key', None)
                import os as _os
                _os.environ.pop('OPENROUTER_API_KEY', None)
            elif backend in ('openai', 'openai-vision'):
                cfg.pop('openai_api_key', None)
                import os as _os
                _os.environ.pop('OPENAI_API_KEY', None)
            else:
                # GLM y otros: limpiar de keyring
                try:
                    import keyring
                    keyring.delete_password("ocr_glm", "api_key")
                except Exception:
                    pass
                cfg.pop('api_key', None)
            self._save_user_config(cfg)
            self.token_input.clear()
            self.status_lbl.setText("● Estado: Credencial eliminada")
            self.status_lbl.setStyleSheet("color: #F59E0B")
            self.api_validated.emit(False)
        except Exception as exc:
            QMessageBox.warning(self, "Error al borrar", str(exc))

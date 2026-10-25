"""Ventana principal – Enterprise Dark Mode.

Ensambla ConfigPanel, StagePanel y LogPanel en tres columnas,
aplica el QSS global "Enterprise Dark" y conecta el OcrWorker (QThread).
"""
from __future__ import annotations

from typing import Optional
import sys
import traceback

from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QLabel, QFrame, QPushButton, QTabWidget
from PyQt6.QtCore import QPropertyAnimation, QEasingCurve, Qt, QTimer

from .styles import APP_QSS, APP_QSS_LIGHT

from .config_panel import ConfigPanel
from .stage_panel import StagePanel
from .log_panel import LogPanel
from .worker import OcrWorker
from .toast_notification import show_toast


    # styles moved to src/ui/styles.py


def _start_qt_app() -> int:
    from PyQt6.QtWidgets import QMessageBox
    import os

    app = QApplication.instance() or QApplication([])

    def _ui_excepthook(exc_type, exc_value, exc_tb) -> None:  # type: ignore[no-untyped-def]
        try:
            traceback.print_exception(exc_type, exc_value, exc_tb)
            QMessageBox.critical(
                None,
                "Error inesperado de interfaz",
                f"Se produjo un error no controlado:\n{exc_value}",
            )
        except Exception:
            pass

    sys.excepthook = _ui_excepthook
    # Ensure QApplication font has a valid positive point size to avoid Qt warnings
    try:
        f = app.font()
        if f.pointSize() <= 0:
            try:
                f.setPointSize(11)
                app.setFont(f)
            except Exception:
                pass
    except Exception:
        pass
    app.setStyleSheet(APP_QSS_LIGHT)

    # ── FASE 6: Login de usuario ───────────────────────────────────────────────
    _session = [None]   # [UserSession | None] — referencia compartida en closures
    skip_login = os.environ.get("OCR_SKIP_LOGIN", "").lower() in ("1", "true", "yes")
    if not skip_login:
        try:
            from src.core.user_manager import UserManager, AuthError
            from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QLineEdit
            _user_mgr = UserManager()

            login_dlg = QDialog()
            login_dlg.setWindowTitle("Iniciar sesión — OCR Enterprise")
            login_dlg.setFixedSize(340, 200)
            login_dlg.setStyleSheet(
                "QDialog{background:#1E293B;color:#F8FAFC;}"
                "QLabel{color:#9CA3AF;font-size:11px;}"
                "QLineEdit{background:#334155;border:1px solid #1E3A8A;border-radius:4px;"
                "color:#E2E8F0;padding:4px 8px;}"
                "QPushButton{background:#1E3A8A;color:#93C5FD;border-radius:4px;padding:6px 14px;}"
                "QPushButton:hover{background:#2563EB;}"
            )
            dlg_lay = QVBoxLayout(login_dlg)
            dlg_lay.setSpacing(10)
            dlg_lay.setContentsMargins(24, 20, 24, 16)
            # Title: use clear text (avoid mojibake) and standard lock emoji
            _title = QLabel("🔒  Iniciar Sesión — OCR Enterprise")
            _title.setStyleSheet("color:#93C5FD; font-size:14px; font-weight:700;")
            dlg_lay.addWidget(_title)
            _user_edit = QLineEdit()
            _user_edit.setPlaceholderText("Usuario")
            dlg_lay.addWidget(_user_edit)
            _pass_edit = QLineEdit()
            _pass_edit.setPlaceholderText("Contraseña")
            _pass_edit.setEchoMode(QLineEdit.EchoMode.Password)
            dlg_lay.addWidget(_pass_edit)
            _err_lbl = QLabel("")
            _err_lbl.setStyleSheet("color:#FCA5A5; font-size:10px;")
            dlg_lay.addWidget(_err_lbl)
            _btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
            _btn_box.accepted.connect(login_dlg.accept)
            dlg_lay.addWidget(_btn_box)

            while True:
                if login_dlg.exec() != QDialog.DialogCode.Accepted:
                    return 0   # usuario canceló — salir
                try:
                    sess = _user_mgr.login(
                        _user_edit.text().strip(),
                        _pass_edit.text(),
                    )
                    _session[0] = sess
                    break
                except Exception as _auth_e:
                    _err_lbl.setText(str(_auth_e))
                    _pass_edit.clear()
        except Exception:
            pass   # Si user_manager no está disponible, continuar sin login

    win = QMainWindow()
    win.setWindowTitle("OCR Enterprise  \u2014  Powered by GLM-4V")
    win.resize(1560, 940)
    # Evita layouts rotos al redimensionar demasiado pequeño.
    win.setMinimumSize(1180, 760)

    # Mantiene la ventana dentro del área visible (sin tapar barra de tareas).
    try:
        screen = app.primaryScreen()
        if screen is not None:
            ag = screen.availableGeometry()
            target_w = min(1560, int(ag.width() * 0.95))
            target_h = min(940, int(ag.height() * 0.92))
            win.resize(max(1180, target_w), max(760, target_h))
            win.move(
                ag.x() + max(8, (ag.width() - win.width()) // 2),
                ag.y() + max(8, (ag.height() - win.height()) // 2),
            )
    except Exception:
        pass

    root = QWidget()
    outer_lay = QVBoxLayout()
    outer_lay.setSpacing(0)
    outer_lay.setContentsMargins(0, 0, 0, 0)

    # ── Brand header bar ────────────────────────────────────────────────────
    header_bar = QWidget()
    header_bar.setObjectName("headerBar")
    header_bar.setFixedHeight(46)
    hdr_lay = QHBoxLayout()
    hdr_lay.setContentsMargins(20, 0, 20, 0)
    hdr_lay.setSpacing(10)
    brand_lbl = QLabel("\u25c8  OCR Enterprise")
    brand_lbl.setObjectName("brandLabel")
    hdr_lay.addWidget(brand_lbl)
    sep_lbl = QLabel("\u00b7")
    sep_lbl.setStyleSheet("color: #D1D5DB; font-size: 18px;")
    hdr_lay.addWidget(sep_lbl)
    sub_lbl = QLabel("Powered by GLM-4V")
    sub_lbl.setStyleSheet("color: #6B7280; font-size: 12px; font-weight: 500;")
    hdr_lay.addWidget(sub_lbl)
    hdr_lay.addStretch()
    # Theme toggle
    theme_btn = QPushButton("\u263e  Modo Oscuro")
    theme_btn.setCheckable(True)
    theme_btn.setFixedHeight(28)
    theme_btn.setObjectName("themeToggle")
    def _toggle_theme(checked: bool) -> None:
        try:
            if checked:
                app.setStyleSheet(APP_QSS)
                theme_btn.setText("\u2600  Modo Claro")
            else:
                app.setStyleSheet(APP_QSS_LIGHT)
                theme_btn.setText("\u263e  Modo Oscuro")
            # guardar preferencia en el config del usuario si es posible
            try:
                cfg_cfg = {}
                try:
                    cfg_cfg = cfg._load_user_config() or {}
                except Exception:
                    cfg_cfg = {}
                cfg_cfg["theme"] = "dark" if checked else "light"
                try:
                    cfg._save_user_config(cfg_cfg)
                except Exception:
                    pass
            except Exception:
                pass
        except Exception:
            pass
    theme_btn.toggled.connect(_toggle_theme)
    hdr_lay.addWidget(theme_btn)
    ver_lbl = QLabel("v2.0")
    ver_lbl.setObjectName("versionLabel")
    hdr_lay.addWidget(ver_lbl)
    header_bar.setLayout(hdr_lay)
    outer_lay.addWidget(header_bar)

    # ── Three-column content ───────────────────────────────────────────────
    content_widget = QWidget()
    layout = QHBoxLayout()
    layout.setSpacing(0)
    layout.setContentsMargins(0, 0, 0, 0)

    cfg = ConfigPanel()
    cfg.setFixedWidth(360)
    # Update estimated cost on mistral mode change
    try:
        def _on_mistral_mode_change(_idx: int) -> None:
            try:
                backend = cfg.backend_cb.currentText() if getattr(cfg, 'backend_cb', None) else ''
                if backend == 'mistral-ocr-latest' and getattr(stage, 'estimated_cost_lbl', None):
                    _idx2 = cfg.mistral_mode_cb.currentIndex() if getattr(cfg, 'mistral_mode_cb', None) else 1
                    per = 0.01 if _idx2 == 0 else (0.03 if _idx2 == 2 else 0.02)
                    n = len(_file_paths)
                    stage.estimated_cost_lbl.setText(f"Costo estimado lote: ${n*per:.2f} ({n} docs × ${per:.2f})")
            except Exception:
                pass
        if getattr(cfg, 'mistral_mode_cb', None):
            cfg.mistral_mode_cb.currentIndexChanged.connect(_on_mistral_mode_change)
    except Exception:
        pass

    # aplicar preferencia de tema guardada (si existe)
    try:
        try:
            user_cfg = cfg._load_user_config() or {}
        except Exception:
            user_cfg = {}
        if user_cfg.get("theme") == "dark":
            app.setStyleSheet(APP_QSS)
            try:
                theme_btn.setChecked(True)
                theme_btn.setText("\u2600  Modo Claro")
            except Exception:
                pass
        else:
            app.setStyleSheet(APP_QSS_LIGHT)
            try:
                theme_btn.setChecked(False)
                theme_btn.setText("\u263e  Modo Oscuro")
            except Exception:
                pass
    except Exception:
        pass

    # Crear el QTabWidget central: 'Archivos' + las pestañas de ConfigPanel (sin duplicar Operación)
    central_tabs = QTabWidget()
    central_tabs.setObjectName("mainTabs")

    stage = StagePanel()
    log = LogPanel()
    # Sincronizar la opción de 'merge' entre ConfigPanel y StagePanel
    try:
        if getattr(cfg, 'merge_chk', None) and getattr(stage, 'merge_chk', None):
            try:
                stage.merge_chk.setChecked(cfg.merge_chk.isChecked())
            except Exception:
                pass
            try:
                cfg.merge_chk.toggled.connect(lambda v: stage.merge_chk.setChecked(v))
            except Exception:
                pass
            try:
                stage.merge_toggled.connect(lambda v: cfg.merge_chk.setChecked(v))
            except Exception:
                pass
    except Exception:
        pass
    # Nuevas pestañas: Credenciales IA, Previsualizador, Configuración Avanzada
    try:
        from .ai_credentials_panel import AICredentialsPanel
        ai_panel = AICredentialsPanel()
        central_tabs.addTab(ai_panel, "🔐 Credenciales IA")
        # Conectar botones de validación/guardar del panel de IA con ConfigPanel
        try:
            def _on_ai_validate() -> None:
                try:
                    if getattr(cfg, 'token_input', None) is not None:
                        cfg.token_input.setText(ai_panel.ocr_token_input.text().strip())
                    # si ConfigPanel tiene google_creds_input, sincronizar
                    if getattr(cfg, 'google_creds_input', None) is not None:
                        cfg.google_creds_input.setText(ai_panel.ocr_json_input.text().strip())
                    # invocar validación estándar del ConfigPanel si existe
                    try:
                        if getattr(cfg, 'validate_api_key', None):
                            cfg.validate_api_key()
                    except Exception:
                        pass
                except Exception:
                    pass

            ai_panel.ocr_validate_btn.clicked.connect(_on_ai_validate)

            def _on_postocr_validate() -> None:
                try:
                    if getattr(cfg, 'postocr_model_cb', None) is not None:
                        cfg.postocr_model_cb.setCurrentText(ai_panel.postocr_model_cb.currentText())
                except Exception:
                    pass

            ai_panel.postocr_validate_btn.clicked.connect(_on_postocr_validate)
        except Exception:
            pass
    except Exception:
        ai_panel = None
    try:
        from .preview_panel import PreviewPanel
        preview_panel = PreviewPanel()
        central_tabs.addTab(preview_panel, "📄 Previsualizador")
    except Exception:
        preview_panel = None
    try:
        from .advanced_config_panel import AdvancedConfigPanel
        adv_panel = AdvancedConfigPanel()
        central_tabs.addTab(adv_panel, "⚙️ Configuración Avanzada")
    except Exception:
        adv_panel = None

    # Prompt Library panel
    try:
        from .prompt_library_panel import PromptLibraryPanel
        from src.core.prompt_manager import PromptManager

        prompt_library = PromptLibraryPanel()
        central_tabs.addTab(prompt_library, "📚 Prompts")

        # manager instance used by the handler
        prompt_manager = PromptManager()

        from PyQt6.QtWidgets import QMessageBox as _QMessageBox
        import json as _json

        def _on_prompt_selected(prompt_name: str) -> None:
            # Cargar contenido del prompt
            content = ""
            try:
                content = prompt_manager.load_prompt(prompt_name)
            except Exception:
                content = ""

            # Actualizar selector en ConfigPanel
            try:
                if getattr(cfg, 'prompt_template_cb', None) is not None:
                    idx = cfg.prompt_template_cb.findText(prompt_name)
                    if idx >= 0:
                        cfg.prompt_template_cb.setCurrentIndex(idx)
                    else:
                        cfg.prompt_template_cb.setCurrentText(prompt_name)
                setattr(cfg, 'selected_prompt_template', prompt_name)
            except Exception:
                pass

            # Actualizar expected_keys si el prompt contiene esquema JSON
            if "{" in content:
                try:
                    schema = None
                    if "```json" in content:
                        schema_text = content.split("```json", 1)[1].split("```", 1)[0]
                        schema = _json.loads(schema_text)
                    else:
                        schema = _json.loads(content)
                    if isinstance(schema, dict) and getattr(cfg, 'update_expected_keys', None):
                        req = schema.get('required', [])
                        if isinstance(req, list):
                            cfg.update_expected_keys(list(req))
                except Exception:
                    pass

            try:
                _QMessageBox.information(
                    win,
                    "Prompt activado",
                    f"Prompt '{prompt_name}' seleccionado.\nSe aplicará al próximo procesamiento.",
                )
            except Exception:
                pass

        try:
            prompt_library.prompt_selected.connect(_on_prompt_selected)
        except Exception:
            pass
    except Exception:
        pass

    # Conectar StagePanel <-> PreviewPanel
    try:
        if preview_panel is not None:
            stage.files_dropped.connect(lambda files: preview_panel.add_files(files))
            def _on_preview_removed(path: str) -> None:
                try:
                    # quitar de la lista global _file_paths y refrescar UI
                    nonlocal _file_paths
                except Exception:
                    pass
                try:
                    if path in _file_paths:
                        _file_paths.remove(path)
                    # actualizar log y preview label
                    try:
                        log.clear_table()
                        for p in _file_paths:
                            log.add_document(p)
                        log.reset_progress(total=len(_file_paths))
                    except Exception:
                        pass
                    try:
                        if _file_paths:
                            text = "\n".join(_file_paths[:10])
                            suffix = f"\n… y {len(_file_paths)-10} más" if len(_file_paths) > 10 else ""
                            stage.preview_label.setText(f"Archivos en cola: {len(_file_paths)}\n{text}{suffix}")
                            stage.drag.setText(f"✅  {len(_file_paths)} archivo(s) en cola  —  arrastra más o usa el botón")
                            stage.clear_btn.setEnabled(True)
                        else:
                            stage._clear_queue()
                    except Exception:
                        pass
                except Exception:
                    pass
            preview_panel.file_removed.connect(_on_preview_removed)
    except Exception:
        pass
    # Componer la pestaña 'Archivos' usando un splitter vertical (trabajo arriba, log abajo)
    from PyQt6.QtWidgets import QSplitter
    files_tab = QWidget()
    splitter = QSplitter(Qt.Orientation.Vertical)
    splitter.addWidget(stage)
    splitter.addWidget(log)
    # Preferir más espacio para el log (parte inferior) — stretch factors y tamaño mínimo
    try:
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        # establecer tamaños iniciales razonables (px)
        splitter.setSizes([360, 720])
    except Exception:
        try:
            splitter.setSizes([480, 520])
        except Exception:
            pass
    try:
        log.setMinimumHeight(200)
    except Exception:
        pass
    files_lay = QVBoxLayout()
    files_lay.setContentsMargins(0, 0, 0, 0)
    files_lay.addWidget(splitter)
    files_tab.setLayout(files_lay)
    central_tabs.addTab(files_tab, "Archivos")

    # Transferir pestañas internas de ConfigPanel al tab principal, excepto 'Operación'
    try:
        for i in range(cfg._tabs.count() - 1, -1, -1):
            title = cfg._tabs.tabText(i) or ""
            widget = cfg._tabs.widget(i)
            if title.strip().lower().startswith("oper"):
                continue
            cfg._tabs.removeTab(i)
            central_tabs.addTab(widget, title)
    except Exception:
        pass

    # ── Rutas completas acumuladas (los nombres de tabla son solo basenames) ──
    _file_paths: list[str] = []
    _worker: list[OcrWorker] = []
    _last_batch_rows: list[dict] = []   # acumula resultados OCR del lote activo
    _results_cache: dict = {}              # {basename: {"json": {}, "image": path, "confidence": {}}}
    _mistral_total_cost: float = 0.0
    _is_processing: list[bool] = [False]

    # ── Panel de excepciones FASE 4 ───────────────────────────────────────────
    from .exception_dashboard import ExceptionDashboard
    exc_dashboard = ExceptionDashboard()
    central_tabs.addTab(exc_dashboard, "⚠ Excepciones")

    # ─── Pestaña "Revisión Visual" – Mesa de Luz ─────────────────────────
    from .review_panel import ReviewPanel as _ReviewPanel
    review_panel_widget = _ReviewPanel(parent=win)
    central_tabs.addTab(review_panel_widget, "🔍 Revisión Visual")

    # ─── Pestaña "📊 MD → Excel" – Conversión directa sin re-OCR ────────────
    _md_excel_panel = None
    try:
        from .md_to_excel_panel import MdToExcelPanel as _MdToExcelPanel
        _md_excel_panel = _MdToExcelPanel(parent=win)
        # Insertar justo después de la pestaña "Archivos" para que sea visible
        _archivos_idx = -1
        for _ti in range(central_tabs.count()):
            if central_tabs.tabText(_ti) == "Archivos":
                _archivos_idx = _ti
                break
        if _archivos_idx >= 0:
            central_tabs.insertTab(_archivos_idx + 1, _md_excel_panel, "📊 MD → Excel")
        else:
            central_tabs.insertTab(1, _md_excel_panel, "📊 MD → Excel")

        def _sync_md_excel_credentials() -> None:
            """Sincroniza credenciales del panel IA con el panel MD→Excel."""
            if _md_excel_panel is None:
                return
            try:
                provider = ""
                api_key  = ""
                model    = ""
                base_url = ""
                if ai_panel is not None:
                    _ai_model = getattr(ai_panel, 'postocr_model_cb', None) and ai_panel.postocr_model_cb.currentText() or ""
                    _ai_token = getattr(ai_panel, 'postocr_token_input', None) and ai_panel.postocr_token_input.text().strip() or ""
                    # mapear modelo a proveedor (mismo helper de la ventana principal)
                    _m = (_ai_model or "").strip().lower()
                    if "deep" in _m:
                        provider = "DeepSeek"
                    elif "google" in _m or "gemini" in _m:
                        provider = "Google Gemini Flash (gratuito)"
                    elif "gpt" in _m or "openai" in _m:
                        provider = "OpenAI GPT-4o"
                    elif "qwen" in _m:
                        provider = "Qwen (Alibaba Cloud)"
                    elif "mistral" in _m:
                        provider = "Mistral Large"
                    elif "claude" in _m or "anthropic" in _m:
                        provider = "Anthropic (Claude 3.5)"
                    api_key  = _ai_token
                    # Mapear texto de UI a nombre de modelo real
                    _model_map = {
                        "deep seek": "", "qwen": "", "mistral": "",
                        "google": "", "open router": "", "openrouter": "",
                        "gpt-4o-mini": "gpt-4o-mini", "gpt-4o": "gpt-4o",
                        "gpt-4o-realtime": "gpt-4o-realtime", "local-ner": "local-ner",
                        "claude-3-haiku": "claude-3-haiku",
                    }
                    model = _model_map.get(_ai_model.strip().lower(), _ai_model)
                _md_excel_panel.set_ai_credentials(provider, api_key, model, base_url)
            except Exception:
                pass

        # Sincronizar al cambiar a la pestaña MD→Excel
        def _on_tab_changed(idx: int) -> None:
            try:
                if "MD" in central_tabs.tabText(idx) and "Excel" in central_tabs.tabText(idx):
                    _sync_md_excel_credentials()
            except Exception:
                pass

        try:
            central_tabs.currentChanged.connect(_on_tab_changed)
        except Exception:
            pass
    except Exception as _md_exc:
        import traceback as _tb
        print(f"[WARN] No se pudo cargar MdToExcelPanel: {_md_exc}\n{_tb.format_exc()}")
    def _open_review_panel(filename: str, file_path: str = "") -> None:
        key = filename
        # Prefer explicit file_path if provided
        if file_path:
            # normalize to basename key stored in cache
            key = file_path.split(os.sep)[-1]
        if key not in _results_cache:
            return
        for i in range(central_tabs.count()):
            if "Revisión Visual" in central_tabs.tabText(i):
                central_tabs.setCurrentIndex(i)
                break
        data = _results_cache[key]
        try:
            # Determinar formato de visualización: JSON o Markdown
            out_mode = (getattr(cfg, 'ocr_output_cb', None) and cfg.ocr_output_cb.currentText()) or "JSON"
            if out_mode and out_mode.lower().startswith("markdown"):
                # Si tenemos JSON estructurado, conviértelo a Markdown simple
                j = data.get("json", {}) or {}
                if isinstance(j, dict) and j:
                    md_lines = []
                    for k, v in j.items():
                        md_lines.append(f"**{k}**: {v}")
                    text_md = "\n\n".join(md_lines)
                else:
                    # fallback: mostrar campo 'text' si existe
                    text_md = data.get("text") or data.get("raw_text") or ""
                review_panel_widget.load_document(
                    data.get("image", ""),
                    text_md,
                    data.get("confidence"),
                )
            else:
                # Mostrar JSON estructurado (tabla editable)
                review_panel_widget.load_document(
                    data.get("image", ""),
                    data.get("json", {}),
                    data.get("confidence"),
                )
        except Exception:
            pass

    log.row_double_clicked.connect(_open_review_panel)

    # ── Barra de exportación ERP (oculta hasta que termine un lote) ──────────
    from PyQt6.QtWidgets import QMessageBox as _QMB, QComboBox as _QCombo
    erp_bar = QFrame()
    erp_bar.setObjectName("card")
    erp_bar.setFixedHeight(44)
    erp_bar_lay = QHBoxLayout()
    erp_bar_lay.setContentsMargins(12, 0, 12, 0)
    erp_bar_lay.setSpacing(8)
    erp_lbl = QLabel("📤  Lote procesado — exportar a ERP:")
    erp_lbl.setStyleSheet("color: #6EE7B7; font-size: 12px; font-weight: 600;")
    erp_bar_lay.addWidget(erp_lbl)
    erp_fmt_cb = _QCombo()
    erp_fmt_cb.addItems(["journal (CSV genérico)", "odoo (Odoo CSV)", "odoo_xml (Odoo XML)", "sap (SAP CSV)"])
    erp_fmt_cb.setFixedWidth(200)
    erp_bar_lay.addWidget(erp_fmt_cb)
    erp_export_btn = QPushButton("Exportar a ERP")
    erp_export_btn.setObjectName("startBtn")
    erp_export_btn.setFixedWidth(130)
    erp_bar_lay.addWidget(erp_export_btn)
    review_btn = QPushButton("\U0001f441 Revisar Lote")
    review_btn.setObjectName("pickBtn")
    review_btn.setFixedWidth(130)
    erp_bar_lay.addWidget(review_btn)
    erp_bar_lay.addStretch()
    erp_bar.setLayout(erp_bar_lay)
    erp_bar.setVisible(False)

    # ── FASE 6: Barra de vigilancia de carpeta ────────────────────────────────
    _watcher_ref: list = []   # [FolderWatcher] — evita GC

    watcher_bar = QFrame()
    watcher_bar.setObjectName("card")
    watcher_bar.setFixedHeight(44)
    wb_lay = QHBoxLayout()
    wb_lay.setContentsMargins(12, 0, 12, 0)
    wb_lay.setSpacing(8)
    wb_lbl = QLabel("📂 Carpeta vigilada:")
    wb_lbl.setStyleSheet("color:#9CA3AF; font-size:11px;")
    wb_lay.addWidget(wb_lbl)
    _watcher_input = QLineEdit()
    _watcher_input.setPlaceholderText("Selecciona una carpeta de entrada...")
    _watcher_input.setFixedHeight(28)
    _watcher_input.setObjectName("watcherInput")
    wb_lay.addWidget(_watcher_input, stretch=1)
    _watcher_browse_btn = QPushButton("📁")
    _watcher_browse_btn.setFixedSize(28, 28)
    _watcher_browse_btn.setToolTip("Seleccionar carpeta")
    wb_lay.addWidget(_watcher_browse_btn)
    _watcher_start_btn = QPushButton("► Vigilar")
    _watcher_start_btn.setFixedHeight(28)
    _watcher_start_btn.setCheckable(True)
    _watcher_start_btn.setObjectName("watcherToggle")
    wb_lay.addWidget(_watcher_start_btn)
    # etiqueta de estado del circuit breaker
    _cb_status_lbl = QLabel("✅ CB: OK")
    _cb_status_lbl.setStyleSheet("color:#6EE7B7; font-size:10px; padding:0 6px;")
    _cb_status_lbl.setToolTip("Estado del Circuit Breaker del backend OCR")
    wb_lay.addWidget(_cb_status_lbl)
    watcher_bar.setLayout(wb_lay)

    def _browse_watch_folder() -> None:
        from PyQt6.QtWidgets import QFileDialog
        folder = QFileDialog.getExistingDirectory(win, "Seleccionar carpeta a vigilar")
        if folder:
            _watcher_input.setText(folder)

    _watcher_browse_btn.clicked.connect(_browse_watch_folder)

    def _toggle_watcher(checked: bool) -> None:
        try:
            from src.core.folder_watcher import FolderWatcher
        except ImportError:
            QMessageBox.critical(win, "Módulo no encontrado", "folder_watcher.py no está disponible.")
            _watcher_start_btn.setChecked(False)
            return
        if checked:
            folder = _watcher_input.text().strip()
            if not folder:
                QMessageBox.warning(win, "Carpeta no especificada", "Introduce la ruta de la carpeta a vigilar.")
                _watcher_start_btn.setChecked(False)
                return
            _watcher_start_btn.setText("■ Detener")
            from PyQt6.QtCore import QMetaObject, Qt as _Qt2, Q_ARG
            def _on_new_file(path: str) -> None:
                # Ejecutar en el hilo Qt de forma segura
                QMetaObject.invokeMethod(
                    win, "_dispatch_watched_file",
                    _Qt2.ConnectionType.QueuedConnection,
                )
                # Fallback: añadir a la cola de archivos directamente con un QTimer
                try:
                    from PyQt6.QtCore import QTimer as _QTimer
                    _QTimer.singleShot(0, lambda p=path: _on_files([p]))
                except Exception:
                    pass
            w_obj = FolderWatcher(
                folder=folder,
                on_new_file=_on_new_file,
            )
            w_obj.start()
            _watcher_ref.clear()
            _watcher_ref.append(w_obj)
        else:
            _watcher_start_btn.setText("► Vigilar")
            if _watcher_ref:
                try:
                    _watcher_ref[0].stop()
                except Exception:
                    pass
            _watcher_ref.clear()

    _watcher_start_btn.toggled.connect(_toggle_watcher)

    # Actualizar etiqueta del circuit breaker cada 10 segundos
    def _refresh_cb_status() -> None:
        try:
            from src.core.circuit_breaker import get_breaker
            backend = cfg.backend_cb.currentText() if getattr(cfg, 'backend_cb', None) else "API"
            cb = get_breaker(backend or "API")
            text = cb.status_text()
            _cb_status_lbl.setText(f"CB: {text}")
            color = "#6EE7B7" if "OK" in text else ("#FCD34D" if "PROB" in text else "#FCA5A5")
            _cb_status_lbl.setStyleSheet(f"color:{color}; font-size:10px; padding:0 6px;")
        except Exception:
            pass

    _cb_timer = QTimer(win)
    _cb_timer.timeout.connect(_refresh_cb_status)
    _cb_timer.start(10_000)   # cada 10 s
    _refresh_cb_status()

    def _on_files(files: list[str]) -> None:
        _file_paths.extend(files)
        for p in files:
            log.add_document(p)
        # update estimated cost label based on backend + mode
        try:
            backend = cfg.backend_cb.currentText() if getattr(cfg, 'backend_cb', None) else ''
            if backend == 'mistral-ocr-latest' and getattr(stage, 'estimated_cost_lbl', None):
                # 3 niveles: batch>1000=$0.01, estándar=$0.02, con anotaciones=$0.03
                try:
                    _idx2 = cfg.mistral_mode_cb.currentIndex() if getattr(cfg, 'mistral_mode_cb', None) else 1
                    per = 0.01 if _idx2 == 0 else (0.03 if _idx2 == 2 else 0.02)
                except Exception:
                    per = 0.02
                n = len(_file_paths)
                try:
                    stage.estimated_cost_lbl.setText(f"Costo estimado lote: ${n*per:.2f} ({n} docs × ${per:.2f})")
                except Exception:
                    pass
        except Exception:
            pass

        # Guard: solo procesar cuando se invoca desde _on_start (vía _is_processing=True)
        if not _is_processing[0]:
            return

        # Leer parámetros de salida desde ConfigPanel
        try:
            output_dir = cfg.dst_input.text().strip() if getattr(cfg, 'dst_input', None) else ""
            if not output_dir:
                from pathlib import Path as _P2
                output_dir = str(_P2.home() / "OCR_output")
        except Exception:
            from pathlib import Path as _P2
            output_dir = str(_P2.home() / "OCR_output")
        try:
            out_format = (cfg.format_cb.currentText() if getattr(cfg, 'format_cb', None) else "xlsx").lower()
        except Exception:
            out_format = "xlsx"
        try:
            merge = cfg.merge_chk.isChecked() if getattr(cfg, 'merge_chk', None) else False
        except Exception:
            merge = False
        try:
            profile = cfg.profile
        except Exception:
            profile = "default"
        try:
            include_images = cfg.include_images_chk.isChecked() if getattr(cfg, 'include_images_chk', None) else False
        except Exception:
            include_images = False
        try:
            expected_keys = cfg.get_expected_keys() if callable(getattr(cfg, 'get_expected_keys', None)) else []
        except Exception:
            expected_keys = []
        try:
            export_profile = cfg.export_profile_cb.currentText() if getattr(cfg, 'export_profile_cb', None) else ""
        except Exception:
            export_profile = ""
        try:
            vendor_master = str(cfg.vendor_master_path or "") if getattr(cfg, 'vendor_master_path', None) is not None else ""
        except Exception:
            vendor_master = ""

        # Normalizar nombre del backend y obtener API key de config (fallbacks)
        try:
            backend_selected = backend
        except Exception:
            backend_selected = ''

        # Sincronizar backend_selected con el panel de credenciales IA.
        # ocr_model_cb tiene prioridad sobre el backend_cb del ConfigPanel para
        # evitar que un "glm" residual en config_panel anule la selección del usuario.
        try:
            _ai_ocr_text = (
                getattr(ai_panel, 'ocr_model_cb', None) and
                ai_panel.ocr_model_cb.currentText() or ""
            ).lower()
            _AI_MODEL_BACKEND_MAP = {
                "mistral ocr": "mistral-ocr-latest",
                "google vision": "google-vision",
                "google docs": "google-docs",
            }
            for _am, _ab in _AI_MODEL_BACKEND_MAP.items():
                if _am in _ai_ocr_text:
                    backend_selected = _ab
                    try:
                        if getattr(cfg, 'backend_cb', None):
                            cfg.backend_cb.setCurrentText(_ab)
                    except Exception:
                        pass
                    break
        except Exception:
            pass

        try:
            _cfg_data = cfg._load_user_config() if getattr(cfg, '_load_user_config', None) else {}
            if not isinstance(_cfg_data, dict):
                _cfg_data = {}
        except Exception:
            _cfg_data = {}

        try:
            api_key = getattr(cfg, 'api_key_input', None) and cfg.api_key_input.text().strip() or str(_cfg_data.get('api_key', '') or '').strip() or os.environ.get('OPENAI_API_KEY', '')
        except Exception:
            try:
                api_key = str(_cfg_data.get('api_key', '') or '').strip()
            except Exception:
                api_key = ''
        # Fallback: intentar leer keyring si todavía no hay api_key
        try:
            if not api_key:
                try:
                    import keyring
                    _kr = keyring.get_password('ocr_glm', 'api_key')
                    if _kr:
                        api_key = _kr.strip()
                except Exception:
                    pass
        except Exception:
            pass

        # placeholder: batch review handler attached later; avoid pausing UI here
        _mistral_key_from_cfg = ""

        # Validación temprana: Mistral requiere su propia API key
        if backend_selected == 'mistral-ocr-latest':
            import os as _os2
            # Intentar propagar la clave al entorno desde todas las fuentes posibles
            if not _os2.environ.get('MISTRAL_API_KEY'):
                _mkey = ""
                # 1. Panel de credenciales IA (ocr_token_input)
                try:
                    _mkey = getattr(ai_panel, 'ocr_token_input', None) and ai_panel.ocr_token_input.text().strip() or ""
                except Exception:
                    pass
                # 2. Credenciales cifradas (ocr_token)
                if not _mkey:
                    try:
                        from src.core.security import load_credentials as _lc
                        _mkey = (_lc().get('ocr_token') or '').strip()
                    except Exception:
                        pass
                # 3. Config JSON (mistral_api_key)
                if not _mkey:
                    try:
                        _mkey = str(_cfg_data.get('mistral_api_key', '') or '').strip()
                    except Exception:
                        pass
                if _mkey:
                    _os2.environ['MISTRAL_API_KEY'] = _mkey
                    api_key = _mkey  # propagar también al api_key del worker
            # Si la clave ya estaba en el entorno, usarla como api_key del worker
            elif not api_key:
                api_key = _os2.environ.get('MISTRAL_API_KEY', '')
            if not _os2.environ.get('MISTRAL_API_KEY'):
                QMessageBox.warning(
                    win,
                    "API Key de Mistral requerida",
                    "Mistral OCR necesita una API Key.\n\n"
                    "Pasos:\n"
                    "1. Ve a la pestaña 'Credenciales IA'\n"
                    "2. Escribe tu clave API de Mistral (console.mistral.ai)\n"
                    "3. Pulsa 'Guardar Credenciales'\n"
                    "4. Vuelve a iniciar el proceso.",
                )
                _is_processing[0] = False
                stage.on_worker_finished()
                return

        # Validación temprana: si el backend elegido requiere API key y no hay una, avisar
        _CLOUD_NO_GLM = {"mistral-ocr-latest", "google-vision", "google-docs", "openrouter"}
        if not _is_local_backend(backend_selected or "") and backend_selected not in _CLOUD_NO_GLM:
            if not api_key:
                QMessageBox.warning(
                    win,
                    "API Key requerida",
                    f"El proveedor '{backend_selected}' requiere una API Key.\n\n"
                    "Configura tu clave en la pestaña 'Credenciales IA' o selecciona "
                    "un motor local (PaddleOCR, EasyOCR, Tesseract).",
                )
                _is_processing[0] = False
                stage.on_worker_finished()
                return

        # ── Validación: el prompt es OBLIGATORIO ──────────────────────────────
        # Sin prompt el LLM inventará un schema diferente en cada factura y el
        # Excel resultará una mezcla inservible. El usuario DEBE pegarlo en cada
        # sesión (no se guarda entre ejecuciones).
        # Se acepta de CUALQUIERA de los dos campos disponibles:
        #   · cfg.custom_prompt_input   → "Prompt de extracción" (panel Operación)
        #   · adv_panel.postocr_prompt_edit → "Prompt para Post-OCR" (Configuración Avanzada)
        def _read_any_prompt() -> str:
            """Devuelve el primer prompt no vacío encontrado entre los campos de la UI."""
            # 1) Campo principal: cfg.custom_prompt_input (panel Operación)
            try:
                _w = getattr(cfg, 'custom_prompt_input', None)
                if _w is not None:
                    _txt = _w.toPlainText().strip()
                    if _txt:
                        return _txt
            except Exception:
                pass
            # 2) Campo avanzado: adv_panel.postocr_prompt_edit (Configuración Avanzada)
            try:
                _adv = adv_panel  # variable de closure
                if _adv is not None:
                    _w2 = getattr(_adv, 'postocr_prompt_edit', None)
                    if _w2 is not None:
                        _txt2 = _w2.toPlainText().strip()
                        if _txt2:
                            return _txt2
            except Exception:
                pass
            return ""

        _custom_prompt_text = _read_any_prompt()
        if not _custom_prompt_text:
            QMessageBox.warning(
                win,
                "Prompt requerido",
                "Debes pegar tu prompt antes de procesar.\n\n"
                "Puedes pegarlo en:\n"
                "  · Panel 'Operación' → campo 'Prompt de extracción'\n"
                "  · 'Configuración Avanzada' → campo 'Prompt para Post-OCR'\n\n"
                "El prompt define las columnas del Excel de salida.\n"
                "No se guarda entre sesiones: pégalo cada vez que abras el programa.",
            )
            _is_processing[0] = False
            stage.on_worker_finished()
            return

        try:
            # Determine prompt content: custom or selected template
            prompt_content = None
            try:
                # Priorizar el contenido pegado en cualquiera de los dos campos.
                # Orden: campo principal (custom_prompt_input) → Configuración Avanzada
                # (postocr_prompt_edit) → plantilla seleccionada.
                try:
                    custom = _custom_prompt_text  # ya calculado y validado arriba
                    if custom:
                        prompt_content = custom
                    else:
                        # fallback: try selected template name and load via prompt_manager if available
                        sel_name = cfg.get_selected_prompt_name() if getattr(cfg, 'get_selected_prompt_name', None) else None
                        if sel_name and 'prompt_manager' in locals():
                            try:
                                prompt_content = prompt_manager.load_prompt(sel_name)
                            except Exception:
                                prompt_content = None
                except Exception:
                    prompt_content = None
            except Exception:
                prompt_content = None

            # fallback to selected_prompt_template or default
            if not prompt_content:
                try:
                    prompt_content = cfg.selected_prompt_template if getattr(cfg, 'selected_prompt_template', None) else None
                except Exception:
                    prompt_content = None

            # Leer proveedor de estructuración (2.º LLM) desde config de Modelos IA
            _struct_provider = ""
            _struct_key      = ""
            _struct_model    = ""
            _struct_base_url = ""
            _struct_json     = ""
            try:
                _struct_provider = getattr(cfg, 'reason_provider_cb', None) and cfg.reason_provider_cb.currentText() or ""
                _struct_key      = getattr(cfg, 'reason_token_input', None) and cfg.reason_token_input.text().strip() or ""
                _struct_model    = getattr(cfg, 'reason_model_input', None) and cfg.reason_model_input.text().strip() or ""
                _struct_base_url = getattr(cfg, 'reason_base_url_input', None) and cfg.reason_base_url_input.text().strip() or ""
                _struct_json     = getattr(cfg, 'reason_json_input', None) and cfg.reason_json_input.text().strip() or ""
            except Exception:
                pass

            # Priorizar la selección de la pestaña "Credenciales IA" si está activa.
            # Esto evita que quede fijado por defecto "Google Gemini Flash" cuando el
            # usuario seleccionó DeepSeek en el panel de post-procesado.
            try:
                def _map_postocr_model_to_provider(model_text: str) -> str:
                    m = (model_text or "").strip().lower()
                    if "deep" in m:
                        return "DeepSeek"
                    if "google" in m or "gemini" in m:
                        return "Google Gemini Flash (gratuito)"
                    if "gpt-4o" in m or "openai" in m:
                        return "OpenAI GPT-4o"
                    if "qwen" in m:
                        return "Qwen (Alibaba Cloud)"
                    if "mistral" in m:
                        return "Mistral Large"
                    if "open router" in m or "openrouter" in m:
                        return "OpenRouter"
                    if "claude" in m or "anthropic" in m:
                        return "Anthropic (Claude 3.5)"
                    return ""

                if ai_panel is not None:
                    _ai_model = getattr(ai_panel, 'postocr_model_cb', None) and ai_panel.postocr_model_cb.currentText() or ""
                    _mapped_provider = _map_postocr_model_to_provider(_ai_model)
                    _ai_token = getattr(ai_panel, 'postocr_token_input', None) and ai_panel.postocr_token_input.text().strip() or ""

                    _use_postocr = bool(getattr(ai_panel, 'use_postocr_chk', None) and ai_panel.use_postocr_chk.isChecked())
                    _seems_configured = bool(_ai_token or _mapped_provider)

                    if _mapped_provider and (_use_postocr or _seems_configured):
                        _struct_provider = _mapped_provider
                    if _ai_token:
                        _struct_key = _ai_token
            except Exception:
                pass
            try:
                _ocr_output_mode = getattr(cfg, 'ocr_output_cb', None) and cfg.ocr_output_cb.currentText() or "JSON"
            except Exception:
                _ocr_output_mode = "JSON"

            # Resolver credenciales automáticamente para el proveedor elegido.
            try:
                _cfg_data = cfg._load_user_config() if getattr(cfg, '_load_user_config', None) else {}
                if not isinstance(_cfg_data, dict):
                    _cfg_data = {}
            except Exception:
                _cfg_data = {}

            _prov_lower = str(_struct_provider or "").strip().lower()
            _provider_cfg_key_candidates = {
                "deepseek": ["deepseek_api_key", "reason_token"],
                "google gemini flash (gratuito)": ["gemini_api_key", "reason_token"],
                "google gemini pro": ["gemini_api_key", "reason_token"],
                "openai gpt-4o": ["openai_api_key", "reason_token"],
                "qwen (alibaba cloud)": ["qwen_api_key", "dashscope_api_key", "reason_token"],
                "mistral large": ["mistral_api_key", "reason_token"],
                "openrouter": ["openrouter_api_key", "reason_token"],
                "anthropic (claude 3.5)": ["openrouter_api_key", "anthropic_api_key", "reason_token"],
                "glm-4 (zhipuai)": ["zhipuai_api_key", "api_key", "reason_token"],
                "azure openai": ["azure_openai_api_key", "openai_api_key", "reason_token"],
                "ollama (local)": ["reason_token"],
                "lm studio (local)": ["reason_token"],
            }
            if not _struct_key:
                for _k in _provider_cfg_key_candidates.get(_prov_lower, ["reason_token"]):
                    _v = str(_cfg_data.get(_k, "") or "").strip()
                    if _v:
                        _struct_key = _v
                        break

            try:
                _log_provider = _struct_provider or "(vacío)"
                _log_model = _struct_model or "(default)"
                _log_key = "yes" if _struct_key else "no"
                print(f"[MainWindow] structuring provider={_log_provider} model={_log_model} key={_log_key}")
            except Exception:
                pass

            # Fallback opcional: intentar leer token desde JSON seleccionado.
            if not _struct_key and _struct_json:
                try:
                    import json as _json
                    from pathlib import Path as _P
                    _d = _json.loads(_P(_struct_json).read_text(encoding='utf-8'))
                    for _cand in ("api_key", "key", "token", "access_token"):
                        _v = str((_d or {}).get(_cand, "") or "").strip()
                        if _v:
                            _struct_key = _v
                            break
                except Exception:
                    pass

            # Mantener proveedor configurado aunque output sea Markdown:
            # la estructuración se aplica en exportación si el texto no viene en JSON.

            w = OcrWorker(
                files=list(_file_paths),
                api_key=api_key,
                output_dir=output_dir,
                output_format=out_format,
                merge=merge,
                profile=profile,
                include_images=include_images,
                expected_keys=expected_keys,
                export_profile=export_profile,
                vendor_master_path=vendor_master,
                backend=backend_selected,
                image_upscale=(1 if not getattr(cfg, 'upscale_cb', None) else (1 if cfg.upscale_cb.currentText() == 'Ninguna' else int(cfg.upscale_cb.currentText().lstrip('x')))),
                use_preprocessor=getattr(cfg, 'preprocess_chk', None) and cfg.preprocess_chk.isChecked(),
                prompt_template=prompt_content,
                use_cache=cfg.use_cache_chk.isChecked() if getattr(cfg, 'use_cache_chk', None) else True,
                local_conf_threshold=cfg.local_conf_spin.value() if getattr(cfg, 'local_conf_spin', None) else 0.8,
                prefer_local=cfg.prefer_local_chk.isChecked() if getattr(cfg, 'prefer_local_chk', None) else True,
                structuring_provider=_struct_provider or None,
                structuring_api_key=_struct_key or None,
                structuring_model=_struct_model or None,
                structuring_base_url=_struct_base_url or None,
                ocr_output_mode=_ocr_output_mode,
            )
        except Exception as exc:
            try:
                print(f"[ERROR MW] OcrWorker creation failed: {exc}")
            except Exception:
                pass
            QMessageBox.critical(win, "Error de inicio", f"No se pudo crear OcrWorker:\n{exc}")
            _is_processing[0] = False
            return
        # Pasar flag de reconciliación contable opcional
        w._accounting_validation = bool(
            getattr(cfg, 'accounting_validation_chk', None)
            and cfg.accounting_validation_chk.isChecked()
        )
        # FASE 4: flags de enrutamiento IA y auditoría
        w._smart_routing = bool(
            getattr(cfg, 'smart_routing_chk', None)
            and cfg.smart_routing_chk.isChecked()
        )
        w._audit_enabled = True
        _worker.clear()
        _worker.append(w)

        # Configure batching parameters from StagePanel UI
        try:
            bsize = getattr(stage, 'batch_size_spin', None) and stage.batch_size_spin.value() or 100
            max_docs = getattr(stage, 'max_docs_spin', None) and stage.max_docs_spin.value() or 0
            review_after = getattr(stage, 'review_after_batch_chk', None) and stage.review_after_batch_chk.isChecked() or False
            if max_docs and max_docs < len(_file_paths):
                _limit_box = QMessageBox(win)
                _limit_box.setIcon(QMessageBox.Icon.Warning)
                _limit_box.setWindowTitle("Límite de documentos activo")
                _limit_box.setText(
                    f"El lote tiene {len(_file_paths)} archivos, pero el límite actual está en {max_docs}."
                )
                _limit_box.setInformativeText(
                    "Si continúas, solo se procesarán esos documentos.\n"
                    "Puedes procesar todos ahora y dejar 'Límite docs' en 0 para futuros lotes."
                )
                _continue_btn = _limit_box.addButton("Procesar solo el límite", QMessageBox.ButtonRole.AcceptRole)
                _all_btn = _limit_box.addButton("Procesar todos", QMessageBox.ButtonRole.ActionRole)
                _cancel_btn = _limit_box.addButton(QMessageBox.StandardButton.Cancel)
                _limit_box.setDefaultButton(_all_btn)
                _limit_box.exec()

                clicked = _limit_box.clickedButton()
                if clicked == _cancel_btn:
                    stage.on_worker_finished()
                    return
                if clicked == _all_btn:
                    max_docs = 0
                    try:
                        if getattr(stage, 'max_docs_spin', None) is not None:
                            stage.max_docs_spin.setValue(0)
                    except Exception:
                        pass
            try:
                w.set_batch_params(batch_size=bsize, max_docs=max_docs, review_after_batch=review_after)
            except Exception:
                pass
        except Exception:
            pass

        # Connect batch-level signals for UI updates
        try:
            def _on_batch_started(num: int, total: int) -> None:
                try:
                    stage.qa_label.setText(f"Lote {num}/{total} - Procesando...")
                except Exception:
                    pass

            def _on_batch_completed(num: int, stats: dict) -> None:
                try:
                    stage.qa_label.setText(f"Lote {num} completado — {stats.get('processed',0)} archivos, {stats.get('errors',0)} errores")
                    # show toast summary
                    try:
                        show_toast(win, f"Lote {num}/{stats.get('total_batches','?')} completado — {stats.get('processed',0)} archivos", 'info')
                    except Exception:
                        pass
                except Exception:
                    pass

            def _on_batch_review_requested(num: int) -> None:
                try:
                    # decidir si pausar según preferencias del usuario
                    should_pause = False
                    try:
                        if getattr(stage, 'review_after_batch_chk', None) is not None and stage.review_after_batch_chk.isChecked():
                            should_pause = True
                    except Exception:
                        pass
                    try:
                        if getattr(cfg, 'preview_on_batch_chk', None) is not None and cfg.preview_on_batch_chk.isChecked():
                            should_pause = True
                    except Exception:
                        try:
                            ucfg = cfg._load_user_config() if getattr(cfg, '_load_user_config', None) else {}
                            if isinstance(ucfg, dict) and ucfg.get('preview_on_batch'):
                                should_pause = True
                        except Exception:
                            pass

                    if should_pause:
                        try:
                            stage._paused = True
                            stage.pause_btn.setText("▶   REANUDAR")
                            stage.pause_btn.setEnabled(True)
                        except Exception:
                            pass

                    # switch to review tab only if user requested it or is already there
                    try:
                        review_idx = -1
                        for i in range(central_tabs.count()):
                            if "Revisión Visual" in central_tabs.tabText(i):
                                review_idx = i
                                break
                        if review_idx >= 0:
                            should_open = False
                            try:
                                if getattr(stage, 'review_after_batch_chk', None) is not None and stage.review_after_batch_chk.isChecked():
                                    should_open = True
                            except Exception:
                                pass
                            try:
                                if getattr(cfg, 'preview_on_batch_chk', None) is not None and cfg.preview_on_batch_chk.isChecked():
                                    should_open = True
                            except Exception:
                                try:
                                    ucfg = cfg._load_user_config() if getattr(cfg, '_load_user_config', None) else {}
                                    if isinstance(ucfg, dict) and ucfg.get('preview_on_batch'):
                                        should_open = True
                                except Exception:
                                    pass
                            try:
                                if central_tabs.currentIndex() == review_idx:
                                    should_open = True
                            except Exception:
                                pass
                            if should_open:
                                central_tabs.setCurrentIndex(review_idx)
                    except Exception:
                        pass

                    try:
                        show_toast(win, f"Revisión solicitada tras lote {num}", 'warning')
                    except Exception:
                        pass
                except Exception:
                    pass

            w.batch_started.connect(_on_batch_started)
            w.batch_completed.connect(_on_batch_completed)
            w.batch_review_requested.connect(_on_batch_review_requested)
        except Exception:
            pass

        # Registrar filenames en el dashboard de excepciones para correlación
        exc_dashboard.register_filenames(_file_paths)
        exc_dashboard.clear_batch()

        w.document_done.connect(log.update_document_row)
        w.document_done.connect(exc_dashboard.on_document_done)
        w.document_qa.connect(log.update_document_qa)
        w.progress.connect(log.set_progress)
        w.tokens_used.connect(cfg.update_telemetry)
        w.finished.connect(log.on_batch_finished)
        w.finished.connect(lambda: _is_processing.__setitem__(0, False))
        w.finished.connect(stage.on_worker_finished)
        w.finished.connect(cfg.save_batch_to_monthly)
        w.error.connect(lambda msg: QMessageBox.critical(win, "Error OCR", msg))
        w.metrics_updated.connect(log.show_metric)
        def _on_export_done(path: str) -> None:
            try:
                # Si el usuario eligió un archivo de salida específico, mover/renombrar
                out_path = path
                try:
                    sel = getattr(stage, 'output_file_input', None) and stage.output_file_input.text().strip()
                except Exception:
                    sel = None
                if sel:
                    try:
                        import shutil
                        from pathlib import Path as _P
                        dst = _P(sel)
                        # crear carpeta destino si no existe
                        dst.parent.mkdir(parents=True, exist_ok=True)
                        shutil.move(out_path, str(dst))
                        out_path = str(dst)
                    except Exception:
                        pass
                try:
                    if preview_panel is not None and getattr(preview_panel, 'add_result_file', None):
                        preview_panel.add_result_file(out_path)
                        # Añadir también QA y sidecars markdown del mismo lote
                        # para comparar Excel vs OCR crudo directamente en previsualizador.
                        try:
                            from pathlib import Path as _P

                            out_p = _P(out_path)
                            qa_p = _P(str(out_p) + ".qa.json")
                            if qa_p.exists():
                                preview_panel.add_result_file(str(qa_p))

                            # Si nombre exportado contiene timestamp, usarlo para sidecars.
                            ts = ""
                            try:
                                name = out_p.stem  # ocr_resultados_YYYYmmdd_HHMMSS
                                if "ocr_resultados_" in name:
                                    ts = name.split("ocr_resultados_", 1)[1]
                            except Exception:
                                ts = ""

                            md_candidates = []
                            if ts:
                                md_candidates = sorted(out_p.parent.glob(f"*_{ts}__mistral.md"))
                            if not md_candidates:
                                md_candidates = sorted(out_p.parent.glob("*__mistral.md"))[-5:]

                            for md in md_candidates:
                                preview_panel.add_result_file(str(md))
                        except Exception:
                            pass
                except Exception:
                    pass
                try:
                    msg = f"Exportado: {out_path}" if out_path else "Exportación completada"
                    show_toast(win, msg, "success", 5000)
                except Exception:
                    pass
            except Exception:
                try:
                    msg = f"Exportado: {path}" if path else "Exportación completada"
                    show_toast(win, msg, "success", 5000)
                except Exception:
                    pass

        w.export_done.connect(_on_export_done)
        # Mostrar resumen QA cuando esté disponible
        def _on_qa_report(path: str, stats: dict) -> None:
            try:
                pct = stats.get("accuracy_pct", 0.0)
                total = stats.get("total_invoices", 0)
                passed = stats.get("invoices_passed", 0)
                show_toast(
                    win,
                    f"QA {passed}/{total} facturas, exactitud {pct:.1f}%",
                    "info",
                    5000,
                )
            except Exception:
                try:
                    show_toast(win, "QA generado", "info", 3500)
                except Exception:
                    pass

        w.qa_report.connect(_on_qa_report)

        # ── Acumulación de resultados para exportación ERP ────────────────────
        _last_batch_rows.clear()
        erp_bar.setVisible(False)

        def _on_document_result(basename: str, status: str, confidence: float,
                                 result_dict: dict | None = None) -> None:
            nonlocal _mistral_total_cost
            try:
                row = dict(result_dict or {})
                row.setdefault("archivo", basename)
                row.setdefault("status",  status)
                row.setdefault("confidence", confidence)
                _last_batch_rows.append(row)
                # Guardar en caché para la pestaña de Revisión Visual
                _results_cache[basename] = {
                    "json": dict(result_dict or {}),
                    "text": (result_dict or {}).get("text") if isinstance(result_dict, dict) else "",
                    "image": next(
                        (p for p in _file_paths if p.endswith(basename)),
                        basename,
                    ),
                    "confidence": {},
                }
                # accumulate mistral cost if present in result
                try:
                    if isinstance(result_dict, dict):
                        def _mistral_unit_price(mode: str) -> float:
                            if mode == 'with_annotations':
                                return 0.03
                            # Regla industrial solicitada: lote/gran volumen >=1000 docs => 0.01
                            try:
                                month_key = __import__('datetime').datetime.now().strftime("%Y-%m")
                                usr = cfg._load_user_config() if getattr(cfg, '_load_user_config', None) else {}
                                ms = (usr or {}).get('mistral_stats', {})
                                processed = int((ms.get(month_key, {}) or {}).get('docs_processed', 0))
                                return 0.01 if processed >= 1000 else 0.02
                            except Exception:
                                return 0.02

                        c = result_dict.get('cost_usd')
                        mm = result_dict.get('mode') or (getattr(cfg, 'mistral_mode_cb', None) and ('with_annotations' if cfg.mistral_mode_cb.currentIndex() == 2 else 'standard'))
                        per = _mistral_unit_price(mm or 'standard')
                        if c is None:
                            c = per
                        try:
                            c_float = float(c)
                        except Exception:
                            c_float = per
                        try:
                            _mistral_total_cost += c_float
                        except Exception:
                            pass
                        # persist per-month stats via config panel helper
                        try:
                            cfg.record_mistral_usage(mm or 'standard', c_float)
                        except Exception:
                            pass
                        # update stage label
                        try:
                            n = len(_file_paths)
                            if getattr(stage, 'estimated_cost_lbl', None):
                                stage.estimated_cost_lbl.setText(f"Costo estimado lote: ${n*per:.2f} ({n} docs × ${per:.2f})")
                        except Exception:
                            pass
                except Exception:
                    pass
                # Toast de error por documento fallido
                if status == "Error":
                    try:
                        show_toast(win, f"Error al procesar: {basename}", "error", 4_000)
                    except Exception:
                        pass
            except Exception:
                pass

        try:
            w.document_payload.connect(_on_document_result)
        except Exception:
            pass

        def _on_batch_finished_erp() -> None:
            try:
                if _last_batch_rows:
                    erp_bar.setVisible(True)
                    review_btn.setVisible(True)
                    errors = sum(1 for r in _last_batch_rows if r.get("status") == "Error")
                    ok = len(_last_batch_rows) - errors
                    if errors:
                        show_toast(
                            win,
                            f"Lote finalizado — {ok} OK, {errors} con error",
                            "warning",
                        )
                    else:
                        show_toast(
                            win,
                            f"\u2713 {ok} documento(s) procesados correctamente",
                            "success",
                        )
            except Exception:
                pass

        w.finished.connect(_on_batch_finished_erp)

        # ── Handler exportación ERP ───────────────────────────────────────────
        def _on_export_erp() -> None:
            try:
                from PyQt6.QtWidgets import QFileDialog
                from src.data.erp_mapper import ERPExporter

                if not _last_batch_rows:
                    QMessageBox.warning(win, "Sin datos", "No hay resultados de lote para exportar.")
                    return

                # Leer formato elegido
                fmt_text = erp_fmt_cb.currentText().split()[0]   # "journal", "odoo", etc.

                # Leer vendor master del ErpPanel si existe
                vm_path = ""
                try:
                    from .erp_panel import ErpPanel as _EP
                    for i in range(central_tabs.count()):
                        w_tab = central_tabs.widget(i)
                        if isinstance(w_tab, _EP):
                            vm_path = w_tab.vendor_master_path
                            break
                except Exception:
                    pass

                # Proponer ruta de salida
                out_dir = cfg.dst_input.text().strip() if getattr(cfg, 'dst_input', None) else ""
                import os as _os
                out_dir = out_dir or str(_os.path.expanduser("~/Desktop"))
                ext_map = {"odoo_xml": "xml", "xml": "xml"}
                ext = ext_map.get(fmt_text, "csv")

                from datetime import datetime as _dt
                default_name = f"erp_export_{fmt_text}_{_dt.today().strftime('%Y%m%d_%H%M%S')}.{ext}"
                save_path, _ = QFileDialog.getSaveFileName(
                    win, "Guardar exportación ERP",
                    str(_os.path.join(out_dir, default_name)),
                    f"Archivos *.{ext} (*.{ext});;Todos (*)",
                )
                if not save_path:
                    return

                exporter = ERPExporter(vendor_master_path=vm_path)
                out = exporter.export(_last_batch_rows, fmt=fmt_text, output_path=save_path)
                QMessageBox.information(
                    win, "Exportación ERP completada",
                    f"Formato: {fmt_text.upper()}\nArchivo: {out}\n\n"
                    f"Filas exportadas: {len(_last_batch_rows)}",
                )
                try:
                    show_toast(win, f"ERP exportado — {len(_last_batch_rows)} filas", "info")
                except Exception:
                    pass
            except Exception as _exc:
                try:
                    show_toast(win, f"Error ERP: {_exc}", "error", 5_000)
                    QMessageBox.critical(win, "Error ERP", str(_exc))
                except Exception:
                    pass

        erp_export_btn.clicked.connect(_on_export_erp)

        def _on_reviewpanel_approved(corrected: dict) -> None:
            try:
                path = getattr(review_panel_widget, '_current_path', None) or ""
                basename = os.path.basename(path) if path else ""
                if basename and basename in _results_cache:
                    _results_cache[basename]["json"] = dict(corrected or {})
                    _results_cache[basename]["reviewed"] = True
                for r in _last_batch_rows:
                    if r.get("archivo") == basename or r.get("filename") == basename:
                        r.update(dict(corrected or {}))
                        r["reviewed"] = True
                try:
                    show_toast(win, f"{basename} revisado", "success")
                except Exception:
                    pass
                # Si el lote está listo y todo fue revisado, lanzar exportación
                if erp_bar.isVisible():
                    all_rev = all(bool(rr.get("reviewed")) for rr in _last_batch_rows)
                    if all_rev:
                        try:
                            _on_export_erp()
                        except Exception:
                            pass
            except Exception:
                pass

        review_panel_widget.approved.connect(_on_reviewpanel_approved)

        def _on_review_batch() -> None:
            from .review_panel import ReviewPanel
            if not _last_batch_rows:
                return
            dlg = ReviewPanel(rows=_last_batch_rows, parent=win)

            def _on_approved(corrected_rows: list) -> None:
                for corrected in corrected_rows:
                    filename = corrected.get("archivo", corrected.get("filename", ""))
                    for i, r in enumerate(_last_batch_rows):
                        if r.get("archivo", r.get("filename", "")) == filename:
                            _last_batch_rows[i] = corrected
                            break

            dlg.approved.connect(_on_approved)
            dlg.exec()

        review_btn.clicked.connect(_on_review_batch)

        # ── FASE 6: Circuit Breaker ────────────────────────────────────────────
        try:
            from src.core.circuit_breaker import get_breaker, CircuitOpenError
            backend_name = cfg.backend_cb.currentText() if getattr(cfg, 'backend_cb', None) else "API"
            cb = get_breaker(backend_name or "API")
            if cb.is_open():
                QMessageBox.critical(
                    win, "Servicio temporalmente cortado",
                    f"El backend '{backend_name}' ha sido cortado por fallos repetidos.\n"
                    f"Estado: {cb.status_text()}\n\nEspera unos minutos o reinicia el servicio.",
                )
                stage.on_worker_finished()
                _is_processing[0] = False
                return
            cb.set_callbacks(
                on_open=lambda n: QTimer.singleShot(
                    0,
                    lambda: QMessageBox.warning(
                        win, "🔴 Circuit Breaker abierto",
                        f"El backend falló {n} veces seguidas.\nSe suspenderán los envíos durante 5 min.",
                    )
                ),
            )
        except ImportError:
            pass
        except Exception:
            pass

        try:
            w.start()
        except Exception as exc:
            QMessageBox.critical(win, "Error al iniciar", f"No se pudo arrancar el worker:\n{exc}")
            _is_processing[0] = False
            return

    def _on_cfg_tab_changed(idx: int) -> None:
        """Oculta el área de trabajo (StagePanel) cuando no estemos en la pestaña Operación."""
        try:
            # animar ancho de columnas para efecto suave
            def _animate(widget, prop, start, end, ms=280):
                try:
                    ani = QPropertyAnimation(widget, prop.encode("utf-8"))
                    ani.setStartValue(start)
                    ani.setEndValue(end)
                    ani.setDuration(ms)
                    ani.setEasingCurve(QEasingCurve.Type.InOutCubic)
                    ani.start()
                    # keep reference to avoid GC
                    setattr(widget, "_last_anim", ani)
                except Exception:
                    try:
                        widget.setMaximumWidth(end)
                    except Exception:
                        pass

            if idx == 0:
                # Mostrar sólo área de trabajo central; ocultar panel izquierdo
                stage.setVisible(True)
                try:
                    cfg.setVisible(True)
                except Exception:
                    pass
                _animate(cfg, "maximumWidth", cfg.maximumWidth() or 360, 0)
                try:
                    ani_ref = getattr(cfg, "_last_anim", None)
                    if ani_ref is not None:
                        ani_ref.finished.connect(lambda: cfg.setVisible(False))
                    else:
                        cfg.setVisible(False)
                except Exception:
                    try:
                        cfg.setVisible(False)
                    except Exception:
                        pass
            else:
                # Mostrar solo el panel izquierdo (config) y ocultar la zona central
                stage.setVisible(False)
                try:
                    cfg.setVisible(True)
                except Exception:
                    pass
                _animate(cfg, "maximumWidth", cfg.maximumWidth() or 0, 360)
        except Exception:
            pass

    def _on_pause() -> None:
        try:
            print("[MainWindow] _on_pause invoked")
        except Exception:
            pass
        if _worker:
            _worker[0].pause()

    def _on_resume() -> None:
        try:
            print("[MainWindow] _on_resume invoked")
        except Exception:
            pass
        if _worker:
            _worker[0].resume()

    def _on_stop() -> None:
        try:
            print("[MainWindow] _on_stop invoked")
        except Exception:
            pass
        _is_processing[0] = False
        if _worker:
            _worker[0].stop()
        log.stop_processing()

    def _on_queue_cleared() -> None:
        try:
            nonlocal _file_paths, _results_cache, _last_batch_rows, _is_processing, _worker, preview_panel
        except Exception:
            pass
        try:
            # Clear internal lists and caches
            _file_paths = []
            try:
                _results_cache.clear()
            except Exception:
                _results_cache = {}
            try:
                _last_batch_rows.clear()
            except Exception:
                _last_batch_rows = []

            # Reset UI: log and preview panel if present
            try:
                log.clear_table()
            except Exception:
                pass
            try:
                if preview_panel is not None:
                    try:
                        preview_panel.file_list.clear()
                    except Exception:
                        pass
                    try:
                        preview_panel.result_list.clear()
                    except Exception:
                        pass
                    try:
                        preview_panel.result_preview.clear()
                    except Exception:
                        pass
                    try:
                        preview_panel.scene.clear()
                    except Exception:
                        pass
                    try:
                        preview_panel._items = []
                    except Exception:
                        pass
                    try:
                        preview_panel._result_items = []
                    except Exception:
                        pass
            except Exception:
                pass

            # Stop any running worker
            try:
                if _worker and _is_processing[0]:
                    try:
                        _worker[0].stop()
                    except Exception:
                        pass
                _is_processing[0] = False
            except Exception:
                pass

            # Ensure stage UI reflects empty queue
            try:
                stage._clear_queue()
            except Exception:
                pass
        except Exception:
            pass

    def _on_start() -> None:
        print("[MainWindow] _on_start invoked")
        if not _file_paths:
            try:
                QMessageBox.information(
                    win,
                    "Sin archivos",
                    "Añade archivos arrastrándolos al panel antes de iniciar.",
                )
                stage.on_worker_finished()
            except Exception:
                pass
            return
        if _is_processing[0]:
            try:
                QMessageBox.warning(
                    win,
                    "En proceso",
                    "Ya hay un lote en procesamiento. Espera a que termine.",
                )
            except Exception:
                pass
            return
        _is_processing[0] = True
        # Iniciar el pipeline completo reutilizando los archivos ya en cola
        _on_files([])

    # ── Signal wiring ─────────────────────────────────────────────────────────
    stage.files_dropped.connect(_on_files)
    stage.queue_cleared.connect(_on_queue_cleared)
    stage.start_requested.connect(_on_start)
    stage.pause_requested.connect(_on_pause)
    stage.resume_requested.connect(_on_resume)
    stage.stop_requested.connect(_on_stop)

    # Confirmación de cierre para evitar pérdida de visibilidad del progreso.
    def _on_window_close(event) -> None:  # type: ignore[no-untyped-def]
        if _is_processing[0]:
            ans = QMessageBox.question(
                win,
                "Proceso en ejecución",
                "Hay un lote en proceso.\n¿Deseas cerrar la aplicación igualmente?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if ans != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            try:
                if _worker:
                    _worker[0].stop()
            except Exception:
                pass
        event.accept()

    win.closeEvent = _on_window_close  # type: ignore[assignment]

    cfg.api_validated.connect(stage.set_api_ready)

    # Gestionar api_ready según backend seleccionado y si hay token
    _LOCAL_BACKENDS = {"ocr-local", "paddle", "easyocr", "paddleocr", "tesseract"}

    def _is_local_backend(name: str) -> bool:
        n = (name or "").lower()
        return n in _LOCAL_BACKENDS or n.startswith(("paddle", "easyocr", "tesseract"))

    def _map_provider_to_backend(txt: str) -> str | None:
        """Mapea el texto del combobox de proveedor a un identificador de backend."""
        if not txt:
            return None
        t = txt.lower()
        if 'local' in t and 'paddle' in t:
            return 'paddle'
        if 'local' in t and 'easy' in t:
            return 'easyocr'
        if 'tesseract' in t:
            return 'tesseract'
        if 'ocr local' in t:
            return 'ocr-local'
        if 'glm-4v' in t or 'glm-4' in t:
            return 'glm'
        if 'openai' in t or 'gpt-4' in t:
            return 'openai'
        if 'azure' in t:
            return 'azure-vision'
        if 'google vision' in t:
            return 'google-vision'
        if 'google document' in t or 'document ai' in t:
            return 'google-docs'
        if 'mistral' in t:
            return 'mistral-ocr-latest'
        if 'openrouter' in t:
            return 'openrouter'
        return None

    def _refresh_api_ready() -> None:
        # Priorizar el proveedor seleccionado en el panel Modelos IA / Credenciales
        try:
            provider_text = cfg.ocr_provider_cb.currentText() if getattr(cfg, 'ocr_provider_cb', None) else ""
        except Exception:
            provider_text = ""
        backend_name = _map_provider_to_backend(provider_text) or \
            (cfg.backend_cb.currentText() if getattr(cfg, 'backend_cb', None) else "")
        if _is_local_backend(backend_name):
            stage.set_api_ready(True)
        else:
            # Para backends IA: listo si hay token escrito (sin obligar a pulsar Validar)
            has_token = bool(getattr(cfg, 'token_input', None) and cfg.token_input.text().strip())
            stage.set_api_ready(has_token)

    try:
        if getattr(cfg, 'backend_cb', None):
            cfg.backend_cb.currentTextChanged.connect(lambda _: _refresh_api_ready())
        if getattr(cfg, 'ocr_provider_cb', None):
            cfg.ocr_provider_cb.currentTextChanged.connect(lambda _: _refresh_api_ready())
        if getattr(cfg, 'token_input', None):
            cfg.token_input.textChanged.connect(lambda _: _refresh_api_ready())
        _refresh_api_ready()
    except Exception:
        pass

    # Conectar limpieza de caché solicitada desde StagePanel hacia ConfigPanel
    try:
        stage.clear_cache_requested.connect(cfg._clear_cache_clicked)
    except Exception:
        pass

    # Conectar actualización de QA global desde LogPanel hacia StagePanel
    try:
        log.qa_summary_updated.connect(lambda pct: stage.qa_label.setText(f"QA: {pct:.1f}%"))
    except Exception:
        pass

    # Conectar carpeta destino elegida en StagePanel al campo de ConfigPanel
    try:
        stage.dst_input.textChanged.connect(lambda txt: cfg.dst_input.setText(txt))
    except Exception:
        pass

    # Sincronizar formato entre StagePanel y ConfigPanel (bidireccional)
    try:
        if getattr(stage, 'format_cb', None) and getattr(cfg, 'format_cb', None):
            stage.format_cb.currentTextChanged.connect(lambda t: cfg.format_cb.setCurrentText(t) if getattr(cfg, 'format_cb', None) else None)
            cfg.format_cb.currentTextChanged.connect(lambda t: stage.format_cb.setCurrentText(t) if getattr(stage, 'format_cb', None) else None)
    except Exception:
        pass

    # Mapear tipo de documento seleccionado en StagePanel al perfil de extracción en ConfigPanel
    try:
        def _map_doc_type_to_profile(txt: str) -> None:
            try:
                mapping = {
                    'Factura': 0,
                    'Documento': 0,
                    'Contrato': 2,
                    'Otro': 4,
                }
                idx = mapping.get(txt, 0)
                btn = cfg._profile_group.button(idx)
                if btn:
                    btn.setChecked(True)
            except Exception:
                pass

        if getattr(stage, 'doc_type_cb', None):
            stage.doc_type_cb.currentTextChanged.connect(_map_doc_type_to_profile)
    except Exception:
        pass

    # Conectar petición de transformar PDFs -> imágenes desde StagePanel
    try:
        stage.transform_to_images_requested.connect(lambda b: cfg.preprocess_chk.setChecked(b) if getattr(cfg, 'preprocess_chk', None) else None)
    except Exception:
        # Fallback: intentar simplemente setear el checkbox si existe
        try:
            stage.transform_to_images_requested.connect(lambda b: cfg.preprocess_chk.setChecked(b) if getattr(cfg, 'preprocess_chk', None) else None)
        except Exception:
            pass

    # Conectar petición de transformar PDFs -> imágenes desde StagePanel
    try:
        stage.transform_to_images_requested.connect(lambda b: cfg.preprocess_chk.setChecked(b) if getattr(cfg, 'preprocess_chk', None) else None)
    except Exception:
        # Fallback: intentar simplemente setear el checkbox si existe
        try:
            stage.transform_to_images_requested.connect(lambda b: cfg.preprocess_chk.setChecked(b) if getattr(cfg, 'preprocess_chk', None) else None)
        except Exception:
            pass

    # Conectar selección de archivo de salida -> guardar nombre en cfg y actualizar carpeta
    try:
        def _on_output_file_selected(path: str) -> None:
            try:
                import os
                setattr(cfg, '_selected_output_file', path)
                # actualizar carpeta destino con la carpeta que contiene el archivo
                d = os.path.dirname(path)
                if d:
                    cfg.dst_input.setText(d)
            except Exception:
                pass
        stage.output_file_selected.connect(_on_output_file_selected)
    except Exception:
        pass

    # ── Barra de navegación lateral ────────────────────────────────────────
    # Ocultar la barra de pestañas nativa (la controla el sidebar)
    try:
        central_tabs.tabBar().setVisible(False)
    except Exception:
        pass

    _SIDEBAR_W   = 260
    _SIDEBAR_MIN = 72
    _sid_expanded = [True]

    nav_frame = QFrame()
    nav_frame.setObjectName("sidebarNav")
    nav_frame.setFixedWidth(_SIDEBAR_W)
    nav_lay = QVBoxLayout()
    nav_lay.setContentsMargins(0, 0, 0, 0)
    nav_lay.setSpacing(0)

    # Botón colapsar / expandir
    # Sidebar collapse button: keep only arrow to avoid duplicate app name in sidebar
    _collapse_btn = QPushButton("◀")
    _collapse_btn.setObjectName("sidebarToggle")
    _collapse_btn.setFixedHeight(46)
    nav_lay.addWidget(_collapse_btn)

    # Items de navegación principal (jerarquía moderna Deep Slate)
    desired = [
        ("📂", "Archivos"),
        ("🔐", "Credenciales IA"),
        ("📊", "Telemetría"),
        ("📄", "Previsualizador"),
        ("🧩", "Esquema"),
        ("🔗", "ERP"),
        ("⚙️", "Configuración Avanzada"),
        ("📊", "MD → Excel"),
    ]
    _nav_btns: list = []
    _sid_active = [0]

    def _find_tab_index(label_text: str) -> int:
        for ii in range(central_tabs.count()):
            try:
                tt = central_tabs.tabText(ii) or ""
                if label_text in tt or tt in label_text:
                    return ii
            except Exception:
                continue
        return -1

    def _activate_nav(tab_idx: int) -> None:
        _sid_active[0] = tab_idx
        for i, _b in enumerate(_nav_btns):
            _active = (i == tab_idx)
            _b.setProperty("navActive", _active)
            _b.style().unpolish(_b)
            _b.style().polish(_b)
        try:
            if 0 <= tab_idx < central_tabs.count():
                central_tabs.setCurrentIndex(tab_idx)
        except Exception:
            pass

    # crear botones en el sidebar buscando el índice de cada pestaña por nombre
    for _icon, _label in desired:
        idx = _find_tab_index(_label) or 0
        _nbtn = QPushButton(f"  {_icon}   {_label}")
        _nbtn.setObjectName("navItem")
        _nbtn.setFixedHeight(46)
        _nbtn.setProperty("navActive", idx == 0)
        # capture index at creation time
        def _make_cb(i: int):
            return lambda _chk=False, _i=i: _activate_nav(_i)
        _nbtn.clicked.connect(_make_cb(idx))
        _nav_btns.append(_nbtn)
        nav_lay.addWidget(_nbtn)

    # estructura de items navegables (icono, label, reserved)
    _NAV_ITEMS = [(i[0], i[1], None) for i in desired]

    # Separador
    _sep_line = QFrame()
    _sep_line.setFrameShape(QFrame.Shape.HLine)
    _sep_line.setFixedHeight(1)
    _sep_line.setStyleSheet("background: #E5E7EB; margin-left: 12px; margin-right: 12px;")
    nav_lay.addWidget(_sep_line)

    # Sección "Ajustes rápidos" — selector de formato compacto
    _qs_label = QLabel("AJUSTES RÁPIDOS")
    _qs_label.setObjectName("sidebarSection")
    nav_lay.addWidget(_qs_label)

    from PyQt6.QtWidgets import QComboBox as _QCB
    _fmt_cb = _QCB()
    _fmt_cb.addItems(["XLSX", "CSV", "DOCX", "TXT"])
    _fmt_cb.setObjectName("cfgCombo")
    _fmt_cb.setFixedHeight(34)
    _fmt_wrap = QWidget()
    _fmt_wrap.setStyleSheet("background: transparent;")
    _fmt_wlay = QVBoxLayout()
    _fmt_wlay.setContentsMargins(12, 4, 12, 8)
    _fmt_wlay.addWidget(_fmt_cb)
    _fmt_wrap.setLayout(_fmt_wlay)
    nav_lay.addWidget(_fmt_wrap)

    # Sincronizar formato bidireccional con ConfigPanel
    try:
        if getattr(cfg, 'format_cb', None):
            cfg.format_cb.currentTextChanged.connect(
                lambda t: _fmt_cb.setCurrentText(t) if t != _fmt_cb.currentText() else None
            )
            _fmt_cb.currentTextChanged.connect(
                lambda t: cfg.format_cb.setCurrentText(t) if getattr(cfg, 'format_cb', None) else None
            )
    except Exception:
        pass

    nav_lay.addStretch(1)

    # Separador footer
    _sep_foot = QFrame()
    _sep_foot.setFrameShape(QFrame.Shape.HLine)
    _sep_foot.setFixedHeight(1)
    _sep_foot.setStyleSheet("background: #E5E7EB; margin-left: 12px; margin-right: 12px;")
    nav_lay.addWidget(_sep_foot)

    _footer_lbl = QLabel("v2.0  ·  OCR Enterprise")
    _footer_lbl.setObjectName("sidebarFooter")
    nav_lay.addWidget(_footer_lbl)

    nav_frame.setLayout(nav_lay)

    # Animación colapso / expansión
    def _toggle_sidebar(_chk: bool = False) -> None:
        _sid_expanded[0] = not _sid_expanded[0]
        _target = _SIDEBAR_W if _sid_expanded[0] else _SIDEBAR_MIN
        try:
            _ani = QPropertyAnimation(nav_frame, b"maximumWidth")
            _ani.setStartValue(nav_frame.width())
            _ani.setEndValue(_target)
            _ani.setDuration(220)
            _ani.setEasingCurve(QEasingCurve.Type.InOutCubic)
            _ani.start()
            nav_frame._anim_ref = _ani  # evitar GC
        except Exception:
            nav_frame.setFixedWidth(_target)

        _expanded = _sid_expanded[0]
        # Show only arrows when toggling; app title is shown in header bar
        _collapse_btn.setText("◀" if _expanded else "▶")
        for i, (_ic, _lb, _) in enumerate(_NAV_ITEMS):
            _nav_btns[i].setText(f"  {_ic}   {_lb}" if _expanded else f"  {_ic}")
        _qs_label.setVisible(_expanded)
        _fmt_wrap.setVisible(_expanded)
        _footer_lbl.setVisible(_expanded)

    _collapse_btn.clicked.connect(_toggle_sidebar)

    layout.addWidget(nav_frame)

    # ── Añadir el QTabWidget central con las pestañas principales
    # La barra ERP se coloca debajo del tab widget, dentro de un VBox
    from PyQt6.QtWidgets import QVBoxLayout as _QVBox2
    _central_col = QWidget()
    _central_col_lay = _QVBox2()
    _central_col_lay.setSpacing(0)
    _central_col_lay.setContentsMargins(0, 0, 0, 0)
    _central_col_lay.addWidget(central_tabs, stretch=1)
    _central_col_lay.addWidget(watcher_bar)
    _central_col_lay.addWidget(erp_bar)
    _central_col.setLayout(_central_col_lay)
    layout.addWidget(_central_col, stretch=1)

    content_widget.setLayout(layout)

    # Scroll general para no perder controles en alturas pequeñas.
    from PyQt6.QtWidgets import QScrollArea
    root_scroll = QScrollArea()
    root_scroll.setWidgetResizable(True)
    root_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    root_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    root_scroll.setFrameShape(QFrame.Shape.NoFrame)
    root_scroll.setWidget(content_widget)
    outer_lay.addWidget(root_scroll, stretch=1)
    root.setLayout(outer_lay)
    win.setCentralWidget(root)
    win.show()
    return app.exec()


def start_ui() -> Optional[int]:
    try:
        return _start_qt_app()
    except ModuleNotFoundError as exc:
        print(f"Módulo no encontrado: {exc}")
        return None
    except Exception as exc:
        print("Error al iniciar la UI:", exc)
        return None


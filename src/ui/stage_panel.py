from __future__ import annotations

from PyQt6.QtWidgets import (
    QFrame,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QWidget,
    QLineEdit,
    QSizePolicy,
    QPushButton,
    QFileDialog,
)
from PyQt6.QtCore import pyqtSignal, Qt
import json
from pathlib import Path


class DragDropArea(QLabel):
    files_dropped = pyqtSignal(list)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("dragArea")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setAcceptDrops(True)
        self.setText(
            "⬇   Arrastra carpetas o archivos aquí para procesar\n\n"
            "Formatos soportados: PDF · JPEG · PNG · TIFF"
        )
        self.setWordWrap(True)

    def dragEnterEvent(self, event) -> None:  # type: ignore[override]
        if event.mimeData().hasUrls() or event.mimeData().hasText():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:  # type: ignore[override]
        if event.mimeData().hasUrls() or event.mimeData().hasText():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:  # type: ignore[override]
        mime = event.mimeData()
        urls: list[str] = []
        if mime.hasUrls():
            for url in mime.urls():
                try:
                    urls.append(str(url.toLocalFile()))
                except Exception:
                    pass
        elif mime.hasText():
            urls.append(mime.text())
        if urls:
            self.files_dropped.emit(urls)


class StagePanel(QFrame):
    files_dropped    = pyqtSignal(list)
    queue_cleared    = pyqtSignal()
    start_requested  = pyqtSignal()
    pause_requested  = pyqtSignal()
    resume_requested = pyqtSignal()
    stop_requested   = pyqtSignal()
    clear_cache_requested = pyqtSignal()
    output_file_selected = pyqtSignal(str)
    transform_to_images_requested = pyqtSignal(bool)
    merge_toggled = pyqtSignal(bool)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("stagePanel")
        self._api_ready = True   # no bloquear inicio; la clave API es opcional en modo simulación
        self._has_files = False
        self._paused    = False


        layout = QVBoxLayout()
        layout.setSpacing(18)
        layout.setContentsMargins(16, 16, 16, 16)

        # ── Drag & Drop area ──────────────────────────────────────────────────
        self.drag = DragDropArea()
        self.drag.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.drag.files_dropped.connect(self._on_drop)
        layout.addWidget(self.drag, stretch=1)

        # ── File picker row (fallback para cuando drag-drop no funciona) ──────
        picker_row = QWidget()
        picker_lay = QHBoxLayout()
        picker_lay.setContentsMargins(0, 0, 0, 0)
        picker_lay.setSpacing(8)

        self.pick_btn = QPushButton("📂  Seleccionar Archivos…")
        self.pick_btn.setObjectName("pickBtn")
        self.pick_btn.setFixedHeight(36)
        self.pick_btn.setToolTip("Abre el selector de archivos para agregar documentos a la cola")
        self.pick_btn.clicked.connect(self._browse_files)

        self.clear_btn = QPushButton("🗑  Limpiar Cola")
        self.clear_btn.setObjectName("clearBtn")
        self.clear_btn.setFixedHeight(36)
        self.clear_btn.setEnabled(False)
        self.clear_btn.setToolTip("Elimina todos los archivos de la cola de procesamiento")
        self.clear_btn.clicked.connect(self._clear_queue)

        picker_lay.addWidget(self.pick_btn)
        picker_lay.addWidget(self.clear_btn)
        # Botón para limpiar caché (disparará señal para que ConfigPanel lo gestione)
        self.clear_cache_btn = QPushButton("🧹 Limpiar caché")
        self.clear_cache_btn.setObjectName("clearBtn")
        self.clear_cache_btn.setFixedHeight(36)
        self.clear_cache_btn.setToolTip("Limpia la caché de resultados OCR guardados localmente")
        self.clear_cache_btn.clicked.connect(lambda: self.clear_cache_requested.emit())
        # Aplicar iconos estándar de Qt donde sea posible
        try:
            from PyQt6.QtWidgets import QApplication
            app = QApplication.instance()
            if app is not None:
                style = app.style()
                try:
                    self.pick_btn.setIcon(style.standardIcon(getattr(style, 'SP_DirOpenIcon')))
                except Exception:
                    try:
                        self.pick_btn.setIcon(style.standardIcon(getattr(style, 'SP_DialogOpenButton')))
                    except Exception:
                        pass
                try:
                    self.clear_btn.setIcon(style.standardIcon(getattr(style, 'SP_TrashIcon')))
                except Exception:
                    try:
                        self.clear_btn.setIcon(style.standardIcon(getattr(style, 'SP_DialogCloseButton')))
                    except Exception:
                        pass
                try:
                    self.clear_cache_btn.setIcon(style.standardIcon(getattr(style, 'SP_TrashIcon')))
                except Exception:
                    pass
        except Exception:
            pass
        picker_lay.addWidget(self.clear_cache_btn)
        picker_row.setLayout(picker_lay)
        layout.addWidget(picker_row)

        # ── Output folder row (guardar resultados) ────────────────────────────
        dst_row = QWidget()
        dst_lay = QHBoxLayout()
        dst_lay.setContentsMargins(0, 0, 0, 0)
        dst_lay.setSpacing(8)
        self.dst_input = QLineEdit()
        self.dst_input.setPlaceholderText("Carpeta de Resultados (opcional)...")
        self.dst_input.setFixedHeight(30)
        dst_btn = QPushButton("Examinar")
        dst_btn.setFixedWidth(100)
        dst_btn.clicked.connect(self._browse_dst)
        try:
            from PyQt6.QtWidgets import QApplication
            app = QApplication.instance()
            if app is not None:
                style = app.style()
                try:
                    dst_btn.setIcon(style.standardIcon(getattr(style, 'SP_DirOpenIcon')))
                except Exception:
                    pass
        except Exception:
            pass
        dst_lay.addWidget(self.dst_input)
        dst_lay.addWidget(dst_btn)
        dst_row.setLayout(dst_lay)
        layout.addWidget(dst_row)

        # ── Output file selector (Guardar como...) ───────────────────────────
        of_row = QWidget()
        of_lay = QHBoxLayout()
        of_lay.setContentsMargins(0, 0, 0, 0)
        of_lay.setSpacing(8)
        self.output_file_input = QLineEdit()
        self.output_file_input.setPlaceholderText("Guardar resultados en (archivo opcional)...")
        self.output_file_input.setFixedHeight(30)
        of_btn = QPushButton("Guardar como...")
        of_btn.setFixedWidth(140)
        of_btn.setFixedHeight(32)
        of_btn.clicked.connect(self._browse_output_file)
        try:
            from PyQt6.QtWidgets import QApplication
            app = QApplication.instance()
            if app is not None:
                style = app.style()
                try:
                    of_btn.setIcon(style.standardIcon(getattr(style, 'SP_DialogSaveButton')))
                except Exception:
                    pass
        except Exception:
            pass
        of_lay.addWidget(self.output_file_input)
        of_lay.addWidget(of_btn)
        of_row.setLayout(of_lay)
        layout.addWidget(of_row)

        # ── Output format & document type selectors ─────────────────────
        opts_row = QWidget()
        opts_lay = QHBoxLayout()
        opts_lay.setContentsMargins(0, 0, 0, 0)
        opts_lay.setSpacing(8)
        from PyQt6.QtWidgets import QComboBox
        self.format_cb = QComboBox()
        self.format_cb.addItems(["XLSX", "CSV", "DOCX", "TXT"])
        self.format_cb.setFixedWidth(140)
        self.format_cb.setToolTip("Formato de salida")
        self.doc_type_cb = QComboBox()
        self.doc_type_cb.addItems(["Factura", "Documento", "Contrato", "Otro"])
        self.doc_type_cb.setFixedWidth(180)
        self.doc_type_cb.setToolTip("Tipo de documento (afecta perfil de extracción)")
        opts_lay.addWidget(QLabel("Formato:"))
        opts_lay.addWidget(self.format_cb)
        opts_lay.addWidget(QLabel("Tipo:"))
        opts_lay.addWidget(self.doc_type_cb)
        # Merge checkbox (rápido acceso desde el StagePanel)
        from PyQt6.QtWidgets import QCheckBox
        self.merge_chk = QCheckBox("Unificar en un solo archivo")
        self.merge_chk.setChecked(True)
        self.merge_chk.setToolTip("Si está activado, exporta un único archivo para todo el lote")
        self.merge_chk.toggled.connect(lambda v: self.merge_toggled.emit(bool(v)))
        opts_lay.addWidget(self.merge_chk)
        opts_lay.addStretch()
        opts_row.setLayout(opts_lay)
        layout.addWidget(opts_row)

        # Estimated cost label (updated by main window when backend/mode/files change)
        self.estimated_cost_lbl = QLabel("Costo estimado lote: $0.00 (0 docs × $0.02)")
        self.estimated_cost_lbl.setStyleSheet("color:#9CA3AF; font-size:12px;")
        layout.addWidget(self.estimated_cost_lbl)

        # ── Lotes y Límites (FASE 7B) ────────────────────────────────────────
        from PyQt6.QtWidgets import QSpinBox, QCheckBox
        batch_row = QWidget()
        batch_lay = QHBoxLayout()
        batch_lay.setContentsMargins(0, 0, 0, 0)
        batch_lay.setSpacing(8)
        self.batch_size_spin = QSpinBox()
        self.batch_size_spin.setRange(1, 2000)
        self.batch_size_spin.setValue(100)
        self.batch_size_spin.setSuffix(" docs/lote")
        self.max_docs_spin = QSpinBox()
        self.max_docs_spin.setRange(0, 100000)
        self.max_docs_spin.setValue(0)
        self.max_docs_spin.setSuffix(" (0 = todos)")
        self.review_after_batch_chk = QCheckBox("⏸ Pausar tras cada lote para revisar")
        batch_lay.addWidget(QLabel("Tamaño lote:"))
        batch_lay.addWidget(self.batch_size_spin)
        batch_lay.addWidget(QLabel("Límite docs:"))
        batch_lay.addWidget(self.max_docs_spin)
        batch_lay.addWidget(self.review_after_batch_chk)
        batch_lay.addStretch()
        batch_row.setLayout(batch_lay)
        layout.addWidget(batch_row)

        # Cargar configuración previa si existe
        try:
            cfg_path = Path.home() / ".ocr_glm_config.json"
            if cfg_path.exists():
                cfg = json.loads(cfg_path.read_text(encoding='utf-8'))
                self.batch_size_spin.setValue(int(cfg.get('batch_size', 100)))
                self.max_docs_spin.setValue(int(cfg.get('max_docs', 0)))
                self.review_after_batch_chk.setChecked(bool(cfg.get('review_after_batch', False)))
        except Exception:
            pass

        # Guardar on change
        def _save_cfg() -> None:
            try:
                cfg_path = Path.home() / ".ocr_glm_config.json"
                cfg = {}
                if cfg_path.exists():
                    try:
                        cfg = json.loads(cfg_path.read_text(encoding='utf-8'))
                    except Exception:
                        cfg = {}
                cfg.update({
                    'batch_size': int(self.batch_size_spin.value()),
                    'max_docs': int(self.max_docs_spin.value()),
                    'review_after_batch': bool(self.review_after_batch_chk.isChecked()),
                    'merge': bool(getattr(self, 'merge_chk', None) and self.merge_chk.isChecked()),
                })
                cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding='utf-8')
            except Exception:
                pass

        self.batch_size_spin.valueChanged.connect(lambda v: _save_cfg())
        self.max_docs_spin.valueChanged.connect(lambda v: _save_cfg())
        self.review_after_batch_chk.toggled.connect(lambda v: _save_cfg())

        # ── Preview scroll area ───────────────────────────────────────────────
        self.preview_area = QScrollArea()
        self.preview_area.setObjectName("previewArea")
        self.preview_area.setWidgetResizable(True)
        self.preview_area.setFixedHeight(110)
        preview_inner = QWidget()
        preview_lay   = QVBoxLayout()
        preview_lay.setContentsMargins(8, 4, 8, 4)
        self.preview_label = QLabel("Previsualizador de archivos")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignTop)
        preview_lay.addWidget(self.preview_label)
        preview_inner.setLayout(preview_lay)
        self.preview_area.setWidget(preview_inner)
        layout.addWidget(self.preview_area)

        # ── QA summary label ──────────────────────────────────────────────────
        self.qa_label = QLabel("QA: —")
        self.qa_label.setObjectName("panelHeader")
        self.qa_label.setFixedHeight(28)
        layout.addWidget(self.qa_label)

        # ── Action Deck ───────────────────────────────────────────────────────
        action_frame = QFrame()
        action_frame.setObjectName("actionDeck")
        action_lay = QHBoxLayout()
        action_lay.setContentsMargins(12, 12, 12, 12)
        action_lay.setSpacing(18)

        self.start_btn = QPushButton("⚡  INICIAR PROCESO")
        self.start_btn.setObjectName("startBtn")
        self.start_btn.setMinimumHeight(50)
        self.start_btn.setEnabled(False)
        self.start_btn.setToolTip("Inicia el procesamiento OCR de todos los archivos en cola (Ctrl+Enter)")

        self.pause_btn = QPushButton("⏸   PAUSAR")
        self.pause_btn.setObjectName("pauseBtn")
        self.pause_btn.setFixedHeight(40)
        self.pause_btn.setEnabled(False)
        self.pause_btn.setFixedWidth(140)
        self.pause_btn.setToolTip("Pausa temporalmente el procesamiento (Ctrl+P)")

        self.stop_btn = QPushButton("⏹   DETENER")
        self.stop_btn.setObjectName("stopBtn")
        self.stop_btn.setFixedHeight(40)
        self.stop_btn.setEnabled(False)
        self.stop_btn.setFixedWidth(140)
        self.stop_btn.setToolTip("Detiene completamente el proceso actual (Esc)")

        action_lay.addWidget(self.start_btn)
        action_lay.addWidget(self.pause_btn)
        action_lay.addWidget(self.stop_btn)
        # Botón de diagnóstico para forzar inicio (útil en pruebas locales)
        self.dbg_start_btn = QPushButton("DBG Iniciar")
        self.dbg_start_btn.setObjectName("dbgStartBtn")
        self.dbg_start_btn.setFixedHeight(40)
        self.dbg_start_btn.setFixedWidth(120)
        self.dbg_start_btn.setToolTip("Botón de depuración: llama a _on_start() directamente")
        self.dbg_start_btn.clicked.connect(self._on_start)
        action_lay.addWidget(self.dbg_start_btn)
        # Botón de depuración: añadir archivo de ejemplo a la cola
        try:
            from pathlib import Path as _P
            sample_path = str(_P(__file__).resolve())
        except Exception:
            sample_path = "sample.pdf"
        self.dbg_add_sample_btn = QPushButton("DBG Añadir muestra")
        self.dbg_add_sample_btn.setObjectName("dbgAddBtn")
        self.dbg_add_sample_btn.setFixedHeight(40)
        self.dbg_add_sample_btn.setFixedWidth(140)
        self.dbg_add_sample_btn.setToolTip("Añade un archivo de ejemplo a la cola para pruebas locales")
        def _dbg_add_sample() -> None:
            try:
                # Emitir la señal como si se hubiera hecho drag&drop
                self.files_dropped.emit([sample_path])
                self._has_files = True
                self.clear_btn.setEnabled(True)
                self.preview_label.setText(f"Archivos en cola: 1\n{sample_path}")
            except Exception:
                pass
        self.dbg_add_sample_btn.clicked.connect(_dbg_add_sample)
        action_lay.addWidget(self.dbg_add_sample_btn)
        action_frame.setLayout(action_lay)
        layout.addWidget(action_frame)

        self.start_btn.clicked.connect(self._on_start)
        self.pause_btn.clicked.connect(self._on_pause)
        self.stop_btn.clicked.connect(self._on_stop)

        self.setLayout(layout)

    # ── Public API ────────────────────────────────────────────────────────────

    def set_api_ready(self, ready: bool) -> None:
        self._api_ready = ready
        self._refresh_start()

    # ── Internal slots ────────────────────────────────────────────────────────

    def _on_drop(self, files: list) -> None:
        self.files_dropped.emit(files)
        self._has_files = True
        self.clear_btn.setEnabled(True)
        self._refresh_start()
        text = "\n".join(files[:10])
        suffix = f"\n… y {len(files)-10} más" if len(files) > 10 else ""
        self.preview_label.setText(f"Archivos en cola: {len(files)}\n{text}{suffix}")
        self.drag.setText(f"✅  {len(files)} archivo(s) en cola  —  arrastra más o usa el botón")
        # Preguntar al usuario si desea transformar PDFs en imágenes para preprocesado
        try:
            from PyQt6.QtWidgets import QMessageBox
            need_transform = False
            # sólo preguntar si hay al menos un PDF en la lista
            for p in files:
                if str(p).lower().endswith('.pdf'):
                    need_transform = True
                    break
            if need_transform:
                res = QMessageBox.question(self, "Transformar a imágenes",
                                           "Se ha detectado(s) PDF(s). ¿Transformar automáticamente a imágenes para preprocesado?",
                                           QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                self.transform_to_images_requested.emit(res == QMessageBox.StandardButton.Yes)
        except Exception:
            pass

    def _refresh_start(self) -> None:
        self.start_btn.setEnabled(self._api_ready and self._has_files)

    def _browse_files(self) -> None:
        """Abre un diálogo para seleccionar archivos manualmente."""
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Seleccionar archivos para procesar",
            "",
            "Documentos (*.pdf *.jpg *.jpeg *.png *.tiff *.tif *.bmp);;Todos los archivos (*)",
        )
        if files:
            self._on_drop(files)

    def _browse_dst(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Seleccionar carpeta de resultados")
        if path:
            try:
                self.dst_input.setText(path)
            except Exception:
                pass

    def _browse_output_file(self) -> None:
        """Permite al usuario seleccionar un archivo destino (Guardar como...)."""
        filters = "Documentos (*.xlsx *.csv *.docx);;Todos los archivos (*)"
        path, _ = QFileDialog.getSaveFileName(self, "Guardar resultados como", "", filters)
        if path:
            try:
                self.output_file_input.setText(path)
                # also emit directory for syncing
                self.output_file_selected.emit(path)
            except Exception:
                pass

    def _clear_queue(self) -> None:
        self._has_files = False
        self.clear_btn.setEnabled(False)
        self.preview_label.setText("Previsualizador de archivos")
        self.drag.setText(
            "⬇   Arrastra carpetas o archivos aquí para procesar\n\n"
            "Formatos soportados: PDF · JPEG · PNG · TIFF"
        )
        self._refresh_start()
        self.queue_cleared.emit()

    def _on_start(self) -> None:
        try:
            print("[StagePanel] _on_start invoked")
        except Exception:
            pass
        self._paused = False
        self.start_btn.setEnabled(False)
        self.pause_btn.setEnabled(True)
        self.stop_btn.setEnabled(True)
        self.pause_btn.setText("⏸   PAUSAR")
        try:
            self.start_requested.emit()
        except Exception:
            try:
                print("[StagePanel] start_requested emit failed")
            except Exception:
                pass

    def _on_pause(self) -> None:
        try:
            print("[StagePanel] _on_pause invoked — paused currently:", self._paused)
        except Exception:
            pass
        if not self._paused:
            self._paused = True
            self.pause_btn.setText("▶   REANUDAR")
            try:
                self.pause_requested.emit()
            except Exception:
                try:
                    print("[StagePanel] pause_requested emit failed")
                except Exception:
                    pass
        else:
            self._paused = False
            self.pause_btn.setText("⏸   PAUSAR")
            try:
                self.resume_requested.emit()
            except Exception:
                try:
                    print("[StagePanel] resume_requested emit failed")
                except Exception:
                    pass

    def on_worker_finished(self) -> None:
        """Called externally when the OcrWorker emits finished(). Reset UI only."""
        self._paused = False
        self.start_btn.setEnabled(self._api_ready and self._has_files)
        self.pause_btn.setEnabled(False)
        self.pause_btn.setText("⏸   PAUSAR")
        self.stop_btn.setEnabled(False)

    def _on_stop(self) -> None:
        try:
            print("[StagePanel] _on_stop invoked")
        except Exception:
            pass
        self._paused = False
        self.start_btn.setEnabled(self._api_ready and self._has_files)
        self.pause_btn.setEnabled(False)
        self.pause_btn.setText("⏸   PAUSAR")
        self.stop_btn.setEnabled(False)
        try:
            self.stop_requested.emit()
        except Exception:
            try:
                print("[StagePanel] stop_requested emit failed")
            except Exception:
                pass

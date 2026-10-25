from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QGroupBox, QLabel, QComboBox, QCheckBox, QPushButton,
    QSpinBox, QDoubleSpinBox, QHBoxLayout
)
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QPlainTextEdit


class AdvancedConfigPanel(QWidget):
    request_pdf_to_img = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        lay = QVBoxLayout()
        # Pre-Procesado Visual
        gb_pp = QGroupBox("Pre-Procesado Visual")
        gbl = QVBoxLayout()
        self.upscale_cb = QComboBox()
        self.upscale_cb.addItems(["Ninguna", "x2", "x3", "x4"])
        gbl.addWidget(self.upscale_cb)
        self.preprocess_chk = QCheckBox("Aplicar limpieza OpenCV (desenruido, contraste)")
        gbl.addWidget(self.preprocess_chk)
        self.light_mode_chk = QCheckBox("Modo ligero (1280px max, menos RAM)")
        gbl.addWidget(self.light_mode_chk)
        # PDF->Imagen moved to Previsualizador toolbar. Keep signal support here.
        # advanced panel no longer shows conversion button to avoid redundancy.
        gb_pp.setLayout(gbl)
        lay.addWidget(gb_pp)

        # Control de Lotes
        gb_batch = QGroupBox("Procesamiento por Lotes")
        bgl = QVBoxLayout()
        self.batch_size_spin = QSpinBox()
        self.batch_size_spin.setRange(10, 500)
        self.batch_size_spin.setValue(100)
        self.batch_size_spin.setSuffix(" docs/lote")
        bgl.addWidget(self.batch_size_spin)
        self.max_docs_spin = QSpinBox()
        self.max_docs_spin.setRange(0, 100000)
        self.max_docs_spin.setValue(0)
        self.max_docs_spin.setSuffix(" (0 = todos)")
        bgl.addWidget(self.max_docs_spin)
        self.pause_after_batch_chk = QCheckBox("⏸ Pausar tras cada lote para revisar")
        bgl.addWidget(self.pause_after_batch_chk)
        bgl.addWidget(QLabel("Ideal para lotes grandes: permite revisión intermedia sin perder progreso"))
        gb_batch.setLayout(bgl)
        lay.addWidget(gb_batch)

        # Herramientas de Revisión
        gb_rev = QGroupBox("Validación Visual")
        rgl = QVBoxLayout()
        self.enable_review_panel_chk = QCheckBox("Activar panel de comparación (Imagen vs Datos)")
        rgl.addWidget(self.enable_review_panel_chk)
        self.confidence_threshold_spin = QDoubleSpinBox()
        self.confidence_threshold_spin.setRange(0.0, 1.0)
        self.confidence_threshold_spin.setSingleStep(0.05)
        self.confidence_threshold_spin.setValue(0.80)
        rgl.addWidget(self.confidence_threshold_spin)
        rgl.addWidget(QLabel("Marcar documentos con confianza < umbral para revisión manual"))
        gb_rev.setLayout(rgl)
        lay.addWidget(gb_rev)

        # Prompts: OCR y Post-OCR (editable)
        gb_prompts = QGroupBox("Prompts / Plantillas")
        pgl2 = QVBoxLayout()
        pgl2.setContentsMargins(8, 8, 8, 8)
        pgl2.setSpacing(8)
        pgl2.addWidget(QLabel("Prompt para OCR (pre-procesado / instrucciones):"))
        self.ocr_prompt_edit = QPlainTextEdit()
        self.ocr_prompt_edit.setPlaceholderText("Instrucciones para el motor OCR, p. ej. 'Extraer campos: fecha, total, NIT' ")
        self.ocr_prompt_edit.setFixedHeight(80)
        pgl2.addWidget(self.ocr_prompt_edit)

        pgl2.addWidget(QLabel("Prompt para Post-OCR / Razonamiento (IA):"))
        self.postocr_prompt_edit = QPlainTextEdit()
        self.postocr_prompt_edit.setPlaceholderText("Instrucciones para la IA de post‑procesado, p. ej. 'Normalizar monedas, corregir errores OCR' ")
        self.postocr_prompt_edit.setFixedHeight(120)
        pgl2.addWidget(self.postocr_prompt_edit)

        gb_prompts.setLayout(pgl2)
        lay.addWidget(gb_prompts)

        lay.addStretch(1)
        self.setLayout(lay)

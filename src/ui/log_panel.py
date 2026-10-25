from __future__ import annotations

import os

from PyQt6.QtWidgets import (
    QFrame,
    QVBoxLayout,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QProgressBar,
    QHeaderView,
)
from PyQt6.QtGui import QColor
from PyQt6.QtCore import pyqtSignal, Qt

_STATUS_COLOR: dict[str, QColor] = {
    "Procesado": QColor(16, 185, 129, 30),
    "Error":     QColor(239, 68, 68, 30),
    "En cola":   QColor(0, 0, 0, 0),
}


class LogPanel(QFrame):
    qa_summary_updated = pyqtSignal(float)
    row_double_clicked = pyqtSignal(str, str)  # emite (nombre de archivo, file_path)
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("logPanel")

        layout = QVBoxLayout()
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)

        hdr = QLabel("LOG DE DOCUMENTOS PROCESADOS")
        hdr.setObjectName("panelHeader")
        layout.addWidget(hdr)

        # ── Document table ────────────────────────────────────────────────────
        # Columns: ID, Filename, Pages, Confidence, QA(%), Status
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["ID", "Nombre de Archivo", "Páginas", "Confianza (%)", "QA (%)", "Estado"]
        )
        self.table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.cellDoubleClicked.connect(self._on_row_double_click)
        layout.addWidget(self.table)

        # ── Etiqueta de métricas de confianza (actualizada por OcrWorker) ─────────────
        self._metrics_lbl = QLabel("Métricas de confianza: sin datos aún")
        self._metrics_lbl.setObjectName("kpiLabel")
        self._metrics_lbl.setWordWrap(True)
        self._metrics_lbl.setToolTip(
            "Promedio de confianza OCR acumulado en ~/.ocr_confidence_metrics.json"
        )
        layout.addWidget(self._metrics_lbl)

        # Nota: La barra de progreso no se muestra según la nueva especificación.
        # Mantenemos el objeto `self.progress` para compatibilidad de API,
        # pero no lo añadimos al layout visual.
        self.progress = QProgressBar()
        self.progress.setFixedHeight(24)
        self.progress.setMinimum(0)
        self.progress.setMaximum(100)
        self.progress.setValue(0)
        self.progress.setFormat("En espera…")

        self.setLayout(layout)
        self._count = 0

    # ── Public API ─────────────────────────────────────────────────────────────

    def clear_table(self) -> None:
        """Vacía la tabla y reinicia contadores."""
        self.table.setRowCount(0)
        self._count = 0
        self.reset_progress()

    def add_document(self, path: str) -> None:
        self._count += 1
        row = self.table.rowCount()
        self.table.insertRow(row)
        name = os.path.basename(path) or path
        self.table.setItem(row, 0, QTableWidgetItem(str(self._count)))
        name_item = QTableWidgetItem(name)
        # almacenar la ruta completa en UserRole para emisiones posteriores
        name_item.setData(Qt.ItemDataRole.UserRole, path)
        self.table.setItem(row, 1, name_item)
        self.table.setItem(row, 2, QTableWidgetItem("\u2014"))
        self.table.setItem(row, 3, QTableWidgetItem("\u2014"))
        self.table.setItem(row, 4, QTableWidgetItem("\u2014"))
        estado_item = QTableWidgetItem("En cola")
        estado_item.setForeground(QColor(75, 85, 99))
        self.table.setItem(row, 5, estado_item)
        self._color_row(row, "En cola")

    def update_document_row(self, row_index: int, status: str, confidence: float) -> None:
        """Called by OcrWorker.document_done signal."""
        if row_index < 0 or row_index >= self.table.rowCount():
            return
        conf_pct = f"{round(confidence * 100, 1)}"
        self.table.setItem(row_index, 3, QTableWidgetItem(conf_pct))
        # leave QA column (4) untouched here; it will be set by update_document_qa
        status_item = QTableWidgetItem(status)
        if status == "Procesado":
            status_item.setForeground(QColor(16, 185, 129))
        elif status == "Error":
            status_item.setForeground(QColor(239, 68, 68))
        else:
            status_item.setForeground(QColor(107, 114, 128))
        self.table.setItem(row_index, 5, status_item)
        self._color_row(row_index, status)
        self.table.scrollToItem(self.table.item(row_index, 0))

    def update_document_qa(self, row_index: int, accuracy_pct: float, passed: bool) -> None:
        """Setea la columna QA para la fila dada.

        `accuracy_pct` es porcentaje 0-100. `passed` indica si pasó QA.
        """
        if row_index < 0 or row_index >= self.table.rowCount():
            return
        qa_text = f"{accuracy_pct:.1f}%"
        item = QTableWidgetItem(qa_text)
        self.table.setItem(row_index, 4, item)
        # marcar visual si falló QA
        if not passed:
            # resaltar QA en rojo claro
            item.setBackground(QColor(239, 68, 68, 60))
        else:
            item.setBackground(QColor(16, 185, 129, 40))
        # Emitir resumen de QA (media aritmética de filas con valor numérico)
        try:
            total = 0.0
            count = 0
            for r in range(self.table.rowCount()):
                qa_item = self.table.item(r, 4)
                if qa_item:
                    txt = qa_item.text().strip()
                    if txt and txt.endswith('%'):
                        try:
                            val = float(txt.rstrip('%'))
                            total += val
                            count += 1
                        except Exception:
                            continue
            avg = (total / count) if count > 0 else 0.0
            self.qa_summary_updated.emit(avg)
        except Exception:
            try:
                self.qa_summary_updated.emit(0.0)
            except Exception:
                pass

    def set_progress(self, value: int, maximum: int) -> None:
        self.progress.setFormat("Procesando: %v / %m documentos")
        self.progress.setMaximum(maximum)
        self.progress.setValue(value)

    def reset_progress(self, total: int = 0) -> None:
        if total > 0:
            # Barra determinista desde el inicio — sin animación errante
            self.progress.setMaximum(total)
            self.progress.setValue(0)
            self.progress.setFormat("Procesando: 0 / %m documentos")
        else:
            self.progress.setMaximum(100)
            self.progress.setValue(0)
            self.progress.setFormat("En espera…")

    def on_batch_finished(self) -> None:
        """llamado cuando el worker emite finished() (lote completado con éxito)."""
        total = self.progress.maximum()
        self.progress.setValue(total)
        self.progress.setFormat(f"Completado: {total} documentos")

    def stop_processing(self) -> None:
        """Called when the worker is stopped — rows remain in their current state."""
        self.progress.setFormat("Detenido")

    # ── Helpers ─────────────────────────────────────────────────────────────────

    def _color_row(self, row: int, status: str) -> None:
        color = _STATUS_COLOR.get(status, QColor(0, 0, 0, 0))
        for col in range(self.table.columnCount()):
            item = self.table.item(row, col)
            if item:
                item.setBackground(color)

    def show_metric(self, text: str) -> None:
        """Slot conectado a OcrWorker.metrics_updated para mostrar métricas en tiempo real."""
        try:
            self._metrics_lbl.setText(text)
        except Exception:
            pass

    def _on_row_double_click(self, row: int, col: int) -> None:
        """Emite el nombre de archivo al hacer doble clic en cualquier celda de una fila."""
        item = self.table.item(row, 1)  # columna 1 = "Nombre de Archivo"
        if item:
            file_path = item.data(Qt.ItemDataRole.UserRole) or ""
            self.row_double_clicked.emit(item.text(), file_path)

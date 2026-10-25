"""Panel de Excepciones OCR — muestra solo documentos problemáticos.

Condiciones de "excepción":
  • Confianza < umbral configurable (por defecto 80%)
  • Estado == "Error"
  • Reconciliación contable fallida (indicador "flagged")

Acciones disponibles por documento:
  • Aprobar   — marca como revisado manualmente (no desaparece, cambia ícono)
  • Re-procesar — emite señal ``reprocess_requested(filenames)`` para el worker
  • Exportar informe — genera un JSON/CSV con todas las excepciones actuales

La clase se conecta desde main_window a las mismas señales de OcrWorker
que LogPanel, sin reemplazarlo ni duplicar lógica de tabla.

Integración rápida
------------------
    from src.ui.exception_dashboard import ExceptionDashboard
    exc_dash = ExceptionDashboard()
    central_tabs.addTab(exc_dash, "⚠ Excepciones")

    # Conectar señales del worker:
    w.document_done.connect(exc_dash.on_document_done)
    w.qa_report.connect(exc_dash.on_qa_report)

    # Escuchar la señal de reprocesado:
    exc_dash.reprocess_requested.connect(my_reprocess_handler)
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

# ── Constantes ────────────────────────────────────────────────────────────────

_COL_IDX       = 0
_COL_FILENAME  = 1
_COL_CONF      = 2
_COL_STATUS    = 3
_COL_REASON    = 4
_COL_REVIEWED  = 5
_NCOLS         = 6

_REASON_LOW_CONF         = "Confianza baja"
_REASON_ERROR            = "Error OCR"
_REASON_ACCOUNTING       = "Fallo contable"
_REASON_MULTI            = "Múltiples"

_COLOR_ERROR    = QColor(239, 68,  68,  40)
_COLOR_WARNING  = QColor(251, 191, 36,  40)
_COLOR_REVIEWED = QColor(16,  185, 129, 30)


class ExceptionDashboard(QFrame):
    """Pestaña que lista solo documentos con algún indicador de excepción."""

    # Emite lista de nombres de archivo para procesarlos de nuevo
    reprocess_requested = pyqtSignal(list)

    def __init__(self, conf_threshold: float = 0.80, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("exceptionDashboard")
        self._threshold = conf_threshold

        # Datos internos: filename → {"row": int, "reasons": set, "reviewed": bool}
        self._registry: dict[str, dict] = {}
        # Mapa de resultados completos para exportación
        self._results: dict[str, dict] = {}

        self._build_ui()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout()
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        # Título
        hdr = QLabel("⚠  PANEL DE EXCEPCIONES")
        hdr.setObjectName("panelHeader")
        root.addWidget(hdr)

        # Fila de controles
        ctrl = QHBoxLayout()
        ctrl.setSpacing(8)

        lbl_thresh = QLabel("Umbral confianza (%):")
        self._thresh_spin = QSpinBox()
        self._thresh_spin.setRange(0, 100)
        self._thresh_spin.setValue(int(self._threshold * 100))
        self._thresh_spin.setFixedWidth(64)
        self._thresh_spin.setToolTip(
            "Documentos con confianza por debajo de este umbral se marcarán como excepción."
        )
        self._thresh_spin.valueChanged.connect(self._on_threshold_changed)

        self._count_lbl = QLabel("0 excepciones")
        self._count_lbl.setObjectName("kpiLabel")

        ctrl.addWidget(lbl_thresh)
        ctrl.addWidget(self._thresh_spin)
        ctrl.addSpacing(16)
        ctrl.addWidget(self._count_lbl)
        ctrl.addStretch()

        self._btn_approve    = QPushButton("✔ Aprobar seleccionados")
        self._btn_reprocess  = QPushButton("🔄 Re-procesar seleccionados")
        self._btn_export     = QPushButton("📤 Exportar informe")
        self._btn_clear      = QPushButton("🗑 Limpiar revisados")

        for btn in (self._btn_approve, self._btn_reprocess, self._btn_export, self._btn_clear):
            btn.setFixedHeight(30)
            ctrl.addWidget(btn)

        root.addLayout(ctrl)

        # Tabla
        self._table = QTableWidget(0, _NCOLS)
        self._table.setHorizontalHeaderLabels(
            ["#", "Archivo", "Confianza (%)", "Estado", "Motivo", "Revisado"]
        )
        hh = self._table.horizontalHeader()
        hh.setSectionResizeMode(_COL_FILENAME, QHeaderView.ResizeMode.Stretch)
        for col in (_COL_IDX, _COL_CONF, _COL_STATUS, _COL_REASON, _COL_REVIEWED):
            hh.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        self._table.setShowGrid(False)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        root.addWidget(self._table)

        self.setLayout(root)

        # Conexiones internas
        self._btn_approve.clicked.connect(self._approve_selected)
        self._btn_reprocess.clicked.connect(self._reprocess_selected)
        self._btn_export.clicked.connect(self._export_report)
        self._btn_clear.clicked.connect(self._clear_reviewed)

    # ── Slots públicos (conectar desde main_window) ───────────────────────────

    def on_document_done(self, row_index: int, status: str, confidence: float) -> None:
        """Conectar a ``OcrWorker.document_done``."""
        # row_index es el índice en _files; necesitamos el filename
        # Se resuelve cuando se llama a ``register_filename`` antes de arrancar
        fn = self._index_to_filename.get(row_index)
        if fn is None:
            return
        reasons: set[str] = set()
        if status == "Error":
            reasons.add(_REASON_ERROR)
        if confidence < self._threshold:
            reasons.add(_REASON_LOW_CONF)
        if reasons:
            self._upsert_row(fn, confidence, status, reasons,
                             extra={"confidence": confidence, "status": status})

    def on_qa_report(self, report_key: str, stats: dict) -> None:
        """Conectar a ``OcrWorker.qa_report`` para capturar fallos contables."""
        if report_key != "accounting":
            return
        issues = stats.get("issues") or []
        for issue in issues:
            for doc_id in (issue.get("docs") or []):
                fn = self._docid_to_filename.get(doc_id, doc_id)
                reasons = {_REASON_ACCOUNTING}
                self._upsert_row(
                    fn,
                    self._results.get(fn, {}).get("confidence", 0.0),
                    self._results.get(fn, {}).get("status", ""),
                    reasons,
                    extra=issue,
                )

    def register_filenames(self, files: list[str]) -> None:
        """Llamar antes de arrancar el worker con la lista de archivos."""
        self._index_to_filename: dict[int, str] = {
            i: os.path.basename(p) for i, p in enumerate(files)
        }
        self._docid_to_filename: dict[str, str] = {
            os.path.basename(p): os.path.basename(p) for p in files
        }

    def clear_batch(self) -> None:
        """Limpia el panel al inicio de un nuevo lote."""
        self._table.setRowCount(0)
        self._registry.clear()
        self._results.clear()
        self._index_to_filename = {}
        self._docid_to_filename = {}
        self._update_count_label()

    # ── Gestión de filas ──────────────────────────────────────────────────────

    def _upsert_row(
        self,
        filename: str,
        confidence: float,
        status: str,
        reasons: set[str],
        extra: dict | None = None,
    ) -> None:
        """Inserta o actualiza una fila para el documento dado."""
        self._results[filename] = {
            "filename":   filename,
            "confidence": confidence,
            "status":     status,
            **(extra or {}),
        }
        if filename in self._registry:
            info = self._registry[filename]
            info["reasons"] |= reasons
            row = info["row"]
            self._refresh_row(row, filename, confidence, status, info["reasons"], info["reviewed"])
        else:
            row = self._table.rowCount()
            self._table.insertRow(row)
            self._registry[filename] = {"row": row, "reasons": reasons, "reviewed": False}
            self._refresh_row(row, filename, confidence, status, reasons, False)
        self._update_count_label()

    def _refresh_row(
        self,
        row: int,
        filename: str,
        confidence: float,
        status: str,
        reasons: set[str],
        reviewed: bool,
    ) -> None:
        conf_pct = f"{confidence * 100:.1f}"
        reason_str = _REASON_MULTI if len(reasons) > 1 else (next(iter(reasons)) if reasons else "")

        items = [
            QTableWidgetItem(str(row + 1)),
            QTableWidgetItem(filename),
            QTableWidgetItem(conf_pct),
            QTableWidgetItem(status),
            QTableWidgetItem(reason_str),
            QTableWidgetItem("✔ Revisado" if reviewed else "—"),
        ]
        for col, item in enumerate(items):
            item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            self._table.setItem(row, col, item)

        # Color de fila
        if reviewed:
            bg = _COLOR_REVIEWED
        elif _REASON_ERROR in reasons or _REASON_ACCOUNTING in reasons:
            bg = _COLOR_ERROR
        else:
            bg = _COLOR_WARNING

        for col in range(_NCOLS):
            it = self._table.item(row, col)
            if it:
                it.setBackground(bg)

    # ── Acciones de botones ───────────────────────────────────────────────────

    def _approve_selected(self) -> None:
        rows = {idx.row() for idx in self._table.selectedIndexes()}
        if not rows:
            QMessageBox.information(self, "Sin selección", "Selecciona uno o más documentos primero.")
            return
        for fn, info in self._registry.items():
            if info["row"] in rows:
                info["reviewed"] = True
                r = info["row"]
                res = self._results.get(fn, {})
                self._refresh_row(r, fn, res.get("confidence", 0.0),
                                   res.get("status", ""), info["reasons"], True)

    def _reprocess_selected(self) -> None:
        rows = {idx.row() for idx in self._table.selectedIndexes()}
        if not rows:
            QMessageBox.information(self, "Sin selección", "Selecciona uno o más documentos primero.")
            return
        fnames = [fn for fn, info in self._registry.items() if info["row"] in rows]
        if fnames:
            self.reprocess_requested.emit(fnames)

    def _export_report(self) -> None:
        if not self._registry:
            QMessageBox.information(self, "Sin excepciones", "No hay excepciones que exportar.")
            return
        default_name = f"excepciones_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        path, _ = QFileDialog.getSaveFileName(
            self, "Guardar informe de excepciones",
            str(Path.home() / default_name),
            "JSON (*.json);;All files (*)",
        )
        if not path:
            return
        report = {
            "generated_at": datetime.now().isoformat(),
            "threshold":    self._threshold,
            "exceptions": [
                {
                    "filename":  fn,
                    "reasons":   sorted(info["reasons"]),
                    "reviewed":  info["reviewed"],
                    **{k: v for k, v in self._results.get(fn, {}).items()
                       if k not in ("filename",)},
                }
                for fn, info in self._registry.items()
            ],
        }
        try:
            Path(path).write_text(
                json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            QMessageBox.information(self, "Exportado", f"Informe guardado en:\n{path}")
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"No se pudo guardar el informe:\n{exc}")

    def _clear_reviewed(self) -> None:
        to_remove = [fn for fn, info in self._registry.items() if info["reviewed"]]
        if not to_remove:
            return
        for fn in to_remove:
            row = self._registry[fn]["row"]
            self._table.removeRow(row)
            del self._registry[fn]
            self._results.pop(fn, None)
        # Reindexar filas restantes
        for fn, info in self._registry.items():
            old_row = info["row"]
            removed_above = sum(
                1 for fn2, inf2 in self._registry.items()
                if fn2 != fn
                and inf2["row"] < old_row
                and fn2 in to_remove
            )
            info["row"] = old_row - removed_above
        self._update_count_label()

    def _on_threshold_changed(self, value: int) -> None:
        self._threshold = value / 100.0

    def _update_count_label(self) -> None:
        n = len(self._registry)
        self._count_lbl.setText(f"{n} excepción{'es' if n != 1 else ''}")

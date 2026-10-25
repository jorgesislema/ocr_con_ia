from __future__ import annotations

import os
from typing import Dict, Any

from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QVBoxLayout,
    QGraphicsView,
    QGraphicsScene,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QSizePolicy,
    QWidget,
    QLineEdit,
    QSplitter,
    QSpacerItem,
)
from PyQt6.QtGui import QPixmap, QWheelEvent, QBrush, QPixmap as QPx, QColor
from PyQt6.QtCore import pyqtSignal, Qt, QUrl
from PyQt6.QtGui import QDesktopServices


class _Viewer(QGraphicsView):
    """QGraphicsView con zoom por rueda y pan con Ctrl+rueda."""

    def __init__(self, scene: QGraphicsScene | None = None, parent: QWidget | None = None):
        super().__init__(scene or QGraphicsScene(), parent)
        self.setRenderHints(self.renderHints())
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)

    def wheelEvent(self, event: QWheelEvent) -> None:
        delta = event.angleDelta().y()
        mods = event.modifiers()
        if mods & Qt.KeyboardModifier.ControlModifier:
            # Ctrl + rueda -> paneo vertical
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta)
            return
        # zoom incremental
        factor = 1.2 if delta > 0 else (1.0 / 1.2)
        self.scale(factor, factor)


class ReviewPanel(QFrame):
    approved = pyqtSignal(dict)  # datos corregidos
    reprocess = pyqtSignal(str)  # file_path
    open_external = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("reviewPanel")
        self._current_path: str | None = None

        self._scene = QGraphicsScene()
        self._viewer = _Viewer(self._scene, self)
        # pequeño patrón ajedrezado como fondo
        tile = QPx(8, 8)
        tile.fill(QColor(0, 0, 0, 0))
        p = QPx(8, 8)
        p.fill(QColor(15, 23, 42))
        brush = QBrush(p)
        self._viewer.setBackgroundBrush(brush)

        # Right side: data area
        self._table = QTableWidget(0, 2)
        self._table.setHorizontalHeaderLabels(["Campo", "Valor"])
        self._table.horizontalHeader().setStretchLastSection(True)
        self._text = QTextEdit()
        self._text.setReadOnly(True)

        # Layout
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        left_widget = QWidget()
        left_l = QVBoxLayout(left_widget)
        left_l.setContentsMargins(0, 0, 0, 0)
        ctrl_l = QHBoxLayout()
        self._zoom_out = QPushButton("-")
        self._zoom_pct = QPushButton("100%")
        self._zoom_in = QPushButton("+")
        self._fit = QPushButton("Ajustar")
        for b in (self._zoom_out, self._zoom_pct, self._zoom_in, self._fit):
            b.setFixedHeight(28)
            b.setFixedWidth(64)
            ctrl_l.addWidget(b)
        ctrl_l.addSpacerItem(QSpacerItem(10, 10))
        left_l.addLayout(ctrl_l)
        left_l.addWidget(self._viewer)
        splitter.addWidget(left_widget)

        right_widget = QWidget()
        right_l = QVBoxLayout(right_widget)
        right_l.setContentsMargins(0, 0, 0, 0)
        right_l.addWidget(self._table)
        right_l.addWidget(self._text)
        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 1)

        root.addWidget(splitter)

        # Bottom actions
        actions = QHBoxLayout()
        self._open_btn = QPushButton("Abrir Original en Visor Externo")
        self._reproc_btn = QPushButton("❌ Reprocesar")
        self._approve_btn = QPushButton("✅ Aprobar y Exportar")
        self._approve_btn.setObjectName("primaryAction")
        actions.addWidget(self._open_btn)
        actions.addWidget(self._reproc_btn)
        actions.addWidget(self._approve_btn)
        root.addLayout(actions)

        # conexiones
        self._zoom_in.clicked.connect(lambda: self._viewer.scale(1.2, 1.2))
        self._zoom_out.clicked.connect(lambda: self._viewer.scale(1 / 1.2, 1 / 1.2))
        self._zoom_pct.clicked.connect(lambda: self._viewer.resetTransform())
        self._fit.clicked.connect(self._fit_view)
        self._open_btn.clicked.connect(self._open_external)
        self._reproc_btn.clicked.connect(self._reprocess)
        self._approve_btn.clicked.connect(self._approve)

        # estado inicial
        self._table.hide()

    def _fit_view(self) -> None:
        rect = self._scene.itemsBoundingRect()
        if rect.isNull():
            return
        self._viewer.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)

    def _open_external(self) -> None:
        if not self._current_path:
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(self._current_path))
        self.open_external.emit(self._current_path)

    def _reprocess(self) -> None:
        if not self._current_path:
            return
        self.reprocess.emit(self._current_path)

    def _approve(self) -> None:
        corrected: Dict[str, Any] = {}
        if self._table.isVisible():
            for r in range(self._table.rowCount()):
                key_it = self._table.item(r, 0)
                if not key_it:
                    continue
                key = key_it.text()
                widget = self._table.cellWidget(r, 1)
                if isinstance(widget, QLineEdit):
                    val = widget.text()
                else:
                    it = self._table.item(r, 1)
                    val = it.text() if it else ""
                corrected[key] = val
        self.approved.emit(corrected)

    def load_document(self, file_path: str, data: dict | str | None, confidence_map: dict | None = None) -> None:
        """Carga imagen/PDF y muestra datos.

        data: dict para JSON (facturas) o str para texto libre.
        confidence_map: mapping campo->float(0..1).
        """
        self._current_path = file_path
        # cargar imagen
        if file_path and os.path.exists(file_path):
            pix = QPixmap(file_path)
            if not pix.isNull():
                self._scene.clear()
                self._scene.addPixmap(pix)
                self._fit_view()
            else:
                self._scene.clear()
                lbl = QLabel(f"No se puede previsualizar: {os.path.basename(file_path)}")
                self._scene.addWidget(lbl)
        else:
            self._scene.clear()
            lbl = QLabel("Archivo no encontrado")
            lbl.setStyleSheet("color:#FCA5A5")
            self._scene.addWidget(lbl)

        # poblar datos
        if data is None:
            self._table.hide()
            self._text.setPlainText("")
            self._text.show()
            return
        if isinstance(data, str):
            self._table.hide()
            self._text.setPlainText(data)
            self._text.show()
            return

        # dict
        self._text.hide()
        self._table.setRowCount(0)
        for i, (k, v) in enumerate(data.items()):
            self._table.insertRow(i)
            self._table.setItem(i, 0, QTableWidgetItem(str(k)))
            le = QLineEdit(str(v))
            # semáforo visual
            conf = None
            if confidence_map:
                conf = confidence_map.get(k)
            if conf is not None:
                if conf >= 0.9:
                    le.setStyleSheet("border: 1px solid #10B981; border-radius:6px; background: rgba(16,185,129,0.03);")
                elif conf < 0.75:
                    le.setStyleSheet("border: 1px solid #EF4444; border-radius:6px; background: rgba(239,68,68,0.03);")
            else:
                le.setStyleSheet("border-radius:6px;")
            self._table.setCellWidget(i, 1, le)
        self._table.show()

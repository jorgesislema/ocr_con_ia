"""Pestaña GUI para Integración ERP: subir maestro de proveedores y opciones.
"""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QHBoxLayout,
    QFileDialog,
    QLineEdit,
)


class ErpPanel(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        root = QVBoxLayout()
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        hdr = QLabel("Integración ERP — Maestro de Proveedores")
        hdr.setObjectName("cardTitle")
        root.addWidget(hdr)

        note = QLabel("Carga el CSV del maestro de proveedores para mapear códigos ERP/GL.")
        note.setWordWrap(True)
        root.addWidget(note)

        row = QHBoxLayout()
        self.path_input = QLineEdit()
        self.path_input.setPlaceholderText("Selecciona vendor_master.csv…")
        browse = QPushButton("Examinar")
        browse.clicked.connect(self.browse)
        row.addWidget(self.path_input)
        row.addWidget(browse)
        root.addLayout(row)

        self.setLayout(root)

    def browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Seleccionar maestro de proveedores", "", "CSV Files (*.csv);;All Files (*)")
        if path:
            self.path_input.setText(path)

    @property
    def vendor_master_path(self) -> str:
        return str(self.path_input.text().strip() or "")

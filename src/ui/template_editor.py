from __future__ import annotations

from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QTextEdit,
    QPushButton,
    QFileDialog,
    QMessageBox,
)
from PyQt6.QtCore import Qt


class TemplateEditor(QDialog):
    """Diálogo simple para editar plantillas .tpl dentro de la carpeta `prompts/`.

    Funcionalidades mínimas:
    - Abrir plantilla seleccionada desde `prompts/`
    - Editar texto
    - Guardar cambios (overwrite)
    - Guardar como (crear nueva plantilla)
    """

    def __init__(self, initial_template: Optional[str] = None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Editor de Plantilla")
        self.resize(980, 720)
        # Abrir maximizada para evitar texto pequeño y ventanas amontonadas
        try:
            self.setWindowState(self.windowState() | Qt.WindowState.WindowMaximized)
        except Exception:
            pass
        self._prompts_dir = Path(__file__).resolve().parents[2] / "prompts"
        self._current_path: Optional[Path] = None

        root = QVBoxLayout()

        # header: filename + checksum
        self._file_label = QLabel("")
        self._checksum_label = QLabel("")
        root.addWidget(self._file_label)
        root.addWidget(self._checksum_label)

        # text area
        self._editor = QTextEdit()
        root.addWidget(self._editor)

        # footer buttons
        btn_row = QHBoxLayout()
        self._btn_open = QPushButton("Abrir...")
        self._btn_save = QPushButton("Guardar")
        self._btn_save_as = QPushButton("Guardar como...")
        self._btn_close = QPushButton("Cerrar")

        btn_row.addWidget(self._btn_open)
        btn_row.addWidget(self._btn_save)
        btn_row.addWidget(self._btn_save_as)
        btn_row.addStretch()
        btn_row.addWidget(self._btn_close)

        root.addLayout(btn_row)

        self.setLayout(root)

        self._btn_open.clicked.connect(self._on_open)
        self._btn_save.clicked.connect(self._on_save)
        self._btn_save_as.clicked.connect(self._on_save_as)
        self._btn_close.clicked.connect(self.accept)

        # load initial template if provided
        if initial_template:
            self.open_template(initial_template)

    def _on_open(self) -> None:
        p, _ = QFileDialog.getOpenFileName(self, "Abrir plantilla", str(self._prompts_dir), "Plantillas (*.tpl);;Todos (*.*)")
        if p:
            rel = Path(p)
            try:
                rel = rel.relative_to(self._prompts_dir)
            except Exception:
                # allow opening arbitrary files but warn
                pass
            self.open_template(str(rel.name))

    def open_template(self, name: str) -> None:
        try:
            p = (self._prompts_dir / name).resolve()
            if not p.exists():
                QMessageBox.warning(self, "No encontrado", f"Plantilla no encontrada: {name}")
                return
            text = p.read_text(encoding="utf-8")
            self._current_path = p
            self._file_label.setText(f"Plantilla: {p.name}")
            # checksum
            try:
                import hashlib

                ch = hashlib.sha256(text.encode("utf-8")).hexdigest()
                self._checksum_label.setText(f"Checksum: {ch}")
            except Exception:
                self._checksum_label.setText("")
            self._editor.setPlainText(text)
        except Exception as exc:
            QMessageBox.critical(self, "Error al abrir", str(exc))

    def _on_save(self) -> None:
        if not self._current_path:
            return self._on_save_as()
        try:
            self._current_path.write_text(self._editor.toPlainText(), encoding="utf-8")
            # update checksum label
            try:
                import hashlib

                ch = hashlib.sha256(self._editor.toPlainText().encode("utf-8")).hexdigest()
                self._checksum_label.setText(f"Checksum: {ch}")
            except Exception:
                pass
            QMessageBox.information(self, "Guardado", f"Plantilla guardada: {self._current_path.name}")
        except Exception as exc:
            QMessageBox.critical(self, "Error al guardar", str(exc))

    def _on_save_as(self) -> None:
        p, _ = QFileDialog.getSaveFileName(self, "Guardar plantilla como", str(self._prompts_dir), "Plantillas (*.tpl)")
        if not p:
            return
        try:
            dest = Path(p)
            if not dest.parent.exists():
                dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(self._editor.toPlainText(), encoding="utf-8")
            self._current_path = dest
            self._file_label.setText(f"Plantilla: {dest.name}")
            try:
                import hashlib

                ch = hashlib.sha256(self._editor.toPlainText().encode("utf-8")).hexdigest()
                self._checksum_label.setText(f"Checksum: {ch}")
            except Exception:
                pass
            QMessageBox.information(self, "Guardado", f"Plantilla guardada: {dest.name}")
        except Exception as exc:
            QMessageBox.critical(self, "Error al guardar", str(exc))

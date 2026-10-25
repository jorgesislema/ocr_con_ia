from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QComboBox,
    QTextEdit,
    QPushButton,
)


class PromptEditorDialog(QDialog):
    def __init__(self, parent=None, prompt_name: str | None = None, content: str = ""):
        super().__init__(parent)
        self.prompt_name = prompt_name
        self.content = content
        self._setup_ui()

    def _setup_ui(self):
        title = "✏️ Editor de Prompts" if self.prompt_name else "➕ Nuevo Prompt"
        self.setWindowTitle(title)
        self.setMinimumSize(700, 600)

        layout = QVBoxLayout(self)

        # Nombre
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("Nombre:"))
        self.name_input = QLineEdit()
        if self.prompt_name:
            self.name_input.setText(self.prompt_name)
        name_layout.addWidget(self.name_input)
        layout.addLayout(name_layout)

        # Categoría
        cat_layout = QHBoxLayout()
        cat_layout.addWidget(QLabel("Categoría:"))
        self.category_cb = QComboBox()
        self.category_cb.addItems(["custom", "invoice", "contract", "receipt", "handwritten"]) 
        cat_layout.addWidget(self.category_cb)
        layout.addLayout(cat_layout)

        # Contenido
        layout.addWidget(QLabel("Contenido del prompt:"))
        self.content_editor = QTextEdit()
        self.content_editor.setPlainText(self.content)
        self.content_editor.setPlaceholderText(
            "Escribe tu prompt aquí. Ejemplo:\n\n"
            "Eres un experto en extracción de datos de facturas.\n"
            "Analiza la imagen y extrae SOLO un JSON válido:\n"
            "{\n"
            '  "numero_factura": "...",\n'
            '  "fecha": "YYYY-MM-DD",\n'
            '  "total": 0.00\n'
            "}\n"
            "Responde SOLO con JSON, sin texto adicional."
        )
        layout.addWidget(self.content_editor)

        # Botones
        btn_layout = QHBoxLayout()
        btn_save = QPushButton("💾 Guardar")
        btn_cancel = QPushButton("❌ Cancelar")
        btn_save.clicked.connect(self.accept)
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_save)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)

    def values(self) -> tuple[str, str, str]:
        name = self.name_input.text().strip()
        category = self.category_cb.currentText().strip()
        content = self.content_editor.toPlainText()
        return name, category, content


__all__ = ["PromptEditorDialog"]

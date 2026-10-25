from __future__ import annotations

from PyQt6.QtWidgets import (
    QFrame,
    QVBoxLayout,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QTextEdit,
    QPushButton,
    QListWidgetItem,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit as QLE,
)
from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtGui import QIcon

from pathlib import Path
from typing import Optional

from src.core.prompt_manager import PromptManager


class PromptEditorDialog(QDialog):
    def __init__(self, name: str = "", category: str = "custom", content: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Prompt Editor")
        self.resize(700, 480)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.name_edit = QLE()
        self.name_edit.setText(name)
        self.cat_edit = QLE()
        self.cat_edit.setText(category)
        self.content_edit = QTextEdit()
        self.content_edit.setPlainText(content)

        form.addRow(QLabel("Nombre:"), self.name_edit)
        form.addRow(QLabel("Categoría:"), self.cat_edit)
        layout.addLayout(form)
        layout.addWidget(QLabel("Contenido:"))
        layout.addWidget(self.content_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self):
        return self.name_edit.text().strip(), self.cat_edit.text().strip(), self.content_edit.toPlainText()


class PromptLibraryPanel(QFrame):
    prompt_selected = pyqtSignal(str)  # emite filename o nombre
    prompt_loaded = pyqtSignal(str)    # emite contenido completo

    def __init__(self, parent=None):
        super().__init__(parent)
        self.prompt_manager = PromptManager()
        self._current_prompt_path: str | None = None
        self._setup_ui()
        self._refresh_list()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Search bar
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("🔍 Buscar prompt...")
        self.search_bar.textChanged.connect(self._filter_prompts)

        # List
        self.prompt_list = QListWidget()
        self.prompt_list.itemDoubleClicked.connect(self._on_prompt_double_click)
        self.prompt_list.currentItemChanged.connect(self._on_prompt_selected)

        # Preview
        self.preview_text = QTextEdit()
        self.preview_text.setReadOnly(True)
        self.preview_text.setMaximumHeight(160)

        # Editor
        self.editor = QTextEdit()
        self.editor.setPlaceholderText("Escribe tu prompt aqui...")
        self.editor.setMinimumHeight(180)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_new = QPushButton("➕ Nuevo Prompt")
        btn_edit = QPushButton("✏️ Editar")
        btn_delete = QPushButton("🗑️ Eliminar")
        btn_save = QPushButton("💾 Guardar Prompt")
        btn_refresh = QPushButton("🔄 Recargar")

        btn_new.clicked.connect(self._create_new_prompt)
        btn_edit.clicked.connect(self._edit_selected_prompt)
        btn_delete.clicked.connect(self._delete_selected_prompt)
        btn_save.clicked.connect(self._save_current_prompt)
        btn_refresh.clicked.connect(self._refresh_list)

        btn_layout.addWidget(btn_new)
        btn_layout.addWidget(btn_edit)
        btn_layout.addWidget(btn_delete)
        btn_layout.addWidget(btn_save)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_refresh)

        layout.addWidget(QLabel("📚 Biblioteca de Prompts:"))
        layout.addWidget(self.search_bar)
        layout.addWidget(self.prompt_list)
        layout.addWidget(QLabel("Editor:"))
        layout.addWidget(self.editor)
        layout.addWidget(self.preview_text)
        layout.addLayout(btn_layout)

    def _refresh_list(self):
        self.prompt_list.clear()
        items = self.prompt_manager.list_prompts()
        for it in items:
            label = f"[{it['type']}] {it['name']}"
            lw = QListWidgetItem(label)
            lw.setData(Qt.ItemDataRole.UserRole, it['path'])
            lw.setToolTip(it['path'])
            self.prompt_list.addItem(lw)

    def _filter_prompts(self, text: str):
        text = (text or "").lower()
        for i in range(self.prompt_list.count()):
            item = self.prompt_list.item(i)
            visible = text in item.text().lower() or text in (item.toolTip() or "").lower()
            item.setHidden(not visible)

    def _on_prompt_selected(self, current: Optional[QListWidgetItem], previous: Optional[QListWidgetItem]):
        if not current:
            self.preview_text.clear()
            self.editor.clear()
            self._current_prompt_path = None
            return
        path = current.data(Qt.ItemDataRole.UserRole)
        self._current_prompt_path = str(path)
        try:
            full = self.prompt_manager.load_prompt(path)
            preview = full[:1000]
        except Exception:
            preview = f"No se pudo cargar preview: {path}"
            full = ""
        self.preview_text.setPlainText(preview)
        self.editor.setPlainText(full)
        # Emit simple identifier (filename)
        self.prompt_selected.emit(Path(path).stem)

    def _on_prompt_double_click(self, item: QListWidgetItem):
        # load full content and emit
        path = item.data(Qt.ItemDataRole.UserRole)
        try:
            content = self.prompt_manager.load_prompt(path)
            self.prompt_loaded.emit(content)
            self.editor.setPlainText(content)
            self._current_prompt_path = str(path)
        except Exception as e:
            from PyQt6.QtWidgets import QMessageBox

            QMessageBox.critical(self, "Error", f"No se pudo cargar prompt:\n{e}")

    def _create_new_prompt(self):
        dlg = PromptEditorDialog(parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            name, category, content = dlg.values()
            if not name or not content:
                from PyQt6.QtWidgets import QMessageBox

                QMessageBox.warning(self, "Aviso", "Nombre y contenido son obligatorios")
                return
            dest = self.prompt_manager.save_prompt(name, content, category or "custom")
            self._refresh_list()
            # select saved
            self._select_path(str(dest))

    def _edit_selected_prompt(self):
        item = self.prompt_list.currentItem()
        if not item:
            return
        path = item.data(Qt.ItemDataRole.UserRole)
        try:
            content = self.prompt_manager.load_prompt(path)
        except Exception as e:
            from PyQt6.QtWidgets import QMessageBox

            QMessageBox.critical(self, "Error", f"No se pudo abrir prompt:\n{e}")
            return

        # derive name/category from path
        p = Path(path)
        name = p.stem
        category = p.parent.name
        dlg = PromptEditorDialog(name=name, category=category, content=content, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_name, new_cat, new_content = dlg.values()
            # if name/category unchanged, overwrite
            if new_name == name and new_cat == category:
                p.write_text(new_content, encoding="utf-8")
                self._refresh_list()
                self._select_path(str(p))
            else:
                # save as new and delete old
                new_path = self.prompt_manager.save_prompt(new_name, new_content, new_cat or "custom")
                try:
                    p.unlink()
                except Exception:
                    pass
                self._refresh_list()
                self._select_path(str(new_path))

    def _delete_selected_prompt(self):
        item = self.prompt_list.currentItem()
        if not item:
            return
        path = item.data(Qt.ItemDataRole.UserRole)
        from PyQt6.QtWidgets import QMessageBox

        res = QMessageBox.question(self, "Confirmar", f"Eliminar prompt {path}?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if res == QMessageBox.StandardButton.Yes:
            try:
                Path(path).unlink()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"No se pudo eliminar:\n{e}")
            self._refresh_list()
            self._current_prompt_path = None
            self.editor.clear()

    def _save_current_prompt(self):
        from PyQt6.QtWidgets import QMessageBox

        content = self.editor.toPlainText()
        if not content.strip():
            QMessageBox.warning(self, "Aviso", "No hay contenido para guardar")
            return

        if self._current_prompt_path:
            p = Path(self._current_prompt_path)
            try:
                p.write_text(content, encoding="utf-8")
                self._refresh_list()
                self._select_path(str(p))
                return
            except Exception as exc:
                QMessageBox.critical(self, "Error", f"No se pudo guardar prompt:\n{exc}")
                return

        name = f"prompt_{len(self.prompt_manager.list_prompts()) + 1}"
        try:
            dest = self.prompt_manager.save_prompt(name, content, category="custom")
            self._refresh_list()
            self._select_path(str(dest))
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"No se pudo guardar prompt:\n{exc}")

    def _select_path(self, path: str):
        for i in range(self.prompt_list.count()):
            item = self.prompt_list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == path:
                self.prompt_list.setCurrentItem(item)
                return

"""src/ui/prompt_selector.py
Módulo independiente con PromptSelector(QGroupBox).

Importable por config_panel y otros widgets sin circularidad:
    from src.ui.prompt_selector import PromptSelector

La clase también se re-exporta desde config_panel por compatibilidad con código
anterior que la importaba desde allí.
"""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)


class PromptSelector(QGroupBox):
    """Árbol jerárquico de prompts con previsualización y acciones.

    Señal
    -----
    prompt_selected(str)
        Emite la ruta relativa al directorio ``prompts/`` cuando el usuario
        selecciona un ítem del árbol.
    """

    prompt_selected = pyqtSignal(str)

    _FOLDER_ICONS: dict[str, str] = {
        "general":        "📁",
        "clients":        "👥",
        "document_types": "📄",
        "system":         "⚙",
        "drafts":         "📝",
    }

    def __init__(self, parent=None) -> None:
        super().__init__("📚  Biblioteca de Prompts", parent)
        self.setObjectName("promptSelectorGroup")
        self._prompts_dir: Path = Path(__file__).resolve().parents[2] / "prompts"
        self._build_ui()
        self.refresh()

    # ── Construcción de UI ────────────────────────────────────────────────

    def _build_ui(self) -> None:
        outer = QVBoxLayout()
        outer.setContentsMargins(10, 14, 10, 10)
        outer.setSpacing(8)

        # Barra de botones
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        self._new_btn     = QPushButton("+ Nuevo")
        self._edit_btn    = QPushButton("✏  Editar")
        self._test_btn    = QPushButton("▶  Probar")
        self._refresh_btn = QPushButton("↺")
        self._refresh_btn.setFixedWidth(32)
        self._refresh_btn.setToolTip("Recargar árbol de prompts")
        for btn in (self._new_btn, self._edit_btn, self._test_btn):
            btn.setFixedHeight(30)
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        btn_row.addWidget(self._new_btn)
        btn_row.addWidget(self._edit_btn)
        btn_row.addWidget(self._test_btn)
        btn_row.addStretch()
        btn_row.addWidget(self._refresh_btn)
        outer.addLayout(btn_row)

        # Árbol + previsualización
        content_row = QHBoxLayout()
        content_row.setSpacing(8)

        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setObjectName("promptTree")
        self._tree.setFixedWidth(200)
        self._tree.setMinimumHeight(220)

        self._preview = QTextEdit()
        self._preview.setObjectName("promptPreview")
        self._preview.setReadOnly(True)
        self._preview.setPlaceholderText("Selecciona un prompt para previsualizar…")
        self._preview.setMinimumHeight(220)

        content_row.addWidget(self._tree)
        content_row.addWidget(self._preview, stretch=1)
        outer.addLayout(content_row)

        # Etiqueta de ruta activa
        self._path_lbl = QLabel("")
        self._path_lbl.setObjectName("promptPathLabel")
        self._path_lbl.setStyleSheet("color: #6B7280; font-size: 11px;")
        outer.addWidget(self._path_lbl)

        self.setLayout(outer)

        # Conexiones
        self._tree.currentItemChanged.connect(self._on_item_changed)
        self._new_btn.clicked.connect(self._on_new)
        self._edit_btn.clicked.connect(self._on_edit)
        self._test_btn.clicked.connect(self._on_test)
        self._refresh_btn.clicked.connect(self.refresh)

    # ── Población del árbol ───────────────────────────────────────────────

    def refresh(self) -> None:
        """Recarga el árbol desde disco llamando a load_prompt_tree."""
        try:
            try:
                from src.core.prompt_manager import load_prompt_tree
            except Exception:
                from core.prompt_manager import load_prompt_tree  # type: ignore[no-redef]
            tree_data = load_prompt_tree(self._prompts_dir)
        except Exception:
            tree_data = {}

        self._tree.clear()
        for category, entries in tree_data.items():
            icon_key = category.lower().replace(" ", "_")
            icon     = self._FOLDER_ICONS.get(icon_key, "📁")
            cat_item = QTreeWidgetItem([f"{icon}  {category}"])
            cat_item.setData(0, Qt.ItemDataRole.UserRole, None)
            for entry in entries:
                child = QTreeWidgetItem([entry["name"]])
                child.setData(0, Qt.ItemDataRole.UserRole, entry["rel_path"])
                child.setToolTip(0, entry["rel_path"])
                cat_item.addChild(child)
            self._tree.addTopLevelItem(cat_item)
            cat_item.setExpanded(True)

    # ── Slots internos ────────────────────────────────────────────────────

    def _on_item_changed(self, current: QTreeWidgetItem | None, _previous) -> None:
        if current is None:
            return
        rel_path: str | None = current.data(0, Qt.ItemDataRole.UserRole)
        if rel_path is None:
            self._path_lbl.setText("")
            return
        self._path_lbl.setText(rel_path)
        full_path = self._prompts_dir / rel_path
        try:
            self._preview.setPlainText(full_path.read_text(encoding="utf-8"))
        except Exception as exc:
            self._preview.setPlainText(f"[Error al leer: {exc}]")
        self.prompt_selected.emit(rel_path)

    def _on_new(self) -> None:
        name, ok = QInputDialog.getText(
            self, "Nuevo prompt", "Nombre del archivo (.txt):"
        )
        if not ok or not name.strip():
            return
        name = name.strip()
        if not (name.endswith(".tpl") or name.endswith(".txt")):
            name += ".txt"
        cats = ["clients", "document_types", "system", "drafts"]
        cat, ok2 = QInputDialog.getItem(
            self, "Categoría", "Selecciona carpeta de destino:", cats, 0, False
        )
        if not ok2:
            return
        target_dir = self._prompts_dir / cat
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / name
        if target.exists():
            QMessageBox.warning(self, "Ya existe", f"'{name}' ya existe en {cat}/.")
            return
        target.write_text(
            f"# Prompt: {name}\n# Carpeta: {cat}\n\n"
            "Extrae la información del documento y devuelve ÚNICAMENTE JSON válido:\n{}\n\n"
            "# Variables disponibles: {{ profile }}, {{ mode }}, {{ filename }}\n",
            encoding="utf-8",
        )
        self.refresh()
        self._open_editor(target)

    def _on_edit(self) -> None:
        current = self._tree.currentItem()
        if current is None:
            QMessageBox.information(self, "Editar", "Selecciona un prompt en el árbol primero.")
            return
        rel_path: str | None = current.data(0, Qt.ItemDataRole.UserRole)
        if rel_path is None:
            return
        self._open_editor(self._prompts_dir / rel_path)

    def _open_editor(self, path: Path) -> None:
        try:
            try:
                from .template_editor import TemplateEditor
            except Exception:
                from src.ui.template_editor import TemplateEditor  # type: ignore[no-redef]
            dlg = TemplateEditor(initial_template=path.name, parent=self)
            dlg.exec()
        except Exception:
            try:
                import subprocess
                import sys as _sys
                if _sys.platform == "win32":
                    subprocess.Popen(["notepad", str(path)])
                else:
                    subprocess.Popen(["xdg-open", str(path)])
            except Exception as ex:
                QMessageBox.warning(self, "Error", f"No se pudo abrir el editor: {ex}")
        self.refresh()

    def _on_test(self) -> None:
        current = self._tree.currentItem()
        if current is None:
            QMessageBox.information(self, "Probar", "Selecciona un prompt en el árbol primero.")
            return
        rel_path: str | None = current.data(0, Qt.ItemDataRole.UserRole)
        if rel_path is None:
            return
        full_path = self._prompts_dir / rel_path
        try:
            raw = full_path.read_text(encoding="utf-8")
        except Exception as exc:
            QMessageBox.warning(self, "Error", f"No se pudo leer el prompt: {exc}")
            return
        ctx = {
            "profile":  "Facturas/Contable",
            "mode":     "single_invoice",
            "filename": "FACT-2024-001.pdf",
        }
        try:
            from jinja2 import Environment, BaseLoader
            rendered = (
                Environment(loader=BaseLoader(), autoescape=False)
                .from_string(raw)
                .render(**ctx)
            )
        except Exception:
            rendered = raw
        dlg = QMessageBox(self)
        dlg.setWindowTitle(f"Vista previa — {rel_path}")
        dlg.setText(
            f"<b>Prompt:</b> {rel_path}<br>"
            f"<b>Contexto:</b> {ctx}<br><br>"
            "<i>Resultado renderizado disponible en «Detalles».</i>"
        )
        dlg.setDetailedText(rendered)
        dlg.exec()

    # ── API pública ───────────────────────────────────────────────────────

    def select_by_path(self, rel_path: str) -> bool:
        """Selecciona el ítem del árbol con la ruta relativa dada.

        Devuelve ``True`` si lo encontró y seleccionó.
        """
        def _search(item: QTreeWidgetItem) -> bool:
            if item.data(0, Qt.ItemDataRole.UserRole) == rel_path:
                self._tree.setCurrentItem(item)
                return True
            for i in range(item.childCount()):
                if _search(item.child(i)):
                    return True
            return False

        for i in range(self._tree.topLevelItemCount()):
            if _search(self._tree.topLevelItem(i)):
                return True
        return False

    def current_rel_path(self) -> str | None:
        """Ruta relativa del prompt actualmente seleccionado, o ``None``."""
        item = self._tree.currentItem()
        if item is None:
            return None
        return item.data(0, Qt.ItemDataRole.UserRole)

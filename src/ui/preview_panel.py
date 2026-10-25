from __future__ import annotations

from pathlib import Path
from typing import List

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QListWidget, QListWidgetItem,
    QGraphicsView, QGraphicsScene, QToolBar, QAction, QSizePolicy, QFileDialog, QMessageBox,
    QTextEdit, QLabel
)
from PyQt6.QtGui import QPixmap, QIcon, QTransform
from PyQt6.QtCore import Qt, QSize, pyqtSignal


class PreviewPanel(QWidget):
    """Visor principal de documentos.

    - QGraphicsView para mostrar la imagen (expandible)
    - Toolbar con Zoom+/-, 100%, Rotar, PDF->Imagen
    - Lista de archivos a la derecha
    """

    file_removed = pyqtSignal(str)
    request_pdf_to_img = pyqtSignal(str)  # emits selected pdf path

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: List[str] = []
        self._result_items: List[str] = []
        self._pix_item = None
        self._scale = 1.0
        self._rotation = 0
        self._current_path: str | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout()
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        main_h = QHBoxLayout()
        main_h.setSpacing(12)

        # Left: graphics view and toolbar
        left_w = QWidget()
        left_l = QVBoxLayout()
        left_l.setContentsMargins(0, 0, 0, 0)
        left_l.setSpacing(6)

        self.scene = QGraphicsScene(self)
        self.view = QGraphicsView(self.scene)
        self.view.setObjectName("previewGraphicsView")
        self.view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.view.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left_l.addWidget(self.view, 1)

        # Toolbar
        self.toolbar = QToolBar()
        self.toolbar.setIconSize(QSize(18, 18))
        self.act_zoom_in = QAction("🔍 +", self)
        self.act_zoom_out = QAction("🔍 -", self)
        self.act_reset = QAction("100%", self)
        self.act_rotate = QAction("🔄 Rotar", self)
        self.act_pdf2img = QAction("📄 PDF -> Imagen", self)
        self.act_remove = QAction("🗑 Eliminar", self)

        for a in (self.act_zoom_in, self.act_zoom_out, self.act_reset, self.act_rotate, self.act_pdf2img, self.act_remove):
            self.toolbar.addAction(a)
            self.toolbar.addSeparator()

        left_l.addWidget(self.toolbar)
        left_w.setLayout(left_l)
        main_h.addWidget(left_w, 3)

        # Right: scanned files + result files
        right_w = QWidget()
        right_l = QVBoxLayout()
        right_l.setContentsMargins(0, 0, 0, 0)
        right_l.setSpacing(6)

        right_l.addWidget(QLabel("Escaneados"))
        self.file_list = QListWidget()
        self.file_list.setObjectName("previewFileList")
        self.file_list.setViewMode(QListWidget.ViewMode.ListMode)
        self.file_list.setIconSize(QSize(110, 82))
        self.file_list.setMovement(QListWidget.Movement.Static)
        self.file_list.setSpacing(6)
        self.file_list.setMinimumWidth(260)
        right_l.addWidget(self.file_list, 2)

        right_l.addWidget(QLabel("Resultados"))
        self.result_list = QListWidget()
        self.result_list.setObjectName("previewResultList")
        self.result_list.setViewMode(QListWidget.ViewMode.ListMode)
        self.result_list.setMovement(QListWidget.Movement.Static)
        self.result_list.setSpacing(6)
        self.result_list.setMinimumWidth(260)
        right_l.addWidget(self.result_list, 1)

        self.result_preview = QTextEdit()
        self.result_preview.setReadOnly(True)
        self.result_preview.setPlaceholderText("Selecciona un resultado para previsualizar...")
        self.result_preview.setMinimumHeight(110)
        right_l.addWidget(self.result_preview, 1)

        right_w.setLayout(right_l)
        main_h.addWidget(right_w, 1)

        root.addLayout(main_h, 1)
        self.setLayout(root)

        # Connections
        self.file_list.itemClicked.connect(self._on_item_selected)
        self.result_list.itemClicked.connect(self._on_result_selected)
        self.act_zoom_in.triggered.connect(lambda: self._change_zoom(1.15))
        self.act_zoom_out.triggered.connect(lambda: self._change_zoom(1 / 1.15))
        self.act_reset.triggered.connect(self._reset_view)
        self.act_rotate.triggered.connect(self._rotate)
        self.act_pdf2img.triggered.connect(self._choose_pdf_and_convert)
        self.act_remove.triggered.connect(self._remove_selected)

    def add_files(self, files: List[str]) -> None:
        for p in files:
            self.add_file(p)

    def add_file(self, path: str) -> None:
        if not path:
            return
        if path in self._items:
            return
        self._items.append(path)
        icon = QIcon()
        try:
            pix = QPixmap(path)
            if not pix.isNull():
                icon = QIcon(pix.scaled(110, 82, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        except Exception:
            pass
        itm = QListWidgetItem(icon, Path(path).name)
        itm.setData(Qt.ItemDataRole.UserRole, path)
        self.file_list.addItem(itm)

    def add_result_file(self, path: str) -> None:
        if not path:
            return
        if path in self._result_items:
            return
        self._result_items.append(path)
        itm = QListWidgetItem(Path(path).name)
        itm.setData(Qt.ItemDataRole.UserRole, path)
        self.result_list.addItem(itm)

    def _on_item_selected(self, itm: QListWidgetItem) -> None:
        path = itm.data(Qt.ItemDataRole.UserRole)
        if not path:
            return
        pix = QPixmap(path)
        if pix.isNull():
            QMessageBox.warning(self, "Vista previa", "No se pudo cargar la imagen seleccionada.")
            return
        self.scene.clear()
        self._pix_item = self.scene.addPixmap(pix)
        self._pix_item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        self.view.fitInView(self._pix_item, Qt.AspectRatioMode.KeepAspectRatio)
        self._scale = 1.0
        self._rotation = 0
        self._current_path = path

    def _on_result_selected(self, itm: QListWidgetItem) -> None:
        path = itm.data(Qt.ItemDataRole.UserRole)
        if not path:
            return
        self._select_matching_source_for_result(str(path))
        try:
            # Si es imagen, mostrar en el visor gráfico para comparar visualmente.
            pix = QPixmap(path)
            if not pix.isNull():
                self.scene.clear()
                self._pix_item = self.scene.addPixmap(pix)
                self._pix_item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
                self.view.fitInView(self._pix_item, Qt.AspectRatioMode.KeepAspectRatio)
                self._scale = 1.0
                self._rotation = 0
                self._current_path = path
        except Exception:
            pass

        try:
            p = Path(path)
            if p.suffix.lower() in {".txt", ".md", ".json", ".csv", ".log"} and p.exists():
                content = p.read_text(encoding="utf-8", errors="ignore")
                self.result_preview.setPlainText(content[:12000])
            elif p.suffix.lower() == ".docx" and p.exists():
                try:
                    from docx import Document

                    doc = Document(p)
                    paragraphs = [para.text for para in doc.paragraphs if para.text.strip()]
                    self.result_preview.setPlainText("\n".join(paragraphs)[:12000] or f"Archivo DOCX: {p.name}")
                except Exception:
                    self.result_preview.setPlainText(
                        f"Archivo DOCX: {p}\n\nNo se pudo renderizar el contenido del documento."
                    )
            elif p.suffix.lower() in {".xlsx", ".xls", ".xlsm"} and p.exists():
                try:
                    import pandas as pd

                    xls = pd.ExcelFile(p)
                    preview_blocks = []
                    for sheet_name in xls.sheet_names[:2]:
                        df = pd.read_excel(xls, sheet_name=sheet_name)
                        head = df.head(20)
                        preview_blocks.append(
                            f"[Hoja: {sheet_name}]\n"
                            f"Filas: {len(df)}  Columnas: {len(df.columns)}\n\n"
                            f"{head.to_string(index=False)}"
                        )
                    self.result_preview.setPlainText("\n\n".join(preview_blocks)[:12000])
                except Exception:
                    self.result_preview.setPlainText(
                        f"Archivo Excel: {p}\n\n"
                        "No se pudo renderizar vista tabular previa."
                    )
            else:
                self.result_preview.setPlainText(str(p))
        except Exception:
            self.result_preview.setPlainText(str(path))

    def _select_matching_source_for_result(self, result_path: str) -> None:
        try:
            result_name = Path(result_path).name
            candidate_stems: list[str] = []

            if "__mistral" in result_name:
                candidate_stems.append(result_name.split("_20", 1)[0])
            else:
                candidate_stems.append(Path(result_name).stem)

            for idx in range(self.file_list.count()):
                item = self.file_list.item(idx)
                if item is None:
                    continue
                source_path = str(item.data(Qt.ItemDataRole.UserRole) or "")
                source_stem = Path(source_path).stem
                if any(source_stem == stem or source_stem in stem or stem in source_stem for stem in candidate_stems if stem):
                    self.file_list.setCurrentItem(item)
                    self._on_item_selected(item)
                    return
        except Exception:
            pass

    def _change_zoom(self, factor: float) -> None:
        if not self._pix_item:
            return
        self._scale = max(0.05, min(10.0, self._scale * factor))
        t = QTransform()
        t.scale(self._scale, self._scale)
        t.rotate(self._rotation)
        self._pix_item.setTransform(t)

    def _reset_view(self) -> None:
        if not self._pix_item:
            return
        self._scale = 1.0
        self._rotation = 0
        self._pix_item.setTransform(QTransform())
        self.view.fitInView(self._pix_item, Qt.AspectRatioMode.KeepAspectRatio)

    def _rotate(self) -> None:
        if not self._pix_item:
            return
        self._rotation = (self._rotation + 90) % 360
        t = QTransform()
        t.scale(self._scale, self._scale)
        t.rotate(self._rotation)
        self._pix_item.setTransform(t)

    def _remove_selected(self) -> None:
        itm = self.file_list.currentItem()
        if not itm:
            return
        path = itm.data(Qt.ItemDataRole.UserRole)
        if path and path in self._items:
            self._items.remove(path)
            self.file_list.takeItem(self.file_list.row(itm))
            self.file_removed.emit(path)
            # clear view if removed was current
            if path == self._current_path:
                self.scene.clear()
                self._pix_item = None
                self._current_path = None

    def _choose_pdf_and_convert(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Seleccionar PDF para convertir", "", "PDF Files (*.pdf);;All Files (*)")
        if not path:
            return
        # try to use pdf2image if available; otherwise emit request
        try:
            from pdf2image import convert_from_path
            pages = convert_from_path(path, first_page=1, last_page=1)
            if pages:
                import tempfile
                tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.png')
                pages[0].save(tmp.name, 'PNG')
                self.add_file(tmp.name)
                return
        except Exception:
            pass
        # fallback: emit signal so caller can handle conversion
        self.request_pdf_to_img.emit(path)

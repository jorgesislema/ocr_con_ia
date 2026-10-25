"""Dynamic Schema Builder — selección de campos a extraer por el motor OCR."""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QGroupBox,
    QCheckBox,
    QPushButton,
    QLabel,
    QScrollArea,
    QFrame,
    QComboBox,
    QInputDialog,
)

# ── Catálogo base de campos ───────────────────────────────────────────────────
# Estructura: {titulo_grupo: {clave_interna: etiqueta_ui}}
_SCHEMA_GROUPS: dict[str, dict[str, str]] = {
    "Datos de Entidad": {
        "emisor_nombre":     "Razón Social",
        "emisor_ruc":        "RUC / NIF / CIF",
        "emisor_direccion":  "Dirección Emisor",
        "receptor_nombre":   "Cliente / Receptor",
        "receptor_ruc":      "RUC / ID Receptor",
    },
    "Cabecera de Documento": {
        "numero_factura":    "N.º Factura",
        "fecha":             "Fecha de Emisión",
        "fecha_vencimiento": "Fecha Vencimiento",
        "moneda":            "Moneda",
        "numero_orden":      "N.º Orden de Compra",
        "condicion_pago":    "Condición de Pago",
    },
    "Montos Totales": {
        "subtotal":   "Subtotal",
        "descuento":  "Descuento",
        "impuestos":  "Impuestos / IVA",
        "total":      "Total a Pagar",
        "forma_pago": "Forma de Pago",
    },
    "Doc. Histórico / Arte": {
        "titulo":                  "Título del documento",
        "autor":                   "Autor / Artista",
        "anio_publicacion":        "Año de publicación",
        "editorial_imprenta":      "Editorial / Imprenta",
        "lugar_publicacion":       "Lugar de publicación",
        "idioma":                  "Idioma",
        "num_paginas":             "N.º páginas / láminas",
        "descripcion_ilustracion": "Descripción de ilustración",
        "texto_visible":           "Texto visible transcrito",
        "dedicatoria":             "Dedicatoria / inscripción",
        "estado_conservacion":     "Estado de conservación",
        "notas_adicionales":       "Notas adicionales",
    },
}


class SchemaPanel(QWidget):
    """Panel embebido como pestaña en el QTabWidget de ConfigPanel.

    Presenta tres QGroupBox (uno por grupo de campos) dentro de un
    QGridLayout.  Expone ``get_active_schema()`` que devuelve la lista
    de claves (keys) de los checkboxes marcados.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        # Mapa interno: clave_campo → QCheckBox
        self._checkboxes: dict[str, QCheckBox] = {}

        root = QVBoxLayout()
        root.setSpacing(10)
        root.setContentsMargins(0, 8, 0, 8)

        lbl = QLabel("CAMPOS A EXTRAER — ESQUEMA ACTIVO")
        lbl.setObjectName("cardTitle")
        root.addWidget(lbl)

        hint = QLabel(
            "Marca los campos que el modelo debe extraer.\n"
            "Usa el grupo «Doc. Histórico / Arte» para libros, manuscritos o láminas."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#6B7280; font-size:11px;")
        root.addWidget(hint)

        # ── Área con scroll (los grupos pueden ser altos en pantallas pequeñas)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        groups_container = QWidget()
        grid = QGridLayout()
        grid.setSpacing(8)
        grid.setContentsMargins(0, 0, 0, 0)

        # Distribución dinámica: 2 columnas, N filas según cantidad de grupos
        _COLS = 2
        for idx, (group_title, fields) in enumerate(_SCHEMA_GROUPS.items()):
            row, col = divmod(idx, _COLS)
            box = QGroupBox(group_title)
            box.setObjectName("profileGroup")
            box_lay = QVBoxLayout()
            box_lay.setSpacing(5)
            box_lay.setContentsMargins(10, 10, 10, 10)

            for key, label in fields.items():
                chk = QCheckBox(label)
                chk.setObjectName("profileRadio")
                chk.setChecked(False)         # desactivado por defecto — usuario elige
                self._checkboxes[key] = chk
                box_lay.addWidget(chk)

            box_lay.addStretch()
            box.setLayout(box_lay)
            grid.addWidget(box, row, col)

        groups_container.setLayout(grid)
        scroll.setWidget(groups_container)
        root.addWidget(scroll, stretch=1)

        # ── Barra de acciones rápidas ─────────────────────────────────────────
        btn_row = QWidget()
        btn_lay = QHBoxLayout()
        btn_lay.setContentsMargins(0, 0, 0, 0)
        btn_lay.setSpacing(8)

        all_btn = QPushButton("Seleccionar Todo")
        all_btn.setObjectName("validateBtn")
        all_btn.clicked.connect(self.select_all)

        clear_btn = QPushButton("Limpiar Selección")
        clear_btn.setObjectName("clearBtn")
        clear_btn.clicked.connect(self.clear_selection)

        btn_lay.addWidget(all_btn)
        btn_lay.addWidget(clear_btn)
        btn_row.setLayout(btn_lay)
        root.addWidget(btn_row)

        # ── Modo Libre: plantillas de usuario
        free_row = QWidget()
        free_lay = QHBoxLayout()
        free_lay.setContentsMargins(0, 8, 0, 0)
        free_lay.setSpacing(8)

        self._templates_combo = QComboBox()
        self._templates_combo.setEditable(False)
        self._templates_combo.setToolTip("Mis Plantillas Guardadas")

        save_tpl_btn = QPushButton("Guardar Esquema Actual")
        save_tpl_btn.setObjectName("validateBtn")
        save_tpl_btn.clicked.connect(self._on_save_current_schema)

        free_lay.addWidget(QLabel("Mis Plantillas Guardadas:"))
        free_lay.addWidget(self._templates_combo, stretch=1)
        free_lay.addWidget(save_tpl_btn)

        free_row.setLayout(free_lay)
        root.addWidget(free_row)

        # TemplateManager — gestiona los ficheros JSON de plantillas
        self._tpl_manager: TemplateManager | None = None
        try:
            from src.data.template_manager import TemplateManager

            self._tpl_manager = TemplateManager()
            self._refresh_templates_dropdown()
            self._templates_combo.currentTextChanged.connect(self._on_template_selected)
        except Exception:
            self._tpl_manager = None

        self.setLayout(root)

    # ── API pública ───────────────────────────────────────────────────────────

    def get_active_schema(self) -> list[str]:
        """Devuelve las claves de los campos marcados por el usuario."""
        return [key for key, chk in self._checkboxes.items() if chk.isChecked()]

    def select_all(self) -> None:
        for chk in self._checkboxes.values():
            chk.setChecked(True)

    def clear_selection(self) -> None:
        for chk in self._checkboxes.values():
            chk.setChecked(False)

    # ── Plantillas de usuario ──────────────────────────────────────────────
    def _refresh_templates_dropdown(self) -> None:
        if not self._tpl_manager:
            return
        templates = self._tpl_manager.load_available_templates()
        self._templates = templates
        self._templates_combo.blockSignals(True)
        self._templates_combo.clear()
        self._templates_combo.addItem("")
        for name in sorted(templates.keys()):
            self._templates_combo.addItem(name)
        self._templates_combo.blockSignals(False)

    def _on_save_current_schema(self) -> None:
        if not self._tpl_manager:
            return
        schema = self.get_active_schema()
        if not schema:
            # No hay campos seleccionados — nada que guardar
            return
        name, ok = QInputDialog.getText(self, "Nombre plantilla", "Nombre para la plantilla:")
        if not ok or not name.strip():
            return
        schema_dict = {"fields": schema}
        try:
            self._tpl_manager.save_custom_template(name.strip(), schema_dict)
            self._refresh_templates_dropdown()
        except Exception:
            return

    def _on_template_selected(self, name: str) -> None:
        if not name or not getattr(self, "_templates", None):
            return
        tpl = self._templates.get(name)
        if not tpl:
            return
        # Soportar formatos: lista directa o dict {"fields": [...]}
        fields = []
        if isinstance(tpl, dict) and "fields" in tpl and isinstance(tpl["fields"], list):
            fields = tpl["fields"]
        elif isinstance(tpl, list):
            fields = tpl
        else:
            return

        # Aplicar: marcar los checkboxes presentes en la plantilla
        for key, chk in self._checkboxes.items():
            chk.setChecked(key in fields)

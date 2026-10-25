"""
md_to_excel_panel.py
────────────────────────────────────────────────────────────────────────────
Panel independiente "📊 MD → Excel".

Permite convertir carpetas de archivos Markdown / JSON (resultado del OCR)
directamente a Excel usando IA, sin necesidad de volver a ejecutar el OCR.

Flujo:
    1. Usuario elige una o varias carpetas con archivos *.md / *.json
    2. La app lista los archivos encontrados
    3. Usuario pega / edita el prompt con el esquema de extracción
    4. Usuario pulsa "▶  Convertir a Excel"
    5. Un hilo secundario llama al LLM para cada archivo y genera el .xlsx
    6. Se muestra progreso en tiempo real y se abre la carpeta de salida
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
from datetime import datetime
from pathlib import Path
from typing import Callable

from PyQt6.QtCore import (
    QMimeData,
    QObject,
    Qt,
    QThread,
    QUrl,
    pyqtSignal,
)
from PyQt6.QtGui import QColor, QDragEnterEvent, QDropEvent, QFont
from PyQt6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

_log = logging.getLogger("ocr.md_to_excel_panel")


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  QListWidget con soporte drag & drop de archivos/carpetas               ║
# ╚══════════════════════════════════════════════════════════════════════════╝
class _DropListWidget(QListWidget):
    """Lista que acepta arrastre de archivos y carpetas desde el explorador."""

    files_dropped = pyqtSignal(list)  # list[str] de rutas

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setDragDropMode(QListWidget.DragDropMode.DropOnly)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # type: ignore[override]
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:  # type: ignore[override]
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:  # type: ignore[override]
        if event.mimeData().hasUrls():
            paths = [u.toLocalFile() for u in event.mimeData().urls()]
            self.files_dropped.emit(paths)
            event.acceptProposedAction()
        else:
            super().dropEvent(event)



_ACCEPTED_EXTS = {".md", ".json", ".txt", ".xlsx", ".xls", ".csv", ".docx", ".doc"}

# Icono según extensión de archivo
_EXT_ICON = {
    ".md":   "📝",
    ".json": "{ }",
    ".txt":  "📄",
    ".xlsx": "📈",
    ".xls":  "📈",
    ".csv":  "📊",
    ".docx": "📘",
    ".doc":  "📘",
}
_EXT_TIPO = {
    ".md":   "Markdown",
    ".json": "JSON",
    ".txt":  "Texto",
    ".xlsx": "Excel",
    ".xls":  "Excel",
    ".csv":  "CSV",
    ".docx": "Word",
    ".doc":  "Word",
}

# Opciones de proveedor para el QComboBox (orden de uso más común)
_PROVIDER_OPTIONS = [
    "DeepSeek",
    "OpenAI GPT-4o",
    "Google Gemini Flash (gratuito)",
    "Google Gemini Pro",
    "Mistral Large",
    "Qwen (Alibaba Cloud)",
    "OpenRouter",
    "Anthropic (Claude 3.5)",
    "GLM-4 (ZhipuAI)",
    "Ollama (local)",
    "LM Studio (local)",
    "Azure OpenAI",
]

# Formatos de salida disponibles
_OUTPUT_FORMATS = [
    ("Excel (.xlsx)",  ".xlsx"),
    ("CSV (.csv)",     ".csv"),
    ("Word (.docx)",   ".docx"),
]

# ─── Prompt por defecto ──────────────────────────────────────────────────────
_DEFAULT_PROMPT = """Eres un experto en extracción de facturas (España / Portugal). \
Recibes como entrada el texto extraído por OCR entre los marcadores ===BEGIN_OCR=== y ===END_OCR===. \
Analiza el texto y devuelve ÚNICAMENTE un JSON válido (sin texto adicional) con un array de objetos, \
uno por cada factura encontrada. Cada objeto debe tener exactamente estas claves:

[
{
  "Nombre archivo": "",
  "Número Factura": "",
  "Fecha": "",
  "Nombre proveedor": "",
  "N.I.F.": "",
  "Conceptos": "",
  "Base": 0.0,
  "IVA": 0.0,
  "IRPF %": 0.0,
  "Importe": 0.0,
  "B Exenta": 0.0,
  "Total": 0.0,
  "Alertas": ""
}
]

Reglas: extrae datos del emisor (no del receptor). Fecha en ISO YYYY-MM-DD si es posible. \
Campos numéricos como float. Alertas: "" si todo está correcto, o descripción breve de problemas. \
Devuelve SOLO el JSON array, sin texto adicional."""


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  Worker — hilo que hace las llamadas al LLM y genera el Excel            ║
# ╚══════════════════════════════════════════════════════════════════════════╝
class _ConversionWorker(QObject):
    """Ejecuta la conversión MD/JSON → Excel en un hilo separado."""

    progress = pyqtSignal(int, int, str)   # (done, total, mensaje)
    file_done = pyqtSignal(str, bool, str)  # (nombre, ok, mensaje)
    finished = pyqtSignal(str)              # ruta del xlsx generado (vacío si error)
    error = pyqtSignal(str)                 # mensaje de error fatal

    def __init__(
        self,
        files: list[Path],
        prompt: str,
        output_dir: Path,
        provider: str,
        api_key: str,
        model: str,
        base_url: str,
        output_format: str = ".xlsx",
    ) -> None:
        super().__init__()
        self._files = files
        self._prompt = prompt
        self._output_dir = output_dir
        self._provider = provider
        self._api_key = api_key
        self._model = model
        self._base_url = base_url
        self._output_format = output_format
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    def run(self) -> None:  # llamado desde QThread
        try:
            self._do_run()
        except Exception as exc:
            _log.exception("Error fatal en _ConversionWorker")
            self.error.emit(str(exc))

    # ── lógica principal ─────────────────────────────────────────────────────
    def _do_run(self) -> None:
        from src.core.structuring_engine import StructuringEngine

        engine = StructuringEngine(
            provider=self._provider,
            api_key=self._api_key,
            model=self._model or "",
            base_url=self._base_url or "",
        )

        rows: list[dict] = []
        total = len(self._files)

        for idx, filepath in enumerate(self._files):
            if self._stop:
                break

            nombre = filepath.name
            self.progress.emit(idx, total, f"Procesando: {nombre}")

            try:
                raw_text = _read_input_file(filepath)
            except Exception as exc:
                self.file_done.emit(nombre, False, f"Error leyendo archivo: {exc}")
                continue

            # Llamar al LLM
            try:
                resp_text, _pt, _ct = engine.structure(raw_text, self._prompt)
            except Exception as exc:
                self.file_done.emit(nombre, False, f"Error LLM: {exc}")
                continue

            if not resp_text or not resp_text.strip():
                self.file_done.emit(
                    nombre, False,
                    "El LLM no devolvió respuesta (API Key inválida, sin créditos o error de red). "
                    "Revisa los logs para más detalles."
                )
                continue

            # Parsear respuesta JSON (array o objeto)
            parsed_list = _parse_llm_response(resp_text)
            if not parsed_list:
                self.file_done.emit(nombre, False, f"No se pudo parsear JSON: {resp_text[:120]!r}")
                continue

            # Derivar nombre de archivo original (quitar sufijo __mistral / timestamp)
            original_name = _stem_to_original_name(filepath.stem) + filepath.suffix
            for row in parsed_list:
                if not row.get("Nombre archivo"):
                    row["Nombre archivo"] = original_name
                rows.append(row)

            self.file_done.emit(nombre, True, f"{len(parsed_list)} factura(s) extraída(s)")

        self.progress.emit(total, total, "Generando archivo de salida…")

        if not rows:
            self.finished.emit("")
            return

        # Escribir según formato elegido
        try:
            fmt = self._output_format
            if fmt == ".csv":
                out_path = _write_csv(rows, self._output_dir)
            elif fmt == ".docx":
                out_path = _write_word(rows, self._output_dir)
            else:
                out_path = _write_excel(rows, self._output_dir)
            self.finished.emit(str(out_path))
        except Exception as exc:
            self.error.emit(f"Error al escribir archivo de salida: {exc}")


# ─── helpers de parseo ───────────────────────────────────────────────────────

def _parse_llm_response(raw: str) -> list[dict]:
    """Extrae un array de dicts desde la respuesta del LLM."""
    raw = raw.strip()
    # Quitar bloques markdown ```json … ```
    raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"\s*```$", "", raw)
    raw = raw.strip()
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [r for r in parsed if isinstance(r, dict)]
        if isinstance(parsed, dict):
            return [parsed]
    except json.JSONDecodeError:
        pass
    # Intentar extraer array embebido
    m = re.search(r"\[[\s\S]*\]", raw)
    if m:
        try:
            parsed = json.loads(m.group(0))
            if isinstance(parsed, list):
                return [r for r in parsed if isinstance(r, dict)]
        except Exception:
            pass
    # Intentar extraer objeto suelto
    m2 = re.search(r"\{[\s\S]*\}", raw)
    if m2:
        try:
            parsed = json.loads(m2.group(0))
            if isinstance(parsed, dict):
                return [parsed]
        except Exception:
            pass
    return []


_TIMESTAMP_SUFFIX_RE = re.compile(r"_\d{8}_\d{6}(?:__\w+)?$")


def _stem_to_original_name(stem: str) -> str:
    """Elimina sufijos de timestamp y backend del nombre de fichero OCR."""
    cleaned = _TIMESTAMP_SUFFIX_RE.sub("", stem)
    # También quitar sufijo __mistral, __deepseek, etc. si quedó
    cleaned = re.sub(r"__\w+$", "", cleaned)
    return cleaned.strip()


def _write_excel(rows: list[dict], output_dir: Path) -> Path:
    """Escribe el Excel con openpyxl; resalta en rojo filas con alertas."""
    try:
        import pandas as pd
    except ImportError as exc:
        raise RuntimeError("pandas no está instalado") from exc
    try:
        import openpyxl
        from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
        _HAS_OPENPYXL = True
    except ImportError:
        _HAS_OPENPYXL = False

    # Columnas canónicas (orden fijo)
    COLS = [
        "Nombre archivo", "Número Factura", "Fecha", "Nombre proveedor",
        "N.I.F.", "Conceptos", "Base", "IVA", "IRPF %", "Importe",
        "B Exenta", "Total", "Alertas",
    ]
    NUMERIC_COLS = {"Base", "IVA", "IRPF %", "Importe", "B Exenta", "Total"}

    normalized: list[dict] = []
    for row in rows:
        out: dict = {}
        for col in COLS:
            val = row.get(col)
            if col in NUMERIC_COLS:
                try:
                    out[col] = float(val) if val is not None else 0.0
                except (TypeError, ValueError):
                    out[col] = 0.0
            elif col == "Alertas":
                out[col] = str(val).strip() if val else ""
            else:
                out[col] = str(val) if val is not None else ""
        normalized.append(out)

    df = pd.DataFrame(normalized, columns=COLS)

    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    xlsx_path = output_dir / f"md_excel_{ts}.xlsx"

    if _HAS_OPENPYXL:
        with pd.ExcelWriter(str(xlsx_path), engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Facturas")
            ws = writer.sheets["Facturas"]

            # Estilos
            header_fill = PatternFill("solid", fgColor="1F4E79")
            alert_fill  = PatternFill("solid", fgColor="FFCCCC")
            header_font = Font(color="FFFFFF", bold=True)
            center_aln  = Alignment(horizontal="center", vertical="center", wrap_text=True)
            thin_border = Border(
                left=Side(style="thin"),
                right=Side(style="thin"),
                top=Side(style="thin"),
                bottom=Side(style="thin"),
            )

            # Cabecera
            for cell in ws[1]:
                cell.fill = header_fill
                cell.font = header_font
                cell.alignment = center_aln
                cell.border = thin_border

            # Filas de datos
            alert_col_idx = COLS.index("Alertas") + 1  # 1-based
            for row_idx, excel_row in enumerate(ws.iter_rows(min_row=2), start=1):
                alerta_val = str(df.iloc[row_idx - 1].get("Alertas", "") or "").strip()
                has_alert = bool(alerta_val)
                for cell in excel_row:
                    cell.border = thin_border
                    cell.alignment = Alignment(vertical="center", wrap_text=True)
                    if has_alert:
                        cell.fill = alert_fill

            # Anchos de columna automáticos
            for col_cells in ws.columns:
                max_len = max(
                    len(str(cell.value or "")) for cell in col_cells
                )
                ws.column_dimensions[col_cells[0].column_letter].width = min(max_len + 4, 50)

            ws.freeze_panes = "A2"
    else:
        df.to_excel(str(xlsx_path), index=False)

    return xlsx_path


def _write_csv(rows: list[dict], output_dir: Path) -> Path:
    """Escribe un CSV plano (sep=;) codificado en UTF-8 con BOM para Excel."""
    try:
        import pandas as pd
    except ImportError as exc:
        raise RuntimeError("pandas no está instalado") from exc

    COLS = [
        "Nombre archivo", "Número Factura", "Fecha", "Nombre proveedor",
        "N.I.F.", "Conceptos", "Base", "IVA", "IRPF %", "Importe",
        "B Exenta", "Total", "Alertas",
    ]
    df = pd.DataFrame(
        [{c: row.get(c, "") for c in COLS} for row in rows],
        columns=COLS,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = output_dir / f"ocr_resultado_{ts}.csv"
    df.to_csv(str(csv_path), index=False, sep=";", encoding="utf-8-sig")
    return csv_path


def _write_word(rows: list[dict], output_dir: Path) -> Path:
    """Escribe un documento Word (.docx) con una tabla formateada."""
    try:
        from docx import Document
        from docx.shared import Pt, RGBColor
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        _HAS_DOCX = True
    except ImportError:
        _HAS_DOCX = False

    COLS = [
        "Nombre archivo", "Número Factura", "Fecha", "Nombre proveedor",
        "N.I.F.", "Conceptos", "Base", "IVA", "IRPF %", "Importe",
        "B Exenta", "Total", "Alertas",
    ]
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    docx_path = output_dir / f"ocr_resultado_{ts}.docx"

    if not _HAS_DOCX:
        # Fallback: escribir texto plano en .docx usando texto
        try:
            import pandas as pd
            df = pd.DataFrame([{c: row.get(c, "") for c in COLS} for row in rows], columns=COLS)
            docx_path_txt = output_dir / f"ocr_resultado_{ts}.txt"
            df.to_string(buf=open(str(docx_path_txt), "w", encoding="utf-8"), index=False)
            raise RuntimeError(
                "python-docx no está instalado. Instala con: pip install python-docx\n"
                f"Se guardó como texto plano en: {docx_path_txt}"
            )
        except RuntimeError:
            raise

    doc = Document()
    doc.add_heading("Resultado OCR — Facturas extraidas", level=1)

    table = doc.add_table(rows=1 + len(rows), cols=len(COLS))
    table.style = "Table Grid"

    # Cabecera
    hdr_cells = table.rows[0].cells
    for i, col in enumerate(COLS):
        hdr_cells[i].text = col
        run = hdr_cells[i].paragraphs[0].runs[0]
        run.bold = True
        run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        from docx.oxml.ns import qn
        from docx.oxml import OxmlElement
        tc = hdr_cells[i]._tc
        tcPr = tc.get_or_add_tcPr()
        shd = OxmlElement("w:shd")
        shd.set(qn("w:fill"), "1F4E79")
        shd.set(qn("w:color"), "auto")
        shd.set(qn("w:val"), "clear")
        tcPr.append(shd)

    # Filas de datos
    for r_idx, row in enumerate(rows):
        row_cells = table.rows[r_idx + 1].cells
        has_alert = bool(str(row.get("Alertas") or "").strip())
        for i, col in enumerate(COLS):
            row_cells[i].text = str(row.get(col, "") or "")
            if has_alert:
                from docx.oxml.ns import qn
                from docx.oxml import OxmlElement
                tc = row_cells[i]._tc
                tcPr = tc.get_or_add_tcPr()
                shd = OxmlElement("w:shd")
                shd.set(qn("w:fill"), "FFCCCC")
                shd.set(qn("w:color"), "auto")
                shd.set(qn("w:val"), "clear")
                tcPr.append(shd)

    doc.save(str(docx_path))
    return docx_path


def _read_input_file(filepath: Path) -> str:
    """Lee cualquier formato de entrada y devuelve su contenido como texto."""
    ext = filepath.suffix.lower()
    if ext in (".md", ".txt", ".json"):
        return filepath.read_text(encoding="utf-8", errors="replace")
    elif ext in (".xlsx", ".xls"):
        try:
            import pandas as pd
            df = pd.read_excel(str(filepath), dtype=str)
            return df.to_markdown(index=False) if hasattr(df, "to_markdown") else df.to_csv(sep=";", index=False)
        except Exception as exc:
            raise RuntimeError(f"No se pudo leer Excel: {exc}") from exc
    elif ext == ".csv":
        try:
            import pandas as pd
            # Intentar detectar separador
            raw = filepath.read_text(encoding="utf-8", errors="replace")
            sep = ";" if raw.count(";") > raw.count(",") else ","
            df = pd.read_csv(str(filepath), sep=sep, dtype=str)
            return df.to_markdown(index=False) if hasattr(df, "to_markdown") else df.to_csv(sep=";", index=False)
        except Exception as exc:
            raise RuntimeError(f"No se pudo leer CSV: {exc}") from exc
    elif ext in (".docx", ".doc"):
        try:
            from docx import Document as _Doc
            doc = _Doc(str(filepath))
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            # Incluir texto de tablas
            for table in doc.tables:
                for row in table.rows:
                    paragraphs.append(" | ".join(c.text.strip() for c in row.cells))
            return "\n".join(paragraphs)
        except Exception as exc:
            raise RuntimeError(f"No se pudo leer Word: {exc}") from exc
    else:
        return filepath.read_text(encoding="utf-8", errors="replace")


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  Panel principal                                                          ║
# ╚══════════════════════════════════════════════════════════════════════════╝
class MdToExcelPanel(QFrame):
    """
    Pestaña '📊 MD → Excel'.

    Atributos externos que main_window puede rellenar antes de que el usuario
    pulse "Convertir":
        set_ai_credentials(provider, api_key, model, base_url)
    """

    # ── señales ──────────────────────────────────────────────────────────────
    conversion_finished = pyqtSignal(str)   # ruta xlsx

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("mdToExcelPanel")

        self._files: list[Path] = []
        self._thread: QThread | None = None
        self._worker: _ConversionWorker | None = None

        # Credenciales de IA (se rellenan desde main_window)
        self._provider  = ""
        self._api_key   = ""
        self._model     = ""
        self._base_url  = ""

        self._build_ui()

    # ── API pública ──────────────────────────────────────────────────────────
    def set_ai_credentials(
        self,
        provider: str,
        api_key: str,
        model: str = "",
        base_url: str = "",
    ) -> None:
        """Rellenar credenciales de IA desde el panel de credenciales principal."""
        self._provider = provider or ""
        self._api_key  = api_key or ""
        self._model    = model or ""
        self._base_url = base_url or ""
        # Seleccionar en el ComboBox la opción más parecida al proveedor recibido
        prov_lower = (provider or "").lower().strip()
        best_idx = 0
        for i in range(self._provider_cb.count()):
            opt = self._provider_cb.itemText(i).lower()
            # coincidencia exacta o por inicio
            if opt == prov_lower or opt.startswith(prov_lower) or prov_lower.startswith(opt.split()[0]):
                best_idx = i
                break
        self._provider_cb.setCurrentIndex(best_idx)
        self._key_edit.setText(self._api_key)
        self._model_edit.setText(self._model)

    # ── construcción de la UI ─────────────────────────────────────────────────
    def _build_ui(self) -> None:
        root_lay = QVBoxLayout(self)
        root_lay.setContentsMargins(12, 12, 12, 12)
        root_lay.setSpacing(10)

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setHandleWidth(6)

        # ── bloque superior: configuración ────────────────────────────────────
        top_widget = QWidget()
        top_lay = QVBoxLayout(top_widget)
        top_lay.setContentsMargins(0, 0, 0, 0)
        top_lay.setSpacing(8)

        # — título ——
        title = QLabel("📊  Convertir archivos a Excel / CSV / Word con IA")
        title.setStyleSheet("font-size:15px; font-weight:bold; color:#1F4E79;")
        top_lay.addWidget(title)

        desc = QLabel(
            "Selecciona la carpeta con archivos del OCR o datos existentes. "
            "La IA los estructurará según el prompt y generará el archivo de salida elegido."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color:#555;")
        top_lay.addWidget(desc)

        # Recuadro explicativo del flujo
        flow_lbl = QLabel(
            "<b>📝 .md / .txt / .json</b>  →  IA extrae JSON  →  Excel / CSV / Word<br>"
            "<b>📈 .xlsx / .xls / .csv</b>  →  IA reestructura según el prompt  →  Excel / CSV / Word<br>"
            "<b>📘 .docx / .doc</b>  →  IA extrae datos del texto  →  Excel / CSV / Word"
        )
        flow_lbl.setWordWrap(True)
        flow_lbl.setStyleSheet(
            "background:#EEF4FB; border:1px solid #AECDE8; border-radius:6px;"
            "padding:6px 10px; color:#1F4E79; font-size:11px;"
        )
        top_lay.addWidget(flow_lbl)

        # — carpeta de entrada ——
        in_grp = QGroupBox("📁  Archivos de entrada (.md, .json, .txt, .xlsx, .csv, .docx)")
        in_lay = QVBoxLayout(in_grp)
        in_lay.setSpacing(6)

        folder_row = QWidget()
        fr_lay = QHBoxLayout(folder_row)
        fr_lay.setContentsMargins(0, 0, 0, 0)
        fr_lay.setSpacing(6)
        self._folder_edit = QLineEdit()
        self._folder_edit.setPlaceholderText("Ruta de la carpeta con archivos .md / .json…")
        self._folder_edit.setReadOnly(True)
        self._browse_btn = QPushButton("📂  Examinar…")
        self._browse_btn.setFixedWidth(120)
        self._browse_btn.clicked.connect(self._browse_input_folder)
        fr_lay.addWidget(self._folder_edit)
        fr_lay.addWidget(self._browse_btn)
        in_lay.addWidget(folder_row)

        self._file_list = _DropListWidget(self)
        self._file_list.setFixedHeight(110)
        self._file_list.setToolTip(
            "Archivos .md / .json encontrados en la carpeta.\n"
            "También puedes arrastrar archivos o carpetas aquí directamente."
        )
        self._file_list.files_dropped.connect(self._on_files_dropped)
        in_lay.addWidget(self._file_list)

        # Fila de acciones de lista
        list_btn_row = QWidget()
        lbr_lay = QHBoxLayout(list_btn_row)
        lbr_lay.setContentsMargins(0, 0, 0, 0)
        lbr_lay.setSpacing(6)
        self._files_count_lbl = QLabel("0 archivos")
        self._files_count_lbl.setStyleSheet("color:#555; font-size:11px;")
        lbr_lay.addWidget(self._files_count_lbl)
        lbr_lay.addStretch()
        _clear_btn = QPushButton("🗑  Limpiar lista")
        _clear_btn.setFixedHeight(26)
        _clear_btn.setToolTip("Eliminar todos los archivos de la cola")
        _clear_btn.clicked.connect(self._clear_file_list)
        lbr_lay.addWidget(_clear_btn)
        in_lay.addWidget(list_btn_row)

        top_lay.addWidget(in_grp)

        # — carpeta de salida + formato ——
        out_grp = QGroupBox("📁  Carpeta de salida y formato")
        out_vlay = QVBoxLayout(out_grp)
        out_vlay.setContentsMargins(6, 6, 6, 6)
        out_vlay.setSpacing(6)

        # Fila 1: carpeta
        out_row1 = QWidget(); or1l = QHBoxLayout(out_row1); or1l.setContentsMargins(0,0,0,0); or1l.setSpacing(6)
        or1l.addWidget(QLabel("Carpeta:"))
        self._output_edit = QLineEdit()
        self._output_edit.setPlaceholderText("Dejar vacío para guardar en la misma carpeta de entrada…")
        self._out_browse_btn = QPushButton("📂  Examinar…")
        self._out_browse_btn.setFixedWidth(120)
        self._out_browse_btn.clicked.connect(self._browse_output_folder)
        or1l.addWidget(self._output_edit)
        or1l.addWidget(self._out_browse_btn)
        out_vlay.addWidget(out_row1)

        # Fila 2: formato de salida
        out_row2 = QWidget(); or2l = QHBoxLayout(out_row2); or2l.setContentsMargins(0,0,0,0); or2l.setSpacing(6)
        lbl_fmt = QLabel("Formato:")
        lbl_fmt.setFixedWidth(60)
        or2l.addWidget(lbl_fmt)
        self._format_cb = QComboBox()
        for _label, _ext in _OUTPUT_FORMATS:
            self._format_cb.addItem(_label, _ext)
        self._format_cb.setToolTip("Elige el formato del archivo de salida generado por la IA")
        self._format_cb.currentIndexChanged.connect(self._on_format_changed)
        or2l.addWidget(self._format_cb)
        or2l.addStretch()
        _fmt_note = QLabel("Word requiere: <b>pip install python-docx</b>")
        _fmt_note.setStyleSheet("color:#888; font-size:10px;")
        or2l.addWidget(_fmt_note)
        out_vlay.addWidget(out_row2)

        top_lay.addWidget(out_grp)

        # — credenciales IA ——
        ai_grp = QGroupBox("🤖  Proveedor de IA")
        ai_grid_lay = QVBoxLayout(ai_grp)
        ai_grid_lay.setSpacing(4)

        row1 = QWidget(); r1l = QHBoxLayout(row1); r1l.setContentsMargins(0,0,0,0); r1l.setSpacing(6)
        lbl_prov = QLabel("Proveedor:")
        lbl_prov.setFixedWidth(72)
        r1l.addWidget(lbl_prov)
        self._provider_cb = QComboBox()
        self._provider_cb.addItems(_PROVIDER_OPTIONS)
        self._provider_cb.setToolTip("Selecciona el proveedor de IA que usará la estructuración")
        r1l.addWidget(self._provider_cb)
        ai_grid_lay.addWidget(row1)

        row2 = QWidget(); r2l = QHBoxLayout(row2); r2l.setContentsMargins(0,0,0,0); r2l.setSpacing(6)
        lbl_key = QLabel("API Key:")
        lbl_key.setFixedWidth(72)
        r2l.addWidget(lbl_key)
        self._key_edit = QLineEdit()
        self._key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._key_edit.setPlaceholderText("sk-…  (se sincroniza automáticamente desde Credenciales IA)")
        r2l.addWidget(self._key_edit)
        ai_grid_lay.addWidget(row2)

        row3 = QWidget(); r3l = QHBoxLayout(row3); r3l.setContentsMargins(0,0,0,0); r3l.setSpacing(6)
        lbl_mod = QLabel("Modelo:")
        lbl_mod.setFixedWidth(72)
        r3l.addWidget(lbl_mod)
        self._model_edit = QLineEdit()
        self._model_edit.setPlaceholderText("deepseek-v4-flash / gpt-4o / gemini-2.0-flash … (dejar vacío para usar el predeterminado)")
        r3l.addWidget(self._model_edit)
        ai_grid_lay.addWidget(row3)

        top_lay.addWidget(ai_grp)
        splitter.addWidget(top_widget)

        # ── bloque inferior: prompt + log ─────────────────────────────────────
        bot_widget = QWidget()
        bot_lay = QVBoxLayout(bot_widget)
        bot_lay.setContentsMargins(0, 0, 0, 0)
        bot_lay.setSpacing(8)

        # — prompt ——
        prompt_grp = QGroupBox("Prompt de extracción (esquema JSON)")
        p_lay = QVBoxLayout(prompt_grp)
        self._prompt_edit = QPlainTextEdit()
        self._prompt_edit.setPlainText(_DEFAULT_PROMPT)
        self._prompt_edit.setMinimumHeight(120)
        self._prompt_edit.setFont(QFont("Courier New", 9))
        p_lay.addWidget(self._prompt_edit)

        reset_btn = QPushButton("↺  Restaurar prompt por defecto")
        reset_btn.setFixedWidth(220)
        reset_btn.clicked.connect(lambda: self._prompt_edit.setPlainText(_DEFAULT_PROMPT))
        p_lay.addWidget(reset_btn, alignment=Qt.AlignmentFlag.AlignRight)

        bot_lay.addWidget(prompt_grp)

        # — botones de acción ——
        btn_row = QWidget()
        btn_lay = QHBoxLayout(btn_row)
        btn_lay.setContentsMargins(0, 0, 0, 0)
        btn_lay.setSpacing(10)

        self._convert_btn = QPushButton("▶   Convertir a Excel")
        self._convert_btn.setObjectName("startBtn")
        self._convert_btn.setFixedHeight(40)
        self._convert_btn.setEnabled(False)
        self._convert_btn.clicked.connect(self._start_conversion)

        self._stop_btn = QPushButton("⏹  Detener")
        self._stop_btn.setFixedHeight(40)
        self._stop_btn.setEnabled(False)
        self._stop_btn.clicked.connect(self._stop_conversion)

        self._open_btn = QPushButton("📂  Abrir Excel")
        self._open_btn.setFixedHeight(40)
        self._open_btn.setEnabled(False)
        self._open_btn.clicked.connect(self._open_output)

        btn_lay.addWidget(self._convert_btn)
        btn_lay.addWidget(self._stop_btn)
        btn_lay.addStretch()
        btn_lay.addWidget(self._open_btn)
        bot_lay.addWidget(btn_row)

        # — barra de progreso ——
        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setFormat("%v / %m archivos")
        bot_lay.addWidget(self._progress)

        # — log ——
        log_grp = QGroupBox("Registro de conversión")
        lg_lay = QVBoxLayout(log_grp)
        self._log_edit = QTextEdit()
        self._log_edit.setReadOnly(True)
        self._log_edit.setFont(QFont("Courier New", 9))
        self._log_edit.setMinimumHeight(100)
        lg_lay.addWidget(self._log_edit)
        bot_lay.addWidget(log_grp)

        splitter.addWidget(bot_widget)
        splitter.setSizes([420, 500])

        root_lay.addWidget(splitter)

        # Estado
        self._last_xlsx: str = ""

    # ── interacción de carpetas ──────────────────────────────────────────────
    def _browse_input_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Seleccionar carpeta con archivos MD / JSON", ""
        )
        if not folder:
            return
        self._folder_edit.setText(folder)
        self._scan_folder(Path(folder))

    def _scan_folder(self, folder: Path) -> None:
        found = sorted(
            [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in _ACCEPTED_EXTS],
            key=lambda p: p.name.lower(),
        )
        self._add_files(found, clear=True, source_folder=folder)

    def _on_files_dropped(self, paths: list[str]) -> None:
        """Recibe rutas soltadas por drag&drop (archivos o carpetas)."""
        new_files: list[Path] = []
        for raw in paths:
            p = Path(raw)
            if p.is_dir():
                new_files.extend(
                    sorted(
                        [f for f in p.iterdir() if f.is_file() and f.suffix.lower() in _ACCEPTED_EXTS],
                        key=lambda x: x.name.lower(),
                    )
                )
            elif p.is_file() and p.suffix.lower() in _ACCEPTED_EXTS:
                new_files.append(p)
        if not new_files:
            self._log("⚠  Ningún archivo .md / .json / .txt en el contenido arrastrado.")
            return
        self._add_files(new_files, clear=False)

    def _add_files(self, new_files: list[Path], *, clear: bool = False, source_folder: Path | None = None) -> None:
        """Añade (o reemplaza) archivos en la lista y en self._files."""
        if clear:
            self._files = []
            self._file_list.clear()
        # Evitar duplicados
        existing = {f for f in self._files}
        for f in new_files:
            if f not in existing:
                self._files.append(f)
                existing.add(f)
                icon = _EXT_ICON.get(f.suffix.lower(), "📄")
                tipo = _EXT_TIPO.get(f.suffix.lower(), "Archivo")
                item = QListWidgetItem(f"{icon}  {f.name}  [{tipo}]")
                item.setToolTip(f"Ruta: {f}\nTipo: {tipo}")
                self._file_list.addItem(item)
        n = len(self._files)
        self._files_count_lbl.setText(f"{n} archivo{'s' if n != 1 else ''}")
        if n == 0:
            item = QListWidgetItem("⚠  No se encontraron archivos compatibles en esta carpeta")
            item.setForeground(QColor("#cc6600"))
            self._file_list.addItem(item)
            self._convert_btn.setEnabled(False)
        else:
            src_txt = f" en {source_folder}" if source_folder else ""
            self._log(f"✅  {n} archivo(s) en cola{src_txt}")
            self._convert_btn.setEnabled(True)

    def _clear_file_list(self) -> None:
        """Vacía la cola de archivos."""
        self._files = []
        self._file_list.clear()
        self._files_count_lbl.setText("0 archivos")
        self._convert_btn.setEnabled(False)
        self._log("🗑  Lista de archivos borrada.")

    def _on_format_changed(self, _idx: int) -> None:
        """Actualiza el texto del botón Convertir según el formato elegido."""
        label = self._format_cb.currentText()  # p.ej. "Excel (.xlsx)"
        fmt_short = label.split("(")[0].strip()  # "Excel", "CSV", "Word"
        self._convert_btn.setText(f"▶   Convertir a {fmt_short}")

    def _browse_output_folder(self) -> None:
        label = self._format_cb.currentText() if hasattr(self, '_format_cb') else "archivo"
        folder = QFileDialog.getExistingDirectory(
            self, f"Seleccionar carpeta de salida ({label})", ""
        )
        if folder:
            self._output_edit.setText(folder)

    # ── conversión ──────────────────────────────────────────────────────────
    def _start_conversion(self) -> None:
        if not self._files:
            QMessageBox.warning(self, "Sin archivos", "Selecciona una carpeta con archivos .md o .json primero.")
            return

        # Leer credenciales del panel (prioridad) o de los campos almacenados
        provider  = self._provider_cb.currentText().strip() or self._provider
        api_key   = self._key_edit.text().strip()           or self._api_key
        model     = self._model_edit.text().strip()         or self._model
        base_url  = self._base_url

        if not provider:
            QMessageBox.warning(
                self,
                "Proveedor de IA requerido",
                "Introduce el proveedor de IA (p.ej. 'DeepSeek') en el campo Proveedor.\n"
                "También puedes configurarlo en la pestaña 'Credenciales IA' y se sincronizará automáticamente.",
            )
            return

        if not api_key:
            ret = QMessageBox.question(
                self,
                "Sin API Key",
                "No se ha introducido una API Key.\n"
                "Si el proveedor lo requiere (p.ej. DeepSeek, OpenAI), la conversión fallará.\n\n"
                "¿Continuar de todas formas?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if ret != QMessageBox.StandardButton.Yes:
                return

        prompt = self._prompt_edit.toPlainText().strip()
        if not prompt:
            QMessageBox.warning(self, "Prompt vacío", "El prompt de extracción no puede estar vacío.")
            return

        # Carpeta de salida
        out_str = self._output_edit.text().strip()
        if out_str:
            output_dir = Path(out_str)
        else:
            # Usar la misma carpeta que la de entrada
            input_folder = self._folder_edit.text().strip()
            output_dir = Path(input_folder) if input_folder else Path.cwd()

        # Formato de salida
        output_format = self._format_cb.currentData() or ".xlsx"  # ".xlsx" / ".csv" / ".docx"

        self._last_xlsx = ""
        self._log_edit.clear()
        fmt_name = self._format_cb.currentText().split("(")[0].strip()
        self._log(f"▶  Iniciando conversión de {len(self._files)} archivo(s) → {fmt_name}…")
        self._log(f"   Proveedor: {provider}  |  Modelo: {model or '(predeterminado)'}")
        self._log(f"   Salida: {output_dir}")

        # Configurar barra
        self._progress.setRange(0, len(self._files))
        self._progress.setValue(0)
        self._progress.setFormat(f"%v / {len(self._files)} archivos")

        # Botones
        self._convert_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)
        self._open_btn.setEnabled(False)

        # Hilo
        self._thread = QThread()
        self._worker = _ConversionWorker(
            files=list(self._files),
            prompt=prompt,
            output_dir=output_dir,
            provider=provider,
            api_key=api_key,
            model=model,
            base_url=base_url,
            output_format=output_format,
        )
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.file_done.connect(self._on_file_done)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.finished.connect(self._thread.quit)
        self._worker.error.connect(self._thread.quit)
        self._thread.finished.connect(self._on_thread_done)
        self._thread.start()

    def _stop_conversion(self) -> None:
        if self._worker:
            self._worker.stop()
        self._log("⏹  Conversión interrumpida por el usuario.")
        self._stop_btn.setEnabled(False)

    # ── slots de señales del worker ──────────────────────────────────────────
    def _on_progress(self, done: int, total: int, msg: str) -> None:
        self._progress.setValue(done)
        if msg:
            self._log(f"   [{done}/{total}] {msg}")

    def _on_file_done(self, nombre: str, ok: bool, msg: str) -> None:
        icon = "✅" if ok else "❌"
        self._log(f"{icon}  {nombre}: {msg}")
        # Colorear item en la lista
        for i in range(self._file_list.count()):
            item = self._file_list.item(i)
            if item and nombre in (item.text() or ""):
                item.setForeground(QColor("#27ae60") if ok else QColor("#c0392b"))
                break

    def _on_finished(self, xlsx_path: str) -> None:
        if xlsx_path:
            self._last_xlsx = xlsx_path
            self._log(f"\n🎉  Excel generado correctamente:\n   {xlsx_path}")
            self.conversion_finished.emit(xlsx_path)
            self._open_btn.setEnabled(True)
        else:
            self._log("⚠  Conversión completada pero no se generó ninguna fila. Revisa los logs.")

    def _on_error(self, msg: str) -> None:
        self._log(f"🔴  ERROR FATAL: {msg}")
        QMessageBox.critical(self, "Error en conversión", msg)

    def _on_thread_done(self) -> None:
        self._progress.setValue(self._progress.maximum())
        self._convert_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)

    # ── abrir archivo de salida ──────────────────────────────────────────────
    def _open_output(self) -> None:
        if not self._last_xlsx or not Path(self._last_xlsx).exists():
            QMessageBox.warning(self, "Archivo no encontrado", "El archivo Excel no está disponible.")
            return
        try:
            import subprocess
            subprocess.Popen(["explorer", "/select,", os.path.abspath(self._last_xlsx)])
        except Exception:
            try:
                os.startfile(os.path.abspath(self._last_xlsx))  # Windows
            except Exception as exc:
                QMessageBox.information(self, "Ruta del Excel", self._last_xlsx)

    # ── log interno ──────────────────────────────────────────────────────────
    def _log(self, msg: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self._log_edit.append(f"[{ts}] {msg}")
        # Auto-scroll al final
        sb = self._log_edit.verticalScrollBar()
        if sb:
            sb.setValue(sb.maximum())

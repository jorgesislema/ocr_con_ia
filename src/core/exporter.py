"""Exporta los resultados OCR a XLSX, CSV o DOCX."""
from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _try_parse_json(text: str) -> dict | None:
    """Si el texto es un objeto JSON válido, lo devuelve; si no, None."""
    stripped = text.strip()
    if not (stripped.startswith("{") and stripped.endswith("}")):
        return None
    try:
        parsed = json.loads(stripped)
        return parsed if isinstance(parsed, dict) else None
    except (json.JSONDecodeError, ValueError):
        return None


def _flatten_results(results: list[dict]) -> tuple[list[dict], bool]:
    """Intenta parsear el campo 'text' de cada doc como JSON y aplanar.

    Devuelve (filas_aplanadas, es_json). Si algún doc tiene JSON,
    todos se fusionan via json_normalize; si no, se usa el esquema plano original.
    """
    import pandas as pd

    parsed_rows = []
    all_json = True
    for doc in results:
        obj = _try_parse_json(doc.get("text", ""))
        if obj is None:
            all_json = False
            break
        meta = {
            "id":         doc["id"],
            "archivo":    doc["filename"],
            "paginas":    doc["pages"],
            "confianza":  round(doc["confidence"] * 100, 1),
            "estado":     doc["status"],
        }
        merged = {**meta, **obj}
        parsed_rows.append(merged)

    if all_json and parsed_rows:
        df = pd.json_normalize(parsed_rows)
        # Convertir columnas numéricas de string a float
        for col in df.columns:
            try:
                df[col] = pd.to_numeric(df[col])
            except (ValueError, TypeError):
                pass
        return df.to_dict(orient="records"), True

    # Fallback: esquema fijo original
    flat = [
        {
            "ID":             doc["id"],
            "Archivo":        doc["filename"],
            "Páginas":        doc["pages"],
            "Confianza (%)":  round(doc["confidence"] * 100, 1),
            "Estado":         doc["status"],
            "Texto Extraído": doc["text"],
        }
        for doc in results
    ]
    return flat, False


def export_results(
    results: list[dict],
    output_dir: str,
    fmt: str,
    merge: bool = True,
    include_images: bool = True,
    expected_keys: list[str] | None = None,
    export_profile: str | None = None,
    vendor_master_path: str | None = None,
    structuring_provider: str | None = None,
    structuring_api_key: str | None = None,
    structuring_model: str | None = None,
    structuring_base_url: str | None = None,
    prompt_template: str | None = None,
) -> list[str]:
    """Escribe los resultados en el formato indicado.

    Parameters
    ----------
    results:       lista de dicts con claves id, filename, pages, confidence, text
    output_dir:    carpeta de destino (se crea si no existe)
    fmt:           "XLSX", "CSV" o "DOCX"
    merge:         si True, un único archivo para todos; si False, uno por documento
    include_images: incrustar imágenes en DOCX
    expected_keys: si se proporciona, solo se exportan esas columnas del JSON

    Returns
    -------
    Lista de rutas de archivos generados.
    """
    # Delegar implementación segura a src.data.exporters
    from src.data.exporters import export_results as _impl

    return _impl(
        results, output_dir, fmt, merge,
        include_images=include_images,
        expected_keys=expected_keys,
        export_profile=export_profile,
        vendor_master_path=vendor_master_path,
        structuring_provider=structuring_provider,
        structuring_api_key=structuring_api_key,
        structuring_model=structuring_model,
        structuring_base_url=structuring_base_url,
        prompt_template=prompt_template,
    )


# ── XLSX ──────────────────────────────────────────────────────────────────────

def _export_xlsx(results: list[dict], out: Path, merge: bool) -> list[str]:
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment

    HEADER_FILL = PatternFill("solid", fgColor="12121C")
    HEADER_FONT = Font(bold=True, color="6B7280")

    def _write_wb(rows: list[dict], path: Path) -> None:
        flat_rows, is_json = _flatten_results(rows)
        if not flat_rows:
            return
        headers = list(flat_rows[0].keys())

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Resultados OCR"

        for col, h in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col, value=str(h).replace("_", " ").title())
            cell.font = HEADER_FONT
            cell.fill = HEADER_FILL
            cell.alignment = Alignment(horizontal="center")

        for r, doc in enumerate(flat_rows, 2):
            for col, key in enumerate(headers, 1):
                val = doc.get(key, "")
                cell = ws.cell(r, col)
                # Escribir numéricos como float, no como texto
                if isinstance(val, (int, float)):
                    cell.value = float(val)
                else:
                    cell.value = val
                    if key in ("texto_extraido", "Texto Extraído", "text"):
                        cell.alignment = Alignment(wrap_text=True)

        # Ajuste de ancho por tipo de columna
        for col_idx, key in enumerate(headers, 1):
            col_letter = ws.cell(1, col_idx).column_letter
            if key.lower() in ("archivo", "filename", "emisor"):
                ws.column_dimensions[col_letter].width = 30
            elif key.lower() in ("texto_extraido", "texto extraído", "text"):
                ws.column_dimensions[col_letter].width = 60
            else:
                ws.column_dimensions[col_letter].width = 18
        wb.save(path)

    if merge:
        path = out / f"ocr_resultados_{_timestamp()}.xlsx"
        _write_wb(results, path)
        return [str(path)]
    paths = []
    for doc in results:
        p = out / f"{Path(doc['filename']).stem}_{_timestamp()}.xlsx"
        _write_wb([doc], p)
        paths.append(str(p))
    return paths


# ── CSV ───────────────────────────────────────────────────────────────────────

def _export_csv(results: list[dict], out: Path, merge: bool) -> list[str]:

    def _write_csv(rows: list[dict], path: Path) -> None:
        flat_rows, _ = _flatten_results(rows)
        if not flat_rows:
            return
        headers = list(flat_rows[0].keys())
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=headers)
            w.writeheader()
            w.writerows(flat_rows)

    if merge:
        path = out / f"ocr_resultados_{_timestamp()}.csv"
        _write_csv(results, path)
        return [str(path)]
    paths = []
    for doc in results:
        p = out / f"{Path(doc['filename']).stem}_{_timestamp()}.csv"
        _write_csv([doc], p)
        paths.append(str(p))
    return paths


# ── DOCX ──────────────────────────────────────────────────────────────────────

def _export_docx(results: list[dict], out: Path, merge: bool) -> list[str]:
    from docx import Document
    from docx.shared import Pt, RGBColor

    def _write_doc(rows: list[dict], path: Path) -> None:
        doc = Document()
        doc.add_heading("Resultados OCR — GLM-4V", level=0)
        for entry in rows:
            doc.add_heading(f"Documento #{entry['id']}: {entry['filename']}", level=1)
            meta = doc.add_paragraph()
            meta.add_run(
                f"Páginas: {entry['pages']}  |  "
                f"Confianza: {round(entry['confidence'] * 100, 1)}%  |  "
                f"Estado: {entry['status']}"
            ).font.color.rgb = RGBColor(0x6B, 0x72, 0x80)
            doc.add_paragraph(entry["text"])
            doc.add_paragraph()   # separador
        doc.save(path)

    if merge:
        path = out / f"ocr_resultados_{_timestamp()}.docx"
        _write_doc(results, path)
        return [str(path)]
    paths = []
    for entry in results:
        p = out / f"{Path(entry['filename']).stem}_{_timestamp()}.docx"
        _write_doc([entry], p)
        paths.append(str(p))
    return paths

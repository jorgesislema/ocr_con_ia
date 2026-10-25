"""Servicio de exportación del documento canónico a Excel / CSV / Word / PDF.

Parte del contrato del SaaS: el usuario revisa (paso 3 del flujo UI) y
exporta (paso 4). La exportación SIEMPRE parte del ``InvoiceSchema``
final (con correcciones humanas si las hubo), nunca del texto crudo.
"""
from __future__ import annotations

import csv
import io
from decimal import Decimal
from pathlib import Path

from app.core.schemas.invoice import InvoiceSchema

Money = Decimal


def _money(value: Decimal | None) -> float:
    """Decimal → float para las librerías de ofimática."""
    return float(value) if value is not None else 0.0


# ═══════════════════════════════════════════════════════════════════════════
#  Excel (openpyxl) — hoja "Factura" + hoja "Detalle"
# ═══════════════════════════════════════════════════════════════════════════

def _export_xlsx(inv: InvoiceSchema) -> bytes:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Factura"

    header_rows = [
        ("Número", inv.invoice_number),
        ("Fecha emisión", str(inv.issue_date) if inv.issue_date else None),
        ("Fecha vencimiento", str(inv.due_date) if inv.due_date else None),
        ("Moneda", inv.currency),
        ("Emisor", inv.supplier.name if inv.supplier else None),
        ("NIF/RUC emisor", inv.supplier.tax_id if inv.supplier else None),
        ("Receptor", inv.customer.name if inv.customer else None),
        ("NIF/RUC receptor", inv.customer.tax_id if inv.customer else None),
        ("Subtotal", _money(inv.subtotal)),
        ("Descuentos", _money(inv.discounts_total())),
        ("Impuestos", _money(inv.taxes_total())),
        ("TOTAL", _money(inv.total)),
    ]
    for row in header_rows:
        ws.append(row)
    # Negrita en el TOTAL
    ws.cell(row=len(header_rows), column=2).font = ws.cell(
        row=len(header_rows), column=1
    ).font.copy(bold=True)

    # Hoja de líneas de detalle
    det = wb.create_sheet("Detalle")
    det.append(["Descripción", "Cantidad", "Precio unitario", "Tasa imp.", "Subtotal", "Página"])
    for li in inv.line_items:
        det.append([
            li.description, _money(li.quantity), _money(li.unit_price),
            _money(li.tax_rate), _money(li.subtotal), li.page,
        ])

    # Hoja de impuestos (array multi-impuesto LatAm/VAT)
    taxes = wb.create_sheet("Impuestos")
    taxes.append(["Tipo", "Tasa %", "Base", "Importe"])
    for t in inv.taxes:
        taxes.append([t.type, _money(t.rate), _money(t.base_amount), _money(t.amount)])

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


# ═══════════════════════════════════════════════════════════════════════════
#  CSV — plano, ideal para importación ERP
# ═══════════════════════════════════════════════════════════════════════════

def _export_csv(inv: InvoiceSchema) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["campo", "valor"])
    writer.writerow(["invoice_number", inv.invoice_number or ""])
    writer.writerow(["issue_date", inv.issue_date or ""])
    writer.writerow(["currency", inv.currency or ""])
    writer.writerow(["supplier", inv.supplier.name if inv.supplier else ""])
    writer.writerow(["supplier_tax_id", inv.supplier.tax_id if inv.supplier else ""])
    writer.writerow(["customer", inv.customer.name if inv.customer else ""])
    writer.writerow(["subtotal", str(inv.subtotal)])
    writer.writerow(["discounts_total", str(inv.discounts_total())])
    writer.writerow(["taxes_total", str(inv.taxes_total())])
    writer.writerow(["total", str(inv.total)])
    writer.writerow([])  # separador
    writer.writerow(["descripcion", "cantidad", "precio_unitario", "tasa_imp", "subtotal", "pagina"])
    for li in inv.line_items:
        writer.writerow([
            li.description, str(li.quantity or ""), str(li.unit_price or ""),
            str(li.tax_rate or ""), str(li.subtotal or ""), li.page or "",
        ])
    return buffer.getvalue().encode("utf-8-sig")  # BOM para Excel en Windows


# ═══════════════════════════════════════════════════════════════════════════
#  Word (python-docx)
# ═══════════════════════════════════════════════════════════════════════════

def _export_docx(inv: InvoiceSchema) -> bytes:
    from docx import Document as DocxDocument
    from docx.shared import Pt

    doc = DocxDocument()
    title = doc.add_heading(f"Factura {inv.invoice_number or '—'}", level=1)
    title.alignment = 1  # centrado

    meta = doc.add_paragraph()
    meta.add_run(f"Fecha: {inv.issue_date or '—'}   Moneda: {inv.currency or '—'}\n").bold = False
    if inv.supplier:
        meta.add_run(f"Emisor: {inv.supplier.name} ({inv.supplier.tax_id or 's/NIF'})\n")
    if inv.customer:
        meta.add_run(f"Receptor: {inv.customer.name} ({inv.customer.tax_id or 's/NIF'})\n")

    # Tabla de líneas
    table = doc.add_table(rows=1, cols=5)
    table.style = "Light Grid Accent 1"
    heads = table.rows[0].cells
    for i, h in enumerate(["Descripción", "Cant.", "P.Unit", "Impuesto", "Subtotal"]):
        heads[i].text = h
        heads[i].paragraphs[0].runs[0].bold = True
    for li in inv.line_items:
        row = table.add_row().cells
        row[0].text = li.description or ""
        row[1].text = str(li.quantity or "")
        row[2].text = str(li.unit_price or "")
        row[3].text = f"{li.tax_rate}%" if li.tax_rate is not None else ""
        row[4].text = str(li.subtotal or "")

    # Totales
    totals = doc.add_paragraph()
    totals.add_run(f"\nSubtotal: {inv.subtotal} {inv.currency or ''}\n").bold = False
    for t in inv.taxes:
        totals.add_run(f"{t.type} {t.rate or ''}: {t.amount} {inv.currency or ''}\n")
    for d in inv.discounts:
        totals.add_run(f"Descuento ({d.concept or 'general'}): -{d.amount}\n")
    run = totals.add_run(f"TOTAL: {inv.total} {inv.currency or ''}")
    run.bold = True
    run.font.size = Pt(14)

    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


# ═══════════════════════════════════════════════════════════════════════════
#  PDF (reportlab)
# ═══════════════════════════════════════════════════════════════════════════

def _export_pdf(inv: InvoiceSchema) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buffer = io.BytesIO()
    pdf = SimpleDocTemplate(buffer, pagesize=A4, topMargin=1.5 * cm, bottomMargin=1.5 * cm)
    style_ok = {"fontName": "Helvetica"}
    story: list = []

    story.append(Paragraph(f"<b>Factura {inv.invoice_number or ''}</b>", style_ok))
    story.append(Paragraph(
        f"Fecha: {inv.issue_date or '—'} · Moneda: {inv.currency or '—'}", style_ok))
    if inv.supplier:
        story.append(Paragraph(f"Emisor: {inv.supplier.name} — {inv.supplier.tax_id or ''}", style_ok))
    if inv.customer:
        story.append(Paragraph(f"Receptor: {inv.customer.name} — {inv.customer.tax_id or ''}", style_ok))
    story.append(Spacer(1, 0.5 * cm))

    data = [["Descripción", "Cant.", "P.Unit", "Impuesto", "Subtotal"]]
    for li in inv.line_items:
        data.append([
            li.description or "", str(li.quantity or ""), str(li.unit_price or ""),
            f"{li.tax_rate}%" if li.tax_rate is not None else "", str(li.subtotal or ""),
        ])
    table = Table(data, colWidths=[7 * cm, 2 * cm, 2.5 * cm, 2 * cm, 2.5 * cm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2563EB")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#9CA3AF")),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
    ]))
    story.append(table)
    story.append(Spacer(1, 0.4 * cm))
    story.append(Paragraph(
        f"<b>Subtotal:</b> {inv.subtotal} · <b>Impuestos:</b> {inv.taxes_total()} · "
        f"<b>Descuentos:</b> {inv.discounts_total()} · "
        f"<b>TOTAL: {inv.total} {inv.currency or ''}</b>", style_ok))

    pdf.build(story)
    return buffer.getvalue()


# ═══════════════════════════════════════════════════════════════════════════
#  Dispatcher
# ═══════════════════════════════════════════════════════════════════════════

_EXPORTERS = {
    "xlsx": _export_xlsx,
    "csv": _export_csv,
    "docx": _export_docx,
    "pdf": _export_pdf,
}

MIME_TYPES = {
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "csv": "text/csv; charset=utf-8",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pdf": "application/pdf",
}


def export_invoice(inv: InvoiceSchema, fmt: str, output_dir: Path,
                   base_name: str) -> Path:
    """Exporta la factura canónica al formato pedido y devuelve la ruta.

    Args:
        inv: InvoiceSchema (ya validado y/o corregido por el humano).
        fmt: "xlsx" | "csv" | "docx" | "pdf".
        output_dir: directorio destino (settings.export_dir).
        base_name: nombre base sin extensión (p. ej. "{task_id}_factura").
    """
    fmt = fmt.lower()
    exporter = _EXPORTERS.get(fmt)
    if exporter is None:
        raise ValueError(f"Formato de exportación no soportado: '{fmt}'. "
                         f"Disponibles: {sorted(_EXPORTERS)}")
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"{base_name}.{fmt}"
    out_path.write_bytes(exporter(inv))
    return out_path

"""Convierte archivos Markdown (salida de Mistral OCR) directamente a XLSX.

Uso:
  python scripts/mistral_md_to_excel.py file1.md file2.md -o out.xlsx

El script intenta extraer: invoice number, date, proveedor, subtotales, impuestos,
total y la tabla de items en formato Markdown. Luego usa `export_invoices_to_excel`
para generar un XLSX con hojas Summary y Lines.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import List, Dict, Any

from src.core.excel_exporter import export_invoices_to_excel
try:
    from src.data.exporters import _maybe_structure_with_llm
except Exception:
    _maybe_structure_with_llm = None


def parse_markdown_invoice(text: str, src_name: str) -> Dict[str, Any]:
    # Normalizar saltos
    t = text.replace('\r\n', '\n').replace('\r', '\n')

    def find_regex(patterns, default=None):
        for p in patterns:
            m = re.search(p, t, flags=re.IGNORECASE)
            if m:
                return m.group(1).strip()
        return default

    invoice_no = find_regex([r'Invoice\s*No\s*[:\-]\s*(.+)', r'Invoice\s*Number\s*[:\-]\s*(.+)'])
    date = find_regex([r'Date\s*[:\-]\s*(.+)'])
    supplier = find_regex([r'^(?:#\s*)?(.+?)\n', r'^(?:#\s*)?(.+?)\n'], default="")

    subtotal = find_regex([r'Total\s+Exclude\s+GST\s*[:\-]\s*([0-9.,]+)', r'Subtotal\s*[:\-]\s*([0-9.,]+)'])
    tax = find_regex([r'Total\s+GST\s*@\s*\d+%\s*[:\-]\s*([0-9.,]+)', r'Tax\s*[:\-]\s*([0-9.,]+)'])
    total = find_regex([r'Total\s+Inclusive\s+GST\s*[:\-]\s*([0-9.,]+)', r'TOTAL\s*[:\-]\s*([0-9.,]+)', r'Total\s+Amount\s*[:\-]\s*([0-9.,]+)'])

    # Buscar tabla Markdown
    items: List[Dict[str, Any]] = []
    # localizar posibles bloques de tabla con encabezado que contenga Description y Qty
    table_blocks = re.findall(r'(^\|.*\|\s*$\n(?:^\|[-\s:|]+\|\s*$\n)(?:^\|.*\|\s*$\n)+)', t, flags=re.MULTILINE)
    for block in table_blocks:
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        if len(lines) < 2:
            continue
        header = [h.strip().lower() for h in re.split(r'\|', lines[0]) if h.strip()]
        # filas con datos
        for row in lines[2:]:
            cols = [c.strip() for c in re.split(r'\|', row) if True]
            # mapear por posición tolerante
            # buscar índices de columnas
            def col_value(key_names):
                for k in key_names:
                    if k in header:
                        idx = header.index(k)
                        if idx < len(cols):
                            return cols[idx]
                return ""

            description = col_value(["description", "descripcion", "item", "detalle"]) or cols[0] if cols else ""
            qty_s = col_value(["qty", "quantity", "cantidad"]) or "1"
            price_s = col_value(["price", "unit price", "precio"]) or col_value(["price", "precio", "unit_price"]) or "0"
            line_total_s = col_value(["amount", "total", "importe"]) or price_s
            # limpiar números
            def to_float(s):
                if s is None:
                    return None
                s2 = re.sub(r"[^0-9,.-]", "", str(s))
                s2 = s2.replace(',', '.')
                try:
                    return float(s2)
                except Exception:
                    return None

            qty = to_float(qty_s) or 1.0
            unit_price = to_float(price_s) or 0.0
            line_total = to_float(line_total_s) or (unit_price * qty)

            items.append({
                "origen": src_name,
                "descripcion": description,
                "cantidad": qty,
                "precio_unitario": unit_price,
                "subtotal": line_total,
                "total": line_total,
            })
        if items:
            break

    inv = {
        "invoice_id": invoice_no or Path(src_name).stem,
        "fecha": date,
        "proveedor": supplier,
        "moneda": "MYR",
        "subtotal": float(subtotal.replace(',', '.')) if subtotal else None,
        "iva": float(tax.replace(',', '.')) if tax else None,
        "total": float(total.replace(',', '.')) if total else None,
        "lines": items,
    }
    return inv


def main(argv: List[str]):
    if not argv:
        print("Uso: python scripts/mistral_md_to_excel.py file1.md [file2.md ...] -o out.xlsx")
        return 1
    args = argv[:]
    out_path = None
    use_ai = False
    provider = None
    api_key = None
    model = None
    base_url = None
    prompt_template = None
    if "-o" in args:
        i = args.index("-o")
        if i + 1 < len(args):
            out_path = args[i + 1]
            args = args[:i] + args[i + 2 :]
    if "--ai" in args:
        use_ai = True
        args = [a for a in args if a != "--ai"]
    if "--provider" in args:
        i = args.index("--provider")
        provider = args[i + 1]
        args = args[:i] + args[i + 2 :]
    if "--api-key" in args:
        i = args.index("--api-key")
        api_key = args[i + 1]
        args = args[:i] + args[i + 2 :]
    if "--model" in args:
        i = args.index("--model")
        model = args[i + 1]
        args = args[:i] + args[i + 2 :]
    if "--base-url" in args:
        i = args.index("--base-url")
        base_url = args[i + 1]
        args = args[:i] + args[i + 2 :]
    if "--prompt-file" in args:
        i = args.index("--prompt-file")
        pf = Path(args[i + 1])
        if pf.exists():
            prompt_template = pf.read_text(encoding="utf-8")
        args = args[:i] + args[i + 2 :]

    files = [Path(p) for p in args if not p.startswith("-")]
    if not files:
        print("No input files")
        return 1
    invoices = []
    for f in files:
        if not f.exists():
            print(f"Advertencia: {f} no existe, omitiendo")
            continue
        text = f.read_text(encoding="utf-8")
        if use_ai and _maybe_structure_with_llm is not None:
            # Construir prompt si no se proporcionó
            if not prompt_template:
                prompt_template = (
                    "Eres un extractor contable. Analiza el MARKDOWN y devuelve SOLO un objeto JSON "
                    "con las claves: excel_headers_table, excel_items_table, audit_alerts. "
                    "Usa fechas YYYY-MM-DD, floats con punto, moneda MYR. Devuelve únicamente JSON."
                )
            parsed = _maybe_structure_with_llm(
                text,
                expected_keys=None,
                structuring_provider=provider or "DeepSeek",
                structuring_api_key=api_key or None,
                structuring_model=model or "deepseek-v4-flash",
                structuring_base_url=base_url or "https://api.deepseek.com/v1",
                prompt_template=prompt_template,
            )
            # _maybe_structure_with_llm puede devolver dict con las tablas
            if isinstance(parsed, dict):
                # El LLM puede devolver las tablas dentro de excel_headers_table/excel_items_table,
                # o directamente los campos del header en la raíz. Normalizamos ambos casos.
                import json

                headers = parsed.get("excel_headers_table") or parsed.get("excel_headers")
                items = parsed.get("excel_items_table") or parsed.get("excel_items")

                # Si las tablas vienen como string JSON, parsearlas
                if isinstance(headers, str):
                    try:
                        headers = json.loads(headers)
                    except Exception:
                        headers = None
                if isinstance(items, str):
                    try:
                        items = json.loads(items)
                    except Exception:
                        items = None

                # Si el LLM devolvió directamente campos del header (no en lista)
                if not headers and any(k in parsed for k in ("invoice_number", "supplier_name", "subtotal_net", "total_gross")):
                    headers = [
                        {
                            "invoice_number": parsed.get("invoice_number"),
                            "invoice_date": parsed.get("invoice_date"),
                            "supplier_name": parsed.get("supplier_name"),
                            "supplier_tax_id": parsed.get("supplier_tax_id"),
                            "supplier_address": parsed.get("supplier_address"),
                            "subtotal_net": parsed.get("subtotal_net"),
                            "tax_amount": parsed.get("tax_amount"),
                            "tax_rate_percent": parsed.get("tax_rate_percent"),
                            "total_gross": parsed.get("total_gross"),
                            "payment_method": parsed.get("payment_method"),
                        }
                    ]

                # Normalizar headers a lista
                if isinstance(headers, dict):
                    headers = [headers]

                if headers and isinstance(headers, list) and len(headers) > 0:
                    h = headers[0]
                    inv = {
                        "invoice_id": h.get("invoice_number"),
                        "fecha": h.get("invoice_date"),
                        "proveedor": h.get("supplier_name"),
                        "moneda": "MYR",
                        "subtotal": h.get("subtotal_net"),
                        "iva": h.get("tax_amount"),
                        "total": h.get("total_gross"),
                        "lines": [],
                    }
                    if items and isinstance(items, list):
                        for it in items:
                            inv["lines"].append(
                                {
                                    "origen": f.name,
                                    "descripcion": it.get("item_description"),
                                    "cantidad": it.get("quantity"),
                                    "precio_unitario": it.get("unit_price"),
                                    "subtotal": it.get("line_total"),
                                    "total": it.get("line_total"),
                                }
                            )
                    invoices.append(inv)
                    continue
            # si no cumple estructura, fallback a parse local
            invoices.append(parse_markdown_invoice(text, f.name))
        else:
            invoices.append(parse_markdown_invoice(text, f.name))

    if not out_path:
        out_path = str(Path.cwd() / "mistral_invoices.xlsx")

    res = export_invoices_to_excel(invoices, out_path)
    print("Escrito:", res)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

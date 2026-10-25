import sys
from pathlib import Path

sys.path.insert(0, ".")

from src.core.excel_exporter import export_invoices_to_excel
from src.core.qa_checker import compare_invoices_json_vs_excel


def _sample_invoices():
    return [
        {
            "invoice_id": "INV-0001",
            "fecha": "2026-04-01",
            "proveedor": "ACME S.A.",
            "moneda": "USD",
            "subtotal": "100.00",
            "iva": "12.00",
            "total": "112.00",
            "lines": [
                {
                    "origen": "Factura 0001",
                    "descripcion": "Producto A",
                    "cantidad": "1",
                    "precio_unitario": "$100.00",
                    "iva_pct": "12%",
                    "subtotal": "100.00",
                    "iva_amount": "12.00",
                    "total": "112.00",
                }
            ],
        },
        {
            "invoice_id": "INV-0002",
            "fecha": "01/04/2026",
            "proveedor": "BETA LTD",
            "moneda": "USD",
            "subtotal": "200,00",
            "iva": "24,00",
            "total": "224,00",
            "lines": [
                {
                    "origen": "Factura 0002",
                    "descripcion": "Servicio B",
                    "cantidad": "2",
                    "precio_unitario": "100,00",
                    "iva_pct": "12%",
                    "subtotal": "200,00",
                    "iva_amount": "24,00",
                    "total": "224,00",
                }
            ],
        },
    ]


def main():
    invoices = _sample_invoices()
    out_dir = Path("out_roundtrip")
    out_dir.mkdir(exist_ok=True)
    out_file = out_dir / "roundtrip_test.xlsx"

    path = export_invoices_to_excel(invoices, out_file)
    print("Exported to:", path)

    diffs = compare_invoices_json_vs_excel(invoices, path)
    if not diffs:
        print("QA OK: exported Excel matches JSON (roundtrip)")
        return 0
    print("QA FAIL: differences found:")
    for d in diffs:
        print(" -", d)
    return 2


if __name__ == "__main__":
    rc = main()
    sys.exit(rc)

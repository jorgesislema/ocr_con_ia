from __future__ import annotations

from src.core.invoice_consolidator import consolidate_product_lines_text

SAMPLE = '''
Factura: 0001
Proveedor: ACME S.A.
1 x Tornillo @ $2.00
3 x Tuerca @ $1.00
SUBTOTAL: $5.00
IVA 12%: $0.60
TOTAL: $5.60

Factura: 0002
Proveedor: BETA LTD
2 x Pulidora @ $100.00 IVA 15%
1 x Broca @ $10.00
BASE: $210.00
IVA 15%: $31.50
VALOR TOTAL $241.50
'''


def main() -> None:
    res = consolidate_product_lines_text(SAMPLE)
    lines = res["lineas_detalle"]
    assert len(lines) == 4, res
    l1 = lines[0]
    assert l1["origen"].startswith("Factura 0001") or "ACME" in l1["origen"]
    assert l1["descripcion"].lower().startswith("tornillo")
    assert l1["cantidad"] == 1.0
    assert l1["precio_unitario"] == 2.0
    assert l1["subtotal_linea"] == 2.0

    l3 = lines[2]
    assert l3["origen"].startswith("Factura 0002") or "BETA" in l3["origen"]
    assert l3["cantidad"] == 2.0
    assert l3["precio_unitario"] == 100.0
    assert l3["porcentaje_iva"] == 15

    print("PASS: audit consolidator basic assertions")


if __name__ == "__main__":
    main()

from __future__ import annotations

from src.core.invoice_consolidator import consolidate_invoices_text


SAMPLE = '''
Factura: 0001
Fecha: 01/04/2026
Proveedor: ACME S.A.
SUBTOTAL: $100.00
IVA 12%: $12.00
TOTAL: $112.00

Factura: 0002
Fecha: 02/04/2026
Proveedor: BETA LTD
BASE: $200.00
IVA 12%: $24.00
IVA 15%: $30.00
VALOR TOTAL $254.00
'''


def main() -> None:
    res = consolidate_invoices_text(SAMPLE)
    assert len(res["facturas"]) == 2, res
    f1, f2 = res["facturas"]
    assert f1["total_pagado"] == 112.0
    assert f1["iva_pagado"] == 12.0
    assert f2["total_pagado"] == 254.0
    assert round(res["gran_total"]["total_iva"], 2) == 66.0
    print("PASS: consolidator basic assertions")


if __name__ == "__main__":
    main()

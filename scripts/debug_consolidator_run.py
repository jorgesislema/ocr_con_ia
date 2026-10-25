from __future__ import annotations

from src.core.invoice_consolidator import consolidate_invoices_text
import json

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

res = consolidate_invoices_text(SAMPLE)
print(json.dumps(res, indent=2, ensure_ascii=False))

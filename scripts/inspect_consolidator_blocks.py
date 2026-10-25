from __future__ import annotations

import re
from src.core import invoice_consolidator as ic

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

blocks = re.split(r"(?i)(?=\bFactura\b)", SAMPLE)
for i, blk in enumerate(blocks):
    print('--- BLOCK', i, '---')
    print(blk)
    m = ic._TOTAL_PAT.search(blk)
    print('TOTAL MATCH:', bool(m), m.group('amt') if m else None)
    iv_lines = [ln for ln in blk.splitlines() if 'IVA' in ln.upper()]
    print('IVA LINES:', iv_lines)
    print('\n')

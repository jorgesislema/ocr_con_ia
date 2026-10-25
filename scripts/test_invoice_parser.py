from __future__ import annotations

from src.core.invoice_parser import parse_invoice_text


SAMPLE = '''
Factura: 000123
Fecha: 12/03/2026
Proveedor: ACME S.A.
Cliente: MARIA DE LOS ANGELES SAN FUENTE GAETE

1 x Widget A    10.00   12%   11.20
2 x Servicio B  50.00    0%  100.00
'''


def main() -> None:
    parsed = parse_invoice_text(SAMPLE)
    assert parsed["num_factura"] == "000123"
    assert parsed["fecha"] == "2026-03-12"
    assert parsed["proveedor"]["nombre"].upper().startswith("ACME")
    assert len(parsed["lineas"]) >= 2
    print("PASS: invoice parser basic assertions")


if __name__ == "__main__":
    main()

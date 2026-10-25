"""Tests del consolidador multipágina (regla #4 — totales dispersos en EU).

Ejecutar:  python -m pytest app/tests/test_consolidator.py -q
"""
from decimal import Decimal

from app.core.schemas.invoice import InvoiceSchema, LineItem, Party, TaxLine
from app.validation.consolidator import consolidate_pages
from app.validation.validator import validate_invoice

D = Decimal


def _page1() -> InvoiceSchema:
    return InvoiceSchema(
        invoice_number="EU-77", currency="EUR",
        supplier=Party(name="GmbH Berlin", tax_id="DE812345678", country="DE"),
        line_items=[LineItem(description="Widget A", quantity=D("10"),
                             unit_price=D("20"), subtotal=D("200"), page=1)],
        subtotal=D("200"),
        taxes=[TaxLine(type="VAT", rate=D("21"), base_amount=D("200"), amount=D("42"))],
        total=D("0"),
    )


def _page2() -> InvoiceSchema:
    return InvoiceSchema(
        customer=Party(name="Kunde AG", country="AT"),
        line_items=[LineItem(description="Widget B", quantity=D("5"),
                             unit_price=D("20"), subtotal=D("100"), page=2)],
        subtotal=D("100"),
        taxes=[TaxLine(type="VAT", rate=D("21"), base_amount=D("100"), amount=D("21"))],
        total=D("363"),  # total final del documento (300 + 63), en la última página
    )


def test_consolidado_suma_subtotales_e_impuestos():
    doc = consolidate_pages([_page1(), _page2()])
    assert doc.subtotal == D("300")
    assert doc.taxes_total() == D("63")
    assert doc.total == D("363")
    # VAT repetido en ambas páginas se agrupa en UN solo TaxLine.
    assert len(doc.taxes) == 1
    assert doc.taxes[0].base_amount == D("300")
    assert len(doc.line_items) == 2
    assert doc.line_items[0].page == 1 and doc.line_items[1].page == 2


def test_consolidado_multipagina_valida_el_total_final():
    """Caso de uso real: subtotales dispersos por página, total en la última."""
    doc = consolidate_pages([_page1(), _page2()])
    report = validate_invoice(doc)
    assert report.is_valid, [i.message for i in report.issues]
    assert report.computed_total == D("363")  # 300 + 63 - 0


def test_parties_se_fusionan_entre_paginas():
    doc = consolidate_pages([_page1(), _page2()])
    assert doc.supplier.name == "GmbH Berlin"
    assert doc.customer.name == "Kunde AG"


def test_paginas_vacias_rechazadas():
    try:
        consolidate_pages([])
        assert False, "debería haber lanzado ValueError"
    except ValueError:
        pass

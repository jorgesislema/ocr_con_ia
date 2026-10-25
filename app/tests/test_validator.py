"""Tests del motor de validación determinista (regla #4).

Ejecutar:  python -m pytest app/tests/test_validator.py -q
No requiere API keys ni Redis — solo aritmética con Decimal.
"""
from decimal import Decimal

from app.core.schemas.invoice import (
    DiscountLine,
    InvoiceSchema,
    LineItem,
    TaxLine,
)
from app.validation.validator import (
    CODE_LINES_SUM_MISMATCH,
    CODE_TOTAL_MISMATCH,
    validate_invoice,
)

D = Decimal


def _invoice(**overrides) -> InvoiceSchema:
    """Factura LatAm de ejemplo: subtotal 150, descuento 7.50, IVA 15% + ICE."""
    base = dict(
        invoice_number="FAC-1",
        currency="USD",
        line_items=[LineItem(description="Cable", quantity=D("120"),
                             unit_price=D("1.25"), subtotal=D("150"))],
        subtotal=D("150"),
        discounts=[DiscountLine(concept="Comercial", amount=D("7.50"))],
        taxes=[TaxLine(type="IVA", rate=D("15"), base_amount=D("142.50"), amount=D("21.38")),
               TaxLine(type="ICE", amount=D("2.10"))],
        total=D("165.98"),
    )
    base.update(overrides)
    return InvoiceSchema(**base)


def test_factura_balanceada_es_valida():
    report = validate_invoice(_invoice())
    assert report.is_valid, [i.message for i in report.issues]
    assert report.computed_total == D("165.98")
    assert report.difference == D("0")


def test_total_alterado_detecta_mismatch():
    report = validate_invoice(_invoice(total=D("200")))
    assert not report.is_valid
    codes = {i.code for i in report.issues}
    assert CODE_TOTAL_MISMATCH in codes
    assert report.difference == D("34.02")


def test_dentro_de_tolerancia_es_valido():
    # Diferencia de 1 céntimo → redondeo permitido (tolerancia 0.02).
    report = validate_invoice(_invoice(total=D("165.99")))
    assert report.is_valid


def test_suma_de_lineas_discrepante_emite_warning():
    report = validate_invoice(_invoice(
        line_items=[LineItem(description="X", subtotal=D("100"))],
        subtotal=D("150"),
    ))
    codes = {i.code for i in report.issues}
    assert CODE_LINES_SUM_MISMATCH in codes
    # Es warning, no error: is_valid depende solo de errores de total.
    assert report.is_valid

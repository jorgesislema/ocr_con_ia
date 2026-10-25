"""Motor de validación determinista — regla arquitectónica #4.

Principio: **la IA extrae, pero Python valida.** Nada de re-preguntar al
LLM: aquí solo hay aritmética exacta con ``Decimal``.

Identidad verificada:
    total == subtotal + suma(taxes.amount) - suma(discounts.amount)

Con tolerancia configurable (redondeos de 1-2 céntimos son normales en
facturación real). Además comprueba la consistencia interna de líneas,
impuestos y descuentos, y emite un ``ValidationReport`` con issues
codificados para la UI de revisión humana.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from app.core.config import get_settings
from app.core.schemas.invoice import InvoiceSchema, ValidationIssue, ValidationReport

# Códigos de incidencia (contrato con la UI de revisión).
CODE_TOTAL_MISMATCH = "TOTAL_MISMATCH"
CODE_LINES_SUM_MISMATCH = "LINES_SUM_MISMATCH"
CODE_TAX_SUM_MISMATCH = "TAX_SUM_MISMATCH"
CODE_DISCOUNT_SIGN = "DISCOUNT_SIGN"
CODE_EMPTY_LINES = "EMPTY_LINES"
CODE_CURRENCY_MISSING = "CURRENCY_MISSING"


def _q(value: Decimal | None) -> Decimal:
    """Normaliza a Decimal no-nulo (0 si falta)."""
    return value if isinstance(value, Decimal) else Decimal(str(value or "0"))


def _abs_diff(a: Decimal, b: Decimal) -> Decimal:
    return abs(a - b)


def validate_invoice(invoice: InvoiceSchema) -> ValidationReport:
    """Valida matemáticamente una factura canónica.

    Returns:
        ValidationReport con ``is_valid`` (False si hay algún issue de
        severidad "error"), la lista de issues y la diferencia calculada
        entre total declarado y total computado.
    """
    settings = get_settings()
    # Tolerancia en unidades de moneda (redondeos de céntimos permitidos).
    tolerance = Decimal(str(settings.validation_tolerance))

    issues: list[ValidationIssue] = []

    subtotal = _q(invoice.subtotal)
    declared_total = _q(invoice.total)
    taxes_sum = invoice.taxes_total()
    discounts_sum = invoice.discounts_total()

    # ── Identidad principal: total == subtotal + impuestos - descuentos ──
    computed_total = subtotal + taxes_sum - discounts_sum
    difference = declared_total - computed_total
    if _abs_diff(declared_total, computed_total) > tolerance:
        issues.append(ValidationIssue(
            code=CODE_TOTAL_MISMATCH,
            severity="error",
            message=(
                f"El total declarado ({declared_total}) no cuadra con "
                f"subtotal ({subtotal}) + impuestos ({taxes_sum}) - "
                f"descuentos ({discounts_sum}) = {computed_total}."
            ),
            expected=str(computed_total),
            actual=str(declared_total),
        ))

    # ── Coherencia de líneas: suma(line_items.subtotal) ≈ subtotal ───────
    if not invoice.line_items:
        issues.append(ValidationIssue(
            code=CODE_EMPTY_LINES, severity="warning",
            message="El documento no tiene líneas de detalle extraídas.",
        ))
    else:
        lines_with_amount = [
            li for li in invoice.line_items
            if li.subtotal is not None or (li.quantity is not None and li.unit_price is not None)
        ]
        lines_sum = sum(
            (_q(li.subtotal) if li.subtotal is not None
             else _q(li.quantity) * _q(li.unit_price))
            for li in lines_with_amount
        )
        if _abs_diff(lines_sum, subtotal) > tolerance:
            issues.append(ValidationIssue(
                code=CODE_LINES_SUM_MISMATCH, severity="warning",
                message=(
                    f"La suma de líneas ({lines_sum}) no coincide con el "
                    f"subtotal declarado ({subtotal})."
                ),
                expected=str(subtotal), actual=str(lines_sum),
            ))

    # ── Coherencia de impuestos: base * rate ≈ amount ─────────────────────
    for i, tax in enumerate(invoice.taxes):
        if tax.rate is not None and tax.base_amount is not None:
            expected_tax = (_q(tax.base_amount) * _q(tax.rate) / Decimal("100")).quantize(Decimal("0.01"))
            if _abs_diff(expected_tax, _q(tax.amount)) > tolerance:
                issues.append(ValidationIssue(
                    code=CODE_TAX_SUM_MISMATCH, severity="warning",
                    message=(
                        f"Impuesto '{tax.type}': base {tax.base_amount} × {tax.rate}% = "
                        f"{expected_tax}, pero se declaró {tax.amount}."
                    ),
                    expected=str(expected_tax), actual=str(tax.amount),
                ))
        if _q(tax.amount) < 0:
            issues.append(ValidationIssue(
                code=CODE_TAX_SUM_MISMATCH, severity="warning",
                message=f"Impuesto '{tax.type}' en posición {i} tiene importe negativo.",
            ))

    # ── Signo de descuentos ────────────────────────────────────────────────
    for d in invoice.discounts:
        if _q(d.amount) < 0:
            issues.append(ValidationIssue(
                code=CODE_DISCOUNT_SIGN, severity="warning",
                message=f"Descuento '{d.concept}' negativo; debe registrarse como importe positivo.",
            ))

    # ── Moneda ─────────────────────────────────────────────────────────────
    if not invoice.currency:
        issues.append(ValidationIssue(
            code=CODE_CURRENCY_MISSING, severity="warning",
            message="No se detectó moneda (ISO 4217).",
        ))

    has_errors = any(i.severity == "error" for i in issues)
    return ValidationReport(
        is_valid=not has_errors,
        issues=issues,
        computed_total=computed_total,
        declared_total=declared_total,
        difference=difference,
        validated_at=datetime.now(timezone.utc),
    )

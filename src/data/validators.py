"""Validadores y utilidades de normalización.

Incluye validadores contables simples y utilidades de parsing.
"""
from __future__ import annotations

import math
from datetime import datetime
from typing import Any


class AccountingValidator:
    """Valida suma de subtotal + impuestos == total con tolerancia."""

    @staticmethod
    def validate_invoice_math(invoice: dict[str, Any]) -> dict[str, Any]:
        """Valida la consistencia matemática de una factura.

        Suma `subtotal` y cada `monto_impuesto` dentro de `desglose_impuestos`
        (si existe) y compara con `total`. Añade banderas en caso de fallo.
        """
        try:
            subtotal = float(invoice.get("subtotal", 0) or 0)
        except Exception:
            subtotal = 0.0

        total_from_taxes = 0.0
        taxes = invoice.get("desglose_impuestos")
        if isinstance(taxes, list):
            for item in taxes:
                try:
                    amt = float(item.get("monto_impuesto", 0) or 0)
                except Exception:
                    amt = 0.0
                total_from_taxes += amt

        computed = subtotal + total_from_taxes

        try:
            total = float(invoice.get("total", 0) or 0)
        except Exception:
            total = 0.0

        if not math.isclose(computed, total, rel_tol=0.0, abs_tol=0.05):
            invoice["math_valid"] = False
            invoice["error_msg"] = "Subtotal + Tax != Total"
        else:
            invoice["math_valid"] = True

        return invoice


def parse_date(value: str) -> datetime | None:
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(value, fmt)
        except Exception:
            continue
    return None

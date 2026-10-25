"""Motor de validación determinista (regla #4) + consolidador multipágina."""

from app.validation.consolidator import consolidate_pages
from app.validation.validator import (
    CODE_DISCOUNT_SIGN,
    CODE_EMPTY_LINES,
    CODE_LINES_SUM_MISMATCH,
    CODE_TAX_SUM_MISMATCH,
    CODE_TOTAL_MISMATCH,
    CODE_CURRENCY_MISSING,
    validate_invoice,
)

__all__ = [
    "CODE_CURRENCY_MISSING",
    "CODE_DISCOUNT_SIGN",
    "CODE_EMPTY_LINES",
    "CODE_LINES_SUM_MISMATCH",
    "CODE_TAX_SUM_MISMATCH",
    "CODE_TOTAL_MISMATCH",
    "consolidate_pages",
    "validate_invoice",
]

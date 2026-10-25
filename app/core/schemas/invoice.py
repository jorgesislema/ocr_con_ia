"""Esquema canónico de datos — regla arquitectónica #2.

Ninguna parte del sistema debe depender del formato particular de la
factura de entrada (LatAm con IGV/IVA/GST, Europa con VAT multipágina,
manuscritos…). Todos los proveedores IA y parsers normalizan su salida a
:pyclass:`InvoiceSchema`, que es el único contrato interno.

Diseño:
    * Dinero como ``Decimal`` (nunca float) para validación exacta.
    * ``taxes`` es un ARRAY porque LatAm factura con múltiples impuestos
      simultáneos (IVA + ICE + propina…) y Europa con varios tipos de VAT.
    * ``pages`` conserva la trazabilidad por página para consolidación
      de documentos multipágina (regla #4).
    * ``validation`` guarda el informe del motor determinista.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Alias de tipo para importes monetarios (se serializa como string).
Money = Annotated[Decimal, Field(default=None, description="Importe monetario en Decimal")]


class DocumentType(str, Enum):
    """Tipos de documento soportados por el pipeline."""

    INVOICE = "invoice"
    RECEIPT = "receipt"
    CREDIT_NOTE = "credit_note"
    OTHER = "other"


class Region(str, Enum):
    """Agrupación fiscal de alto nivel."""

    LATAM = "LATAM"
    EU = "EU"
    OTHER = "OTHER"


class TaxLine(BaseModel):
    """Un impuesto individual de la factura.

    Soporta los múltiples impuestos de LatAm (IGV, ICE, IVA reducido…)
    y los tipos de VAT europeos dentro del mismo documento.
    """

    model_config = ConfigDict(json_encoders={Decimal: str})

    type: str = Field(..., examples=["IVA", "IGV", "VAT", "GST"], description="Nombre del impuesto")
    rate: Decimal | None = Field(None, description="Porcentaje aplicado (21, 12, 8.5…)")
    base_amount: Decimal | None = Field(None, description="Base imponible sobre la que se aplica")
    amount: Decimal = Field(..., description="Importe del impuesto en moneda")


class DiscountLine(BaseModel):
    """Descuento global o por línea, normalizado."""

    model_config = ConfigDict(json_encoders={Decimal: str})

    concept: str | None = Field(None, examples=["Descuento comercial", "Early payment"])
    amount: Decimal = Field(..., description="Importe descontado (positivo)")


class LineItem(BaseModel):
    """Línea de detalle de la factura."""

    model_config = ConfigDict(json_encoders={Decimal: str})

    description: str
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    tax_rate: Decimal | None = Field(None, description="Tipo de impuesto aplicado a la línea")
    subtotal: Decimal | None = Field(None, description="quantity * unit_price (sin impuestos)")
    page: int | None = Field(None, ge=1, description="Página de origen (trazabilidad)")


class Party(BaseModel):
    """Emisor o receptor del documento."""

    name: str | None = None
    tax_id: str | None = Field(None, description="RUC / NIF / CIF / VAT number")
    address: str | None = None
    country: str | None = Field(None, examples=["EC", "ES", "MY"], description="Código ISO país")
    email: str | None = None
    phone: str | None = None


class PageMeta(BaseModel):
    """Metadatos por página — base del consolidador multipágina (regla #4)."""

    page_number: int = Field(..., ge=1)
    provider: str | None = Field(None, description="Proveedor IA que procesó la página")
    confidence: float | None = Field(None, ge=0.0, le=1.0)
    raw_text_ref: str | None = Field(None, description="Referencia al texto crudo almacenado")


class ValidationIssue(BaseModel):
    """Incidencia detectada por el motor de validación determinista."""

    code: str = Field(..., examples=["TOTAL_MISMATCH", "TAX_SUM_MISMATCH", "LINES_SUM_MISMATCH"])
    severity: Literal["error", "warning"] = "error"
    message: str
    expected: str | None = None
    actual: str | None = None


class ValidationReport(BaseModel):
    """Resultado del validador determinista (regla arquitectónica #4)."""

    is_valid: bool
    issues: list[ValidationIssue] = []
    # Identidad matemática verificada: total == subtotal + impuestos - descuentos
    computed_total: Decimal | None = None
    declared_total: Decimal | None = None
    difference: Decimal | None = None
    validated_at: datetime | None = None


class InvoiceSchema(BaseModel):
    """Esquema universal de factura/documento.

    Todo proveedor IA (Gemini, Mistral, futuros) devuelve este objeto y
    toda exportación (Excel/CSV/Word/PDF) parte de él.
    """

    model_config = ConfigDict(json_encoders={Decimal: str})

    # ── Identificación ────────────────────────────────────────────────────
    schema_version: str = "1.0"
    document_type: DocumentType = DocumentType.INVOICE
    invoice_number: str | None = None
    issue_date: date | None = None
    due_date: date | None = None
    currency: str | None = Field(None, min_length=3, max_length=3, description="ISO 4217")
    region: Region | None = None

    # ── Partes ────────────────────────────────────────────────────────────
    supplier: Party | None = None
    customer: Party | None = None

    # ── Contenido económico ───────────────────────────────────────────────
    line_items: list[LineItem] = []
    subtotal: Decimal = Field(default=Decimal("0"), description="Suma de líneas, sin impuestos")
    discounts: list[DiscountLine] = []
    taxes: list[TaxLine] = Field(
        default_factory=list,
        description="Array de impuestos — soporta multi-impuesto LatAm y VAT europeo",
    )
    total: Decimal = Field(default=Decimal("0"), description="Total final a pagar")

    # ── Trazabilidad ──────────────────────────────────────────────────────
    pages: list[PageMeta] = Field(default_factory=list, description="Metadatos por página")
    notes: str | None = None
    # Texto completo y limpio del documento — lo pide el prompt (TAREA 1) y lo
    # consume el exportador de Word/TXT (TAREA 3).
    full_text_content: str | None = Field(
        None, description="Texto completo limpio del documento para exportar a Word/TXT"
    )
    extra_fields: dict[str, Any] = Field(
        default_factory=dict, description="Campos regionales no canónicos (passthrough)"
    )
    validation: ValidationReport | None = Field(
        None, description="Informe del motor de validación determinista"
    )

    @field_validator("currency")
    @classmethod
    def _upper_currency(cls, v: str | None) -> str | None:
        return v.upper() if v else v

    # ── Ayudas de dominio ─────────────────────────────────────────────────
    def taxes_total(self) -> Decimal:
        """Suma de todos los importes de impuestos."""
        return sum((t.amount for t in self.taxes), Decimal("0"))

    def discounts_total(self) -> Decimal:
        """Suma de todos los descuentos."""
        return sum((d.amount for d in self.discounts), Decimal("0"))

"""Consolidador de documentos multipágina — parte de la regla arquitectónica #4.

Problema: en facturas europeas (y algunos PDFs LatAm largos) los totales
están DISPERSOS: el subtotal puede aparecer por página, los impuestos por
tipo en páginas distintas y el total final solo en la última página.

Estrategia:
    1. El proveedor extrae cada página como un ``InvoiceSchema`` PARCIAL
       (``is_single_page=False`` en el prompt).
    2. Este módulo consolida: suma subtotales, concatena y agrupa líneas,
       agrupa impuestos por (type, rate), y toma el total final del último
       valor declarado no-cero.
    3. El resultado consolidado pasa por el ``Validator`` para verificar la
       identidad matemática del total FINAL (nunca por página).
"""
from __future__ import annotations

from decimal import Decimal

from app.core.schemas.invoice import (
    DiscountLine,
    InvoiceSchema,
    LineItem,
    PageMeta,
    Party,
    TaxLine,
)


def _merge_party(primary: Party | None, secondary: Party | None) -> Party | None:
    """Combina datos de emisor/receptor repartidos entre páginas."""
    if primary is None:
        return secondary
    if secondary is None:
        return primary
    # Rellena huecos de la primera con datos de la segunda.
    return Party(
        name=primary.name or secondary.name,
        tax_id=primary.tax_id or secondary.tax_id,
        address=primary.address or secondary.address,
        country=primary.country or secondary.country,
        email=primary.email or secondary.email,
        phone=primary.phone or secondary.phone,
    )


def _merge_taxes(all_taxes: list[list[TaxLine]]) -> list[TaxLine]:
    """Agrupa impuestos repetidos por (type, rate) sumando sus importes.

    Caso típico EU: el VAT 21% aparece en páginas 1 y 2 → un solo
    TaxLine con el importe acumulado. Caso LatAm: IVA + ICE coexisten.
    """
    merged: dict[tuple[str, str], TaxLine] = {}
    for page_taxes in all_taxes:
        for tax in page_taxes:
            key = (tax.type.upper(), str(tax.rate))
            if key in merged:
                merged[key].amount += tax.amount
                if merged[key].base_amount is None and tax.base_amount is not None:
                    merged[key].base_amount = tax.base_amount
                elif tax.base_amount is not None:
                    merged[key].base_amount = (merged[key].base_amount or Decimal("0")) + tax.base_amount
            else:
                merged[key] = tax.model_copy(deep=True)
    return list(merged.values())


def consolidate_pages(page_invoices: list[InvoiceSchema]) -> InvoiceSchema:
    """Consolida las extracciones parciales de cada página en UN documento.

    Args:
        page_invoices: extracciones parciales, EN ORDEN de página. Cada una
            tiene sus propios subtotales/impuestos por página y ``total``
            en 0 salvo que la página muestre el total final del documento.

    Returns:
        InvoiceSchema único y consolidado, listo para ``validate_invoice``.
    """
    if not page_invoices:
        raise ValueError("consolidate_pages: lista de páginas vacía")
    if len(page_invoices) == 1:
        return page_invoices[0]

    base = page_invoices[0].model_copy(deep=True)

    # ── Escalares: primer valor no-nulo entre páginas ──────────────────────
    for page in page_invoices[1:]:
        base.invoice_number = base.invoice_number or page.invoice_number
        base.issue_date = base.issue_date or page.issue_date
        base.due_date = base.due_date or page.due_date
        base.currency = base.currency or page.currency
        base.region = base.region or page.region
        base.supplier = _merge_party(base.supplier, page.supplier)
        base.customer = _merge_party(base.customer, page.customer)
        base.notes = base.notes or page.notes
        base.extra_fields.update(page.extra_fields)

    # ── Líneas: concatena conservando la página de origen ──────────────────
    merged_items: list[LineItem] = []
    for idx, page in enumerate(page_invoices, start=1):
        for item in page.line_items:
            item_copy = item.model_copy(deep=True)
            item_copy.page = item_copy.page or idx
            merged_items.append(item_copy)
    base.line_items = merged_items

    # ── Subtotal: suma de los subtotales por página (regla #4) ────────────
    base.subtotal = sum((p.subtotal for p in page_invoices), Decimal("0"))

    # ── Descuentos: concatena y suma ──────────────────────────────────────
    base.discounts = [
        d.model_copy(deep=True) for p in page_invoices for d in p.discounts
    ]

    # ── Impuestos: agrupados por (type, rate) acumulando importes ─────────
    base.taxes = _merge_taxes([p.taxes for p in page_invoices])

    # ── Total final: el último total declarado NO cero del documento ──────
    final_total = Decimal("0")
    for page in page_invoices:
        if page.total and page.total != 0:
            final_total = page.total
    base.total = final_total

    # ── Texto completo: concatena el texto limpio de todas las páginas ────
    texts = [(p.full_text_content or "").strip() for p in page_invoices]
    joined = "\n\n".join(t for t in texts if t)
    base.full_text_content = joined or None

    # ── Metadatos de página para trazabilidad ─────────────────────────────
    base.pages = [
        PageMeta(
            page_number=idx,
            provider=p.pages[0].provider if p.pages else None,
            confidence=p.pages[0].confidence if p.pages else None,
            raw_text_ref=p.pages[0].raw_text_ref if p.pages else None,
        )
        for idx, p in enumerate(page_invoices, start=1)
    ]
    return base

"""Prompt interno de extracción hacia el esquema canónico.

Compartido por todos los proveedores (Gemini y Mistral usan el mismo
contrato JSON, solo cambia el transporte). Mantener la regla de oro:
el LLM SOLO devuelve JSON válido — nunca markdown, nunca explicaciones.
"""
from __future__ import annotations

import json

from app.core.schemas.invoice import InvoiceSchema

# Contrato JSON esperado, generado desde el propio esquema Pydantic para
# que prompt y código NUNCA diverjan.
_CANONICAL_EXAMPLE = {
    "document_type": "invoice",
    "invoice_number": "FAC-2026-001234",
    "issue_date": "2026-03-15",
    "due_date": "2026-04-15",
    "currency": "USD",
    "region": "LATAM",
    "supplier": {"name": "Comercial Andina S.A.", "tax_id": "RUC 1792345678001",
                 "address": "Av. Amazonas 123, Quito", "country": "EC"},
    "customer": {"name": "Importadora del Pacífico", "tax_id": "RUC 0993456789001",
                 "country": "EC"},
    "line_items": [
        {"description": "Cable THHN 12 AWG", "quantity": 120, "unit_price": 1.25,
         "tax_rate": 15, "subtotal": 150.00, "page": 1}
    ],
    "subtotal": 150.00,
    "discounts": [{"concept": "Descuento comercial", "amount": 7.50}],
    "taxes": [
        {"type": "IVA", "rate": 15, "base_amount": 142.50, "amount": 21.38},
        {"type": "ICE", "rate": None, "base_amount": None, "amount": 2.10}
    ],
    "total": 165.98,
    "notes": None
}


def build_extraction_prompt(hint: str = "invoice", region_hint: str | None = None,
                            is_single_page: bool = True) -> str:
    """Construye el prompt de usuario según tipo de documento y región."""
    region_rule = ""
    if region_hint == "LATAM":
        region_rule = (
            "- Región LATAM: el documento puede llevar VARIOS impuestos simultáneos "
            "(IVA/IGV, ICE, IRBPNR, propina…). Regístralos TODOS en el array `taxes`, "
            "cada uno con su `rate` y `amount`. No confundas retenciones con impuestos: "
            "las retenciones NO se suman al total.\n"
        )
    elif region_hint == "EU":
        region_rule = (
            "- Región EU: puede haber múltiples tipos de VAT (reducido/general) en un mismo "
            "documento. Usa un elemento por tipo en el array `taxes`.\n"
        )

    multipage_rule = (
        "- Documento multipágina: esta página es PARCIAL. Rellena SOLO los datos visibles "
        "en esta página: `subtotal` = suma de las líneas de ESTA página, `taxes` = impuestos "
        "de ESTA página, y deja `total` en 0 salvo que aparezca el TOTAL FINAL del documento "
        "(normalmente en la última página).\n"
        if not is_single_page
        else ""
    )

    return f"""Eres un motor de extracción de datos de documentos contables.
Analiza el documento adjunto ({hint}) y devuelve EXCLUSIVAMENTE un objeto JSON válido
que cumpla EXACTAMENTE este esquema canónico. Sin markdown, sin explicaciones, sin ```.

Reglas estrictas:
- Todos los importes son números; usa punto decimal, sin símbolos de moneda ni separadores de miles.
- `subtotal` = suma de las líneas de detalle (ANTES de impuestos y descuentos).
- `taxes` es un ARRAY: un elemento por cada impuesto distinto.
- `discounts` es un ARRAY: un elemento por cada descuento global visible.
- `total` = importe final total a pagar (después de impuestos y descuentos).
- Fechas en formato ISO 8601 (YYYY-MM-DD).
- `currency` en código ISO 4217 de 3 letras (USD, EUR, MXN, ECS→USD, …).
- Si un dato no aparece en el documento, usa null (no inventes valores).
{region_rule}{multipage_rule}
Esquema y ejemplo de salida:
{json.dumps(_CANONICAL_EXAMPLE, indent=2, ensure_ascii=False)}
"""


# ── Esquema JSON (JSON Schema) para modelos con salida estructurada ─────────
# Gemini (response_schema) y Mistral (response_format json_schema) aceptan
# un JSON Schema; lo derivamos del modelo Pydantic para no duplicar.

def canonical_json_schema() -> dict:
    """JSON Schema del InvoiceSchema para *structured output*."""
    return InvoiceSchema.model_json_schema()


SYSTEM_PROMPT = (
    "Extraes datos de documentos (facturas, recibos, manuscritos, partituras) con máxima "
    "precisión y devuelves SOLO JSON válido conforme al esquema canónico indicado. "
    "Nunca inventas importes: si no puedes leer un dato con confianza, lo pones a null."
)

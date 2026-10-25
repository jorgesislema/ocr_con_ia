"""Generador de prompts dinámicos — TAREA 1.

``build_extraction_prompt(pais, columnas_solicitadas)`` construye el prompt
que se envía al LLM (Gemini o Mistral) con:

    1. El JSON Schema del ``InvoiceSchema`` (inyectado, nunca duplicado a mano).
    2. La normativa fiscal del país (mapeo ISO → normativa; desconocido → "Genérica").
    3. Reglas estrictas anti-alucinación y de manejo de manuscritos (→ null).
    4. Prioridad del total IMPRESO sobre el calculado en descuadres de redondeo.
    5. La obligación de devolver ``full_text_content`` (texto limpio completo,
       usado por el exportador de Word/TXT).
    6. Las ``columnas_solicitadas`` para que la IA priorice esos campos.
"""
from __future__ import annotations

import json

from app.core.schemas.invoice import InvoiceSchema

# ── 2) Mapeo país (ISO-3166 alpha-2) → normativa fiscal ─────────────────────
COUNTRY_NORMATIVA: dict[str, str] = {
    "EC": "Ecuador — Emisor con RUC (13 dígitos). Normativa SRI. IVA 15% "
          "(tarifa vigente), ICE aplicable. Las retenciones NO se suman al total.",
    "MX": "México — RFC del emisor y receptor. Facturación SAT (CFDI). IVA 16% "
          "general (8% frontera norte), IEPS aplicable.",
    "CO": "Colombia — NIT. Normativa DIAN. IVA 19%, INC (Impuesto Nacional al Consumo), ICA.",
    "PE": "Perú — RUC. Normativa SUNAT. IGV 18%, ISC aplicable.",
    "AR": "Argentina — CUIT. Normativa AFIP/ARCA. IVA 21%, percepciones de IIBB.",
    "CL": "Chile — RUT. Normativa SII. IVA 19%.",
    "UY": "Uruguay — RUT. Normativa DGI. IVA 22%.",
    "ES": "España — NIF/CIF. Normativa AEAT. IVA 21% / 10% / 4%, IRPF (retención) si aplica.",
    "EU": "Unión Europea — VAT Number (formato: código de país + dígitos, ej. DE812345678). "
          "Puede haber varios tipos de VAT (reducido/general) en el mismo documento.",
}

DEFAULT_NORMATIVA = (
    "Genérica — sin normativa fiscal específica: extrae impuestos, subtotales y "
    "totales exactamente como aparecen impresos, sin asumir tarifas."
)


def _normativa_de(pais: str) -> str:
    """Resuelve la normativa del país. Código no reconocido → 'Genérica'."""
    if not pais:
        return DEFAULT_NORMATIVA
    return COUNTRY_NORMATIVA.get(pais.strip().upper(), DEFAULT_NORMATIVA)


# ── Ejemplo canónico (se serializa del propio esquema Pydantic) ──────────────
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
    "notes": None,
    "full_text_content": "FACTURA FAC-2026-001234 — Comercial Andina S.A. — "
                         "(aquí va el texto completo y limpio de TODA la página/documento)",
}


def build_extraction_prompt(
    pais: str,
    columnas_solicitadas: list[str],
    *,
    hint: str = "invoice",
    is_single_page: bool = True,
) -> str:
    """Construye el prompt de extracción dinámico.

    Args:
        pais: código ISO-3166 del país del documento (p. ej. "EC", "MX", "ES").
            Desconocido o vacío → normativa "Genérica".
        columnas_solicitadas: campos que el cliente final quiere ver; la IA
            debe priorizar su exactitud (no limita el resto de la extracción).
        hint: tipo de documento (invoice | receipt | manuscript | music_score).
        is_single_page: False cuando el consolidador extrae página a página
            (entonces los totales por página son PARCIALES).

    Returns:
        Prompt listo para enviar al LLM junto al documento.
    """
    # ── 2) Normativa por país ──────────────────────────────────────────────
    normativa = _normativa_de(pais)

    # ── 6) Columnas solicitadas por el cliente ─────────────────────────────
    if columnas_solicitadas:
        columnas_rule = (
            "CAMPOS PRIORITARIOS (el cliente final solicita estas columnas; "
            "dedica máxima atención a su exactitud y presencia):\n"
            + "\n".join(f"- {c}" for c in columnas_solicitadas)
            + "\nEl resto del esquema también se extrae, pero estos campos son prioritarios.\n"
        )
    else:
        columnas_rule = ""

    # ── 4) Regla de documento multipágina ──────────────────────────────────
    multipage_rule = (
        "- Documento multipágina: esta página es PARCIAL. Rellena SOLO los datos visibles "
        "en esta página: `subtotal` = suma de las líneas de ESTA página, `taxes` = impuestos "
        "de ESTA página, y deja `total` en 0 salvo que aparezca el TOTAL FINAL del documento "
        "(normalmente en la última página).\n"
        if not is_single_page
        else ""
    )

    return f"""Eres un motor de extracción de datos de documentos contables.
Analiza el documento adjunto (tipo: {hint}) y devuelve EXCLUSIVAMENTE un objeto JSON válido
que cumpla EXACTAMENTE el esquema canónico indicado. Sin markdown, sin explicaciones, sin ```.

CONTEXTO NORMATIVO DEL DOCUMENTO:
{normativa}

Reglas estrictas (obligatorias):
1. NO ALUCINES. Nunca inventes datos que no estén visibles en el documento. Si un dato no
   aparece o no es legible con confianza, usa null (¡nunca valores inventados o estimados!).
2. MANUSCRITOS: si el documento (o parte) está manuscrito y un campo es ilegible o ambiguo,
   devuelve null para ese campo. Es preferible un null honesto que un dato inventado.
3. TOTALES: si hay descuadre de redondeo entre el total calculado (subtotal + impuestos
   - descuentos) y el total IMPRESO en el documento, GANA SIEMPRE el total impreso. Copia
   los importes tal cual aparecen, sin recalcularlos tú.
4. Todos los importes son números con punto decimal, sin símbolos de moneda ni separadores
   de miles. Fechas en ISO 8601 (YYYY-MM-DD). `currency` en ISO 4217 (3 letras).
5. `taxes` es un ARRAY: un elemento por cada impuesto distinto del documento.
6. TEXTO COMPLETO OBLIGATORIO: la llave `full_text_content` debe contener el texto completo
   y limpio del documento (sin artefactos de OCR, con saltos de línea legibles, conservando
   tablas como filas de texto). Se usa para generar Word/TXT: no lo resumas ni lo trunques.
{columnas_rule}{multipage_rule}
Esquema y ejemplo de salida:
{json.dumps(_CANONICAL_EXAMPLE, indent=2, ensure_ascii=False)}
"""


# ── JSON Schema para modelos con salida estructurada ─────────────────────────
# Gemini (response_schema) y Mistral (response_format json_schema) aceptan un
# JSON Schema; lo derivamos del modelo Pydantic para no duplicarlo.

def canonical_json_schema() -> dict:
    """JSON Schema del InvoiceSchema para *structured output*."""
    return InvoiceSchema.model_json_schema()


SYSTEM_PROMPT = (
    "Extraes datos de documentos (facturas, recibos, manuscritos, partituras) con máxima "
    "precisión y devuelves SOLO JSON válido conforme al esquema canónico indicado. "
    "Nunca inventas importes: si no puedes leer un dato con confianza, lo pones a null."
)

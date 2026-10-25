from __future__ import annotations

import re
from typing import Any, Dict


def _join_text_from_ocr(ocr_json: dict) -> str:
    """Intenta concatenar todo el texto disponible en la salida OCR."""
    parts = []
    # formatos comunes: {'lines': [...]} o {'text': '...'} o lists of segments
    try:
        if isinstance(ocr_json, dict):
            # buscar keys que contengan 'text' o 'lines' o 'words'
            for k, v in ocr_json.items():
                if isinstance(v, str) and 'text' in k.lower():
                    parts.append(v)
                elif isinstance(v, list):
                    for item in v:
                        if isinstance(item, str):
                            parts.append(item)
                        elif isinstance(item, dict):
                            # attempt to find text fields inside dicts
                            for kk, vv in item.items():
                                if isinstance(vv, str) and 'text' in kk.lower():
                                    parts.append(vv)
                                elif isinstance(vv, (list, tuple)):
                                    for sub in vv:
                                        if isinstance(sub, str):
                                            parts.append(sub)
                elif isinstance(v, dict):
                    parts.append(str(v))
        elif isinstance(ocr_json, list):
            for it in ocr_json:
                if isinstance(it, str):
                    parts.append(it)
                elif isinstance(it, dict):
                    parts.append(str(it))
    except Exception:
        pass
    joined = '\n'.join(parts)
    # fallback: if nothing found, dump JSON
    if not joined.strip():
        try:
            import json

            joined = json.dumps(ocr_json, ensure_ascii=False)
        except Exception:
            joined = str(ocr_json)
    return joined


def deterministic_map(ocr_json: dict) -> Dict[str, Any]:
    """Extrae campos básicos con reglas/regex desde la salida OCR.

    Devuelve un dict con keys típicas: date, total, invoice_number, tax_id, provider.
    Esta función está pensada como primer paso determinista; es simple pero útil
    cuando el layout es consistente.
    """
    text = _join_text_from_ocr(ocr_json)
    res: Dict[str, Any] = {
        "date": None,
        "total": None,
        "invoice_number": None,
        "tax_id": None,
        "provider": None,
    }

    # fecha: dd/mm/yyyy, d/m/yyyy, yyyy-mm-dd
    date_rx = re.search(r"(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4})", text)
    if date_rx:
        res["date"] = date_rx.group(1)
    else:
        date_rx2 = re.search(r"(\d{4}[\-]\d{1,2}[\-]\d{1,2})", text)
        if date_rx2:
            res["date"] = date_rx2.group(1)

    # total: buscar la última ocurrencia de un monto con decimales
    money_rx = re.findall(r"(?:total|importe|monto|amount)\D{0,10}([0-9]{1,3}(?:[\.,][0-9]{3})*(?:[\.,][0-9]{2}))",
                          text, flags=re.IGNORECASE)
    if money_rx:
        res["total"] = money_rx[-1]
    else:
        # fallback: cualquier número con dos decimales
        any_money = re.findall(r"([0-9]+[\.,][0-9]{2})", text)
        if any_money:
            res["total"] = any_money[-1]

    # invoice number: buscar tokens tipo NF-1234 o Nº 1234 o Invoice 1234
    inv_rx = re.search(r"(?:N[oº\.]*|Invoice|Factura)\s*[:#\-\s]*([A-Za-z0-9\-\/]+)", text, flags=re.IGNORECASE)
    if inv_rx:
        res["invoice_number"] = inv_rx.group(1)

    # tax id / ruc: spesso una secuencia de 9-14 dígitos
    tax_rx = re.search(r"\b(\d{9,14})\b", text)
    if tax_rx:
        res["tax_id"] = tax_rx.group(1)

    # provider: heurística: línea antes de 'Invoice' o 'Factura' o encabezado
    prov_rx = re.search(r"([A-Z][A-Za-z0-9 &\-\.]{3,50})\s*\n\s*(?:Invoice|Factura|Bill)", text)
    if prov_rx:
        res["provider"] = prov_rx.group(1).strip()

    return res


def ia_fallback(ocr_json: dict, model: str = "gpt-4o-mini") -> Dict[str, Any]:
    """Placeholder: invocar un LLM/NER para extraer/normalizar si el mapeo determinista falla.

    Aquí dejamos un stub que más adelante conectará con el `prompt_manager` o servicio LLM.
    """
    # Por ahora devolvemos dict vacío para indicar que es un stub
    return {}

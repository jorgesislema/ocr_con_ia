"""Export helpers: parsing, sanitization and export to XLSX/CSV/DOCX.

This module provides safe parsing of GLM responses, sanitization against
CSV/Excel injection and structured flattening via pandas.json_normalize.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any
import os
import hashlib

import pandas as pd

logger = logging.getLogger(__name__)
_TELE_FILE = Path.home() / ".ocr_glm_telemetry.json"

# Claves por defecto que queremos forzar en la etapa de estructuración y export
# para asegurar que el Excel contiene las columnas críticas solicitadas por el
# usuario (fecha, número, proveedor, NIF, líneas y totales).
DEFAULT_EXPECTED_KEYS = [
    "fecha_emision",
    "numero_factura",
    "proveedor",
    "nif_proveedor",
    "subtotal",
    "iva",
    "total",
    "lineas",
]


def _load_user_config() -> dict:
    try:
        cfg_path = Path.home() / ".ocr_glm_config.json"
        if cfg_path.exists():
            data = json.loads(cfg_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


def _sanitize_ocr_text_for_prompt(s: str) -> str:
    """Sanitiza texto OCR antes de inyectarlo en el prompt para evitar
    escapes inválidos en JSON y caracteres de control que rompan respuestas.
    """
    if not s:
        return s
    import re

    # eliminar caracteres de control no imprimibles excepto \n y \t
    s = re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f]', ' ', s)
    # escapar backslashes simples para evitar escapes inválidos en JSON
    # (doblar todas las barras invertidas)
    s = s.replace('\\', '\\\\')
    # normalizar espacios múltiples
    s = re.sub(r'[ \t]+', ' ', s)
    return s.strip()


def _record_structuring_telemetry(provider: str, prompt_tokens: int, completion_tokens: int, model: str | None = None) -> None:
    """Persistir consumo de la etapa de estructuración LLM por día/backend.

    Usa el mismo formato de `~/.ocr_glm_telemetry.json` que consume la UI:
      {"YYYY-MM-DD": {"backend": {"prompt": int, "completion": int, "calls": int}}}
    """
    try:
        pt = int(prompt_tokens or 0)
        ct = int(completion_tokens or 0)
    except Exception:
        pt, ct = 0, 0

    if pt <= 0 and ct <= 0:
        return

    backend_key = (model or provider or "structuring").strip().lower()
    if not backend_key:
        backend_key = "structuring"

    day_key = datetime.now().strftime("%Y-%m-%d")
    raw: dict = {}
    try:
        if _TELE_FILE.exists():
            raw = json.loads(_TELE_FILE.read_text(encoding="utf-8")) or {}
            if not isinstance(raw, dict):
                raw = {}
    except Exception:
        raw = {}

    day_entry = raw.get(day_key)
    if not isinstance(day_entry, dict):
        day_entry = {}

    backend_entry = day_entry.get(backend_key)
    if not isinstance(backend_entry, dict):
        backend_entry = {"prompt": 0, "completion": 0, "calls": 0}

    backend_entry["prompt"] = int(backend_entry.get("prompt", 0) or 0) + pt
    backend_entry["completion"] = int(backend_entry.get("completion", 0) or 0) + ct
    backend_entry["calls"] = int(backend_entry.get("calls", 0) or 0) + 1

    day_entry[backend_key] = backend_entry
    raw[day_key] = day_entry

    try:
        _TELE_FILE.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def _build_structuring_prompt(base_prompt: str | None, expected_keys: list[str] | None) -> str:
    """Construye prompt de estructuración para convertir markdown OCR a JSON."""
    prompt = (base_prompt or "").strip()
    if expected_keys:
        _float_hints = {"subtotal", "descuento", "impuestos", "total"}
        schema = {k: ("float" if k in _float_hints else "string") for k in expected_keys}
        schema_str = json.dumps(schema, ensure_ascii=False)
        forced = (
            "Eres un motor de extracción de datos para documentos OCR. "
            "Devuelve ÚNICAMENTE un objeto JSON válido, sin texto adicional, "
            "sin markdown y sin bloques de código. "
            f"Usa exactamente este esquema: {schema_str}. "
            "Si no encuentras un valor, usa null."
        )
        return f"{forced}\n\n{prompt}" if prompt else forced

    if prompt:
        return prompt
    return (
        "Eres un motor de extracción de datos para OCR. "
        "Devuelve solo JSON válido con los campos clave de la factura: "
        "fecha, numero_factura, emisor, subtotal, impuestos, total."
    )


def _load_prompt_from_profile(active_profile: str | None) -> str:
    if not active_profile:
        return ""
    try:
        from src.core.prompt_manager import load_render_prompt

        rendered, _used_name, _checksum = load_render_prompt([active_profile], {})
        return rendered or ""
    except Exception:
        return ""


def _resolve_prompt_template_content(prompt_template: str | None) -> str:
    """Resuelve contenido de prompt desde texto inline o nombre de plantilla."""
    raw = (prompt_template or "").strip()
    if not raw:
        return ""
    if "\n" in raw or "{" in raw:
        return raw
    return _load_prompt_from_profile(raw)


def _extract_schema_keys_from_prompt(prompt: str | None) -> list[str] | None:
    """Intenta extraer una definición de esquema (JSON object/array) embebida en el prompt.

    Soporta JSON con comentarios de línea (//) como los que usan los prompts
    de usuario. Retorna lista de claves si se detecta un objeto con ≥3 claves,
    o None.
    """
    if not prompt:
        return None
    try:
        import re

        # Estrategia 1: eliminar comentarios // y parsear JSON
        cleaned = re.sub(r"[ \t]*//[^\n]*", "", prompt)
        # Intentar JSON array primero, luego objeto simple
        for pat in [
            r"\[\s*\{([\s\S]*?)\}\s*\]",  # array con un objeto
            r"\{([\s\S]*?)\}",              # objeto suelto
        ]:
            m = re.search(pat, cleaned)
            if m:
                block = m.group(0)
                try:
                    parsed = json.loads(block)
                    if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
                        keys = list(parsed[0].keys())
                        if len(keys) >= 3:
                            return keys
                    elif isinstance(parsed, dict) and len(parsed) >= 3:
                        return list(parsed.keys())
                except Exception:
                    pass

        # Estrategia 2: regex directa sobre "clave": en el prompt original
        # (funciona aunque el JSON tenga comentarios o sea inválido)
        keys_found = re.findall(r'"([^"\n]{1,60})"\s*:', prompt)
        if keys_found:
            seen: list[str] = []
            for k in keys_found:
                if k not in seen:
                    seen.append(k)
            if len(seen) >= 3:
                return seen
    except Exception:
        pass
    return None


def _maybe_structure_with_llm(
    raw_text: str,
    expected_keys: list[str] | None = None,
    structuring_provider: str | None = None,
    structuring_api_key: str | None = None,
    structuring_model: str | None = None,
    structuring_base_url: str | None = None,
    prompt_template: str | None = None,
) -> dict:
    """Usa el proveedor de razonamiento para convertir markdown OCR a JSON."""
    if not (raw_text or "").strip():
        return {}

    cfg = _load_user_config()
    provider = (structuring_provider or cfg.get("reason_provider") or "").strip()
    if not provider:
        return {}

    api_key = (structuring_api_key or cfg.get("reason_token") or "").strip()
    model = (structuring_model or cfg.get("reason_model") or "").strip()
    base_url = (structuring_base_url or cfg.get("reason_base_url") or "").strip()

    if not api_key:
        provider_lower = provider.lower()
        key_map = {
            "deepseek": "DEEPSEEK_API_KEY",
            "google gemini flash (gratuito)": "GEMINI_API_KEY",
            "google gemini pro": "GEMINI_API_KEY",
            "openai gpt-4o": "OPENAI_API_KEY",
            "qwen (alibaba cloud)": "DASHSCOPE_API_KEY",
            "mistral large": "MISTRAL_API_KEY",
            "openrouter": "OPENROUTER_API_KEY",
            "anthropic (claude 3.5)": "OPENROUTER_API_KEY",
            "glm-4 (zhipuai)": "ZHIPUAI_API_KEY",
            "azure openai": "AZURE_OPENAI_API_KEY",
        }
        env_name = key_map.get(provider_lower)
        if env_name:
            api_key = (os.environ.get(env_name) or "").strip()

    if not api_key and provider.lower() not in {"ollama (local)", "lm studio (local)"}:
        return {}

    base_prompt = _resolve_prompt_template_content(prompt_template)
    if base_prompt:
        # Si el llamante pasó un prompt_template, respetarlo tal cual (sin
        # forzar esquemas ni añadir texto adicional). El prompt puede variar
        # según el tipo de documento y debe ser usado exactamente.
        prompt = base_prompt
    else:
        active_profile = cfg.get("active_prompt_profile") or cfg.get("default_template")
        base_prompt = _load_prompt_from_profile(active_profile)
        prompt = _build_structuring_prompt(base_prompt, expected_keys)

    try:
        from src.core.structuring_engine import StructuringEngine

        logger.info(
            "Export structuring: provider=%s model=%s prompt_len=%d raw_len=%d",
            provider,
            model or "default",
            len(prompt),
            len(raw_text),
        )
        engine = StructuringEngine(
            provider=provider,
            api_key=api_key,
            model=model,
            base_url=base_url,
        )
        # Sanitizar el texto OCR antes de enviarlo al LLM para evitar
        # escapes inválidos y caracteres de control que pueden romper JSON.
        sanitized = _sanitize_ocr_text_for_prompt(raw_text or "")
        structured_text, _pt, _ct = engine.structure(sanitized, prompt)
        # Opcional: capturar sidecars de LLM para tests/diagnóstico cuando
        # la variable de entorno `OCR_TEST_CAPTURE` está activada.
        try:
            cap = (os.environ.get("OCR_TEST_CAPTURE") or "").lower()
            if cap in ("1", "true", "yes"):
                out_root = Path.cwd() / "output" / "llm_captures"
                out_root.mkdir(parents=True, exist_ok=True)
                # nombre determinístico por hash del texto y timestamp
                h = hashlib.sha1((raw_text or "").encode("utf-8")).hexdigest()[:10]
                ts = _timestamp()
                stem = f"{provider.replace(' ','_')}_{h}_{ts}"
                # raw response
                try:
                    (out_root / f"{stem}__raw.txt").write_text(str(structured_text or ""), encoding="utf-8")
                except Exception:
                    pass
                # parsed JSON (si parsea)
                try:
                    parsed_side = parsed = _parse_glm_response(structured_text or "")
                    (out_root / f"{stem}__parsed.json").write_text(json.dumps(parsed_side, ensure_ascii=False, indent=2), encoding="utf-8")
                except Exception:
                    pass
        except Exception:
            pass
        # Registrar consumo real de la etapa de estructuración (DeepSeek/OpenAI/etc.)
        # para que telemetría no quede en 0 cuando el OCR backend no usa tokens.
        _record_structuring_telemetry(provider, _pt, _ct, model)
        # Log raw LLM response for debugging export issues where structuring
        # parece no aplicarse y Excel queda con campos vacíos.
        try:
            if structured_text:
                logger.info(
                    "LLM raw response (len=%d, pt=%s ct=%s) for provider=%s",
                    len(structured_text),
                    _pt,
                    _ct,
                    provider,
                )
                # Log a short preview of the response to avoid huge logs
                logger.debug("LLM raw preview: %s", (structured_text or "")[:1000])
            else:
                logger.warning("LLM returned empty response for provider=%s", provider)
        except Exception:
            pass
        parsed = _parse_glm_response(structured_text or "")
        if not parsed:
            logger.warning(
                "LLM returned content but parsing failed (provider=%s). Raw len=%d",
                provider,
                len(structured_text or ""),
            )
        return parsed
    except Exception as exc:
        logger.warning("Estructuración LLM en export falló (%s): %s", provider, exc)
        return {}


def _heuristic_from_raw(raw: str) -> dict:
    """Heurísticas simples para extraer campos críticos desde texto crudo.

    Devuelve dict con claves `numero_factura`, `fecha_emision`, `total`, `proveedor` cuando se detectan.
    """
    import re

    out = {"numero_factura": None, "fecha_emision": None, "total": None, "proveedor": None}
    if not raw:
        return out

    # número factura (incluir variantes como 'Cash Inv No.' y 'Cash Invoice No.')
    patterns_no = [
        r"Invoice\s*No[:\s]*([A-Z0-9\-_/]+)",
        r"Invoice\s*#[:\s]*([A-Z0-9\-_/]+)",
        r"Invoice\s*No\s*[:\s]*([A-Z0-9\-_/]+)",
        r"Cash\s+Inv\s+No[:\.\s]*([A-Z0-9\-_/]+)",
        r"Cash\s+Invoice\s+No[:\.\s]*([A-Z0-9\-_/]+)",
        r"Número\s*de\s*factura[:\s]*([A-Z0-9\-_/]+)",
        r"Factura\s*[:#]?\s*([A-Z0-9\-_/]+)",
        r"Invoice\s+No\s*[:]?[\s]*([A-Z0-9\-_/]+)",
    ]
    for p in patterns_no:
        m = re.search(p, raw, re.IGNORECASE)
        if m:
            out["numero_factura"] = m.group(1).strip()
            break

    # fecha
    date_patterns = [r"(\d{4}-\d{2}-\d{2})", r"(\d{2}/\d{2}/\d{4})", r"(\d{2}\.\d{2}\.\d{4})",
                     r"(\d{1,2}\s+[A-Za-z]+\s+\d{4})"]
    for p in date_patterns:
        m = re.search(p, raw)
        if m:
            out["fecha_emision"] = m.group(1).strip()
            break

    # total (buscar la última aparición de 'total' con número). Cubrir variantes como
    # 'Total Payable', 'Total Payable:', 'Total 0% supplies:' etc.
    num_pat = r"([\d]{1,3}(?:[\.,][\d]{3})*(?:[\.,][\d]{2})?)"
    total_patterns = [
        rf"(?i)Total(?:\s+[A-Za-z]+){{0,3}}\s*[:\-]?\s*{num_pat}",
        rf"(?i)Total\s*Payable(?:\s+[A-Za-z]+)?[:\s]*{num_pat}",
        rf"(?i)Total\s*\d?%\s*supplies[:\s]*{num_pat}",
        rf"(?i)Total\s*Inclusive\s*GST[:\s]*{num_pat}",
    ]
    for p in total_patterns:
        ms = list(re.finditer(p, raw, re.IGNORECASE))
        if ms:
            m = ms[-1]
            val = m.group(1).replace(" ","").replace(",",".")
            try:
                out["total"] = float(val)
            except Exception:
                out["total"] = val
            break

    # proveedor: primera línea en mayúsculas o 'OJC MARKETING SDN BHD' style
    try:
        lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
        if lines:
            # prefer lines before 'Invoice' header
            for ln in lines[:10]:
                if 'invoice' in ln.lower() or 'tax invoice' in ln.lower():
                    break
                # heurística: cadena con palabras en mayúscula y espacios
                if ln.isupper() and len(ln.split()) <= 6:
                    out["proveedor"] = ln
                    break
            if not out["proveedor"]:
                # fallback: primera non-empty line
                out["proveedor"] = lines[0]
    except Exception:
        pass

    return out


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _sanitize_for_excel(value: Any) -> Any:
    """Recursively sanitize values to prevent CSV/Excel injection.

    If a string starts with one of = + - @ it is prefixed with an apostrophe.
    Works recursively for dicts and lists.
    """
    if isinstance(value, str):
        if value and value[0] in ("=", "+", "-", "@"):
            return "'" + value
        return value
    if isinstance(value, dict):
        return {k: _sanitize_for_excel(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize_for_excel(v) for v in value]
    return value


def _normalize_llm_keys(parsed: dict) -> dict:
    """Normaliza claves frecuentes devueltas por LLM a las claves en español
    que usa el esquema del proyecto. No elimina claves desconocidas, solo
    añade alias para incrementar tasa de acierto en el filtrado final.
    """
    if not isinstance(parsed, dict):
        return parsed

    mapping = {
        # fechas
        "invoice_date": "fecha_emision",
        "invoice_time": "hora_emision",
        "due_date": "fecha_vencimiento",
        # totales
        "grand_total": "total",
        "total_including_tax": "total",
        "total_excluding_tax": "subtotal",
        "total_amount": "total",
        "total_quantity": "cantidad_total",
        "tax_amount": "iva",
        "tax_rate_percentage": "iva_porcentaje",
        "gst_percentage": "iva_porcentaje",
        "payment_amount": "total_pagado",
        "payment_method": "metodo_pago",
        "rounding_amount": "redondeo",
        # proveedor / emisor
        "company_name": "proveedor",
        "company_registration": "nif_proveedor",
        "company_registration_number": "nif_proveedor",
        "company_address": "direccion_proveedor",
        "address": "direccion_proveedor",
        "company_phone": "telefono_proveedor",
        # invoice identifiers
        "invoice_number": "numero_factura",
        "invoice_no": "numero_factura",
        "bill_to": "cliente",
        "sales_person": "vendedor",
        # items
        "items": "lineas",
        "description": "descripcion",
        "sku": "sku",
        "product_code": "sku",
        "quantity": "cantidad",
        "unit_price": "precio_unitario",
        "amount": "importe",
        # otros observados en logs
        "date": "fecha_emision",
        "client_name": "proveedor",
        "business_name": "proveedor",
        "gst_amount": "iva",
        "gst_id": "nif_proveedor",
        "gst_number": "nif_proveedor",
        "seller": "proveedor",
        "buyer": "cliente",
        "code": "sku",
        "item_code": "sku",
        "total": "total",
        "total_including_gst": "total",
        "total_including_tax": "total",
        "total_excluding_gst": "subtotal",
        "total_excluding_tax": "subtotal",
        "total_gst": "iva",
        "total_amount": "total",
        "subtotal": "subtotal",
        # campos directos del LLM que faltaban en el mapa
        "tax": "iva",
        "supplier": "proveedor",
        "currency": "moneda",
    }

    out = dict(parsed)
    try:
        for k, v in list(parsed.items()):
            kl = str(k).strip()
            lk = kl.lower()
            if lk in mapping:
                tgt = mapping[lk]
                # no sobreescribir si ya existe el valor objetivo
                if tgt not in out or not out.get(tgt):
                    out[tgt] = parsed.get(k)
    except Exception:
        return parsed
    # Manejo de estructuras anidadas observadas (seller/buyer/items)
    try:
        header = parsed.get("header")
        if isinstance(header, dict):
            nested_header = {
                "invoice_number": "numero_factura",
                "date": "fecha_emision",
                "invoice_date": "fecha_emision",
                "supplier_name": "proveedor",
                "supplier_tax_id": "nif_proveedor",
                "supplier_address": "direccion_proveedor",
                "buyer_name": "cliente",
                "cashier": "cajero",
                "salesperson": "vendedor",
                "pos_number": "pos_numero",
                "store_number": "tienda_numero",
                "payment_method": "metodo_pago",
                "cash_tendered": "efectivo_recibido",
                "change": "cambio",
                "rounding": "redondeo",
                "loyalty_points_used": "puntos_fidelidad",
                "loyalty_program": "programa_fidelidad",
                # campos del prompt de Malasia
                "subtotal_net": "subtotal",
                "tax_amount": "iva",
                "total_gross": "total",
            }
            for src, tgt in nested_header.items():
                if not out.get(tgt):
                    value = header.get(src)
                    if value is not None and (not isinstance(value, str) or value.strip()):
                        out[tgt] = value

        financials = parsed.get("financials")
        if isinstance(financials, dict):
            nested_financials = {
                "subtotal_excluding_tax": "subtotal",
                "discount": "descuento",
                "tax_amount": "iva",
                "tax_rate": "iva_porcentaje",
                "total_amount": "total",
            }
            for src, tgt in nested_financials.items():
                if not out.get(tgt):
                    value = financials.get(src)
                    if value is not None and (not isinstance(value, str) or value.strip()):
                        out[tgt] = value

        contact = parsed.get("contact")
        if isinstance(contact, dict):
            if not out.get("telefono_proveedor") and contact.get("phone"):
                out["telefono_proveedor"] = contact.get("phone")
            if not out.get("fax_proveedor") and contact.get("fax"):
                out["fax_proveedor"] = contact.get("fax")
            if not out.get("email_proveedor") and contact.get("email"):
                out["email_proveedor"] = contact.get("email")

        invoice = parsed.get("invoice")
        if isinstance(invoice, dict):
            nested_invoice = {
                "number": "numero_factura",
                "date": "fecha_emision",
                "time": "hora_emision",
                "cashier": "cajero",
                "sales_person": "vendedor",
                "type": "tipo_factura",
            }
            for src, tgt in nested_invoice.items():
                if not out.get(tgt):
                    value = invoice.get(src)
                    if value is not None and (not isinstance(value, str) or value.strip()):
                        out[tgt] = value

        summary = parsed.get("summary")
        if isinstance(summary, dict):
            nested_summary = {
                "total_amount": "subtotal",
                "grand_total": "total",
                "total_discount": "descuento",
                "total_item_discount": "descuento",
                "round_adjustment": "redondeo",
                "round_amount": "redondeo",
                "total_quantity": "cantidad_total",
            }
            for src, tgt in nested_summary.items():
                if not out.get(tgt):
                    value = summary.get(src)
                    if value is not None and (not isinstance(value, str) or value.strip()):
                        out[tgt] = value

        payment = parsed.get("payment")
        if isinstance(payment, dict):
            nested_payment = {
                "method": "metodo_pago",
                "amount": "total_pagado",
                "approval_code": "codigo_aprobacion",
            }
            for src, tgt in nested_payment.items():
                if not out.get(tgt):
                    value = payment.get(src)
                    if value is not None and (not isinstance(value, str) or value.strip()):
                        out[tgt] = value

        gst_summary = parsed.get("gst_summary")
        if isinstance(gst_summary, list) and gst_summary:
            out["gst_summary"] = gst_summary

        # seller puede venir como dict
        seller = parsed.get("seller") or parsed.get("vendor")
        if isinstance(seller, dict):
            if not out.get("proveedor"):
                name = seller.get("name") or seller.get("business_name") or seller.get("company_name")
                if name:
                    out["proveedor"] = name
            if not out.get("nif_proveedor"):
                nif = seller.get("gst_number") or seller.get("registration_number") or seller.get("company_registration_number")
                if nif:
                    out["nif_proveedor"] = nif

        # buyer as cliente
        buyer = parsed.get("buyer")
        if isinstance(buyer, dict) and not out.get("cliente"):
            bname = buyer.get("name") or buyer.get("business_name")
            if bname:
                out["cliente"] = bname

        # items: normalizar claves internas
        items = parsed.get("items") or parsed.get("lineas")
        if isinstance(items, list):
            norm_items = []
            for it in items:
                if not isinstance(it, dict):
                    norm_items.append(it)
                    continue
                nit = dict(it)
                # cantidades
                if "quantity" in it and "cantidad" not in nit:
                    nit["cantidad"] = it.get("quantity")
                if "original_quantity" in it and "cantidad_original" not in nit:
                    nit["cantidad_original"] = it.get("original_quantity")
                if "corrected_quantity" in it and "cantidad" not in nit:
                    nit["cantidad"] = it.get("corrected_quantity")
                if "unit_price" in it and "precio_unitario" not in nit:
                    nit["precio_unitario"] = it.get("unit_price")
                if "amount" in it and "line_total" not in nit:
                    nit["line_total"] = it.get("amount")
                if "total" in it and "line_total" not in nit:
                    nit["line_total"] = it.get("total")
                if "raw_line" in it and "raw_line" not in nit:
                    nit["raw_line"] = it.get("raw_line")
                if "tax_code" in it and "tax_code" not in nit:
                    nit["tax_code"] = it.get("tax_code")
                if "code" in it and "sku" not in nit:
                    nit["sku"] = it.get("code")
                if "item_code" in it and "sku" not in nit:
                    nit["sku"] = it.get("item_code")
                norm_items.append(nit)
            out["lineas"] = norm_items
    except Exception:
        pass
    return out


def _parse_glm_response(raw: str) -> dict:
    """Intentar extraer y parsear el primer objeto JSON contenido en la respuesta.

    Busca la primera llave '{' y encuentra su cierre balanceado. Si no encuentra
    un JSON válido, registra el error y devuelve {}.
    """
    if not raw:
        return {}

    # 1) Si el contenido ya es JSON completo, usarlo tal cual.
    stripped = raw.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        try:
            parsed_direct = json.loads(stripped)
            if isinstance(parsed_direct, dict) and parsed_direct:
                return parsed_direct
        except Exception:
            pass

    # 1.5) Si el LLM devolvió un JSON array ([{...}]), extraer el primer objeto
    # directamente. IMPORTANTE: esto debe ejecutarse ANTES del MistralMarkdownParser
    # para evitar que el parser de markdown reinterprete la respuesta del LLM con
    # claves normalizadas distintas (e.g. "numero_factura" en vez de "Número Factura"),
    # lo que provoca que todos los campos del esquema queden como None en el Excel.
    if stripped.startswith("["):
        try:
            parsed_arr = json.loads(stripped)
            if isinstance(parsed_arr, list) and parsed_arr and isinstance(parsed_arr[0], dict):
                first = parsed_arr[0]
                if first:
                    return first
        except Exception:
            pass
        # Si json.loads falló, buscar el primer objeto dentro del array
        try:
            brace_start = stripped.find("{")
            if brace_start != -1:
                depth = 0
                brace_end = -1
                for i in range(brace_start, len(stripped)):
                    ch = stripped[i]
                    if ch == "{":
                        depth += 1
                    elif ch == "}":
                        depth -= 1
                        if depth == 0:
                            brace_end = i
                            break
                if brace_end != -1:
                    candidate = stripped[brace_start:brace_end + 1]
                    parsed_inner = json.loads(candidate)
                    if isinstance(parsed_inner, dict) and parsed_inner:
                        return parsed_inner
        except Exception:
            pass

    # 2) Intentar parser especializado de markdown/recibos (Mistral OCR).
    # NOTA: solo debe usarse para texto OCR crudo (markdown), no para respuestas
    # JSON del LLM (que ya fueron tratadas en los pasos anteriores).
    try:
        from src.core.mistral_markdown_parser import MistralMarkdownParser

        parsed_md = MistralMarkdownParser().parse_invoice(raw, country_hint="auto")
        if isinstance(parsed_md, dict) and parsed_md:
            # Aceptar si hay señales útiles (fecha/total/proveedor/líneas, etc.).
            if any(parsed_md.get(k) is not None for k in (
                "numero_factura", "invoice_number", "fecha", "date",
                "total", "subtotal", "impuestos", "proveedor", "supplier", "lineas", "items"
            )):
                return parsed_md
    except Exception:
        pass

    # 3) Buscar primer '{' y parsear el primer objeto balanceado.
    start = raw.find("{")
    if start == -1:
        logger.debug("No se encontró '{' en la respuesta GLM")
        return {}

    depth = 0
    end = -1
    for i in range(start, len(raw)):
        ch = raw[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i
                break

    if end == -1:
        logger.error("No se pudo localizar el cierre del JSON en la respuesta GLM")
        return {}

    candidate = raw[start:end+1]
    try:
        parsed = json.loads(candidate)
        if isinstance(parsed, dict):
            return parsed
        logger.error("JSON parseado no es un dict: %s", type(parsed))
        return {}
    except Exception as exc:
        logger.error("Fallo parseando JSON extraído: %s — contenido: %s", exc, candidate[:200])
        # Intentar reparar escapes inválidos comunes (ej: 'bad escape \i')
        try:
            import re as _re
            # Doblar backslashes que no forman secuencias de escape válidas
            candidate_fixed = _re.sub(r'\\(?!["\\\/bfnrtu])', r'\\\\', candidate)
            parsed2 = json.loads(candidate_fixed)
            if isinstance(parsed2, dict):
                return parsed2
        except Exception as exc2:
            logger.debug("Reparación heurística de JSON falló: %s", exc2)
        # Si no se pudo parsear JSON, intentar heurística avanzada (markdown/table)
        try:
            from src.core.invoice_parser import parse_invoice_text
            fallback = parse_invoice_text(raw)
            if isinstance(fallback, dict) and fallback:
                return fallback
        except Exception:
            pass
        return {}


def _flatten_taxes(data_dict: dict) -> None:
    """Extrae entradas de 'desglose_impuestos' y las convierte en claves planas.

    Para cada item en la lista espera keys: 'tasa_porcentaje', 'base_imponible', 'monto_impuesto'.
    Añade claves dinámicas en el nivel raíz:
      base_imponible_iva_{tasa} -> base_imponible
      monto_iva_{tasa} -> monto_impuesto

    Finalmente elimina 'desglose_impuestos' del diccionario original si existe.
    """
    if not isinstance(data_dict, dict):
        return
    taxes = data_dict.get("desglose_impuestos")
    if not taxes or not isinstance(taxes, list):
        return

    for item in taxes:
        try:
            tasa = item.get("tasa_porcentaje")
            # normalizar la tasa a un token seguro para clave (ej: 21, 21_5)
            if tasa is None:
                continue
            # convertir a string y reemplazar coma/punto por underscore
            tasa_str = str(tasa).replace(",", "_").replace(".", "_")
            base = item.get("base_imponible")
            monto = item.get("monto_impuesto")
            data_dict[f"base_imponible_iva_{tasa_str}"] = base
            data_dict[f"monto_iva_{tasa_str}"] = monto
        except Exception:
            continue

    # eliminar la lista original para evitar columnas anidadas
    try:
        del data_dict["desglose_impuestos"]
    except Exception:
        pass


def _flatten_results(results: list[dict]) -> list[dict]:
    """Aplana resultados usando JSON válido en `text` cuando existe.

    Genera columnas dinámicas según las claves del JSON extraído.
    """
    flat_rows: list[dict] = []
    for doc in results:
        meta = {
            "id": doc.get("id"),
            "archivo": doc.get("filename"),
            "paginas": doc.get("pages"),
            "confianza": round(doc.get("confidence", 0) * 100, 1),
            "estado": doc.get("status"),
        }
        payload: dict = {}
        text_val = doc.get("text", "")
        if isinstance(text_val, str):
            stripped = text_val.strip()
            if stripped.startswith("{") and stripped.endswith("}"):
                try:
                    parsed = json.loads(stripped)
                    if isinstance(parsed, dict):
                        payload = parsed
                except Exception:
                    payload = {}
        row = {**meta, **payload} if payload else {**meta, "raw_text": text_val}
        flat_rows.append(_sanitize_for_excel(row))
    return flat_rows


def _prepare_rows(
    results: list[dict],
    expected_keys: list[str] | None = None,
    structuring_provider: str | None = None,
    structuring_api_key: str | None = None,
    structuring_model: str | None = None,
    structuring_base_url: str | None = None,
    prompt_template: str | None = None,
) -> list[dict]:
    """Convierte la lista original en filas aplanadas y sanitizadas.

    Para cada documento intenta parsear `text` como JSON estructurado; si lo
    consigue, fusiona la metadata y el JSON. Si no, deja el texto en
    `raw_text`.

    Si se pasan ``expected_keys``, solo se incluyen esas claves del JSON
    parseado (elimina columnas vacías/no solicitadas del export).
    """
    rows: list[dict] = []
    # Resolver prompt_template para detectar si contiene un esquema embebido.
    enforced_prompt_keys = None
    try:
        resolved_prompt = _resolve_prompt_template_content(prompt_template)
        enforced_prompt_keys = _extract_schema_keys_from_prompt(resolved_prompt)
    except Exception:
        enforced_prompt_keys = None

    for doc in results:
        meta = {
            "id": doc.get("id"),
            "archivo": doc.get("filename"),
            "paginas": doc.get("pages"),
            "confianza": round(doc.get("confidence", 0) * 100, 1),
            "estado": doc.get("status"),
        }
        raw_text = doc.get("text", "")
        parsed_heuristic = _parse_glm_response(raw_text)
        # Normalizar claves heurísticas temprano para que la fusión con LLM
        # compare claves en el mismo espacio de nombres (español).
        try:
            if parsed_heuristic:
                parsed_heuristic = _normalize_llm_keys(parsed_heuristic)
        except Exception:
            pass

        # La etapa 2 (LLM) debe ser prioritaria cuando hay proveedor configurado,
        # para estructurar según el prompt del proyecto.
        parsed_llm = _maybe_structure_with_llm(
            raw_text,
            expected_keys=expected_keys,
            structuring_provider=structuring_provider,
            structuring_api_key=structuring_api_key,
            structuring_model=structuring_model,
            structuring_base_url=structuring_base_url,
            prompt_template=prompt_template,
        )

        # Si el prompt inline contiene un esquema explícito, respetarlo
        # exactamente: no mezclar con heurísticas y no normalizar claves.
        enforce_schema = bool(enforced_prompt_keys)

        if not enforce_schema:
            # Normalizar la respuesta LLM antes de fusionar para que sus claves
            # coincidan con las heurísticas y con `expected_keys`.
            try:
                if parsed_llm:
                    parsed_llm = _normalize_llm_keys(parsed_llm)
            except Exception:
                pass

        # Relleno automático de campos críticos si el LLM devuelve null/vacío.
        try:
            criticals = ["numero_factura", "fecha_emision", "total", "proveedor"]
            # aplicar heurística a raw_text y parsed_heuristic
            heur_full = parsed_heuristic or {}
            heur_from_raw = _heuristic_from_raw(raw_text)
            if parsed_llm:
                for c in criticals:
                    v = parsed_llm.get(c) if isinstance(parsed_llm, dict) else None
                    if v is None or (isinstance(v, str) and not v.strip()):
                        # intentar from parsed_heuristic
                        candidate = None
                        if isinstance(heur_full, dict) and heur_full.get(c):
                            candidate = heur_full.get(c)
                        if not candidate and heur_from_raw.get(c):
                            candidate = heur_from_raw.get(c)
                        if candidate is not None:
                            try:
                                parsed_llm[c] = candidate
                            except Exception:
                                pass
            else:
                # si no hay LLM, rellenar parsed desde heurísticas sencillas
                parsed_llm = dict(heur_full or {})
                for k, v in heur_from_raw.items():
                    if v is not None and not parsed_llm.get(k):
                        parsed_llm[k] = v
        except Exception:
            pass

        if enforce_schema:
            # Si el prompt pedía un esquema, usar únicamente la salida LLM
            # (si existe) y filtrar solo las claves solicitadas.
            parsed = parsed_llm or {}
        elif parsed_llm and parsed_heuristic:
            # Fusionar preservando información heurística: solo sobrescribir
            # con valores no nulos/devueltos por el LLM. Esto evita perder
            # datos que el LLM dejó como null o vacíos.
            parsed = dict(parsed_heuristic)
            try:
                for k, v in parsed_llm.items():
                    if v is None:
                        continue
                    # tratar cadenas vacías como 'ausente'
                    if isinstance(v, str) and not v.strip():
                        continue
                    parsed[k] = v
            except Exception:
                # en caso de error, caer al comportamiento previo (LLM sobre todo)
                parsed = {**parsed_heuristic, **parsed_llm}
        elif parsed_llm:
            parsed = parsed_llm
        else:
            parsed = parsed_heuristic

        try:
            logger.debug(
                "Prepare row: file=%s llm=%s heuristic=%s",
                meta.get("archivo") or "",
                bool(parsed_llm),
                bool(parsed_heuristic),
            )
        except Exception:
            pass

        if parsed:
            # Si hay esquema activo (prompt inline con claves explícitas), NO
            # normalizar claves — el LLM fue instruido con las claves exactas;
            # normalizarlas las destruiría. Solo normalizar en modo legacy.
            if not enforce_schema:
                try:
                    parsed = _normalize_llm_keys(parsed)
                except Exception:
                    pass
            # Preferir las claves de esquema embebido en el prompt si existen
            if enforced_prompt_keys:
                parsed = {k: parsed.get(k) for k in enforced_prompt_keys}
                # "Nombre archivo" nunca aparece en el OCR; tomarlo del nombre
                # real del fichero que viene en los metadatos del resultado.
                if "Nombre archivo" in enforced_prompt_keys and not parsed.get("Nombre archivo"):
                    parsed["Nombre archivo"] = meta.get("archivo", "")
            elif expected_keys:
                parsed = {k: parsed.get(k) for k in expected_keys}

            # Intentar convertir cadenas numéricas a float para campos que
            # parecen numéricos (ej: 'subtotal','iva','total').
            try:
                for k, v in list(parsed.items()):
                    if v is None:
                        continue
                    if isinstance(v, str):
                        vv = v.replace(" ", "").replace("€", "").replace(",", ".")
                        try:
                            if vv.replace('.', '', 1).isdigit():
                                parsed[k] = float(vv)
                        except Exception:
                            pass
            except Exception:
                pass
            merged = {**meta, **parsed, "ocr_markdown": raw_text}
            # Aplanar desglose de impuestos si existe
            try:
                _flatten_taxes(merged)
            except Exception:
                pass
        else:
            merged = {**meta, "raw_text": raw_text, "ocr_markdown": raw_text}

        # Sanitizar para Excel/CSV
        safe = _sanitize_for_excel(merged)
        rows.append(safe)
    return rows


def _write_mistral_sidecars(out_dir: Path, stem: str, raw: str) -> None:
    """Escribe sidecar markdown crudo de Mistral.

    Requisito de negocio: no generar sidecar JSON en este flujo.
    """
    ts = _timestamp()
    md_path = out_dir / f"{stem}_{ts}__mistral.md"

    try:
        md_path.write_text(raw or "", encoding="utf-8")
    except Exception:
        pass


def _write_preview_sidecar(out_path: Path, rows: list[dict]) -> None:
    """Escribe un archivo de texto resumen junto al `out_path` para que el
    `PreviewPanel` pueda mostrar un contenido inmediato si no puede renderizar
    el formato nativo (Excel/CSV/DOCX).
    """
    try:
        preview_path = out_path.with_suffix(out_path.suffix + ".preview.txt")
        # prefer human readable summary: if rows present, dump first row keys/values
        if rows and isinstance(rows, list):
            first = rows[0]
            lines = [f"Archivo: {out_path.name}", "Resumen (primer registro):"]
            for k, v in list(first.items())[:40]:
                try:
                    lines.append(f"{k}: {v}")
                except Exception:
                    lines.append(f"{k}: (no serializable)")
            preview_path.write_text("\n".join(lines), encoding="utf-8")
            return
        # fallback: small JSON dump of rows
        preview_path.write_text(json.dumps(rows or {}, ensure_ascii=False, indent=2)[:12000], encoding="utf-8")
    except Exception:
        pass


def export_to_xlsx(
    results: list[dict],
    out_dir: Path,
    merge: bool = True,
    expected_keys: list[str] | None = None,
    structuring_provider: str | None = None,
    structuring_api_key: str | None = None,
    structuring_model: str | None = None,
    structuring_base_url: str | None = None,
    prompt_template: str | None = None,
) -> list[str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = _prepare_rows(
        results,
        expected_keys,
        structuring_provider=structuring_provider,
        structuring_api_key=structuring_api_key,
        structuring_model=structuring_model,
        structuring_base_url=structuring_base_url,
        prompt_template=prompt_template,
    )
    if not rows:
        return []

    df = pd.json_normalize(rows)
    # Detectar columnas de impuestos dinámicas y convertir a numérico + rellenar 0
    tax_cols = [c for c in df.columns if c.startswith("base_imponible_iva_") or c.startswith("monto_iva_")]
    if tax_cols:
        for col in tax_cols:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df[tax_cols] = df[tax_cols].fillna(0)
    # Intentar convertir otras columnas numéricas
    for col in df.columns:
        if col in tax_cols:
            continue
        try:
            df[col] = pd.to_numeric(df[col], errors="ignore")
        except Exception:
            pass

    paths: list[str] = []
    if merge:
        path = out_dir / f"ocr_resultados_{_timestamp()}.xlsx"
        df.to_excel(path, index=False, engine="openpyxl")
        try:
            _write_preview_sidecar(path, rows)
        except Exception:
            pass
        paths.append(str(path))
        # Guardar sidecars por documento: markdown raw y payload JSON
        try:
            for doc in results:
                name = doc.get("filename") or str(doc.get("id") or "doc")
                stem = Path(name).stem
                raw = doc.get("text") or ""
                _write_mistral_sidecars(out_dir, stem, raw)
        except Exception:
            pass
        return paths

    for row in rows:
        name = row.get("archivo") or "doc"
        single_df = pd.json_normalize([row])
        tax_cols_single = [c for c in single_df.columns if c.startswith("base_imponible_iva_") or c.startswith("monto_iva_")]
        if tax_cols_single:
            for col in tax_cols_single:
                single_df[col] = pd.to_numeric(single_df[col], errors="coerce")
            single_df[tax_cols_single] = single_df[tax_cols_single].fillna(0)
        for col in single_df.columns:
            if col in tax_cols_single:
                continue
            try:
                single_df[col] = pd.to_numeric(single_df[col], errors="ignore")
            except Exception:
                pass
        path = out_dir / f"{Path(name).stem}_{_timestamp()}.xlsx"
        single_df.to_excel(path, index=False, engine="openpyxl")
        try:
            _write_preview_sidecar(path, [row])
        except Exception:
            pass
        paths.append(str(path))
        # guardar sidecars para este documento
        try:
            # buscar doc original
            orig = None
            for d in results:
                if (d.get("filename") and Path(d.get("filename")).stem == Path(name).stem) or str(d.get("id") or "") == name:
                    orig = d
                    break
            raw = (orig.get("text") if orig else "") or ""
            _write_mistral_sidecars(out_dir, Path(name).stem, raw)
        except Exception:
            pass
    return paths


def export_to_csv(
    results: list[dict],
    out_dir: Path,
    merge: bool = True,
    expected_keys: list[str] | None = None,
    structuring_provider: str | None = None,
    structuring_api_key: str | None = None,
    structuring_model: str | None = None,
    structuring_base_url: str | None = None,
    prompt_template: str | None = None,
) -> list[str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = _prepare_rows(
        results,
        expected_keys,
        structuring_provider=structuring_provider,
        structuring_api_key=structuring_api_key,
        structuring_model=structuring_model,
        structuring_base_url=structuring_base_url,
        prompt_template=prompt_template,
    )
    if not rows:
        return []

    df = pd.json_normalize(rows)
    # columnas dinámicas de impuestos
    tax_cols = [c for c in df.columns if c.startswith("base_imponible_iva_") or c.startswith("monto_iva_")]
    if tax_cols:
        for col in tax_cols:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df[tax_cols] = df[tax_cols].fillna(0)
    for col in df.columns:
        if col in tax_cols:
            continue
        try:
            df[col] = pd.to_numeric(df[col], errors="ignore")
        except Exception:
            pass

    paths: list[str] = []
    if merge:
        path = out_dir / f"ocr_resultados_{_timestamp()}.csv"
        df.to_csv(path, index=False, encoding="utf-8-sig")
        try:
            _write_preview_sidecar(path, rows)
        except Exception:
            pass
        paths.append(str(path))
        # Guardar sidecars por documento
        try:
            for doc in results:
                name = doc.get("filename") or str(doc.get("id") or "doc")
                stem = Path(name).stem
                raw = doc.get("text") or ""
                _write_mistral_sidecars(out_dir, stem, raw)
        except Exception:
            pass
        return paths

    for row in rows:
        name = row.get("archivo") or "doc"
        single_df = pd.json_normalize([row])
        tax_cols_single = [c for c in single_df.columns if c.startswith("base_imponible_iva_") or c.startswith("monto_iva_")]
        if tax_cols_single:
            for col in tax_cols_single:
                single_df[col] = pd.to_numeric(single_df[col], errors="coerce")
            single_df[tax_cols_single] = single_df[tax_cols_single].fillna(0)
        for col in single_df.columns:
            if col in tax_cols_single:
                continue
            try:
                single_df[col] = pd.to_numeric(single_df[col], errors="ignore")
            except Exception:
                pass
        path = out_dir / f"{Path(name).stem}_{_timestamp()}.csv"
        single_df.to_csv(path, index=False, encoding="utf-8-sig")
        try:
            _write_preview_sidecar(path, [row])
        except Exception:
            pass
        paths.append(str(path))
        # guardar sidecars para este documento
        try:
            orig = None
            for d in results:
                if (d.get("filename") and Path(d.get("filename")).stem == Path(name).stem) or str(d.get("id") or "") == name:
                    orig = d
                    break
            raw = (orig.get("text") if orig else "") or ""
            _write_mistral_sidecars(out_dir, Path(name).stem, raw)
        except Exception:
            pass
    return paths


def export_to_docx(
    results: list[dict],
    out_dir: Path,
    merge: bool = True,
    include_images: bool = True,
    expected_keys: list[str] | None = None,
    structuring_provider: str | None = None,
    structuring_api_key: str | None = None,
    structuring_model: str | None = None,
    structuring_base_url: str | None = None,
    prompt_template: str | None = None,
) -> list[str]:
    from docx import Document
    from docx.shared import RGBColor

    out_dir.mkdir(parents=True, exist_ok=True)
    rows = _prepare_rows(
        results,
        expected_keys,
        structuring_provider=structuring_provider,
        structuring_api_key=structuring_api_key,
        structuring_model=structuring_model,
        structuring_base_url=structuring_base_url,
        prompt_template=prompt_template,
    )
    if not rows:
        return []

    paths: list[str] = []
    def _write_doc(rows_list: list[dict], path: Path) -> None:
        doc = Document()
        doc.add_heading("Resultados OCR — GLM-4V", level=0)
        for entry in rows_list:
            doc.add_heading(f"Documento #{entry.get('id')}: {entry.get('archivo')}", level=1)
            meta = doc.add_paragraph()
            meta.add_run(
                f"Páginas: {entry.get('paginas')}  |  Confianza: {entry.get('confianza')}%  |  Estado: {entry.get('estado')}"
            ).font.color.rgb = RGBColor(0x6B, 0x72, 0x80)
            # Añadir content
            content_keys = [k for k in entry.keys() if k not in ("id","archivo","paginas","confianza","estado")]
            # Si se incluyen imágenes, insertar por página primero
            if include_images and entry.get("images"):
                from docx.shared import Inches

                for img_path in entry.get("images"):
                    try:
                        # Insert image ajustada al ancho máximo razonable (6 inches)
                        doc.add_picture(img_path, width=Inches(6))
                    except Exception:
                        # si no se puede insertar, añadir referencia al path
                        doc.add_paragraph(f"[Imagen no insertada: {img_path}]")

            for k in content_keys:
                doc.add_paragraph(f"{k}: {entry.get(k)}")
            doc.add_paragraph()
        doc.save(path)

    if merge:
        path = out_dir / f"ocr_resultados_{_timestamp()}.docx"
        _write_doc(rows, path)
        paths.append(str(path))
        # Guardar sidecars por documento
        try:
            for doc in results:
                name = doc.get("filename") or str(doc.get("id") or "doc")
                stem = Path(name).stem
                raw = doc.get("text") or ""
                _write_mistral_sidecars(out_dir, stem, raw)
        except Exception:
            pass
        return paths

    for entry in rows:
        p = out_dir / f"{Path(entry.get('archivo') or 'doc').stem}_{_timestamp()}.docx"
        _write_doc([entry], p)
        paths.append(str(p))
        # sidecars
        try:
            name = entry.get("archivo") or "doc"
            orig = None
            for d in results:
                if (d.get("filename") and Path(d.get("filename")).stem == Path(name).stem) or str(d.get("id") or "") == name:
                    orig = d
                    break
            raw = (orig.get("text") if orig else "") or ""
            _write_mistral_sidecars(out_dir, Path(name).stem, raw)
        except Exception:
            pass
    return paths


def export_results(
    results: list[dict],
    output_dir: str,
    fmt: str,
    merge: bool = True,
    include_images: bool = False,
    expected_keys: list[str] | None = None,
    export_profile: str | None = None,
    vendor_master_path: str | None = None,
    structuring_provider: str | None = None,
    structuring_api_key: str | None = None,
    structuring_model: str | None = None,
    structuring_base_url: str | None = None,
    prompt_template: str | None = None,
) -> list[str]:
    out = Path(output_dir)
    f = fmt.upper()
    if f == "XLSX":
        return export_to_xlsx(
            results,
            out,
            merge,
            expected_keys=expected_keys,
            structuring_provider=structuring_provider,
            structuring_api_key=structuring_api_key,
            structuring_model=structuring_model,
            structuring_base_url=structuring_base_url,
            prompt_template=prompt_template,
        )
    if f == "CSV":
        return export_to_csv(
            results,
            out,
            merge,
            expected_keys=expected_keys,
            structuring_provider=structuring_provider,
            structuring_api_key=structuring_api_key,
            structuring_model=structuring_model,
            structuring_base_url=structuring_base_url,
            prompt_template=prompt_template,
        )
    if f == "DOCX":
        return export_to_docx(
            results,
            out,
            merge,
            include_images=include_images,
            expected_keys=expected_keys,
            structuring_provider=structuring_provider,
            structuring_api_key=structuring_api_key,
            structuring_model=structuring_model,
            structuring_base_url=structuring_base_url,
            prompt_template=prompt_template,
        )
    raise ValueError(f"Formato no soportado: {fmt}")


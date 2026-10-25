from __future__ import annotations

import json
import re
from typing import Any


_CURR_RE = re.compile(r"(?i)(rm|myr|usd|eur|sgd|gbp|\$|€|£)")


def _empty_payload(raw_text: str) -> dict[str, Any]:
    return {
        "invoice_number": None,
        "date": None,
        "total": 0.0,
        "currency": None,
        "items": [],
        "raw_text": raw_text,
    }


def _extract_json_block(text: str) -> dict[str, Any] | None:
    raw = (text or "").strip()
    if not raw:
        return None

    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?", "", raw, flags=re.IGNORECASE).strip()
        raw = re.sub(r"```$", "", raw).strip()

    if raw.startswith("{") and raw.endswith("}"):
        try:
            obj = json.loads(raw)
            return obj if isinstance(obj, dict) else None
        except Exception:
            pass

    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        try:
            obj = json.loads(raw[start:end + 1])
            return obj if isinstance(obj, dict) else None
        except Exception:
            return None
    return None


def _normalize_amount(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    txt = str(value).strip()
    if not txt:
        return 0.0
    txt = _CURR_RE.sub("", txt).replace(" ", "")
    if "." in txt and "," in txt:
        if txt.rfind(".") > txt.rfind(","):
            txt = txt.replace(",", "")
        else:
            txt = txt.replace(".", "").replace(",", ".")
    else:
        txt = txt.replace(",", "")
    txt = re.sub(r"[^0-9.\-]", "", txt)
    try:
        return float(txt) if txt else 0.0
    except Exception:
        return 0.0


def _pick_currency(text: str, data: dict[str, Any] | None = None) -> str | None:
    if isinstance(data, dict):
        for k in ("currency", "moneda"):
            v = data.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip().upper()
    m = re.search(r"(?i)\b(MYR|RM|USD|EUR|SGD|GBP)\b|[\$€£]", text or "")
    if not m:
        return None
    token = m.group(0)
    return {"$": "USD", "€": "EUR", "£": "GBP", "RM": "MYR"}.get(token.upper(), token.upper())


def _pick_first(text: str, patterns: list[str]) -> str | None:
    for pat in patterns:
        m = re.search(pat, text, flags=re.IGNORECASE | re.MULTILINE)
        if m:
            value = (m.group(1) or "").strip()
            if value:
                return value
    return None


def parse_invoice_text(text: str) -> dict[str, Any]:
    """Parsea texto OCR/markdown y devuelve esquema estándar en inglés.

    Siempre devuelve:
    {
      "invoice_number": str|None,
      "date": str|None,
      "total": float,
      "currency": str|None,
      "items": list,
      "raw_text": str
    }
    """
    raw = text or ""
    out = _empty_payload(raw)

    # 1) Intentar JSON embebido
    parsed = _extract_json_block(raw)
    if isinstance(parsed, dict):
        out["invoice_number"] = (
            parsed.get("invoice_number")
            or parsed.get("invoice_no")
            or parsed.get("numero_factura")
            or parsed.get("receipt_number")
        )
        out["date"] = (
            parsed.get("date")
            or parsed.get("invoice_date")
            or parsed.get("fecha")
        )
        out["total"] = _normalize_amount(
            parsed.get("total")
            or parsed.get("grand_total")
            or parsed.get("total_amount")
        )
        items = parsed.get("items") or parsed.get("lineas")
        out["items"] = items if isinstance(items, list) else []
        out["currency"] = _pick_currency(raw, parsed)
        return out

    # 2) Fallback Regex Universal
    out["invoice_number"] = _pick_first(
        raw,
        [
            r"Invoice\s*No[:.]?\s*([A-Z0-9\-/]+)",
            r"Receipt\s*Number[:.]?\s*([A-Z0-9\-/]+)",
            r"Tax\s*Invoice\s*No[:.]?\s*([A-Z0-9\-/]+)",
            r"INV[#\s:.-]*([A-Z0-9\-/]+)",
        ],
    )

    out["date"] = _pick_first(
        raw,
        [
            r"Date[:.]?\s*(\d{2}[-/]\d{2}[-/]\d{4})",
            r"\b(\d{4}-\d{2}-\d{2})\b",
            r"\b(\d{2}[-/]\d{2}[-/]\d{4})\b",
        ],
    )

    total_txt = _pick_first(
        raw,
        [
            r"Total\s*(?:RM|\$|€|USD|EUR|MYR)?[:.]?\s*([\d,.]+)",
            r"Amount\s*Due\s*(?:RM|\$|€|USD|EUR|MYR)?[:.]?\s*([\d,.]+)",
            r"Grand\s*Total\s*(?:RM|\$|€|USD|EUR|MYR)?[:.]?\s*([\d,.]+)",
        ],
    )
    out["total"] = _normalize_amount(total_txt)
    out["currency"] = _pick_currency(raw)

    return out

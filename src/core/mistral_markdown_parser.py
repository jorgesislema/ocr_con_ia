from __future__ import annotations

import re
from datetime import datetime
from typing import Any


class MistralMarkdownParser:
    """Parser especializado para facturas internacionales en Markdown."""

    def parse_invoice(self, markdown_text: str, country_hint: str = "auto") -> dict[str, Any]:
        """Extrae campos estructurados de una factura OCR en formato Markdown."""
        text = markdown_text or ""
        hint = (country_hint or "auto").strip().lower()
        if hint == "auto":
            hint = self._detect_country_hint(text)

        result: dict[str, Any] = {
            "numero_factura": None,
            "invoice_number": None,
            "fecha": None,
            "date": None,
            "proveedor": {"nombre": None, "id_fiscal": None},
            "supplier": {"name": None, "registration_no": None, "address": None},
            "customer": {"name": None, "address": None},
            "subtotal": None,
            "total": None,
            "impuestos": None,
            "lineas": [],
            "items": [],
            "totals": {"subtotal": None, "gst_rate": None, "gst_amount": None, "total": None},
            "payment_method": None,
            "country_hint": hint,
        }

        if hint == "malaysia":
            result["numero_factura"] = self._extract_regex(
                text,
                [
                    r"(?im)^\s*TAX\s*INVOICE\s*NO\.?\s*[:#\-]?\s*([A-Z0-9\-/]+)",
                    r"(?im)^\s*INVOICE\s*(?:NO\.?|NUMBER)?\s*[:#\-]?\s*([A-Z0-9\-/]+)",
                    r"(?im)^\s*INV#\s*[:#\-]?\s*([A-Z0-9\-/]+)",
                    r"(?im)^\s*Receipt#\s*[:#\-]?\s*([A-Z0-9\-/]+)",
                ],
            )
            result["subtotal"] = self._extract_float(
                text,
                [
                    r"(?im)^\s*(?:Excluded\s*GST\)?\s*)?Sub\s*Total(?:\s*\(RM\))?\s*[:\-]?\s*([0-9][0-9.,]*)",
                    r"(?im)^\s*Total\s*Exclude\s*GST\s*[:\-]?\s*([0-9][0-9.,]*)",
                    r"(?im)^\s*GST\s*Summary.*?(?:Amount\s*\(RM\)|Amount).*?([0-9][0-9.,]*)\s+[0-9][0-9.,]*\s*$",
                ],
            )
            result["total"] = self._extract_float(
                text,
                [
                    r"(?im)^\s*Total\s*RM(?:\s*inc\.?(?:\s*GST)?)?\s*[:\-]?\s*([0-9][0-9.,]*)",
                    r"(?im)^\s*Grand\s*Total\s*[:\-]?\s*(?:RM\s*)?([0-9][0-9.,]*)",
                    r"(?im)^\s*TakeOut\s*Total\s*\(incl\s*GST\)\s*([0-9][0-9.,]*)",
                    r"(?im)^\s*TOTAL\s*[:\-]?\s*([0-9][0-9.,]*)",
                    r"(?im)^\s*Total\s*\(RM\)\s*[:\-]?\s*([0-9][0-9.,]*)",
                ],
            )
            result["impuestos"] = self._extract_float(
                text,
                [
                    r"(?im)^\s*GST\s*RM\s*[:\-]?\s*([0-9][0-9.,]*)",
                    r"(?im)^\s*(?:GST|SST|TAX)\s*[:\-]?\s*(?:RM\s*)?([0-9][0-9.,]*)",
                    r"(?im)^\s*Total\s*GST(?:\s*@\s*6%)?\s*[:\-]?\s*([0-9][0-9.,]*)",
                    r"(?im)^\s*TOTAL\s*INCLUDES\s*6%\s*GST\s*([0-9][0-9.,]*)",
                ],
            )
        elif hint == "ecuador":
            result["numero_factura"] = self._extract_regex(
                text,
                [
                    r"(?im)^\s*(?:Factura|No\.?\s*Factura|N[oº]\.?\s*Factura)\s*[:#\-]?\s*([A-Z0-9\-/]+)",
                    r"(?im)^\s*Clave\s*de\s*acceso\s*[:#\-]?\s*([0-9]{20,})",
                ],
            )
            result["total"] = self._extract_float(
                text,
                [
                    r"(?im)^\s*Total\s*(?:a\s*pagar)?\s*[:\-]?\s*([0-9][0-9.,]*)",
                    r"(?im)^\s*Importe\s*Total\s*[:\-]?\s*([0-9][0-9.,]*)",
                ],
            )
            result["impuestos"] = self._extract_float(
                text,
                [
                    r"(?im)^\s*IVA\s*(?:12|15)?\s*%?\s*[:\-]?\s*([0-9][0-9.,]*)",
                    r"(?im)^\s*Impuestos\s*[:\-]?\s*([0-9][0-9.,]*)",
                ],
            )
        else:  # europe/general
            result["numero_factura"] = self._extract_regex(
                text,
                [
                    r"(?im)^\s*Invoice\s*(?:No\.?|Number)?\s*[:#\-]?\s*([A-Z0-9\-/]+)",
                    r"(?im)^\s*Document\s*No\.?\s*[:#\-]?\s*([A-Z0-9\-/]+)",
                ],
            )
            result["total"] = self._extract_float(
                text,
                [
                    r"(?im)^\s*(?:Grand\s*)?Total\s*[:\-]?\s*(?:EUR|USD|GBP|\$|€)?\s*([0-9][0-9.,]*)",
                ],
            )
            result["impuestos"] = self._extract_float(
                text,
                [
                    r"(?im)^\s*(?:VAT|TVA|MWST|IVA)\s*[:\-]?\s*([0-9][0-9.,]*)",
                    r"(?im)^\s*Tax\s*[:\-]?\s*([0-9][0-9.,]*)",
                ],
            )

        result["fecha"] = self._extract_date(text)
        result["date"] = result["fecha"]
        result["proveedor"]["nombre"] = self._extract_regex(
            text,
            [
                r"(?im)^\s*(?:Supplier|Vendor|Proveedor|Emisor|From)\s*[:\-]?\s*(.+)$",
            ],
        )
        if not result["proveedor"]["nombre"]:
            result["proveedor"]["nombre"] = self._extract_supplier_name(text)
        result["proveedor"]["id_fiscal"] = self._extract_regex(
            text,
            [
                r"(?im)^\s*(?:RUC|NIF|CIF|VAT\s*No\.?|GST\s*Reg(?:istration)?\s*No\.?|GST\s*ID\s*No\.?|ROC\s*NO\.?|Co\s*No\.?|Registration\s*No\.?)\s*[:\-]?\s*([A-Z0-9\-]{6,30})",
            ],
        )
        result["supplier"]["name"] = result["proveedor"]["nombre"]
        result["supplier"]["registration_no"] = result["proveedor"]["id_fiscal"]
        result["supplier"]["address"] = self._extract_supplier_address(text)
        result["customer"]["name"] = self._extract_regex(text, [r"(?im)^\s*(?:Bill\s*To|Customer|Cliente)\s*[:\-]?\s*(.+)$"])
        result["payment_method"] = self._extract_regex(text, [r"(?im)^\s*(VISA\s*CARD|CASH|MASTERCARD|AMEX|DEBIT\s*CARD).*$"])

        result["lineas"] = self._parse_markdown_table(text)
        result["items"] = [
            {
                "description": row.get("descripcion"),
                "quantity": row.get("cantidad"),
                "unit_price": row.get("precio_unitario"),
                "amount": row.get("total"),
            }
            for row in result["lineas"]
        ]
        result["invoice_number"] = result["numero_factura"]
        result["totals"]["subtotal"] = result["subtotal"]
        result["totals"]["gst_rate"] = "6%" if hint == "malaysia" else None
        result["totals"]["gst_amount"] = result["impuestos"]
        result["totals"]["total"] = result["total"]

        if result["subtotal"] is None and result["total"] is not None and result["impuestos"] is not None:
            result["subtotal"] = round(float(result["total"]) - float(result["impuestos"]), 2)
            result["totals"]["subtotal"] = result["subtotal"]

        return result

    def _extract_supplier_name(self, text: str) -> str | None:
        candidates = []
        for line in (text or "").splitlines()[:12]:
            raw = line.strip()
            if len(raw) < 4:
                continue
            up = raw.upper()
            if any(token in up for token in ("TAX INVOICE", "SIMPLIFIED", "INVOICE NO", "DATE", "TEL:", "FAX:", "CASH BILL")):
                continue
            if sum(ch.isalpha() for ch in raw) < 4:
                continue
            candidates.append(raw)
        return candidates[0] if candidates else None

    def _extract_supplier_address(self, text: str) -> str | None:
        lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
        if not lines:
            return None
        address_lines = []
        started = False
        for line in lines[:12]:
            up = line.upper()
            if any(token in up for token in ("SDN BHD", "ENTERPRISE", "RESTAURANTS", "MARKETING", "PETRON", "PERNIAGAAN")):
                started = True
                continue
            if not started:
                continue
            if any(token in up for token in ("TEL", "FAX", "TAX INVOICE", "CASH BILL", "SIMPLIFIED")):
                break
            address_lines.append(line)
        return ", ".join(address_lines) if address_lines else None

    def _detect_country_hint(self, text: str) -> str:
        up = (text or "").upper()
        if "RM" in up or "MALAYSIA" in up or "GST" in up:
            return "malaysia"
        if "RUC" in up or "SRI" in up or "FACTURA ELECTRONICA" in up.replace("Ó", "O"):
            return "ecuador"
        if "VAT" in up or "TVA" in up or "EU" in up:
            return "europe"
        return "europe"

    def _extract_regex(self, text: str, patterns: list[str]) -> str | None:
        for pat in patterns:
            m = re.search(pat, text)
            if m:
                val = m.group(1).strip()
                return val if val else None
        return None

    def _extract_float(self, text: str, patterns: list[str]) -> float | None:
        for pat in patterns:
            m = re.search(pat, text)
            if not m:
                continue
            val = m.group(1).strip()
            parsed = self._to_float(val)
            if parsed is not None:
                return parsed
        return None

    def _to_float(self, value: str) -> float | None:
        text = (value or "").strip()
        if not text:
            return None
        text = re.sub(r"(?i)(rm|usd|eur|gbp|\$|€)", "", text)
        text = text.replace(" ", "")

        if "." in text and "," in text:
            if text.rfind(".") > text.rfind(","):
                text = text.replace(",", "")
            else:
                text = text.replace(".", "").replace(",", ".")
        elif "," in text:
            parts = text.split(",")
            if len(parts[-1]) <= 2:
                text = text.replace(",", ".")
            else:
                text = text.replace(",", "")

        text = re.sub(r"[^0-9.\-]", "", text)
        if not text:
            return None
        try:
            return float(text)
        except Exception:
            return None

    def _extract_date(self, text: str) -> str | None:
        patterns = [
            (r"\b(\d{4}-\d{2}-\d{2})\b", "%Y-%m-%d"),
            (r"\b(\d{2}/\d{2}/\d{4})\b", "%d/%m/%Y"),
            (r"\b(\d{2}-\d{2}-\d{4})\b", "%d-%m-%Y"),
            (r"\b(\d{2}\.\d{2}\.\d{4})\b", "%d.%m.%Y"),
        ]
        for pat, fmt in patterns:
            m = re.search(pat, text)
            if not m:
                continue
            raw = m.group(1)
            try:
                return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
            except Exception:
                return raw
        return None

    def _parse_markdown_table(self, text: str) -> list[dict[str, Any]]:
        lines = [ln.rstrip() for ln in (text or "").splitlines() if ln.strip()]
        if not lines:
            return []

        header_map: dict[str, int] = {}
        start_idx = -1
        for idx, line in enumerate(lines):
            if "|" not in line:
                continue
            cols = [c.strip().lower() for c in line.split("|") if c.strip()]
            for col_idx, col in enumerate(cols):
                if "qty" in col or "cantidad" in col or "quantity" in col:
                    header_map["qty"] = col_idx
                if "price" in col or "unit" in col or "precio" in col:
                    header_map["unit_price"] = col_idx
                if "amount" in col or "total" in col or "importe" in col:
                    header_map["total"] = col_idx
                if "description" in col or "descripcion" in col or "item" in col:
                    header_map["description"] = col_idx
            if "qty" in header_map and "total" in header_map:
                start_idx = idx + 1
                break

        if start_idx < 0:
            return self._parse_receipt_lines(lines)

        rows: list[dict[str, Any]] = []
        for line in lines[start_idx:]:
            if "|" not in line:
                break
            cols = [c.strip() for c in line.split("|") if c.strip()]
            if not cols or len(cols) <= max(header_map.values()):
                continue

            qty = self._to_float(cols[header_map["qty"]]) or 0.0
            total = self._to_float(cols[header_map["total"]]) or 0.0
            unit_price = (
                self._to_float(cols[header_map["unit_price"]])
                if "unit_price" in header_map and header_map["unit_price"] < len(cols)
                else None
            )
            if "description" in header_map and header_map["description"] < len(cols):
                desc = cols[header_map["description"]].strip()
            else:
                used = set(header_map.values())
                desc = " ".join(v for i, v in enumerate(cols) if i not in used).strip()

            rows.append(
                {
                    "descripcion": desc or None,
                    "cantidad": float(qty),
                    "precio_unitario": float(unit_price or 0.0),
                    "total": float(total),
                }
            )

        return rows

    def _parse_receipt_lines(self, lines: list[str]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for line in lines:
            raw = line.strip()
            if not raw:
                continue
            if any(token in raw.upper() for token in ("TOTAL", "GST", "CASH", "CHANGE", "ROUND", "AMOUNT", "DATE", "INVOICE", "CASHIER", "SALESPERSON", "BILL TO", "APPROVAL CODE")):
                continue

            # "2 M SpicyDeluxe 25.40"
            m = re.match(r"^([0-9]+)\s+(.+?)\s+([0-9]+(?:\.[0-9]{2})?)$", raw)
            if m:
                qty = float(m.group(1))
                desc = m.group(2).strip()
                amount = float(m.group(3))
                rows.append(
                    {
                        "descripcion": desc,
                        "cantidad": qty,
                        "precio_unitario": round(amount / qty, 2) if qty else 0.0,
                        "total": amount,
                    }
                )
                continue

            # "000000111 1 193.00 193.00"
            m = re.match(r"^[A-Z0-9\-]+\s+([0-9]+)\s+([0-9]+(?:\.[0-9]{2})?)\s+([0-9]+(?:\.[0-9]{2})?)$", raw, flags=re.IGNORECASE)
            if m:
                qty = float(m.group(1))
                unit = float(m.group(2))
                amount = float(m.group(3))
                rows.append(
                    {
                        "descripcion": raw.split()[0],
                        "cantidad": qty,
                        "precio_unitario": unit,
                        "total": amount,
                    }
                )

        return rows

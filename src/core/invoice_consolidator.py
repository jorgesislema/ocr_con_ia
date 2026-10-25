from __future__ import annotations

import json
import re
from typing import List, Dict


def _norm_num(s: str) -> float:
    if not s:
        return 0.0
    s = str(s)
    s = s.replace("$", "").replace("€", "").replace("USD", "")
    # Normalize decimal separator handling European (1.234,56) and US (1,234.56) formats
    if "." in s and "," in s:
        if s.rfind(".") < s.rfind(","):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        parts = s.split(",")
        if len(parts[-1]) <= 2:
            s = s.replace(",", ".")
        else:
            s = s.replace(",", "")
    s = re.sub(r"[^0-9.\-]", "", s)
    try:
        return float(s)
    except Exception:
        return 0.0


_TOTAL_PAT = re.compile(r"\b(?P<label>TOTAL A PAGAR|TOTAL\s*USD|VALOR TOTAL|TOTAL)\b\W*(?P<amt>\$?\s*[0-9.,]+)", re.IGNORECASE)
_IVA_LINE_PAT = re.compile(r"IVA[^0-9\n\r]{0,10}([0-9.,]+)\b|([0-9.,]+)\s*\$?\s*IVA|([0-9.,]+)\s*\bIVA\b", re.IGNORECASE)
_DATE_PAT = re.compile(r"(\d{2}/\d{2}/\d{4})|(\d{4}-\d{2}-\d{2})")
_FACTURA_ID_PAT = re.compile(r"Factura[:#\-\s]*([A-Za-z0-9\-/]+)", re.IGNORECASE)
_PROVEEDOR_PAT = re.compile(r"Proveedor[:\s]*([^\n\r]{3,120})", re.IGNORECASE)


def consolidate_invoices_text(text: str) -> Dict:
    """Extrae una lista de facturas (subtotal, iva_pagado, total_pagado) y totales agregados.

    Heurísticas: busca todas las ocurrencias de líneas con 'TOTAL' y para cada una
    recoge contexto previo para extraer fecha, proveedor e IVA. Si no hay IVA explícito,
    intenta deducir como total - subtotal si se encuentra 'SUBTOTAL' o 'BASE'.
    """
    out: Dict = {"facturas": [], "gran_total": {"total_subtotal": 0.0, "total_iva": 0.0, "total_general": 0.0}}

    # Prefer splitting the document by invoice boundaries (palabra 'Factura')
    blocks = re.split(r"(?i)(?=\bFactura\b)", text)
    if len(blocks) <= 1:
        # fallback: treat whole text as single block
        blocks = [text]

    for blk in blocks:
        if not blk.strip():
            continue
        # buscar total dentro del bloque
        m = _TOTAL_PAT.search(blk)
        if not m:
            # intentar la última cantidad monetaria del bloque
            am = re.findall(r"([0-9]{1,3}(?:[\.,][0-9]{3})*(?:[\.,][0-9]{2})?)", blk)
            if am:
                amt_raw = am[-1]
            else:
                continue
        else:
            amt_raw = m.group("amt")
        total = _norm_num(amt_raw)
        ctx = blk
        # identificador
        ident = None
        idm = _FACTURA_ID_PAT.search(ctx)
        if idm:
            ident = idm.group(1).strip()
        else:
            # fallback: try a line beginning with digits or the first non-empty line
            lines_ctx = [ln for ln in ctx.splitlines() if ln.strip()]
            if lines_ctx:
                # prefer a line that contains digits (likely invoice number)
                found = None
                for ln in lines_ctx[:3]:
                    if re.search(r"\d{3,}", ln):
                        found = ln
                        break
                ident = (found or lines_ctx[0])[:40].strip()
            else:
                ident = ""

        # fecha
        date = ""
        dm = _DATE_PAT.search(ctx)
        if dm:
            date = dm.group(0)
            # normalize dd/mm/yyyy -> yyyy-mm-dd
            if "/" in date:
                parts = date.split("/")
                if len(parts) == 3:
                    date = f"{parts[2]}-{parts[1].zfill(2)}-{parts[0].zfill(2)}"

        # proveedor
        prov = ""
        pm = _PROVEEDOR_PAT.search(ctx)
        if pm:
            prov = pm.group(1).strip()
        else:
            # try previous lines for uppercase names
            lines = ctx.splitlines()
            for ln in reversed(lines[:6]):
                if len(ln.strip()) > 3 and any(c.isalpha() for c in ln) and ln.strip().upper() == ln.strip():
                    prov = ln.strip()
                    break

        # IVA pagado: buscar en el bloque previo todas las ocurrencias en líneas que contienen 'IVA'
        iva_pagado = 0.0
        for ln in ctx.splitlines():
            if "IVA" in ln.upper():
                # preferir montos monetarios con decimales (p.ej. 12.00) o con símbolo de moneda
                money_matches = re.findall(r"\$\s*([0-9]{1,3}(?:[\.,][0-9]{3})*(?:[\.,][0-9]{2}))", ln)
                if money_matches:
                    for a in money_matches:
                        iva_pagado += _norm_num(a)
                    continue
                # si no hay montos con decimales, iterar por cada número y evitar los que son porcentajes (p.ej. '12%')
                for m in re.finditer(r"([0-9]{1,3}(?:[\.,][0-9]{3})*(?:[\.,][0-9]{2})?)", ln):
                    a = m.group(1)
                    # char siguiente al match (si existe)
                    end = m.end(1)
                    tail = ln[end:end+2]
                    if re.match(r"\s*%", tail):
                        continue
                    iva_pagado += _norm_num(a)
        # Si no hallamos IVA explícito, intentar hallar 'SUBTOTAL' y deducir
        subtotal = 0.0
        subm = re.search(r"SUBTOTAL[:\s]*\$?\s*([0-9.,]+)", ctx, re.IGNORECASE)
        if subm:
            subtotal = _norm_num(subm.group(1))
            if iva_pagado == 0.0:
                iva_pagado = round(total - subtotal, 2) if total and subtotal else 0.0
        else:
            # intentar 'BASE' o 'BASE IMPONIBLE'
            basem = re.search(r"BASE(?:\s+IMPONIBLE)?[:\s]*\$?\s*([0-9.,]+)", ctx, re.IGNORECASE)
            if basem:
                subtotal = _norm_num(basem.group(1))
                if iva_pagado == 0.0:
                    iva_pagado = round(total - subtotal, 2) if total and subtotal else 0.0

        # Si aún no hay subtotal, deducir como total - iva (if iva found)
        if subtotal == 0.0 and iva_pagado > 0.0:
            subtotal = round(total - iva_pagado, 2)

        factura = {
            "identificador": ident or "",
            "fecha": date,
            "proveedor": prov,
            "subtotal": round(subtotal, 2),
            "iva_pagado": round(iva_pagado, 2),
            "total_pagado": round(total, 2),
        }
        out["facturas"].append(factura)
        out["gran_total"]["total_subtotal"] += factura["subtotal"]
        out["gran_total"]["total_iva"] += factura["iva_pagado"]
        out["gran_total"]["total_general"] += factura["total_pagado"]

    # Round totals
    for k in out["gran_total"]:
        out["gran_total"][k] = round(out["gran_total"][k], 2)

    return out


def consolidate_product_lines_text(text: str) -> Dict:
    """Extrae cada línea de producto/servicio de todas las facturas encontradas.

    Devuelve JSON con la clave `lineas_detalle` que contiene objetos con el formato requerido.
    Heurísticas (robustas para outputs OCR/AIs diversas):
    - Divide el texto por bloques iniciados por 'Factura' (si no hay, trata todo como un bloque).
    - Para cada bloque identifica `origen` por número de factura o proveedor.
    - Busca líneas que parezcan items: patrones tipo 'N x descripción @ precio', o 'descripcion ... precio'.
    - Intenta extraer cantidad, precio unitario, porcentaje IVA (si aparece en la línea), subtotal y total.
    - Si no se encuentra cantidad, asume 1.
    Esta función está pensada para ser independiente del backend IA (funciona sobre texto).
    """
    out = {"lineas_detalle": []}

    # split into invoice-like blocks
    blocks = re.split(r"(?i)(?=\bFactura\b)", text)
    if len(blocks) <= 1:
        blocks = [text]

    # helper patterns
    qty_x_pat = re.compile(r"(?P<cantidad>[0-9]+(?:[\.,][0-9]+)?)\s*[xX]\s*(?P<descripcion>.+?)\s*(?:@|precio|pvp|unitario|u)\s*\$?\s*(?P<precio>[0-9.,]+)", re.IGNORECASE)
    qty_only_pat = re.compile(r"^(?P<cantidad>[0-9]+(?:[\.,][0-9]+)?)\s+(?P<descripcion>.+?)\s+\$?\s*(?P<precio>[0-9.,]+)$")
    price_end_pat = re.compile(r"(?P<descripcion>.+?)\s+\$\s*(?P<precio>[0-9.,]+)$")
    percent_pat = re.compile(r"(?P<pct>[0-9]{1,2})\s*%")

    for blk in blocks:
        if not blk.strip():
            continue
        # determine origin
        idm = _FACTURA_ID_PAT.search(blk)
        provm = _PROVEEDOR_PAT.search(blk)
        if idm:
            origin = f"Factura {idm.group(1).strip()}"
        elif provm:
            origin = provm.group(1).strip()
        else:
            # fallback first non-empty line
            lines_nonempty = [l for l in blk.splitlines() if l.strip()]
            origin = lines_nonempty[0].strip() if lines_nonempty else ""

        for ln in blk.splitlines():
            ln = ln.strip()
            if not ln:
                continue
            # skip explicit summary lines that start with these keywords
            if re.match(r"^(SUBTOTAL|TOTAL|IVA|BASE|VALOR TOTAL)[:\s]", ln, re.IGNORECASE):
                continue

            m = qty_x_pat.search(ln)
            cantidad = 1.0
            descripcion = ""
            precio_unitario = 0.0
            subtotal_line = 0.0
            iva_pct = 0
            iva_line = 0.0
            total_line = 0.0

            if m:
                cantidad = float(m.group("cantidad").replace(',', '.'))
                descripcion = m.group("descripcion").strip()
                precio_unitario = _norm_num(m.group("precio"))
                subtotal_line = round(cantidad * precio_unitario, 2)
                # check for percent in same line
                pm = percent_pat.search(ln)
                if pm:
                    iva_pct = int(pm.group("pct"))
                    iva_line = round(subtotal_line * iva_pct / 100.0, 2)
                total_line = round(subtotal_line + iva_line, 2)
            else:
                m2 = qty_only_pat.search(ln)
                if m2:
                    cantidad = float(m2.group("cantidad").replace(',', '.'))
                    descripcion = m2.group("descripcion").strip()
                    precio_unitario = _norm_num(m2.group("precio"))
                    subtotal_line = round(cantidad * precio_unitario, 2)
                    pm = percent_pat.search(ln)
                    if pm:
                        iva_pct = int(pm.group("pct"))
                        iva_line = round(subtotal_line * iva_pct / 100.0, 2)
                    total_line = round(subtotal_line + iva_line, 2)
                else:
                    m3 = price_end_pat.search(ln)
                    if m3:
                        descripcion = m3.group("descripcion").strip()
                        precio_unitario = _norm_num(m3.group("precio"))
                        cantidad = 1.0
                        subtotal_line = round(precio_unitario * cantidad, 2)
                        pm = percent_pat.search(ln)
                        if pm:
                            iva_pct = int(pm.group("pct"))
                            iva_line = round(subtotal_line * iva_pct / 100.0, 2)
                        total_line = round(subtotal_line + iva_line, 2)
                    else:
                        # fallback: if line contains a monetary-looking number (decimals or currency)
                        nums = re.findall(r"[0-9]{1,3}(?:[\.,][0-9]{3})*(?:[\.,][0-9]{2})?", ln)
                        if nums:
                            candidate = nums[-1]
                            # require either currency symbol in line or decimals (two digits)
                            if "$" in ln or "€" in ln or re.search(r"[\.,][0-9]{2}$", candidate):
                                precio_unitario = _norm_num(candidate)
                                descripcion = ln[: ln.rfind(candidate)].strip()
                                cantidad = 1.0
                                subtotal_line = round(precio_unitario * cantidad, 2)
                                pm = percent_pat.search(ln)
                                if pm:
                                    iva_pct = int(pm.group("pct"))
                                    iva_line = round(subtotal_line * iva_pct / 100.0, 2)
                                total_line = round(subtotal_line + iva_line, 2)
                            else:
                                continue
                        else:
                            continue

            entry = {
                "origen": origin,
                "descripcion": descripcion,
                "cantidad": round(float(cantidad), 3),
                "precio_unitario": round(float(precio_unitario), 2),
                "porcentaje_iva": int(iva_pct),
                "subtotal_linea": round(float(subtotal_line), 2),
                "iva_linea": round(float(iva_line), 2),
                "total_linea": round(float(total_line), 2),
            }
            out["lineas_detalle"].append(entry)

    return out

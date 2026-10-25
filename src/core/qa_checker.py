"""QA utilities: comprobar que el JSON extraído coincide con el XLSX/CSV final.

Funciones principales:
- `compare_invoices_json_vs_excel(invoices, excel_path)` -> list de mensajes de diferencia (vacío = OK)

La comparación es tolerante a formatos (coma/punto, símbolos de moneda)
y normaliza fechas a ISO cuando es posible.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
import re
from datetime import datetime

_log = logging.getLogger("ocr.qa")


def _parse_number(s: Any) -> float | None:
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return float(s)
    t = str(s).strip()
    if not t:
        return None
    t = re.sub(r"[€$¥£]|USD|EUR", "", t, flags=re.IGNORECASE)
    t = t.replace(" ", "")
    if "." in t and "," in t:
        if t.rfind(".") > t.rfind(","):
            t = t.replace(",", "")
        else:
            t = t.replace(".", "").replace(",", ".")
    elif "," in t:
        parts = t.split(",")
        if len(parts[-1]) == 2:
            t = t.replace(",", ".")
        else:
            t = t.replace(",", "")
    t = re.sub(r"[^0-9.\-]", "", t)
    try:
        return float(t)
    except Exception:
        return None


def _normalize_date(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    s = str(value).strip()
    if not s:
        return None
    fmts = ["%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y", "%Y/%m/%d"]
    for f in fmts:
        try:
            return datetime.strptime(s, f).date().isoformat()
        except Exception:
            continue
    return s


# ── Tipos esperados por campo (solo para validación de formato) ───────────────
_FIELD_VALIDATORS: Dict[str, str] = {
    "fecha":             "date",
    "fecha_emision":     "date",
    "fecha_vencimiento": "date",
    "total":             "number",
    "subtotal":          "number",
    "iva":               "number",
    "base_imponible":    "number",
    "numero_factura":    "str",
    "proveedor":         "str",
    "nif_proveedor":     "str",
    "cliente":           "str",
}

# ── Campos mínimos requeridos (validación estricta) ───────────────────────────
# fecha_vencimiento, nif_proveedor, cliente y subtotal son opcionales en muchos documentos.
_REQUIRED_FIELDS: list[str] = [
    "fecha",
    "numero_factura",
    "total",
]


def _apply_invoice_aliases(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Añade aliases español/inglés para evitar falsos negativos en QA."""
    out = dict(payload or {})

    def _first(*vals: Any) -> Any:
        for v in vals:
            if v is None:
                continue
            if isinstance(v, str) and not v.strip():
                continue
            return v
        return None

    # Identificadores y fechas
    out["numero_factura"] = _first(out.get("numero_factura"), out.get("invoice_number"), out.get("invoice_no"))
    out["fecha"] = _first(out.get("fecha"), out.get("fecha_emision"), out.get("date"), out.get("invoice_date"))
    out["fecha_emision"] = _first(out.get("fecha_emision"), out.get("fecha"), out.get("date"), out.get("invoice_date"))

    # Proveedor
    out["proveedor"] = _first(out.get("proveedor"), out.get("supplier"), out.get("supplier_name"))
    out["nif_proveedor"] = _first(out.get("nif_proveedor"), out.get("supplier_tax_id"), out.get("tax_id"))

    # Totales
    subtotal = _first(out.get("subtotal"), out.get("net_amount"), out.get("total_excluding_tax"))
    total = _first(out.get("total"), out.get("total_amount"), out.get("gross_amount"))
    iva = _first(out.get("iva"), out.get("tax_amount"), out.get("tax"))

    out["subtotal"] = subtotal
    out["total"] = total
    out["iva"] = iva

    # Heurística cuando IVA no viene explícito
    if out.get("subtotal") is None and out.get("total") is not None:
        out["subtotal"] = out.get("total")
    if out.get("iva") is None and out.get("subtotal") is not None and out.get("total") is not None:
        try:
            out["iva"] = max(0.0, float(out.get("total")) - float(out.get("subtotal")))
        except Exception:
            out["iva"] = 0.0
    if out.get("base_imponible") is None and out.get("subtotal") is not None:
        out["base_imponible"] = out.get("subtotal")

    return out

QAReport = Dict  # alias de tipo para claridad


def _validate_field_type(
    field: str,
    value: Any,
    expected_type: str,
    errors: List[str],
    warnings: List[str],
) -> None:
    """Valida el tipo/formato de un campo individual."""
    if expected_type == "date":
        norm = _normalize_date(value)
        if norm is None:
            warnings.append(f"Campo '{field}' no pudo normalizarse como fecha: {value!r}")
        elif norm > datetime.today().date().isoformat():
            warnings.append(f"Campo '{field}' tiene fecha futura: {norm}")
    elif expected_type == "number":
        num = _parse_number(value)
        if num is None:
            errors.append(f"Campo '{field}' no es un número válido: {value!r}")
        elif num < 0:
            warnings.append(f"Campo '{field}' tiene valor negativo: {num}")
    elif expected_type == "str":
        if len(str(value).strip()) < 2:
            warnings.append(f"Campo '{field}' parece demasiado corto: {value!r}")


def validate_extraction(
    raw_result: Dict,
    expected_keys: List[str] | None = None,
    rules: Dict | None = None,
) -> QAReport:
    """Valida el diccionario extraído por el motor OCR antes de exportar.

    Parámetros
    ----------
    raw_result :
        Resultado de un único documento tal como lo construye OcrWorker
        (claves: ``text``, ``filename``, ``status``, ``pages``, etc.).
    rules :
        Reglas de validación adicionales por campo::

            {
                "total":    {"min": 0, "max": 1_000_000},
                "proveedor": {"min_length": 3},
                "fecha":    {"not_future": True},
            }

        Cada clave es el nombre de un campo del payload extraído.
        Claves de regla soportadas:
        - ``min`` / ``max``         — rango numérico (números)
        - ``min_length``            — longitud mínima de la cadena
        - ``not_future``            — rechaza fechas futuras como error (no warning)
        - ``required``              — si ``False`` omite el campo de los requeridos
    expected_keys :
        Campos que DEBEN estar presentes. Si es ``None`` usa ``_FIELD_VALIDATORS``.

    Retorna
    -------
    dict con claves ``valid`` (bool), ``errors`` (list[str]), ``warnings`` (list[str]).
    """
    import json as _json

    errors:   List[str] = []
    warnings: List[str] = []
    filename = raw_result.get("filename", "?")

    # Si el backend es Mistral, intentamos extraer payload y aplicar validaciones
    backend_name = str(raw_result.get("backend") or "").lower()
    if "mistral" in backend_name:
        # Para Mistral intentamos obtener un payload estructurado: primero JSON
        # embebido, si no existe usamos heurísticas con `parse_invoice_text`.
        text_field = raw_result.get("text") or ""
        text_str = ""
        if isinstance(text_field, dict):
            text_str = str(text_field.get("text") or "")
        else:
            text_str = str(text_field)

        if not text_str.strip():
            errors.append("No se extrajo texto del documento (Mistral).")
            report: QAReport = {
                "valid":    len(errors) == 0,
                "errors":   errors,
                "warnings": warnings,
            }
            _log.warning("validate_extraction '%s' (mistral): %d errores — %s",
                         filename, len(errors), "; ".join(errors[:3]))
            return report

        # Siempre intentar parser base antes de validar.
        payload = {}
        try:
            from src.core.invoice_parser import parse_invoice_text

            payload = parse_invoice_text(text_str) or {}
        except Exception:
            payload = {}

        # Complementar con JSON embebido si existe.
        try:
            start = text_str.find("{")
            end = text_str.rfind("}") + 1
            if start >= 0 and end > start:
                import json as _json

                parsed_json = _json.loads(text_str[start:end])
                if isinstance(parsed_json, dict):
                    payload = {**payload, **parsed_json}
        except Exception:
            pass
        payload = _apply_invoice_aliases(payload)

        # Ahora aplicar validaciones iguales al flujo normal usando `payload`
        combined = {
            **payload,
            **{k: v for k, v in raw_result.items()
               if k not in ("text", "images", "status", "id", "pages")},
        }

        _rules = rules or {}
        required = list(expected_keys) if expected_keys else list(_REQUIRED_FIELDS)
        required = [f for f in required if _rules.get(f, {}).get("required", True) is not False]

        for field in required:
            val = combined.get(field)
            if val is None or str(val).strip() == "":
                errors.append(f"Campo requerido ausente o vacío: '{field}'")
            else:
                _validate_field_type(
                    field, val,
                    _FIELD_VALIDATORS.get(field, "str"),
                    errors, warnings,
                )

        # Aplicar reglas personalizadas también
        for field, field_rules in (_rules.items()):
            if not isinstance(field_rules, dict):
                continue
            val = combined.get(field)
            if val is None:
                continue
            if "min" in field_rules or "max" in field_rules:
                num = _parse_number(val)
                if num is None:
                    errors.append(f"[rules] Campo '{field}' no es numérico: {val!r}")
                else:
                    r_min = field_rules.get("min")
                    r_max = field_rules.get("max")
                    if r_min is not None and num < r_min:
                        errors.append(f"[rules] '{field}' = {num} < mínimo permitido {r_min}")
                    if r_max is not None and num > r_max:
                        errors.append(f"[rules] '{field}' = {num} > máximo permitido {r_max}")
            min_len = field_rules.get("min_length")
            if min_len is not None:
                if len(str(val).strip()) < int(min_len):
                    warnings.append(f"[rules] '{field}' tiene menos de {min_len} caracteres: {val!r}")
            if field_rules.get("not_future"):
                norm = _normalize_date(val)
                if norm and norm > datetime.today().date().isoformat():
                    errors.append(f"[rules] '{field}' tiene fecha futura: {norm}")

        report: QAReport = {
            "valid":    len(errors) == 0,
            "errors":   errors,
            "warnings": warnings,
        }
        if errors:
            _log.warning("validate_extraction '%s' (mistral): %d errores — %s",
                         filename, len(errors), "; ".join(errors[:3]))
        elif warnings:
            _log.info("validate_extraction '%s' (mistral): %d advertencias", filename, len(warnings))
        else:
            _log.debug("validate_extraction '%s' (mistral): OK", filename)
        return report

    # Extraer payload JSON del campo ``text`` cuando viene como cadena
    text_field = raw_result.get("text") or ""
    payload: Dict = {}
    if isinstance(text_field, dict):
        payload = text_field
    elif isinstance(text_field, str):
        try:
            start = text_field.find("{")
            end   = text_field.rfind("}") + 1
            if start >= 0 and end > start:
                payload = _json.loads(text_field[start:end])
        except Exception:
            pass

    # Asegurar parser universal ANTES de validar campos.
    try:
        from src.core.invoice_parser import parse_invoice_text

        parsed_payload = parse_invoice_text(str(text_field or "")) or {}
        if isinstance(parsed_payload, dict):
            payload = {**parsed_payload, **payload}
    except Exception:
        pass
    payload = _apply_invoice_aliases(payload)

    combined = {
        **payload,
        **{k: v for k, v in raw_result.items()
           if k not in ("text", "images", "status", "id", "pages")},
    }

    # 1. Campos requeridos — respetando regla 'required: False'
    _rules = rules or {}
    required = list(expected_keys) if expected_keys else list(_REQUIRED_FIELDS)
    # Filtrar campos marcados explícitamente como no-requeridos en rules
    required = [f for f in required if _rules.get(f, {}).get("required", True) is not False]

    for field in required:
        val = combined.get(field)
        if val is None or str(val).strip() == "":
            errors.append(f"Campo requerido ausente o vacío: '{field}'")
        else:
            _validate_field_type(
                field, val,
                _FIELD_VALIDATORS.get(field, "str"),
                errors, warnings,
            )

    # 2. Aplicar reglas personalizadas (min/max, min_length, not_future) ──────
    for field, field_rules in _rules.items():
        if not isinstance(field_rules, dict):
            continue
        val = combined.get(field)
        if val is None:
            continue  # la ausencia ya fue capturada en paso 1 si era requerido

        # Regla: rango numérico
        if "min" in field_rules or "max" in field_rules:
            num = _parse_number(val)
            if num is None:
                errors.append(f"[rules] Campo '{field}' no es numérico: {val!r}")
            else:
                r_min = field_rules.get("min")
                r_max = field_rules.get("max")
                if r_min is not None and num < r_min:
                    errors.append(f"[rules] '{field}' = {num} < mínimo permitido {r_min}")
                if r_max is not None and num > r_max:
                    errors.append(f"[rules] '{field}' = {num} > máximo permitido {r_max}")

        # Regla: longitud mínima de cadena
        min_len = field_rules.get("min_length")
        if min_len is not None:
            if len(str(val).strip()) < int(min_len):
                warnings.append(
                    f"[rules] '{field}' tiene menos de {min_len} caracteres: {val!r}"
                )

        # Regla: fecha no futura (error en lugar de warning)
        if field_rules.get("not_future"):
            norm = _normalize_date(val)
            if norm and norm > datetime.today().date().isoformat():
                errors.append(f"[rules] '{field}' tiene fecha futura: {norm}")

    # 4. Coherencia numérica: subtotal + iva ≈ total (tolerancia 0.05)
    sub = _parse_number(combined.get("subtotal") or combined.get("base_imponible"))
    iva = _parse_number(combined.get("iva"))
    tot = _parse_number(combined.get("total"))
    if sub is not None and iva is not None and tot is not None:
        computed = round(sub + iva, 2)
        if abs(computed - tot) > 0.05:
            warnings.append(
                f"Coherencia: subtotal({sub}) + iva({iva}) = {computed} ≠ total({tot})"
            )

    # 5. Estado del documento
    if str(raw_result.get("status") or "").lower() == "error":
        errors.append("Documento marcado como Error — extracción incompleta")

    report: QAReport = {
        "valid":    len(errors) == 0,
        "errors":   errors,
        "warnings": warnings,
    }
    if errors:
        _log.warning("validate_extraction '%s': %d errores — %s",
                     filename, len(errors), "; ".join(errors[:3]))
    elif warnings:
        _log.info("validate_extraction '%s': %d advertencias", filename, len(warnings))
    else:
        _log.debug("validate_extraction '%s': OK", filename)

    return report


def compare_invoices_json_vs_excel(invoices: List[Dict], excel_path: str | Path) -> tuple[List[str], Dict]:
    """Compara la lista de facturas (JSON) contra el XLSX/CSV exportado.

    Devuelve una tupla `(mensajes, stats)` donde `mensajes` es la lista de diferencias
    y `stats` es un diccionario resumido con conteos y per-invoice info.
    Comparaciones realizadas:
        - número de facturas
        - para cada factura: subtotal/iva/total aproximado (±0.01)
        - número de líneas y correspondencia básica de descripción+cantidad+precio
    """
    p = Path(excel_path)
    msgs: List[str] = []
    stats: Dict = {
        "total_invoices": len(invoices),
        "invoices_passed": 0,
        "per_invoice": {},
        "value_mismatches": 0,
        "line_mismatches": 0,
        "other": 0,
    }

    # Leer con pandas; soporta xlsx y csv
    try:
        if p.suffix.lower() in (".xlsx", ".xls"):
            try:
                xl = pd.read_excel(p, sheet_name=None, engine="openpyxl")
                summary_df = xl.get("Summary") or xl[list(xl.keys())[0]]
                lines_df = xl.get("Lines") or pd.DataFrame()
            except Exception:
                # Algunos flujos guardan CSV con extensión .xlsx.
                summary_df = pd.read_csv(p, encoding="utf-8-sig")
                lines_df = pd.DataFrame()
        elif p.suffix.lower() == ".csv":
            summary_df = pd.read_csv(p, encoding="utf-8-sig")
            lines_df = pd.DataFrame()
        else:
            _log.warning("compare_invoices_json_vs_excel: formato no soportado '%s'", p.suffix)
            msgs.append(f"Formato no soportado: {p.suffix}")
            return msgs, stats
    except Exception as exc:
        _log.error("Error leyendo archivo exportado '%s': %s", p, exc)
        msgs.append(f"Error leyendo {p}: {exc}")
        return msgs, stats

    # Normalizar summary_df
    def norm_row(r: Any) -> Dict:
        return {
            "InvoiceID": str(r.get("InvoiceID") if "InvoiceID" in r.index else r.get("id", "")),
            "Fecha": _normalize_date(r.get("Fecha") if "Fecha" in r.index else r.get("fecha")),
            "Proveedor": str(r.get("Proveedor") if "Proveedor" in r.index else r.get("proveedor", "")),
            "Subtotal": _parse_number(r.get("Subtotal") if "Subtotal" in r.index else r.get("subtotal")),
            "IVA": _parse_number(r.get("IVA") if "IVA" in r.index else r.get("iva")),
            "Total": _parse_number(r.get("Total") if "Total" in r.index else r.get("total")),
        }

    summary_norm = []
    for _, row in summary_df.fillna("").iterrows():
        summary_norm.append(norm_row(row))

    # Map invoices by InvoiceID (fall back a índices), normalizando payload desde `text`.
    inv_map: Dict[str, Dict] = {}
    for i, inv in enumerate(invoices):
        iid = str(inv.get("invoice_id") or inv.get("id") or i)
        merged = dict(inv)
        try:
            from src.core.invoice_parser import parse_invoice_text

            parsed = parse_invoice_text(str(inv.get("text") or "")) or {}
            if isinstance(parsed, dict):
                merged = {**parsed, **merged}
        except Exception:
            pass
        merged = _apply_invoice_aliases(merged)
        inv_map[iid] = merged

    # Compare counts
    if len(summary_norm) != len(invoices):
        msgs.append(f"Mismatch invoice count: json={len(invoices)} vs excel={len(summary_norm)}")
        stats["other"] += 1

    # For each summary row, compare totals
    for sr in summary_norm:
        iid = str(sr.get("InvoiceID") or "")
        if iid not in inv_map:
            # try fuzzy match by proveedor+fecha
            matched = None
            for k, v in inv_map.items():
                if (str(v.get("proveedor") or "") == (sr.get("Proveedor") or "")) and (
                    (_normalize_date(v.get("fecha") or v.get("date")) or "") == (sr.get("Fecha") or "")
                ):
                    matched = k
                    break
            if matched is None:
                msgs.append(f"Invoice in Excel not found in JSON: InvoiceID={iid}, Proveedor={sr.get('Proveedor')}")
                stats["other"] += 1
                continue
            iid = matched

        inv = inv_map[iid]
        # compare numeric totals with tolerance
        per_inv_diffs = 0
        comparable_values = 0
        for key, col in (("subtotal", "Subtotal"), ("iva", "IVA"), ("total", "Total")):
            json_val = _parse_number(inv.get(key) or inv.get(col.lower()))
            excel_val = sr.get(col)
            if json_val is None and excel_val is None:
                continue
            comparable_values += 1
            if json_val is None or excel_val is None:
                msgs.append(f"Null mismatch for {iid} {col}: json={json_val} excel={excel_val}")
                per_inv_diffs += 1
                stats["value_mismatches"] += 1
                continue
            if abs(float(json_val) - float(excel_val)) > 0.01:
                msgs.append(f"Value mismatch {iid} {col}: json={json_val} excel={excel_val}")
                per_inv_diffs += 1
                stats["value_mismatches"] += 1

        # Si no hubo ningún valor comparable, no se considera aprobado.
        if comparable_values == 0:
            msgs.append(f"No comparable structured values for {iid}: subtotal/iva/total ausentes")
            per_inv_diffs += 1
            stats["other"] += 1

        # record per-invoice
        stats["per_invoice"][iid] = {"diffs": per_inv_diffs, "passed": per_inv_diffs == 0}
        if per_inv_diffs == 0:
            stats["invoices_passed"] += 1

    # Lines-level basic checks: count of lines per invoice
    if not lines_df.empty:
        # ensure InvoiceID column exists
        if "InvoiceID" not in lines_df.columns:
            msgs.append("Lines sheet missing InvoiceID column")
            stats["other"] += 1
        else:
            # count lines per invoice in excel
            excel_counts = lines_df.groupby("InvoiceID").size().to_dict()
            for inv in invoices:
                iid = str(inv.get("invoice_id") or inv.get("id") or "")
                json_count = len(inv.get("lines") or [])
                excel_count = int(excel_counts.get(iid, 0))
                if json_count != excel_count:
                    msgs.append(f"Line count mismatch for {iid}: json={json_count} excel={excel_count}")
                    stats["line_mismatches"] += 1
                    # update per-invoice diffs if present
                    if iid in stats["per_invoice"]:
                        stats["per_invoice"][iid]["diffs"] += 1
                        stats["per_invoice"][iid]["passed"] = stats["per_invoice"][iid]["diffs"] == 0

    # Compute simple accuracy percentage based on invoices passed
    try:
        stats["accuracy_pct"] = 0.0 if stats["total_invoices"] == 0 else (stats["invoices_passed"] / stats["total_invoices"]) * 100.0
    except Exception:
        stats["accuracy_pct"] = 0.0

    return msgs, stats


# ─────────────────────────────────────────────────────────────────────────────
# Hook de validación contable multi-documento
# ─────────────────────────────────────────────────────────────────────────────

def run_accounting_validation(
    docs: List[Dict],
    rules_path: str | None = None,
    tolerance_pct: float = 2.0,
    enabled: bool = True,
) -> Dict:
    """Ejecuta la reconciliación contable sobre un lote de documentos procesados.

    Se llama opcionalmente tras completar la exportación, cuando el usuario
    tiene habilitado el toggle ``📊 Validación Contable`` en la config.

    Parámetros
    ----------
    docs : list[dict]
        Resultados de OcrWorker (``status == "done"``), cada uno con al menos
        ``doc_type``, ``doc_id`` / ``numero_factura``, ``total``, ``lines``, etc.
    rules_path : str | None
        Ruta a un JSON con reglas personalizadas para ``ReconciliationEngine``.
        Puede ser ``None`` para usar los valores por defecto.
    tolerance_pct : float
        Tolerancia monetaria en % (trasladada al motor si no hay rules_path).
    enabled : bool
        Si es ``False`` devuelve inmediatamente un reporte vacío (motor desactivado).

    Devuelve
    --------
    dict con claves:
        - ``enabled``     : bool
        - ``issues``      : list[dict]  (ValidationIssue.as_dict() de cada una)
        - ``issue_count`` : int
        - ``error_count`` : int
        - ``warning_count``: int
    """
    if not enabled:
        return {
            "enabled": False, "issues": [], "issue_count": 0,
            "error_count": 0, "warning_count": 0,
        }
    try:
        from src.core.reconciliation_engine import ReconciliationEngine  # type: ignore
        engine = ReconciliationEngine(rules_path=rules_path, tolerance_pct=tolerance_pct)
        issues = engine.validate_batch(docs)
    except ImportError:
        issues = []
    issue_dicts = [i.as_dict() if hasattr(i, "as_dict") else dict(i) for i in issues]
    return {
        "enabled":       True,
        "issues":        issue_dicts,
        "issue_count":   len(issue_dicts),
        "error_count":   sum(1 for i in issue_dicts if i.get("severity") == "error"),
        "warning_count": sum(1 for i in issue_dicts if i.get("severity") == "warning"),
    }


# ─────────────────────────────────────────────────────────────────────────────
# FASE 6 — Validación semántica avanzada por campo
# ─────────────────────────────────────────────────────────────────────────────

def validate_semantics(
    field: str,
    value: Any,
    doc_type: str = "factura",
) -> list[str]:
    """Valida semánticamente el valor de un campo extraído.

    A diferencia de ``validate_extraction`` (que valida un documento completo),
    esta función valida **un campo individual** en el momento de edición o justo
    después de la extracción OCR, ideal para el panel de revisión interactivo.

    Devuelve
    --------
    list[str]
        Lista de mensajes de ERROR (vacía si el valor es válido).
        Todos los problemas detectados son errores — las advertencias se elevan
        a error en FASE 6 para garantizar calidad SaaS.
    """
    errors: list[str] = []
    if value is None or str(value).strip() == "":
        return errors  # campo vacío se valida en validate_extraction, no aquí

    str_val = str(value).strip()

    # ── Identificadores fiscales ──────────────────────────────────────────────
    tax_fields = {"nif_proveedor", "cif_proveedor", "ruc", "nit",
                  "nif_cliente", "cif_cliente", "tax_id", "vat_number"}
    if field in tax_fields:
        errs = _validate_tax_id(str_val, doc_type)
        errors.extend(errs)

    # ── Fechas futuras → ERROR (era advertencia, FASE 6 lo eleva) ────────────
    date_fields = {"fecha", "fecha_factura", "fecha_emision",
                   "fecha_vencimiento", "invoice_date", "due_date"}
    if field in date_fields:
        norm = _normalize_date_str(str_val)
        if norm:
            today = datetime.today().date().isoformat()
            if norm > today:
                errors.append(
                    f"'{field}' tiene fecha futura ({norm}); "
                    "comprueba el documento."
                )

    # ── Importes y moneda ─────────────────────────────────────────────────────
    currency_fields = {"total", "subtotal", "iva", "base_imponible",
                       "total_factura", "importe_total", "tax_amount",
                       "net_amount", "gross_amount"}
    if field in currency_fields:
        errors.extend(_validate_currency_format(str_val))

    # ── Número de factura: no debe estar vacío o ser sólo ceros ───────────────
    if field in {"numero_factura", "invoice_number", "num_factura"}:
        stripped = re.sub(r"[^0-9A-Za-z]", "", str_val)
        if not stripped or re.fullmatch(r"0+", stripped):
            errors.append(
                f"'{field}' parece inválido: {str_val!r}"
            )

    return errors


# ── Helpers privados FASE 6 ───────────────────────────────────────────────────

def _normalize_date_str(value: str) -> str | None:
    """Intenta convertir value a 'YYYY-MM-DD'.  Devuelve None si falla."""
    formats = [
        "%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d",
        "%d/%m/%y", "%d-%m-%y",
        "%Y/%m/%d", "%m/%d/%Y",
    ]
    clean = value.strip().split("T")[0]  # elimina la parte de hora si la hay
    for fmt in formats:
        try:
            return datetime.strptime(clean, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _validate_tax_id(value: str, doc_type: str) -> list[str]:
    """Valida NIF/CIF (España), RUC (Ecuador/Perú) y NIT (Colombia/Bolivia).

    Aplica verificación de dígito de control según el país infeferido por
    el doc_type o la longitud/formato del identificador.
    """
    errors: list[str] = []
    clean = re.sub(r"[\s\-\.]", "", value.upper())

    if not clean:
        return errors

    # NIF España: 8 dígitos + letra verificadora
    if re.fullmatch(r"\d{8}[A-Z]", clean):
        letras = "TRWAGMYFPDXBNJZSQVHLCKE"
        expected = letras[int(clean[:8]) % 23]
        if clean[-1] != expected:
            errors.append(
                f"NIF '{value}': letra verificadora incorrecta "
                f"(esperada '{expected}', encontrada '{clean[-1]}')."
            )
        return errors

    # CIF España: letra + 7 dígitos + dígito/letra de control
    if re.fullmatch(r"[ABCDEFGHJKLMNPQRSUVW]\d{7}[0-9A-J]", clean):
        digits = [int(c) for c in clean[1:8]]
        odd_sum  = digits[0] + digits[2] + digits[4] + digits[6]
        even_sum = sum(
            (2 * d) // 10 + (2 * d) % 10 for d in (digits[1], digits[3], digits[5])
        )
        control  = (10 - (odd_sum + even_sum) % 10) % 10
        control_letters = "JABCDEFGHI"
        org_type = clean[0]
        expected_str = (
            control_letters[control]
            if org_type in "KLMNPQRSW"
            else str(control)
        )
        if clean[-1] not in (expected_str, control_letters[control]):
            errors.append(
                f"CIF '{value}': dígito de control incorrecto."
            )
        return errors

    # RUC Ecuador: 13 dígitos, mod10 o mod11 según tipo
    if re.fullmatch(r"\d{13}", clean):
        # Verificación simplificada mod10 para personas naturales (tercer dígito < 6)
        if int(clean[2]) < 6:
            coefs = [2, 1, 2, 1, 2, 1, 2, 1, 2]
            total = sum(
                (v * int(clean[i])) - (9 if (v * int(clean[i])) > 9 else 0)
                for i, v in enumerate(coefs)
            )
            check = (10 - (total % 10)) % 10
            if check != int(clean[9]):
                errors.append(
                    f"RUC Ecuador '{value}': dígito verificador incorrecto."
                )
        return errors

    # RUC Perú: 11 dígitos, mod11
    if re.fullmatch(r"\d{11}", clean):
        coefs = [5, 4, 3, 2, 7, 6, 5, 4, 3, 2]
        total = sum(int(clean[i]) * coefs[i] for i in range(10))
        remainder = 11 - (total % 11)
        check = 0 if remainder in (10, 11) else remainder
        if check != int(clean[10]):
            errors.append(
                f"RUC Perú '{value}': dígito verificador incorrecto."
            )
        return errors

    # NIT Colombia: entre 9 y 10 dígitos
    if re.fullmatch(r"\d{9,10}", clean):
        # Verificación de dígito de verificación (mod11)
        coefs = [71, 67, 59, 53, 47, 43, 41, 37, 29, 23, 19, 17, 13, 7, 3]
        digits_only = clean[:-1]
        coefs_used = coefs[len(coefs) - len(digits_only):]
        total = sum(int(d) * c for d, c in zip(digits_only, coefs_used))
        remainder = total % 11
        expected = 0 if remainder in (0, 1) else 11 - remainder
        if expected != int(clean[-1]):
            errors.append(
                f"NIT Colombia '{value}': dígito de verificación incorrecto."
            )
        return errors

    # Formato desconocido — avisamos pero no bloqueamos
    if len(clean) < 7:
        errors.append(
            f"Identificador fiscal '{value}' demasiado corto ({len(clean)} chars)."
        )

    return errors


def _validate_currency_format(value: str) -> list[str]:
    """Verifica que un importe sea numérico con como máximo 2 decimales."""
    errors: list[str] = []
    clean = re.sub(r"[€$£¥]|USD|EUR|PEN|COP|BOB|MXN", "", value, flags=re.IGNORECASE)
    clean = clean.strip().replace(",", ".")  # Europa: 1.234,56 → 1234.56
    # quitar separadores de miles (punto si quedan varios o está antes de 3 dígitos finales)
    clean = re.sub(r"\.(?=\d{3}(?:\.|$))", "", clean)

    if not clean:
        return errors

    try:
        float(clean)
    except ValueError:
        errors.append(f"Importe no reconocido: {value!r}")
        return errors

    # Verificar decimales
    if "." in clean:
        _, dec = clean.rsplit(".", 1)
        if len(dec) > 2:
            errors.append(
                f"Importe '{value}' tiene más de 2 decimales; "
                "comprueba si es un error de extracción."
            )

    return errors

"""Genera un reporte simple (JSON + HTML) comparando sidecars LLM capturados.

Busca pairs `{stem}__raw.txt` y `{stem}__parsed.json` en `output/llm_captures/` y crea:
 - `output/llm_captures/report.json` : resumen por stem
 - `output/llm_captures/report.html` : vista rápida con links y detalles

Esto ayuda a ver qué campos críticos faltan tras la estructuración.
"""
from pathlib import Path
import json
import html

CAP_DIR = Path.cwd() / "output" / "llm_captures"
OUT_JSON = CAP_DIR / "report.json"
OUT_HTML = CAP_DIR / "report.html"

CRITICAL_ALIASES = {
    "numero_factura": ["numero_factura", "invoice_number", "invoice_no", "bill_number", "number"],
    "fecha_emision": ["fecha_emision", "date", "invoice_date"],
    "total": ["total", "grand_total", "total_amount"],
    "proveedor": ["proveedor", "supplier", "company_name", "seller", "business_name"],
}


def find_captures():
    if not CAP_DIR.exists():
        return []
    files = list(CAP_DIR.iterdir())
    stems = {}
    for f in files:
        name = f.name
        if name.endswith("__raw.txt"):
            stem = name.rsplit("__raw.txt", 1)[0]
            stems.setdefault(stem, {})["raw"] = f
        elif name.endswith("__parsed.json"):
            stem = name.rsplit("__parsed.json", 1)[0]
            stems.setdefault(stem, {})["parsed"] = f
    return stems


def load_parsed(fp: Path):
    try:
        txt = fp.read_text(encoding="utf-8")
        return json.loads(txt) if txt.strip() else {}
    except Exception:
        return {}


def heuristic_extract(raw: str) -> dict:
    """Intentar extraer `numero_factura`, `fecha_emision`, `total` desde texto crudo usando regex simples."""
    import re

    out = {"numero_factura": None, "fecha_emision": None, "total": None}
    if not raw:
        return out

    # invoice number patterns
    patterns_no = [r"Invoice\s*No[:\s]*([A-Z0-9\-_/]+)", r"Invoice\s*#[:\s]*([A-Z0-9\-_/]+)",
                   r"No\.?\s*[:]?\s*([A-Z0-9\-_/]+)", r"Número\s*de\s*factura[:\s]*([A-Z0-9\-_/]+)",
                   r"Factura\s*[:#]?\s*([A-Z0-9\-_/]+)"]
    for p in patterns_no:
        m = re.search(p, raw, re.IGNORECASE)
        if m:
            out["numero_factura"] = m.group(1).strip()
            break

    # date patterns
    date_patterns = [r"(\d{4}-\d{2}-\d{2})", r"(\d{2}/\d{2}/\d{4})", r"(\d{2}\.\d{2}\.\d{4})",
                     r"(\d{1,2}\s+[A-Za-z]+\s+\d{4})"]
    for p in date_patterns:
        m = re.search(p, raw)
        if m:
            out["fecha_emision"] = m.group(1).strip()
            break

    # total patterns (look for the last occurrence of 'Total' with a number)
    num_pat = r"([\d]{1,3}(?:[\.,][\d]{3})*(?:[\.,][\d]{2})?)"
    total_patterns = [rf"Total\s*[:\-]?\s*{num_pat}", rf"Amount\s*Due\s*[:\-]?\s*{num_pat}", rf"Grand\s*Total\s*[:\-]?\s*{num_pat}"]
    for p in total_patterns:
        ms = list(re.finditer(p, raw, re.IGNORECASE))
        if ms:
            # prefer last match (often summary at bottom)
            m = ms[-1]
            val = m.group(1).replace(" ","").replace(",",".")
            try:
                out["total"] = float(val)
            except Exception:
                out["total"] = val
            break

    return out


def analyze():
    stems = find_captures()
    report = []
    # try to import project parser for deeper heuristic parsing
    try:
        from src.data.exporters import _parse_glm_response
    except Exception:
        _parse_glm_response = None
    for stem, files in sorted(stems.items()):
        raw_text = files.get("raw").read_text(encoding="utf-8") if files.get("raw") else ""
        parsed = load_parsed(files.get("parsed")) if files.get("parsed") else {}
        heur = heuristic_extract(raw_text)
        entry = {"stem": stem, "has_raw": bool(raw_text.strip()), "has_parsed": bool(parsed), "parsed": parsed}
        # deeper heuristic parser from project (Mistral markdown) if available
        parsed_heuristic_full = {}
        try:
            if _parse_glm_response:
                parsed_heuristic_full = _parse_glm_response(raw_text)
        except Exception:
            parsed_heuristic_full = {}
        entry["parsed_heuristic"] = parsed_heuristic_full or {}
        # check critical fields
        present = {}
        missing = []
        for k, aliases in CRITICAL_ALIASES.items():
            found = None
            for a in aliases:
                if isinstance(parsed, dict) and a in parsed and parsed.get(a) not in (None, ""):
                    found = parsed.get(a)
                    break
            present[k] = bool(found)
            if not found:
                missing.append(k)
            else:
                entry.setdefault("found_values", {})[k] = found
        entry["present"] = present
        entry["missing_critical"] = missing
        # small metrics
        entry["parsed_keys_count"] = len(parsed) if isinstance(parsed, dict) else 0
        # heuristics: intentar recuperar valores faltantes
        entry["heuristic"] = heur
        recovered = {}
        for crit in entry.get("missing_critical", []):
            if heur.get(crit) is not None:
                recovered[crit] = heur.get(crit)
        entry["recovered_by_heuristic"] = recovered
        report.append(entry)
        # per-field diagnostics: compare raw/heuristic/full-heuristic/llm
        diagnostics = {}
        for field, aliases in CRITICAL_ALIASES.items():
            diag = {"present_in_llm": False, "present_in_heuristic": False, "present_in_heuristic_full": False, "present_in_regex": False, "verdict": "missing"}
            # check in LLM parsed
            try:
                for a in aliases:
                    if isinstance(parsed, dict) and parsed.get(a) not in (None, ""):
                        diag["present_in_llm"] = True
                        diag["llm_value"] = parsed.get(a)
                        break
            except Exception:
                pass
            # check in lightweight heuristic (regex)
            try:
                if heur.get(field) is not None:
                    diag["present_in_regex"] = True
                    diag.setdefault("regex_value", heur.get(field))
            except Exception:
                pass
            # check in full heuristic parser
            try:
                for a in aliases:
                    if isinstance(parsed_heuristic_full, dict) and parsed_heuristic_full.get(a) not in (None, ""):
                        diag["present_in_heuristic_full"] = True
                        diag["heuristic_full_value"] = parsed_heuristic_full.get(a)
                        break
            except Exception:
                pass
            # check parsed_heuristic (previous parse stage)
            try:
                for a in aliases:
                    if isinstance(entry.get("parsed", {}), dict) and entry.get("parsed").get(a) not in (None, ""):
                        diag["present_in_heuristic"] = True
                        diag.setdefault("heuristic_value", entry.get("parsed").get(a))
                        break
            except Exception:
                pass

            # decide verdict
            if diag["present_in_llm"]:
                if not (diag["present_in_heuristic_full"] or diag["present_in_regex"] or diag["present_in_heuristic"]):
                    diag["verdict"] = "llm_inferred"
                else:
                    # present in both; check equality
                    v_llm = diag.get("llm_value")
                    v_heur = diag.get("heuristic_full_value") or diag.get("heuristic_value") or diag.get("regex_value")
                    if v_llm != v_heur:
                        diag["verdict"] = "llm_changed"
                    else:
                        diag["verdict"] = "ok"
            else:
                if diag["present_in_heuristic_full"] or diag["present_in_regex"] or diag["present_in_heuristic"]:
                    diag["verdict"] = "lost_in_llm"
                else:
                    diag["verdict"] = "missing_in_all"
            diagnostics[field] = diag
        entry["diagnostics"] = diagnostics
    return report


def render_html(report_list):
    rows = []
    for e in report_list:
        stem = html.escape(e["stem"]) 
        raw_link = f"{e['stem']}__raw.txt"
        parsed_link = f"{e['stem']}__parsed.json"
        miss = ", ".join(e.get("missing_critical", [])) or "—"
        rows.append(f"<tr><td><a href=\"{raw_link}\">{stem}</a></td><td><a href=\"{parsed_link}\">parsed</a></td><td>{e.get('parsed_keys_count')}</td><td>{html.escape(miss)}</td></tr>")
    body = "\n".join(rows)
    html_doc = (
        "<!doctype html>\n"
        "<html>\n"
        "<head><meta charset=\"utf-8\"><title>LLM Captures Report</title>\n"
        "<style>body{font-family:Arial,Helvetica,sans-serif}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ddd;padding:8px}th{background:#f4f4f4}</style>\n"
        "</head>\n"
        "<body>\n"
        "<h1>LLM Captures Report</h1>\n"
        "<p>Generado en captura automática. Revisa los archivos raw/parsed enlazados abajo.</p>\n"
        "<table>\n"
        "<tr><th>Stem</th><th>Parsed</th><th>Parsed keys</th><th>Missing critical</th></tr>\n"
        + body
        + "\n</table>\n</body>\n</html>"
    )
    return html_doc


def write_reports(report):
    CAP_DIR.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    OUT_HTML.write_text(render_html(report), encoding="utf-8")
    # CSV resumen adicional
    try:
        import csv
        out_csv = CAP_DIR / "report_summary.csv"
        with out_csv.open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["stem","has_raw","has_parsed","parsed_keys_count","missing_critical","recovered_by_heuristic"])
            for e in report:
                w.writerow([e.get("stem"), e.get("has_raw"), e.get("has_parsed"), e.get("parsed_keys_count"),
                            ";".join(e.get("missing_critical",[])), json.dumps(e.get("recovered_by_heuristic",{}), ensure_ascii=False)])
    except Exception:
        pass


if __name__ == "__main__":
    rep = analyze()
    write_reports(rep)
    print(f"Report generated: {OUT_JSON}\n{OUT_HTML}")

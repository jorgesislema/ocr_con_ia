import json
from pathlib import Path
from src.data.exporters import _parse_glm_response

FIX = Path(__file__).parent / "fixtures"


def load(path):
    return Path(path).read_text(encoding="utf-8")

def contains_total(d, expected):
    if not isinstance(d, dict):
        return False
    for v in d.values():
        if isinstance(v, (int, float)) and abs(float(v) - expected) < 1e-6:
            return True
        if isinstance(v, dict) and contains_total(v, expected):
            return True
        if isinstance(v, list):
            for it in v:
                if isinstance(it, dict) and contains_total(it, expected):
                    return True
    return False


def test_parse_golden_001():
    raw = load(FIX / "golden_001.md")
    parsed = _parse_glm_response(raw)
    # Expect heuristic parser to extract key fields
    assert isinstance(parsed, dict)
    # invoice number should appear under any of the known keys
    keys_invoice = [parsed.get(k) for k in ("invoice_number", "numero_factura", "invoice_no")]
    assert "PEGIV-1030765" in keys_invoice
    # total can appear under various keys; search numeric values
    def contains_total(d, expected):
        if not isinstance(d, dict):
            return False
        for v in d.values():
            if isinstance(v, (int, float)) and abs(float(v) - expected) < 1e-6:
                return True
            if isinstance(v, dict) and contains_total(v, expected):
                return True
            if isinstance(v, list):
                for it in v:
                    if isinstance(it, dict) and contains_total(it, expected):
                        return True
        return False

    assert contains_total(parsed, 193.0)


def test_parse_golden_002():
    raw = load(FIX / "golden_002.md")
    parsed = _parse_glm_response(raw)
    assert isinstance(parsed, dict)
    keys_invoice = [parsed.get(k) for k in ("invoice_number", "numero_factura", "invoice_no")]
    assert "PEGIV-1030531" in keys_invoice
    assert contains_total(parsed, 170.0)


def test_parse_golden_003_empty():
    raw = load(FIX / "golden_003.md")
    parsed = _parse_glm_response(raw)
    # For this minimal receipt we accept either {} or a dict lacking numero_factura
    assert isinstance(parsed, dict)
    assert not parsed.get("numero_factura")

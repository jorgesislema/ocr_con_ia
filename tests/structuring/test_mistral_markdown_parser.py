from pathlib import Path
from src.core.mistral_markdown_parser import MistralMarkdownParser

FIX = Path(__file__).parent / "fixtures"


def test_mistral_parser_golden_001():
    raw = (FIX / "golden_001.md").read_text(encoding="utf-8")
    parsed = MistralMarkdownParser().parse_invoice(raw, country_hint="auto")
    assert isinstance(parsed, dict)
    # basic expectations
    assert parsed.get("invoice_number") == "PEGIV-1030765" or parsed.get("numero_factura") == "PEGIV-1030765"
    # total may be under various keys; ensure a numeric close to 193.0 exists
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


def test_mistral_parser_golden_002():
    raw = (FIX / "golden_002.md").read_text(encoding="utf-8")
    parsed = MistralMarkdownParser().parse_invoice(raw, country_hint="auto")
    assert isinstance(parsed, dict)
    assert parsed.get("invoice_number") == "PEGIV-1030531" or parsed.get("numero_factura") == "PEGIV-1030531"

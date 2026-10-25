import json
from pathlib import Path
from src.data.exporters import _prepare_rows
import src.core.structuring_engine as se

FIX = Path(__file__).parent / "fixtures"


def make_doc(md_path, filename):
    raw = Path(md_path).read_text(encoding="utf-8")
    return {"id": 1, "filename": filename, "pages": 1, "confidence": 1.0, "status": "Procesado", "text": raw}


def test_llm_structuring_success(monkeypatch):
    # Simulate StructuringEngine.structure returning a valid JSON string
    def fake_structure(self, raw_text, prompt):
        js = json.dumps({
            "invoice_number": "PEGIV-1030765",
            "date": "2019-01-15",
            "total": 193.0,
            "supplier": "OJC MARKETING SDN BHD"
        })
        return js, 10, 20

    monkeypatch.setattr(se.StructuringEngine, "structure", fake_structure)

    doc = make_doc(FIX / "golden_001.md", "X00016469670.jpg")
    rows = _prepare_rows([doc], structuring_provider="DeepSeek", structuring_api_key="DUMMY")
    assert rows and isinstance(rows, list)
    r = rows[0]
    # normalized key should be numero_factura
    assert r.get("numero_factura") == "PEGIV-1030765"
    assert float(r.get("total")) == 193.0
    assert r.get("proveedor") == "OJC MARKETING SDN BHD" or r.get("supplier") == "OJC MARKETING SDN BHD"


def test_llm_structuring_malformed_fallback(monkeypatch):
    # Simulate StructuringEngine.structure returning non-JSON text -> fallback heuristic should extract data
    def fake_structure_bad(self, raw_text, prompt):
        return ("This is not JSON, just text: Invoice No : PEGIV-1030765 Total: 193.00"), 0, 0

    monkeypatch.setattr(se.StructuringEngine, "structure", fake_structure_bad)

    doc = make_doc(FIX / "golden_001.md", "X00016469670.jpg")
    rows = _prepare_rows([doc], structuring_provider="DeepSeek", structuring_api_key="DUMMY")
    assert rows and isinstance(rows, list)
    r = rows[0]
    # Heuristic parser should still find invoice number or total
    assert r.get("numero_factura") == "PEGIV-1030765" or r.get("invoice_number") == "PEGIV-1030765" or any(
        str(v).find("PEGIV-1030765") >= 0 for v in r.values() if isinstance(v, str)
    )
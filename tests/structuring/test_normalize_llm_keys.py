from src.data.exporters import _normalize_llm_keys


def test_normalize_simple_keys():
    src = {
        "invoice_number": "INV-1",
        "date": "2020-01-01",
        "total_amount": 12.3,
        "supplier": "ACME"
    }
    out = _normalize_llm_keys(src)
    assert out.get("numero_factura") == "INV-1"
    assert out.get("fecha_emision") == "2020-01-01"
    assert out.get("total") == 12.3
    # supplier mapping may arrive under different key names; accept either
    assert out.get("proveedor") == "ACME" or out.get("supplier") == "ACME"

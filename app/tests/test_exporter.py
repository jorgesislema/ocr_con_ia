"""Tests de DocumentExporter — TAREA 3 (columnas selectivas + sanitización).

Ejecutar:  python -m pytest app/tests/test_exporter.py -q
"""
from app.services.exporter import REDACTED, DocumentExporter, sanitize_value

SAMPLE = {
    "document_type": "invoice",
    "invoice_number": "FAC-77",
    "issue_date": "2026-10-01",
    "currency": "EUR",
    "supplier": {"name": "Mock GmbH", "tax_id": "DE000", "country": "DE"},
    "customer": {"name": "Cliente SL", "tax_id": "ES000"},
    "line_items": [
        {"description": "Licencia anual", "quantity": 2, "unit_price": 500,
         "subtotal": 1000, "page": 1},
        {"description": "Soporte", "quantity": 1, "unit_price": 100,
         "subtotal": 100, "page": 2},
    ],
    "subtotal": 1100,
    "discounts": [],
    "taxes": [{"type": "VAT", "rate": 21, "base_amount": 1100, "amount": 231}],
    "total": 1331,
    "full_text_content": "FACTURA FAC-77\nTarjeta corporativa: 4111 1111 1111 1111\npassword: s3cr3t0",
}


# ── Sanitización (TAREA 3.4) ─────────────────────────────────────────────────

def test_tarjeta_con_separadores_se_redacta():
    assert sanitize_value("Pago con 4111 1111 1111 1111 confirmado") == \
        f"Pago con {REDACTED} confirmado"


def test_tarjeta_sin_separadores_se_redacta():
    assert sanitize_value("4111111111111111") == REDACTED


def test_password_inline_se_redacta():
    out = sanitize_value("usuario: ana / password: s3cr3t0 fin")
    assert "s3cr3t0" not in out
    assert REDACTED in out


def test_none_y_null_son_celda_vacia():
    assert sanitize_value(None) == ""
    assert sanitize_value("null") == ""
    assert sanitize_value("NULL") == ""


def test_texto_normal_no_se_toca():
    assert sanitize_value("Total 1331 EUR") == "Total 1331 EUR"


# ── Columnas selectivas (TAREA 3.2) ──────────────────────────────────────────

def test_columnas_solicitadas_y_celda_vacia_para_desconocidas():
    exp = DocumentExporter(SAMPLE, ["invoice_number", "total", "columna_inexistente"])
    rows = exp._rows()
    assert len(rows) == 2  # una fila por line_item
    assert rows[0]["invoice_number"] == "FAC-77"
    assert rows[0]["total"] == "1331"
    assert rows[0]["columna_inexistente"] == ""  # campo ausente → celda vacía


def test_campos_none_se_exportan_como_vacio():
    data = dict(SAMPLE)
    data["notes"] = None
    exp = DocumentExporter(data, ["notes"])
    assert exp._rows()[0]["notes"] == ""


def test_columna_con_nombre_sensible_se_redacta():
    exp = DocumentExporter(SAMPLE, ["password_del_erp"])
    assert exp._rows()[0]["password_del_erp"] == REDACTED


def test_columnas_por_defecto_si_no_se_envian():
    exp = DocumentExporter(SAMPLE)
    assert "line.description" in exp.columnas and "total" in exp.columnas


# ── Formatos ─────────────────────────────────────────────────────────────────

def test_to_csv_bytes_con_encabezados_y_bom():
    csv_bytes = DocumentExporter(SAMPLE, ["invoice_number", "total"]).to_csv()
    assert csv_bytes.startswith(b"\xef\xbb\xbf")  # BOM utf-8-sig
    text = csv_bytes.decode("utf-8-sig")
    assert text.splitlines()[0] == "invoice_number,total"


def test_to_txt_usa_full_text_content_y_sanitiza():
    txt = DocumentExporter(SAMPLE, ["invoice_number"]).to_txt().decode("utf-8")
    assert "FACTURA FAC-77" in txt
    assert "4111" not in txt and "s3cr3t0" not in txt  # datos sensibles fuera
    assert REDACTED in txt


def test_to_docx_usa_full_text_content():
    docx_bytes = DocumentExporter(SAMPLE).to_docx()
    assert docx_bytes[:2] == b"PK"  # zip del docx


def test_to_xlsx_genera_workbook_valido():
    xlsx_bytes = DocumentExporter(SAMPLE, ["invoice_number"]).to_xlsx()
    assert xlsx_bytes[:2] == b"PK"


def test_to_pdf_genera_pdf_valido():
    pdf_bytes = DocumentExporter(SAMPLE, ["invoice_number"]).to_pdf()
    assert pdf_bytes[:5] == b"%PDF-"


def test_formato_invalido_lanza_valueerror():
    try:
        DocumentExporter(SAMPLE).export("doc")
        assert False, "debería lanzar ValueError"
    except ValueError:
        pass

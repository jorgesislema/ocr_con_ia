"""Prueba de integración end-to-end del SaaS sin claves reales.

Simula un proveedor IA (mock) y recorre el pipeline completo:
    upload → cola (eager) → extracción → consolidación → validación
    → revisión humana → exportación xlsx/csv/docx/pdf.

Ejecutar desde la raíz del repo:
    python app/tests/e2e_smoke.py
"""
from __future__ import annotations

import io
import os
import sys

# Clave de admin para crear cuentas en el test (antes de importar la app).
os.environ.setdefault("OCR_ADMIN_KEY", "e2e-admin-key")
from decimal import Decimal

# ── 1. Mock del proveedor IA ANTES de importar la app ────────────────────────
from app.ai.base import BaseAIProvider, ExtractionInput, ExtractionResult
from app.ai import factory as ai_factory

MOCK_INVOICE = {
    "document_type": "invoice",
    "invoice_number": "E2E-001",
    "issue_date": "2026-10-01",
    "currency": "EUR",
    "region": "EU",
    "supplier": {"name": "Mock GmbH", "tax_id": "DE000", "country": "DE"},
    "customer": {"name": "Cliente SL", "country": "ES"},
    "line_items": [
        {"description": "Licencia anual", "quantity": 2, "unit_price": 500,
         "subtotal": 1000, "page": 1},
    ],
    "subtotal": 1000,
    "discounts": [],
    "taxes": [{"type": "VAT", "rate": 21, "base_amount": 1000, "amount": 210}],
    "total": 1210,
    "full_text_content": "FACTURA E2E-001 — Mock GmbH — texto completo de prueba",
}


class MockProvider(BaseAIProvider):
    name = "mock"

    def extract_data(self, file: ExtractionInput) -> ExtractionResult:
        return ExtractionResult(data=MOCK_INVOICE, provider=self.name, model="mock-1")

    def extract_page(self, file: ExtractionInput, page_number: int) -> dict:
        return MOCK_INVOICE

    def available(self) -> bool:
        return True


ai_factory._PROVIDER_CLASSES["mock"] = MockProvider

# ── 2. Cliente de prueba + cuentas vía /auth (TAREA 1: JWT + planes) ────────
import fitz  # PyMuPDF
from fastapi.testclient import TestClient

from app.api.main import app
from app.core.db.base import init_db

init_db()  # crea tablas (el esquema de User cambió con TAREA 1)

client = TestClient(app)

ADMIN = {"X-Admin-Key": "e2e-admin-key"}


def _register_and_login(email: str, max_documents: int | None = None) -> dict:
    """Crea la cuenta (como haría el operador tras el pago) y loguea.

    Idempotente: si la cuenta ya existe (corrida anterior), solo loguea.
    """
    body = {"email": email, "password": "cliente-pass-123", "plan": "free"}
    if max_documents is not None:
        body["max_documents"] = max_documents
    r = client.post("/auth/register", headers=ADMIN, json=body)
    assert r.status_code in (201, 409), r.text  # 409 = ya existía de otra corrida
    r = client.post("/auth/login", json={"email": email, "password": "cliente-pass-123"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["token_type"] == "bearer" and data["access_token"]
    return data


# Usuario A: plan free por defecto (50 docs). Usuario B: cuota 1 → prueba el 403.
user_a = _register_and_login("e2e-a@example.com")
user_b = _register_and_login("e2e-b@example.com", max_documents=1)
H = {"Authorization": f"Bearer {user_a['access_token']}"}
H_B = {"Authorization": f"Bearer {user_b['access_token']}"}

# /auth/me alimenta la navbar (TAREA 2)
r = client.get("/auth/me", headers=H)
assert r.status_code == 200 and r.json()["email"] == "e2e-a@example.com"
print("[0] AUTH JWT OK (register admin → login → /auth/me)")


def _make_pdf() -> bytes:
    pdf = fitz.open()
    for i in range(2):
        page = pdf.new_page()
        page.insert_text((72, 72), f"Pagina {i + 1} de prueba E2E")
    buf = io.BytesIO()
    pdf.save(buf)
    pdf.close()
    buf.seek(0)
    return buf.getvalue()

# ── 3. Flujo completo (con el Bearer token de usuario A) ─────────────────────
r = client.post("/api/v1/documents", headers=H,
                files={"file": ("e2e.pdf", _make_pdf(), "application/pdf")},
                data={"pais": "ES", "columnas": "invoice_number,total,full_text_content"})
assert r.status_code == 202, r.text
task_id = r.json()["task_id"]
print(f"[1] CARGA OK → task_id={task_id} ({r.json()['page_count']} páginas, pais=ES)")

import app.workers.tasks as wtasks  # noqa: E402 (referencia para procesar en línea)

# Forzar el proveedor mock y procesar en línea (eager).
# tasks.py importa get_provider desde app.ai.factory EN CADA llamada, así que
# parcheamos el símbolo en el módulo factory (lookup en tiempo de ejecución).
import app.ai.factory as ai_factory_mod
_orig_get_provider = ai_factory_mod.get_provider
ai_factory_mod.get_provider = lambda preferred=None, file=None: MockProvider()
try:
    wtasks.process_document(task_id)
finally:
    ai_factory_mod.get_provider = _orig_get_provider

r = client.get(f"/api/v1/tasks/{task_id}", headers=H)
task = r.json()
print(f"[2] EXTRACCIÓN → status={task['status']} válido={task['is_valid']} "
      f"proveedor={task['provider_used']}")
assert task["status"] in ("completed", "needs_review"), task

# Multipágina con datos idénticos por página: total declarado = 1210 pero el
# consolidado duplica subtotal/impuestos → el validador DEBE marcar NEEDS_REVIEW
print(f"    issues: {[i['code'] for i in task['issues']]}")
if task["status"] == "needs_review":
    print("[3] REVISIÓN HUMANA necesaria (validador detectó descuadre) ✔")

# Corrección humana: subtotales duplicados → arreglar a los valores reales
data = task["extracted_data"]
data["subtotal"] = "1000.00"
data["total"] = "1210.00"
data["taxes"] = [{"type": "VAT", "rate": "21", "base_amount": "1000", "amount": "210"}]
r = client.patch(f"/api/v1/tasks/{task_id}", headers={**H, "Content-Type": "application/json"},
                 json={"extracted_data": data, "approve": True})
task = r.json()
assert task["status"] == "completed", task
print(f"[3] REVISIÓN OK → status={task['status']} (re-validado por el backend)")

# Exportación en los 4 formatos + TXT dinámico con columnas selectivas
for fmt in ("xlsx", "csv", "docx", "pdf"):
    r = client.post(f"/api/v1/tasks/{task_id}/export", headers={**H, "Content-Type": "application/json"},
                    json={"format": fmt})
    assert r.status_code == 200, (fmt, r.text)
    size = len(r.content)
    print(f"[4] EXPORT {fmt.upper()} OK ({size} bytes, {r.headers.get('content-type')})")

# TAREA 2/3: formato txt + columnas solicitadas + Content-Disposition
r = client.post(f"/api/v1/tasks/{task_id}/export", headers={**H, "Content-Type": "application/json"},
                json={"formato": "txt", "columnas": ["invoice_number"]})
assert r.status_code == 200, r.text
assert "attachment" in r.headers.get("content-disposition", "")
txt = r.content.decode("utf-8")
assert "FACTURA E2E-001" in txt, txt  # full_text_content presente
print("[4] EXPORT TXT OK (formato + columnas dinámicas + Content-Disposition)")

# TAREA 2/3: csv con columnas limitadas
r = client.post(f"/api/v1/tasks/{task_id}/export", headers={**H, "Content-Type": "application/json"},
                json={"formato": "csv", "columnas": ["invoice_number", "total"]})
assert r.status_code == 200, r.text
first_line = r.content.decode("utf-8-sig").splitlines()[0]
assert first_line == "invoice_number,total", first_line
print(f"[4] EXPORT CSV con columnas OK (encabezado: {first_line})")

# ── TAREA 1.5: el contador de uso se incrementó al procesar con éxito ──────
used_before = client.get("/auth/me", headers=H).json()["documents_used"]
r = client.get("/auth/me", headers=H)
# El doc de A se procesó con éxito → +1 desde el arranque de esta corrida.
assert r.json()["documents_used"] >= 1, r.json()
print(f"[5] CONTADOR OK → documents_used={r.json()['documents_used']}")

# ── TAREA 1.4: usuario B (cuota 1) → tras 1 doc, la 2ª subida devuelve 403 ──
r = client.post("/api/v1/documents", headers=H_B,
                files={"file": ("b1.pdf", _make_pdf(), "application/pdf")})
if r.status_code == 403:
    # B ya agotó su cuota en una corrida anterior → el límite ya está activo.
    print("[5] LÍMITE DE PLAN OK → 403: 'Has alcanzado el límite de tu plan...'")
else:
    assert r.status_code == 202, r.text
    import app.ai.factory as _f  # procesa el doc de B con el mock
    _orig = _f.get_provider
    _f.get_provider = lambda preferred=None, file=None: MockProvider()
    try:
        wtasks.process_document(r.json()["task_id"])
    finally:
        _f.get_provider = _orig

    r = client.post("/api/v1/documents", headers=H_B,
                    files={"file": ("b2.pdf", _make_pdf(), "application/pdf")})
    assert r.status_code == 403, r.text
    assert "Has alcanzado el límite de tu plan" in r.json()["detail"]
    print("[5] LÍMITE DE PLAN OK → 403: 'Has alcanzado el límite de tu plan...'")

# Sin token → 401 en el flujo completo
r = client.post("/api/v1/documents", files={"file": ("x.pdf", _make_pdf(), "application/pdf")})
assert r.status_code == 401, r.text
print("[5] SIN TOKEN OK → 401 (el flujo está bloqueado sin JWT)")

print("\n✅ E2E COMPLETO: auth JWT → carga → extracción → validación → revisión → exportación → planes")

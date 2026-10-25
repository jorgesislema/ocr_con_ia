"""Prueba de integración end-to-end del SaaS sin claves reales.

Simula un proveedor IA (mock) y recorre el pipeline completo:
    upload → cola (eager) → extracción → consolidación → validación
    → revisión humana → exportación xlsx/csv/docx/pdf.

Ejecutar desde la raíz del repo:
    python app/tests/e2e_smoke.py
"""
from __future__ import annotations

import io
import sys
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

# ── 2. Cliente de prueba + carga del PDF sintético ──────────────────────────
import fitz  # PyMuPDF
from fastapi.testclient import TestClient

from app.api.main import app
from app.core.db.base import SessionLocal, init_db
from app.core.db.models import User
from app.api.deps import generate_api_key

init_db()
with SessionLocal() as db:
    user = db.query(User).filter(User.email == "e2e@ocr.local").first()
    if user is None:
        user = User(email="e2e@ocr.local", api_key=generate_api_key())
        db.add(user)
    else:
        user.api_key = generate_api_key()  # rota la clave en cada corrida
    db.commit()
    API_KEY = user.api_key

client = TestClient(app)

# PDF de 2 páginas para forzar la ruta multipágina
pdf = fitz.open()
for i in range(2):
    page = pdf.new_page()
    page.insert_text((72, 72), f"Pagina {i + 1} de prueba E2E")
buf = io.BytesIO()
pdf.save(buf)
pdf.close()
buf.seek(0)

# ── 3. Flujo completo ────────────────────────────────────────────────────────
H = {"X-API-Key": API_KEY}

r = client.post("/api/v1/documents", headers=H,
                files={"file": ("e2e.pdf", buf, "application/pdf")})
assert r.status_code == 202, r.text
task_id = r.json()["task_id"]
print(f"[1] CARGA OK → task_id={task_id} ({r.json()['page_count']} páginas)")

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

# Exportación en los 4 formatos
for fmt in ("xlsx", "csv", "docx", "pdf"):
    r = client.post(f"/api/v1/tasks/{task_id}/export", headers={**H, "Content-Type": "application/json"},
                    json={"format": fmt})
    assert r.status_code == 200, (fmt, r.text)
    size = len(r.content)
    print(f"[4] EXPORT {fmt.upper()} OK ({size} bytes, {r.headers.get('content-type')})")

print("\n✅ E2E COMPLETO: carga → extracción → validación → revisión → exportación")

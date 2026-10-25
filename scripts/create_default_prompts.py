from pathlib import Path

PROMPTS = {
    "Factura Malaysia": '''Eres un experto en extracción de datos de facturas de Malaysia.
Analiza la imagen y extrae SOLO un JSON válido con el siguiente esquema:

```json
{
  "invoice_number": "número de factura",
  "date": "YYYY-MM-DD",
  "supplier": {
    "name": "nombre del proveedor",
    "registration_no": "número de registro (ROC/SST)",
    "address": "dirección completa"
  },
  "customer": {
    "name": "nombre del cliente",
    "address": "dirección"
  },
  "items": [
    {
      "description": "descripción del item",
      "quantity": 0,
      "unit_price": 0.00,
      "amount": 0.00
    }
  ],
  "totals": {
    "subtotal": 0.00,
    "gst_rate": "6%",
    "gst_amount": 0.00,
    "total": 0.00
  },
  "payment_method": "VISA CARD / CASH / etc"
}
```
''',

    "Factura Ecuador": '''Eres un experto en extracción de datos de facturas (Ecuador/LatAm).
Extrae SOLO un JSON con campos: invoice_number, date(YYYY-MM-DD), supplier{name, ruc, address}, customer{name, address}, items[], totals{subtotal, tax, total}.
Responde únicamente con JSON válido.
''',

    "Contrato - Extractor": '''Eres un asistente legal que extrae metadatos de contratos.
Extrae SOLO un JSON con campos: contract_id, parties[{name, role}], start_date, end_date, governing_law, clauses[] (texto).
''',

    "Prompt Genérico": '''Eres un extractor genérico. Analiza la imagen y responde SOLO con JSON plano con campos relevantes detectados.
Ejemplo mínimo: {"text": "Transcripción completa..."}
''',
}


def ensure_prompts():
    base = Path.home() / ".ocr_prompts"
    base.mkdir(parents=True, exist_ok=True)
    for name, content in PROMPTS.items():
        slug = name.replace(' ', '_').lower() + '.txt'
        path = base / 'examples'
        path.mkdir(parents=True, exist_ok=True)
        f = path / slug
        if not f.exists():
            f.write_text(content, encoding='utf-8')
            print(f'Created: {f}')
        else:
            print(f'Skipped existing: {f}')

if __name__ == '__main__':
    ensure_prompts()
    print('Done')

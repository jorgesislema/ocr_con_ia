"""
Prueba end-to-end: usa el template real clients/example_client.tpl (ahora español)
y simula la respuesta de DeepSeek para verificar columnas correctas en Excel.
"""
import sys, json
from pathlib import Path

sys.path.insert(0, r'h:\git\OCR con Glm\OCR-con-GLM-IA')

# Leer el template real
TPL_PATH = Path(r'h:\git\OCR con Glm\OCR-con-GLM-IA\prompts\clients\example_client.tpl')
USER_PROMPT = TPL_PATH.read_text(encoding='utf-8')
print(f'Template cargado: {len(USER_PROMPT)} chars')
print(f'Primeras 80 chars: {USER_PROMPT[:80]!r}')
print()

_ORIG_PROMPT = '''Eres un experto en extracción de facturas (España / Portugal). Recibes como entrada el texto extraído por OCR entre los marcadores ===BEGIN_OCR=== y ===END_OCR===. Analiza el texto y devuelve ÚNICAMENTE un JSON válido (sin texto adicional) con un array de objetos, uno por cada factura encontrada. Cada objeto debe tener exactamente estas claves (nombres en español, respetar mayúsculas tal como abajo):

[
{
"Nombre archivo": "", // string — nombre del fichero original (si no está, devolver "")
"Número Factura": "", // string — tal cual aparece
"Fecha": "", // string — ISO YYYY-MM-DD si es posible, si no transcribe tal cual
"Nombre proveedor": "", // string
"N.I.F.": "", // string
"Conceptos": "", // string — descripciones concatenadas separadas por " | "
"Base": 0.0, // float — suma de bases imponibles
"IVA": 0.0, // float — suma de importes IVA
"IRPF %": 0.0, // float — porcentaje de IRPF (numero sin %). 0.0 si no aplica
"Importe": 0.0, // float — base + IVA (antes de IRPF)
"B Exenta": 0.0, // float — base exenta
"Total": 0.0 // float — total final (aplicar IRPF si corresponde)
}
]

Reglas y prioridad de extracción:

Extrae Número Factura completo tal como aparece (no formatear).
Fecha: preferir ISO YYYY-MM-DD.
Nombre proveedor y N.I.F.: identificar al emisor.
Total: debe reflejar el importe final pagadero.
null solo si el campo es completamente inexistente e ilegible.
Salida exigida: Sólo el JSON array.
'''

# Simular lo que DeepSeek devolvería siguiendo el prompt del usuario
SIMULATED_LLM_RESPONSE = json.dumps([
    {
        "Nombre archivo": "2 Facil - Repetitiva.pdf",
        "Número Factura": "2018_0201",
        "Fecha": "2018-10-30",
        "Nombre proveedor": "EMPRENDE ON LINE, SL",
        "N.I.F.": "B-54643549",
        "Conceptos": "Cuota Fiscal - Sociedades | Cuota CONTABLE - Sociedades | LABORAL - Nómina Administrador",
        "Base": 149.0,
        "IVA": 31.29,
        "IRPF %": 0.0,
        "Importe": 180.29,
        "B Exenta": 0.0,
        "Total": 180.29
    }
], ensure_ascii=False, indent=2)

# Parchear _maybe_structure_with_llm para que devuelva nuestra respuesta simulada
import src.data.exporters as exp

original_maybe = exp._maybe_structure_with_llm

def mock_llm(raw_text, **kwargs):
    import json as _j
    arr = _j.loads(SIMULATED_LLM_RESPONSE)
    return arr[0] if arr else {}

exp._maybe_structure_with_llm = mock_llm

# Crear resultados de prueba
results = [
    {
        "id": "test-001",
        "filename": "2 Facil - Repetitiva.pdf",
        "pages": 1,
        "confidence": 1.0,
        "status": "Procesado",
        "text": "Factura 2018_0201 fecha 2018-10-30 total 180.29",
    }
]

rows = exp._prepare_rows(
    results,
    expected_keys=None,
    structuring_provider="DeepSeek",
    structuring_api_key="fake-key",
    structuring_model=None,
    structuring_base_url=None,
    prompt_template=USER_PROMPT,
)

print('Columnas en la fila resultante:')
for k, v in rows[0].items():
    print(f'  {k!r}: {v!r}')

EXPECTED_KEYS = ["Nombre archivo", "Número Factura", "Fecha", "Nombre proveedor",
                 "N.I.F.", "Conceptos", "Base", "IVA", "IRPF %", "Importe", "B Exenta", "Total"]

present = [k for k in EXPECTED_KEYS if k in rows[0]]
missing = [k for k in EXPECTED_KEYS if k not in rows[0]]

print(f'\nClaves del schema presentes: {len(present)}/12')
if missing:
    print('FALTAN:', missing)
else:
    print('OK: todas las 12 claves del prompt están en la fila.')

# Exportar a Excel de prueba
import pandas as pd
out = Path(r'i:\pruevas v2\resultado\test_schema_export.xlsx')
out.parent.mkdir(parents=True, exist_ok=True)
df = pd.DataFrame(rows)
df.to_excel(out, index=False)
print(f'\nExcel escrito en: {out}')
print('Columnas Excel:', list(df.columns))

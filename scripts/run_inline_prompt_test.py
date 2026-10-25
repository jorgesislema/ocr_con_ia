import json
import sys
from pathlib import Path

# asegurar import de src
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

# archivo mistral a probar
mistral_path = Path(r"i:\pruevas v2\resultado\10\1 Imposible_20260419_114551__mistral.md")
if not mistral_path.exists():
    print('Mistral file not found:', mistral_path)
    sys.exit(2)
text = mistral_path.read_text(encoding='utf-8')

results = [{
    'id': 1,
    'filename': '1 Imposible.pdf',
    'pages': 1,
    'confidence': 1.0,
    'status': 'Procesado',
    'text': text,
    'backend': 'mistral'
}]

# Prompt inline del usuario (exacto)
prompt_template = '''Eres un experto en extracción de facturas (España / Portugal). Recibes como entrada el texto extraído por OCR entre los marcadores ===BEGIN_OCR=== y ===END_OCR===. Analiza el texto y devuelve ÚNICAMENTE un JSON válido (sin texto adicional) con un array de objetos, uno por cada factura encontrada. Cada objeto debe tener exactamente estas claves (nombres en español, respetar mayúsculas tal como abajo):

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
Fecha: preferir ISO YYYY-MM-DD; si aparece DD/MM/YY o DD/MM/YYYY convertir; si solo mes/año, poner YYYY-MM-01; si no se puede, dejar el texto original.
Nombre proveedor y N.I.F.: identificar al emisor (no al receptor). Si hay varios nombres, elegir el que aparezca cerca del encabezado o del CIF.
Conceptos: concatenar las líneas de detalle relevantes (líneas de descripción), separadas por " | ". Truncar a 300 chars si es excesivo.
Base, IVA, B Exenta, Total: devolver en euros como float con punto decimal. Si en OCR usan coma decimal, convertir a punto. Si moneda distinta, incluir nota de moneda en Conceptos y convertir los números tal cual aparecen.
IRPF %: si aparece retención (p.ej. "Retención 15%"), devolver 15.0; si no aparece, 0.0.
Importe: calcular como Base + IVA si no aparece explícitamente.
Total: debe reflejar el importe final pagadero (si hay retención: Total = Base + IVA - (Base * IRPF_pct/100)). Si el documento muestra un Total diferente por descuentos o ajustes, use el Total explícito del documento.
null solo si el campo es completamente inexistente e ilegible; para campos numéricos preferir 0.0 si es plausible inferir que no existe (ej. ausencia de IRPF → 0.0).
Reglas de formato: todos los campos numéricos deben ser números (no strings). Las claves deben aparecer exactamente como en el esquema.
Salida exigida:

Sólo el JSON array, punto final. Ejemplo mínimo:
[...]

Notas para el motor:

Si el OCR incluye varias facturas en el mismo PDF, devolver un objeto por cada factura.
No añadas campos distintos a los especificados.
No incluyas explicaciones, tablas ni formatos alternativos.'''

print('Running export with inline prompt...')

from src.data.exporters import export_results
out = export_results(
    results,
    str(mistral_path.parent),
    'XLSX',
    merge=True,
    expected_keys=None,
    structuring_provider='DeepSeek',
    prompt_template=prompt_template,
)
print('Export paths:', out)

# QA
try:
    from src.core.qa_checker import compare_invoices_json_vs_excel
    if out:
        msgs, stats = compare_invoices_json_vs_excel(results, out[0])
        print('QA messages:')
        print(json.dumps(msgs, ensure_ascii=False, indent=2))
        print('QA stats:')
        print(json.dumps(stats, ensure_ascii=False, indent=2))
except Exception as e:
    print('QA compare failed:', e)

# print preview
for p in out:
    prev = Path(p).with_suffix(Path(p).suffix + '.preview.txt')
    try:
        print('\nPreview for', p)
        print(prev.read_text(encoding='utf-8'))
    except Exception as e:
        print('No preview for', p, e)

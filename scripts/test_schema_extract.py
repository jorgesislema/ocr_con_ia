import sys
sys.path.insert(0, r'h:\git\OCR con Glm\OCR-con-GLM-IA')

from src.data.exporters import _extract_schema_keys_from_prompt

USER_PROMPT = '''Eres un experto en extracción de facturas (España / Portugal). Recibes como entrada el texto extraído por OCR entre los marcadores ===BEGIN_OCR=== y ===END_OCR===. Analiza el texto y devuelve ÚNICAMENTE un JSON válido (sin texto adicional) con un array de objetos, uno por cada factura encontrada. Cada objeto debe tener exactamente estas claves (nombres en español, respetar mayúsculas tal como abajo):

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
'''

keys = _extract_schema_keys_from_prompt(USER_PROMPT)
print('Claves detectadas:', keys)
print('Total claves:', len(keys) if keys else 0)

EXPECTED = ["Nombre archivo", "Número Factura", "Fecha", "Nombre proveedor", "N.I.F.",
            "Conceptos", "Base", "IVA", "IRPF %", "Importe", "B Exenta", "Total"]

if keys:
    missing = [k for k in EXPECTED if k not in keys]
    extra   = [k for k in keys if k not in EXPECTED]
    if not missing and not extra:
        print('OK: todas las claves coinciden exactamente.')
    else:
        print('MISSING:', missing)
        print('EXTRA:',   extra)
else:
    print('ERROR: no se detectaron claves')

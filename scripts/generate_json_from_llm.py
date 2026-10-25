import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.data.exporters import _maybe_structure_with_llm
from src.data.exporters import _sanitize_ocr_text_for_prompt
from src.core.qa_checker import _parse_number

MISTRAL_FILE = Path(r"i:\pruevas v2\resultado\10\1 Imposible_20260419_114551__mistral.md")
if not MISTRAL_FILE.exists():
    print('Mistral file not found:', MISTRAL_FILE)
    sys.exit(2)
raw = MISTRAL_FILE.read_text(encoding='utf-8')

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

Reglas y prioridad de extracción:... (omitido para brevedad)'''

print('Calling LLM structuring...')
parsed = _maybe_structure_with_llm(raw, prompt_template=prompt_template, structuring_provider='DeepSeek')
print('LLM parsed:', parsed)

# Map parsed fields (many possible aliases) to required keys

def first_of(d, keys):
    for k in keys:
        if not d:
            continue
        if k in d and d[k] is not None and str(d[k]).strip() != "":
            return d[k]
    return None

# Build output
out = []
obj = {}
obj["Nombre archivo"] = "1 Imposible.pdf"
obj["Número Factura"] = first_of(parsed, ["invoice_number", "numero_factura", "header.invoice_number"]) or ""
# Fecha: try several keys
fecha = first_of(parsed, ["fecha", "date", "invoice_date", "header.invoice_date"])
obj["Fecha"] = fecha or ""
obj["Nombre proveedor"] = first_of(parsed, ["proveedor", "supplier", "supplier_name", "company_name"]) or ""
obj["N.I.F."] = first_of(parsed, ["nif_proveedor", "supplier_tax_id", "tax_id", "gst_number"]) or ""

# Conceptos: join descriptions
items = parsed.get("items") or parsed.get("lineas") or []
concepts = []
for it in items:
    if isinstance(it, dict):
        desc = it.get("description") or it.get("descripcion") or it.get("Concepto") or ""
        if desc:
            concepts.append(str(desc).strip())
obj["Conceptos"] = " | ".join(concepts)[:300]

# Numeric fields
base = first_of(parsed, ["subtotal", "subtotal_net", "base", "base_imponible"]) 
iva = first_of(parsed, ["iva", "tax_amount", "tax", "gst_amount"]) 
irpf = first_of(parsed, ["irpf", "retention", "retention_percent", "irpf_pct"]) 
total = first_of(parsed, ["total", "total_gross", "total_amount"]) 

# normalize numbers
base_n = _parse_number(base) or 0.0
iva_n = _parse_number(iva) or 0.0
irpf_n = _parse_number(irpf) or 0.0
total_n = _parse_number(total)

obj["Base"] = float(round(base_n,2))
obj["IVA"] = float(round(iva_n,2))
obj["IRPF %"] = float(round(irpf_n,2))
obj["Importe"] = float(round(base_n + iva_n,2))
obj["B Exenta"] = 0.0
# Compute Total applying IRPF if irpf present, else use explicit total if available
if total_n is not None:
    obj["Total"] = float(round(total_n,2))
else:
    obj["Total"] = float(round(base_n + iva_n - (base_n * (irpf_n/100.0)),2))

out.append(obj)

# write JSON sidecar next to mistral file
out_path = MISTRAL_FILE.parent / (MISTRAL_FILE.stem + '.structured.json')
out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
print('Wrote structured JSON to', out_path)
print(json.dumps(out, ensure_ascii=False, indent=2))

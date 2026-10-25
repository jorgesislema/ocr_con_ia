import re
import json
from pathlib import Path
from datetime import datetime

M_PATH = Path(r"i:\pruevas v2\resultado\10\1 Imposible_20260419_114551__mistral.md")
if not M_PATH.exists():
    print('file missing')
    raise SystemExit(1)
text = M_PATH.read_text(encoding='utf-8')
lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
# Nombre proveedor: first line
nombre_proveedor = lines[0] if lines else ""

# NIF: look for N.I.F. or CIF
nif = ""
for ln in lines[:20]:
    m = re.search(r"N\.I\.F\.\s*[:]?\s*([A-Z0-9\-\.]+)", ln, re.IGNORECASE)
    if m:
        nif = m.group(1).strip()
        break
    m2 = re.search(r"C\.I\.F\.\s*[:]?\s*([A-Z0-9\-\.]+)", ln, re.IGNORECASE)
    if m2:
        nif = m2.group(1).strip()
        break

# Numero Factura: find line containing 'Factura'
numero_factura = ""
for ln in lines[:40]:
    if 'factura' in ln.lower():
        numero_factura = ln
        break

# Fecha: find patterns like Fecha 6/09/21
fecha = ""
for ln in lines[:40]:
    if 'fecha' in ln.lower():
        m = re.search(r"(\d{1,2}[\-/]\d{1,2}[\-/]\d{2,4})", ln)
        if m:
            raw = m.group(1)
            # normalize
            parts = re.split(r"[\-/]", raw)
            if len(parts) == 3:
                d, mth, y = parts
                if len(y) == 2:
                    y = '20' + y
                try:
                    dt = datetime(int(y), int(mth), int(d))
                    fecha = dt.date().isoformat()
                except Exception:
                    fecha = raw
            else:
                fecha = raw
            break

# Parse markdown table lines for items
# Find table start index
table_lines = []
for i, ln in enumerate(lines):
    if re.match(r"\|\s*Cantidad\s*\|", ln, re.IGNORECASE):
        # collect subsequent table rows until blank or non-pipe
        j = i+2
        while j < len(lines) and lines[j].startswith('|'):
            table_lines.append(lines[j])
            j += 1
        break

items = []
for tl in table_lines:
    # split by | and strip
    parts = [p.strip() for p in tl.split('|')[1:-1]]
    if not parts:
        continue
    # assume columns: Cantidad, CONCEPTOS, Precio, TOTAL
    qty = parts[0] if len(parts) > 0 else ''
    desc = parts[1] if len(parts) > 1 else ''
    price = parts[2] if len(parts) > 2 else ''
    if desc or price or qty:
        items.append({'cantidad': qty, 'descripcion': desc, 'precio': price})

# Normalize numbers
def parse_amount(s):
    if not s:
        return None
    s = s.replace('€', '').replace('EUR', '').strip()
    s = s.replace('\xa0',' ').replace(' ', '')
    s = s.replace(',', '.')
    m = re.search(r"([0-9]+(?:\.[0-9]+)?)", s)
    if m:
        try:
            return float(m.group(1))
        except:
            return None
    return None

# compute base and iva
total_base = 0.0
total_iva = 0.0
rate = None
# detect 'IVA INCLUIDO 10%'
m = re.search(r"I\.V\.A\.\s*INCLUIDO\s*(\d{1,2})\%", text, re.IGNORECASE)
if m:
    rate = float(m.group(1))

for it in items:
    qty = int(re.sub(r"\D", "", it.get('cantidad') or '0') or 0)
    price = parse_amount(it.get('precio') or '') or 0.0
    if qty == 0 and price == 0.0:
        continue
    if rate:
        # price includes VAT, compute base per unit
        base_unit = price / (1 + rate/100.0)
        iva_unit = price - base_unit
        total_base += base_unit * qty
        total_iva += iva_unit * qty
    else:
        # assume price is base
        total_base += price * qty

# Round
total_base = round(total_base, 2)
total_iva = round(total_iva, 2)
importe = round(total_base + total_iva, 2)
irpf_pct = 0.0
# search for retencion
m = re.search(r"Retención\s*(\d{1,2})\%", text, re.IGNORECASE)
if m:
    irpf_pct = float(m.group(1))

# B Exenta default 0.0
b_exenta = 0.0
# Total applying IRPF
total_final = round(importe - (total_base * irpf_pct/100.0), 2)

output = [
    {
        "Nombre archivo": "1 Imposible.pdf",
        "Número Factura": numero_factura or "",
        "Fecha": fecha or "",
        "Nombre proveedor": nombre_proveedor or "",
        "N.I.F.": nif or "",
        "Conceptos": ' | '.join([it['descripcion'] for it in items if it.get('descripcion')])[:300],
        "Base": float(total_base),
        "IVA": float(total_iva),
        "IRPF %": float(irpf_pct),
        "Importe": float(importe),
        "B Exenta": float(b_exenta),
        "Total": float(total_final)
    }
]

# write JSON
outp = M_PATH.parent / (M_PATH.stem + '.heuristic.json')
outp.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding='utf-8')
print('Wrote', outp)
print(json.dumps(output, ensure_ascii=False, indent=2))

# Also create Excel
import pandas as pd
from pathlib import Path

df = pd.json_normalize(output)
path_x = M_PATH.parent / 'heuristic_output.xlsx'
df.to_excel(path_x, index=False)
print('Wrote excel', path_x)

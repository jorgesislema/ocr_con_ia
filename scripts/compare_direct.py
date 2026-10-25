import json
from pathlib import Path
import pandas as pd
import re

json_path = Path(r"i:\pruevas v2\resultado\10\1 Imposible_20260419_114551__mistral.heuristic.json")
excel_path = Path(r"i:\pruevas v2\resultado\10\heuristic_output.xlsx")

if not json_path.exists() or not excel_path.exists():
    print('Missing files:', json_path.exists(), excel_path.exists())
    raise SystemExit(1)

invoices = json.loads(json_path.read_text(encoding='utf-8'))
df = pd.read_excel(excel_path, engine='openpyxl')

# Normalize column names to simple keys
col_map = {c: c.strip() for c in df.columns}
df.rename(columns=col_map, inplace=True)

# helper to parse numbers
def parse_num(x):
    if x is None:
        return None
    if isinstance(x, (int,float)):
        return float(x)
    s = str(x)
    s = re.sub(r"[^0-9,\.-]", "", s)
    s = s.replace(',', '.')
    try:
        return float(s)
    except:
        return None

rows = []
for inv in invoices:
    name = inv.get('Nombre archivo') or ''
    # try match by Nombre archivo or Número Factura
    row = None
    if 'Nombre archivo' in df.columns:
        matches = df[df['Nombre archivo'].astype(str).str.contains(name.split('.')[0], na=False)]
        if not matches.empty:
            row = matches.iloc[0]
    if row is None and 'Número Factura' in df.columns:
        num = inv.get('Número Factura') or ''
        matches = df[df['Número Factura'].astype(str).str.contains(str(num), na=False)]
        if not matches.empty:
            row = matches.iloc[0]
    rows.append((inv, row))

# Print comparison
for inv, row in rows:
    print('--- Invoice:', inv.get('Nombre archivo'))
    print('JSON -> Base:', inv.get('Base'), 'IVA:', inv.get('IVA'), 'Total:', inv.get('Total'))
    if row is None:
        print('No matching row found in Excel')
        continue
    # extract from excel
    excel_base = None
    excel_iva = None
    excel_total = None
    for col in df.columns:
        lc = col.lower()
        if 'base' in lc and excel_base is None:
            excel_base = parse_num(row[col])
        if (lc == 'iva' or 'iva' in lc) and excel_iva is None:
            excel_iva = parse_num(row[col])
        if 'total' in lc and excel_total is None:
            excel_total = parse_num(row[col])
    print('Excel -> Base:', excel_base, 'IVA:', excel_iva, 'Total:', excel_total)
    # compute diffs
    def show_diff(k, jv, ev):
        if jv is None and ev is None:
            print(f'{k}: both None')
            return
        if jv is None:
            print(f'{k}: JSON None vs Excel {ev}')
            return
        if ev is None:
            print(f'{k}: JSON {jv} vs Excel None')
            return
        diff = float(jv) - float(ev)
        print(f'{k}: JSON {jv} vs Excel {ev} -> diff {diff:.2f}')
    show_diff('Base', inv.get('Base'), excel_base)
    show_diff('IVA', inv.get('IVA'), excel_iva)
    show_diff('Total', inv.get('Total'), excel_total)

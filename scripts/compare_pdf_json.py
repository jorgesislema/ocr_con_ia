import re
import json
from pathlib import Path
from decimal import Decimal, ROUND_HALF_UP

try:
    from PyPDF2 import PdfReader
except Exception:
    PdfReader = None


def extract_text_from_pdf(path: Path) -> str:
    if PdfReader is None:
        raise RuntimeError('PyPDF2 not available in environment')
    reader = PdfReader(str(path))
    texts = []
    for p in reader.pages:
        try:
            texts.append(p.extract_text() or '')
        except Exception:
            texts.append('')
    return '\n'.join(texts)


def parse_invoice_from_text(text: str) -> dict:
    out = {}
    # Fecha: formats like 'Fecha 6/09/21'
    m = re.search(r'Fecha\s+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})', text)
    if m:
        out['Fecha'] = m.group(1)
    # Número factura
    m = re.search(r'Factura[-\s]*B[^\d]*(\d+)', text, re.IGNORECASE)
    if m:
        out['Número Factura'] = m.group(1)
    # NIF
    m = re.search(r'N\.I\.F\.\s*([A-Z0-9-]+)', text)
    if m:
        out['NIF'] = m.group(1)
    # IVA incluido
    m = re.search(r'I\.?V\.?A\.?\s*INCLUIDO\s*(\d{1,2})%', text, re.IGNORECASE)
    if m:
        out['IVA_incluido_pct'] = int(m.group(1))
    # Price lines: capture quantity and unit price like '5 | Comidas |38.30 €'
    prices = []
    for mm in re.finditer(r'\|\s*(\d+)\s*\|[^|]*\|\s*([0-9]+[.,][0-9]{2})\s*€', text):
        qty = int(mm.group(1))
        price = float(mm.group(2).replace(',', '.'))
        prices.append((qty, price))
    if prices:
        out['lines'] = prices
        total = sum(q*p for q,p in prices)
        out['Total_calc'] = float(Decimal(total).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))
        # if IVA included, compute base and iva
        if 'IVA_incluido_pct' in out:
            rate = out['IVA_incluido_pct']/100.0
            base = out['Total_calc'] / (1+rate)
            iva = out['Total_calc'] - base
            out['Base_calc'] = float(Decimal(base).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))
            out['IVA_calc'] = float(Decimal(iva).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))
    return out


def find_pdf_for_json(json_invoice: dict, folder: Path) -> Path:
    name = json_invoice.get('Nombre archivo') or ''
    if not name:
        return None
    p = folder / name
    if p.exists():
        return p
    # try name without extension
    stem = Path(name).stem
    for f in folder.glob(stem + '*'):
        if f.suffix.lower() in ['.pdf']:
            return f
    return None


if __name__ == '__main__':
    json_path = Path(r"i:\pruevas v2\resultado\10\1 Imposible_20260419_114551__mistral.heuristic.json")
    if not json_path.exists():
        print('JSON not found:', json_path)
        raise SystemExit(1)
    invoices = json.loads(json_path.read_text(encoding='utf-8'))
    folder = Path(json_path.parent)
    for inv in invoices:
        print('--- Invoice JSON Nombre archivo:', inv.get('Nombre archivo'))
        pdf = find_pdf_for_json(inv, folder)
        if not pdf:
            print('PDF not found for', inv.get('Nombre archivo'))
            continue
        print('Using PDF:', pdf)
        try:
            txt = extract_text_from_pdf(pdf)
        except Exception as e:
            print('Error extracting PDF text:', e)
            continue
        parsed = parse_invoice_from_text(txt)
        print('Parsed from PDF:', parsed)
        # compare numeric
        def cmp_val(key, jkey, round2=True):
            j = inv.get(jkey)
            p = parsed.get(key)
            print(f"Compare {jkey}: JSON={j} PDF_parsed={p}")
        cmp_val('Total_calc', 'Total')
        cmp_val('Base_calc', 'Base')
        cmp_val('IVA_calc', 'IVA')
        # print lines
        if 'lines' in parsed:
            print('Lines parsed (qty,unit_price):', parsed['lines'])

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

json_path = Path(r"i:\pruevas v2\resultado\10\1 Imposible_20260419_114551__mistral.heuristic.json")
excel_path = Path(r"i:\pruevas v2\resultado\10\heuristic_output.xlsx")

if not json_path.exists():
    print('JSON not found:', json_path)
    sys.exit(2)
if not excel_path.exists():
    print('Excel not found:', excel_path)
    sys.exit(2)

invoices = json.loads(json_path.read_text(encoding='utf-8'))

from src.core.qa_checker import compare_invoices_json_vs_excel
msgs, stats = compare_invoices_json_vs_excel(invoices, excel_path)
print('QA messages:')
print('\n'.join(msgs))
print('\nQA stats:')
import json as _j
print(_j.dumps(stats, ensure_ascii=False, indent=2))

import sys
import json
from pathlib import Path

if len(sys.argv) < 3:
    print('Usage: run_export_from_qa.py <qa_json_path> <out_dir> [provider]')
    sys.exit(1)
qa_path = Path(sys.argv[1])
out_dir = Path(sys.argv[2])
provider = sys.argv[3] if len(sys.argv) > 3 else None

if not qa_path.exists():
    print('qa_file_missing')
    sys.exit(2)

D = json.loads(qa_path.read_text(encoding='utf-8'))
raw = D.get('raw_mistral') or {}
results = []
for name, text in raw.items():
    results.append({'filename': name, 'id': name, 'pages': 1, 'confidence': 1.0, 'status': 'processed', 'text': text})

from src.data.exporters import export_to_xlsx
paths = export_to_xlsx(results, out_dir, merge=True, structuring_provider=provider)
print('exported:', paths)

import json
import sys
from pathlib import Path

# Asegurar que el repo root está en sys.path para importar `src`
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

ROOT = Path(r"i:\pruevas v2\resultado\10")
if not ROOT.exists():
    print('Result dir not found:', ROOT)
    sys.exit(2)

# collect mistral sidecars
mistral_files = sorted(ROOT.glob('*__mistral.md'))
results = []
for i, p in enumerate(mistral_files, start=1):
    txt = p.read_text(encoding='utf-8')
    stem = p.stem
    # derive filename: take part before first '__' or underscore timestamp
    orig = stem.split('__')[0]
    # try to remove trailing timestamp-like segments separated by '_'
    parts = orig.split('_')
    if len(parts) > 1 and parts[-1].isdigit():
        orig_name = ' '.join(parts[:-1])
    else:
        orig_name = ' '.join(parts)
    filename = orig_name + '.pdf'
    results.append({
        'id': i,
        'filename': filename,
        'pages': 1,
        'confidence': 1.0,
        'status': 'Procesado',
        'text': txt,
        'backend': 'mistral'
    })

print('Found', len(results), 'mistral files')

# load prompt template content if available
prompt_path = REPO_ROOT / 'prompts' / 'clients' / 'example_client.tpl'
prompt_content = None
if prompt_path.exists():
    prompt_content = prompt_path.read_text(encoding='utf-8')
    print('Loaded prompt from', prompt_path)
else:
    print('Prompt template not found at', prompt_path)

# run exporter
from src.data.exporters import export_results
out = export_results(
    results,
    str(ROOT),
    'XLSX',
    merge=True,
    expected_keys=None,
    structuring_provider='DeepSeek',
    prompt_template=prompt_content,
)
print('Export paths:', out)

# run QA compare
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

# print preview sidecar
for p in out:
    prev = Path(p).with_suffix(Path(p).suffix + '.preview.txt')
    try:
        print('\nPreview for', p)
        print(prev.read_text(encoding='utf-8'))
    except Exception as e:
        print('No preview for', p, e)

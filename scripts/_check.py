import ast, sys
files = [
    'src/ui/config_panel.py',
    'src/ui/schema_panel.py',
    'src/ui/main_window.py',
    'src/ui/worker.py',
    'src/core/ocr_engine.py',
    'src/core/exporter.py',
    'src/data/exporters.py',
]
ok = True
for f in files:
    try:
        ast.parse(open(f, encoding='utf-8').read())
        print('OK:', f)
    except SyntaxError as e:
        print('ERROR:', f, e)
        ok = False
sys.exit(0 if ok else 1)

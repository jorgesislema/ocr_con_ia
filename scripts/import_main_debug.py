import importlib.util, traceback, sys
p = r'h:/git/OCR con Glm/OCR-con-GLM-IA/src/ui/main_window.py'
try:
    spec = importlib.util.spec_from_file_location('mw', p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    print('Imported OK')
except Exception as e:
    traceback.print_exc()
    sys.exit(1)

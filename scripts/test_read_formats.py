from pathlib import Path
from PIL import Image

from src.core.ocr_engine import OCREngine

# Mock: reemplazamos la llamada real a la API por una que retorna texto y contadores
def _fake_call(self, b64: str):
    return "MOCK_TEXT", 3, 5

OCREngine._call_glm = _fake_call

# Creamos instancia sin __init__ para evitar requerir API key / cliente
engine = object.__new__(OCREngine)
engine._prompt = "MOCK_PROMPT"

# Directorio temporal de prueba
tmp = Path("tmp_format_test")
tmp.mkdir(exist_ok=True)

# Crear una imagen y guardarla en varios formatos
img = Image.new("RGB", (200, 100), color=(73, 109, 137))
img.save(tmp / "test.png")
img.save(tmp / "test.jpg")
# Guardar como PDF (una página)
img.save(tmp / "test.pdf", "PDF", resolution=100.0)
img.save(tmp / "test.tif")

files = [tmp / "test.png", tmp / "test.jpg", tmp / "test.pdf", tmp / "test.tif", tmp / "test.bmp"]

for f in files:
    if not f.exists():
        print(f.name, "-> MISSING")
        continue
    try:
        out = engine.process_file(str(f))
        print(f.name, "-> OK:", out)
    except Exception as e:
        print(f.name, "-> ERROR:", e)

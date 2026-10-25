"""Regenera Excel/CSV/DOCX a partir de un archivo .qa.json que contiene
`raw_mistral` con el markdown recuperado por Mistral OCR.

Uso:
    python scripts/reexport_from_qa.py "I:\\pruevas v2\\resultado\\2\\ocr_resultados_20260416_125829.xlsx.qa.json"

El script crea archivos en la misma carpeta de input.
"""
from pathlib import Path
import json
import sys

if len(sys.argv) < 2:
    print("Uso: reexport_from_qa.py <path_to_qa.json>")
    sys.exit(2)

qa_path = Path(sys.argv[1])
if not qa_path.exists():
    print("No existe:", qa_path)
    sys.exit(2)

out_dir = qa_path.parent
data = json.loads(qa_path.read_text(encoding="utf-8"))
raw = data.get("raw_mistral") or {}

results = []
idx = 1
for name, txt in raw.items():
    results.append({
        "id": idx,
        "filename": name,
        "pages": 1,
        "confidence": 1.0,
        "status": "Procesado",
        "text": txt,
    })
    idx += 1

print(f"Generando exports para {len(results)} documentos en: {out_dir}")

# Añadir workspace al path
import os
root = Path(__file__).resolve().parents[1]
if str(root) not in sys.path:
    sys.path.insert(0, str(root))

try:
    from src.data.exporters import export_to_xlsx, export_to_csv, export_to_docx
except Exception as e:
    print("Error importando exporters:", e)
    raise

xlsx_paths = export_to_xlsx(results, out_dir, merge=True)
csv_paths = export_to_csv(results, out_dir, merge=True)
docx_paths = []
try:
    docx_paths = export_to_docx(results, out_dir, merge=True)
except Exception:
    pass

print("XLSX:", xlsx_paths)
print("CSV:", csv_paths)
print("DOCX:", docx_paths)
print("Preview sidecars generados junto a los archivos.")

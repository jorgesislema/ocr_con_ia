#!/usr/bin/env python3
"""Script de inicialización colocable en la raíz del repo.

Crea la estructura dentro de la carpeta del repositorio.
Ejecuta: python scripts/init_project.py
"""
from pathlib import Path
import datetime

ROOT = Path(__file__).resolve().parent

STRUCT = {
    "src/core": ["ocr_engine.py", "preprocessor.py", "security.py"],
    "src/data": ["database.py", "exporters.py", "validators.py"],
    "src/ui": ["main_window.py", "dashboard.py"],
    "tests/unit": ["__init__.py"],
    "tests/integration": ["__init__.py"],
    "logs": [".gitkeep"],
    "output": [".gitkeep"],
}

TEMPLATES = {
    ".env": """# Variables sensibles: completar localmente
TOKEN=
GLM_API_KEY=
DEBUG=false
""",

    ".gitignore": """
# Entorno virtual
.venv/

# Python
__pycache__/
*.py[cod]
*.pyo

# Env
.env

# Editor
.vscode/

# Outputs y logs
logs/
output/

# OS
.DS_Store
""",

    "requirements.txt": """
opencv-python-headless==4.8.0
numpy==1.26.2
pandas==2.2.2
openpyxl==3.1.2
python-docx==0.8.11
python-dotenv==1.0.0
keyring==24.1.0
cryptography==40.0.2
pydantic==2.5.1
Pillow==10.1.0
# sqlite3 es parte de la librería estándar
""",
}

FILE_HEADER = "Archivo generado por scripts/init_project.py\nFecha: {date}\n"
DEFAULT_CONTENT = {"py": "# {path}\n\n"}


def create_structure():
    created = []
    for d, files in STRUCT.items():
        dirpath = ROOT / d
        dirpath.mkdir(parents=True, exist_ok=True)
        for f in files:
            fp = dirpath / f
            if not fp.exists():
                if fp.suffix == ".py":
                    content = FILE_HEADER.format(date=datetime.datetime.utcnow().isoformat()) + "\n" + DEFAULT_CONTENT["py"].format(path=str(fp.relative_to(ROOT)))
                else:
                    content = ""
                fp.write_text(content, encoding="utf-8")
                created.append(str(fp.relative_to(ROOT)))

    for name, body in TEMPLATES.items():
        fp = ROOT / name
        if not fp.exists():
            fp.write_text(body.strip() + "\n", encoding="utf-8")
            created.append(name)

    readme = ROOT / "README.md"
    if not readme.exists():
        readme.write_text("# PROYECTO_OCR_GLM\n\nInicio rápido. Ejecuta `python scripts/init_project.py` desde la carpeta del repo para recrear la estructura.", encoding="utf-8")
        created.append("README.md")

    return created


def main():
    created = create_structure()
    if created:
        print("Archivos/directorios creados:")
        for c in created:
            print(" -", c)
    else:
        print("La estructura ya existe. No se realizaron cambios.")


if __name__ == "__main__":
    main()

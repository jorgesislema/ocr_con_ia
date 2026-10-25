import traceback
import sys
import logging
from pathlib import Path

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)s %(name)s %(message)s')
# Reducir ruido de matplotlib y font_manager desde el arranque
for _noisy in ("matplotlib", "matplotlib.font_manager"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

# Add project root to sys.path so `import src` works when running from scripts/
script_dir = Path(__file__).resolve().parent
project_root = script_dir.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Cargar variables de entorno desde .env (si existe) antes de importar nada más
_env_file = project_root / ".env"
if _env_file.exists():
    try:
        try:
            from dotenv import load_dotenv
        except ImportError:
            logging.getLogger("ocr.startup").warning("python-dotenv no está instalado, saltando carga de .env")
        else:
            load_dotenv(dotenv_path=_env_file, override=False)
            logging.getLogger("ocr.startup").info(".env cargado desde %s", _env_file)
    except Exception as _e:
        logging.getLogger("ocr.startup").warning("No se pudo cargar .env: %s", _e)

try:
    from src.ui.main_window import start_ui
    start_ui()
except Exception:
    traceback.print_exc()
    sys.exit(1)

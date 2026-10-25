from __future__ import annotations

import json
import re
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional


_PROMPT_EXTENSIONS = (".txt", ".json", ".tpl")


def _slugify(text: str) -> str:
    text = text.strip()
    text = text.replace(" ", "_")
    text = re.sub(r"[^A-Za-z0-9_\-]", "", text)
    text = re.sub(r"_+", "_", text)
    return text.lower()


class PromptManager:
    """Gestión simple de prompts por proyecto.

    Guarda prompts en: ~/.ocr_prompts/{category}/{name}.txt
    """

    def __init__(self, base_path: Optional[Path] = None):
        self.base_path = Path(base_path) if base_path else Path.home() / ".ocr_prompts"
        self.base_path.mkdir(parents=True, exist_ok=True)

    def list_prompts(self) -> List[Dict]:
        """Retorna lista de prompts disponibles con metadatos.

        Cada entrada: {"name": ..., "file": ..., "path": ..., "type": ...}
        """
        prompts: List[Dict] = []
        files: list[Path] = []
        for ext in _PROMPT_EXTENSIONS:
            files.extend(self.base_path.rglob(f"*{ext}"))

        for p in sorted(set(files)):
            try:
                rel = p.relative_to(self.base_path)
                parts = rel.parts
                category = parts[0] if len(parts) > 1 else p.parent.name
            except Exception:
                category = p.parent.name

            # Human-friendly name from filename
            name = p.stem.replace("_", " ").strip()
            name = name.title() if name else p.name

            prompts.append({
                "name": name,
                "file": p.name,
                "path": str(p),
                "type": category,
                "ext": p.suffix.lower(),
            })

        # order by type then name
        prompts.sort(key=lambda x: (x.get("type", ""), x.get("name", "")))
        return prompts

    def _find_prompt_file(self, prompt_name: str) -> Path:
        """Busca un archivo de prompt por nombre, filename o ruta absoluta.

        Heurísticas (en orden): ruta absoluta, exact filename, stem match (case-insensitive).
        """
        cand = Path(prompt_name)
        if cand.exists() and cand.is_file():
            return cand

        # exact filename or stem en formatos soportados
        for ext in _PROMPT_EXTENSIONS:
            for p in self.base_path.rglob(f"*{ext}"):
                if p.name == prompt_name:
                    return p
        for ext in _PROMPT_EXTENSIONS:
            for p in self.base_path.rglob(f"*{ext}"):
                if p.stem.lower() == prompt_name.lower():
                    return p

        # last try: case-insensitive filename
        for ext in _PROMPT_EXTENSIONS:
            for p in self.base_path.rglob(f"*{ext}"):
                if p.name.lower() == prompt_name.lower():
                    return p

        raise FileNotFoundError(f"Prompt not found: {prompt_name}")

    def load_prompt(self, prompt_name: str, category: str | None = None) -> str:
        """Carga el contenido del prompt seleccionado (utf-8).

        `prompt_name` puede ser el nombre humano (stem), filename o ruta absoluta.
        Si se proporciona `category`, intenta primero `~/.ocr_prompts/{category}/{name}.*`.
        """
        p = None
        if category:
            cat_dir = self.base_path / _slugify(category)
            name = str(prompt_name).strip()
            if "." in name:
                cand = cat_dir / name
                if cand.exists() and cand.is_file():
                    p = cand
            if p is None:
                for ext in _PROMPT_EXTENSIONS:
                    cand = cat_dir / f"{_slugify(name)}{ext}"
                    if cand.exists() and cand.is_file():
                        p = cand
                        break
        if p is None:
            p = self._find_prompt_file(prompt_name)
        if p.suffix.lower() == ".json":
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                for key in ("prompt", "template", "content", "text"):
                    val = data.get(key)
                    if isinstance(val, str) and val.strip():
                        return val
                return json.dumps(data, ensure_ascii=False, indent=2)
            if isinstance(data, list):
                return json.dumps(data, ensure_ascii=False, indent=2)
            return str(data)
        return p.read_text(encoding="utf-8")

    def save_prompt(
        self,
        name: str,
        content: str,
        category: str = "custom",
        file_format: str = "txt",
    ) -> Path:
        """Guarda un nuevo prompt en `~/.ocr_prompts/{category}/{slug(name)}.txt`.

        Si ya existe un archivo con el mismo nombre, añade un sufijo timestamp.
        Retorna la Path del archivo creado.
        """
        safe_cat = _slugify(category) or "custom"
        dest_dir = self.base_path / safe_cat
        dest_dir.mkdir(parents=True, exist_ok=True)

        ext = str(file_format or "txt").strip().lower().lstrip(".")
        if ext not in {"txt", "json", "tpl"}:
            ext = "txt"

        filename = f"{_slugify(name)}.{ext}"
        dest = dest_dir / filename
        if dest.exists():
            ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")
            dest = dest_dir / f"{_slugify(name)}_{ts}.{ext}"

        dest.write_text(content, encoding="utf-8")
        return dest

    def delete_prompt(self, prompt_name: str) -> bool:
        """Elimina un prompt personalizado. Retorna True si se borró.

        Levanta FileNotFoundError si no existe.
        """
        p = self._find_prompt_file(prompt_name)
        p.unlink()
        return True

    def get_prompt_preview(self, prompt_name: str, max_chars: int = 200) -> str:
        """Retorna los primeros `max_chars` del prompt para preview.

        Si el prompt no existe se lanza FileNotFoundError.
        """
        txt = self.load_prompt(prompt_name)
        return txt[:max_chars]


__all__ = ["PromptManager"]

import hashlib
import re
from pathlib import Path
from typing import Tuple, List, Dict

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"
_USER_TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "user_templates"

# ── Reglas de auto-selección (orden de prioridad descendente) ─────────────────
# Cada regla: (regex, candidatos en orden preferente: .txt primero, .tpl fallback)
_AUTO_RULES: list[tuple[re.Pattern, list[str]]] = [
    (
        re.compile(r"fact|inv(oice)?|factura", re.IGNORECASE),
        ["document_types/invoice.txt", "document_types/invoice.tpl"],
    ),
    (
        re.compile(r"contr(act|ato)|acuerdo|agre(ement)?", re.IGNORECASE),
        ["document_types/contract.txt", "document_types/contract.tpl"],
    ),
    (
        re.compile(r"recib|receipt|recei|nota.?cr[eé]d|nota.?deb", re.IGNORECASE),
        ["document_types/receipt.txt", "document_types/receipt.tpl"],
    ),
]

# Mapa directo doc_type_hint → candidatos en orden preferente
_DOC_TYPE_MAP: dict[str, list[str]] = {
    "invoice":  ["document_types/invoice.txt",  "document_types/invoice.tpl"],
    "factura":  ["document_types/invoice.txt",  "document_types/invoice.tpl"],
    "contract": ["document_types/contract.txt", "document_types/contract.tpl"],
    "contrato": ["document_types/contract.txt", "document_types/contract.tpl"],
    "receipt":  ["document_types/receipt.txt",  "document_types/receipt.tpl"],
    "recibo":   ["document_types/receipt.txt",  "document_types/receipt.tpl"],
    "default":  ["system/default.tpl"],
}

# Categorías que se excluyen de auto-selección
_EXCLUDED_CATEGORIES = {"drafts"}


def _read_template_file(name: str) -> str:
    """Lee un template por nombre o ruta relativa.

    Soporta tanto nombres planos (``"invoice.tpl"``) como rutas relativas
    (``"document_types/invoice.tpl"``). Busca primero en PROMPTS_DIR, luego
    en _USER_TEMPLATES_DIR.
    """
    # Intentar como ruta relativa dentro de PROMPTS_DIR (incluye subdirs)
    p = PROMPTS_DIR / name
    if p.exists() and p.is_file():
        return p.read_text(encoding="utf-8")
    # Intentar en user_templates
    pu = _USER_TEMPLATES_DIR / name
    if pu.exists() and pu.is_file():
        return pu.read_text(encoding="utf-8")
    raise FileNotFoundError(name)


def load_render_prompt(candidates: List[str], context: Dict | None = None) -> Tuple[str, str, str]:
    """Busca en order los templates indicados en `candidates`, renderiza con Jinja2 si está
    disponible y devuelve (text, used_name, checksum_sha256).

    Si no se encuentra ningún template, lanza FileNotFoundError.
    Si Jinja2 no está disponible, devuelve el contenido crudo del primer template encontrado.
    """
    ctx = context or {}
    # normalize candidates
    for name in candidates:
        if not name:
            continue
        try:
            raw = _read_template_file(name)
        except FileNotFoundError:
            continue
        # try render with jinja2
        try:
            from jinja2 import Environment, BaseLoader, meta

            env = Environment(loader=BaseLoader(), autoescape=False)
            template = env.from_string(raw)
            text = template.render(**ctx)
        except Exception:
            # fallback: no jinja2 or rendering error -> use raw
            text = raw
        checksum = hashlib.sha256(text.encode("utf-8")).hexdigest()
        return text, name, checksum
    raise FileNotFoundError("No template found in candidates: %s" % ", ".join(candidates))


def get_active_prompt(candidates: List[str], context: Dict | None = None) -> str:
    """Devuelve el CONTENIDO renderizado de la plantilla activa.

    Este helper existe para evitar ambigüedad entre ruta y contenido.
    """
    text, _used_name, _checksum = load_render_prompt(candidates, context or {})
    return text


def scan_prompts_dir() -> dict[str, list[dict]]:
    """Escanea PROMPTS_DIR recursivamente y devuelve un árbol categorizado.

    Delegado en :func:`load_prompt_tree` — mantenido por compatibilidad con
    código existente que importa directamente ``scan_prompts_dir``.
    """
    # load_prompt_tree se define más adelante; la llamada directa funciona porque
    # Python resuelve los nombres en tiempo de ejecución, no de definición.
    return load_prompt_tree(PROMPTS_DIR)


def auto_select_prompt(filename: str, doc_type_hint: str | None = None) -> str | None:  # noqa: E501
    """Selecciona automáticamente el prompt más adecuado para un archivo dado.

    Parámetros
    ----------
    filename :
        Nombre del archivo a procesar (p. ej. ``"FACT-2024-001.pdf"``).
    doc_type_hint :
        Pista sobre el tipo (p. ej. ``"invoice"``). Tiene prioridad sobre el nombre.

    Retorna
    -------
    Ruta relativa a ``PROMPTS_DIR`` del prompt seleccionado, o ``None`` si no
    hay coincidencia y no existe ningún fallback.
    """
    def _first_existing(candidates: list[str]) -> str | None:
        """Devuelve la primera ruta candidata que exista en PROMPTS_DIR."""
        for c in candidates:
            if (PROMPTS_DIR / c).exists():
                return c
        return None

    # 1. doc_type_hint directo
    if doc_type_hint:
        candidates = _DOC_TYPE_MAP.get(doc_type_hint.lower().strip(), [])
        found = _first_existing(candidates)
        if found:
            return found

    # 2. Regex sobre el stem del nombre de archivo
    stem = Path(filename).stem if filename else ""
    for pattern, candidates in _AUTO_RULES:
        if pattern.search(stem):
            found = _first_existing(candidates)
            if found:
                return found
            # intento fallback al nivel raíz con el mismo nombre de fichero
            for c in candidates:
                root_candidate = PROMPTS_DIR / Path(c).name
                if root_candidate.exists():
                    return root_candidate.name

    # 3. Fallbacks genéricos: foto_libre → default (cualquier extensión)
    for fallback in (
        "system/foto_libre.txt",
        "system/foto_libre.tpl",
        "system/default.tpl",
        "default.tpl",
    ):
        if (PROMPTS_DIR / fallback).exists():
            return fallback

    return None


def load_prompt_tree(root_dir: str | Path | None = None) -> dict[str, list[dict]]:
    """Escanea el directorio de prompts y devuelve un árbol categorizado.

    Equivalente a :func:`scan_prompts_dir` pero acepta ``root_dir`` como
    parámetro, lo que permite apuntar a directorios alternativos en tests.

    Parámetros
    ----------
    root_dir :
        Directorio raíz de prompts. Si es ``None``, usa :data:`PROMPTS_DIR`.

    Retorna
    -------
    Dict ``{categoría: [{name, rel_path, full_path}, ...]}``.  Los archivos en
    la raíz van bajo ``"General"``; cada subcarpeta se convierte en categoría.
    """
    root = Path(root_dir) if root_dir is not None else PROMPTS_DIR

    result: dict[str, list[dict]] = {}
    if not root.exists():
        return result

    exts = {".tpl", ".txt"}

    # Archivos en el nivel raíz (excluir subdirectories)
    root_entries = [
        {"name": p.stem, "rel_path": p.name, "full_path": p}
        for p in sorted(root.iterdir())
        if p.is_file() and p.suffix in exts
    ]
    if root_entries:
        result["General"] = root_entries

    # Subcarpetas → categoría
    for subdir in sorted(root.iterdir()):
        if not subdir.is_dir() or subdir.name.startswith("."):
            continue
        entries = [
            {
                "name": p.stem,
                "rel_path": p.relative_to(root).as_posix(),
                "full_path": p,
            }
            for p in sorted(subdir.rglob("*"))
            if p.is_file() and p.suffix in exts
        ]
        if entries:
            category = subdir.name.replace("_", " ").title()
            result[category] = entries

    return result

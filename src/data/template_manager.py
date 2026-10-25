from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict


class TemplateManager:
    """Gestor simple de plantillas de extracción de usuario.

    Busca la carpeta `user_templates/` en el directorio de salida (si se
    pasa) o en la carpeta `Documentos` del usuario. Si no existe, la crea.
    """

    def __init__(self, output_dir: str | Path | None = None) -> None:
        self._provided_output = Path(output_dir) if output_dir else None
        self.templates_dir = self._locate_or_create_templates_dir()

    def _locate_or_create_templates_dir(self) -> Path:
        dir_candidates: list[Path] = []

        if self._provided_output:
            dir_candidates.append(self._provided_output / "user_templates")
        else:
            dir_candidates.append(Path.cwd() / "user_templates")

        # Segunda opción: Documentos del usuario
        dir_candidates.append(Path.home() / "Documents" / "user_templates")

        # Si alguna ya existe, la usamos. Si no, intentamos crear la primera.
        for d in dir_candidates:
            if d.exists() and d.is_dir():
                return d

        # Intentar crear la primera candidata (preferida)
        preferred = dir_candidates[0]
        try:
            preferred.mkdir(parents=True, exist_ok=True)
            return preferred
        except Exception:
            # Fallback: crear en Documents
            fallback = dir_candidates[-1]
            fallback.mkdir(parents=True, exist_ok=True)
            return fallback

    def load_available_templates(self) -> Dict[str, Any]:
        """Lee todos los .json en la carpeta de plantillas y devuelve
        un diccionario {nombre: contenido}.
        El nombre usado es el stem (sin extensión) del fichero.
        """
        results: Dict[str, Any] = {}
        for p in sorted(self.templates_dir.glob("*.json")):
            try:
                with p.open("r", encoding="utf-8") as fh:
                    data = json.load(fh)
                results[p.stem] = data
            except Exception:
                # Ignorar ficheros corruptos
                continue
        return results

    def save_custom_template(self, name: str, schema_dict: Any) -> Path:
        """Guarda un dict JSON como plantilla con el nombre dado.

        Se normaliza el `name` a un filename seguro.
        Devuelve la ruta al fichero creado.
        """
        safe = re.sub(r"[^A-Za-z0-9_\- ]+", "", name).strip()
        safe = safe.replace(" ", "_") or "template"
        filename = f"{safe}.json"
        target = self.templates_dir / filename
        with target.open("w", encoding="utf-8") as fh:
            json.dump(schema_dict, fh, ensure_ascii=False, indent=2)
        return target

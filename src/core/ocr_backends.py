from __future__ import annotations

from typing import Callable, Dict, Tuple

# Backend registry: name -> factory function returning an object with
# a `process_base64(b64: str) -> tuple[str, int, int]` method.
_REGISTRY: Dict[str, Callable[[], object]] = {}


def register_backend(name: str, factory: Callable[[], object]) -> None:
    _REGISTRY[name] = factory


def available_backends() -> list[str]:
    return sorted(_REGISTRY.keys())


def get_backend(name: str):
    # Auto-cargar backends conocidos para que se auto-registren
    _auto_import_backends()
    factory = _REGISTRY.get(name)
    if not factory:
        raise KeyError(f"Backend not registered: {name}")
    return factory()


_backends_imported = False


def _auto_import_backends() -> None:
    """Importa módulos de backends conocidos para que ejecuten su register_backend."""
    global _backends_imported
    if _backends_imported:
        return
    _backends_imported = True
    _known = [
        "src.core.backends.mistral_backend",
    ]
    for mod_name in _known:
        try:
            __import__(mod_name)
        except Exception:
            pass

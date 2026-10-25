#!/usr/bin/env python3
"""Runner sencillo para pruebas del mapeo post‑OCR.

Uso:
  python scripts/test_postocr.py [ruta_a_json | --samples]

Si no se pasa ruta, procesa todos los JSON en `tests/postocr_samples/`.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


def _process_file(p: Path, use_ia: bool = False, model: str | None = None) -> None:
    print(f"\n--- Procesando: {p} ---")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"Error leyendo JSON: {exc}")
        return
    try:
        from src.core.postocr import deterministic_map, ia_fallback, _join_text_from_ocr
    except Exception:
        from core.postocr import deterministic_map, ia_fallback, _join_text_from_ocr

    joined = _join_text_from_ocr(data)
    print("Texto concatenado:\n", joined)
    mapped = deterministic_map(data)
    print("Resultado determinista:")
    print(json.dumps(mapped, ensure_ascii=False, indent=2))
    if use_ia:
        print("Ejecutando fallback IA (stub) con modelo:", model)
        ia_res = ia_fallback(data, model=model or "gpt-4o-mini")
        print("Resultado IA (stub):")
        print(json.dumps(ia_res or {}, ensure_ascii=False, indent=2))


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    ap = argparse.ArgumentParser(description="Test runner para postocr")
    ap.add_argument("path", nargs="?", help="Archivo JSON a procesar")
    ap.add_argument("--samples", action="store_true", help="Procesar samples incluidos")
    ap.add_argument("--ia", action="store_true", help="Ejecutar fallback IA (stub)")
    ap.add_argument("--model", default=None, help="Modelo IA a usar con --ia")
    args = ap.parse_args(argv)

    base = Path(__file__).resolve().parent.parent
    # Asegurar que el paquete `src` esté en sys.path para imports relativos
    src_path = str(base / "src")
    if src_path not in sys.path:
        sys.path.insert(0, src_path)
    samples_dir = base / "tests" / "postocr_samples"

    files = []
    if args.path:
        p = Path(args.path)
        if not p.exists():
            print(f"Archivo no encontrado: {p}")
            return 2
        files = [p]
    elif args.samples or not sys.argv[1:]:
        if samples_dir.exists():
            files = sorted(list(samples_dir.glob("*.json")))
        else:
            print(f"No hay samples en {samples_dir}")
            return 1

    for f in files:
        _process_file(f, use_ia=args.ia, model=args.model)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

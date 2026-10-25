"""Test rápido: persiste telemetría por backend usando ConfigPanel.

Este script simula dos lotes de OCR con backends diferentes y comprueba
que el archivo de telemetría contiene entradas por día con claves de
backend separadas.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

from PyQt6.QtWidgets import QApplication

from src.ui.config_panel import ConfigPanel


def main() -> int:
    app = QApplication([])
    cfg = ConfigPanel()

    # Asegurar archivo limpio
    tele_file = cfg._TELE_FILE
    if tele_file.exists():
        tele_file.unlink()

    # Primer lote: Mistral
    cfg.update_telemetry(1200, 800, backend="mistral-ocr-latest")
    cfg.save_batch_to_monthly()

    # Segundo lote: Google Vision
    cfg.update_telemetry(500, 300, backend="google-vision")
    cfg.save_batch_to_monthly()

    # Leer y verificar estructura
    raw = json.loads(tele_file.read_text(encoding="utf-8"))
    today = datetime.now().strftime("%Y-%m-%d")
    entry = raw.get(today)
    assert entry is not None, "No se creó entrada para hoy"
    assert "mistral-ocr-latest" in entry, "Falta clave de backend 'mistral-ocr-latest'"
    assert "google-vision" in entry, "Falta clave de backend 'google-vision'"
    m = entry["mistral-ocr-latest"]
    g = entry["google-vision"]
    assert m["prompt"] == 1200 and m["completion"] == 800, f"Valores mistral inesperados: {m}"
    assert g["prompt"] == 500 and g["completion"] == 300, f"Valores google inesperados: {g}"

    print("PASS: telemetría por backend guardada correctamente")
    return 0


if __name__ == "__main__":
    sys.exit(main())

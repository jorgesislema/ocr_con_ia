"""Enrutador de contenido IA para selección de pipeline OCR óptimo.

``route_content(image, doc_hint)`` analiza una imagen PIL (o ruta de
archivo) mediante heurísticas rápidas de visión computacional y devuelve
un dict de configuración que ``OcrTask._build_engine()`` puede consumir
directamente, permitiendo que cada documento se procese con el pipeline
más adecuado a su naturaleza.

Tipos detectados
----------------
* ``music_omr``         — partitura con pentagramas
* ``latex_math``        — página con fórmulas matemáticas densas
* ``legal_dense``       — texto muy denso en columnas (contratos, escrituras)
* ``scanned_noisy``     — escaneado con ruido / baja calidad
* ``table_heavy``       — tablas de datos / facturas / planillas
* ``handwritten``       — escritura manuscrita predominante
* ``standard``          — texto impreso genérico (fallback)

Uso
---
    from src.core.content_router import route_content
    routing = route_content(pil_img, doc_hint="factura")
    # routing → {
    #   "content_type": "table_heavy",
    #   "backend":      "glm",
    #   "prompt_key":   "invoice",
    #   "preprocess":   True,
    #   "upscale":      1,
    #   "light_mode":   False,
    #   "model_hint":   "glm-4v-plus",
    #   "confidence":   0.87,     # confianza de la detección
    # }

El módulo funciona aunque ``cv2`` / ``numpy`` no estén instalados:
en ese caso aplica sólo heurísticas basadas en PIL (degradado suave).
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

_log = logging.getLogger("ocr.router")

# ── Mapas de configuración por tipo de contenido ─────────────────────────────

_PIPELINE_MAP: dict[str, dict] = {
    "music_omr": {
        "backend":    "glm",
        "prompt_key": "music_omr",
        "preprocess": True,
        "upscale":    2,
        "light_mode": False,
        "model_hint": "glm-4v-plus",
    },
    "latex_math": {
        "backend":    "glm",
        "prompt_key": "latex_math",
        "preprocess": True,
        "upscale":    2,
        "light_mode": False,
        "model_hint": "glm-4v-plus",
    },
    "legal_dense": {
        "backend":    "glm",
        "prompt_key": "legal",
        "preprocess": True,
        "upscale":    1,
        "light_mode": True,
        "model_hint": "glm-4v-flash",
    },
    "scanned_noisy": {
        "backend":    "glm",
        "prompt_key": "invoice",
        "preprocess": True,
        "upscale":    2,
        "light_mode": False,
        "model_hint": "glm-4v-plus",
    },
    "table_heavy": {
        "backend":    "glm",
        "prompt_key": "invoice",
        "preprocess": True,
        "upscale":    1,
        "light_mode": False,
        "model_hint": "glm-4v-flash",
    },
    "handwritten": {
        "backend":    "glm",
        "prompt_key": "generic",
        "preprocess": True,
        "upscale":    2,
        "light_mode": False,
        "model_hint": "glm-4v-plus",
    },
    "standard": {
        "backend":    "glm",
        "prompt_key": "invoice",
        "preprocess": False,
        "upscale":    1,
        "light_mode": True,
        "model_hint": "glm-4v-flash",
    },
}

# Palabras clave en ``doc_hint`` que fuerzan un tipo sin análisis de imagen
_HINT_OVERRIDES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"music|musica|partitura|pentagrama", re.I), "music_omr"),
    (re.compile(r"math|formula|latex|ecuacion", re.I), "latex_math"),
    (re.compile(r"manuscrit|handwritten|mano", re.I), "handwritten"),
    (re.compile(r"legal|contrato|notarial|escritura\s*notarial", re.I), "legal_dense"),
    (re.compile(r"scan|escaneado|noisy|ruid", re.I), "scanned_noisy"),
    (re.compile(r"factura|invoice|tabla|table|planilla", re.I), "table_heavy"),
]


# ── API pública ───────────────────────────────────────────────────────────────

def route_content(
    image: Any | None = None,
    doc_hint: str = "",
    *,
    path: str | Path | None = None,
    override_backend: str | None = None,
    override_upscale: int | None = None,
) -> dict:
    """Detecta el tipo de contenido y devuelve la configuración de pipeline.

    Parámetros
    ----------
    image : PIL.Image | None
        Imagen ya cargada. Si se pasa junto con ``path`` se usa ``image``.
    doc_hint : str
        Pista semántica libre (nombre de archivo, perfil de extracción, etc.).
    path : str | Path | None
        Ruta del documento de origen (usado para cargar la imagen si
        ``image`` es None o para deducir tipo por extensión).
    override_backend : str | None
        Si se pasa, sobreescribe el backend del pipeline seleccionado.
    override_upscale : int | None
        Si se pasa, sobreescribe el upscale del pipeline seleccionado.

    Devuelve
    --------
    dict con claves: content_type, backend, prompt_key, preprocess,
    upscale, light_mode, model_hint, confidence.
    """
    # 1. Comprobación por texto del hint (rápida, sin análisis de imagen)
    forced = _check_hint_override(doc_hint, path)
    if forced:
        return _build_result(forced, 1.0, override_backend, override_upscale)

    # 2. Intentar análisis de imagen
    try:
        pil_img = _ensure_pil(image, path)
    except Exception as exc:
        _log.debug("route_content: no se pudo cargar imagen: %s", exc)
        pil_img = None

    if pil_img is None:
        return _build_result("standard", 0.5, override_backend, override_upscale)

    content_type, confidence = _analyze_image(pil_img)
    result = _build_result(content_type, confidence, override_backend, override_upscale)
    _log.debug(
        "route_content: %s → %s (conf=%.2f) backend=%s",
        doc_hint or "?", content_type, confidence, result["backend"],
    )
    return result


# ── Análisis por hint de texto ────────────────────────────────────────────────

def _check_hint_override(hint: str, path: Any) -> str | None:
    """Retorna el tipo si el hint (o nombre de archivo) coincide con un patrón."""
    combined = hint or ""
    if path:
        combined = combined + " " + str(path)
    for pattern, content_type in _HINT_OVERRIDES:
        if pattern.search(combined):
            return content_type
    return None


# ── Análisis de imagen ────────────────────────────────────────────────────────

def _analyze_image(pil_img) -> tuple[str, float]:
    """Devuelve (content_type, confidence) usando heurísticas de imagen."""
    try:
        return _analyze_cv2(pil_img)
    except Exception:
        pass
    try:
        return _analyze_pil_only(pil_img)
    except Exception:
        pass
    return "standard", 0.5


def _analyze_cv2(pil_img) -> tuple[str, float]:
    """Heurísticas completas usando cv2 + numpy."""
    import cv2
    import numpy as np

    # Convertir a numpy BGR
    img_rgb = pil_img.convert("RGB")
    arr = np.array(img_rgb)
    bgr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape

    # ── 1. Detección de pentagramas (música) ──────────────────────────────
    # Proyección horizontal: 5 líneas delgadas paralelas con separación uniforme
    horiz_proj = np.sum(gray < 128, axis=1).astype(float)
    # Suavizado y detección de picos
    kernel = np.ones(3) / 3
    smooth_proj = np.convolve(horiz_proj, kernel, mode="same")
    thresh_line = np.max(smooth_proj) * 0.6
    peaks = np.where(smooth_proj > thresh_line)[0]
    if len(peaks) >= 5:
        # Verificar separación uniforme entre los primeros picos (pentagrama)
        gaps = np.diff(peaks[:20])
        if len(gaps) >= 4:
            std_gaps = float(np.std(gaps[:5]))
            mean_gap = float(np.mean(gaps[:5]))
            if mean_gap > 3 and std_gaps / (mean_gap + 1e-6) < 0.25:
                # 5 líneas con separación muy uniforme → pentagrama
                conf = min(0.95, 0.7 + (1.0 - std_gaps / (mean_gap + 1e-6)) * 0.25)
                return "music_omr", float(conf)

    # ── 2. Fórmulas matemáticas ───────────────────────────────────────────
    # Caracteres pequeños dispersos, muchos píxeles aislados, relación de aspecto
    # de símbolos: usar Laplacian high-frequency + densidad de contornos pequeños
    lap = cv2.Laplacian(gray, cv2.CV_64F)
    lap_std = float(np.std(lap))
    # Umbralizar para detectar caracteres
    _, bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    cnts, _ = cv2.findContours(bw, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    tiny = [c for c in cnts if cv2.contourArea(c) < 50]
    tiny_ratio = len(tiny) / max(len(cnts), 1)
    if lap_std > 20 and tiny_ratio > 0.45 and len(cnts) > 80:
        conf = min(0.92, 0.55 + tiny_ratio * 0.5 + lap_std / 200)
        return "latex_math", float(conf)

    # ── 3. Escaneado ruidoso ──────────────────────────────────────────────
    brightness = float(np.mean(gray))
    noise_est  = float(np.std(gray - cv2.GaussianBlur(gray, (5, 5), 0)))
    if noise_est > 22 or brightness < 80:
        conf = min(0.90, 0.55 + noise_est / 100 + (80 - min(brightness, 80)) / 200)
        return "scanned_noisy", float(conf)

    # ── 4. Tablas (muchas líneas horizontales y verticales) ───────────────
    edges = cv2.Canny(gray, 50, 150, apertureSize=3)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=60,
                             minLineLength=int(w * 0.25), maxLineGap=20)
    h_lines = 0; v_lines = 0
    if lines is not None:
        for ln in lines:
            x1, y1, x2, y2 = ln[0]
            angle = abs(np.degrees(np.arctan2(y2 - y1, x2 - x1 + 1e-6)))
            if angle < 10 or angle > 170:
                h_lines += 1
            elif 80 < angle < 100:
                v_lines += 1
    if h_lines >= 4 and v_lines >= 2:
        conf = min(0.93, 0.60 + min(h_lines, 20) / 40 + min(v_lines, 10) / 20)
        return "table_heavy", float(conf)

    # ── 5. Escritura manuscrita (contornos irregulares, alta entropía direccional) ─
    if lines is not None and len(lines) > 0:
        angles = []
        for ln in lines[:50]:
            x1, y1, x2, y2 = ln[0]
            ang = float(np.degrees(np.arctan2(y2 - y1, x2 - x1 + 1e-6))) % 180
            angles.append(ang)
        angle_std = float(np.std(angles)) if angles else 0
        if angle_std > 35:
            return "handwritten", 0.72

    # ── 6. Texto denso en columnas (legal) ───────────────────────────────
    text_density = float(np.sum(bw > 0)) / (h * w)
    if text_density > 0.12 and h_lines < 3:
        return "legal_dense", 0.68

    return "standard", 0.60


def _analyze_pil_only(pil_img) -> tuple[str, float]:
    """Heurísticas básicas usando solo PIL (sin cv2)."""
    gray = pil_img.convert("L")
    pixels = list(gray.getdata())
    total = len(pixels)
    if total == 0:
        return "standard", 0.5

    dark = sum(1 for p in pixels if p < 128)
    brightness = sum(pixels) / total
    dark_ratio  = dark / total

    # Escaneado: muchos píxeles muy grises
    if brightness < 85 or dark_ratio > 0.55:
        return "scanned_noisy", 0.65

    # Muy poco texto (claro): probablemente documento limpio
    if dark_ratio < 0.04:
        return "standard", 0.70

    return "standard", 0.55


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ensure_pil(image: Any | None, path: Any | None):
    """Devuelve un PIL.Image cargado o None si no se puede."""
    if image is not None:
        return image
    if path is not None:
        from PIL import Image
        return Image.open(str(path))
    return None


def _build_result(
    content_type: str,
    confidence: float,
    override_backend: str | None,
    override_upscale: int | None,
) -> dict:
    cfg = dict(_PIPELINE_MAP.get(content_type, _PIPELINE_MAP["standard"]))
    if override_backend:
        cfg["backend"] = override_backend
    if override_upscale is not None:
        cfg["upscale"] = int(override_upscale)
    return {
        "content_type": content_type,
        "confidence":   round(confidence, 3),
        **cfg,
    }

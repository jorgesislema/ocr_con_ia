"""Pipeline de preprocesamiento adaptativo para OCR Enterprise.

El pipeline analiza cada imagen antes de enviarla al backend y aplica
únicamente los filtros que mejoran la calidad: deskew si la inclinación
supera 2°, denoise si el nivel de ruido es alto y upscale inteligente
solo cuando la resolución estimada está por debajo de 300 DPI.

Interfaz pública principal
--------------------------
adaptive_preprocess(pil_image, config) -> PIL.Image.Image

Función heredada (backward compat)
-----------------------------------
enhance_image(image_bytes) -> bytes
"""
from __future__ import annotations

import io
import math
import statistics
from typing import Any

from PIL import Image


# ─────────────────────────────────────────────────────────────────────────────
# Umbrales y constantes
# ─────────────────────────────────────────────────────────────────────────────

_SKEW_THRESHOLD_DEG: float   = 2.0   # rotar solo si inclinación > N grados
_NOISE_THRESHOLD: float      = 30.0  # Laplacian var < N → imagen ruidosa
_DARK_BRIGHTNESS: float      = 80.0  # brillo promedio < N → imagen oscura
_LOW_CONTRAST: float         = 30.0  # std de grises < N → contraste bajo
_LOW_DPI_THRESHOLD: int      = 300   # upscale si DPI estimado < N
_TARGET_SHORT_SIDE: int      = 1200  # píxeles mínimos del lado corto tras upscale
_DENOISE_H: int              = 10    # fastNlMeans h
_CLAHE_CLIP: float           = 3.0


# ─────────────────────────────────────────────────────────────────────────────
# A. Estimación de calidad
# ─────────────────────────────────────────────────────────────────────────────

def _estimate_quality(pil_image: Image.Image) -> dict[str, Any]:
    """Analiza la imagen y devuelve métricas de calidad.

    Devuelve
    --------
    dict con claves:
        - ``width``, ``height``       : dimensiones en píxeles
        - ``estimated_dpi``           : DPI estimado por lado corto (asume 300 DPI ~ A4 2480px)
        - ``brightness``              : promedio de grises 0-255
        - ``contrast``                : desviación estándar de grises
        - ``estimated_noise``         : varianza del Laplaciano (mayor = menos ruido)
        - ``skew_angle``              : ángulo estimado de inclinación en grados
        - ``needs_upscale``           : bool
        - ``needs_deskew``            : bool
        - ``needs_denoise``           : bool
        - ``needs_brightness``        : bool
    """
    try:
        import cv2
        import numpy as np
    except ImportError:
        # Sin OpenCV devolvemos calidad neutra
        return {
            "width": pil_image.width, "height": pil_image.height,
            "estimated_dpi": 300, "brightness": 128.0, "contrast": 60.0,
            "estimated_noise": 100.0, "skew_angle": 0.0,
            "needs_upscale": False, "needs_deskew": False,
            "needs_denoise": False, "needs_brightness": False,
        }

    arr = np.array(pil_image.convert("L"))  # escala de grises
    h, w = arr.shape

    # ── Brillo y contraste ────────────────────────────────────────────────
    brightness = float(arr.mean())
    contrast   = float(arr.std())

    # ── Ruido (varianza del Laplaciano: baja → ruidoso / borroso) ─────────
    try:
        lap        = cv2.Laplacian(arr, cv2.CV_64F)
        noise_var  = float(lap.var())
    except Exception:
        noise_var  = 100.0

    # ── DPI estimado ──────────────────────────────────────────────────────
    # Asumimos que un A4 a 300 DPI tiene 2480 px de ancho;
    # el lado más corto a 300 DPI equivale a ~2480 px.
    short_side   = min(w, h)
    # Heurística: si el lado corto < 1240 px asumimos <150 DPI
    estimated_dpi = int(short_side * 300 / 2480) if short_side > 0 else 300
    estimated_dpi = max(1, min(estimated_dpi, 1200))

    # ── Ángulo de inclinación (Hough probabilístico sobre bordes) ─────────
    skew_angle = 0.0
    try:
        edges = cv2.Canny(arr, 50, 150, apertureSize=3)
        lines = cv2.HoughLinesP(
            edges, 1, math.pi / 180, threshold=80,
            minLineLength=max(50, w // 8), maxLineGap=20
        )
        if lines is not None and len(lines) > 0:
            angles = []
            for ln in lines:
                x1, y1, x2, y2 = ln[0]
                dx, dy = x2 - x1, y2 - y1
                if dx != 0:
                    angle = math.degrees(math.atan2(dy, dx))
                    # Filtrar ángulos muy alejados de la horizontal
                    if abs(angle) < 45:
                        angles.append(angle)
            if angles:
                skew_angle = statistics.median(angles)
    except Exception:
        skew_angle = 0.0

    return {
        "width":           w,
        "height":          h,
        "estimated_dpi":   estimated_dpi,
        "brightness":      brightness,
        "contrast":        contrast,
        "estimated_noise": noise_var,
        "skew_angle":      skew_angle,
        "needs_upscale":   estimated_dpi < _LOW_DPI_THRESHOLD,
        "needs_deskew":    abs(skew_angle) > _SKEW_THRESHOLD_DEG,
        "needs_denoise":   noise_var < _NOISE_THRESHOLD,
        "needs_brightness": brightness < _DARK_BRIGHTNESS or contrast < _LOW_CONTRAST,
    }


# ─────────────────────────────────────────────────────────────────────────────
# B. Filtros adaptativos
# ─────────────────────────────────────────────────────────────────────────────

def _safe_deskew(bgr: "np.ndarray", angle: float) -> "np.ndarray":  # type: ignore[name-defined]
    """Rota la imagen BGR el ángulo necesario para enderezarla.

    Solo se llama cuando abs(angle) > _SKEW_THRESHOLD_DEG.
    """
    import cv2
    import numpy as np

    h, w = bgr.shape[:2]
    center = (w // 2, h // 2)
    M = cv2.getRotationMatrix2D(center, -angle, 1.0)
    # Ampliar el lienzo para no perder esquinas
    cos_a = abs(M[0, 0])
    sin_a = abs(M[0, 1])
    new_w = int(h * sin_a + w * cos_a)
    new_h = int(h * cos_a + w * sin_a)
    M[0, 2] += (new_w - w) / 2
    M[1, 2] += (new_h - h) / 2
    rotated = cv2.warpAffine(
        bgr, M, (new_w, new_h),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REPLICATE,
    )
    return rotated


def _safe_upscale(pil_image: Image.Image) -> Image.Image:
    """LANCZOS ×2 solo si la resolución estimada está por debajo del umbral.

    Nunca aplica más de ×2 en una sola llamada para evitar artefactos.
    """
    w, h = pil_image.size
    short_side = min(w, h)
    if short_side >= _TARGET_SHORT_SIDE:
        return pil_image  # ya suficientemente grande
    # Factor mínimo necesario para alcanzar _TARGET_SHORT_SIDE, máximo ×2
    factor = min(2.0, _TARGET_SHORT_SIDE / max(short_side, 1))
    if factor <= 1.05:
        return pil_image
    new_size = (int(w * factor), int(h * factor))
    return pil_image.resize(new_size, Image.LANCZOS)


def _adaptive_filters(
    pil_image: Image.Image,
    quality: dict[str, Any],
    config: dict[str, Any],
) -> Image.Image:
    """Aplica a *pil_image* solo los filtros que la métrica de calidad requiere.

    Orden del pipeline:
    1. Deskew (antes de cualquier otro para que los filtros operen sobre imagen recta).
    2. Denoise.
    3. Mejora de brillo / contraste (CLAHE + gamma).
    4. Upscale (al final para no amplificar ruido antes de denoising).

    Parámetros de ``config``
    ------------------------
    - ``upscale``          : int (1..8) — factor de upscale forzado por el usuario.
    - ``light_mode``       : bool — si True, salta el denoise (más rápido).
    - ``force_deskew``     : bool — forzar deskew aunque esté por debajo del umbral.
    """
    try:
        import cv2
        import numpy as np
    except ImportError:
        return pil_image

    try:
        img_rgb = np.array(pil_image.convert("RGB"))
        bgr = img_rgb[:, :, ::-1].copy()

        applied: list[str] = []

        # 1. Deskew
        skew = quality.get("skew_angle", 0.0)
        if abs(skew) > _SKEW_THRESHOLD_DEG or config.get("force_deskew", False):
            try:
                bgr = _safe_deskew(bgr, skew)
                applied.append(f"deskew({skew:.1f}°)")
            except Exception:
                pass

        # 2. Denoise — solo si ruido alto Y no en modo rápido
        light_mode = config.get("light_mode", False)
        if quality.get("needs_denoise", False) and not light_mode:
            try:
                bgr = cv2.fastNlMeansDenoisingColored(bgr, None, _DENOISE_H, _DENOISE_H, 7, 21)
                applied.append("denoise")
            except Exception:
                pass

        # 3. Brillo / contraste
        if quality.get("needs_brightness", False):
            try:
                gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
                clahe = cv2.createCLAHE(clipLimit=_CLAHE_CLIP, tileGridSize=(8, 8))
                gray = clahe.apply(gray)
                # Gamma correction si imagen muy oscura
                if quality.get("brightness", 128) < _DARK_BRIGHTNESS:
                    lut = np.array(
                        [min(255, int(pow(i / 255.0, 0.6) * 255)) for i in range(256)],
                        dtype=np.uint8,
                    )
                    gray = cv2.LUT(gray, lut)
                bgr = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
                applied.append("clahe+gamma")
            except Exception:
                pass

        # 4. Sharpen ligero (siempre, mejora bordes de letras)
        try:
            kernel = np.array([[0, -0.5, 0], [-0.5, 3.0, -0.5], [0, -0.5, 0]])
            bgr = cv2.filter2D(bgr, -1, kernel)
        except Exception:
            pass

        # 5. Upscale (inteligente o forzado por usuario)
        user_upscale = int(config.get("upscale", 1) or 1)
        if user_upscale > 1:
            # Upscale forzado por el usuario (checkbox upscale_cb)
            new_w = int(bgr.shape[1] * user_upscale)
            new_h = int(bgr.shape[0] * user_upscale)
            bgr = cv2.resize(bgr, (new_w, new_h), interpolation=cv2.INTER_CUBIC)
            applied.append(f"upscale×{user_upscale}(forzado)")
        elif quality.get("needs_upscale", False):
            # Upscale inteligente: solo ×2 si el lado corto sigue siendo < 1200 px
            rgb_pil = Image.fromarray(bgr[:, :, ::-1])
            prev_size = rgb_pil.size
            rgb_pil = _safe_upscale(rgb_pil)
            bgr = np.array(rgb_pil)[:, :, ::-1].copy()
            if rgb_pil.size != prev_size:
                applied.append("upscale×2(adaptativo)")

        # Convertir de vuelta a PIL
        result = Image.fromarray(bgr[:, :, ::-1])

        # Adjuntar log de filtros aplicados como atributo extra (inofensivo si se ignora)
        try:
            result._preprocess_applied = applied or ["sin cambios"]  # type: ignore[attr-defined]
        except Exception:
            pass

        return result

    except Exception:
        return pil_image


# ─────────────────────────────────────────────────────────────────────────────
# B (principal). adaptive_preprocess
# ─────────────────────────────────────────────────────────────────────────────

def adaptive_preprocess(
    pil_image: Image.Image,
    config: dict[str, Any] | None = None,
) -> Image.Image:
    """Pipeline adaptativo principal.

    Estima la calidad de la imagen y aplica únicamente los filtros necesarios:
    - Deskew cuando inclinación > 2°
    - Denoise cuando ruido estimado es alto (Laplacian var < 30)
    - CLAHE + gamma cuando la imagen está oscura o tiene poco contraste
    - Upscale inteligente LANCZOS × 2 solo si DPI estimado < 300

    El parámetro ``config`` acepta las mismas claves que ``_adaptive_filters``.
    Si es ``None`` se usan los valores por defecto (comportamiento recomendado).

    Devuelve siempre una imagen PIL aunque OpenCV no esté disponible.
    """
    if config is None:
        config = {}

    try:
        quality = _estimate_quality(pil_image)
        result  = _adaptive_filters(pil_image, quality, config)
        return result
    except Exception:
        return pil_image


# ─────────────────────────────────────────────────────────────────────────────
# Backward compat: función original
# ─────────────────────────────────────────────────────────────────────────────

def enhance_image(image_bytes: bytes) -> bytes:
    """[Backward compat] Recibe bytes de imagen, aplica pipeline adaptativo, devuelve JPEG bytes."""
    try:
        pil_img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        result  = adaptive_preprocess(pil_img)
        buf = io.BytesIO()
        result.save(buf, format="JPEG", quality=92)
        return buf.getvalue()
    except Exception:
        return image_bytes

"""
Módulo de notificaciones toast para PyQt6.

Uso::

    from src.ui.toast_notification import show_toast

    show_toast(parent_widget, "Lote completado con éxito", "success")
    show_toast(parent_widget, "Error al procesar factura.pdf", "error")
    show_toast(parent_widget, "Confianza baja — revisa el documento", "warning")

Tipos disponibles: ``"success"``, ``"error"``, ``"warning"``, ``"info"``

Las notificaciones:
  - Aparecen en la esquina inferior derecha del padre (o pantalla).
  - Se apilan automáticamente si hay varias activas.
  - Se auto-eliminan tras *duration* ms (por defecto 3 000 ms).
  - Admiten clic para cerrar anticipadamente.
  - Hacen fade-in / fade-out suave.
  - Son compatibles con Windows, Linux y macOS.
"""
from __future__ import annotations

import weakref
from typing import Literal

from PyQt6.QtCore import (
    QEasingCurve,
    QPoint,
    QPropertyAnimation,
    QRect,
    QTimer,
    Qt,
)
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QWidget,
)

# ── Tipos ──────────────────────────────────────────────────────────────────────
ToastType = Literal["success", "error", "warning", "info"]

# ── Constantes ─────────────────────────────────────────────────────────────────
_DURATION_MS: int = 3_000   # ms antes del fade-out automático
_FADE_MS: int = 280          # duración del fade in / out
_MARGIN: int = 16            # píxeles desde los bordes de la ventana
_SPACING: int = 10           # espacio entre toasts apilados
_MAX_WIDTH: int = 360        # ancho máximo del mensaje

# ── Paleta de estilos ──────────────────────────────────────────────────────────
_STYLE: dict[ToastType, dict[str, str]] = {
    "success": {
        "bg":     "#10B981",
        "border": "#059669",
        "shadow": "rgba(16,185,129,0.35)",
        "icon":   "✓",
        "fg":     "#FFFFFF",
    },
    "error": {
        "bg":     "#EF4444",
        "border": "#DC2626",
        "shadow": "rgba(239,68,68,0.35)",
        "icon":   "✕",
        "fg":     "#FFFFFF",
    },
    "warning": {
        "bg":     "#F59E0B",
        "border": "#D97706",
        "shadow": "rgba(245,158,11,0.35)",
        "icon":   "⚠",
        "fg":     "#1E293B",
    },
    "info": {
        "bg":     "#3B82F6",
        "border": "#2563EB",
        "shadow": "rgba(59,130,246,0.35)",
        "icon":   "ℹ",
        "fg":     "#FFFFFF",
    },
}

# ── Registro global de toasts activos (referencias débiles) ───────────────────
_active: list[weakref.ref[Toast]] = []


def _purge() -> None:
    """Elimina referencias muertas del registro global."""
    global _active
    _active = [r for r in _active if r() is not None]


def _stack_offset(parent: QWidget | None) -> int:
    """Calcula el desplazamiento Y acumulado de los toasts activos del mismo padre."""
    _purge()
    offset = 0
    for ref in _active:
        t = ref()
        if t is not None and t.isVisible() and t.parent() is parent:
            offset += t.height() + _SPACING
    return offset


# ── Clase principal ────────────────────────────────────────────────────────────

class Toast(QFrame):
    """Notificación toast flotante en la esquina inferior derecha.

    Crea instancias a través de :func:`show_toast` para gestionar
    el apilamiento automático.
    """

    def __init__(
        self,
        message: str,
        type: ToastType = "success",  # noqa: A002  (shadowing built-in intencional)
        parent: QWidget | None = None,
        duration: int = _DURATION_MS,
    ) -> None:
        flags = (
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
        )
        super().__init__(parent, flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        s = _STYLE.get(type, _STYLE["info"])

        # ── Contenido ─────────────────────────────────────────────────────────
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 10, 16, 10)
        lay.setSpacing(10)

        icon_lbl = QLabel(s["icon"])
        icon_lbl.setFont(QFont("Segoe UI Emoji", 13, QFont.Weight.Bold))
        icon_lbl.setStyleSheet(f"color: {s['fg']}; background: transparent;")
        icon_lbl.setFixedSize(22, 22)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(icon_lbl)

        msg_lbl = QLabel(message)
        msg_lbl.setFont(QFont("Inter", 10))
        msg_lbl.setWordWrap(True)
        msg_lbl.setMaximumWidth(_MAX_WIDTH)
        msg_lbl.setStyleSheet(f"color: {s['fg']}; background: transparent;")
        lay.addWidget(msg_lbl, stretch=1)

        # ── Estilo del frame ──────────────────────────────────────────────────
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {s['bg']};
                border: 1px solid {s['border']};
                border-radius: 10px;
            }}
        """)
        self.setMinimumWidth(240)

        # ── Efecto de opacidad para animaciones ───────────────────────────────
        self._effect = QGraphicsOpacityEffect(self)
        self._effect.setOpacity(0.0)
        self.setGraphicsEffect(self._effect)

        # ── Registro y posicionamiento ────────────────────────────────────────
        self.adjustSize()
        y_off = _stack_offset(parent)
        _active.append(weakref.ref(self))
        self._place(y_off)

        # ── Mostrar ───────────────────────────────────────────────────────────
        self.show()
        self.raise_()
        self._fade_in()

        # ── Auto-cierre ───────────────────────────────────────────────────────
        self._close_timer = QTimer(self)
        self._close_timer.setSingleShot(True)
        self._close_timer.timeout.connect(self._fade_out)
        self._close_timer.start(duration)

        # Clic izquierdo = cerrar anticipadamente
        self.mousePressEvent = lambda _e: self._fade_out()

    # ── Posicionamiento ───────────────────────────────────────────────────────

    def _place(self, y_offset: int = 0) -> None:
        """Coloca el toast en la esquina inferior derecha del padre / pantalla."""
        self.adjustSize()
        w, h = self.width(), self.height()

        x, y = self._anchor(w, h)
        y -= y_offset
        self.move(x, y)

    def _anchor(self, w: int, h: int) -> tuple[int, int]:
        """Devuelve la coordenada (x, y) base sin apilar."""
        par = self.parent()
        if isinstance(par, QWidget):
            if par.isWindow():
                geo: QRect = par.geometry()
                return (
                    geo.x() + geo.width() - w - _MARGIN,
                    geo.y() + geo.height() - h - _MARGIN,
                )
            # Widget embebido → coordenadas globales
            tl: QPoint = par.mapToGlobal(QPoint(0, 0))
            return (
                tl.x() + par.width() - w - _MARGIN,
                tl.y() + par.height() - h - _MARGIN,
            )
        # Sin padre → esquina de la pantalla disponible
        screen = QApplication.primaryScreen()
        if screen:
            ag = screen.availableGeometry()
            return (
                ag.x() + ag.width() - w - _MARGIN,
                ag.y() + ag.height() - h - _MARGIN,
            )
        return (60, 60)

    # ── Animaciones ───────────────────────────────────────────────────────────

    def _fade_in(self) -> None:
        self._anim = QPropertyAnimation(self._effect, b"opacity", self)
        self._anim.setDuration(_FADE_MS)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.start()

    def _fade_out(self) -> None:
        # Evitar doble invocación
        try:
            self._close_timer.stop()
        except RuntimeError:
            pass
        self._anim = QPropertyAnimation(self._effect, b"opacity", self)
        self._anim.setDuration(_FADE_MS)
        self._anim.setStartValue(self._effect.opacity())
        self._anim.setEndValue(0.0)
        self._anim.setEasingCurve(QEasingCurve.Type.InCubic)
        self._anim.finished.connect(self.close)
        self._anim.start()


# ── API pública ────────────────────────────────────────────────────────────────

def show_toast(
    parent: QWidget | None,
    message: str,
    type: ToastType = "success",    # noqa: A002
    duration: int = _DURATION_MS,
) -> Toast:
    """Muestra una notificación toast en la esquina inferior derecha.

    Args:
        parent:   Ventana o widget padre. ``None`` usa la pantalla primaria.
        message:  Texto a mostrar (admite saltos de línea automáticos).
        type:     ``"success"`` | ``"error"`` | ``"warning"`` | ``"info"``
        duration: Ms antes del fade-out automático (por defecto 3 000 ms).

    Returns:
        La instancia :class:`Toast` creada.  Normalmente puede ignorarse.

    Example::

        show_toast(main_win, "✓ 12 documentos procesados", "success")
        show_toast(main_win, "No se pudo contactar el backend", "error")
        show_toast(main_win, "Confianza < 70 % en 3 campos", "warning")
    """
    return Toast(message=message, type=type, parent=parent, duration=duration)

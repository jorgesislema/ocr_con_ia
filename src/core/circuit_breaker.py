"""Circuit Breaker — FASE 6.

Protege al motor OCR (u otros servicios externos) de llamadas en cascada
cuando el servicio falla repetidamente.

Estados
-------
CLOSED   → funcionando normalmente; cada fallo incrementa el contador.
OPEN     → servicio cortado; todas las llamadas fallan inmediatamente
            hasta que expire el timeout de recuperación.
HALF_OPEN → se permite UNA llamada de prueba; si tiene éxito → CLOSED,
            si falla → OPEN de nuevo.

Uso típico
----------
    from src.core.circuit_breaker import CircuitBreaker, CircuitOpenError

    breaker = CircuitBreaker(max_failures=5, recovery_timeout=300)

    try:
        with breaker:
            result = call_external_api(...)
    except CircuitOpenError as e:
        show_error(str(e))   # "Servicio cortado por 4m 32s..."
"""
from __future__ import annotations

import logging
import threading
import time
from enum import Enum, auto
from typing import Callable

_log = logging.getLogger("ocr.circuit_breaker")


class CircuitState(Enum):
    CLOSED    = auto()
    OPEN      = auto()
    HALF_OPEN = auto()


class CircuitOpenError(RuntimeError):
    """Excepción lanzada cuando el circuito está abierto."""


class CircuitBreaker:
    """Implementación thread-safe del patrón Circuit Breaker.

    Parámetros
    ----------
    max_failures :
        Número de fallos consecutivos que activan el circuito.  Por defecto 5.
    recovery_timeout :
        Segundos que el circuito permanece OPEN antes de pasar a HALF_OPEN.
        Por defecto 300 s (5 minutos).
    name :
        Nombre identificativo para logs y mensajes de error.
    on_open :
        Callback opcional ``(failures: int) -> None`` invocado cuando el circuito
        se abre.  Ideal para mostrar una notificación Qt en el hilo principal.
    on_close :
        Callback opcional ``() -> None`` invocado cuando el circuito se cierra.
    """

    def __init__(
        self,
        max_failures: int = 5,
        recovery_timeout: float = 300.0,
        name: str = "API",
        on_open: Callable[[int], None] | None = None,
        on_close: Callable[[], None] | None = None,
    ) -> None:
        self._max_failures      = max_failures
        self._recovery_timeout  = recovery_timeout
        self._name              = name
        self._on_open           = on_open
        self._on_close          = on_close

        self._state             = CircuitState.CLOSED
        self._failure_count     = 0
        self._opened_at: float  = 0.0
        self._lock              = threading.Lock()

    # ── Propiedades públicas ──────────────────────────────────────────────────

    @property
    def state(self) -> CircuitState:
        with self._lock:
            self._check_recovery()
            return self._state

    @property
    def failure_count(self) -> int:
        with self._lock:
            return self._failure_count

    @property
    def seconds_remaining(self) -> float:
        """Segundos que quedan hasta que el circuito pase a HALF_OPEN (0 si ya pasó)."""
        with self._lock:
            if self._state != CircuitState.OPEN:
                return 0.0
            elapsed = time.monotonic() - self._opened_at
            return max(0.0, self._recovery_timeout - elapsed)

    def is_open(self) -> bool:
        return self.state == CircuitState.OPEN

    # ── Context manager ───────────────────────────────────────────────────────

    def __enter__(self) -> "CircuitBreaker":
        with self._lock:
            self._check_recovery()
            if self._state == CircuitState.OPEN:
                remaining = self._recovery_timeout - (time.monotonic() - self._opened_at)
                mins, secs = divmod(max(0.0, remaining), 60)
                raise CircuitOpenError(
                    f"Servicio '{self._name}' cortado por CircuitBreaker "
                    f"({int(mins)}m {int(secs)}s restantes antes de reintentar). "
                    f"Fallos acumulados: {self._failure_count}."
                )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        if exc_type is None:
            # Éxito → resetear
            self._record_success()
        elif exc_type is not CircuitOpenError:
            # Error real (no el nuestro) → registrar fallo
            self._record_failure()
        return False  # no suprimir excepciones

    # ── API explícita (sin context manager) ───────────────────────────────────

    def record_success(self) -> None:
        self._record_success()

    def record_failure(self) -> None:
        self._record_failure()

    def reset(self) -> None:
        """Resetea el circuito a CLOSED manualmente."""
        with self._lock:
            self._state         = CircuitState.CLOSED
            self._failure_count = 0
            self._opened_at     = 0.0
        _log.info("CircuitBreaker '%s' reseteado manualmente → CLOSED", self._name)

    def set_callbacks(
        self,
        on_open: Callable[[int], None] | None = None,
        on_close: Callable[[], None] | None = None,
    ) -> None:
        """Reemplaza los callbacks on_open / on_close en caliente (thread-safe)."""
        with self._lock:
            if on_open is not None:
                self._on_open = on_open
            if on_close is not None:
                self._on_close = on_close

    # ── Estado resumen ────────────────────────────────────────────────────────

    def status_text(self) -> str:
        """Texto corto para mostrar en la UI (una línea)."""
        with self._lock:
            self._check_recovery()
            if self._state == CircuitState.CLOSED:
                return f"✅ {self._name}: OK ({self._failure_count} fallos recientes)"
            if self._state == CircuitState.HALF_OPEN:
                return f"🔶 {self._name}: PROBANDO reconexión…"
            remaining = self._recovery_timeout - (time.monotonic() - self._opened_at)
            mins, secs = divmod(max(0.0, remaining), 60)
            return (
                f"🔴 {self._name}: CORTADO — {int(mins)}m {int(secs)}s "
                f"hasta próximo intento"
            )

    # ── Internos ──────────────────────────────────────────────────────────────

    def _check_recovery(self) -> None:
        """Transición OPEN → HALF_OPEN si expiró el timeout. Debe llamarse con lock activo."""
        if self._state == CircuitState.OPEN:
            elapsed = time.monotonic() - self._opened_at
            if elapsed >= self._recovery_timeout:
                self._state = CircuitState.HALF_OPEN
                _log.info(
                    "CircuitBreaker '%s' → HALF_OPEN (elapsed=%.0fs)",
                    self._name, elapsed,
                )

    def _record_success(self) -> None:
        with self._lock:
            if self._state in (CircuitState.HALF_OPEN, CircuitState.OPEN):
                _log.info("CircuitBreaker '%s' → CLOSED (recuperado)", self._name)
                if self._on_close:
                    try:
                        self._on_close()
                    except Exception:
                        pass
            self._state         = CircuitState.CLOSED
            self._failure_count = 0
            self._opened_at     = 0.0

    def _record_failure(self) -> None:
        with self._lock:
            self._failure_count += 1
            _log.warning(
                "CircuitBreaker '%s': fallo %d/%d",
                self._name, self._failure_count, self._max_failures,
            )
            if self._state == CircuitState.HALF_OPEN:
                # Prueba fallida → volver a OPEN
                self._opened_at = time.monotonic()
                self._state     = CircuitState.OPEN
                _log.warning("CircuitBreaker '%s' → OPEN (prueba fallida)", self._name)
            elif (
                self._state == CircuitState.CLOSED
                and self._failure_count >= self._max_failures
            ):
                self._opened_at = time.monotonic()
                self._state     = CircuitState.OPEN
                _log.error(
                    "CircuitBreaker '%s' → OPEN tras %d fallos consecutivos",
                    self._name, self._failure_count,
                )
                if self._on_open:
                    try:
                        self._on_open(self._failure_count)
                    except Exception:
                        pass


# ── Instancia global compartida (una por backend) ─────────────────────────────
# main_window puede importarla directamente sin crear una nueva cada vez.
_breakers: dict[str, CircuitBreaker] = {}
_breakers_lock = threading.Lock()


def get_breaker(
    name: str = "API",
    max_failures: int = 5,
    recovery_timeout: float = 300.0,
) -> CircuitBreaker:
    """Devuelve (o crea) el CircuitBreaker asociado a ``name``."""
    with _breakers_lock:
        if name not in _breakers:
            _breakers[name] = CircuitBreaker(
                max_failures=max_failures,
                recovery_timeout=recovery_timeout,
                name=name,
            )
        return _breakers[name]

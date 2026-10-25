"""Rate limiter con retry exponencial y fallback a backend local ante límite de cuota API."""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable

_log = logging.getLogger("ocr.rate_limiter")


class RateLimiter:
    """Gestiona llamadas a APIs externas con backoff exponencial ante 429/quota.

    Uso típico
    ----------
    ::

        rl = RateLimiter()
        result = rl.call_with_retry(
            engine.process_file, path,
            stop_flag_ref=_stop,
            fallback_fn=local_engine.process_file,
        )

    Parámetros
    ----------
    max_retries:           número máximo de reintentos ante error de rate limit
    base_delay:            espera inicial en segundos (se duplica en cada intento)
    max_delay:             techo de espera (cap del backoff)
    local_conf_threshold:  umbral de confianza para decidir si se activa fallback
    """

    def __init__(
        self,
        max_retries: int = 5,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        local_conf_threshold: float = 0.0,
    ) -> None:
        self._max_retries = max_retries
        self._base_delay = base_delay
        self._max_delay = max_delay
        self._local_conf_threshold = local_conf_threshold
        self._lock = threading.Lock()
        self._consecutive_429 = 0

    # ── Public API ─────────────────────────────────────────────────────────────

    def call_with_retry(
        self,
        fn: Callable[..., Any],
        *args: Any,
        stop_flag_ref: list[bool] | None = None,
        fallback_fn: Callable[..., Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        """Llama a *fn* con reintentos exponenciales ante errores 429/quota.

        Parameters
        ----------
        fn:             función a llamar (p. ej. ``engine.process_file``)
        *args:          argumentos posicionales para *fn*
        stop_flag_ref:  ``[bool]`` mutable — aborta si ``True``
        fallback_fn:    función alternativa local si se agotan los reintentos
        **kwargs:       argumentos clave para *fn*
        """
        last_exc: Exception | None = None

        for attempt in range(self._max_retries + 1):
            if stop_flag_ref and stop_flag_ref[0]:
                raise RuntimeError("Procesamiento detenido por el usuario")

            try:
                result = fn(*args, **kwargs)
                with self._lock:
                    self._consecutive_429 = 0  # reset en éxito
                return result

            except Exception as exc:
                if self._is_rate_limit_error(exc):
                    last_exc = exc
                    with self._lock:
                        self._consecutive_429 += 1

                    if attempt >= self._max_retries:
                        if fallback_fn is not None:
                            _log.warning(
                                "Rate limit persistente tras %d reintentos. Usando backend local.",
                                self._max_retries,
                            )
                            return fallback_fn(*args, **kwargs)
                        break  # sin fallback: salir del loop

                    wait = min(self._base_delay * (2 ** attempt), self._max_delay)
                    _log.warning(
                        "Rate limit detectado (intento %d/%d). Esperando %.1fs…",
                        attempt + 1,
                        self._max_retries,
                        wait,
                    )
                    # Espera interruptible: comprueba stop_flag cada 0.5 s
                    elapsed = 0.0
                    while elapsed < wait:
                        if stop_flag_ref and stop_flag_ref[0]:
                            raise RuntimeError(
                                "Procesamiento detenido durante espera de rate limit"
                            )
                        time.sleep(0.5)
                        elapsed += 0.5
                else:
                    raise  # error no relacionado con rate limit → propagar

        raise RuntimeError(
            f"Rate limit persistente tras {self._max_retries} reintentos: {last_exc}"
        )

    # ── Properties ─────────────────────────────────────────────────────────────

    @property
    def consecutive_429(self) -> int:
        """Número de errores 429 consecutivos desde el último éxito."""
        with self._lock:
            return self._consecutive_429

    # ── Helpers ─────────────────────────────────────────────────────────────────

    @staticmethod
    def _is_rate_limit_error(exc: Exception) -> bool:
        """Detecta errores de rate limit por mensaje o código HTTP."""
        msg = str(exc).lower()
        return (
            "429" in msg
            or "rate limit" in msg
            or "toomanyrequests" in msg
            or "quota" in msg
            or "exceeded" in msg
            or "ratelimit" in msg
            or "too many" in msg
        )

"""Watchdog de carpeta de entrada — FASE 6.

Monitorea una carpeta en un hilo de fondo y encola automáticamente
todo archivo nuevo que cumpla los filtros indicados.

Diseño
------
- Usa ``threading.Thread`` + polling con ``Path.stat()`` para evitar
  dependencias externas (la librería `watchdog` PyPI es opcional).
- Si ``watchdog`` está instalada se usará su Observer para mayor eficiencia;
  en caso contrario cae al polling cada ``poll_interval`` segundos.
- Emite una señal Qt-compatible vía callback en lugar de señales directas
  para no acoplar este módulo a PyQt6.

Uso típico
----------
    from src.core.folder_watcher import FolderWatcher

    def on_new_file(path: str) -> None:
        # Este callback se invoca desde el hilo watcher, NO desde el hilo Qt.
        # Usa QMetaObject.invokeMethod o una Queue thread-safe para pasar a Qt.
        queue.put(path)

    watcher = FolderWatcher(
        folder="/ruta/entrada",
        on_new_file=on_new_file,
        extensions={".pdf", ".png", ".jpg", ".tiff"},
    )
    watcher.start()
    # …
    watcher.stop()
"""
from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path
from typing import Callable, Set

_log = logging.getLogger("ocr.folder_watcher")

# Extensiones soportadas por defecto
_DEFAULT_EXTENSIONS: frozenset[str] = frozenset({
    ".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".webp",
})

# Tiempo mínimo en segundos que un archivo debe existir antes de procesarlo
# (evita leer archivos que aún se están copiando).
_STABLE_SECS: float = 2.0


def _is_stable(path: Path, stable_secs: float = _STABLE_SECS) -> bool:
    """Devuelve True si el archivo lleva al menos ``stable_secs`` sin modificarse."""
    try:
        mtime = path.stat().st_mtime
        return (time.time() - mtime) >= stable_secs
    except OSError:
        return False


class FolderWatcher:
    """Observador de carpeta con polling de respaldo.

    Parámetros
    ----------
    folder :
        Ruta de la carpeta a monitorear (debe existir).
    on_new_file :
        Callable(path: str) invocado desde el hilo watcher cuando se detecta
        un archivo nuevo y estable.
    extensions :
        Conjunto de extensiones a aceptar (con punto, lowercase).
        Por defecto: pdf, png, jpg, jpeg, tiff, bmp, webp.
    poll_interval :
        Segundos entre escaneos en modo polling.  Por defecto 3.
    stable_secs :
        Segundos de inactividad del archivo antes de considerarlo listo.
        Por defecto 2.
    recursive :
        Si True, monitorea también subdirectorios.
    """

    def __init__(
        self,
        folder: str | Path,
        on_new_file: Callable[[str], None],
        extensions: Set[str] | None = None,
        poll_interval: float = 3.0,
        stable_secs: float = _STABLE_SECS,
        recursive: bool = False,
    ) -> None:
        self._folder        = Path(folder)
        self._on_new_file   = on_new_file
        self._extensions    = frozenset(
            ext.lower() for ext in (extensions or _DEFAULT_EXTENSIONS)
        )
        self._poll_interval = max(0.5, float(poll_interval))
        self._stable_secs   = max(0.5, float(stable_secs))
        self._recursive     = recursive

        self._seen: set[str]       = set()   # rutas ya encoladas
        self._stop_event            = threading.Event()
        self._thread: threading.Thread | None = None
        self._watcher_obj: object | None = None  # objeto watchdog si disponible

    # ── Propiedades ───────────────────────────────────────────────────────────

    @property
    def folder(self) -> Path:
        return self._folder

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ── Control ───────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Inicia el hilo watcher (idempotente si ya está corriendo)."""
        if self.running:
            return

        if not self._folder.is_dir():
            raise FileNotFoundError(
                f"FolderWatcher: la carpeta no existe o no es un directorio: {self._folder}"
            )

        self._stop_event.clear()

        # Intentar usar la librería watchdog primero (más eficiente)
        started_watchdog = self._try_start_watchdog()
        if not started_watchdog:
            # Fallback a polling
            self._thread = threading.Thread(
                target=self._poll_loop,
                name=f"FolderWatcher-{self._folder.name}",
                daemon=True,
            )
            self._thread.start()
            _log.info("FolderWatcher: modo POLLING en '%s' (intervalo=%ss)",
                      self._folder, self._poll_interval)

    def stop(self) -> None:
        """Detiene el watcher."""
        self._stop_event.set()
        if self._watcher_obj is not None:
            try:
                self._watcher_obj.stop()
                self._watcher_obj.join(timeout=5)
            except Exception:
                pass
            self._watcher_obj = None
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        self._thread = None
        _log.info("FolderWatcher detenido")

    def set_folder(self, folder: str | Path) -> None:
        """Cambia la carpeta observada (detiene y reinicia si estaba corriendo)."""
        was_running = self.running
        if was_running:
            self.stop()
        self._folder = Path(folder)
        self._seen.clear()
        if was_running:
            self.start()

    def mark_seen(self, path: str) -> None:
        """Marca manualmente un archivo como ya procesado (evita reencolarlo)."""
        self._seen.add(str(path))

    # ── Implementación polling ─────────────────────────────────────────────────

    def _poll_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._scan()
            except Exception as exc:
                _log.warning("FolderWatcher poll error: %s", exc)
            self._stop_event.wait(timeout=self._poll_interval)

    def _scan(self) -> None:
        glob = "**/*" if self._recursive else "*"
        for p in self._folder.glob(glob):
            if not p.is_file():
                continue
            if p.suffix.lower() not in self._extensions:
                continue
            key = str(p.resolve())
            if key in self._seen:
                continue
            if not _is_stable(p, self._stable_secs):
                continue

            self._seen.add(key)
            _log.info("FolderWatcher: nuevo archivo detectado → %s", p.name)
            try:
                self._on_new_file(str(p))
            except Exception as exc:
                _log.error("FolderWatcher on_new_file() error: %s", exc)

    # ── Implementación watchdog (opcional) ────────────────────────────────────

    def _try_start_watchdog(self) -> bool:
        """Intenta usar la librería 'watchdog'. Devuelve True si tuvo éxito."""
        try:
            from watchdog.observers import Observer  # type: ignore[import]
            from watchdog.events import (  # type: ignore[import]
                FileSystemEventHandler,
                FileCreatedEvent,
                FileMovedEvent,
            )

            watcher = self   # captura de closure

            class _Handler(FileSystemEventHandler):  # type: ignore[misc]
                def _handle(self, path: str) -> None:
                    p = Path(path)
                    if p.suffix.lower() not in watcher._extensions:
                        return
                    key = str(p.resolve())
                    if key in watcher._seen:
                        return
                    # Esperar estabilidad (watchdog no garantiza que el archivo esté completo)
                    for _ in range(10):
                        if _is_stable(p, watcher._stable_secs):
                            break
                        time.sleep(0.5)
                    watcher._seen.add(key)
                    _log.info("FolderWatcher(watchdog): nuevo → %s", p.name)
                    try:
                        watcher._on_new_file(str(p))
                    except Exception as exc:
                        _log.error("FolderWatcher on_new_file() error: %s", exc)

                def on_created(self, event: FileCreatedEvent) -> None:
                    if not event.is_directory:
                        self._handle(event.src_path)

                def on_moved(self, event: FileMovedEvent) -> None:
                    if not event.is_directory:
                        self._handle(event.dest_path)

            observer = Observer()
            observer.schedule(_Handler(), str(self._folder), recursive=self._recursive)
            observer.start()
            self._watcher_obj = observer
            self._thread = observer  # type: ignore[assignment]
            _log.info("FolderWatcher: modo WATCHDOG en '%s'", self._folder)
            return True

        except ImportError:
            return False
        except Exception as exc:
            _log.warning("FolderWatcher: fallo al iniciar watchdog (%s), usando polling", exc)
            return False

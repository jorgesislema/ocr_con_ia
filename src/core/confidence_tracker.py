"""Rastreador persistente de métricas de confianza OCR por cliente/tipo de documento."""
from __future__ import annotations

import json
import logging
import threading
from pathlib import Path

_log = logging.getLogger("ocr.confidence_tracker")

_DEFAULT_PATH = Path.home() / ".ocr_confidence_metrics.json"
_MAX_VALUES_PER_KEY = 500  # ventana deslizante — evita crecimiento infinito en disco


class ConfidenceTracker:
    """Guarda y consulta métricas de confianza OCR por cliente/tipo de documento.

    El archivo de persistencia se almacena en ``~/.ocr_confidence_metrics.json``
    (configurable vía parámetro *path*).  Todas las operaciones son thread-safe.

    Formato de clave interna: ``"<client>/<doc_type>"``

    Uso típico
    ----------
    ::

        tracker = ConfidenceTracker()
        tracker.record("ACME S.A.", "Facturas/Contable", confidence=0.92, status="Procesado")
        metrics = tracker.get_metrics("ACME S.A.", "Facturas/Contable")
        # {'key': 'ACME S.A./Facturas/Contable', 'avg_confidence': 0.92,
        #  'error_rate': 0.0, 'total': 1, 'errors': 0}
    """

    def __init__(self, path: str | Path | None = None) -> None:
        self._path = Path(path) if path else _DEFAULT_PATH
        self._lock = threading.Lock()
        self._data: dict = self._load()

    # ── Write ──────────────────────────────────────────────────────────────────

    def record(
        self,
        client: str,
        doc_type: str,
        confidence: float,
        status: str,
    ) -> None:
        """Registra una nueva lectura de confianza para el par cliente/tipo.

        Parameters
        ----------
        client:     identificador del cliente (se usa ``"default"`` si desconocido)
        doc_type:   perfil de documento, p. ej. ``"Facturas/Contable"``
        confidence: valor 0-1
        status:     ``"Procesado"`` o ``"Error"`` (cualquier otro se ignora)
        """
        key = f"{client}/{doc_type}"
        with self._lock:
            entry = self._data.setdefault(key, {"values": [], "errors": 0, "total": 0})
            entry["total"] += 1
            entry["values"].append(round(float(confidence), 4))
            if status.strip().lower() == "error":
                entry["errors"] += 1
            # Mantener solo las últimas N lecturas (ventana deslizante)
            if len(entry["values"]) > _MAX_VALUES_PER_KEY:
                entry["values"] = entry["values"][-_MAX_VALUES_PER_KEY:]
            self._save_unlocked()

    # ── Read ───────────────────────────────────────────────────────────────────

    def get_metrics(self, client: str, doc_type: str) -> dict:
        """Devuelve métricas agregadas para el par cliente/tipo.

        Returns
        -------
        dict con claves:
            ``key``, ``avg_confidence`` (0-1), ``error_rate`` (0-1),
            ``total`` (registros acumulados), ``errors`` (registros con status Error)
        """
        key = f"{client}/{doc_type}"
        with self._lock:
            entry = dict(self._data.get(key, {}))

        values: list[float] = entry.get("values", [])
        total: int = entry.get("total", 0)
        errors: int = entry.get("errors", 0)
        avg = sum(values) / len(values) if values else 0.0
        err_rate = errors / total if total else 0.0
        return {
            "key": key,
            "avg_confidence": round(avg, 4),
            "error_rate": round(err_rate, 4),
            "total": total,
            "errors": errors,
        }

    def get_all_metrics(self) -> list[dict]:
        """Devuelve lista de métricas calculadas para todas las claves registradas."""
        with self._lock:
            keys = list(self._data.keys())

        result = []
        for key in keys:
            parts = key.split("/", 1)
            client = parts[0] if parts else "default"
            doc_type = parts[1] if len(parts) > 1 else key
            result.append(self.get_metrics(client, doc_type))
        return result

    def get_all(self) -> dict:
        """Devuelve copia raw del diccionario interno (para serialización/debug)."""
        with self._lock:
            return dict(self._data)

    def summary_text(self, client: str, doc_type: str) -> str:
        """Cadena lista para mostrar en UI con las métricas principales."""
        m = self.get_metrics(client, doc_type)
        return (
            f"[Métricas] {doc_type} · "
            f"Confianza avg: {m['avg_confidence']:.1%}  · "
            f"Tasa error: {m['error_rate']:.1%}  · "
            f"Total procesados: {m['total']}"
        )

    # ── Persistence ─────────────────────────────────────────────────────────────

    def _load(self) -> dict:
        try:
            if self._path.exists():
                return json.loads(self._path.read_text(encoding="utf-8"))
        except Exception as exc:
            _log.warning("No se pudo cargar métricas de confianza (%s): %s", self._path, exc)
        return {}

    def _save_unlocked(self) -> None:
        """Persiste al disco.  Debe llamarse dentro de ``self._lock``."""
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps(self._data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            _log.warning("No se pudo guardar métricas de confianza: %s", exc)

"""Motor de Aprendizaje de Correcciones — FASE 6.

Persiste en SQLite los pares (campo, valor_ocr) → corrección_humana  y
los ofrece como sugerencias al abrir el ReviewPanel.

Uso típico
----------
    from src.core.correction_learner import CorrectionLearner

    learner = CorrectionLearner()          # abre / crea la DB
    suggestions = learner.suggest(row)     # {"total": "1000.00", ...}
    learner.learn("total", "100.00", "1000.00")  # guarda corrección
"""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any

_log = logging.getLogger("ocr.correction_learner")

# Ruta por defecto: junto a la raíz del proyecto en la carpeta de datos
_DEFAULT_DB = Path(__file__).resolve().parent.parent.parent / "data" / "corrections.db"


class CorrectionLearner:
    """Almacén persistente de correcciones humanas con sugerencias automáticas.

    Parámetros
    ----------
    db_path :
        Ruta al archivo SQLite. Se crea si no existe.
    min_occurrences :
        Número mínimo de veces que debe aparecer un par (campo, ocr_value)
        para que la sugerencia se active.  Por defecto 1 (activa siempre).
    """

    def __init__(
        self,
        db_path: str | Path | None = None,
        min_occurrences: int = 1,
    ) -> None:
        self._db_path = Path(db_path or _DEFAULT_DB)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._min_occ = max(1, int(min_occurrences))
        self._conn = self._connect()
        self._init_schema()

    # ── Conexión ──────────────────────────────────────────────────────────────

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _init_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS corrections (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                field       TEXT    NOT NULL,
                ocr_value   TEXT    NOT NULL,
                correction  TEXT    NOT NULL,
                occurrences INTEGER NOT NULL DEFAULT 1,
                created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
                updated_at  TEXT    NOT NULL DEFAULT (datetime('now')),
                UNIQUE (field, ocr_value, correction)
            );
            CREATE INDEX IF NOT EXISTS idx_corrections_field_ocr
                ON corrections (field, ocr_value);
            """
        )
        self._conn.commit()

    # ── API pública ───────────────────────────────────────────────────────────

    def learn(self, field: str, ocr_value: Any, correction: Any) -> None:
        """Guarda o incrementa el contador de un par (campo, ocr_value → corrección).

        Parámetros
        ----------
        field :
            Nombre del campo extraído (ej. "total", "proveedor").
        ocr_value :
            Valor tal como lo devolvió el OCR (antes de corregir).
        correction :
            Valor corregido por el operario.
        """
        ocr_str  = str(ocr_value).strip()
        corr_str = str(correction).strip()
        field_str = str(field).strip().lower()

        if not ocr_str or not corr_str or ocr_str == corr_str:
            return  # nada que aprender

        try:
            self._conn.execute(
                """
                INSERT INTO corrections (field, ocr_value, correction, occurrences)
                VALUES (?, ?, ?, 1)
                ON CONFLICT(field, ocr_value, correction)
                DO UPDATE SET
                    occurrences = occurrences + 1,
                    updated_at  = datetime('now')
                """,
                (field_str, ocr_str, corr_str),
            )
            self._conn.commit()
            _log.debug("Corrección aprendida: [%s] '%s' → '%s'", field_str, ocr_str, corr_str)
        except Exception as exc:
            _log.warning("CorrectionLearner.learn error: %s", exc)

    def suggest(self, payload: dict[str, Any]) -> dict[str, str]:
        """Devuelve sugerencias para todos los campos del payload.

        Parámetros
        ----------
        payload :
            Diccionario campo → valor_ocr (el JSON extraído del documento).

        Devuelve
        --------
        dict con los campos para los que existe una corrección sugerida.
        Si un campo no tiene sugerencia, no aparece en el resultado.
        """
        suggestions: dict[str, str] = {}
        for field, value in payload.items():
            ocr_str   = str(value).strip() if value is not None else ""
            field_str = str(field).strip().lower()
            if not ocr_str:
                continue
            try:
                row = self._conn.execute(
                    """
                    SELECT correction FROM corrections
                    WHERE field = ? AND ocr_value = ? AND occurrences >= ?
                    ORDER BY occurrences DESC
                    LIMIT 1
                    """,
                    (field_str, ocr_str, self._min_occ),
                ).fetchone()
                if row:
                    suggestions[field] = row["correction"]
            except Exception as exc:
                _log.warning("CorrectionLearner.suggest error para '%s': %s", field, exc)
        return suggestions

    def learn_from_review(self, original_row: dict, corrected_row: dict) -> None:
        """Compara dos rows (antes y después de revisión humana) y aprende todos los cambios.

        Extrae los payloads JSON de los campos ``text`` para hacer la comparación
        campo a campo.
        """
        import json as _json

        def _extract(row: dict) -> dict[str, Any]:
            text = row.get("text", "")
            if isinstance(text, dict):
                return dict(text)
            if isinstance(text, str):
                try:
                    s, e = text.find("{"), text.rfind("}") + 1
                    if s >= 0 and e > s:
                        return _json.loads(text[s:e])
                except Exception:
                    pass
            return {k: v for k, v in row.items()
                    if k not in ("text", "images", "id", "pages", "_review_status")}

        orig    = _extract(original_row)
        updated = _extract(corrected_row)

        for field, corr_val in updated.items():
            orig_val = orig.get(field)
            if orig_val is not None and str(orig_val) != str(corr_val):
                self.learn(field, orig_val, corr_val)

    def top_patterns(self, limit: int = 20) -> list[dict]:
        """Devuelve los patrones más frecuentes (para auditoría/depuración)."""
        try:
            rows = self._conn.execute(
                """
                SELECT field, ocr_value, correction, occurrences, updated_at
                FROM corrections
                ORDER BY occurrences DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]
        except Exception as exc:
            _log.warning("CorrectionLearner.top_patterns error: %s", exc)
            return []

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:
            pass

"""Motor de reconciliación contable multi-documento.

Valida cruzadamente un conjunto de documentos relacionados:
  - Factura (invoice) vs Orden de Compra (purchase_order) vs Guía de Remisión (delivery_note)
  - Suma de líneas vs total declarado
  - Coherencia de fechas (OC→Guía→Factura)
  - Matching de SKU / referencia de artículo entre documentos
  - Tolerancia configurable (por defecto ±2%)

Interfaz pública
----------------
engine = ReconciliationEngine()
engine.load_rules("rules.json")          # opcional
issues = engine.cross_validate([doc1, doc2, doc3])

Cada doc es un dict con claves:
    doc_type   : "invoice" | "purchase_order" | "delivery_note" | str
    doc_id     : identificador único del documento
    date       : fecha del documento (str ISO o reconocible)
    total      : float  — total declarado
    subtotal   : float  — base imponible (opcional)
    tax        : float  — impuestos (opcional)
    po_number  : str    — nº de orden de compra referenciada
    lines      : list[dict]  — líneas con keys sku, qty, unit_price, amount
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

_log = logging.getLogger("ocr.accounting")

# ─────────────────────────────────────────────────────────────────────────────
# Tipo de retorno
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ValidationIssue:
    """Representa una discrepancia encontrada durante la reconciliación.

    Atributos
    ---------
    severity : ``"error"`` o ``"warning"``
    rule     : identificador de la regla que generó el issue
    message  : descripción legible
    docs     : IDs de documentos involucrados
    detail   : información adicional (valores concretos, diffs, etc.)
    """
    severity: str          # "error" | "warning"
    rule:     str
    message:  str
    docs:     list[str] = field(default_factory=list)
    detail:   dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "severity": self.severity,
            "rule":     self.rule,
            "message":  self.message,
            "docs":     self.docs,
            "detail":   self.detail,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Helpers internos
# ─────────────────────────────────────────────────────────────────────────────

_DATE_FMTS = [
    "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y",
    "%m/%d/%Y", "%Y/%m/%d", "%d.%m.%Y",
]


def _parse_date(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    s = str(value).strip()
    if not s:
        return None
    for fmt in _DATE_FMTS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _parse_number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    # Eliminar símbolos de moneda y espacios
    s = re.sub(r"[€$¥£]|USD|EUR", "", s, flags=re.IGNORECASE).replace(" ", "")
    # Normalizar separadores
    if "." in s and "," in s:
        if s.rfind(".") > s.rfind(","):
            s = s.replace(",", "")
        else:
            s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        parts = s.split(",")
        if len(parts[-1]) == 2:
            s = s.replace(",", ".")
        else:
            s = s.replace(",", "")
    s = re.sub(r"[^0-9.\-]", "", s)
    try:
        return float(s)
    except ValueError:
        return None


def _within_tolerance(a: float, b: float, pct: float) -> bool:
    """Devuelve True si |a-b| / max(|a|,|b|,1) <= pct/100."""
    if a == b == 0:
        return True
    return abs(a - b) / max(abs(a), abs(b), 1.0) <= pct / 100.0


# ─────────────────────────────────────────────────────────────────────────────
# Motor principal
# ─────────────────────────────────────────────────────────────────────────────

class ReconciliationEngine:
    """Motor de reconciliación contable multi-documento.

    Uso básico
    ----------
    engine = ReconciliationEngine()
    issues = engine.cross_validate([invoice_dict, po_dict, dn_dict])

    Uso con reglas personalizadas
    -----------------------------
    engine = ReconciliationEngine()
    engine.load_rules("rules.json")
    issues = engine.cross_validate(docs)
    """

    # Reglas base habilitadas por defecto
    _DEFAULT_RULES: dict[str, bool] = {
        "line_sum_vs_total":   True,   # suma de líneas vs total declarado
        "subtotal_tax_total":  True,   # subtotal + impuesto ≈ total
        "date_sequence":       True,   # OC ≤ guía ≤ factura
        "po_matching":         True,   # factura referencia OC existente
        "sku_matching":        True,   # SKUs presentes en OC/guía
        "duplicate_doc_id":    True,   # IDs duplicados en el lote
    }

    def __init__(self, tolerance_pct: float = 2.0) -> None:
        """
        Parameters
        ----------
        tolerance_pct : float
            Tolerancia porcentual para comparaciones numéricas (por defecto 2%).
        """
        self._tolerance   = float(tolerance_pct)
        self._rules       = dict(self._DEFAULT_RULES)  # copia mutable
        self._custom_tols: dict[str, float] = {}

    # ── Carga de reglas ───────────────────────────────────────────────────

    def load_rules(self, path: str | Path) -> None:
        """Carga ajustes de reglas desde un JSON.

        Formato admitido::

            {
                "tolerance_pct": 1.5,
                "rules": {
                    "sku_matching": false,
                    "date_sequence": true
                },
                "custom_tolerances": {
                    "line_sum_vs_total": 0.5
                }
            }
        """
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception as exc:
            _log.warning("load_rules: no se pudo cargar '%s': %s", path, exc)
            return

        if "tolerance_pct" in data:
            try:
                self._tolerance = float(data["tolerance_pct"])
            except Exception:
                pass

        for rule_name, enabled in (data.get("rules") or {}).items():
            if rule_name in self._rules:
                self._rules[rule_name] = bool(enabled)

        for rule_name, tol in (data.get("custom_tolerances") or {}).items():
            try:
                self._custom_tols[rule_name] = float(tol)
            except Exception:
                pass

        _log.debug("load_rules: reglas cargadas de %s — tolerancia=%.1f%%", path, self._tolerance)

    # ── API pública ───────────────────────────────────────────────────────

    def cross_validate(self, docs: list[dict]) -> list[ValidationIssue]:
        """Valida cruzadamente una lista de documentos relacionados.

        Parameters
        ----------
        docs : list[dict]
            Cada doc debe tener al menos ``doc_type`` y ``doc_id``.
            Campos opcionales: ``date``, ``total``, ``subtotal``, ``tax``,
            ``po_number``, ``lines`` (list[dict]).

        Returns
        -------
        list[ValidationIssue]
            Lista de discrepancias encontradas; vacía si todo es coherente.
        """
        issues: list[ValidationIssue] = []
        if not docs:
            return issues

        # Clasificar documentos por tipo
        invoices  = [d for d in docs if _doc_type(d) == "invoice"]
        pos       = [d for d in docs if _doc_type(d) == "purchase_order"]
        dns       = [d for d in docs if _doc_type(d) == "delivery_note"]

        # 1. IDs duplicados
        if self._rules.get("duplicate_doc_id", True):
            issues.extend(self._check_duplicate_ids(docs))

        # 2. Suma de líneas vs total en cada doc que tenga líneas
        if self._rules.get("line_sum_vs_total", True):
            for doc in docs:
                issues.extend(self._check_line_sum(doc))

        # 3. Subtotal + impuesto ≈ total
        if self._rules.get("subtotal_tax_total", True):
            for doc in docs:
                issues.extend(self._check_subtotal_tax(doc))

        # 4. Secuencia de fechas: OC ≤ Guía ≤ Factura
        if self._rules.get("date_sequence", True):
            issues.extend(self._check_date_sequence(invoices, pos, dns))

        # 5. Factura debe referenciar una PO existente en el lote
        if self._rules.get("po_matching", True):
            issues.extend(self._check_po_matching(invoices, pos))

        # 6. SKU de factura presentes en PO / Guía
        if self._rules.get("sku_matching", True):
            issues.extend(self._check_sku_matching(invoices, pos + dns))

        if issues:
            _log.warning(
                "cross_validate: %d issue(s) en lote de %d docs",
                len(issues), len(docs),
            )
        else:
            _log.info("cross_validate: lote de %d docs sin discrepancias", len(docs))

        return issues

    # ── Reglas individuales ───────────────────────────────────────────────

    def _tol(self, rule: str) -> float:
        """Tolerancia para una regla dada (usa custom_tolerances si existe)."""
        return self._custom_tols.get(rule, self._tolerance)

    def _check_duplicate_ids(self, docs: list[dict]) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        seen: dict[str, list[str]] = {}
        for doc in docs:
            did = str(doc.get("doc_id") or "").strip()
            if not did:
                continue
            seen.setdefault(did, []).append(_doc_type(doc))
        for did, types in seen.items():
            if len(types) > 1:
                issues.append(ValidationIssue(
                    severity="warning",
                    rule="duplicate_doc_id",
                    message=f"ID de documento duplicado: '{did}' aparece en {types}",
                    docs=[did],
                    detail={"types": types},
                ))
        return issues

    def _check_line_sum(self, doc: dict) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        lines: list[dict] = doc.get("lines") or []
        if not lines:
            return issues

        total_declared = _parse_number(doc.get("total"))
        if total_declared is None:
            return issues

        line_sum = 0.0
        computable = 0  # número de líneas con valor numérico
        for ln in lines:
            amount = _parse_number(ln.get("amount") or ln.get("line_total"))
            if amount is None:
                qty   = _parse_number(ln.get("qty") or ln.get("quantity") or ln.get("cantidad"))
                price = _parse_number(ln.get("unit_price") or ln.get("precio_unitario"))
                if qty is not None and price is not None:
                    amount = qty * price
            if amount is not None:
                line_sum += amount
                computable += 1

        # Sin datos numéricos en las líneas → no se puede validar
        if computable == 0:
            return issues

        tol = self._tol("line_sum_vs_total")
        if not _within_tolerance(line_sum, total_declared, tol):
            diff = round(line_sum - total_declared, 4)
            issues.append(ValidationIssue(
                severity="error",
                rule="line_sum_vs_total",
                message=(
                    f"[{_doc_id(doc)}] Suma de líneas ({line_sum:.2f}) "
                    f"≠ total declarado ({total_declared:.2f}) "
                    f"— diferencia {diff:+.4f} ({abs(diff/max(total_declared,1))*100:.2f}%)"
                ),
                docs=[_doc_id(doc)],
                detail={
                    "line_sum":       line_sum,
                    "total_declared": total_declared,
                    "diff":           diff,
                    "tolerance_pct":  tol,
                },
            ))
        return issues

    def _check_subtotal_tax(self, doc: dict) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        sub = _parse_number(
            doc.get("subtotal") or doc.get("base_imponible") or doc.get("base")
        )
        tax = _parse_number(
            doc.get("tax") or doc.get("iva") or doc.get("impuestos") or doc.get("igv")
        )
        tot = _parse_number(doc.get("total"))

        if sub is None or tax is None or tot is None:
            return issues

        computed = round(sub + tax, 4)
        tol = self._tol("subtotal_tax_total")
        if not _within_tolerance(computed, tot, tol):
            diff = round(computed - tot, 4)
            issues.append(ValidationIssue(
                severity="warning",
                rule="subtotal_tax_total",
                message=(
                    f"[{_doc_id(doc)}] subtotal({sub:.2f}) + impuesto({tax:.2f}) "
                    f"= {computed:.2f} ≠ total({tot:.2f}) "
                    f"— diferencia {diff:+.4f}"
                ),
                docs=[_doc_id(doc)],
                detail={
                    "subtotal":  sub,
                    "tax":       tax,
                    "computed":  computed,
                    "total":     tot,
                    "diff":      diff,
                },
            ))
        return issues

    def _check_date_sequence(
        self,
        invoices: list[dict],
        pos: list[dict],
        dns: list[dict],
    ) -> list[ValidationIssue]:
        """Verifica que OC ≤ Guía ≤ Factura."""
        issues: list[ValidationIssue] = []
        if not (pos or dns) or not invoices:
            return issues

        # Aplanamos fechas de cada tipo
        po_dates  = [(_parse_date(d.get("date")), _doc_id(d)) for d in pos]
        dn_dates  = [(_parse_date(d.get("date")), _doc_id(d)) for d in dns]
        inv_dates = [(_parse_date(d.get("date")), _doc_id(d)) for d in invoices]

        # Fecha más tardía de OC
        latest_po = max(
            (dt for dt, _ in po_dates if dt is not None), default=None
        )
        # Fecha más temprana de Guías
        earliest_dn = min(
            (dt for dt, _ in dn_dates if dt is not None), default=None
        )
        # Fecha más temprana de Facturas
        earliest_inv = min(
            (dt for dt, _ in inv_dates if dt is not None), default=None
        )

        # OC debe ser anterior a Guía
        if latest_po and earliest_dn and latest_po > earliest_dn:
            issues.append(ValidationIssue(
                severity="error",
                rule="date_sequence",
                message=(
                    f"Orden de compra ({latest_po.date()}) "
                    f"es posterior a Guía de Remisión ({earliest_dn.date()})"
                ),
                docs=[d for _, d in po_dates if _parse_date(d) is not None] +
                     [d for _, d in dn_dates if _parse_date(d) is not None],
                detail={
                    "latest_po":    str(latest_po.date()),
                    "earliest_dn":  str(earliest_dn.date()),
                },
            ))

        # Guía (o OC si no hay guía) debe ser anterior a Factura
        ref_date  = earliest_dn or latest_po
        ref_label = "Guía de Remisión" if earliest_dn else "Orden de Compra"
        if ref_date and earliest_inv and ref_date > earliest_inv:
            issues.append(ValidationIssue(
                severity="error",
                rule="date_sequence",
                message=(
                    f"{ref_label} ({ref_date.date()}) "
                    f"es posterior a Factura ({earliest_inv.date()})"
                ),
                docs=[d for _, d in inv_dates if _parse_date(d) is not None],
                detail={
                    "ref_date":       str(ref_date.date()),
                    "ref_label":      ref_label,
                    "earliest_inv":   str(earliest_inv.date()),
                },
            ))

        return issues

    def _check_po_matching(
        self,
        invoices: list[dict],
        pos: list[dict],
    ) -> list[ValidationIssue]:
        """Verifica que toda factura referencie una OC del lote."""
        if not pos or not invoices:
            return []

        issues: list[ValidationIssue] = []
        po_ids = {str(d.get("doc_id") or "").strip() for d in pos}
        po_ids.discard("")

        for inv in invoices:
            po_ref = str(inv.get("po_number") or inv.get("orden_compra") or "").strip()
            if not po_ref:
                # Solo warning si la factura no menciona ninguna OC
                issues.append(ValidationIssue(
                    severity="warning",
                    rule="po_matching",
                    message=(
                        f"[{_doc_id(inv)}] Factura sin referencia a Orden de Compra"
                    ),
                    docs=[_doc_id(inv)],
                ))
            elif po_ids and po_ref not in po_ids:
                issues.append(ValidationIssue(
                    severity="warning",
                    rule="po_matching",
                    message=(
                        f"[{_doc_id(inv)}] Factura referencia OC '{po_ref}' "
                        f"que no está en el lote (POs presentes: {sorted(po_ids)})"
                    ),
                    docs=[_doc_id(inv)],
                    detail={"po_ref": po_ref, "known_po_ids": sorted(po_ids)},
                ))
        return issues

    def _check_sku_matching(
        self,
        invoices: list[dict],
        reference_docs: list[dict],
    ) -> list[ValidationIssue]:
        """Verifica que los SKU de la factura coincidan con los docs de referencia."""
        if not reference_docs or not invoices:
            return []

        # Recopilar SKUs de los docs de referencia (OC + Guías)
        ref_skus: set[str] = set()
        for doc in reference_docs:
            for ln in (doc.get("lines") or []):
                sku = str(ln.get("sku") or ln.get("codigo") or ln.get("ref") or "").strip()
                if sku:
                    ref_skus.add(sku.upper())

        if not ref_skus:
            return []  # sin SKUs de referencia, no podemos comparar

        issues: list[ValidationIssue] = []
        for inv in invoices:
            inv_skus: set[str] = set()
            for ln in (inv.get("lines") or []):
                sku = str(ln.get("sku") or ln.get("codigo") or ln.get("ref") or "").strip()
                if sku:
                    inv_skus.add(sku.upper())

            if not inv_skus:
                continue  # factura sin líneas con SKU, no penalizar

            missing = inv_skus - ref_skus
            if missing:
                issues.append(ValidationIssue(
                    severity="warning",
                    rule="sku_matching",
                    message=(
                        f"[{_doc_id(inv)}] SKU(s) en factura no encontrados "
                        f"en OC/Guía: {sorted(missing)}"
                    ),
                    docs=[_doc_id(inv)],
                    detail={
                        "missing_skus":    sorted(missing),
                        "invoice_skus":    sorted(inv_skus),
                        "reference_skus":  sorted(ref_skus),
                    },
                ))
        return issues


# ─────────────────────────────────────────────────────────────────────────────
# Helpers privados de módulo
# ─────────────────────────────────────────────────────────────────────────────

def _doc_type(doc: dict) -> str:
    """Normaliza el campo ``doc_type`` a una de las categorías reconocidas."""
    raw = str(doc.get("doc_type") or doc.get("tipo") or "").strip().lower()
    if "invoice" in raw or "factura" in raw:
        return "invoice"
    if "purchase" in raw or "orden" in raw or "order" in raw or raw == "po":
        return "purchase_order"
    if "delivery" in raw or "guia" in raw or "guía" in raw or "remision" in raw or raw in ("dn", "gr"):
        return "delivery_note"
    return raw  # tipo desconocido


def _doc_id(doc: dict) -> str:
    return str(doc.get("doc_id") or doc.get("id") or doc.get("numero_factura") or "?")

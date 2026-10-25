"""Mapeo ERP: convierte resultados OCR validados a formatos CSV/XML para Odoo y SAP.

Clases principales
------------------
* ``ERPMapper``    — enriquece con códigos ERP/GL desde un CSV maestro de proveedores.
* ``ERPExporter``  — genera los asientos contables en los formatos de importación de
                     Odoo (CSV nativo) y SAP (BAPI_ACC_DOCUMENT_POST).

Formatos soportados
-------------------
* ``"journal"``  — CSV genérico con columnas:
    Fecha, Cuenta_Debe, Cuenta_Haber, Monto, IVA, Referencia, Descripcion,
    ID_Fiscal, Proveedor, ERP_Vendor_Code, GL_Account_Code
* ``"odoo"``     — CSV listo para importar en Odoo v14-17 (account.move):
    Date, Journal, Reference, Label, Account, Debit, Credit, Partner, Currency
* ``"odoo_xml"`` — XML para el endpoint RPC de Odoo (or-native import)
* ``"sap"``      — CSV BAPI_ACC_DOCUMENT_POST para SAP ECC/S4HANA:
    BUKRS, BLDAT, BUDAT, BLART, WAERS, BKTXT, HKONT, SHKZW, DMBTR, SGTXT, LIFNR

Uso rápido
----------
    from src.data.erp_mapper import ERPExporter

    rows = [
        {
            "fecha": "2025-04-10", "proveedor": "ACME S.A.",
            "id_fiscal": "20123456789", "total": 1190.0,
            "subtotal": 1000.0, "iva": 190.0,
            "numero_factura": "F-2025-001", "moneda": "PEN",
        },
    ]
    exporter = ERPExporter(vendor_master_path="vendor_master.csv")
    path = exporter.export(rows, fmt="odoo",   output_path="output/asientos_odoo.csv")
    path = exporter.export(rows, fmt="sap",    output_path="output/asientos_sap.csv")
    path = exporter.export(rows, fmt="journal",output_path="output/asientos.csv")
"""
from __future__ import annotations

import csv
import json
import re
import xml.etree.ElementTree as ET
from datetime import date as _date_cls, datetime
from pathlib import Path
from typing import Any

# pandas es opcional — si no está, usamos solo la lógica CSV stdlib
try:
    import pandas as pd
    _HAS_PANDAS = True
except ImportError:  # pragma: no cover
    pd = None  # type: ignore
    _HAS_PANDAS = False


# ── Constantes de cuentas contables por defecto ───────────────────────────────
# Estos valores pueden sobreescribirse pasando vendor_master.csv con columnas extras

_DEFAULT_AP_ACCOUNT   = "42100"   # Proveedores (cuenta de pasivo)
_DEFAULT_TAX_ACCOUNT  = "40110"   # IVA Soportado (activo/corriente)
_DEFAULT_EXP_ACCOUNT  = "60100"   # Compras / Gastos generales
_DEFAULT_JOURNAL_CODE = "FACT_P"  # Código de diario Odoo (Facturas Proveedor)
_DEFAULT_SAP_COMPANY  = "0001"    # Código de sociedad SAP
_DEFAULT_CURRENCY     = "PEN"     # Moneda por defecto


# ─────────────────────────────────────────────────────────────────────────────
# Helpers de parseo
# ─────────────────────────────────────────────────────────────────────────────

_DATE_FMTS = [
    "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y",
    "%d.%m.%Y", "%Y/%m/%d", "%d %b %Y",
]

def _parse_date(value: Any) -> str:
    """Devuelve la fecha en formato ISO YYYY-MM-DD o la fecha de hoy."""
    if not value:
        return datetime.today().strftime("%Y-%m-%d")
    s = str(value).strip()
    for fmt in _DATE_FMTS:
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return s  # devolver tal cual si no reconocemos el formato


def _parse_amount(value: Any, default: float = 0.0) -> float:
    """Convierte strings de monto a float tolerando separadores mixtos."""
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    s = re.sub(r"[€$¥£S/.](?=\d{3})", "", str(value).strip())  # separadores de miles
    s = re.sub(r"[€$¥£]|USD|EUR|PEN|MXN|CLP|COP", "", s, flags=re.IGNORECASE)
    s = s.replace(" ", "")
    # Normalizar coma decimal
    if "," in s and "." in s:
        if s.rfind(".") > s.rfind(","):
            s = s.replace(",", "")
        else:
            s = s.replace(".", "").replace(",", ".")
    elif "," in s and len(s.split(",")[-1]) <= 2:
        s = s.replace(",", ".")
    s = re.sub(r"[^0-9.\-]", "", s)
    try:
        return float(s)
    except ValueError:
        return default


def _get(row: dict, *keys: str, default: Any = "") -> Any:
    """Busca el primer valor no vacío entre las claves alternativas."""
    for k in keys:
        v = row.get(k)
        if v not in (None, "", "null", "NULL"):
            return v
    return default


# ─────────────────────────────────────────────────────────────────────────────
# ERPMapper — enriquecimiento con maestro de proveedores
# ─────────────────────────────────────────────────────────────────────────────

class ERPMapper:
    """Une los datos extraídos con un CSV maestro de proveedores para añadir
    códigos ERP (Vendor Code) y cuentas GL (GL Account Code).

    El CSV debe contener al menos las columnas:
    ``ID Fiscal``, ``ERP_Vendor_Code``, ``GL_Account_Code``.

    Columnas opcionales adicionales que se usan si están presentes:
    ``AP_Account``, ``Tax_Account``, ``Company_Code``.
    """

    def __init__(self, vendor_master_path: str | Path = "") -> None:
        self.vendor_master_path = Path(vendor_master_path) if vendor_master_path else None
        self._master: list[dict] | None = None

    # ── Carga del maestro ─────────────────────────────────────────────────

    def _load_master(self) -> list[dict]:
        if self._master is not None:
            return self._master
        if not self.vendor_master_path or not self.vendor_master_path.exists():
            self._master = []
            return self._master
        rows: list[dict] = []
        try:
            with open(self.vendor_master_path, newline="", encoding="utf-8-sig") as fh:
                reader = csv.DictReader(fh)
                for row in reader:
                    rows.append({k.strip(): str(v or "").strip() for k, v in row.items()})
        except Exception:
            pass
        self._master = rows
        return self._master

    def _lookup(self, id_fiscal: str) -> dict:
        """Devuelve el registro del maestro para un ID Fiscal dado."""
        norm = str(id_fiscal or "").strip()
        for rec in self._load_master():
            if rec.get("ID Fiscal", "").strip() == norm:
                return rec
        return {}

    # ── API pública ───────────────────────────────────────────────────────

    def enrich(self, row: dict) -> dict:
        """Añade claves ERP a un dict de resultado OCR en base al ID Fiscal."""
        id_fiscal = str(_get(row, "id_fiscal", "emisor_ruc", "ruc", "ID Fiscal", default=""))
        rec = self._lookup(id_fiscal)
        result = dict(row)
        result["ERP_Vendor_Code"] = rec.get("ERP_Vendor_Code") or "NUEVO_PROVEEDOR"
        result["GL_Account_Code"] = rec.get("GL_Account_Code") or _DEFAULT_EXP_ACCOUNT
        result["AP_Account"]      = rec.get("AP_Account")      or _DEFAULT_AP_ACCOUNT
        result["Tax_Account"]     = rec.get("Tax_Account")     or _DEFAULT_TAX_ACCOUNT
        result["Company_Code"]    = rec.get("Company_Code")    or _DEFAULT_SAP_COMPANY
        return result

    def apply_gl_codes(self, extracted_df: "pd.DataFrame") -> "pd.DataFrame":
        """Compat: enriquece un DataFrame de pandas (pandas requerido)."""
        if not _HAS_PANDAS:
            raise ImportError("pandas es necesario para apply_gl_codes()")
        records = extracted_df.to_dict(orient="records")
        enriched = [self.enrich(r) for r in records]
        return pd.DataFrame(enriched)


# ─────────────────────────────────────────────────────────────────────────────
# ERPExporter — genera asientos contables en formato de destino
# ─────────────────────────────────────────────────────────────────────────────

class ERPExporter:
    """Convierte una lista de dicts de resultados OCR a los formatos de
    importación contable de Odoo o SAP.

    Parámetros
    ----------
    vendor_master_path : str | Path
        Ruta al CSV maestro de proveedores (puede ser '' para omitir).
    default_currency : str
        Moneda ISO por defecto (ej. "PEN", "USD", "EUR").
    """

    def __init__(
        self,
        vendor_master_path: str | Path = "",
        default_currency: str = _DEFAULT_CURRENCY,
    ) -> None:
        self._mapper = ERPMapper(vendor_master_path)
        self._currency = default_currency.upper()

    # ── API pública ───────────────────────────────────────────────────────

    def export(
        self,
        rows: list[dict],
        fmt: str = "journal",
        output_path: str | Path = "",
    ) -> Path:
        """Exporta los resultados OCR al formato indicado.

        Parámetros
        ----------
        rows : list[dict]
            Lista de dicts de resultados OCR.  Cada dict puede tener:
            ``fecha``, ``proveedor``, ``id_fiscal``, ``total``,
            ``subtotal``, ``iva``, ``numero_factura``, ``moneda``.
        fmt : str
            ``"journal"`` (CSV genérico) · ``"odoo"`` (Odoo CSV) ·
            ``"odoo_xml"`` (XML Odoo) · ``"sap"`` (SAP CSV).
        output_path : str | Path
            Ruta de salida; si está vacía, se genera automáticamente junto
            al primer documento o en el directorio actual.

        Devuelve
        --------
        Path al archivo generado.
        """
        enriched = [self._mapper.enrich(r) for r in rows]
        out = Path(output_path) if output_path else self._auto_path(fmt)

        fmt_norm = fmt.lower().replace("-", "_")
        if fmt_norm == "odoo":
            return self._write_odoo_csv(enriched, out)
        if fmt_norm in ("odoo_xml", "xml"):
            return self._write_odoo_xml(enriched, out)
        if fmt_norm == "sap":
            return self._write_sap_csv(enriched, out)
        # default: journal CSV genérico
        return self._write_journal_csv(enriched, out)

    # ── CSV Genérico — Asiento Diario ─────────────────────────────────────

    def _write_journal_csv(self, rows: list[dict], out: Path) -> Path:
        """CSV genérico: una fila de asiento por factura."""
        out.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = [
            "Fecha", "Cuenta_Debe", "Cuenta_Haber",
            "Monto", "IVA", "Total",
            "Referencia", "Descripcion",
            "ID_Fiscal", "Proveedor",
            "ERP_Vendor_Code", "GL_Account_Code", "Moneda",
        ]
        with open(out, "w", newline="", encoding="utf-8-sig") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for r in rows:
                total    = _parse_amount(_get(r, "total", "monto", "importe"))
                subtotal = _parse_amount(_get(r, "subtotal", "base_imponible"))
                iva      = _parse_amount(_get(r, "iva", "impuesto", "igv", "tax"))
                if subtotal == 0 and iva == 0 and total > 0:
                    # Desglosar asumiendo IVA del 18 %
                    subtotal = round(total / 1.18, 2)
                    iva      = round(total - subtotal, 2)
                writer.writerow({
                    "Fecha":          _parse_date(_get(r, "fecha", "date")),
                    "Cuenta_Debe":    r.get("GL_Account_Code") or _DEFAULT_EXP_ACCOUNT,
                    "Cuenta_Haber":   r.get("AP_Account")      or _DEFAULT_AP_ACCOUNT,
                    "Monto":          f"{subtotal:.2f}",
                    "IVA":            f"{iva:.2f}",
                    "Total":          f"{total:.2f}",
                    "Referencia":     _get(r, "numero_factura", "invoice_number", "referencia", "ref"),
                    "Descripcion":    _get(r, "descripcion", "concepto", "description"),
                    "ID_Fiscal":      _get(r, "id_fiscal", "emisor_ruc", "ruc"),
                    "Proveedor":      _get(r, "proveedor", "emisor", "vendor", "supplier"),
                    "ERP_Vendor_Code": r.get("ERP_Vendor_Code", "NUEVO_PROVEEDOR"),
                    "GL_Account_Code": r.get("GL_Account_Code", _DEFAULT_EXP_ACCOUNT),
                    "Moneda":         _get(r, "moneda", "currency") or self._currency,
                })
        return out

    # ── Odoo CSV (importación directa account.move) ───────────────────────

    def _write_odoo_csv(self, rows: list[dict], out: Path) -> Path:
        """CSV en el formato nativo de importación de Odoo v14-17.

        Genera dos líneas por factura (debe + haber).
        """
        out.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = [
            "Date", "Journal", "Reference",
            "Label", "Account", "Debit", "Credit",
            "Partner", "Currency",
        ]
        with open(out, "w", newline="", encoding="utf-8-sig") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            for r in rows:
                fecha    = _parse_date(_get(r, "fecha", "date"))
                ref      = str(_get(r, "numero_factura", "invoice_number", "referencia", "ref") or "")
                partner  = str(_get(r, "proveedor", "emisor", "vendor") or "")
                total    = _parse_amount(_get(r, "total", "monto", "importe"))
                subtotal = _parse_amount(_get(r, "subtotal", "base_imponible"))
                iva      = _parse_amount(_get(r, "iva", "impuesto", "igv", "tax"))
                currency = str(_get(r, "moneda", "currency") or self._currency).upper()
                gl_acc   = r.get("GL_Account_Code") or _DEFAULT_EXP_ACCOUNT
                ap_acc   = r.get("AP_Account")      or _DEFAULT_AP_ACCOUNT
                tax_acc  = r.get("Tax_Account")     or _DEFAULT_TAX_ACCOUNT

                if subtotal == 0 and iva == 0 and total > 0:
                    subtotal = round(total / 1.18, 2)
                    iva      = round(total - subtotal, 2)

                # Línea gasto (DEBE)
                writer.writerow({
                    "Date": fecha, "Journal": _DEFAULT_JOURNAL_CODE,
                    "Reference": ref,
                    "Label": f"Gasto — {ref}",
                    "Account": gl_acc,
                    "Debit": f"{subtotal:.2f}", "Credit": "0.00",
                    "Partner": partner, "Currency": currency,
                })
                # Línea IVA (DEBE) — solo si hay IVA
                if iva > 0:
                    writer.writerow({
                        "Date": fecha, "Journal": _DEFAULT_JOURNAL_CODE,
                        "Reference": ref,
                        "Label": f"IVA Soportado — {ref}",
                        "Account": tax_acc,
                        "Debit": f"{iva:.2f}", "Credit": "0.00",
                        "Partner": partner, "Currency": currency,
                    })
                # Línea proveedor (HABER)
                writer.writerow({
                    "Date": fecha, "Journal": _DEFAULT_JOURNAL_CODE,
                    "Reference": ref,
                    "Label": f"Factura proveedor — {ref}",
                    "Account": ap_acc,
                    "Debit": "0.00", "Credit": f"{total:.2f}",
                    "Partner": partner, "Currency": currency,
                })
        return out

    # ── Odoo XML (xmlrpc-ready, optional) ────────────────────────────────

    def _write_odoo_xml(self, rows: list[dict], out: Path) -> Path:
        """XML de asientos para importar vía opción 'Importar' de Odoo."""
        out.parent.mkdir(parents=True, exist_ok=True)
        root = ET.Element("odoo")
        for r in rows:
            fecha    = _parse_date(_get(r, "fecha", "date"))
            ref      = str(_get(r, "numero_factura", "invoice_number", "referencia") or "")
            partner  = str(_get(r, "proveedor", "emisor", "vendor") or "")
            total    = _parse_amount(_get(r, "total", "monto", "importe"))
            subtotal = _parse_amount(_get(r, "subtotal", "base_imponible"))
            iva      = _parse_amount(_get(r, "iva", "impuesto", "igv", "tax"))
            if subtotal == 0 and iva == 0 and total > 0:
                subtotal = round(total / 1.18, 2)
                iva      = round(total - subtotal, 2)
            currency = str(_get(r, "moneda", "currency") or self._currency).upper()
            gl_acc   = r.get("GL_Account_Code") or _DEFAULT_EXP_ACCOUNT
            ap_acc   = r.get("AP_Account")      or _DEFAULT_AP_ACCOUNT
            tax_acc  = r.get("Tax_Account")     or _DEFAULT_TAX_ACCOUNT

            move = ET.SubElement(root, "record", model="account.move", id=f"move_{ref or id(r)}")
            ET.SubElement(move, "field", name="date").text = fecha
            ET.SubElement(move, "field", name="ref").text  = ref
            ET.SubElement(move, "field", name="journal_id", ref=_DEFAULT_JOURNAL_CODE)
            ET.SubElement(move, "field", name="currency_id", ref=f"base.{currency.lower()}")

            lines = ET.SubElement(move, "field", name="line_ids")
            for account, debit, credit, label in [
                (gl_acc,  subtotal, 0.0,  f"Gasto — {ref}"),
                (tax_acc, iva,      0.0,  f"IVA — {ref}") if iva > 0 else (None, None, None, None),
                (ap_acc,  0.0,      total, f"Proveedor — {ref}"),
            ]:
                if account is None:
                    continue
                line = ET.SubElement(lines, "record", model="account.move.line")
                ET.SubElement(line, "field", name="name").text        = label
                ET.SubElement(line, "field", name="account_id").text  = account
                ET.SubElement(line, "field", name="debit").text       = f"{debit:.2f}"
                ET.SubElement(line, "field", name="credit").text      = f"{credit:.2f}"
                ET.SubElement(line, "field", name="partner_id").text  = partner

        tree = ET.ElementTree(root)
        ET.indent(tree, space="  ")
        tree.write(str(out), encoding="utf-8", xml_declaration=True)
        return out

    # ── SAP CSV (BAPI_ACC_DOCUMENT_POST) ─────────────────────────────────

    def _write_sap_csv(self, rows: list[dict], out: Path) -> Path:
        """CSV para importación SAP vía BAPI_ACC_DOCUMENT_POST.

        Columnas: BUKRS, BLDAT, BUDAT, BLART, WAERS, BKTXT,
                  HKONT, SHKZW, DMBTR, SGTXT, LIFNR
        """
        out.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = [
            "BUKRS", "BLDAT", "BUDAT", "BLART", "WAERS",
            "BKTXT", "HKONT", "SHKZW", "DMBTR", "SGTXT", "LIFNR",
        ]
        today = datetime.today().strftime("%Y%m%d")
        with open(out, "w", newline="", encoding="utf-8-sig") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames, delimiter=";")
            writer.writeheader()
            for r in rows:
                try:
                    fecha_iso = _parse_date(_get(r, "fecha", "date"))
                    bldat = fecha_iso.replace("-", "")  # YYYYMMDD
                except Exception:
                    bldat = today
                ref      = str(_get(r, "numero_factura", "invoice_number", "referencia") or "")
                lifnr    = str(r.get("ERP_Vendor_Code") or "NUEVO_PROVEEDOR")
                total    = _parse_amount(_get(r, "total", "monto", "importe"))
                subtotal = _parse_amount(_get(r, "subtotal", "base_imponible"))
                iva      = _parse_amount(_get(r, "iva", "impuesto", "igv", "tax"))
                currency = str(_get(r, "moneda", "currency") or self._currency).upper()
                gl_acc   = r.get("GL_Account_Code") or _DEFAULT_EXP_ACCOUNT
                ap_acc   = r.get("AP_Account")      or _DEFAULT_AP_ACCOUNT
                tax_acc  = r.get("Tax_Account")     or _DEFAULT_TAX_ACCOUNT
                bukrs    = r.get("Company_Code")    or _DEFAULT_SAP_COMPANY

                if subtotal == 0 and iva == 0 and total > 0:
                    subtotal = round(total / 1.18, 2)
                    iva      = round(total - subtotal, 2)

                common = {
                    "BUKRS": bukrs, "BLDAT": bldat, "BUDAT": today,
                    "BLART": "RE", "WAERS": currency,
                    "BKTXT": f"OCR-{ref}"[:25],
                }
                # Posición gasto (DEBE = S)
                writer.writerow({**common,
                    "HKONT": gl_acc, "SHKZW": "S",
                    "DMBTR": f"{subtotal:.2f}",
                    "SGTXT": f"Gasto {ref}"[:50], "LIFNR": lifnr,
                })
                # Posición IVA (DEBE = S)
                if iva > 0:
                    writer.writerow({**common,
                        "HKONT": tax_acc, "SHKZW": "S",
                        "DMBTR": f"{iva:.2f}",
                        "SGTXT": f"IVA {ref}"[:50], "LIFNR": "",
                    })
                # Posición proveedor (HABER = H)
                writer.writerow({**common,
                    "HKONT": ap_acc, "SHKZW": "H",
                    "DMBTR": f"{total:.2f}",
                    "SGTXT": f"Prov {ref}"[:50], "LIFNR": lifnr,
                })
        return out

    # ── Helpers ───────────────────────────────────────────────────────────

    def _auto_path(self, fmt: str) -> Path:
        ext_map = {"odoo": "csv", "odoo_xml": "xml", "xml": "xml", "sap": "csv"}
        ext = ext_map.get(fmt.lower(), "csv")
        today = datetime.today().strftime("%Y%m%d_%H%M%S")
        return Path(f"erp_export_{fmt}_{today}.{ext}")


# ── Función de conveniencia ────────────────────────────────────────────────────

def export_to_erp(
    ocr_results: list[dict],
    fmt: str = "journal",
    output_path: str | Path = "",
    vendor_master_path: str | Path = "",
) -> Path:
    """Atajo de módulo. Exporta directamente sin instanciar ``ERPExporter``.

    Parámetros
    ----------
    ocr_results        : lista de dicts de resultados OCR.
    fmt                : ``"journal"``, ``"odoo"``, ``"odoo_xml"``, ``"sap"``.
    output_path        : ruta de salida (opcional).
    vendor_master_path : ruta al CSV maestro de proveedores (opcional).

    Devuelve
    --------
    Path al archivo generado.
    """
    exporter = ERPExporter(vendor_master_path=vendor_master_path)
    return exporter.export(ocr_results, fmt=fmt, output_path=output_path)

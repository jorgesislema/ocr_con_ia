"""Normalización post-OCR de texto extraído.

Aplica correcciones deterministas sobre el texto bruto devuelto por el motor
OCR antes de que llegue al parser o a la UI:

- Fechas: varios formatos → ISO 8601 (YYYY-MM-DD) donde sea posible.
- Monedas: limpieza de símbolos, espacios y separadores de miles.
- Espacios: elimina líneas vacías múltiples, normaliza tabulaciones.
- JSON passthrough: si el texto es un JSON válido, no se toca la estructura
  interna (solo se normalizan valores de tipo string dentro de él).

Punto de entrada principal
--------------------------
normalize_text(text: str) -> str
"""
from __future__ import annotations

import json
import re
from typing import Any


# ─────────────────────────────────────────────────────────────────────────────
# Patrones
# ─────────────────────────────────────────────────────────────────────────────

# Fechas —————————————————————————————————————————————————————————————————
# DD/MM/YYYY o DD-MM-YYYY
_PAT_DMY = re.compile(
    r"(?<!\d)"
    r"(0?[1-9]|[12]\d|3[01])"  # día
    r"[/\-\.]"
    r"(0?[1-9]|1[0-2])"        # mes
    r"[/\-\.]"
    r"(\d{4})"                  # año 4 dígitos
    r"(?!\d)"
)

# MM/DD/YYYY (solo cuando el día es > 12 para distinguirlo del anterior)
_PAT_MDY = re.compile(
    r"(?<!\d)"
    r"(0?[1-9]|1[0-2])"        # mes
    r"[/\-\.]"
    r"(1[3-9]|2\d|3[01])"      # día inequívoco > 12
    r"[/\-\.]"
    r"(\d{4})"
    r"(?!\d)"
)

# "12 de enero de 2024", "12 enero 2024", etc.
_MESES_ES = {
    "enero": "01", "febrero": "02", "marzo": "03", "abril": "04",
    "mayo": "05", "junio": "06", "julio": "07", "agosto": "08",
    "septiembre": "09", "octubre": "10", "noviembre": "11", "diciembre": "12",
    "jan": "01", "feb": "02", "mar": "03", "apr": "04",
    "may": "05", "jun": "06", "jul": "07", "aug": "08",
    "sep": "09", "oct": "10", "nov": "11", "dec": "12",
}
_MESES_PATTERN = "|".join(_MESES_ES.keys())
_PAT_TEXTUAL = re.compile(
    r"(?<!\w)"
    r"(0?[1-9]|[12]\d|3[01])"          # día
    r"\s+(?:de\s+)?"
    r"(" + _MESES_PATTERN + r")"        # mes textual
    r"(?:\s+de)?\s+"
    r"(\d{4})"                           # año
    r"(?!\w)",
    re.IGNORECASE,
)

# Monedas ————————————————————————————————————————————————————————————————
# Detecta: $ 1.234,56 / USD 1,234.56 / €1.234,56 / 1.234,56 USD
_PAT_CURRENCY = re.compile(
    r"([\$€£¥]|USD|EUR|GBP|JPY)?\s*"
    r"(\d{1,3}(?:[.,]\d{3})+(?:[.,]\d{1,4})?|\d+[.,]\d{1,4}|\d+)"
    r"\s*([\$€£¥]|USD|EUR|GBP|JPY)?",
    re.IGNORECASE,
)

# Espacios ————————————————————————————————————————————————————————————————
_PAT_MULTI_BLANK = re.compile(r"\n{3,}")
_PAT_TRAILING    = re.compile(r"[ \t]+$", re.MULTILINE)
_PAT_TABS        = re.compile(r"\t")


# ─────────────────────────────────────────────────────────────────────────────
# Utilidades internas
# ─────────────────────────────────────────────────────────────────────────────

def _normalize_date_dmy(m: re.Match) -> str:
    day, month, year = m.group(1), m.group(2), m.group(3)
    return f"{year}-{month.zfill(2)}-{day.zfill(2)}"


def _normalize_date_mdy(m: re.Match) -> str:
    month, day, year = m.group(1), m.group(2), m.group(3)
    return f"{year}-{month.zfill(2)}-{day.zfill(2)}"


def _normalize_date_textual(m: re.Match) -> str:
    day   = m.group(1).zfill(2)
    month = _MESES_ES.get(m.group(2).lower(), "??")
    year  = m.group(3)
    return f"{year}-{month}-{day}"


def _normalize_dates(text: str) -> str:
    """Convierte fechas encontradas en el texto a ISO 8601 (YYYY-MM-DD)."""
    text = _PAT_TEXTUAL.sub(_normalize_date_textual, text)
    text = _PAT_MDY.sub(_normalize_date_mdy, text)
    text = _PAT_DMY.sub(_normalize_date_dmy, text)
    return text


def _normalize_currency_value(value_str: str) -> str:
    """Devuelve un string numérico limpio con punto decimal estándar.

    Detecta automáticamente si el separador de miles es '.' o ','
    según la cantidad de dígitos tras el último separador.
    """
    s = value_str.strip()
    # Contar ocurrencias de punto y coma
    n_dot   = s.count(".")
    n_comma = s.count(",")

    if n_dot == 0 and n_comma == 0:
        return s  # entero sin separadores
    if n_dot > 1 and n_comma == 0:
        # Ej: 1.234.567 → separadores de miles con punto → entero
        return s.replace(".", "")
    if n_comma > 1 and n_dot == 0:
        # Ej: 1,234,567 → separadores de miles con coma → entero
        return s.replace(",", "")
    if n_dot >= 1 and n_comma >= 1:
        # Hay ambos — el que aparece último es el decimal
        last_dot   = s.rfind(".")
        last_comma = s.rfind(",")
        if last_dot > last_comma:
            # Punto decimal → 1.234,56  no; 1,234.56  sí
            return s.replace(",", "")
        else:
            # Coma decimal → 1.234,56
            return s.replace(".", "").replace(",", ".")
    if n_comma == 1 and n_dot == 0:
        parts = s.split(",")
        if len(parts[1]) <= 2 and len(parts[0]) <= 3:
            # Probablemente decimal: 12,34
            return s.replace(",", ".")
        elif len(parts[1]) == 3:
            # Probablemente miles: 1,234
            return s.replace(",", "")
    if n_dot == 1 and n_comma == 0:
        parts = s.split(".")
        if len(parts[1]) == 3 and len(parts[0]) >= 1:
            # Probablemente miles: 1.234
            return s.replace(".", "")
        return s  # decimal normal
    return s


def _normalize_amounts_in_text(text: str) -> str:
    """Normaliza cantidades monetarias en texto libre (no JSON).

    No modifica la sintaxis del texto; solo limpia separadores de miles
    para que los parsers posteriores lean correctamente los números.
    Solo actúa cuando el número va acompañado de un símbolo de divisa.
    """
    def _repl(m: re.Match) -> str:
        prefix  = (m.group(1) or "").strip()
        raw_val = m.group(2)
        suffix  = (m.group(3) or "").strip()
        # Ignorar coincidencias sin símbolo de divisa (evita tocar fechas u otros números)
        if not prefix and not suffix:
            return m.group(0)
        cleaned = _normalize_currency_value(raw_val)
        if prefix:
            return f"{prefix}{cleaned}"
        if suffix:
            return f"{cleaned} {suffix}"
        return cleaned

    # Solo aplicar si hay símbolo o palabra de divisa en el texto completo
    if not re.search(r"[\$€£¥]|USD|EUR|GBP", text, re.IGNORECASE):
        return text
    return _PAT_CURRENCY.sub(_repl, text)


def _normalize_whitespace(text: str) -> str:
    """Limpia espacios y líneas en blanco excesivas."""
    text = _PAT_TABS.sub("    ", text)
    text = _PAT_TRAILING.sub("", text)
    text = _PAT_MULTI_BLANK.sub("\n\n", text)
    return text.strip()


# ─────────────────────────────────────────────────────────────────────────────
# Normalización de JSON
# ─────────────────────────────────────────────────────────────────────────────

def _normalize_json_values(obj: Any) -> Any:
    """Recorre recursivamente un JSON y normaliza las cadenas de texto."""
    if isinstance(obj, dict):
        return {k: _normalize_json_values(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_normalize_json_values(item) for item in obj]
    if isinstance(obj, str):
        val = _normalize_dates(obj)
        return val
    return obj


def _try_normalize_as_json(text: str) -> str | None:
    """Si ``text`` es JSON válido, normaliza sus valores string y devuelve el JSON.

    Devuelve ``None`` si el texto no es JSON.
    """
    stripped = text.strip()
    if not (stripped.startswith("{") or stripped.startswith("[")):
        return None
    try:
        obj = json.loads(stripped)
    except Exception:
        return None
    normalized = _normalize_json_values(obj)
    try:
        return json.dumps(normalized, ensure_ascii=False, indent=2)
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Punto de entrada público
# ─────────────────────────────────────────────────────────────────────────────

def normalize_text(text: str) -> str:
    """Normaliza el texto extraído por el motor OCR.

    Estrategia:
    1. Si el texto es JSON → normalizar valores internos (fechas ISO) y devolver.
    2. Si es texto libre  → normalizar fechas, monedas y espacios.

    Nunca lanza excepciones; en caso de error devuelve el texto original.
    """
    if not text or not isinstance(text, str):
        return text or ""
    try:
        # Intentar tratarlo como JSON
        json_result = _try_normalize_as_json(text)
        if json_result is not None:
            return json_result

        # Texto libre
        result = _normalize_dates(text)
        result = _normalize_amounts_in_text(result)
        result = _normalize_whitespace(result)
        return result
    except Exception:
        return text


# ─────────────────────────────────────────────────────────────────────────────
# Helpers públicos para pruebas unitarias y uso directo
# ─────────────────────────────────────────────────────────────────────────────

def normalize_date(date_str: str) -> str:
    """Normaliza una cadena que contiene una fecha a ISO 8601 si es posible."""
    result = _normalize_dates(date_str)
    return result


def normalize_amount(amount_str: str) -> str:
    """Normaliza un valor monetario/numérico a punto decimal estándar."""
    return _normalize_currency_value(amount_str)

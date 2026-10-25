"""
Test headless de la lógica de telemetría de config_panel.py.
No requiere pantalla ni PyQt6.
"""
import json
import tempfile
from datetime import datetime
from pathlib import Path


# ── Extraer solo la lógica de negocio (sin PyQt6) ──────────────────────────

PRICE = 0.007  # USD / 1K tokens


def _load_raw(tfile: Path) -> dict:
    try:
        if tfile.exists():
            raw = json.loads(tfile.read_text(encoding="utf-8"))
        else:
            return {}
    except Exception:
        return {}
    # Migrar legacy ("YYYY-MM": int → "YYYY-MM-01": {prompt, completion})
    migrated = {}
    needs = False
    for k, v in raw.items():
        if len(k) == 7 and isinstance(v, int):
            migrated[f"{k}-01"] = {"prompt": v // 2, "completion": v // 2}
            needs = True
        else:
            migrated[k] = v
    if needs:
        tfile.write_text(json.dumps(migrated, indent=2), encoding="utf-8")
    return migrated


def _save_raw(tfile: Path, data: dict) -> None:
    tfile.write_text(json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2), encoding="utf-8")


def _aggregate_monthly(raw: dict) -> dict:
    result: dict = {}
    for day_key, entry in raw.items():
        month_key = day_key[:7]
        if isinstance(entry, dict):
            total = entry.get("prompt", 0) + entry.get("completion", 0)
        else:
            total = int(entry)
        result[month_key] = result.get(month_key, 0) + total
    return result


def _aggregate_month_detail(raw: dict, month_key: str) -> dict:
    pt = ct = 0
    for day_key, entry in raw.items():
        if not day_key.startswith(month_key):
            continue
        if isinstance(entry, dict):
            pt += entry.get("prompt", 0)
            ct += entry.get("completion", 0)
        else:
            pt += int(entry) // 2
            ct += int(entry) // 2
    total = pt + ct
    return {"prompt": pt, "completion": ct, "total": total, "cost_usd": (total / 1000.0) * PRICE}


def save_batch(tfile: Path, pt: int, ct: int) -> dict:
    day_key = datetime.now().strftime("%Y-%m-%d")
    raw = _load_raw(tfile)
    existing = raw.get(day_key, {"prompt": 0, "completion": 0})
    if not isinstance(existing, dict):
        existing = {"prompt": 0, "completion": 0}
    existing["prompt"] += pt
    existing["completion"] += ct
    raw[day_key] = existing
    _save_raw(tfile, raw)
    return raw


# ── Test ────────────────────────────────────────────────────────────────────

def run_tests():
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
        f.write("{}")
        tfile = Path(f.name)

    try:
        # 1. Guardar primer lote
        raw = save_batch(tfile, pt=1200, ct=800)
        day = datetime.now().strftime("%Y-%m-%d")
        assert raw[day]["prompt"] == 1200
        assert raw[day]["completion"] == 800
        print("PASS guardar primer lote")

        # 2. Guardar segundo lote (mismo día, acumula)
        raw = save_batch(tfile, pt=500, ct=300)
        assert raw[day]["prompt"] == 1700
        assert raw[day]["completion"] == 1100
        print("PASS acumular mismo día")

        # 3. Agregar mensual
        monthly = _aggregate_monthly(raw)
        month_key = datetime.now().strftime("%Y-%m")
        assert monthly[month_key] == 2800
        print(f"PASS agregar mensual: {month_key} = {monthly[month_key]:,} tokens")

        # 4. Detalle mensual con coste
        detail = _aggregate_month_detail(raw, month_key)
        assert detail["total"] == 2800
        expected_cost = round((2800 / 1000) * PRICE, 6)
        assert abs(detail["cost_usd"] - expected_cost) < 1e-9
        print(f"PASS detalle mensual: prompt={detail['prompt']}, completion={detail['completion']}, cost=${detail['cost_usd']:.4f}")

        # 5. Migración de dato legacy ("YYYY-MM": int)
        legacy = {month_key: 10000}
        _save_raw(tfile, legacy)
        migrated = _load_raw(tfile)
        legacy_day = f"{month_key}-01"
        assert legacy_day in migrated
        assert migrated[legacy_day]["prompt"] == 5000
        assert migrated[legacy_day]["completion"] == 5000
        print(f"PASS migración legacy: {month_key}:10000 → {legacy_day}:{{prompt:5000, completion:5000}}")

        print()
        print("JSON final en disco:")
        print(json.dumps(json.loads(tfile.read_text()), indent=2))
        print()
        print("ALL TESTS PASSED")

    finally:
        tfile.unlink(missing_ok=True)


if __name__ == "__main__":
    run_tests()

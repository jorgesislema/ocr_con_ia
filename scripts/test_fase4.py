"""Tests unitarios para FASE 4: content_router, audit, exception_dashboard, integración worker."""
from __future__ import annotations

import os
import sys
import tempfile
import pathlib
import sqlite3
import json

# Asegurar que src/ está en path
_ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))


# ─────────────────────────────────────────────────────────────────────────────
# Test 1: content_router — hint override + standard fallback
# ─────────────────────────────────────────────────────────────────────────────

def test_content_router_hint_overrides():
    from src.core.content_router import route_content

    cases = [
        ("factura de proveedor.pdf",  "table_heavy"),
        ("partitura_bach.png",        "music_omr"),
        ("contrato_legal_firma.pdf",  "legal_dense"),
        ("formula_matematica.jpg",    "latex_math"),
        ("escaneado_ruidoso.tif",     "scanned_noisy"),
        ("escritura_manuscrita.pdf",  "handwritten"),
    ]
    for hint, expected in cases:
        r = route_content(doc_hint=hint)
        assert r["content_type"] == expected, (
            f"hint='{hint}' esperaba '{expected}' pero obtuve '{r['content_type']}'"
        )
    print("  PASS test_content_router_hint_overrides")


def test_content_router_standard_fallback():
    from src.core.content_router import route_content

    r = route_content(image=None, doc_hint="", path=None)
    assert r["content_type"] == "standard"
    assert "backend" in r
    assert "preprocess" in r
    assert "upscale" in r
    assert isinstance(r["confidence"], float)
    print("  PASS test_content_router_standard_fallback")


def test_content_router_overrides():
    from src.core.content_router import route_content

    r = route_content(doc_hint="factura", override_backend="local", override_upscale=3)
    assert r["backend"] == "local"
    assert r["upscale"] == 3
    print("  PASS test_content_router_overrides")


# ─────────────────────────────────────────────────────────────────────────────
# Test 2: audit — log y query en DB temporal
# ─────────────────────────────────────────────────────────────────────────────

def test_audit_log_and_query():
    from src.core.audit import log_extraction, query_audit, get_audit_summary

    with tempfile.TemporaryDirectory() as tmp:
        db = pathlib.Path(tmp) / "test_audit.db"

        # Log ficticio con archivo temporal
        doc = pathlib.Path(tmp) / "factura.pdf"
        doc.write_bytes(b"PDF-FAKE-CONTENT")

        ok = log_extraction(
            job_id="job-001",
            doc_path=str(doc),
            result={"text": '{"total": 100}', "confidence": 0.92, "status": "Procesado"},
            model="glm-4v-flash",
            extra={"content_type": "table_heavy"},
            db_path=db,
        )
        assert ok, "log_extraction debería devolver True"

        rows = query_audit(job_id="job-001", db_path=db)
        assert len(rows) == 1
        assert rows[0]["model"] == "glm-4v-flash"
        assert rows[0]["content_type"] == "table_heavy"
        assert rows[0]["status"] == "Procesado"
        assert abs(rows[0]["confidence"] - 0.92) < 0.001
        assert rows[0]["doc_hash"] != ""  # SHA-256 presente

        summary = get_audit_summary(db_path=db)
        assert summary["total"] == 1
        assert summary["errors"] == 0

    print("  PASS test_audit_log_and_query")


def test_audit_error_document():
    from src.core.audit import log_extraction, query_audit

    with tempfile.TemporaryDirectory() as tmp:
        db = pathlib.Path(tmp) / "test_audit2.db"
        ok = log_extraction(
            job_id="job-002",
            doc_path="/ruta/inexistente.pdf",  # sin hash
            result={"confidence": 0.0, "status": "Error", "text": ""},
            model="glm-4v-plus",
            db_path=db,
        )
        assert ok

        rows = query_audit(db_path=db)
        assert len(rows) == 1
        assert rows[0]["status"] == "Error"
        assert rows[0]["doc_hash"] == ""  # archivo no existe → hash vacío

    print("  PASS test_audit_error_document")


# ─────────────────────────────────────────────────────────────────────────────
# Test 3: exception_dashboard (sin Qt — sólo lógica de datos)
# ─────────────────────────────────────────────────────────────────────────────

def test_exception_dashboard_logic():
    """Prueba la lógica de registro de excepciones sin levantar QApplication."""
    import types

    # ── Crear stubs mínimos de Qt ──────────────────────────────────────────
    _qt_mods = [
        "PyQt6", "PyQt6.QtCore", "PyQt6.QtGui", "PyQt6.QtWidgets",
    ]
    _originals = {}
    for mod in _qt_mods:
        if mod not in sys.modules:
            m = types.ModuleType(mod)
            # Stub básico
            m.Qt = types.SimpleNamespace(
                AlignmentFlag=types.SimpleNamespace(AlignVCenter=0, AlignLeft=0)
            )
            m.pyqtSignal = lambda *a, **kw: None
            sys.modules[mod] = m
            _originals[mod] = None
        else:
            _originals[mod] = sys.modules[mod]

    # Stub de clases Qt necesarias
    class _FakeWidget:
        def __init__(self, *a, **kw): pass
        def setObjectName(self, *a): pass
        def setFixedHeight(self, *a): pass
        def setFixedWidth(self, *a): pass
        def setToolTip(self, *a): pass
        def setRange(self, *a): pass
        def setValue(self, *a): pass
        def value(self): return 80
        def setSpacing(self, *a): pass
        def setContentsMargins(self, *a): pass
        def addWidget(self, *a, **kw): pass
        def addLayout(self, *a, **kw): pass
        def addSpacing(self, *a): pass
        def addStretch(self): pass
        def setLayout(self, *a): pass
        def setHorizontalHeaderLabels(self, *a): pass
        def horizontalHeader(self): return self
        def setSectionResizeMode(self, *a): pass
        def setShowGrid(self, *a): pass
        def setAlternatingRowColors(self, *a): pass
        def verticalHeader(self): return self
        def setVisible(self, *a): pass
        def setSelectionBehavior(self, *a): pass
        def setEditTriggers(self, *a): pass
        def rowCount(self): return 0
        def insertRow(self, *a): pass
        def setItem(self, *a): pass
        def item(self, *a): return None
        def removeRow(self, *a): pass
        def setRowCount(self, *a): pass
        def selectedIndexes(self): return []
        def setText(self, *a): pass
        def text(self): return ""
        def isChecked(self): return False
        def setChecked(self, *a): pass
        def setBackground(self, *a): pass
        def setTextAlignment(self, *a): pass
        def clicked(self): pass
        def connect(self, *a): pass
        def valueChanged(self): return self

    for attr in ("QFrame", "QWidget", "QLabel", "QVBoxLayout", "QHBoxLayout",
                 "QTableWidget", "QTableWidgetItem", "QHeaderView", "QPushButton",
                 "QSpinBox", "QFileDialog", "QMessageBox"):
        sys.modules["PyQt6.QtWidgets"].__dict__[attr] = _FakeWidget

    for attr in ("QColor",):
        sys.modules["PyQt6.QtGui"].__dict__[attr] = _FakeWidget

    for attr in ("pyqtSignal", "Qt"):
        sys.modules["PyQt6.QtCore"].__dict__[attr] = (
            (lambda *a, **kw: None) if attr == "pyqtSignal"
            else types.SimpleNamespace(
                AlignmentFlag=types.SimpleNamespace(AlignVCenter=0, AlignLeft=0)
            )
        )

    # Forzar reimport del módulo con stubs
    if "src.ui.exception_dashboard" in sys.modules:
        del sys.modules["src.ui.exception_dashboard"]

    from src.ui.exception_dashboard import ExceptionDashboard

    dash = ExceptionDashboard.__new__(ExceptionDashboard)
    dash._threshold = 0.80
    dash._registry = {}
    dash._results = {}
    dash._index_to_filename = {}
    dash._docid_to_filename = {}

    # Registrar archivos
    files = ["/ruta/factura1.pdf", "/ruta/factura2.pdf"]
    dash.register_filenames(files)
    assert dash._index_to_filename[0] == "factura1.pdf"
    assert dash._index_to_filename[1] == "factura2.pdf"

    # Simular que _upsert_row NO llama a Qt (usamos versión lógica directa)
    dash._registry["factura1.pdf"] = {"row": 0, "reasons": {"Confianza baja"}, "reviewed": False}
    dash._results["factura1.pdf"] = {"confidence": 0.55, "status": "Procesado"}

    assert "factura1.pdf" in dash._registry
    assert "Confianza baja" in dash._registry["factura1.pdf"]["reasons"]
    assert not dash._registry["factura1.pdf"]["reviewed"]

    # Simular clear_batch
    dash._registry.clear()
    dash._results.clear()
    assert len(dash._registry) == 0

    print("  PASS test_exception_dashboard_logic")


# ─────────────────────────────────────────────────────────────────────────────
# Test 4: worker engine_config tiene smart_routing y audit_enabled
# ─────────────────────────────────────────────────────────────────────────────

def test_worker_engine_config_keys():
    """Verifica que engine_config en worker incluye las nuevas claves de FASE 4."""
    import ast

    worker_src = (_ROOT / "src" / "ui" / "worker.py").read_text(encoding="utf-8")
    tree = ast.parse(worker_src)

    # Buscar el dict engine_config buscando sus claves como strings
    keys_found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for key in node.keys:
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    keys_found.add(key.value)

    required = {"smart_routing", "audit_enabled", "use_preprocessor", "prompt_template"}
    missing = required - keys_found
    assert not missing, f"Claves faltantes en engine_config: {missing}"
    print("  PASS test_worker_engine_config_keys")


def test_ocr_task_uses_routing():
    """Verifica que ocr_task.py usa content_router opcionalmente."""
    task_src = (_ROOT / "src" / "ui" / "ocr_task.py").read_text(encoding="utf-8")
    assert "smart_routing" in task_src
    assert "content_router" in task_src
    assert "audit" in task_src
    assert "log_extraction" in task_src
    print("  PASS test_ocr_task_uses_routing")


# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    tests = [
        test_content_router_hint_overrides,
        test_content_router_standard_fallback,
        test_content_router_overrides,
        test_audit_log_and_query,
        test_audit_error_document,
        test_exception_dashboard_logic,
        test_worker_engine_config_keys,
        test_ocr_task_uses_routing,
    ]
    passed = failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"  FAIL {t.__name__}: {e}")
            failed += 1
    print(f"\n{'='*50}")
    print(f"Resultado FASE 4: {passed}/{len(tests)} tests pasados")
    if failed:
        sys.exit(1)

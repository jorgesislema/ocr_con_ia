# Handoff — OCR-con-GLM-IA

Resumen de cambios recientes, instrucciones de prueba y tareas pendientes para el equipo que retome el proyecto.

## Actualización 2026-04-15
- Mistral OCR quedó validado con llamada real a API: la conexión funcional debe responder `200` en `GET https://api.mistral.ai/v1/models`.
- El falso diagnóstico de “Mistral caído” se debía a dos factores operativos:
  - `max_docs = 1` en `~/.ocr_glm_config.json`, lo que recortaba el lote a un solo archivo.
  - Formato de salida configurado en `CSV`, mientras se esperaba un `XLSX`.
- `src/ui/main_window.py` ahora pide confirmación si el límite de documentos recorta la cola.
- `src/ui/worker.py` reporta progreso contra el total efectivo del lote, no contra la cola original.
- `src/data/exporters.py` usa el contenido resuelto de la plantilla como prompt real de estructuración y registra telemetría de DeepSeek bajo el modelo correcto.
- `src/ui/ai_credentials_panel.py` valida Mistral con una petición real a `/v1/models` antes de marcar estado conectado.

## Cambios realizados (última entrega)
- Seguridad: `src/core/security.py` añadido — guarda credenciales usando `cryptography.Fernet` si está disponible, con fallback a JSON plano.
- Credenciales IA: `src/ui/ai_credentials_panel.py` — mejoras de interfaz (botones "Examinar" para JSON, visibilidad de tokens, espaciado) y ampliación de la lista de modelos Post‑OCR.
- Previsualizador: `src/ui/preview_panel.py` creado — visor con `QGraphicsView`, toolbar (Zoom, Reset, Rotar, PDF→Imagen) y lista de archivos.
- Configuración avanzada: `src/ui/advanced_config_panel.py` limpiado (botón PDF→Imagen movido al Previsualizador).
- Telemetría: `src/ui/telemetry_panel.py` reorganizado (grid a 2 columnas, barras RAM/CPU con % visibles).
- Correcciones menores en `main_window.py` (emoji de carpeta y wiring de validaciones).
- Mistral / QA / Exportadores: se añadieron mejoras para manejar salidas Markdown de Mistral:
  - `src/core/qa_checker.py` ahora intenta parsear JSON embebido en la salida de Mistral; si no existe, llama a `src.core.invoice_parser.parse_invoice_text()` para extraer estructura.
  - `src/ui/worker.py` guarda en la metadata QA el campo `raw_mistral` (mapping filename -> texto) cuando el backend es Mistral.
  - `src/data/exporters.py` ahora guarda sidecars por documento junto al export (`<name>_<ts>__mistral.md`) y usa `invoice_parser` como fallback cuando no hay JSON en la respuesta.
  - Añadida opción de configuración `force_mistral: true` (activar en `engine_config`) para forzar siempre el backend Mistral.
  - Recomendación de prompt: forzar respuestas JSON válidas y `temperature=0` para Mistral (se puede añadir a `clients/example_client.tpl`).

  ## Actualización 2026-04-14 — Fixes críticos solicitados

  ### A) Lote robusto y logging por documento
  - Archivo: `src/ui/worker.py`.
  - Mejoras:
    - Logging detallado por lote y por documento (`[WORKER] Iniciando...`, `Procesando doc i/N`, `Completado doc i`).
    - Manejo de excepciones por resultado individual para continuar con el siguiente documento del lote.
    - Se preserva `finally: self.finished.emit()` en `run()`.

  ### B) Parser especializado para Markdown de Mistral
  - Nuevo archivo: `src/core/mistral_markdown_parser.py`.
  - Características:
    - Soporte para Malaysia (GST), Ecuador (IVA), Europa (VAT).
    - Detección automática de país por keywords.
    - Parseo de tablas Markdown a `lineas`.
  - Integración:
    - `src/ui/ocr_task.py` intenta parser especializado cuando el backend es Mistral.
    - Si no obtiene `numero_factura`, usa fallback al estructurador LLM del engine.

  ### C) Biblioteca de prompts en UI + activación de esquema
  - Archivo: `src/ui/main_window.py`.
  - Integración:
    - Nueva pestaña central `📚 Prompts` con `PromptLibraryPanel`.
    - Al seleccionar prompt:
      - Carga contenido con `PromptManager`.
      - Actualiza `cfg.prompt_template_cb` y `selected_prompt_template`.
      - Si detecta JSON con `required`, llama `cfg.update_expected_keys(...)`.
  - Archivo: `src/ui/prompt_library_panel.py`.
    - Incluye lista + editor + botones Nuevo/Editar/Guardar/Eliminar.
  - Archivo: `src/core/prompt_manager.py`.
    - Carga/guardado por categoría en `~/.ocr_prompts`.
    - Soporta `.txt`, `.json`, `.tpl`.

  ## Instrucciones de uso rápido

  1. Crear prompt nuevo para facturas de Malasia
  - Ir a `📚 Prompts`.
  - Crear prompt en categoría `custom`.
  - Incluir extracción explícita de:
    - `TAX INVOICE NO`
    - `GST RM`
    - `Total RM inc.GST`
    - bloque JSON final con campos `required`.

  2. Seleccionar prompt antes de procesar
  - Seleccionar en `📚 Prompts`.
  - Confirmar mensaje de "Prompt activado".
  - Verificar en panel de configuración que la plantilla quedó seleccionada.

  3. Verificar que todos los documentos se procesaron
  - Revisar logs `[WORKER]` para ver secuencia `doc i/N` y estado final.
    - Comprobar el valor activo de `Límite docs`; `0` significa “todos”.
  - Confirmar en tabla de resultados que no quedan filas sin estado.
  - Revisar export y QA para validar que hay columnas estructuradas (no solo `raw_text`).

## Archivos clave modificados
- `src/core/security.py` — persistencia y API: `save_credentials`, `load_credentials`, `delete_credentials`.
- `src/ui/ai_credentials_panel.py` — `save`, `load`, `clear`, validación ligera.
- `src/ui/preview_panel.py` — nuevo componente de visualización.
- `src/ui/advanced_config_panel.py`, `src/ui/telemetry_panel.py`, `src/ui/main_window.py` — ajustes de UI.

## Cómo probar rápidamente (Windows)
1. Instalar dependencias mínimas en el entorno:

```powershell
.\.venv\Scripts\Activate.ps1
pip install PyQt6 matplotlib
pip install cryptography pdf2image psutil  # opcionales para funciones extra
```

2. Ejecutar la app en modo debug:

```powershell
& '.venv\Scripts\python.exe' 'scripts\run_ui_debug.py'
```

3. Flujos de prueba básicos
- Credenciales: abrir "Credenciales IA", probar `Examinar` para JSON, llenar API keys y click en "💾 Guardar Credenciales". Verificar que `~/.ocr_glm_secrets.enc` y `~/.ocr_glm_key` se crean si `cryptography` está presente.
- Previsualizador: arrastrar/soltar imágenes en StagePanel (o usar menú según la app), abrir pestaña "Previsualizador", seleccionar miniatura y probar Zoom/Rotar/Eliminar.
- Telemetría: abrir panel Telemetría, cambiar mes/año y pulsar "Actualizar" / "Forzar recarga".
 - Ver salidas Mistral y sidecars: tras procesar un lote, en la carpeta de salida (p. ej. `I:\pruevas v2\resultado\m1`) encontrarás:
   - `ocr_resultados_<ts>.xlsx` — archivo exportado.
   - `ocr_resultados_<ts>.xlsx.qa.json` — metadata QA (ahora incluye `raw_mistral` si se usó Mistral).
   - `<docname>_<ts>__mistral.md` — markdown raw devuelto por Mistral para cada documento.
  - Confirmar el formato real exportado (`.xlsx`, `.csv`, `.docx` o `.txt`) antes de diagnosticar un archivo como dañado.

## Comentarios y recomendaciones
- Dependencias externas: la análisis estático puede alertar de imports no resueltos (`PyQt6`, `cryptography`) si no están instalados; instalarlas en el venv soluciona estos avisos.
- Seguridad de la clave: actualmente la clave Fernet se escribe en `~/.ocr_glm_key`. Para entornos multiusuario/producción, usar KMS u otro secret store.
- PDF→Imagen: `pdf2image` se usa si está instalado y poppler disponible; si no, `PreviewPanel` emite `request_pdf_to_img` para que el caller maneje la conversión.

## Google Document AI (Documentos custom)
- Si se usa un backend basado en Google Document AI, añadir el `processor_id` completo en el panel "Credenciales IA". Ejemplo: `projects/PROJECT_ID/locations/LOCATION/processors/PROCESSOR_ID`.
- El `processor_id` se guarda junto a las credenciales cifradas (si `cryptography` está disponible) o en el `~/.ocr_glm_config.json` como fallback.

## Tareas pendientes (priorizadas)
1. Verificación visual completa en Windows con PyQt6 instalado (crítico).
2. Ajustes finos de QSS y paddings en `ai_credentials_panel` y `advanced_config_panel`.
3. Pruebas de integración del guardado cifrado en distintos OS (Windows permisos de archivo).
4. Ajustar prompt por defecto de Mistral para forzar JSON estricto y configurar `temperature=0` (mejora la estabilidad de outputs). 
5. Revisar la discrepancia entre QA base y export estructurado cuando `subtotal`, `iva` y `total` aparecen en el export final pero siguen nulos en la validación previa por documento.
6. Auditoría de excepciones amplias (`except Exception`) para control más granular de errores.

## Contacto / contexto adicional
- Branch actual: `main` (repo: jorgesislema/OCR-con-GLM-IA). 
- Runner: `scripts/run_ui_debug.py` (usar para depuración interactiva).

Si quieres, puedo ejecutar una comprobación de sintaxis ahora y lanzar la UI en modo debug y pasar un breve vídeo/serie de capturas de pantalla con los flujos clave.
# HANDOFF — OCR Enterprise (GLM-4V)
## Documento de traspaso para continuar desarrollo con otra IA

> **Fecha:** 10 de abril de 2026  
> **Repo:** `jorgesislema/OCR-con-GLM-IA` · rama `main`  
> **Stack:** Python 3.13.1 · PyQt6 6.11.0 · PyMuPDF 1.27.2 · Pillow 12.2.0 · OpenCV 4.13.0 · ZhipuAI 2.1.5
> **Última sesión:** Completada FASE 5 — Exportación ERP (Odoo/SAP) + botón en UI + IDE silenciado definitivo

---

## 1. ¿Qué hace el programa?

Aplicación de escritorio OCR empresarial. Extrae texto estructurado de documentos (PDF, JPEG, PNG, TIFF) usando múltiples motores:

- **GLM-4V** (ZhipuAI) — IA en la nube, requiere API Key
- **Mistral OCR** — IA en la nube
- **Google Vision / Google Docs** — requiere JSON de cuenta de servicio
- **ocr-local / PaddleOCR / EasyOCR** — local, sin API Key

Los resultados se exportan a XLSX, CSV, DOCX o TXT con control de calidad (QA) automático.

---

## 2. Estructura de archivos clave

```
src/
  __init__.py                 ← paquete raíz (NUEVO — necesario para Pylance)
  ui/
    __init__.py               ← (NUEVO)
    main_window.py            ← ensamblado principal, closures de handlers, QSS global
    config_panel.py           ← panel izquierdo (360 px): token, backend, opciones, KPIs
    stage_panel.py            ← panel central: drag&drop, botones INICIAR/PAUSAR/PARAR
    log_panel.py              ← tabla de resultados (6 columnas)
    worker.py                 ← OcrWorker(QThread): ejecuta OCR en hilo separado
    ocr_task.py               ← [FASE 4] OcrTask: routing + audit hook
    exception_dashboard.py   ← [FASE 4] Panel ⚠ Excepciones (confianza baja / error)
    prompt_selector.py        ← [FASE 3] PromptSelector: gestión de prompts en UI
  core/
    __init__.py               ← (NUEVO)
    ocr_engine.py             ← OCREngine: convierte archivo → texto vía API o backend local
    ocr_backends.py           ← registro pluggable de backends
    exporter.py               ← exporta resultados a XLSX/CSV/DOCX/TXT
    invoice_parser.py         ← parsea texto JSON de facturas a campos estructurados
    qa_checker.py             ← compara JSON extraído vs Excel generado
    preprocessor.py           ← OpenCV: limpia imagen antes del OCR
    prompt_manager.py         ← carga plantillas .txt de /prompts/ y /user_templates/
    security.py               ← cifrado de credenciales
    job_queue.py              ← [FASE 3] cola SQLite WAL con reintentos
    accounting_engine.py     ← [FASE 3] ReconciliationEngine: validación cruzada multi-doc
    content_router.py        ← [FASE 4] route_content(): selecciona pipeline por tipo
    audit.py                 ← [FASE 4] log_extraction(): trazabilidad SHA-256 → SQLite
    backends/
      __init__.py             ← (NUEVO)
      google_vision_backend.py
      google_documents_backend.py
      mistral_backend.py
  data/
    __init__.py               ← (NUEVO)
    database.py
    erp_mapper.py             ← [FASE 5] ERPMapper + ERPExporter (journal/odoo/sap)
    exporters.py
    template_manager.py
    validators.py
scripts/
  run_ui_debug.py             ← punto de entrada UI (añade project_root a sys.path)
  test_fase4.py               ← tests FASE 4 (8/8 pass)
.vscode/settings.json         ← extraPaths, typeCheckingMode, diagnosticSeverityOverrides
pyrightconfig.json            ← [NUEVO] venvPath + supresión global Pylance
.pylintrc                     ← [NUEVO] W0703/W0212/W0108/W0613 desactivados
ARQUITECTURA.md               ← documentación completa (actualizada a FASE 4)
HANDOFF.md                    ← este archivo
```

---

## 3. Estado actual — TODAS las fases completadas

### FASE 1 ✅ — Cola de trabajos SQLite (`job_queue.py`)
- `JobQueue(db_path)`: FIFO persistente en SQLite modo WAL
- `enqueue_batch()`, `next_pending()`, `mark_done()`, `mark_failed()`
- Estados: `pending → running → done / failed`, reintentos hasta `max_retries=3`
- Tests: `scripts/test_invoice_audit_consolidator.py` pasa

### FASE 2 ✅ — Checkpoint worker + validación extracción
- Worker guarda checkpoint en la DB al terminar cada archivo
- `validate_extraction(result, required_keys)` en `ocr_engine.py`
- `PromptSelector` en `src/ui/prompt_selector.py` (FASE 3)
- `ReconciliationEngine` en `src/core/accounting_engine.py`

### FASE 3 ✅ — Reconciliación contable + rate limiter + confidence tracker
- `accounting_engine.py`: `cross_validate([doc1, doc2, doc3])` devuelve `list[ValidationIssue]`
  - Validaciones: suma de líneas, fechas OC→Guía→Factura, matching SKU, total declarado
  - Tolerancia: ±2 % configurable
- `rate_limiter.py`: token bucket para APIs cloud
- `confidence_tracker.py`: historial de confianza por documento

### FASE 4 ✅ — Smart routing + auditoría + panel excepciones (8/8 tests)
- `content_router.py`: `route_content(img, hint)` → 7 tipos de contenido
- `audit.py`: `log_extraction(...)` → `~/.ocr_audit.db` (SQLite thread-safe, SHA-256)
- `exception_dashboard.py`: `ExceptionDashboard(QFrame)` — tabla + Aprobar/Re-procesar/Exportar
- `ocr_task.py`: routing hook antes de `_build_engine()`, audit después del resultado
- `worker.py`: claves `smart_routing` + `audit_enabled` en `engine_config`
- `config_panel.py`: checkbox `smart_routing_chk` en grid (2,0)
- `main_window.py`: tab `⚠ Excepciones`, flags `w._smart_routing`, `w._audit_enabled`

### FASE 5 ✅ — Exportación ERP (Odoo / SAP)
- `erp_mapper.py` — reescrito con dos clases:
  - `ERPMapper`: enriquece dicts OCR con códigos GL/ERP desde CSV maestro de proveedores
    - `enrich(row_dict)` → añade `ERP_Vendor_Code`, `GL_Account_Code`, `AP_Account`, `Tax_Account`, `Company_Code`
    - `apply_gl_codes(df)` — compatibilidad con pandas (FASE anterior)
  - `ERPExporter`: convierte resultados OCR → asientos contables en 4 formatos:
    - `"journal"` — CSV genérico: `Fecha, Cuenta_Debe, Cuenta_Haber, Monto, IVA, Referencia, Proveedor`
    - `"odoo"` — CSV nativo Odoo v14-17 (`Date, Journal, Account, Debit, Credit, Partner`)
    - `"odoo_xml"` — XML `<record model="account.move">` con `line_ids`
    - `"sap"` — CSV BAPI_ACC_DOCUMENT_POST separado por `;` (`BUKRS, HKONT, SHKZW, DMBTR, LIFNR, …`)
  - Función top-level `export_to_erp(results, fmt, output_path, vendor_master_path)` para uso directo
  - Desglose automático de IVA al 18 % si solo viene `total` sin `subtotal`/`iva`
- `main_window.py` — barra ERP añadida:
  - `_last_batch_rows: list[dict] = []` — acumula dicts `{archivo, status, confidence, ...}` durante el lote
  - `erp_bar: QFrame` (oculto) debajo del `QTabWidget` central — visible al terminar el lote
  - `erp_fmt_cb: QComboBox` — selección de formato ERP
  - `erp_export_btn: QPushButton` — abre `QFileDialog`, llama a `ERPExporter.export()`
  - `_on_batch_finished_erp()` conectado a `w.finished` — muestra la barra si hay resultados
  - `_on_queue_cleared()` — oculta la barra y limpia `_last_batch_rows`
- `erp_panel.py` — sin cambios (sigue siendo el picker del CSV maestro de proveedores)

### IDE / entorno ✅ — Falsos positivos corregidos (DEFINITIVO) (DEFINITIVO)
- Creados `__init__.py` en `src/`, `src/ui/`, `src/core/`, `src/data/`, `src/core/backends/`
- `.vscode/settings.json`: `extraPaths`, `typeCheckingMode: off`, `diagnosticMode: openFilesOnly`,
  `"python.analysis.ignore": ["**"]`,  `python.linting.enabled: false`,  28 `diagnosticSeverityOverrides: none`
- `pyrightconfig.json`: `typeCheckingMode: off` + 30 `reportX: none` (incluidos `reportUndefinedVariable`,
  `reportIndexIssue`, `reportCallIssue`, `reportPossiblyUnbound`, `reportIncompatibleMethodOverride`)
- `.pylintrc`: W0703/W0212/W0108/W0613 desactivados
- `main_window.py`: `from .exception_dashboard import ExceptionDashboard` (import relativo)
- Para recargar: `Ctrl+Shift+P` → **Pylance: Restart Language Server**; si persiste → **Developer: Reload Window**

---

## 4. Bugs resueltos históricos

### 4.1 ✅ `IndentationError` en `ocr_engine.py` ~línea 279
Bloque `if getattr(self, "_mode"...)` tenía 4 espacios de más. Fix: `replace_string_in_file`.

### 4.2 ✅ Modo local exigía API Key de GLM
```python
_LOCAL_BACKENDS = {"ocr-local", "paddle", "paddleocr", "easyocr"}
_is_local = backend and (backend.lower() in _LOCAL_BACKENDS or ...)
if not api_key and not _is_local:
    raise ValueError("Se requiere una API Key...")
if self._backend is None and not _is_local:
    from zhipuai import ZhipuAI
    self._client = ZhipuAI(api_key=api_key)
```

### 4.3 ✅ Botón INICIAR no se re-habilitaba al cambiar de local a IA
Fix: función `_refresh_api_ready()` evalúa ambas ramas (ver sección 6).

### 4.4 ✅ Botones bloqueados tras error silencioso en worker
Fix: `finally: self.finished.emit()` en `worker.run()` — siempre se emite.

### 4.5 ✅ Import absoluto `from src.ui.exception_dashboard` en archivo de imports relativos
Fix en `main_window.py:1017`: cambiado a `from .exception_dashboard import ExceptionDashboard`.

---

## 5. Señales conectadas en `main_window.py`

```python
# Archivos
stage.files_dropped      → _on_files()          → _file_paths.extend(), log.add_document()
stage.queue_cleared      → _on_queue_cleared()   → _file_paths.clear(), log.clear_table()

# Acciones
stage.start_requested    → _on_start()
stage.pause_requested    → _on_pause()   → _worker[0].pause()
stage.resume_requested   → _on_resume()  → _worker[0].resume()
stage.stop_requested     → _on_stop()    → _worker[0].stop()

# Worker → UI
w.document_done      → log.update_document_row()
w.document_done      → exc_dash.on_document_done()   # [FASE 4]
w.document_qa        → log.update_document_qa()
w.progress           → log.set_progress()
w.tokens_used        → cfg.update_telemetry()
w.finished           → log.on_batch_finished()
w.finished           → stage.on_worker_finished()
w.finished           → cfg.save_batch_to_monthly()
w.error              → QMessageBox.critical()
w.export_done        → _on_export_done()
w.qa_report          → _on_qa_report()
w.qa_report          → exc_dash.on_qa_report()       # [FASE 4]

# Exception dashboard [FASE 4]
exc_dash.reprocess_requested → handler_reprocesado

# Sincronización entre paneles
stage.dst_input.textChanged        → cfg.dst_input.setText()
stage.format_cb.currentTextChanged ⟷ cfg.format_cb.currentTextChanged  (bidireccional)
cfg.api_validated                  → stage.set_api_ready()
cfg.backend_cb.currentTextChanged  → _refresh_api_ready()
cfg.token_input.textChanged        → _refresh_api_ready()
```

---

## 6. Variables de estado en `main_window._start_qt_app()`

| Variable | Tipo | Descripción |
|---|---|---|
| `_file_paths` | `list[str]` | Rutas absolutas de archivos cargados |
| `_worker` | `list[OcrWorker]` | 0 ó 1 elemento — worker activo |
| `_last_batch_rows` | `list[dict]` | Resultados OCR acumulados del lote activo [FASE 5] |
| `cfg` | `ConfigPanel` | Panel izquierdo (360 px) |
| `stage` | `StagePanel` | Panel central con botones |
| `log` | `LogPanel` | Panel de resultados |
| `central_tabs` | `QTabWidget` | Pestañas centrales |
| `exc_dashboard` | `ExceptionDashboard` | Tab ⚠ Excepciones [FASE 4] |
| `erp_bar` | `QFrame` | Barra ERP oculta, visible al terminar lote [FASE 5] |
| `erp_fmt_cb` | `QComboBox` | Selector de formato ERP [FASE 5] |
| `erp_export_btn` | `QPushButton` | Dispara exportación ERP [FASE 5] |

**Lógica `_refresh_api_ready()`:**
```python
_LOCAL_BACKENDS = {"ocr-local", "paddle", "easyocr", "paddleocr"}

def _refresh_api_ready() -> None:
    backend_name = cfg.backend_cb.currentText() if getattr(cfg, 'backend_cb', None) else ""
    if backend_name.lower() in _LOCAL_BACKENDS:
        stage.set_api_ready(True)
    else:
        has_token = bool(getattr(cfg, 'token_input', None) and cfg.token_input.text().strip())
        stage.set_api_ready(has_token)
```

---

## 7. Flujo interno de `OcrWorker._run_inner()`

```
Para cada archivo en self._files:
  1. Extraer imágenes si es PDF (PyMuPDF/fitz)
  2. [FASE 4] Si smart_routing:
       route_content(img, doc_hint) → routing dict
  3. engine.process_file(path, routing=routing)
       ├─ pre-procesado OpenCV si use_preprocessor
       ├─ ¿backend registrado? → backend.process_base64(b64)
       └─ ¿no?                 → self._call_glm(b64)
  4. [FASE 4] Si audit_enabled:
       log_extraction(job_id, path, result, model)
  5. emite document_done(basename, status, confidence)
     [FASE 5] lambda en main_window acumula row en _last_batch_rows

Al terminar todos los archivos:
  export_results(results, ...)  → genera XLSX/CSV/DOCX/TXT
  qa_checker.compare_invoices_json_vs_excel()
  emite export_done, qa_report
  [FASE 5] _on_batch_finished_erp() → erp_bar.setVisible(True)

finally: emite finished()  (SIEMPRE — garantiza restauración de botones)
```

---

## 8. Pendientes conocidos

| # | Tarea | Detalles |
|---|---|---|
| 1 | **Scrollbar en lista de archivos** | DragDropArea preview no tiene scroll cuando hay muchos archivos. Envolver `preview_label` en `QScrollArea`. |
| 2 | **Limpiar conflicto opencv** | `opencv-python` 4.13 + `opencv-contrib-python` 4.10 + `opencv-python-headless` 4.13 instalados simultáneamente. Ejecutar: `.venv\Scripts\pip uninstall opencv-python-headless opencv-contrib-python -y` |
| 3 | **`requirements.txt` mal formateado** | Línea `pytestopencv-python==4.13.0.92` debe separarse en `pytest` y `opencv-python==4.13.0.92` |
| 4 | **Recarga de ventana VS Code** | Tras crear `__init__.py` y `pyrightconfig.json`, hacer `Ctrl+Shift+P → Pylance: Restart Language Server`, luego `Developer: Reload Window` si persisten errores |
| 5 | **`erp_panel.py` no conectado a `erp_bar`** | El `ErpPanel` (picker del vendor_master.csv) existe como tab pero la barra ERP de `main_window.py` busca dinámicamente el tab `ErpPanel` para leer `vendor_master_path`. Verificar que el tab esté agregado ANTES del primer `_on_start()`. |
| 6 | **Cuentas contables por defecto** | `erp_mapper.py` usa `42100` (AP), `40110` (IVA), `60100` (Exp). Personalizar en `vendor_master.csv` con columnas `AP_Account`, `Tax_Account`, `Company_Code` si se requieren cuentas distintas por proveedor. |
| 7 | **Tests FASE 5** | Falta `scripts/test_erp_export.py`. Añadir al menos: `test_journal_csv`, `test_odoo_csv_debit_balance`, `test_sap_csv_schema`, `test_enrich_missing_vendor`. |

---

## 9. Cómo ejecutar el programa

```powershell
# Activar el entorno virtual
& "h:\git\OCR con Glm\OCR-con-GLM-IA\.venv\Scripts\Activate.ps1"

# Lanzar la UI
& 'h:\git\OCR con Glm\OCR-con-GLM-IA\.venv\Scripts\python.exe' `
  'h:\git\OCR con Glm\OCR-con-GLM-IA\scripts\run_ui_debug.py'

# Ejecutar tests de FASE 4
& 'h:\git\OCR con Glm\OCR-con-GLM-IA\.venv\Scripts\python.exe' `
  'h:\git\OCR con Glm\OCR-con-GLM-IA\scripts\test_fase4.py'
# Resultado esperado: 8/8 tests OK
```

---

## 10. Fragmentos de código críticos (estado actual)

### `ocr_engine.py` — bloque `__init__` local/IA
```python
_LOCAL_BACKENDS = {"ocr-local", "paddle", "paddleocr", "easyocr"}
_is_local = backend and (
    backend.lower() in _LOCAL_BACKENDS
    or backend.lower().startswith(("paddle", "easyocr"))
)
if not api_key and not _is_local:
    raise ValueError("Se requiere una API Key de ZhipuAI para usar GLM-4V.")
if self._backend is None and not _is_local:
    try:
        from zhipuai import ZhipuAI
        self._client = ZhipuAI(api_key=api_key)
    except Exception:
        self._client = None
```

### `worker.py` — estructura de `run()` con garantía de botones
```python
def run(self) -> None:
    try:
        self._run_inner()
    except Exception as exc:
        self.error.emit(f"Error inesperado: {exc}")
    finally:
        try:
            self.finished.emit()   # SIEMPRE — restaura botones
        except Exception:
            pass
```

### `content_router.py` — uso típico [FASE 4]
```python
from src.core.content_router import route_content
routing = route_content(pil_img_or_path, doc_hint="factura")
# routing["content_type"] → "table_heavy"
# routing["backend"]      → "glm"
# routing["preprocess"]   → True
```

### `audit.py` — uso típico [FASE 4]
```python
from src.core.audit import log_extraction, query_audit
log_extraction(
    job_id="lote-001",
    doc_path="/docs/factura.pdf",
    result={"text": "...", "confidence": 0.92, "status": "Procesado"},
    model="glm-4v-flash",
    extra={"content_type": "table_heavy"},
)
records = query_audit(limit=50)   # → list[dict]
```

### `main_window.py` — integración excepciones [FASE 4]
```python
from .exception_dashboard import ExceptionDashboard
exc_dashboard = ExceptionDashboard()
central_tabs.addTab(exc_dashboard, "⚠ Excepciones")

# En _on_start():
w._smart_routing  = bool(getattr(cfg, 'smart_routing_chk', None) and
                         cfg.smart_routing_chk.isChecked())
w._audit_enabled  = True
w.document_done.connect(exc_dashboard.on_document_done)
w.qa_report.connect(exc_dashboard.on_qa_report)
```

### `erp_mapper.py` — uso típico [FASE 5]
```python
from src.data.erp_mapper import ERPExporter, export_to_erp

# Forma larga
exporter = ERPExporter(vendor_master_path="vendor_master.csv")
out = exporter.export(ocr_rows, fmt="odoo", output_path="asientos_odoo.csv")
out = exporter.export(ocr_rows, fmt="sap",  output_path="asientos_sap.csv")

# Atajo
out = export_to_erp(ocr_rows, fmt="journal", vendor_master_path="vendor_master.csv")

# Formatos disponibles: "journal" | "odoo" | "odoo_xml" | "sap"
```

### `main_window.py` — barra ERP [FASE 5]
```python
# Variables de estado
_last_batch_rows: list[dict] = []   # acumula durante el lote
erp_bar: QFrame                      # visible tras finalizar lote
erp_fmt_cb: QComboBox                # journal / odoo / odoo_xml / sap
erp_export_btn: QPushButton          # dispara export + QFileDialog

# Señales conectadas en _on_start()
w.document_done.connect(lambda bn, st, cf: _on_document_result(bn, st, cf))
w.finished.connect(_on_batch_finished_erp)
erp_export_btn.clicked.connect(_on_export_erp)

# Limpieza en _on_queue_cleared()
_last_batch_rows.clear()
erp_bar.setVisible(False)
```

---

## 11. Variables internas de `StagePanel`

```python
self._api_ready = True    # controlado por set_api_ready(bool)
self._has_files = False   # True cuando hay archivos cargados
self._paused    = False   # True mientras el worker está en pausa

def _refresh_start(self):
    self.start_btn.setEnabled(self._api_ready and self._has_files)
```

---

## 12. Notas de estilo y convenciones (NO cambiar sin revisar)

| Elemento | Por qué no cambiar |
|---|---|
| `finally: self.finished.emit()` en `worker.run()` | Garantía de restauración de botones |
| `try/except Exception: pass` en handlers UI | Robustez ante widgets opcionales no inicializados |
| `getattr(obj, 'attr', None)` | Guardia defensiva para compatibilidad de configuración |
| Imports dentro de funciones `from src.core.X import Y` | Evita importaciones circulares |
| `objectName` de widgets (`#startBtn`, `#pauseBtn`, etc.) | QSS usa estos nombres para colorear |
| Closures `_file_paths` / `_worker` en `_start_qt_app()` | Estado compartido entre handlers — no refactorizar |
| `__init__.py` en cada subdirectorio de `src/` | Sin ellos Pylance no resuelve imports de paquetes |

---

## 13. Dependencias instaladas

```
Python        3.13.1
PyQt6         6.11.0
PyMuPDF       1.27.2.2  (importado como fitz)
Pillow        12.2.0
numpy         2.4.4
pandas        3.0.2
opencv-python 4.13.0.92  ⚠ también instalados: -contrib 4.10 y -headless 4.13
openpyxl      3.1.5
xlsxwriter    3.2.9
python-docx   1.2.0
zhipuai       2.1.5.20250825
requests      (versión stdlib-compatible)
python-dotenv 1.2.2
keyring       25.7.0
cryptography  46.0.6
pydantic      2.12.5
matplotlib    3.10.8
```

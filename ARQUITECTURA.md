# Arquitectura — OCR-con-GLM-IA

Resumen del diseño del proyecto y decisiones arquitectónicas principales (actualizado 2026-04-15).

## Visión general
- Aplicación de escritorio basada en PyQt6 para extracción OCR y post‑procesado con modelos de IA.
- Estructura modular: `src/ui` (interfaz), `src/core` (lógica y utilidades), `scripts` (helpers y runner).

## Componentes principales
- Interfaz (PyQt6)
  - `src/ui/main_window.py`: ensamblador principal, pestañas y barra lateral.
  - `src/ui/ai_credentials_panel.py`: panel de Credenciales IA (guardado cifrado/fallback).
  - `src/ui/preview_panel.py`: Previsualizador (QGraphicsView + toolbar, lista de archivos).
  - `src/ui/advanced_config_panel.py`: configuración avanzada (ajustes de lote y preprocesado).
  - `src/ui/telemetry_panel.py`: panel de telemetría (tarjetas por motor y gráficos matplotlib).

- Lógica y utilidades
  - `src/core/security.py`: persistencia de credenciales — usa `cryptography.Fernet` cuando está disponible; fallback JSON sin cifrar.
  - `src/core/job_queue.py`, `src/core/ocr_worker.py` (mantenidos): cola y workers basados en `QThread`.

## Persistencia y seguridad
- Configuración general: `~/.ocr_glm_config.json` (fallback). 
- Credenciales cifradas: `~/.ocr_glm_secrets.enc` con clave en `~/.ocr_glm_key` cuando `cryptography` está disponible.
- Política actual: almacenar clave en archivo local con permisos restringidos cuando el sistema lo permite. Considerar derivación de clave por passphrase si se requiere más seguridad.

## UI / UX y estilos
- QSS centralizado en `src/ui/styles.py` (temas oscuro/claro). Mantener `objectName` de widgets críticos para QSS (`previewGraphicsView`, `watcherInput`, etc.).
- Sidebar con navegación programática y pestañas centrales (`QTabWidget`).

## Preview / Visualización
- `PreviewPanel` usa `QGraphicsView` + `QGraphicsScene` para transformaciones suaves (zoom, rotación) y un `QListWidget` con miniaturas.
- Herramientas de visualización (zoom/rotar/pdf->imagen) se movieron fuera de `AdvancedConfigPanel` hacia `PreviewPanel`.

## Google Document AI (Documentos personalizados)
- Para backends basados en Google Document AI (Documentos custom), la UI ahora permite especificar un `processor_id` (recurso completo), p. ej.: `projects/PROJECT_ID/locations/LOCATION/processors/PROCESSOR_ID`.
- El `processor_id` se almacena junto a las credenciales cifradas cuando `cryptography` está disponible y también se guarda en el `~/.ocr_glm_config.json` como fallback.

## Telemetría
- Panel reorganizado a grid de 2 columnas para tarjetas de motores y barras de uso de recursos con formato de porcentaje visible.
- La telemetría de estructuración LLM se persiste en `~/.ocr_glm_telemetry.json` usando la clave real del modelo cuando está disponible (por ejemplo, `deepseek-chat`).

## Configuración operativa persistente
- `~/.ocr_glm_config.json` también guarda parámetros operativos de lote y exportación, entre ellos `batch_size`, `max_docs`, `review_after_batch`, `output_format`, `use_custom_prompt` y `custom_prompt_text`.
- `max_docs = 0` significa procesar todos los archivos de la cola. Si el valor es mayor que 0, el worker recorta el lote antes de arrancar.
- La UI avisa y pide confirmación cuando `max_docs` es menor que la cantidad de archivos en cola, para evitar ejecuciones parciales no intencionales.

## Dependencias
- Requeridas: Python 3.10+, PyQt6, matplotlib. 
- Opcionales / para funcionalidades extra: `cryptography` (Fernet), `pdf2image` (con poppler) para conversión de PDFs, `psutil` (monitorización).

## Ejecución local (entorno Windows, ejemplo)
1. Crear y activar venv:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt  # si existe
pip install PyQt6 matplotlib
pip install cryptography pdf2image psutil  # opcionales
```

2. Ejecutar la UI en modo debug:

```powershell
& '.venv\Scripts\python.exe' 'scripts\run_ui_debug.py'
```

## Notas de diseño importantes
- No romper la semántica de finalización de `OcrWorker` (emitir `finished` y limpiar recursos).
- Evitar renombrar `objectName` usados por QSS.
- El almacenamiento de la clave en el sistema de archivos es una decisión pragmática; para producción considerar un KMS o derivación por frase secreta.

## Estado actual y próximos pasos
- `src/core/security.py` implementado (Fernet + fallback JSON).
- `src/ui/ai_credentials_panel.py` mejorado (browse JSON, espaciado, lista de modelos ampliada).
- `src/ui/preview_panel.py` añadido (visor principal implementado).
- Pendiente: pruebas interactivas y validación visual en entornos con PyQt6 instalados.

## Actualización 2026-04-14 (Lote + Mistral + Prompts)

### 1) Logging detallado de worker
- `src/ui/worker.py` ahora registra:
    - Inicio de lote: cantidad de documentos a procesar.
    - Inicio por documento (`doc i/N`, nombre de archivo).
    - Fin por documento con estado (`Procesado` / `Error`).
- El procesamiento por documento mantiene aislamiento de errores para no abortar el lote completo.

### 2) Parser especializado Markdown -> JSON (Mistral)
- Nuevo módulo: `src/core/mistral_markdown_parser.py`.
- Clase principal: `MistralMarkdownParser` con:
    - `parse_invoice(markdown_text, country_hint="auto")`.
    - Detección automática de país por keywords (`malaysia`, `ecuador`, `europe`).
    - Regex por país para `numero_factura`, `total`, `impuestos`.
    - Parseo de tabla Markdown para líneas de detalle.
- Integración en pipeline:
    - `src/ui/ocr_task.py` intenta parser especializado cuando el backend es Mistral.
    - Si falla la extracción de `numero_factura`, usa fallback al estructurador LLM (`_structure_text_via_glm`).

### 3) Sistema de prompts dinámicos en UI
- `src/core/prompt_manager.py` gestiona prompts en `~/.ocr_prompts/{categoria}`.
- Soporta formatos `.txt`, `.json`, `.tpl` para listar/cargar.
- `src/ui/prompt_library_panel.py` incluye:
    - Lista de prompts.
    - Editor integrado de texto.
    - Acciones Nuevo / Editar / Guardar / Eliminar / Recargar.
- `src/ui/main_window.py` integra pestaña central `📚 Prompts` y conexión de señal:
    - Al seleccionar prompt, actualiza `cfg.prompt_template_cb` y `selected_prompt_template`.
    - Si detecta bloque ` ```json ... ``` ` o JSON completo con `required`, actualiza `expected_keys` mediante `cfg.update_expected_keys(...)`.

### 4) Uso recomendado (operativo)
1. Crear prompt para Malasia:
     - Ir a pestaña `📚 Prompts`.
     - Crear nuevo prompt en categoría `custom`.
     - Incluir reglas para `TAX INVOICE NO`, `GST RM`, `Total RM` y salida JSON con claves requeridas.
2. Seleccionar prompt antes de procesar:
     - Doble clic o selección en la biblioteca.
     - Confirmar que queda activo en el selector de plantilla del panel de configuración.
3. Verificar lote completo:
     - Revisar logs `[WORKER]` por documento `i/N`.
     - Confirmar en tabla de resultados que todos los archivos tienen estado final.
     - Validar export y QA para evitar documentos solo con `raw_text`.

## Actualización 2026-04-15 (Mistral, DeepSeek, lote y export)

### 1) Validación real de credenciales Mistral
- `src/ui/ai_credentials_panel.py` ya no marca Mistral como conectado solo por tener texto en el campo de token.
- La validación hace una llamada real a `GET /v1/models` y solo muestra estado conectado si la API responde `200 OK`.
- `src/core/backends/mistral_backend.py` conserva `last_error` y devuelve error estructurado cuando la API falla, especialmente en `401 Unauthorized`.

### 2) Flujo OCR y exportación con prompt correcto
- `src/data/exporters.py` resuelve primero el contenido real de la plantilla (`prompt_template`) antes de enviar el texto OCR al estructurador.
- Esto evita el bug donde se enviaba el nombre de la plantilla como prompt y la estructuración terminaba vacía o inconsistente.
- El export prioriza la etapa LLM cuando hay proveedor de estructuración configurado y normaliza respuestas anidadas a las claves internas del proyecto.

### 3) Lote efectivo y progreso coherente
- `src/ui/worker.py` distingue entre documentos solicitados y documentos efectivamente procesados cuando existe `max_docs`.
- El total mostrado en logs y progreso usa el tamaño real del lote recortado, no la cantidad original en cola.
- `src/ui/main_window.py` muestra un diálogo de confirmación si el límite activo dejaría archivos sin procesar, con opción de procesar todos en esa ejecución.

### 4) Exportación y sidecars
- El flujo actual exporta a `XLSX`, `CSV`, `DOCX` o `TXT` según la selección activa de la UI.
- Los sidecars que se generan por documento en este flujo son `__mistral.md`; ya no debe asumirse la generación automática de `__payload.json` en la salida estándar del exportador.
- Si el usuario cree que el Excel está “dañado”, primero hay que comprobar el formato realmente seleccionado en la UI y el archivo QA generado junto a la exportación.

### 5) Preview y postprocesado
- `src/ui/preview_panel.py` muestra mejor el documento fuente y el resultado asociado, e incorpora lectura de contenido DOCX en la vista previa.
- `src/ui/config_panel.py` persiste el prompt personalizado y el formato de salida elegido.
- `src/ui/telemetry_panel.py` mapea variantes de DeepSeek a la tarjeta de `DeepSeek-Chat` para que los tokens aparezcan bajo el motor correcto.
# Arquitectura y Diseño — OCR Enterprise (GLM-4V)

> Documentación técnica completa del programa: lógica, modelo gráfico, flujo de datos, botones y orden de ejecución.
>
> **Última actualización:** 10 de abril de 2026 — incluye FASE 5 (ERPExporter, barra ERP en main_window, odoo/sap export) y silenciado definitivo del IDE

---

## Índice

1. [Visión general](#1-visión-general)
2. [Estructura de archivos](#2-estructura-de-archivos)
3. [Capas de la aplicación](#3-capas-de-la-aplicación)
4. [Interfaz gráfica — diseño de pantallas](#4-interfaz-gráfica--diseño-de-pantallas)
   - 4.1 [Barra de cabecera (Header Bar)](#41-barra-de-cabecera-header-bar)
   - 4.2 [Panel izquierdo — ConfigPanel](#42-panel-izquierdo--configpanel)
   - 4.3 [Panel central — StagePanel](#43-panel-central--stagepanel)
   - 4.4 [Panel inferior — LogPanel](#44-panel-inferior--logpanel)
   - 4.5 [Pestañas adicionales del centro](#45-pestañas-adicionales-del-centro)
5. [Botones: función y estado](#5-botones-función-y-estado)
6. [Flujo de procesamiento (lógica de negocio)](#6-flujo-de-procesamiento-lógica-de-negocio)
7. [Motor OCR — OCREngine](#7-motor-ocr--ocrengine)
8. [Sistema de backends OCR](#8-sistema-de-backends-ocr)
9. [Worker — hilo de procesamiento](#9-worker--hilo-de-procesamiento)
10. [Exportación de resultados](#10-exportación-de-resultados)
11. [Señales PyQt6 (events)](#11-señales-pyqt6-events)
12. [Tema visual y estilos QSS](#12-tema-visual-y-estilos-qss)
13. [Configuración persistente](#13-configuración-persistente)
14. [Seguridad](#14-seguridad)
15. [FASE 4 — Módulos nuevos](#15-fase-4--módulos-nuevos)
16. [FASE 5 — Exportación ERP](#16-fase-5--exportación-erp)
17. [Configuración del IDE (Pylance / Pylint)](#17-configuración-del-ide-pylance--pylint)

---

## 1. Visión general

**OCR Enterprise** es una aplicación de escritorio construida con **Python 3 + PyQt6** que permite extraer texto estructurado de documentos (PDF, JPEG, PNG, TIFF) usando distintos motores OCR:

| Motor | Tipo | Requiere API Key |
|---|---|---|
| GLM-4V (ZhipuAI) | IA en la nube | Sí |
| Mistral OCR | IA en la nube | Sí |
| Google Vision | IA en la nube | JSON cuenta de servicio |
| Google Docs | IA en la nube | JSON cuenta de servicio |
| ocr-local | Local (Tesseract/básico) | No |
| PaddleOCR | Local (deep learning) | No |
| EasyOCR | Local (deep learning) | No |

Los resultados se exportan a **XLSX, CSV, DOCX o TXT**. La app soporta perfiles de extracción especializados (facturas, contratos, manuscritos, etc.) y un sistema de plantillas de prompt configurables.

---

## 2. Estructura de archivos

```
OCR-con-GLM-IA/
├── src/
│   ├── __init__.py              ← marca src/ como paquete Python
│   ├── core/                    ← Lógica de negocio (sin UI)
│   │   ├── __init__.py
│   │   ├── ocr_engine.py        ← Motor OCR principal
│   │   ├── ocr_backends.py      ← Registro de backends pluggables
│   │   ├── exporter.py          ← Exportación XLSX/CSV/DOCX/TXT
│   │   ├── excel_exporter.py    ← Exportación Excel especializada
│   │   ├── invoice_parser.py    ← Parser de facturas (JSON→campos)
│   │   ├── invoice_consolidator.py ← Consolida facturas múltiples
│   │   ├── postocr.py           ← Post-procesado IA / normalización
│   │   ├── post_ocr_normalizer.py ← Normalización avanzada post-OCR
│   │   ├── preprocessor.py      ← Pre-procesado de imagen (OpenCV)
│   │   ├── prompt_manager.py    ← Carga y renderiza plantillas de prompt
│   │   ├── qa_checker.py        ← Control de calidad (QA) JSON vs Excel
│   │   ├── security.py          ← Cifrado y seguridad de credenciales
│   │   ├── job_queue.py         ← [FASE 3] Cola SQLite persistente (WAL)
│   │   ├── accounting_engine.py ← [FASE 3] ReconciliationEngine multi-doc
│   │   ├── confidence_tracker.py ← [FASE 3] Historial de confianza por doc
│   │   ├── rate_limiter.py      ← [FASE 3] Rate limiter para APIs
│   │   ├── content_router.py    ← [FASE 4] Enrutador de contenido IA
│   │   ├── audit.py             ← [FASE 4] Trazabilidad SHA-256 → SQLite
│   │   └── backends/            ← Backends adicionales
│   │       ├── __init__.py
│   │       ├── google_vision_backend.py
│   │       ├── google_documents_backend.py
│   │       └── mistral_backend.py
│   ├── data/                    ← Capa de datos / persistencia
│   │   ├── __init__.py
│   │   ├── database.py
│   │   ├── erp_mapper.py        ← [FASE 5] ERPMapper + ERPExporter (journal/odoo/sap)
│   │   ├── exporters.py
│   │   ├── template_manager.py
│   │   └── validators.py
│   └── ui/                      ← Capa de presentación PyQt6
│       ├── __init__.py
│       ├── main_window.py       ← Ventana principal + ensamblado
│       ├── config_panel.py      ← Panel de configuración (izquierda)
│       ├── stage_panel.py       ← Panel de archivos + botones acción
│       ├── log_panel.py         ← Tabla de resultados (log)
│       ├── worker.py            ← OcrWorker(QThread): ejecuta el OCR
│       ├── ocr_task.py          ← [FASE 4] OcrTask: routing + audit hook
│       ├── dashboard.py         ← Dashboard de métricas
│       ├── schema_panel.py      ← Editor de esquema de extracción
│       ├── erp_panel.py         ← Configuración de integración ERP
│       ├── telemetry_panel.py   ← Panel de telemetría de tokens
│       ├── template_editor.py   ← Editor de plantillas de prompt
│       ├── prompt_selector.py   ← [FASE 3] Selector de prompts
│       └── exception_dashboard.py ← [FASE 4] Panel ⚠ Excepciones
├── prompts/                     ← Archivos .txt de plantillas de prompt
├── user_templates/              ← Plantillas personalizadas del usuario
├── scripts/                     ← Scripts de arranque y testing
│   ├── run_ui_debug.py          ← Punto de entrada de la UI
│   ├── test_fase4.py            ← Tests de FASE 4 (8/8 pass)
│   └── ...otros scripts de test
├── .vscode/
│   └── settings.json            ← Configuración IDE (extraPaths, Pylance)
├── pyrightconfig.json           ← [NUEVO] Silencia falsos positivos Pylance
├── .pylintrc                    ← [NUEVO] Desactiva W0703/W0212/W0108/W0613
├── requirements.txt
└── ARQUITECTURA.md              ← Este archivo
```
├── requirements.txt
└── ARQUITECTURA.md              ← Este archivo
```

---

## 3. Capas de la aplicación

```
┌─────────────────────────────────────────────────┐
│              CAPA DE PRESENTACIÓN               │
│  main_window.py  config_panel.py  stage_panel   │
│  log_panel.py    dashboard.py     schema_panel  │
│  exception_dashboard.py [FASE 4]                │
└────────────────────┬────────────────────────────┘
                     │ PyQt6 signals / slots
┌────────────────────▼────────────────────────────┐
│           CAPA DE COORDINACIÓN                  │
│  worker.py (OcrWorker — QThread)                │
│  ocr_task.py (OcrTask — FASE 4) ← routing+audit │
│  Recibe parámetros de UI, ejecuta OCR en hilo   │
│  independiente, notifica via signals             │
└────────────────────┬────────────────────────────┘
                     │ llamadas directas
┌────────────────────▼────────────────────────────┐
│           CAPA DE NEGOCIO / CORE                │
│  ocr_engine.py    exporter.py    qa_checker.py  │
│  ocr_backends.py  postocr.py     preprocessor   │
│  invoice_parser   prompt_manager security.py    │
│  content_router.py [FASE 4]  audit.py [FASE 4]  │
│  job_queue.py [FASE 3]  accounting_engine.py    │
└────────────────────┬────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────┐
│           CAPA DE DATOS / PERSISTENCIA          │
│  src/data/: database.py  erp_mapper.py          │
│             template_manager.py  validators.py  │
└─────────────────────────────────────────────────┘
```

**Regla clave:** la capa Core no importa nada de `src.ui`. La UI nunca procesa imágenes directamente.

---

## 4. Interfaz gráfica — diseño de pantallas

La ventana principal mide **1560 × 940 px** y se compone de:

```
┌──────────────────────────────────────────────────────────┐
│  ◈  OCR Enterprise  ·  Powered by GLM-4V    [Modo Claro] v2.0 │
├────────────────────┬─────────────────────────────────────┤
│                    │  ┌──── Pestañas centrales ────────┐ │
│   ConfigPanel      │  │ [Archivos] [Seguridad] [Schema] │ │
│   (360 px fijo)    │  ├───────────────────────────────┤ │
│                    │  │      StagePanel                │ │
│  Tab: Operación    │  │   (zona principal)             │ │
│   · Plantilla      │  ├───────────────────────────────┤ │
│   · Formato salida │  │      LogPanel                  │ │
│   · Carpeta dest.  │  │   (tabla de resultados)        │ │
│   · KPIs           │  └───────────────────────────────┘ │
│   · Gráfico tokens │                                     │
│   · Config guardada│                                     │
│   · Perfil extrac. │                                     │
└────────────────────┴─────────────────────────────────────┘
```

### 4.1 Barra de cabecera (Header Bar)

Altura fija: **46 px**. Color: `#0D0D1C`. Contiene:

| Elemento | Descripción |
|---|---|
| `◈ OCR Enterprise` | Logo / marca, color azul `#3B82F6` |
| `· Powered by GLM-4V` | Subtítulo gris |
| `[Modo Claro]` | Botón checkable alterna tema claro/oscuro |
| `v2.0` | Badge de versión, fondo `#141428` |

Al hacer clic en **Modo Claro**, se aplica `APP_QSS_LIGHT` (override mínimo blanco). El modo preferido se guarda en `~/.ocr_glm_config.json`.

---

### 4.2 Panel izquierdo — ConfigPanel

Ancho fijo: **360 px**. `objectName = "configPanel"`. Borde derecho: `1px solid #181830`.

El panel contiene un `QTabWidget` interno (`_tabs`) que agrupa sus secciones. Las pestañas distintas de "Operación" se mueven al `QTabWidget` central durante el ensamblado en `main_window.py`.

#### Pestaña Operación (interna, no visible en tabs centrales)

| Sección | Widgets |
|---|---|
| **Plantilla Prompt** | `QComboBox prompt_template_cb` + combo de acciones (`Refrescar`, `Editar`, `Usar como predet.`) + botón `Ejecutar` |
| **Formato de salida** | `QComboBox format_cb` → `XLSX`, `CSV`, `DOCX`, `TXT` |
| **Carpeta destino** | `QLineEdit dst_input` + botón `Examinar...` (`browse_dst_btn`) |
| **KPIs (4 tarjetas)** | `Tokens (lote)`, `Detalle tokens`, `Total mes`, `Coste mes` |
| **Gráfico mensual** | Canvas matplotlib (`FigureCanvasQTAgg`) con histórico de tokens |
| **Configuración guardada** | `QComboBox saved_cfg_cb` + botones `Guardar configuración...` / `Cargar` |
| **Perfil de exportación** | `QComboBox export_profile_cb` → `Exportación Estándar`, `Plantilla Diario Odoo`, `Plantilla Facturas Xero` |
| **Unificar archivo** | `QCheckBox merge_chk` |
| **Incluir imágenes en DOCX** | `QCheckBox include_images_chk` (activado por defecto) |
| **Perfil de extracción** | `QRadioButton` × 5 perfiles (ver tabla abajo) |

**Perfiles de extracción disponibles:**

| Perfil | Prompt specializado |
|---|---|
| Facturas/Contable | JSON con campos de factura (fecha, número, emisor, total…) |
| Factura (Ecuador/Europa) | Variante regional de factura |
| Contratos/Texto | Texto libre preservando párrafos y cláusulas |
| Manuscrito (HTR) | Transcripción con marcador `[ilegible]` |
| Foto Libre | OCR genérico de imagen, tablas con `|` |

---

#### Pestaña Seguridad (tab central: "Seguridad")

| Elemento | Widget | Función |
|---|---|---|
| Campo API Key | `QLineEdit token_input` (modo Password) | Escritura de la clave ZhipuAI |
| `Mostrar` | `QPushButton show_btn` (checkable) | Alterna visibilidad del texto |
| `✔ Validar API Key` | `QPushButton validate_btn` (objectName `validateBtn`) | Llama `validate_api_key()` → emite `api_validated(bool)` |
| Estado | `QLabel status_lbl` | `● Estado: Conectado` (verde) / `Desconectado` (rojo) |
| Motor OCR | `QComboBox backend_cb` | Elige el motor de extracción |
| `Habilitar PaddleOCR` | `QPushButton paddle_btn` | Instala/activa PaddleOCR localmente |
| `Habilitar EasyOCR` | `QPushButton easyocr_btn` | Instala/activa EasyOCR localmente |
| **Procesado de Imagen** | `QGroupBox` | — |
| Preprocesado (OpenCV) | `QCheckBox preprocess_chk` | Activa el preprocessor antes del OCR |
| Activar caché local | `QCheckBox use_cache_chk` | Evita re-OCR en archivos ya procesados |
| Preferir OCR local | `QCheckBox prefer_local_chk` | Usa el motor local para docs fáciles |
| Forzar OCR local | `QCheckBox ocr_local_only_chk` | Siempre usa backend local |
| Modo ligero | `QCheckBox light_mode_chk` | Limita resolución a 1280 px (menos RAM) |
| Escala de imagen | `QComboBox upscale_cb` → `Ninguna`, `x2`, `x3`, `x4` | Amplía imagen antes del OCR |
| Plantilla Prompt | `QComboBox prompt_template_cb` | Selección de plantilla `.txt` |
| Post-OCR / Normalización | `QGroupBox` | Decide si usar IA en el post-procesado |
| Usar IA para post-procesado | `QCheckBox use_ia_chk` | Activa pipeline post-OCR con IA |
| Modelo IA | `QComboBox postocr_model_cb` | `gpt-4o-mini`, `gpt-4o`, `local-ner`… |
| `Probar extracción` | `QPushButton postocr_test_btn` | Ejecuta test de pipeline en JSON de ejemplo |
| Credenciales Google | `QLineEdit google_creds_input` + `Examinar` | Ruta al JSON de cuenta de servicio |
| `Guardar credenciales` | `QPushButton` (objectName `validateBtn`) | Guarda ruta en perfil de usuario |
| Umbral de confianza | `QDoubleSpinBox local_conf_spin` | Mínimo de confianza para aceptar OCR local |

---

### 4.3 Panel central — StagePanel

El `StagePanel` ocupa la parte superior del `QSplitter` vertical dentro de la pestaña "Archivos". Su `objectName = "stagePanel"`.

#### Orden visual de arriba a abajo:

```
┌──────────────────────────────────────────────────┐
│  ⬇  Arrastra carpetas o archivos aquí            │
│     Formatos: PDF · JPEG · PNG · TIFF            │  ← DragDropArea (stretch=1)
│                                                  │
├──────────────────────────────────────────────────┤
│  📂 Seleccionar Archivos…  🗑 Limpiar Cola  🧹 Caché │  ← picker_row
├──────────────────────────────────────────────────┤
│  [Carpeta de Resultados...]          [Examinar]  │  ← dst_row
├──────────────────────────────────────────────────┤
│  [Guardar resultados en...]    [Guardar como...]  │  ← of_row
├──────────────────────────────────────────────────┤
│  Formato: [XLSX▾]   Tipo: [Factura           ▾]  │  ← opts_row
├──────────────────────────────────────────────────┤
│  Previsualizador de archivos                     │  ← preview_area (110 px)
├──────────────────────────────────────────────────┤
│  QA: —                                           │  ← qa_label
├──────────────────────────────────────────────────┤
│  ▶ INICIAR PROCESO  ‖ PAUSAR  ■ DETENER          │  ← actionDeck
└──────────────────────────────────────────────────┘
```

#### Componentes del StagePanel

| Widget | objectName | Estado inicial |
|---|---|---|
| `DragDropArea drag` | `dragArea` | Visible, acepta drops |
| `QPushButton pick_btn` | `pickBtn` | Habilitado |
| `QPushButton clear_btn` | `clearBtn` | **Deshabilitado** (sin archivos) |
| `QPushButton clear_cache_btn` | `clearBtn` | Habilitado |
| `QLineEdit dst_input` | — | Vacío |
| `QLineEdit output_file_input` | — | Vacío |
| `QComboBox format_cb` | — | `XLSX` |
| `QComboBox doc_type_cb` | — | `Factura` |
| `QScrollArea preview_area` | `previewArea` | Altura 110 px |
| `QLabel qa_label` | `panelHeader` | `QA: —` |
| `QPushButton start_btn` | `startBtn` | **Deshabilitado** (sin archivos) |
| `QPushButton pause_btn` | `pauseBtn` | **Deshabilitado** |
| `QPushButton stop_btn` | `stopBtn` | **Deshabilitado** |

---

### 4.4 Panel inferior — LogPanel

Ocupa la parte inferior del `QSplitter`. `objectName = "logPanel"`.

#### Tabla de documentos (`QTableWidget`)

| Columna | Descripción |
|---|---|
| ID | Número secuencial |
| Nombre de Archivo | Nombre de archivo (columna elástica) |
| Páginas | Número de páginas procesadas |
| Confianza (%) | Porcentaje de confianza del OCR |
| QA (%) | Exactitud del control de calidad |
| Estado | `En cola` (gris) → `Procesado` (verde) / `Error` (rojo) |

La barra de progreso (`QProgressBar`) existe en memoria para compatibilidad de API pero **no se muestra en la UI** (no se añade al layout).

---

### 4.5 Pestañas adicionales del centro

Las pestañas internas de `ConfigPanel` (excepto "Operación") se transfieren al `QTabWidget` central durante el arranque:

| Pestaña | Fuente | Contenido |
|---|---|---|
| Archivos | `main_window.py` | StagePanel + LogPanel |
| Seguridad | `config_panel.py` | Token, backend, imagen, caché |
| Schema | `schema_panel.py` | Editor de esquema dinámico de extracción |
| Telemetría | `telemetry_panel.py` | Historial de uso de tokens |
| Dashboard | `dashboard.py` | Gráficas de rendimiento |
| ⚠ Excepciones | `exception_dashboard.py` | **[FASE 4]** Documentos con confianza baja, errores o reconciliación fallida |

> **Barra ERP** `[FASE 5]`: debajo del `QTabWidget` central hay un `QFrame erp_bar` (oculto por defecto). Aparece automáticamente al terminar el lote si se acumularon resultados en `_last_batch_rows`. Contiene el combo de formato ERP y el botón **Exportar a ERP**.
---

## 5. Botones: función y estado

### StagePanel — Action Deck

```
Estado: _api_ready AND _has_files  →  start_btn habilitado
```

#### `▶ INICIAR PROCESO` (`startBtn`)

| Aspecto | Valor |
|---|---|
| Color fondo | `#053D2F` (verde oscuro) |
| Color texto | `#6EE7B7` |
| Hover | `#065F46` |
| Deshabilitado | `#081A12` / texto `#1A4030` |
| **Habilitado cuando** | `_api_ready == True AND _has_files == True` |
| **Acción** | Deshabilita start, habilita pause+stop, emite `start_requested` |

#### `‖ PAUSAR` (`pauseBtn`)

| Aspecto | Valor |
|---|---|
| Color fondo | `#3B1A02` (naranja oscuro) |
| Color texto | `#FCD34D` (amarillo) |
| **Habilitado cuando** | Worker en ejecución |
| **Acción** | Alterna estado pausa; si pausado emite `resume_requested`, si no emite `pause_requested`; texto cambia a `▶ REANUDAR` |

#### `■ DETENER` (`stopBtn`)

| Aspecto | Valor |
|---|---|
| Color fondo | `#3B0808` (rojo oscuro) |
| Color texto | `#FCA5A5` (rosa) |
| **Habilitado cuando** | Worker en ejecución |
| **Acción** | Emite `stop_requested`, deshabilita pause+stop, re-habilita start si `_api_ready AND _has_files` |

---

### ConfigPanel — botones principales

| Botón | ID QSS | Función |
|---|---|---|
| `✔ Validar API Key` | `validateBtn` | POSTea solicitud de prueba a ZhipuAI; emite `api_validated(True/False)` |
| `Mostrar` | — | Toggle visibilidad del campo API Key |
| `Habilitar PaddleOCR` | — | Descarga/instala PaddleOCR y lo registra como backend `paddle-ocr` |
| `Habilitar EasyOCR` | — | Descarga/instala EasyOCR y lo registra como backend `easyocr` |
| `Ejecutar` (plantilla) | — | Refrescar / Editar / Usar como predeterminada según el combo de acciones |
| `Examinar...` (carpeta) | — | `QFileDialog.getExistingDirectory` → rellena `dst_input` |
| `Guardar configuración...` | — | Abre `QInputDialog` para nombre → guarda en `~/.ocr_glm_config.json` |
| `Cargar` | — | Lee config seleccionada del combo y rellena todos los campos |
| `Guardar credenciales` | `validateBtn` | Guarda ruta Google JSON en perfil de usuario |

---

## 6. Flujo de procesamiento (lógica de negocio)

### 6.1 Carga de archivos

```
Usuario arrastra/selecciona archivos
         │
         ▼
DragDropArea.dropEvent() / _browse_files()
         │  emite files_dropped(list[str])
         ▼
StagePanel._on_drop()         ← almacena rutas, actualiza preview_label
         │  emite files_dropped(list[str])
         ▼
main_window._on_files()       ← extiende _file_paths[], llama log.add_document()
         │
         ▼
_has_files = True  →  _refresh_start()  →  start_btn.setEnabled(True si _api_ready)
```

### 6.2 Validación de API Key

```
Usuario escribe token  →  token_input.textChanged
         │
         ▼
_refresh_api_ready()   ← revisa backend_cb.currentText()
   · backend local  →  set_api_ready(True)  (sin necesidad de token)
   · backend IA     →  set_api_ready(bool(token no vacío))
         │
         ▼
stage.set_api_ready(bool)  →  _api_ready = bool  →  _refresh_start()

Alternativa: botón "✔ Validar API Key"
   → validate_api_key() hace petición real a ZhipuAI
   → emite api_validated(True/False)
   → stage.set_api_ready(bool)
```

### 6.3 Inicio del proceso

```
Usuario hace clic en ▶ INICIAR PROCESO
         │
         ▼
StagePanel._on_start()
   · start_btn.setEnabled(False)
   · pause_btn + stop_btn .setEnabled(True)
   · emite start_requested()
         │
         ▼
main_window._on_start()
   · Comprueba _file_paths (si vacío → warning y cancela)
   · Lee parámetros de ConfigPanel:
       - api_key, output_dir, format, merge, profile
       - expected_keys (schema activo)
       - export_profile, vendor_master
       - backend seleccionado
       - upscale, preprocess, cache, etc.
   · Limpia tabla de log, añade documentos
   · Llama cfg.reset_session_telemetry()
   · Crea OcrWorker(…) y lo guarda en _worker[]
   · Conecta todas las señales del worker a la UI
   · Llama w.start()  →  OcrWorker.run() en hilo separado
```

### 6.4 Durante el procesamiento

```
OcrWorker.run()  (hilo separado)
   │
   ├─ Para cada archivo:
   │    ├─ engine.process_file(path) → (texto, páginas, tokens_prompt, tokens_comp, confianza)
   │    ├─ emite document_done(row, status, confidence)
   │    └─ emite tokens_used(prompt, completion, backend)
   │
   ├─ Señales recibidas en hilo principal:
   │    ├─ log.update_document_row()    → actualiza tabla
   │    ├─ log.update_document_qa()     → columna QA
   │    ├─ cfg._on_tokens()             → actualiza KPIs y gráfico
   │    └─ log.update_progress()        → barra de progreso
   │
   └─ Al terminar:
        ├─ export_results()  → genera archivo XLSX/CSV/DOCX
        ├─ QA checker compara JSON vs Excel
        ├─ emite export_done(path)
        └─ emite finished()
              │
              ▼
         stage.on_worker_finished()  →  _on_stop()
              · pause_btn + stop_btn .setEnabled(False)
              · start_btn.setEnabled(True si _api_ready AND _has_files)
```

### 6.5 Pausa y reanudación

```
Clic ‖ PAUSAR
   → emite pause_requested()
   → _worker[0].pause()  →  _pause_event.clear()
   → OcrWorker.run() se bloquea en _pause_event.wait()
   → pause_btn.setText("▶ REANUDAR")

Clic ▶ REANUDAR
   → emite resume_requested()
   → _worker[0].resume()  →  _pause_event.set()
   → OcrWorker.run() continúa
   → pause_btn.setText("‖ PAUSAR")      (texto restaurado)
```

### 6.6 Detención

```
Clic ■ DETENER
   → emite stop_requested()
   → _worker[0].stop()  →  _stop_flag = True; _pause_event.set()
   → OcrWorker.run() rompe el bucle en la próxima iteración
   → finished() → stage.on_worker_finished()
```

---

## 7. Motor OCR — OCREngine

**Archivo:** `src/core/ocr_engine.py`

### Inicialización

```python
OCREngine(
    api_key,          # clave ZhipuAI (puede ser vacía para backend local)
    profile,          # perfil de extracción
    expected_keys,    # lista de campos para esquema dinámico
    backend,          # nombre del motor ("glm", "ocr-local", ...)
    mode,             # "single_invoice" u otro
    use_preprocessor, # aplicar OpenCV antes del OCR
    upscale,          # factor de escala de imagen (1, 2, 3, 4)
    use_cache,        # usar caché local
    local_conf_threshold, # umbral mínimo de confianza
    prefer_local,     # preferir OCR local para documentos sencillos
)
```

La iniciación sigue este árbol de decisión:

```
¿backend es local?  →  NO instanciar ZhipuAI (ahorro de tokens)
¿backend es IA?     →  instanciar ZhipuAI(api_key) solo si backend registrado es None
```

**Backends locales reconocidos:**
`{"ocr-local", "paddle", "paddleocr", "easyocr"}` + cualquier nombre que empiece por `paddle` o `easyocr`.

### Prompts por perfil

| Perfil | Tipo de salida |
|---|---|
| Facturas/Contable | JSON con campos fijos de factura |
| Contratos/Texto | Texto libre con párrafos y cláusulas |
| Manuscrito (HTR) | Transcripción con `[ilegible]` |
| Foto Libre | Texto libre, tablas con `|` |
| Doc. Histórico/Arte | Texto o descripción visual |

Si `expected_keys` está definido, se construye un prompt dinámico JSON con exactamente esos campos. Si se detectan claves de arte/histórico, se usa el prompt especializado.

### `process_file(path)`

```
path → ¿PDF?  → fitz extrae páginas → _pil_to_b64() → call_backend()
     → ¿imagen? → PIL.Image.open() → _pil_to_b64() → call_backend()

call_backend():
   ¿self._backend registrado?  → backend.process_base64(b64)
   ¿no?                        → self._call_glm(b64)

Retorna: (text, pages, prompt_tokens, completion_tokens, confidence)
```

### Fallback GLM (modo `single_invoice`)

```
_call_glm() con perfil factura
   → si mode == "single_invoice"
       → parse_invoice_text(text)  (invoice_parser)
       → devuelve JSON estructurado
   → si no → devuelve texto crudo
```

---

## 8. Sistema de backends OCR

**Archivo:** `src/core/ocr_backends.py`

Un registro simple de funciones fábrica:

```python
_REGISTRY: Dict[str, Callable[[], object]] = {}

register_backend(name, factory)   # registra un backend
available_backends() → list[str]  # lista los disponibles
get_backend(name) → instancia     # crea instancia del backend
```

Cada backend debe implementar:

```python
def process_base64(self, b64: str) -> tuple[str, int, int]:
    # retorna (texto_extraído, tokens_prompt, tokens_completado)
```

**Backends registrados en tiempo de ejecución:**

| Nombre | Cuándo se añade |
|---|---|
| `paddle-ocr` | Al pulsar "Habilitar PaddleOCR" en ConfigPanel |
| `easyocr` | Al pulsar "Habilitar EasyOCR" en ConfigPanel |
| Cualquier otro | Código externo llama a `register_backend()` |

Por defecto, si no hay ninguno registrado, el combo muestra: `glm`, `mistral-ocr-latest`, `google-vision`, `google-docs`, `ocr-local`.

---

## 9. Worker — hilo de procesamiento

**Archivo:** `src/ui/worker.py`

### Clase `OcrWorker(QThread)`

**Señales emitidas:**

| Señal | Tipos | Cuándo |
|---|---|---|
| `document_done` | `(int, str, float)` | Al terminar cada archivo |
| `document_qa` | `(int, bool, float)` | Resultado del QA por documento |
| `progress` | `(int, int)` | Current, total tras cada archivo |
| `tokens_used` | `(int, int, str)` | Tokens prompt/completado + backend |
| `export_done` | `(str)` | Ruta del archivo exportado |
| `qa_report` | `(str, dict)` | Ruta + estadísticas QA del batch |
| `finished` | `()` | Siempre al terminar (éxito, error o stop) |
| `error` | `(str)` | Descripción del error |

**Estructura de `run()`:**

```python
def run(self):
    try:
        self._run_inner()
    except Exception as exc:
        self.error.emit(f"Error inesperado: {exc}")
    finally:
        self.finished.emit()   # SIEMPRE se emite
```

Esto garantiza que los botones siempre se restauren aunque ocurra un fallo no capturado.

**Control de pausa/stop:**

```python
_pause_event: threading.Event   # .clear() pausa / .set() reanuda
_stop_flag: bool                # True → sale del bucle for

pause() → _pause_event.clear()
resume() → _pause_event.set()
stop() → _stop_flag = True; _pause_event.set()
```

---

## 10. Exportación de resultados

**Archivo:** `src/core/exporter.py`

### Formatos soportados

```
export_results(results, output_dir, format, merge, ...)
   │
   ├─ XLSX → pandas + openpyxl (excel_exporter.py)
   ├─ CSV  → csv.DictWriter
   ├─ DOCX → python-docx (con o sin imágenes incrustadas)
   └─ TXT  → texto plano, un archivo por documento
```

### Pipeline de exportación

```
results: list[dict]    ← cada dict tiene: id, filename, pages, confidence, status, text, images
         │
         ▼
_flatten_results()     ← intenta parsear 'text' como JSON y aplanar
         │
         ├─ Si todos son JSON → pd.json_normalize → columnas dinámicas
         └─ Si no → esquema fijo (id, archivo, páginas, confianza, estado, texto)
         │
         ▼
export a XLSX/CSV/DOCX/TXT
         │
         ▼
qa_checker.compare_invoices_json_vs_excel()  ← compara JSON vs hoja Excel
         │
         ▼
Guarda {archivo}.qa.json con estadísticas
```

---

## 11. Señales PyQt6 (events)

### Mapa completo de señales

```
ConfigPanel.api_validated(bool)
    └→ stage.set_api_ready(bool)
    └→ _refresh_api_ready() (via textChanged / currentTextChanged)

StagePanel.files_dropped(list[str])
    └→ main_window._on_files()   → _file_paths.extend()
                                  → log.add_document()

StagePanel.queue_cleared()
    └→ main_window._on_queue_cleared()  → _file_paths.clear()
                                         → log.clear_table()

StagePanel.start_requested()
    └→ main_window._on_start()   → crea OcrWorker → w.start()

StagePanel.pause_requested()
    └→ main_window._on_pause()   → _worker[0].pause()

StagePanel.resume_requested()
    └→ main_window._on_resume()  → _worker[0].resume()

StagePanel.stop_requested()
    └→ main_window._on_stop()    → _worker[0].stop()

StagePanel.output_file_selected(str)
    └→ main_window (guardado de ruta de archivo de salida)

StagePanel.clear_cache_requested()
    └→ ConfigPanel (limpia directorio de caché)

OcrWorker.document_done(int, str, float)
    └→ log.update_document_row()

OcrWorker.document_qa(int, bool, float)
    └→ log.update_document_qa()

OcrWorker.progress(int, int)
    └→ log.update_progress()

OcrWorker.tokens_used(int, int, str)
    └→ cfg._on_tokens()         → actualiza KPIs + gráfico

OcrWorker.export_done(str)
    └→ main_window (muestra ruta en status bar / log)

OcrWorker.qa_report(str, dict)
    └→ stage.qa_label actualiza texto resumen

OcrWorker.error(str)
    └→ main_window (muestra QMessageBox.critical)

OcrWorker.finished()
    └→ stage.on_worker_finished()  →  _on_stop()
                                       restaura botones
OcrWorker.document_done → _on_document_result()  → _last_batch_rows.append(row)  # [FASE 5]
OcrWorker.finished      → _on_batch_finished_erp() → erp_bar.setVisible(True)   # [FASE 5]
erp_export_btn.clicked  → _on_export_erp() → ERPExporter.export()               # [FASE 5]
```

---

## 12. Tema visual y estilos QSS

### Paleta de colores principal

| Token | Valor | Uso |
|---|---|---|
| Fondo global | `#0B0B14` | QWidget base |
| Fondo panel | `#0E0E1C` | ConfigPanel / LogPanel |
| Borde | `#181830` | Separadores |
| Borde card | `#1E1E32` | Tarjetas internas |
| Texto primario | `#C4CDD8` | Contenido |
| Texto cabecera | `#374151` | Labels de sección |
| Azul acción | `#3B82F6` | Botón Validar, foco de inputs |
| Verde éxito | `#10B981` | KPI valores, radio checked |
| Rojo error | `#EF4444` | Estado desconectado |
| Naranja pausa | `#F59E0B` | Indicadores de espera |

### Botones especiales

```css
#startBtn  → fondo #053D2F · texto #6EE7B7 (verde)
#pauseBtn  → fondo #3B1A02 · texto #FCD34D (amarillo)
#stopBtn   → fondo #3B0808 · texto #FCA5A5 (rojo)
#validateBtn → gradiente linear #1E3A8A → #2563EB (azul)
#pickBtn   → fondo #102040 · texto #93C5FD (azul claro)
#clearBtn  → fondo #1A0808 · texto #F87171 (rojo claro)
```

### Modo Claro

Se aplica un override mínimo (`APP_QSS_LIGHT`):
- Fondo global → `#FFFFFF`
- Texto → `#0B1220`
- Inputs → borde `#E6E6EA`

La preferencia se persiste en `~/.ocr_glm_config.json`.

---

## 13. Configuración persistente

**Archivo:** `~/.ocr_glm_config.json`

Guardado automático de:

| Clave | Contenido |
|---|---|
| `theme` | `"dark"` o `"light"` |
| `named_configs` | Dict de configuraciones guardadas por nombre |
| Cada config | backend, perfil, formato, carpeta destino, opciones de imagen |

La carga ocurre al arrancar la app. Las configuraciones guardadas aparecen en el `QComboBox saved_cfg_cb`.

---

## 15. FASE 4 — Módulos nuevos

### 15.1 `src/core/content_router.py` — Enrutador de contenido IA

Analiza una imagen PIL mediante heurísticas de visión computacional (cv2 + PIL fallback) y devuelve el pipeline OCR óptimo para `OcrTask._build_engine()`.

**Función pública:**
```python
routing = route_content(image_or_path, doc_hint="factura")
# → {
#   "content_type": "table_heavy",
#   "backend":      "glm",
#   "prompt_key":   "invoice",
#   "preprocess":   True,
#   "upscale":      1,
#   "light_mode":   False,
#   "model_hint":   "glm-4v-plus",
#   "confidence":   0.87,
# }
```

**Tipos de contenido detectados:**

| Tipo | Heurística principal | Pipeline asignado |
|---|---|---|
| `music_omr` | Líneas horizontales paralelas (pentagramas) | GLM + upscale x2 |
| `latex_math` | Densidad de símbolos math (`∑∫√`) | GLM + preprocess |
| `legal_dense` | Alta densidad de texto, columnas estrechas | GLM + llm-4v-plus |
| `scanned_noisy` | Ruido σ alto + baja nitidez | OCR-local + preprocess x2 |
| `table_heavy` | Líneas grid / separadores de tabla | GLM + prompt invoice |
| `handwritten` | Bajo contraste de bordes, varianza alta | GLM + prompt HTR |
| `standard` | Fallback | GLM + prompt genérico |

> **Sin cv2:** el módulo degrada silenciosamente a heurísticas PIL-only (modo reducido).

---

### 15.2 `src/core/audit.py` — Trazabilidad de extracciones

Registra cada extracción en `~/.ocr_audit.db` (SQLite thread-safe) con SHA-256 del documento para detectar reprocesados.

```python
from src.core.audit import log_extraction, query_audit

log_extraction(job_id, doc_path, result, model, extra)
records = query_audit(limit=50)
records = query_audit(job_id="abc-123")
```

**Esquema de la tabla `audit_log`:**

| Columna | Tipo | Descripción |
|---|---|---|
| `id` | INTEGER | PK autoincrement |
| `job_id` | TEXT | ID de lote |
| `doc_path` | TEXT | Ruta original |
| `doc_hash` | TEXT | SHA-256 del archivo |
| `model` | TEXT | Nombre del modelo usado |
| `content_type` | TEXT | Tipo detectado por content_router |
| `confidence` | REAL | Confianza final (0–1) |
| `status` | TEXT | `Procesado` / `Error` |
| `fields_count` | INTEGER | Número de campos extraídos |
| `created_at` | TEXT | Timestamp ISO UTC |

> En modo "silent no-op" si la DB no puede crearse — nunca interrumpe el pipeline.

---

### 15.3 `src/ui/exception_dashboard.py` — Panel ⚠ Excepciones

`ExceptionDashboard(QFrame)` muestra solo los documentos que cumplen al menos una condición de excepción:

- Confianza < umbral configurable (por defecto 80 %)
- Estado == `"Error"`
- Reconciliación contable fallida (`flagged`)

**Señales:**
```python
reprocess_requested = pyqtSignal(list)   # list[str] de filenames
```

**Acciones disponibles:**

| Botón | Comportamiento |
|---|---|
| Aprobar | Marca fila como revisada manualmente (ícono ✔, no desaparece) |
| Re-procesar | Emite `reprocess_requested([filenames])` al worker |
| Exportar informe | Guarda JSON/CSV con todas las excepciones actuales |
| Umbral (QSpinBox) | Ajusta el porcentaje mínimo de confianza (1–100) |

**Conexión en `main_window.py`:**
```python
w.document_done.connect(exc_dash.on_document_done)
w.qa_report.connect(exc_dash.on_qa_report)
exc_dash.reprocess_requested.connect(handler)
```

---

### 15.4 `src/ui/ocr_task.py` — OcrTask (routing + audit hook)

Wrapper sobre `OCREngine` que:
1. Llama a `route_content()` si `smart_routing=True` antes de `_build_engine()`
2. Llama a `log_extraction()` si `audit_enabled=True` después de obtener el resultado

Integrado en `worker.py` via las claves `smart_routing` y `audit_enabled` de `engine_config`.

---

### 15.5 `config_panel.py` — checkbox Smart Routing (FASE 4)

Añadido en grid posición `(2, 0)`:

| Widget | objectName | Default |
|---|---|---|
| `QCheckBox smart_routing_chk` | — | `False` |

Se guarda/carga con el resto de la configuración en `~/.ocr_glm_config.json`.

---

### 15.6 `src/core/job_queue.py` — Cola SQLite persistente (FASE 3)

`JobQueue` reemplaza el checkpoint JSON (`.ocr_state.json`) con una DB SQLite en modo WAL.

```python
jq = JobQueue(Path(output_dir) / ".ocr_jobs.db")
jq.enqueue_batch(files, profile, backend)
while (job := jq.next_pending()) is not None:
    ...procesar...
    jq.mark_done(job["id"], result_dict)
```

Estados de job: `pending` → `running` → `done` / `failed`.  
Reintentos automáticos hasta `max_retries` (default 3).

---

### 15.7 `src/core/accounting_engine.py` — ReconciliationEngine (FASE 3)

Valida cruzadamente un conjunto de documentos relacionados (factura + OC + guía de remisión):

```python
engine = ReconciliationEngine()
issues = engine.cross_validate([doc1, doc2, doc3])
# issues: list[ValidationIssue]
#   .severity: "error" | "warning" | "info"
#   .code:     "LINE_SUM_MISMATCH" | "DATE_ORDER" | ...
#   .message:  str
```


---

## 16. FASE 5 — Exportación ERP

### 16.1 `src/data/erp_mapper.py`

#### `ERPMapper`

Enriquece un dict de resultado OCR con códigos ERP/GL desde un CSV maestro de proveedores.

| Columna CSV | Uso |
|---|---|
| `ID Fiscal` | Llave de búsqueda (RUC / NIF / CIF…) |
| `ERP_Vendor_Code` | Código de proveedor en Odoo/SAP |
| `GL_Account_Code` | Cuenta de gasto (DEBE) — ej. `60100` |
| `AP_Account` | Cuenta de proveedores (HABER) — ej. `42100` |
| `Tax_Account` | Cuenta de IVA soportado — ej. `40110` |
| `Company_Code` | Sociedad SAP — ej. `0001` |

**Valores por defecto si la columna no existe en el CSV o el proveedor no se encuentra:**

```python
_DEFAULT_AP_ACCOUNT  = "42100"   # Proveedores
_DEFAULT_TAX_ACCOUNT = "40110"   # IVA Soportado
_DEFAULT_EXP_ACCOUNT = "60100"   # Compras/Gastos
_DEFAULT_SAP_COMPANY = "0001"    # Sociedad SAP
```

#### `ERPExporter`

Convierte una lista de dicts OCR a asientos contables.

```
Factura entrada  (proveedor):       DEBE gasto                + DEBE IVA → HABER proveedor
Si solo hay total sin subtotal/iva: se desglosa automáticamente al 18 %
```

| Método | Archivo generado | Separador |
|---|---|---|
| `export(rows, fmt="journal")` | `Fecha, Cuenta_Debe… Proveedor` | `,` |
| `export(rows, fmt="odoo")` | `Date, Journal, Account, Debit, Credit, Partner` | `,` |
| `export(rows, fmt="odoo_xml")` | XML `<record model="account.move">` | — |
| `export(rows, fmt="sap")` | `BUKRS;BLDAT;BUDAT;BLART;WAERS;HKONT;SHKZW;DMBTR;SGTXT;LIFNR` | `;` |

**Función top-level de conveniencia:**
```python
from src.data.erp_mapper import export_to_erp
out = export_to_erp(rows, fmt="odoo", output_path="out.csv", vendor_master_path="vm.csv")
```

### 16.2 `main_window.py` — barra ERP

#### Posición en el layout

```
_central_col (QWidget, VBox)
  ├─ central_tabs (QTabWidget, stretch=1)
  └─ erp_bar      (QFrame, h=44, oculto por defecto)
       ├─ erp_lbl      ("📤  Lote procesado — exportar a ERP:")
       ├─ erp_fmt_cb   (combobox de formato)
       └─ erp_export_btn ("Exportar a ERP")
```

#### Ciclo de vida

| Evento | Efecto |
|---|---|
| `_on_start()` ejecutado | `_last_batch_rows.clear()`, `erp_bar.setVisible(False)` |
| `w.document_done` emitido | lambda añade row a `_last_batch_rows` |
| `w.finished` emitido | `_on_batch_finished_erp()` → `erp_bar.setVisible(True)` si hay rows |
| Clic **Exportar a ERP** | `QFileDialog` → `ERPExporter.export()` → `QMessageBox.information` |
| `_on_queue_cleared()` | `_last_batch_rows.clear()`, `erp_bar.setVisible(False)` |

#### `_on_export_erp()` — lógica interna

1. Lee el formato del `erp_fmt_cb` (primera palabra: `journal` / `odoo` / `odoo_xml` / `sap`).
2. Busca un tab `ErpPanel` activo en `central_tabs` para obtener `vendor_master_path`.
3. Propone nombre de archivo con timestamp como `erp_export_{fmt}_{YYYYMMDD_HHMMSS}.{ext}`.
4. Abre `QFileDialog.getSaveFileName()`.
5. Instancia `ERPExporter(vendor_master_path)` y llama `exporter.export(rows, fmt, path)`.
6. Muestra `QMessageBox.information` con la ruta y número de filas procesadas.
7. Errores capturados con `QMessageBox.critical`.

---

## 17. Configuración del IDE (Pylance / Pylint)

### Archivos de configuración

| Archivo | Propósito |
|---|---|
| `.vscode/settings.json` | `extraPaths`, `typeCheckingMode: off`, `diagnosticSeverityOverrides` |
| `pyrightconfig.json` | `venvPath`, `reportMissingImports: none`, supresión global de falsos positivos |
| `.pylintrc` | Desactiva W0703/W0212/W0108/W0613 (patrones deliberados de la arquitectura) |

### Por qué NO hay errores reales

Todos los **338 warnings** del IDE son **falsos positivos** de cuatro categorías:

| Categoría | Causa real | Norma `#` |
|---|---|---|
| `Unable to import PyQt6.*` | IDE no apuntaba al venv correcto | Resuelto con `pyrightconfig.json` + `__init__.py` |
| `Access to protected member _X` | Patrón closure → acceso a `cfg._tabs`, `w._smart_routing` etc. | W0212 desactivado (intencional) |
| `Catching too general Exception` | `try/except Exception: pass` defensivo en GUI Qt | W0703 desactivado (intencional) |
| `Lambda may not be necessary` | Patrón conexión señales Qt: `connect(lambda x: ...)` | W0108 desactivado (intencional) |

> **Regla:** no añadir `# type: ignore` masivos. Los archivos compilan sin errores:
> ```
> python -m py_compile src/ui/main_window.py   # OK
> python -m py_compile src/core/content_router.py # OK
> python -m py_compile src/core/audit.py        # OK
> ```

---

*Fin de la documentación — actualizada a FASE 5 (10/04/2026)*

> Para detalles de SchemaPanel, ErpPanel, Dashboard, Telemetry → ver archivos fuente en `src/ui/`.

## Notas operativas recientes — Mistral, QA y sidecars

Se han introducido varias mejoras para manejar las salidas Markdown que devuelve Mistral y facilitar la depuración:

- `force_mistral` (config): opción booleana en `engine_config` que, si está a `true`, fuerza siempre `backend="mistral"` al crear el motor (`src/ui/ocr_task.py`). Útil para pruebas repetibles sin smart routing.

- `raw_mistral` en metadata QA: `src/ui/worker.py` añade al archivo `{export}.qa.json` un campo `raw_mistral` (mapping filename→texto) cuando el backend usado es Mistral. Permite inspeccionar el Markdown original sin reprocesar PDFs.

- Sidecars por documento: `src/data/exporters.py` ahora escribe junto al export:
    - `<docname>_<ts>__mistral.md` — Markdown crudo devuelto por Mistral.
    - `<docname>_<ts>__payload.json` — JSON parseado (si existía) o el resultado del fallback `invoice_parser.parse_invoice_text()` aplicado al Markdown.

- Fallback de parsing: la función `_parse_glm_response()` intenta extraer JSON desde `text`; si falla, llama a `src.core.invoice_parser.parse_invoice_text(raw)` para construir un payload estructurado que será usado en el Excel/CSV.

- QA reforzado: `src/core/qa_checker.py` al validar extracciones de Mistral intenta parsear JSON embebido, y si no existe, usa `parse_invoice_text()` y luego aplica las mismas reglas/validaciones que para otros backends. Esto evita falsos positivos en QA cuando Mistral devuelve texto libre.

### Recomendaciones prácticas

1. Prompt: actualizar `clients/example_client.tpl` para pedir explícitamente "SOLO JSON" con el esquema esperado y ejemplos (few-shot). Usar `temperature=0` para respuestas determinísticas.
2. Si ya tienes `*__mistral.md` sidecars generados, no es necesario reprocesar los PDFs: ejecuta el pequeño script de regeneración (`scripts/regen_payloads.py`) que aplica `parse_invoice_text()` sobre cada Markdown y escribe/actualiza `__payload.json`.
3. Para diagnosticar por qué solo 1 de 3 PDFs fue procesado, revisar logs de `scripts/run_ui_debug.py` y buscar `status: "Error"` o excepciones en consola. También validar la columna `status` en cada resultado y el contenido de `raw_mistral`.

### Comandos útiles

Desde la raíz del repo (PowerShell):
```powershell
Set-Location "H:\git\OCR con Glm\OCR-con-GLM-IA"
& .venv\Scripts\Activate.ps1
python scripts\run_ui_debug.py

# listar sidecars generados
Get-ChildItem "I:\pruevas v2\resultado\m1" -Filter "*__mistral.md" | Select Name,Length,LastWriteTime
Get-ChildItem "I:\pruevas v2\resultado\m1" -Filter "*__payload.json" | Select Name,Length,LastWriteTime
```

Si quieres que aplique el prompt por defecto con `temperature=0` y active `force_mistral` en la configuración programaticamente, indícalo y lo parcheo enseguida.

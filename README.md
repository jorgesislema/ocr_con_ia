# OCR Con IA — SaaS de extracción de documentos

Plataforma SaaS de extracción de datos con IA para **facturas de Latinoamérica
(multi-impuesto) y Europa (multipágina, totales dispersos), manuscritos,
partituras y documentos genéricos**, con exportación a **Excel / CSV / Word / PDF**.

> Este repositorio contiene dos capas:
> * **SaaS web** (`app/`) — la plataforma comercial (FastAPI + Celery + frontend de 4 pasos). *Nueva.*
> * **App de escritorio** (`src/`) — la aplicación PyQt6 original, intacta y funcional.

## Principios arquitectónicos

| # | Regla | Implementación |
|---|-------|----------------|
| 1 | **Desacoplamiento de IA (Factory)** | `app/ai/` — `BaseAIProvider` abstracto + `GeminiProvider` (gratuito, multimodal) y `MistralProvider` (pago, precisión en tablas). Elección por configuración del usuario o dificultad del documento. |
| 2 | **Esquema canónico** | `app/core/schemas/invoice.py` — `InvoiceSchema` (Pydantic) con `taxes: [{type, rate, amount}]`, descuentos, subtotales, totales y metadatos por página. Único contrato interno. |
| 3 | **Secretos centralizados** | `app/core/config.py` → `get_secret(key)`: Infisical/Vault en producción, `.env` en desarrollo. |
| 4 | **Validación determinista** | `app/validation/validator.py` — Python verifica `total == subtotal + Σimpuestos − Σdescuentos` con `Decimal` exacto. `consolidator.py` suma subtotales por página antes de validar el total final multipágina. |
| 5 | **Flujo asíncrono** | `app/workers/` — Celery + Redis. El endpoint solo encola y devuelve `task_id`. |

## Estructura de la capa SaaS

```
app/
├── core/
│   ├── config.py               # Settings + get_secret (Infisical/Vault/.env)
│   ├── schemas/invoice.py      # InvoiceSchema canónico (Pydantic)
│   └── db/                     # SQLAlchemy 2.0: User, Document, ExtractionTask, ExportFile
├── ai/
│   ├── base.py                 # BaseAIProvider (ABC) + ExtractionInput/Result
│   ├── gemini_provider.py      # Multimodal, tier gratuito
│   ├── mistral_provider.py     # OCR + LLM, alta precisión en tablas
│   ├── factory.py              # get_provider() — auto o por preferencia
│   └── prompts.py              # Prompt canónico compartido (JSON desde el schema)
├── validation/
│   ├── validator.py            # Motor aritmético determinista (Decimal)
│   └── consolidator.py         # Consolidación multipágina (totales dispersos)
├── workers/
│   ├── celery_app.py           # Celery + Redis (eager en dev)
│   └── tasks.py                # pipeline: extraer → consolidar → validar
├── api/
│   ├── main.py                 # FastAPI + CORS + frontend estático
│   ├── deps.py                 # Auth multi-tenant X-API-Key
│   └── routes/documents.py     # upload / estado / revisión / exportación
├── services/exporter.py        # Excel, CSV, Word, PDF desde InvoiceSchema
├── frontend/                   # SPA del flujo de 4 pasos (HTML/CSS/JS)
└── tests/                      # Tests del validador y consolidador
```

## API (v1)

| Método | Ruta | Descripción |
|--------|------|-------------|
| `POST` | `/api/v1/documents` | Sube el archivo y encola. Devuelve `task_id` (HTTP 202). |
| `GET` | `/api/v1/tasks/{id}` | Estado (`queued→processing→completed/needs_review/failed`) + JSON canónico. |
| `PATCH` | `/api/v1/tasks/{id}` | Guarda correcciones humanas y re-valida matemáticamente. |
| `POST` | `/api/v1/tasks/{id}/export` | Genera `xlsx` / `csv` / `docx` / `pdf`. |
| `GET` | `/health` | Health check. |

Autenticación: header `X-API-Key` (usuario demo en desarrollo).

## Flujo del frontend (4 pasos)

1. **Carga** — arrastrar PDF/imagen → `POST /documents` → `task_id`.
2. **Progreso** — polling de `GET /tasks/{id}` con barra y log.
3. **Revisión humana** — tabla editable (líneas, impuestos, descuentos) con banner
   del validador determinista; al aprobar, el backend **re-valida** la aritmética.
4. **Exportación** — descarga en Excel, CSV, Word o PDF.

## Puesta en marcha (desarrollo)

```powershell
# 1. Dependencias
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-saas.txt

# 2. Configurar claves (solo dev)
copy .env.example .env      # y rellenar GEMINI_API_KEY y/o MISTRAL_API_KEY

# 3. Arrancar API (modo eager: no requiere Redis)
uvicorn app.api.main:app --reload --port 8000

# 4. Web UI en http://localhost:8000 · docs en http://localhost:8000/docs
```

Con Redis (producción):

```powershell
$env:OCR_CELERY_EAGER="false"
$env:OCR_REDIS_URL="redis://…"
celery -A app.workers.celery_app:celery worker --loglevel=info
uvicorn app.api.main:app --port 8000
```

Tests del motor de validación (sin claves ni Redis):

```powershell
python -m pytest app/tests -q
```

## App de escritorio original

La aplicación PyQt6 sigue disponible (motores GLM-4V, Mistral OCR, Google Vision,
OCR local, Paddle/EasyOCR, exportación, ERP). Ver `ARQUITECTURA.md` para su
documentación técnica completa y `scripts/run_ui_debug.py` para arrancarla.

## Roadmap SaaS

- [ ] Alembic + PostgreSQL en producción
- [ ] Autenticación JWT / OAuth y facturación de planes
- [ ] Webhooks de finalización de tarea
- [ ] Reutilización del `content_router` del proyecto original para dificultad fina
- [ ] Detección de duplicados por SHA-256 (ya almacenado en `documents.sha256`)

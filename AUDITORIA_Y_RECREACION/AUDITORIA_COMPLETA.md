# AUDITORÍA COMPLETA DEL REPOSITORIO OCR-con-GLM-IA

## 1. RESUMEN EJECUTIVO

**Proyecto:** Aplicación de escritorio OCR industrial que extrae texto estructurado de documentos (PDF, JPEG, PNG, TIFF) usando múltiples motores de IA y exporta a XLSX, CSV, DOCX, TXT y formatos ERP.

**Stack actual:** Python 3.13.1, PyQt6, PyMuPDF, Pillow, OpenCV, pandas, ZhipuAI

**Estado:** 6 fases completadas, arquitectura madura pero con deuda técnica acumulada.

---

## 2. PROBLEMAS CRÍTICOS IDENTIFICADOS

### 2.1. Frontend (PyQt6)
- **Monolito UI:** `main_window.py` acumula 1560+ líneas con lógica de negocio mezclada
- **Acoplamiento:** UI llama directamente a `OCREngine`, violando separación de capas
- **Sin web:** Solo app de escritorio, imposible despliegue en servidores
- **Hardcoding:** Dimensiones fijas (1560x940px), sin responsive
- **Estilos:** QSS inline en `styles.py`, sin theming profesional

### 2.2. Backend
- **Sin REST API completa:** `server.py` tiene solo 4 endpoints básicos
- **Sin autenticación JWT:** Solo X-API-Key estático
- **Sin validación de entrada:** No hay Pydantic models para requests
- **Sin rate limiting real:** `rate_limiter.py` es básico
- **Base de datos:** SQLite sin migraciones, sin connection pooling

### 2.3. OCR Engine
- **Tight coupling:** `ocr_engine.py` (1078+ líneas) hace todo: OCR, preprocessing, caching, structuring
- **Backends limitados:** Solo 4 paid + 2 local, sin soporte para Tesseract, PaddleOCR completo
- **Sin parallelismo real:** QThreadPool con max 3, sin distribución
- **Cache:** Simple hash-based, sin invalidación inteligente

### 2.4. Code Quality
- **Sin type hints completos:** pyright desactivado
- **Sin tests unitarios reales:** Solo tests de integración básicos
- **Sin CI/CD:** No hay pipeline automatizado
- **Docstrings:** Inconsistentes, algunos archivos sin documentación

---

## 3. ESTRUCTURA ACTUAL DE ARCHIVOS

```
OCR-con-GLM-IA/
├── src/
│   ├── api/server.py              # FastAPI incompleto
│   ├── core/
│   │   ├── ocr_engine.py          # 1078+ líneas, monolito
│   │   ├── structuring_engine.py  # 15+ proveedores LLM
│   │   ├── ocr_backends.py        # Registry de backends
│   │   ├── preprocessor.py        # OpenCV pipeline
│   │   ├── prompt_manager.py      # Jinja2 templates
│   │   ├── job_queue.py           # SQLite WAL
│   │   ├── audit.py               # SHA-256 trail
│   │   ├── content_router.py      # Detección IA
│   │   ├── qa_checker.py          # Validación
│   │   ├── rate_limiter.py        # Backoff exponencial
│   │   ├── circuit_breaker.py     # Circuit Breaker
│   │   ├── correction_learner.py  # Aprendizaje
│   │   ├── folder_watcher.py      # Watchdog
│   │   ├── security.py            # Fernet encryption
│   │   ├── erp_mapper.py          # Odoo/SAP
│   │   └── backends/              # Mistral, Google Vision, Google DocAI
│   ├── data/
│   │   ├── database.py            # SQLite helper
│   │   ├── exporters.py           # 1400+ líneas export
│   │   ├── erp_mapper.py          # ERP integration
│   │   └── template_manager.py    # User templates
│   └── ui/
│       ├── main_window.py         # 1560+ líneas
│       ├── worker.py              # QThread
│       ├── ocr_task.py            # QRunnable
│       └── [15+ panels]           # PyQt6 widgets
├── prompts/                       # Jinja2 templates
├── user_templates/                # JSON schemas
├── scripts/                       # Debug/test scripts
└── tests/                         # Minimal tests
```

---

## 4. TÉCNICAS OCR SOPORTADAS (ACTUAL)

### Gratuitas
| Backend | Estado | Calidad |
|---------|--------|---------|
| PaddleOCR | Parcial (dynamic register) | Alta |
| EasyOCR | Parcial (dynamic register) | Media |
| Tesseract | No implementado | Media |
| ocr-local | Básico | Baja |

### De Pago
| Backend | Estado | Costo/Pág | Calidad |
|---------|--------|-----------|---------|
| GLM-4V (ZhipuAI) | Principal | ~$0.01 | Alta |
| Mistral OCR | Implementado | $0.01-$0.03 | Muy Alta |
| Google Vision | Implementado | $0.0015 | Alta |
| Google DocAI | Implementado | $0.01 | Muy Alta |
| OpenAI GPT-4V | Solo structuring | $0.01 | Muy Alta |
| Claude Vision | Via OpenRouter | Variable | Muy Alta |

---

## 5. INTEGRACIONES IA SOPORTADAS (ACTUAL)

### Para OCR (Extracción de imagen a texto)
- ZhipuAI GLM-4V (principal)
- Mistral OCR
- Google Cloud Vision
- Google Document AI

### Para Estructuración (Texto a JSON)
- OpenAI GPT-4o
- DeepSeek V4
- Google Gemini Flash/Pro
- Qwen Max
- Mistral Large
- Anthropic Claude (via OpenRouter)
- GLM-4 (ZhipuAI)
- Ollama (local)
- LM Studio (local)
- Azure OpenAI
- OpenRouter

---

## 6. FLUJO DE PROCESAMIENTO ACTUAL

```
Archivos (PDF/JPEG/PNG/TIFF)
  → StagePanel (drag-and-drop)
  → OcrWorker (QThread)
    → OcrTask (QRunnable, max 3 concurrent)
      → route_content() [detección IA]
      → OCREngine.process_file()
        → preprocessor.adaptive_preprocess() [OpenCV]
        → backend.process_base64() [GLM-4V/Mistral/Google]
        → StructuringEngine.structure() [DeepSeek/GPT/etc]
      → audit.log_extraction()
  → export_results() [XLSX/CSV/DOCX/TXT/ERP]
  → QA validation
  → UI update
```

---

## 7. DEUDA TÉCNICA ACUMULADA

1. **上帝类:** `ocr_engine.py` y `exporters.py` son monolitos
2. **Sin inyección de dependencias:** Todo hardcodeado
3. **Sin contratos:** No hay interfaces/protocols formales
4. **Testing débil:** <30% cobertura real
5. **Sin observabilidad:** Logs básicos, sin métricas estructuradas
6. **Sin documentación de API:** No hay OpenAPI/Swagger funcional
7. **Configuración fragmentada:** .env + ~/.ocr_glm_config.json + hardcoded
8. **Sin migraciones DB:** SQLite sin schema versioning
9. **Frontend acoplado:** Lógica de negocio en UI
10. **Sin despliegue:** No hay Docker, no hay CI/CD

---

## 8. RECOMENDACIONES PARA RECREACIÓN

### Arquitectura Objetivo
- **Backend:** FastAPI completo con clean architecture
- **Frontend:** React/Next.js (web) o mantener PyQt6 desktop como alternativa
- **OCR:** Plugin system con 10+ backends
- **IA:** Provider agnostic con fallback chain
- **DB:** PostgreSQL + Redis para cache
- **Deploy:** Docker + docker-compose
- **Testing:** >80% cobertura, E2E tests
- **CI/CD:** GitHub Actions

### Prioridades
1. Separar frontend de backend (API-first)
2. Implementar plugin system para OCR backends
3. Crear interface para todas las IAs
4. Añadir Tesseract, Surya, DocTR como gratuitos
5. Añadir Azure AI Document Intelligence, AWS Textract como pagos
6. Testing completo
7. Docker + despliegue

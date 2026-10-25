# ARQUITECTURA OBJETIVO - OCR INDUSTRIAL

## RESUMEN
Arquitectura completa para recrear el proyecto OCR Industrial con separación frontend/backend, soporte para 15+ backends OCR, 15+ proveedores LLM, y deployment profesional.

---

## 1. VISIÓN GENERAL

```
┌─────────────────────────────────────────────────────────────────┐
│                        FRONTEND                                  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │   React/    │  │   Vue.js/   │  │  PyQt6      │             │
│  │   Next.js   │  │   Nuxt.js   │  │  (Desktop)  │             │
│  └─────────────┘  └─────────────┘  └─────────────┘             │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ REST API + WebSocket
                              │
┌─────────────────────────────────────────────────────────────────┐
│                        BACKEND                                   │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │   FastAPI   │  │   Celery    │  │   Redis     │             │
│  │   (API)     │  │   (Tasks)   │  │   (Cache)   │             │
│  └─────────────┘  └─────────────┘  └─────────────┘             │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    OCR ENGINE                            │   │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐   │   │
│  │  │PaddleOCR│  │Tesseract│  │ Surya   │  │ EasyOCR │   │   │
│  │  └─────────┘  └─────────┘  └─────────┘  └─────────┘   │   │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐   │   │
│  │  │GLM-4V   │  │Mistral  │  │GPT-4V   │  │Claude   │   │   │
│  │  └─────────┘  └─────────┘  └─────────┘  └─────────┘   │   │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐   │   │
│  │  │Gemini   │  │DocAI    │  │Textract │  │Vision   │   │   │
│  │  └─────────┘  └─────────┘  └─────────┘  └─────────┘   │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                 STRUCTURING ENGINE                       │   │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐   │   │
│  │  │GPT-4o   │  │Claude   │  │Gemini   │  │DeepSeek │   │   │
│  │  └─────────┘  └─────────┘  └─────────┘  └─────────┘   │   │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐   │   │
│  │  │Qwen     │  │Mistral  │  │GLM-4    │  │Llama3   │   │   │
│  │  └─────────┘  └─────────┘  └─────────┘  └─────────┘   │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │
┌─────────────────────────────────────────────────────────────────┐
│                      DATA LAYER                                  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │ PostgreSQL  │  │    Redis    │  │  MinIO/S3   │             │
│  │  (Main DB)  │  │  (Cache)    │  │  (Files)    │             │
│  └─────────────┘  └─────────────┘  └─────────────┘             │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. ESTRUCTURA DE DIRECTORIOS

```
ocr-industrial/
├── frontend/
│   ├── src/
│   │   ├── app/                    # Next.js App Router
│   │   ├── components/             # Componentes React
│   │   ├── hooks/                  # Custom hooks
│   │   ├── lib/                    # Utilidades
│   │   ├── stores/                 # Estado global (Zustand)
│   │   └── types/                  # TypeScript types
│   ├── public/                     # Assets estáticos
│   ├── package.json
│   ├── tailwind.config.js
│   └── tsconfig.json
│
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                 # FastAPI app
│   │   ├── config.py               # Settings
│   │   ├── api/                    # API endpoints
│   │   │   └── v1/
│   │   │       ├── ocr.py
│   │   │       ├── exports.py
│   │   │       ├── prompts.py
│   │   │       ├── backends.py
│   │   │       ├── jobs.py
│   │   │       └── admin.py
│   │   ├── core/                   # Business logic
│   │   │   ├── ocr/
│   │   │   ├── structuring/
│   │   │   ├── export/
│   │   │   ├── qa/
│   │   │   └── security/
│   │   ├── models/                 # SQLAlchemy models
│   │   ├── services/               # Business services
│   │   ├── storage/                # File storage
│   │   └── utils/                  # Utilities
│   ├── backends/                   # OCR backend plugins
│   │   ├── base.py
│   │   ├── paddleocr_backend.py
│   │   ├── tesseract_backend.py
│   │   ├── surya_backend.py
│   │   ├── easyocr_backend.py
│   │   ├── glm4v_backend.py
│   │   ├── mistral_backend.py
│   │   ├── openai_vision_backend.py
│   │   ├── anthropic_backend.py
│   │   ├── google_vision_backend.py
│   │   ├── google_docai_backend.py
│   │   ├── azure_document_backend.py
│   │   └── aws_textract_backend.py
│   ├── alembic/                    # DB migrations
│   ├── tests/
│   ├── requirements.txt
│   └── pyproject.toml
│
├── docker/
│   ├── Dockerfile.frontend
│   ├── Dockerfile.backend
│   ├── docker-compose.yml
│   └── docker-compose.dev.yml
│
├── docs/
│   ├── API.md
│   ├── ARCHITECTURE.md
│   └── DEPLOYMENT.md
│
├── .github/
│   └── workflows/
│       ├── ci.yml
│       └── deploy.yml
│
└── README.md
```

---

## 3. BACKEND DETALLADO

### 3.1 main.py (FastAPI App)
```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_database()
    await init_cache()
    yield
    # Shutdown
    await close_database()
    await close_cache()

app = FastAPI(
    title="OCR Industrial API",
    version="2.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(ocr_router, prefix="/api/v1/ocr", tags=["OCR"])
app.include_router(exports_router, prefix="/api/v1/exports", tags=["Exports"])
app.include_router(prompts_router, prefix="/api/v1/prompts", tags=["Prompts"])
app.include_router(backends_router, prefix="/api/v1/backends", tags=["Backends"])
app.include_router(jobs_router, prefix="/api/v1/jobs", tags=["Jobs"])
app.include_router(admin_router, prefix="/api/v1/admin", tags=["Admin"])
```

### 3.2 OCR Engine (Plugin System)
```python
# backends/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

class BackendType(Enum):
    LOCAL = "local"
    CLOUD_PAID = "cloud_paid"
    CLOUD_FREE = "cloud_free"

@dataclass
class OCRResult:
    text: str
    confidence: float
    pages: int
    backend: str
    processing_time: float
    tokens_used: int = 0
    cost: float = 0.0
    metadata: dict = None

class OCRBackend(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...
    
    @property
    @abstractmethod
    def backend_type(self) -> BackendType: ...
    
    @abstractmethod
    async def process_image(self, image_bytes: bytes, **kwargs) -> OCRResult: ...
    
    @abstractmethod
    async def process_pdf(self, pdf_bytes: bytes, **kwargs) -> OCRResult: ...
    
    @abstractmethod
    async def health_check(self) -> bool: ...

# backends/registry.py
class BackendRegistry:
    _backends: dict[str, OCRBackend] = {}
    
    @classmethod
    def register(cls, backend: OCRBackend):
        cls._backends[backend.name] = backend
    
    @classmethod
    def get(cls, name: str) -> OCRBackend:
        return cls._backends.get(name)
    
    @classmethod
    def available(cls) -> list[str]:
        return list(cls._backends.keys())
```

### 3.3 Structuring Engine
```python
# core/structuring/provider.py
from abc import ABC, abstractmethod

class LLMProvider(ABC):
    @abstractmethod
    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.1
    ) -> str: ...
    
    @abstractmethod
    def estimate_cost(self, tokens: int) -> float: ...

# core/structuring/engine.py
class StructuringEngine:
    def __init__(self):
        self.providers: dict[str, LLMProvider] = {}
        self.fallback_chain = [
            "groq", "deepseek", "gemini", "qwen",
            "mistral", "openai", "anthropic"
        ]
    
    async def structure(
        self,
        ocr_text: str,
        prompt: str,
        provider: str = "auto"
    ) -> dict:
        if provider == "auto":
            for p in self.fallback_chain:
                try:
                    return await self._try_provider(p, ocr_text, prompt)
                except:
                    continue
            raise Exception("All providers failed")
        return await self._try_provider(provider, ocr_text, prompt)
```

### 3.4 Export System
```python
# core/export/orchestrator.py
class ExportOrchestrator:
    def __init__(self):
        self.exporters = {
            "xlsx": XLSXExporter(),
            "csv": CSVExporter(),
            "docx": DOCXExporter(),
            "txt": TXTExporter(),
            "json": JSONExporter(),
            "erp_odoo_csv": ERPExporter("odoo_csv"),
            "erp_odoo_xml": ERPExporter("odoo_xml"),
            "erp_sap": ERPExporter("sap"),
        }
    
    async def export(
        self,
        results: list[OCRResult],
        format: str,
        output_dir: str
    ) -> ExportResult:
        exporter = self.exporters[format]
        return await exporter.export(results, output_dir)
```

### 3.5 Job Queue (Celery + Redis)
```python
# services/job_service.py
from celery import Celery

celery_app = Celery(
    'ocr_industrial',
    broker='redis://localhost:6379/0',
    backend='redis://localhost:6379/1'
)

@celery_app.task(bind=True)
def process_document_task(self, job_id: str, file_path: str, config: dict):
    """Tarea asíncrona para procesar documento"""
    try:
        update_job_status(job_id, "processing")
        
        # OCR
        ocr_result = ocr_engine.process_document(file_path, config)
        
        # Structuring
        if config.get("structuring"):
            structured = structuring_engine.structure(
                ocr_result.text,
                config["prompt"]
            )
        
        # Export
        export_result = export_orchestrator.export(
            [ocr_result],
            config["output_format"],
            config["output_dir"]
        )
        
        update_job_status(job_id, "completed", result=export_result)
        
    except Exception as e:
        update_job_status(job_id, "failed", error=str(e))
        raise
```

---

## 4. FRONTEND DETALLADO

### 4.1 Layout Principal
```tsx
// src/components/layout/AppLayout.tsx
export function AppLayout({ children }: { children: React.ReactNode }) {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  
  return (
    <div className="flex h-screen bg-gray-100">
      <Sidebar open={sidebarOpen} onToggle={() => setSidebarOpen(!sidebarOpen)} />
      
      <div className="flex-1 flex flex-col overflow-hidden">
        <Header />
        
        <main className="flex-1 overflow-auto p-6">
          {children}
        </main>
      </div>
    </div>
  );
}
```

### 4.2 OCR Processing Page
```tsx
// src/app/page.tsx
export default function OCRPage() {
  const [files, setFiles] = useState<File[]>([]);
  const [config, setConfig] = useState<OCRConfig>(defaultConfig);
  const { processBatch, results, loading } = useOCR();
  
  return (
    <div className="grid grid-cols-12 gap-6 h-full">
      {/* Config Panel */}
      <div className="col-span-3">
        <OCRConfig config={config} onChange={setConfig} />
      </div>
      
      {/* Main Area */}
      <div className="col-span-6 flex flex-col gap-6">
        <FileUploader onFilesAccepted={setFiles} />
        
        {files.length > 0 && (
          <>
            <FileList files={files} onRemove={handleRemove} />
            
            <Button 
              onClick={() => processBatch(files, config)}
              loading={loading}
            >
              Procesar {files.length} archivos
            </Button>
          </>
        )}
        
        {results.length > 0 && (
          <OCRResults results={results} />
        )}
      </div>
      
      {/* Preview Panel */}
      <div className="col-span-3">
        <DocumentPreview />
      </div>
    </div>
  );
}
```

---

## 5. DOCKER

### docker-compose.yml
```yaml
version: '3.8'

services:
  frontend:
    build:
      context: ./frontend
      dockerfile: ../docker/Dockerfile.frontend
    ports:
      - "3000:3000"
    environment:
      - NEXT_PUBLIC_API_URL=http://localhost:8000
    depends_on:
      - backend

  backend:
    build:
      context: ./backend
      dockerfile: ../docker/Dockerfile.backend
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://user:pass@postgres:5432/ocr_industrial
      - REDIS_URL=redis://redis:6379/0
      - ZHIPUAI_API_KEY=${ZHIPUAI_API_KEY}
      - MISTRAL_API_KEY=${MISTRAL_API_KEY}
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      # ... other env vars
    depends_on:
      - postgres
      - redis
    volumes:
      - ./data:/app/data
      - ./prompts:/app/prompts

  worker:
    build:
      context: ./backend
      dockerfile: ../docker/Dockerfile.worker
    environment:
      - DATABASE_URL=postgresql://user:pass@postgres:5432/ocr_industrial
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      - postgres
      - redis

  postgres:
    image: postgres:16-alpine
    environment:
      - POSTGRES_USER=user
      - POSTGRES_PASSWORD=pass
      - POSTGRES_DB=ocr_industrial
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  minio:
    image: minio/minio
    command: server /data --console-address ":9001"
    environment:
      - MINIO_ROOT_USER=minioadmin
      - MINIO_ROOT_PASSWORD=minioadmin
    ports:
      - "9000:9000"
      - "9001:9001"
    volumes:
      - minio_data:/data

volumes:
  postgres_data:
  minio_data:
```

---

## 6. CI/CD

### .github/workflows/ci.yml
```yaml
name: CI

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      
      - name: Install dependencies
        run: |
          cd backend
          pip install -r requirements.txt
          pip install pytest pytest-cov
      
      - name: Run tests
        run: |
          cd backend
          pytest tests/ --cov=app --cov-report=xml
      
      - name: Upload coverage
        uses: codecov/codecov-action@v3

  lint:
    runs-on: ubuntu-latest
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Run Ruff
        run: ruff check backend/
      
      - name: Run MyPy
        run: mypy backend/

  build:
    runs-on: ubuntu-latest
    needs: [test, lint]
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Build Docker images
        run: |
          docker compose -f docker-compose.yml build
```

---

## 7. FLUJO COMPLETO

```
1. Usuario sube archivos (PDF/IMG)
   ↓
2. Frontend envía a API (/api/v1/ocr/process)
   ↓
3. Backend crea Job en PostgreSQL
   ↓
4. Celery worker toma el Job
   ↓
5. OCR Engine procesa:
   a. Detecta contenido (ContentRouter)
   b. Preprocesa imagen (Preprocessor)
   c. Selecciona backend (Registry)
   d. Ejecuta OCR (Backend)
   e. Post-procesa texto
   ↓
6. Structuring Engine estructura:
   a. Selecciona LLM (Fallback Chain)
   b. Envía prompt + texto OCR
   c. Parsea respuesta JSON
   ↓
7. Export Orchestrator exporta:
   a. Selecciona formato (XLSX/CSV/DOCX/etc)
   b. Genera archivo
   c. Genera sidecar JSON
   ↓
8. Backend actualiza Job status
   ↓
9. Frontend recibe notificación (WebSocket)
   ↓
10. Usuario descarga resultado
```

---

## 8. MÉTRICAS Y MONITOREO

### Endpoints de monitoreo
```python
@app.get("/api/v1/admin/metrics")
async def get_metrics():
    return {
        "total_documents": await get_total_documents(),
        "total_tokens": await get_total_tokens(),
        "total_cost": await get_total_cost(),
        "backend_usage": await get_backend_usage(),
        "avg_confidence": await get_avg_confidence(),
        "active_jobs": await get_active_jobs(),
    }

@app.get("/api/v1/admin/backends/health")
async def check_backends_health():
    results = {}
    for backend_name in registry.available():
        backend = registry.get(backend_name)
        results[backend_name] = await backend.health_check()
    return results
```

---

## 9. SEGURIDAD

### Autenticación
```python
# API Key authentication
@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    api_key = request.headers.get("X-API-Key")
    if not api_key or not validate_api_key(api_key):
        return JSONResponse(status_code=401, content={"error": "Invalid API key"})
    return await call_next(request)

# JWT authentication (opcional)
from fastapi.security import HTTPBearer

security = HTTPBearer()

@app.get("/api/v1/protected")
async def protected_endpoint(user = Depends(get_current_user)):
    return {"user": user}
```

### Encriptación
```python
from cryptography.fernet import Fernet

def encrypt_credentials(data: dict) -> str:
    key = get_encryption_key()
    f = Fernet(key)
    return f.encrypt(json.dumps(data).encode()).decode()

def decrypt_credentials(token: str) -> dict:
    key = get_encryption_key()
    f = Fernet(key)
    return json.loads(f.decrypt(token.encode()).decode())
```

---

## 10. RESUMEN DE TECNOLOGÍAS

| Capa | Tecnología | Propósito |
|------|------------|-----------|
| Frontend | React/Next.js + Tailwind | UI web moderna |
| Frontend Desktop | PyQt6 | App de escritorio |
| API | FastAPI | REST API de alto rendimiento |
| Queue | Celery + Redis | Tareas asíncronas |
| Cache | Redis | Cache de resultados |
| Database | PostgreSQL | Base de datos principal |
| Storage | MinIO/S3 | Almacenamiento de archivos |
| OCR Local | PaddleOCR, Tesseract, Surya, EasyOCR | OCR gratuito |
| OCR Cloud | GLM-4V, Mistral, GPT-4V, Claude, Gemini, Vision, DocAI, Textract | OCR de pago |
| LLM | GPT-4o, Claude, Gemini, DeepSeek, Qwen, Mistral, GLM-4, Llama3 | Estructuración |
| Testing | pytest, Cypress | Unit + E2E tests |
| CI/CD | GitHub Actions | Integración continua |
| Deploy | Docker Compose | Contenedores |
| Monitoring | Prometheus + Grafana | Métricas |

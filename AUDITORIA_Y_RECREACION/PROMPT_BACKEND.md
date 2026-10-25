# PROMPT PARA RECREACIÓN DEL BACKEND - OCR INDUSTRIAL

## CONTEXTO
Estás recreando el backend de un sistema OCR industrial que procesa documentos (PDF, JPEG, PNG, TIFF) usando múltiples motores de IA y exporta a múltiples formatos. El sistema debe ser modular, escalable y soportar 10+ backends OCR.

## ARQUITECTURA OBJETIVO

```
backend/
├── app/
│   ├── main.py                    # FastAPI app factory
│   ├── config.py                  # Settings con Pydantic
│   ├── dependencies.py            # Dependency injection
│   ├── api/
│   │   ├── v1/
│   │   │   ├── ocr.py             # Endpoints OCR
│   │   │   ├── exports.py         # Endpoints exportación
│   │   │   ├── prompts.py         # Gestión de prompts
│   │   │   ├── backends.py        # Gestión de backends
│   │   │   ├── jobs.py            # Gestión de trabajos
│   │   │   ├── audit.py           # Audit trail
│   │   │   ├── templates.py       # Templates de extracción
│   │   │   └── admin.py           # Admin endpoints
│   │   └── deps.py                # Shared dependencies
│   ├── core/
│   │   ├── ocr/
│   │   │   ├── engine.py          # OREngine (Orchestrator)
│   │   │   ├── registry.py        # Backend registry
│   │   │   ├── base.py            # Abstract OCRBackend
│   │   │   ├── preprocessing.py   # Image preprocessing
│   │   │   ├── postprocessing.py  # Text normalization
│   │   │   └── content_router.py  # Smart content detection
│   │   ├── structuring/
│   │   │   ├── engine.py          # StructuringEngine
│   │   │   ├── provider.py        # Abstract LLMProvider
│   │   │   ├── providers/         # 15+ provider implementations
│   │   │   └── prompt_manager.py  # Prompt loading/rendering
│   │   ├── export/
│   │   │   ├── orchestrator.py    # Export orchestrator
│   │   │   ├── base.py            # Abstract Exporter
│   │   │   ├── xlsx.py            # Excel exporter
│   │   │   ├── csv.py             # CSV exporter
│   │   │   ├── docx.py            # Word exporter
│   │   │   ├── txt.py             # Text exporter
│   │   │   └── erp/               # ERP exporters (Odoo/SAP)
│   │   ├── qa/
│   │   │   ├── validator.py       # QA validation
│   │   │   ├── reconciler.py      # Accounting reconciliation
│   │   │   └── semantic.py        # Semantic validation
│   │   ├── security/
│   │   │   ├── auth.py            # JWT/OAuth2
│   │   │   ├── encryption.py      # Fernet encryption
│   │   │   └── api_keys.py        # API key management
│   │   └── resilience/
│   │       ├── circuit_breaker.py # Circuit breaker
│   │       ├── rate_limiter.py    # Rate limiting
│   │       └── retry.py          # Retry with backoff
│   ├── models/
│   │   ├── schemas.py             # Pydantic models
│   │   ├── database.py            # SQLAlchemy models
│   │   └── enums.py               # Enums
│   ├── services/
│   │   ├── ocr_service.py         # OCR business logic
│   │   ├── export_service.py      # Export business logic
│   │   ├── job_service.py         # Job queue management
│   │   ├── audit_service.py       # Audit trail
│   │   ├── prompt_service.py      # Prompt management
│   │   └── telemetry_service.py   # Metrics/telemetry
│   ├── storage/
│   │   ├── file_storage.py        # File I/O
│   │   ├── cache.py               # Redis cache
│   │   └── temp.py                # Temp file management
│   └── utils/
│       ├── image.py               # Image utilities
│       ├── pdf.py                 # PDF utilities
│       ├── validators.py          # Input validators
│       └── formatters.py          # Output formatters
├── backends/
│   ├── __init__.py
│   ├── base.py                    # Abstract OCRBackend
│   ├── paddleocr_backend.py       # PaddleOCR (gratuito)
│   ├── easyocr_backend.py         # EasyOCR (gratuito)
│   ├── tesseract_backend.py       # Tesseract (gratuito)
│   ├── surya_backend.py           # Surya OCR (gratuito)
│   ├── doctr_backend.py           # DocTR (gratuito)
│   ├── glm4v_backend.py           # GLM-4V (pago)
│   ├── mistral_backend.py         # Mistral OCR (pago)
│   ├── google_vision_backend.py   # Google Vision (pago)
│   ├── google_docai_backend.py    # Google DocAI (pago)
│   ├── openai_vision_backend.py   # OpenAI GPT-4V (pago)
│   ├── anthropic_backend.py       # Claude Vision (pago)
│   ├── azure_document_backend.py  # Azure Doc Intelligence (pago)
│   ├── aws_textract_backend.py    # AWS Textract (pago)
│   └── nomic_backend.py           # Nomic Embed (gratuito)
├── tests/
│   ├── unit/
│   ├── integration/
│   └── e2e/
├── alembic/                       # DB migrations
├── docker/
│   ├── Dockerfile
│   └── docker-compose.yml
├── requirements.txt
├── pyproject.toml
└── README.md
```

---

## MÓDULO 1: OCR ENGINE (CORE)

### Interface Base
```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Optional, AsyncGenerator

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
    tokens_used: Optional[int] = None
    cost: Optional[float] = None
    metadata: Optional[dict] = None

@dataclass
class OCRPageResult:
    page_number: int
    text: str
    confidence: float
    image_path: Optional[str] = None
    tables: Optional[list] = None

class OCRBackend(ABC):
    """Interface para todos los backends OCR"""
    
    @property
    @abstractmethod
    def name(self) -> str: ...
    
    @property
    @abstractmethod
    def backend_type(self) -> BackendType: ...
    
    @property
    @abstractmethod
    def supported_formats(self) -> list[str]: ...
    
    @abstractmethod
    async def process_image(self, image_bytes: bytes, **kwargs) -> OCRResult: ...
    
    @abstractmethod
    async def process_pdf(self, pdf_bytes: bytes, **kwargs) -> OCRResult: ...
    
    @abstractmethod
    async def health_check(self) -> bool: ...
    
    def estimate_cost(self, pages: int) -> Optional[float]:
        return None
```

### Implementación del Engine
```python
class OCREngine:
    """Orquestador principal de OCR"""
    
    def __init__(self, config: Settings):
        self.registry = BackendRegistry()
        self.preprocessor = ImagePreprocessor()
        self.postprocessor = TextPostprocessor()
        self.content_router = ContentRouter()
        self.cache = LRICache(max_size=1000)
        self._init_backends()
    
    async def process_document(
        self,
        file: UploadFile,
        backend: str = "auto",
        prompt: Optional[str] = None,
        preprocessing: bool = True,
        structuring: bool = True
    ) -> OCRResult:
        # 1. Detect content type
        content_type = self.content_router.detect(file)
        
        # 2. Select best backend
        if backend == "auto":
            backend = self._select_backend(content_type, file)
        
        # 3. Preprocess
        if preprocessing:
            processed = await self.preprocessor.process(file, content_type)
        else:
            processed = file
        
        # 4. OCR
        ocr_backend = self.registry.get(backend)
        result = await ocr_backend.process_document(processed)
        
        # 5. Post-process
        result.text = self.postprocessor.normalize(result.text)
        
        # 6. Structure (optional)
        if structuring and prompt:
            result = await self._structure(result, prompt)
        
        return result
```

---

## MÓDULO 2: BACKENDS OCR

### 2.1 GRATUITOS

#### PaddleOCR Backend
```python
class PaddleOCRBackend(OCRBackend):
    """PaddleOCR - Motor OCR gratuito de Baidu"""
    
    name = "paddleocr"
    backend_type = BackendType.LOCAL
    supported_formats = ["png", "jpg", "jpeg", "tiff", "bmp", "pdf"]
    
    def __init__(self):
        from paddleocr import PaddleOCR
        self.ocr = PaddleOCR(
            use_angle_cls=True,
            lang='es',  # Soporte multilingüe
            use_gpu=False,
            show_log=False
        )
    
    async def process_image(self, image_bytes: bytes, **kwargs) -> OCRResult:
        # Implementación con PaddleOCR
        ...
    
    async def process_pdf(self, pdf_bytes: bytes, **kwargs) -> OCRResult:
        # Convertir PDF a imágenes y procesar
        ...
```

#### EasyOCR Backend
```python
class EasyOCRBackend(OCRBackend):
    """EasyOCR - Motor OCR basado en PyTorch"""
    
    name = "easyocr"
    backend_type = BackendType.LOCAL
    supported_formats = ["png", "jpg", "jpeg", "tiff", "bmp"]
    
    def __init__(self):
        import easyocr
        self.reader = easyocr.Reader(['es', 'en'])
    
    async def process_image(self, image_bytes: bytes, **kwargs) -> OCRResult:
        # Implementación con EasyOCR
        ...
```

#### Tesseract Backend
```python
class TesseractBackend(OCRBackend):
    """Tesseract OCR - Motor de Google"""
    
    name = "tesseract"
    backend_type = BackendType.LOCAL
    supported_formats = ["png", "jpg", "jpeg", "tiff", "bmp", "pdf"]
    
    def __init__(self):
        import pytesseract
        self.pytesseract = pytesseract
        # Verificar instalación
        self.pytesseract.get_tesseract_version()
    
    async def process_image(self, image_bytes: bytes, **kwargs) -> OCRResult:
        # Implementación con Tesseract
        ...
```

#### Surya Backend
```python
class SuryaBackend(OCRBackend):
    """Surya OCR - OCR de nueva generación"""
    
    name = "surya"
    backend_type = BackendType.LOCAL
    supported_formats = ["png", "jpg", "jpeg", "tiff", "bmp", "pdf"]
    
    def __init__(self):
        from surya import detection, recognition
        self.detection = detection
        self.recognition = recognition
```

#### DocTR Backend
```python
class DocTRBackend(OCRBackend):
    """DocTR - OCR basado en deep learning"""
    
    name = "doctr"
    backend_type = BackendType.LOCAL
    supported_formats = ["png", "jpg", "jpeg", "tiff", "bmp", "pdf"]
    
    def __init__(self):
        from doctr.io import DocumentFile
        from doctr.models import ocr_predictor
        self.model = ocr_predictor(pretrained=True)
```

### 2.2 DE PAGO

#### GLM-4V Backend
```python
class GLM4VBackend(OCRBackend):
    """GLM-4V - Modelo multimodal de ZhipuAI"""
    
    name = "glm-4v"
    backend_type = BackendType.CLOUD_PAID
    supported_formats = ["png", "jpg", "jpeg", "tiff", "bmp", "pdf"]
    cost_per_page = 0.01
    
    def __init__(self, api_key: str):
        from zhipuai import ZhipuAI
        self.client = ZhipuAI(api_key=api_key)
    
    async def process_image(self, image_bytes: bytes, **kwargs) -> OCRResult:
        base64_image = self._encode_base64(image_bytes)
        response = self.client.chat.completions.create(
            model="glm-4v-flash",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}},
                    {"type": "text", "text": kwargs.get("prompt", "Extrae todo el texto de esta imagen")}
                ]
            }],
            timeout=60
        )
        return OCRResult(
            text=response.choices[0].message.content,
            confidence=0.95,
            pages=1,
            backend=self.name,
            processing_time=response.usage.total_tokens,
            tokens_used=response.usage.total_tokens
        )
```

#### Mistral OCR Backend
```python
class MistralOCRBackend(OCRBackend):
    """Mistral OCR - Motor OCR de Mistral AI"""
    
    name = "mistral-ocr"
    backend_type = BackendType.CLOUD_PAID
    supported_formats = ["png", "jpg", "jpeg", "pdf"]
    cost_per_page = 0.01  # $1/1000 pages
    
    def __init__(self, api_key: str):
        from mistralai import MistralAI
        self.client = MistralAI(api_key=api_key)
    
    async def process_pdf(self, pdf_bytes: bytes, **kwargs) -> OCRResult:
        # Mistral soporta PDF directamente
        ...
```

#### Google Vision Backend
```python
class GoogleVisionBackend(OCRBackend):
    """Google Cloud Vision API"""
    
    name = "google-vision"
    backend_type = BackendType.CLOUD_PAID
    supported_formats = ["png", "jpg", "jpeg", "tiff", "bmp", "pdf"]
    cost_per_page = 0.0015
    
    def __init__(self, credentials: dict):
        from google.cloud import vision
        self.client = vision.ImageAnnotatorClient.from_service_account_info(credentials)
    
    async def process_image(self, image_bytes: bytes, **kwargs) -> OCRResult:
        image = vision.Image(content=image_bytes)
        response = self.client.document_text_detection(image=image)
        ...
```

#### OpenAI Vision Backend
```python
class OpenAIVisionBackend(OCRBackend):
    """OpenAI GPT-4V para OCR"""
    
    name = "openai-vision"
    backend_type = BackendType.CLOUD_PAID
    supported_formats = ["png", "jpg", "jpeg", "gif", "webp"]
    cost_per_page = 0.01
    
    def __init__(self, api_key: str):
        from openai import OpenAI
        self.client = OpenAI(api_key=api_key)
    
    async def process_image(self, image_bytes: bytes, **kwargs) -> OCRResult:
        base64_image = self._encode_base64(image_bytes)
        response = self.client.chat.completions.create(
            model="gpt-4o",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}},
                    {"type": "text", "text": kwargs.get("prompt", "Extract all text from this image")}
                ]
            }]
        )
        ...
```

#### Azure Document Intelligence Backend
```python
class AzureDocumentBackend(OCRBackend):
    """Azure AI Document Intelligence"""
    
    name = "azure-document"
    backend_type = BackendType.CLOUD_PAID
    supported_formats = ["pdf", "png", "jpg", "jpeg", "tiff", "bmp"]
    cost_per_page = 0.01
    
    def __init__(self, endpoint: str, key: str):
        from azure.ai.documentintelligence import DocumentIntelligenceClient
        self.client = DocumentIntelligenceClient(endpoint, key)
    
    async def process_pdf(self, pdf_bytes: bytes, **kwargs) -> OCRResult:
        poller = self.client.begin_analyze_document("prebuilt-read", body=pdf_bytes)
        result = poller.result()
        ...
```

#### AWS Textract Backend
```python
class AWSTextractBackend(OCRBackend):
    """AWS Textract"""
    
    name = "aws-textract"
    backend_type = BackendType.CLOUD_PAID
    supported_formats = ["pdf", "png", "jpg", "jpeg"]
    cost_per_page = 0.015
    
    def __init__(self, aws_key: str, aws_secret: str, region: str):
        import boto3
        self.client = boto3.client(
            'textract',
            aws_access_key_id=aws_key,
            aws_secret_access_key=aws_secret,
            region_name=region
        )
```

---

## MÓDULO 3: PREPROCESSING

```python
class ImagePreprocessor:
    """Pipeline de preprocesamiento adaptativo"""
    
    async def process(
        self,
        file: UploadFile,
        content_type: str,
        options: PreprocessingOptions = None
    ) -> ProcessedImage:
        # 1. Load image
        image = await self._load_image(file)
        
        # 2. Detect quality
        quality = self._estimate_quality(image)
        
        # 3. Apply pipeline adaptativo
        if quality.score < 0.5:
            image = self._deskew(image)
            image = self._denoise(image)
            image = self._enhance_contrast(image)
            image = self._sharpen(image)
        elif quality.score < 0.8:
            image = self._deskew(image)
            image = self._enhance_contrast(image)
        
        # 4. Smart upscale si es necesario
        if image.width < 1000 or image.height < 1000:
            image = self._smart_upscale(image)
        
        return ProcessedImage(image=image, quality=quality)
    
    def _deskew(self, image: np.ndarray) -> np.ndarray:
        """Corrección de inclinación usando Hough transform"""
        ...
    
    def _denoise(self, image: np.ndarray) -> np.ndarray:
        """Reducción de ruido"""
        ...
    
    def _enhance_contrast(self, image: np.ndarray) -> np.ndarray:
        """CLAHE + corrección gamma"""
        ...
    
    def _sharpen(self, image: np.ndarray) -> np.ndarray:
        """Enfoque Laplaciano"""
        ...
    
    def _smart_upscale(self, image: np.ndarray) -> np.ndarray:
        """Upscale inteligente con LANCZOS"""
        ...
```

---

## MÓDULO 4: STRUCTURING ENGINE

```python
class StructuringEngine:
    """Motor de estructuración LLM"""
    
    def __init__(self, config: Settings):
        self.providers = {}
        self._init_providers(config)
    
    async def structure(
        self,
        ocr_text: str,
        prompt: str,
        provider: str = "auto",
        output_format: str = "json"
    ) -> StructuredResult:
        # Seleccionar proveedor
        if provider == "auto":
            provider = self._select_provider()
        
        llm = self.providers[provider]
        
        # Estructurar
        response = await llm.complete(
            system_prompt=self._get_system_prompt(output_format),
            user_prompt=f"{prompt}\n\nTexto OCR:\n{ocr_text}",
            temperature=0.1
        )
        
        # Parse response
        structured = self._parse_response(response)
        
        return StructuredResult(
            data=structured,
            provider=provider,
            tokens_used=response.usage.total_tokens,
            confidence=self._calculate_confidence(structured)
        )

class LLMProvider(ABC):
    """Interface para proveedores LLM"""
    
    @abstractmethod
    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.1
    ) -> LLMResponse: ...
    
    @abstractmethod
    def estimate_cost(self, tokens: int) -> float: ...
```

### Proveedores Soportados

| Proveedor | Modelo | Endpoint | Costo/1K tokens |
|-----------|--------|----------|-----------------|
| OpenAI | GPT-4o | api.openai.com | $0.005 |
| DeepSeek | V4 | api.deepseek.com | $0.0002 |
| Gemini | Flash 2.0 | generativelanguage.googleapis.com | $0.0001 |
| Gemini | Pro 2.5 | generativelanguage.googleapis.com | $0.00125 |
| Qwen | Max | dashscope.aliyuncs.com | $0.0008 |
| Mistral | Large | api.mistral.ai | $0.002 |
| Claude | 3.5 Sonnet | api.anthropic.com | $0.003 |
| GLM-4 | GLM-4 | open.bigmodel.cn | $0.001 |
| Ollama | Llama3 | localhost:11434 | Gratis |
| LM Studio | Local | localhost:1234 | Gratis |
| Azure | GPT-4o | Custom | Variable |
| OpenRouter | Multi | openrouter.ai | Variable |
| Groq | Llama3 | api.groq.com | Gratis |
| Together | Mixtral | api.together.xyz | $0.0002 |
| Fireworks | Mixtral | api.fireworks.ai | $0.0002 |

---

## MÓDULO 5: EXPORTACIÓN

```python
class ExportOrchestrator:
    """Orquestador de exportación"""
    
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
        output_dir: str,
        options: ExportOptions = None
    ) -> ExportResult:
        exporter = self.exporters[format]
        return await exporter.export(results, output_dir, options)

class XLSXExporter:
    """Exportador Excel con pandas"""
    
    async def export(self, results, output_dir, options):
        # Crear DataFrame
        df = self._results_to_dataframe(results)
        
        # Aplicar formato
        with pd.ExcelWriter(f"{output_dir}/output.xlsx") as writer:
            df.to_excel(writer, index=False)
            
            # Añadir formatos condicionales
            self._add_conditional_formats(writer, df)
        
        # Generar sidecar JSON
        self._generate_sidecar(results, output_dir)
```

---

## MÓDULO 6: API REST

```python
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="OCR Industrial API",
    version="2.0.0",
    description="API para procesamiento OCR industrial con múltiples backends"
)

# Endpoints principales
@app.post("/api/v1/ocr/process")
async def process_document(
    file: UploadFile,
    backend: str = "auto",
    prompt: Optional[str] = None,
    output_format: str = "json",
    current_user: User = Depends(get_current_user)
):
    """Procesar documento con OCR"""
    ...

@app.get("/api/v1/ocr/backends")
async def list_backends():
    """Listar backends disponibles"""
    ...

@app.get("/api/v1/ocr/jobs/{job_id}")
async def get_job_status(job_id: str):
    """Obtener estado de un trabajo"""
    ...

@app.post("/api/v1/ocr/batch")
async def process_batch(
    files: list[UploadFile],
    backend: str = "auto",
    parallel: int = 3
):
    """Procesar múltiples documentos en paralelo"""
    ...

@app.get("/api/v1/exports/{job_id}")
async def download_export(
    job_id: str,
    format: str = "xlsx"
):
    """Descargar exportación"""
    ...

@app.get("/api/v1/audit")
async def get_audit_log(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None
):
    """Obtener log de auditoría"""
    ...
```

---

## MÓDULO 7: BASE DE DATOS

```python
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Float, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

Base = declarative_base()

class OCRJob(Base):
    __tablename__ = "ocr_jobs"
    
    id = Column(String, primary_key=True)
    user_id = Column(String, index=True)
    file_name = Column(String)
    file_hash = Column(String)
    backend_used = Column(String)
    status = Column(String)  # pending, processing, completed, failed
    result = Column(JSON)
    confidence = Column(Float)
    tokens_used = Column(Integer)
    cost = Column(Float)
    processing_time = Column(Float)
    created_at = Column(DateTime)
    completed_at = Column(DateTime)

class AuditLog(Base):
    __tablename__ = "audit_log"
    
    id = Column(Integer, primary_key=True)
    job_id = Column(String, index=True)
    document_hash = Column(String)
    action = Column(String)
    details = Column(JSON)
    timestamp = Column(DateTime)
```

---

## MÓDULO 8: TESTING

```python
# tests/unit/test_ocr_engine.py
import pytest
from app.core.ocr.engine import OCREngine

@pytest.fixture
def engine():
    return OCREngine(config=TestConfig())

@pytest.mark.asyncio
async def test_process_image(engine, sample_image):
    result = await engine.process_document(sample_image)
    assert result.text is not None
    assert result.confidence > 0
    assert result.backend in ["paddleocr", "tesseract"]

@pytest.mark.asyncio
async def test_auto_backend_selection(engine, sample_image):
    result = await engine.process_document(sample_image, backend="auto")
    assert result.backend is not None

# tests/integration/test_api.py
@pytest.mark.asyncio
async def test_process_endpoint(client, auth_headers, sample_pdf):
    response = await client.post(
        "/api/v1/ocr/process",
        headers=auth_headers,
        files={"file": ("test.pdf", sample_pdf, "application/pdf")}
    )
    assert response.status_code == 200
    assert "text" in response.json()
```

---

## REQUISITOS FINALES

1. **15+ backends OCR** (5+ gratuitos, 10+ pagos)
2. **Async completo** (FastAPI + async/await)
3. **Clean Architecture** (separación de capas)
4. **Testing >80%** (unit + integration + e2e)
5. **Docker listo** (docker-compose con todos los servicios)
6. **Migraciones DB** (Alembic)
7. **Rate limiting** (por usuario, por backend)
8. **Circuit breaker** (fallo gracefully)
9. **Cache inteligente** (Redis + LRU local)
10. **Observabilidad** (logs estructurados, métricas, tracing)

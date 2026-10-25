# PROMPT PARA SISTEMA DE EXTRACCIÓN DE DOCUMENTOS

## CONTEXTO
Estás construyendo el módulo de extracción de un sistema OCR industrial. Este módulo se encarga de recibir documentos (PDF, imágenes), detectar su contenido, preprocesarlos, ejecutar OCR con el backend más adecuado, y devolver texto estructurado.

## ARQUITECTURA DEL MÓDULO DE EXTRACCIÓN

```
extraccion/
├── __init__.py
├── receptor.py              # Recibe archivos del usuario
├── detector_contenido.py    # Detecta tipo de contenido
├── preprocessor.py          # Preprocesamiento de imágenes
├── seleccionador_backend.py # Selecciona mejor backend OCR
├── ejecutor_ocr.py          # Ejecuta OCR con backend seleccionado
├── postprocesador.py        # Normaliza y limpia texto OCR
├── estructurador.py         # Convierte texto a JSON estructurado
├── validador.py             # Valida calidad del resultado
├── cache.py                 # Cache de resultados
└── orquestador.py           # Coordina todo el pipeline
```

---

## 1. RECEPTOR DE DOCUMENTOS

```python
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import hashlib

class DocumentFormat(Enum):
    PDF = "pdf"
    PNG = "png"
    JPG = "jpg"
    JPEG = "jpeg"
    TIFF = "tiff"
    BMP = "bmp"
    WEBP = "webp"

@dataclass
class ReceivedDocument:
    file_bytes: bytes
    filename: str
    format: DocumentFormat
    file_hash: str
    size_bytes: int
    metadata: dict = None

class DocumentReceiver:
    """Recibe y valida documentos del usuario"""
    
    SUPPORTED_FORMATS = {
        '.pdf': DocumentFormat.PDF,
        '.png': DocumentFormat.PNG,
        '.jpg': DocumentFormat.JPG,
        '.jpeg': DocumentFormat.JPEG,
        '.tiff': DocumentFormat.TIFF,
        '.tif': DocumentFormat.TIFF,
        '.bmp': DocumentFormat.BMP,
        '.webp': DocumentFormat.WEBP,
    }
    
    MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
    MAX_PAGES_PDF = 500
    
    async def receive(
        self,
        file_bytes: bytes,
        filename: str
    ) -> ReceivedDocument:
        # 1. Validar formato
        format = self._detect_format(filename)
        if not format:
            raise ValueError(f"Formato no soportado: {filename}")
        
        # 2. Validar tamaño
        if len(file_bytes) > self.MAX_FILE_SIZE:
            raise ValueError(f"Archivo excede {self.MAX_FILE_SIZE/1024/1024}MB")
        
        # 3. Calcular hash
        file_hash = hashlib.sha256(file_bytes).hexdigest()
        
        # 4. Validar PDF (si es PDF)
        if format == DocumentFormat.PDF:
            await self._validate_pdf(file_bytes)
        
        return ReceivedDocument(
            file_bytes=file_bytes,
            filename=filename,
            format=format,
            file_hash=file_hash,
            size_bytes=len(file_bytes)
        )
    
    def _detect_format(self, filename: str) -> DocumentFormat:
        ext = Path(filename).suffix.lower()
        return self.SUPPORTED_FORMATS.get(ext)
    
    async def _validate_pdf(self, pdf_bytes: bytes):
        import fitz
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        if len(doc) > self.MAX_PAGES_PDF:
            raise ValueError(f"PDF excede {self.MAX_PAGES_PDF} páginas")
        doc.close()
```

---

## 2. DETECTOR DE CONTENIDO

```python
import cv2
import numpy as np
from enum import Enum

class ContentType(Enum):
    STANDARD_TEXT = "standard_text"
    TABLE_HEAVY = "table_heavy"
    HANDWRITTEN = "handwritten"
    SCANNED_NOISY = "scanned_noisy"
    LEGAL_DENSE = "legal_dense"
    MATH_FORMULA = "math_formula"
    MUSIC_SCORE = "music_score"
    MIXED_CONTENT = "mixed_content"

@dataclass
class ContentAnalysis:
    content_type: ContentType
    confidence: float
    recommended_backend: str
    preprocessing_level: str  # "none", "light", "heavy"
    estimated_difficulty: float  # 0-1

class ContentDetector:
    """Detecta tipo de contenido usando heurísticas OpenCV"""
    
    def analyze(self, image: np.ndarray) -> ContentAnalysis:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
        
        # Extraer features
        features = {
            "text_density": self._text_density(gray),
            "line_density": self._line_density(gray),
            "noise_level": self._noise_level(gray),
            "brightness": self._brightness(gray),
            "edge_density": self._edge_density(gray),
            "angular_entropy": self._angular_entropy(gray),
            "symbol_density": self._symbol_density(gray),
        }
        
        # Clasificar
        content_type = self._classify(features)
        
        # Seleccionar backend recomendado
        backend = self._recommend_backend(content_type, features)
        
        # Nivel de preprocesamiento
        preprocessing = self._recommend_preprocessing(features)
        
        return ContentAnalysis(
            content_type=content_type,
            confidence=self._calculate_confidence(features),
            recommended_backend=backend,
            preprocessing_level=preprocessing,
            estimated_difficulty=self._estimate_difficulty(features)
        )
    
    def _text_density(self, gray: np.ndarray) -> float:
        """Densidad de texto (píxeles oscuros vs total)"""
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        return np.sum(binary > 0) / binary.size
    
    def _line_density(self, gray: np.ndarray) -> float:
        """Densidad de líneas horizontales/verticales"""
        edges = cv2.Canny(gray, 50, 150)
        
        # Líneas horizontales
        h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (40, 1))
        h_lines = cv2.morphologyEx(edges, cv2.MORPH_OPEN, h_kernel)
        
        # Líneas verticales
        v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 40))
        v_lines = cv2.morphologyEx(edges, cv2.MORPH_OPEN, v_kernel)
        
        total_lines = np.sum(h_lines > 0) + np.sum(v_lines > 0)
        return total_lines / edges.size
    
    def _noise_level(self, gray: np.ndarray) -> float:
        """Nivel de ruido"""
        return cv2.Laplacian(gray, cv2.CV_64F).var()
    
    def _classify(self, features: dict) -> ContentType:
        """Clasifica contenido basado en features"""
        if features["line_density"] > 0.01:
            return ContentType.TABLE_HEAVY
        elif features["angular_entropy"] > 0.7:
            return ContentType.HANDWRITTEN
        elif features["noise_level"] > 500:
            return ContentType.SCANNED_NOISY
        elif features["text_density"] > 0.3:
            return ContentType.LEGAL_DENSE
        elif features["symbol_density"] > 0.1:
            return ContentType.MATH_FORMULA
        else:
            return ContentType.STANDARD_TEXT
    
    def _recommend_backend(self, content_type: ContentType, features: dict) -> str:
        """Recomienda backend basado en contenido"""
        recommendations = {
            ContentType.TABLE_HEAVY: "azure-document",  # Mejor en tablas
            ContentType.HANDWRITTEN: "gpt-4v",  # Mejor en manuscritos
            ContentType.SCANNED_NOISY: "paddleocr",  # Robusto a ruido
            ContentType.LEGAL_DENSE: "claude",  # Entiende contexto legal
            ContentType.MATH_FORMULA: "gpt-4v",  # Entiende fórmulas
            ContentType.STANDARD_TEXT: "paddleocr",  # Rápido y gratis
        }
        return recommendations.get(content_type, "auto")
    
    def _recommend_preprocessing(self, features: dict) -> str:
        """Recomienda nivel de preprocesamiento"""
        if features["noise_level"] > 500:
            return "heavy"
        elif features["noise_level"] > 200:
            return "light"
        return "none"
```

---

## 3. PREPROCESADOR ADAPTATIVO

```python
import cv2
import numpy as np
from PIL import Image

class AdaptivePreprocessor:
    """Pipeline de preprocesamiento adaptativo"""
    
    async def process(
        self,
        image_bytes: bytes,
        content_analysis: ContentAnalysis
    ) -> np.ndarray:
        # Cargar imagen
        image = self._load_image(image_bytes)
        
        # Aplicar pipeline según análisis
        if content_analysis.preprocessing_level == "heavy":
            image = self._deskew(image)
            image = self._denoise(image)
            image = self._enhance_contrast(image)
            image = self._sharpen(image)
            image = self._binarize(image)
        elif content_analysis.preprocessing_level == "light":
            image = self._deskew(image)
            image = self._enhance_contrast(image)
        
        # Smart upscale si es necesario
        if image.shape[1] < 1000 or image.shape[0] < 1000:
            image = self._smart_upscale(image)
        
        return image
    
    def _load_image(self, image_bytes: bytes) -> np.ndarray:
        """Carga imagen desde bytes"""
        nparr = np.frombuffer(image_bytes, np.uint8)
        image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        return image
    
    def _deskew(self, image: np.ndarray) -> np.ndarray:
        """Corrección de inclinación"""
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        coords = np.column_stack(np.where(gray > 0))
        
        if len(coords) < 100:
            return image
        
        angle = cv2.minAreaRect(coords)[-1]
        
        if angle < -45:
            angle = -(90 + angle)
        else:
            angle = -angle
        
        if abs(angle) < 0.5:
            return image
        
        (h, w) = image.shape[:2]
        center = (w // 2, h // 2)
        M = cv2.getRotationMatrix2D(center, angle, 1.0)
        
        return cv2.warpAffine(
            image, M, (w, h),
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_REPLICATE
        )
    
    def _denoise(self, image: np.ndarray) -> np.ndarray:
        """Reducción de ruido"""
        return cv2.fastNlMeansDenoisingColored(image, None, 10, 10, 7, 21)
    
    def _enhance_contrast(self, image: np.ndarray) -> np.ndarray:
        """CLAHE + corrección gamma"""
        # CLAHE
        lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        l = clahe.apply(l)
        lab = cv2.merge([l, a, b])
        image = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
        
        # Gamma correction
        gamma = 1.5
        look_up_table = np.array([
            ((i / 255.0) ** (1 / gamma)) * 255
            for i in range(256)
        ]).astype("uint8")
        
        return cv2.LUT(image, look_up_table)
    
    def _sharpen(self, image: np.ndarray) -> np.ndarray:
        """Enfoque Laplaciano"""
        kernel = np.array([[-1, -1, -1], [-1, 9, -1], [-1, -1, -1]])
        return cv2.filter2D(image, -1, kernel)
    
    def _binarize(self, image: np.ndarray) -> np.ndarray:
        """Binarización adaptativa"""
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        binary = cv2.adaptiveThreshold(
            gray, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY, 11, 2
        )
        return cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)
    
    def _smart_upscale(self, image: np.ndarray) -> np.ndarray:
        """Upscale inteligente con LANCZOS"""
        h, w = image.shape[:2]
        
        if w < 1000:
            scale = 1000 / w
            new_w = int(w * scale)
            new_h = int(h * scale)
            return cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4)
        
        return image
```

---

## 4. EJECUTOR OCR

```python
import asyncio
import time
from typing import Optional

class OCRExecutor:
    """Ejecuta OCR con backend seleccionado"""
    
    def __init__(self, registry: BackendRegistry):
        self.registry = registry
        self.cache = LRICache(maxsize=1000)
    
    async def execute(
        self,
        image_bytes: bytes,
        backend: str = "auto",
        content_analysis: Optional[ContentAnalysis] = None,
        prompt: Optional[str] = None
    ) -> OCRResult:
        start_time = time.time()
        
        # 1. Check cache
        cache_key = self._get_cache_key(image_bytes, backend)
        cached = self.cache.get(cache_key)
        if cached:
            return cached
        
        # 2. Seleccionar backend
        if backend == "auto":
            backend = self._select_backend(content_analysis)
        
        # 3. Obtener instancia
        ocr_backend = self.registry.get(backend)
        if not ocr_backend:
            raise ValueError(f"Backend no encontrado: {backend}")
        
        # 4. Ejecutar OCR
        try:
            result = await ocr_backend.process_image(
                image_bytes,
                prompt=prompt
            )
        except Exception as e:
            # Fallback a siguiente backend
            result = await self._fallback_execute(image_bytes, backend, e)
        
        # 5. Calcular tiempo
        result.processing_time = time.time() - start_time
        
        # 6. Guardar en cache
        self.cache.set(cache_key, result)
        
        return result
    
    def _select_backend(self, content_analysis: Optional[ContentAnalysis]) -> str:
        """Selecciona backend óptimo"""
        if content_analysis:
            return content_analysis.recommended_backend
        
        # Fallback: orden de preferencia
        return "paddleocr"  # Gratis, rápido, buena calidad
    
    async def _fallback_execute(
        self,
        image_bytes: bytes,
        failed_backend: str,
        error: Exception
    ) -> OCRResult:
        """Fallback a siguiente backend en caso de error"""
        fallback_chain = [
            "paddleocr", "surya", "tesseract",
            "mistral", "glm-4v", "gpt-4v"
        ]
        
        for backend_name in fallback_chain:
            if backend_name == failed_backend:
                continue
            
            backend = self.registry.get(backend_name)
            if not backend:
                continue
            
            try:
                return await backend.process_image(image_bytes)
            except:
                continue
        
        raise Exception(f"All backends failed. Last error: {error}")
    
    def _get_cache_key(self, image_bytes: bytes, backend: str) -> str:
        """Genera clave de cache"""
        import hashlib
        return hashlib.sha256(image_bytes + backend.encode()).hexdigest()
```

---

## 5. POSTPROCESADOR

```python
import re
from datetime import datetime

class TextPostprocessor:
    """Normaliza y limpia texto OCR"""
    
    def normalize(self, text: str) -> str:
        # 1. Limpiar whitespace
        text = self._normalize_whitespace(text)
        
        # 2. Corregir errores comunes
        text = self._fix_common_errors(text)
        
        # 3. Normalizar fechas
        text = self._normalize_dates(text)
        
        # 4. Normalizar monedas
        text = self._normalize_currencies(text)
        
        return text
    
    def _normalize_whitespace(self, text: str) -> str:
        """Normaliza espacios en blanco"""
        # Múltiples espacios a uno
        text = re.sub(r' +', ' ', text)
        # Múltiples líneas vacías a una
        text = re.sub(r'\n\s*\n', '\n\n', text)
        return text.strip()
    
    def _fix_common_errors(self, text: str) -> str:
        """Corrige errores comunes de OCR"""
        fixes = {
            r'(?<=\d)[.,](?=\d{3})': '',  # Miles: 1.000 -> 1000
            r'(?<=\d)[.,](?=\d{2})': '.',  # Decimales: 1,50 -> 1.50
            r'O(?=\d)': '0',  # O -> 0 antes de número
            r'l(?=\d)': '1',  # l -> 1 antes de número
        }
        
        for pattern, replacement in fixes.items():
            text = re.sub(pattern, replacement, text)
        
        return text
    
    def _normalize_dates(self, text: str) -> str:
        """Normaliza fechas a ISO 8601"""
        date_patterns = [
            (r'(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})', self._parse_date),
            (r'(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})', self._parse_spanish_date),
        ]
        
        for pattern, parser in date_patterns:
            text = re.sub(pattern, lambda m: parser(m), text)
        
        return text
    
    def _normalize_currencies(self, text: str) -> str:
        """Normaliza monedas"""
        currency_patterns = [
            (r'\$', 'USD'),
            (r'€', 'EUR'),
            (r'£', 'GBP'),
            (r'S/', 'PEN'),
            (r'\bCOL\$?\b', 'COP'),
        ]
        
        for pattern, currency in currency_patterns:
            text = re.sub(pattern, currency, text)
        
        return text
```

---

## 6. ESTRUCTURADOR

```python
import json
import re

class DocumentStructurer:
    """Convierte texto OCR a JSON estructurado"""
    
    def __init__(self, llm_provider: LLMProvider):
        self.llm_provider = llm_provider
    
    async def structure(
        self,
        ocr_text: str,
        prompt: str,
        output_format: str = "json"
    ) -> dict:
        system_prompt = self._get_system_prompt(output_format)
        
        response = await self.llm_provider.complete(
            system_prompt=system_prompt,
            user_prompt=f"{prompt}\n\nTexto OCR:\n{ocr_text}",
            temperature=0.1
        )
        
        return self._parse_response(response)
    
    def _get_system_prompt(self, output_format: str) -> str:
        return f"""Eres un asistente especializado en extraer información estructurada de texto OCR.

Instrucciones:
1. Analiza el texto OCR proporcionado
2. Extrae la información relevante según el prompt
3. Responde en formato {output_format}
4. Si un campo no está disponible, usa null
5. Mantén la precisión de los valores originales
6. Para fechas, usa formato ISO 8601
7. Para monedas, incluye el código de moneda

Formato de salida: {output_format}"""
    
    def _parse_response(self, response: str) -> dict:
        """Parsea respuesta del LLM"""
        # Intentar parsear como JSON
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            pass
        
        # Intentar extraer JSON del texto
        json_match = re.search(r'\{[\s\S]*\}', response)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass
        
        # Fallback: devolver como texto
        return {"raw_text": response}
```

---

## 7. ORQUESTADOR PRINCIPAL

```python
from dataclasses import dataclass
from typing import Optional
import time

@dataclass
class ExtractionResult:
    document: ReceivedDocument
    content_analysis: ContentAnalysis
    ocr_result: OCRResult
    structured_data: Optional[dict]
    processing_time: float
    backend_used: str
    confidence: float
    cache_hit: bool

class ExtractionOrchestrator:
    """Coordina todo el pipeline de extracción"""
    
    def __init__(self):
        self.receiver = DocumentReceiver()
        self.detector = ContentDetector()
        self.preprocessor = AdaptivePreprocessor()
        self.executor = OCRExecutor(BackendRegistry())
        self.postprocessor = TextPostprocessor()
        self.estructurador = None  # Se inicializa con LLM
        self.validador = ResultValidator()
    
    async def extract(
        self,
        file_bytes: bytes,
        filename: str,
        backend: str = "auto",
        prompt: Optional[str] = None,
        structuring: bool = True,
        preprocessing: bool = True
    ) -> ExtractionResult:
        start_time = time.time()
        
        # 1. Recibir documento
        document = await self.receiver.receive(file_bytes, filename)
        
        # 2. Detectar contenido
        if preprocessing:
            image = self.preprocessor._load_image(file_bytes)
            content_analysis = self.detector.analyze(image)
        else:
            content_analysis = ContentAnalysis(
                content_type=ContentType.STANDARD_TEXT,
                confidence=0.5,
                recommended_backend=backend,
                preprocessing_level="none",
                estimated_difficulty=0.5
            )
        
        # 3. Preprocesar
        if preprocessing and content_analysis.preprocessing_level != "none":
            processed_image = await self.preprocessor.process(file_bytes, content_analysis)
            processed_bytes = self._image_to_bytes(processed_image)
        else:
            processed_bytes = file_bytes
        
        # 4. Ejecutar OCR
        ocr_result = await self.executor.execute(
            processed_bytes,
            backend=content_analysis.recommended_backend if backend == "auto" else backend,
            content_analysis=content_analysis
        )
        
        # 5. Postprocesar
        ocr_result.text = self.postprocessor.normalize(ocr_result.text)
        
        # 6. Estructurar (opcional)
        structured_data = None
        if structuring and prompt and self.estructurador:
            structured_data = await self.estructurador.structure(
                ocr_result.text,
                prompt
            )
        
        # 7. Validar
        validation = self.validador.validate(ocr_result, structured_data)
        
        return ExtractionResult(
            document=document,
            content_analysis=content_analysis,
            ocr_result=ocr_result,
            structured_data=structured_data,
            processing_time=time.time() - start_time,
            backend_used=ocr_result.backend,
            confidence=ocr_result.confidence,
            cache_hit=False
        )
```

---

## 8. FLUJO COMPLETO

```
1. Recibir archivo
   ↓
2. Validar formato y tamaño
   ↓
3. Calcular hash (para cache)
   ↓
4. Detectar tipo de contenido
   ↓
5. Seleccionar backend OCR
   ↓
6. Preprocesar imagen (si es necesario)
   ↓
7. Ejecutar OCR
   ↓
8. Postprocesar texto
   ↓
9. Estructurar con LLM (opcional)
   ↓
10. Validar resultado
   ↓
11. Devolver ExtractionResult
```

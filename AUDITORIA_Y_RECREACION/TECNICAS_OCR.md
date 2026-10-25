# GUÍA COMPLETA DE TÉCNICAS OCR INDUSTRIALES

## RESUMEN
Documentación completa de todas las técnicas OCR disponibles (gratuitas y de pago), con comparativas, casos de uso y recomendaciones de implementación.

---

## 1. TÉCNICAS OCR GRATUITAS / OPEN SOURCE

### 1.1 PaddleOCR
**Desarrollador:** Baidu Research
**Licencia:** Apache 2.0
**Idiomas:** 80+ idiomas (incluido español)

```bash
pip install paddlepaddle paddleocr
```

**Características:**
- Motor de detección de texto (PP-OCRv4)
- Reconocimiento de caracteres (PP-OCRv4)
- Clasificación de ángulos
- Reconocimiento de tablas
- Reconocimiento de fórmulas matemáticas
- Soporte GPU

**Modelos disponibles:**
| Modelo | Velocidad | Precisión | Tamaño |
|--------|-----------|-----------|--------|
| PP-OCRv4 | Rápido | 99%+ en-print | 15MB |
| PP-OCRv3 | Medio | 98%+ en-print | 12MB |
| PP-OCRv2 | Lento | 97%+ en-print | 10MB |

**Código de ejemplo:**
```python
from paddleocr import PaddleOCR

ocr = PaddleOCR(use_angle_cls=True, lang='es')
result = ocr.ocr('image.jpg', cls=True)

for line in result:
    bbox, (text, confidence) = line[0], line[1]
    print(f"Text: {text}, Confidence: {confidence}")
```

---

### 1.2 Tesseract OCR
**Desarrollador:** Google (originally HP)
**Licencia:** Apache 2.0
**Idiomas:** 100+ idiomas

```bash
# Instalación Windows
# Descargar installer de https://github.com/UB-Mannheim/tesseract/wiki
pip install pytesseract
```

**Características:**
- LSTM neural network
- Modo página completa
- Modo línea por línea
- Modo palabra por palabra
- Modo bloque
- Output en texto, hOCR, TSV, ALTO, PDF

**Idiomas españoles disponibles:**
- `spa` - Español estándar
- `spa_old` - Español antiguo
- `cat` - Catalán
- `glg` - Gallego
- `eus` - Euskera

**Código de ejemplo:**
```python
import pytesseract
from PIL import Image

# Configuración optimizada
custom_config = r'--oem 3 --psm 6'
text = pytesseract.image_to_string(
    Image.open('image.jpg'),
    lang='spa',
    config=custom_config
)

# Con bounding boxes
data = pytesseract.image_to_data(
    Image.open('image.jpg'),
    lang='spa',
    output_type=pytesseract.Output.DICT
)
```

---

### 1.3 EasyOCR
**Desarrollador:** Jaided AI
**Licencia:** Apache 2.0
**Idiomas:** 80+ idiomas

```bash
pip install easyocr
```

**Características:**
- Basado en PyTorch
- Detección de texto con CRAFT
- Reconocimiento con CRNN
- GPU automática si está disponible
- Soporte personalizado de modelo

**Código de ejemplo:**
```python
import easyocr

reader = easyocr.Reader(['es', 'en'])
result = reader.readtext('image.jpg')

for (bbox, text, prob) in result:
    print(f"Text: {text}, Probability: {prob}")
```

---

### 1.4 Surya OCR
**Desarrollador:** VikParuchuri
**Licencia:** GPL-3.0
**Idiomas:** 90+ idiomas

```bash
pip install surya-ocr
```

**Características:**
- Detección de texto con modelo Transformer
- Reconocimiento con decoder-only Transformer
- Soporte de layout detection
- Tablas y formularios
- Velocidad > 4x Tesseract
- Precisión superior en documentos complejos

**Código de ejemplo:**
```python
from surya.detection import DetectionPredictor
from surya.recognition import RecognitionPredictor

det_predictor = DetectionPredictor()
rec_predictor = RecognitionPredictor()

images = [Image.open("doc.jpg")]
det_results = det_predictor(images)
rec_results = rec_predictor(images, det_results)
```

---

### 1.5 DocTR
**Desarrollador:** Mindee
**Licencia:** Apache 2.0
**Idiomas:** Multiidioma

```bash
pip install python-doctr[torch]  # PyTorch
pip install python-doctr[tf]     # TensorFlow
```

**Características:**
- Arquitectura DBNet para detección
- CRNN para reconocimiento
- OTR (Object Text Recognition)
- Análisis de documentos completos
- Extracción de tablas
- Soporte GPU

**Código de ejemplo:**
```python
from doctr.io import DocumentFile
from doctr.models import ocr_predictor

model = ocr_predictor(pretrained=True)
doc = DocumentFile.from_pdf("document.pdf")
result = model(doc)

for page in result.pages:
    for block in page.blocks:
        for line in block.lines:
            for word in line.words:
                print(f"{word.value} ({word.confidence:.2f})")
```

---

### 1.6 Kraken
**Desarrollador:** Ketos
**Licencia:** Apache 2.0
**Idiomas:** Multiidioma (especializado en históricos)

```bash
pip install kraken
```

**Características:**
- Especializado en documentos históricos
- Entrenamiento personalizado
- Segmentation y recognition
- Soporte RTL
- Modelos pre-entrenados

---

### 1.7 TrOCR (Microsoft)
**Desarrollador:** Microsoft Research
**Licencia:** MIT
**Idiomas:** Inglés principal

```bash
pip install transformers torch
```

**Características:**
- Transformer-based (encoder-decoder)
- Pre-entrenado en IAM dataset
- Fine-tuning capabilities
- State-of-the-art en inglés

```python
from transformers import TrOCRProcessor, VisionEncoderDecoderModel
from PIL import Image

processor = TrOCRProcessor.from_pretrained("microsoft/trocr-base-handwritten")
model = VisionEncoderDecoderModel.from_pretrained("microsoft/trocr-base-handwritten")

image = Image.open("image.jpg").convert("RGB")
pixel_values = processor(images=image, return_tensors="pt").pixel_values
generated_ids = model.generate(pixel_values)
text = processor.batch_decode(generated_ids, skip_special_tokens=True)[0]
```

---

### 1.8 VLM (Visual Language Models) - GRATUITOS

#### LLaVA (Large Language and Vision Assistant)
```python
from llava.model import LlavaLlamaForCausalLM

# Modelos disponibles:
# - llava-1.5-7b
# - llava-1.5-13b
# - llava-1.5-34b
```

#### Qwen-VL (Qwen Vision Language)
```python
from transformers import AutoModelForCausalLM, AutoProcessor

model = AutoModelForCausalLM.from_pretrained("Qwen/Qwen-VL")
processor = AutoProcessor.from_pretrained("Qwen/Qwen-VL")
```

#### InternVL
```python
# Modelo multimodal de Shanghai AI Lab
# Precisión competitiva con GPT-4V en benchmarks
```

---

## 2. TÉCNICAS OCR DE PAGO

### 2.1 OpenAI GPT-4V / GPT-4o
**Costo:** $0.01-$0.03 por imagen
**Precisión:** 99%+ en documentos impresos

```python
from openai import OpenAI

client = OpenAI(api_key="your-key")
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{
        "role": "user",
        "content": [
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}},
            {"type": "text", "text": "Extract all text from this document"}
        ]
    }]
)
```

**Ventajas:**
- Entiende contexto y semántica
- Maneja documentos complejos
- Output estructurado (JSON)
- Multiidioma nativo

---

### 2.2 Anthropic Claude 3.5 Sonnet / Claude 3 Opus
**Costo:** $0.003-$0.015 por imagen
**Precisión:** 99%+ en documentos impresos

```python
import anthropic

client = anthropic.Anthropic(api_key="your-key")
response = client.messages.create(
    model="claude-3-5-sonnet-20241022",
    max_tokens=4096,
    messages=[{
        "role": "user",
        "content": [
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": base64_image}},
            {"type": "text", "text": "Extract all text from this document"}
        ]
    }]
)
```

---

### 2.3 Google Gemini 2.0 Flash / Gemini 2.5 Pro
**Costo:** $0.0001-$0.00125 por imagen
**Precisión:** 98%+ en documentos impresos

```python
import google.generativeai as genai

model = genai.GenerativeModel("gemini-2.0-flash")
response = model.generate_content([
    {"mime_type": "image/jpeg", "data": base64_image},
    "Extract all text from this image"
])
```

**Ventajas:**
- Muy bajo costo
- Alta velocidad
- Soporte de documentos largos
- Contexto de 1M tokens

---

### 2.4 GLM-4V (ZhipuAI)
**Costo:** ~$0.01 por imagen
**Precisión:** 97%+ en documentos impresos

```python
from zhipuai import ZhipuAI

client = ZhipuAI(api_key="your-key")
response = client.chat.completions.create(
    model="glm-4v-flash",
    messages=[{
        "role": "user",
        "content": [
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}},
            {"type": "text", "text": "Extrae todo el texto de esta imagen"}
        ]
    }]
)
```

---

### 2.5 Mistral OCR
**Costo:** $1 por 1000 páginas
**Precisión:** 99%+ en documentos impresos

```python
from mistralai import MistralAI

client = MistralAI(api_key="your-key")
response = client.ocr.process(
    model="mistral-ocr-latest",
    document={"type": "document_url", "document_url": f"data:application/pdf;base64,{base64_pdf}"}
)
```

**Ventajas:**
- Soporte nativo de PDF
- Output en Markdown
- Tablas estructuradas
- Muy rápido

---

### 2.6 Google Cloud Vision API
**Costo:** $1.50 por 1000 imágenes
**Precisión:** 98%+ en documentos impresos

```python
from google.cloud import vision

client = vision.ImageAnnotatorClient()
image = vision.Image(content=image_bytes)
response = client.document_text_detection(image=image)
text = response.full_text_annotation.text
```

---

### 2.7 Azure AI Document Intelligence (Form Recognizer)
**Costo:** $10 por 1000 páginas (Standard)
**Precisión:** 99%+ en documentos estructurados

```python
from azure.ai.documentintelligence import DocumentIntelligenceClient

client = DocumentIntelligenceClient(endpoint, key)
poller = client.begin_analyze_document("prebuilt-read", body=pdf_bytes)
result = poller.result()
```

**Modelos pre-construidos:**
- `prebuilt-read` - OCR general
- `prebuilt-layout` - Layout analysis
- `prebuilt-invoice` - Facturas
- `prebuilt-receipt` - Recibos
- `prebuilt-id` - Documentos de identidad
- `prebuilt-taxus` - Impuestos US

---

### 2.8 AWS Textract
**Costo:** $0.015 por página (primera millón)
**Precisión:** 98%+ en documentos estructurados

```python
import boto3

client = boto3.client('textract')
response = client.detect_document_text(Document={'Bytes': image_bytes})
```

**Capacidades:**
- Detección de texto
- Análisis de formularios
- Análisis de tablas
- Query engine (preguntas sobre el documento)

---

### 2.9 Amazon Bedrock (Claude/GPT via AWS)
**Costo:** Variable según modelo
**Precisión:** Variable

```python
import boto3

bedrock = boto3.client('bedrock-runtime')
response = bedrock.invoke_model(
    modelId="anthropic.claude-3-5-sonnet-20241022-v2:0",
    body=json.dumps({
        "messages": [{"role": "user", "content": [...]}],
        "max_tokens": 4096
    })
)
```

---

### 2.10 Nomic Embed (Para embedding de documentos)
**Costo:** Gratuito (local) / $0.0001 por 1K tokens (API)
**Uso:** Embeddings para búsqueda semántica

---

## 3. COMPARATIVA DETALLADA

### Precisión por tipo de documento

| Backend | Documento impreso | Manuscrito | Tablas | Formularios | PDF complejo |
|---------|-------------------|------------|--------|-------------|--------------|
| PaddleOCR | 99% | 85% | 95% | 90% | 95% |
| Tesseract | 95% | 60% | 70% | 65% | 80% |
| EasyOCR | 97% | 80% | 85% | 80% | 90% |
| Surya | 98% | 85% | 90% | 85% | 92% |
| GPT-4V | 99% | 95% | 98% | 97% | 99% |
| Claude | 99% | 94% | 97% | 96% | 98% |
| Gemini | 98% | 90% | 95% | 92% | 96% |
| GLM-4V | 97% | 88% | 92% | 90% | 95% |
| Mistral | 99% | 92% | 96% | 94% | 98% |
| Google Vision | 98% | 85% | 92% | 88% | 95% |
| Azure DocAI | 99% | 90% | 98% | 97% | 99% |
| AWS Textract | 98% | 88% | 97% | 95% | 97% |

### Velocidad (por página)

| Backend | Velocidad (seg/pág) | Throughput |
|---------|---------------------|------------|
| Tesseract | 0.5-2 | 30-120/min |
| PaddleOCR | 0.2-0.5 | 120-300/min |
| EasyOCR | 0.3-1 | 60-200/min |
| Surya | 0.1-0.3 | 200-600/min |
| GPT-4V | 2-5 | 12-30/min |
| Claude | 2-4 | 15-30/min |
| Gemini | 1-3 | 20-60/min |
| GLM-4V | 1-3 | 20-60/min |
| Mistral | 0.5-2 | 30-120/min |
| Google Vision | 0.5-1 | 60-120/min |
| Azure DocAI | 1-3 | 20-60/min |
| AWS Textract | 1-2 | 30-60/min |

### Costo (por 1000 páginas)

| Backend | Costo por 1K páginas | Costo mensual estimado (10K docs) |
|---------|----------------------|-----------------------------------|
| Tesseract | $0 (local) | $0 |
| PaddleOCR | $0 (local) | $0 |
| EasyOCR | $0 (local) | $0 |
| Surya | $0 (local) | $0 |
| GPT-4V | $10-30 | $100-300 |
| Claude | $3-15 | $30-150 |
| Gemini | $0.1-1.25 | $1-12.5 |
| GLM-4V | ~$10 | ~$100 |
| Mistral | $1 | $10 |
| Google Vision | $1.50 | $15 |
| Azure DocAI | $10 | $100 |
| AWS Textract | $15 | $150 |

---

## 4. RECOMENDACIONES POR CASO DE USO

### Facturas y recibos
1. **Mistral OCR** - Mejor relación calidad/precio
2. **Google Vision** - Buen balance
3. **PaddleOCR** - Gratis, buena precisión

### Documentos legales
1. **GPT-4V** - Entiende contexto legal
2. **Claude** - Excelente en documentos largos
3. **Azure DocAI** - Modelos pre-entrenados

### Manuscritos
1. **GPT-4V** - Mejor en manuscritos
2. **Claude** - Muy bueno
3. **Surya** - Mejor open source

### Tablas y formularios
1. **Azure DocAI** - Modelos especializados
2. **AWS Textract** - Análisis de tablas
3. **PaddleOCR** - Buena detección de tablas

### Alto volumen (>10K docs/día)
1. **PaddleOCR** (local) - Sin costo
2. **Mistral** - Bajo costo
3. **Gemini** - Muy bajo costo

### Presupuesto mínimo
1. **PaddleOCR** + **Tesseract** (fallback)
2. **Surya** para documentos complejos
3. **Gemini** para estructuración (muy barato)

---

## 5. CADENA DE FALLBACK RECOMENDADA

```
PaddleOCR (local, rápido)
  ↓ si falla o calidad baja
Surya OCR (local, mejor calidad)
  ↓ si falla
Tesseract (local, universal)
  ↓ si requiere más precisión
Mistral OCR (pago, bajo costo)
  ↓ si requiere comprensión semántica
GPT-4V / Claude (pago, máxima calidad)
```

---

## 6. OPTIMIZACIONES DE RENDIMIENTO

### Procesamiento paralelo
```python
import asyncio
from concurrent.futures import ThreadPoolExecutor

executor = ThreadPoolExecutor(max_workers=4)

async def process_batch(files: list[File]) -> list[OCRResult]:
    loop = asyncio.get_event_loop()
    tasks = [
        loop.run_in_executor(executor, process_file, f)
        for f in files
    ]
    return await asyncio.gather(*tasks)
```

### Caching inteligente
```python
import hashlib
from functools import lru_cache

def get_cache_key(file_bytes: bytes, backend: str) -> str:
    return hashlib.sha256(file_bytes + backend.encode()).hexdigest()

@lru_cache(maxsize=1000)
def cached_ocr(cache_key: str, file_bytes: bytes, backend: str):
    return process_ocr(file_bytes, backend)
```

### Batch processing
```python
# Para Tesseract
config = '--oem 3 --psm 6 -c tessedit_create_tsv=1'

# Para PaddleOCR
ocr = PaddleOCR(use_angle_cls=True, lang='es', use_gpu=True)
result = ocr.ocr('image.jpg', cls=True)  # GPU batch
```

---

## 7. PREPROCESSING AVANZADO

### Pipeline completo
```python
import cv2
import numpy as np
from PIL import Image

def advanced_preprocess(image: np.ndarray) -> np.ndarray:
    # 1. Deskew
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    coords = np.column_stack(np.where(gray > 0))
    angle = cv2.minAreaRect(coords)[-1]
    if angle < -45:
        angle = -(90 + angle)
    else:
        angle = -angle
    (h, w) = image.shape[:2]
    center = (w // 2, h // 2)
    M = cv2.getRotationMatrix2D(center, angle, 1.0)
    image = cv2.warpAffine(image, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    
    # 2. Denoise
    image = cv2.fastNlMeansDenoisingColored(image, None, 10, 10, 7, 21)
    
    # 3. CLAHE (Contrast Limited Adaptive Histogram Equalization)
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    l = clahe.apply(l)
    lab = cv2.merge([l, a, b])
    image = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
    
    # 4. Gamma correction
    gamma = 1.5
    look_up_table = np.array([((i / 255.0) ** (1 / gamma)) * 255 for i in range(256)]).astype("uint8")
    image = cv2.LUT(image, look_up_table)
    
    # 5. Sharpen
    kernel = np.array([[-1, -1, -1], [-1, 9, -1], [-1, -1, -1]])
    image = cv2.filter2D(image, -1, kernel)
    
    # 6. Binarization (adaptive threshold)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    binary = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
    
    return cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)
```

---

## 8. MÉTRICAS DE EVALUACIÓN

### CER (Character Error Rate)
```python
def calculate_cer(reference: str, hypothesis: str) -> float:
    """Calcula Character Error Rate"""
    import Levenshtein
    return Levenshtein.distance(reference, hypothesis) / len(reference)

# CER < 0.05 = Excelente
# CER 0.05-0.10 = Bueno
# CER 0.10-0.20 = Aceptable
# CER > 0.20 = Necesita mejora
```

### WER (Word Error Rate)
```python
def calculate_wer(reference: str, hypothesis: str) -> float:
    """Calcula Word Error Rate"""
    ref_words = reference.split()
    hyp_words = hypothesis.split()
    import Levenshtein
    return Levenshtein.distance(ref_words, hyp_words) / len(ref_words)
```

### Word-level confidence
```python
def calculate_confidence(ocr_result: dict) -> float:
    """Calcula confianza promedio"""
    confidences = [word['confidence'] for word in ocr_result['words']]
    return sum(confidences) / len(confidences) if confidences else 0
```

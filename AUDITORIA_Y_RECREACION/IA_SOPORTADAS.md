# GUÍA COMPLETA DE INTEGRACIONES IA SOPORTADAS

## RESUMEN
Documentación completa de todas las integraciones de IA para OCR y estructuración, incluyendo modelos locales, cloud y sus configuraciones.

---

## 1. CATEGORÍAS DE IA

### 1.1 IA para OCR (Extracción de imagen a texto)
Modelos que aceptan imágenes y devuelven texto.

### 1.2 IA para Estructuración (Texto a JSON)
Modelos de lenguaje que transforman texto OCR en datos estructurados.

### 1.3 IA para Embeddings (Búsqueda semántica)
Modelos que generan vectores para búsqueda y similitud.

### 1.4 IA para Clasificación
Modelos que clasifican documentos por tipo.

---

## 2. MODELOS PARA OCR (VISIÓN)

### 2.1 OpenAI GPT-4V / GPT-4o
```python
# Configuración
OPENAI_API_KEY = "sk-..."
OPENAI_BASE_URL = "https://api.openai.com/v1"

# Modelos disponibles
models = {
    "gpt-4o": {"cost": 0.005, "vision": True, "max_tokens": 128000},
    "gpt-4o-mini": {"cost": 0.00015, "vision": True, "max_tokens": 128000},
    "gpt-4-turbo": {"cost": 0.01, "vision": True, "max_tokens": 128000},
    "gpt-4-vision-preview": {"cost": 0.01, "vision": True, "max_tokens": 4096},
}

# Ejemplo de uso
from openai import OpenAI

client = OpenAI(api_key=OPENAI_API_KEY)

def ocr_with_gpt4v(image_base64: str, prompt: str = "Extract all text") -> str:
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}},
                {"type": "text", "text": prompt}
            ]
        }],
        max_tokens=4096,
        temperature=0.1
    )
    return response.choices[0].message.content
```

---

### 2.2 Anthropic Claude 3.5 Sonnet / Claude 3 Opus
```python
# Configuración
ANTHROPIC_API_KEY = "sk-ant-..."

# Modelos disponibles
models = {
    "claude-3-5-sonnet-20241022": {"cost": 0.003, "vision": True, "max_tokens": 8192},
    "claude-3-opus-20240229": {"cost": 0.015, "vision": True, "max_tokens": 4096},
    "claude-3-haiku-20240307": {"cost": 0.00025, "vision": True, "max_tokens": 4096},
}

# Ejemplo de uso
import anthropic

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

def ocr_with_claude(image_base64: str, prompt: str = "Extract all text") -> str:
    response = client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=4096,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": image_base64
                    }
                },
                {"type": "text", "text": prompt}
            ]
        }]
    )
    return response.content[0].text
```

---

### 2.3 Google Gemini 2.0 Flash / Gemini 2.5 Pro
```python
# Configuración
GOOGLE_API_KEY = "AIza..."

# Modelos disponibles
models = {
    "gemini-2.0-flash": {"cost": 0.0001, "vision": True, "context": 1000000},
    "gemini-2.0-flash-lite": {"cost": 0.000075, "vision": True, "context": 1000000},
    "gemini-2.5-pro-exp-03-25": {"cost": 0.00125, "vision": True, "context": 1000000},
    "gemini-1.5-pro": {"cost": 0.00125, "vision": True, "context": 2000000},
    "gemini-1.5-flash": {"cost": 0.000075, "vision": True, "context": 1000000},
}

# Ejemplo de uso
import google.generativeai as genai

genai.configure(api_key=GOOGLE_API_KEY)
model = genai.GenerativeModel("gemini-2.0-flash")

def ocr_with_gemini(image_base64: str, prompt: str = "Extract all text") -> str:
    import base64
    image_data = base64.b64decode(image_base64)
    response = model.generate_content([
        {"mime_type": "image/jpeg", "data": image_data},
        prompt
    ])
    return response.text
```

---

### 2.4 GLM-4V (ZhipuAI)
```python
# Configuración
ZHIPUAI_API_KEY = "..."

# Modelos disponibles
models = {
    "glm-4v-flash": {"cost": 0.01, "vision": True, "max_tokens": 2048},
    "glm-4v-plus": {"cost": 0.01, "vision": True, "max_tokens": 4096},
    "glm-4v": {"cost": 0.01, "vision": True, "max_tokens": 4096},
}

# Ejemplo de uso
from zhipuai import ZhipuAI

client = ZhipuAI(api_key=ZHIPUAI_API_KEY)

def ocr_with_glm4v(image_base64: str, prompt: str = "Extrae todo el texto") -> str:
    response = client.chat.completions.create(
        model="glm-4v-flash",
        messages=[{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}},
                {"type": "text", "text": prompt}
            ]
        }],
        timeout=60
    )
    return response.choices[0].message.content
```

---

### 2.5 Qwen-VL (Alibaba)
```python
# Configuración
DASHSCOPE_API_KEY = "..."

# Modelos disponibles
models = {
    "qwen-vl-max": {"cost": 0.001, "vision": True},
    "qwen-vl-plus": {"cost": 0.0003, "vision": True},
    "qwen-turbo-vl": {"cost": 0.0001, "vision": True},
}

# Ejemplo con SDK local
from transformers import AutoModelForCausalLM, AutoProcessor

model = AutoModelForCausalLM.from_pretrained("Qwen/Qwen2-VL-7B-Instruct")
processor = AutoProcessor.from_pretrained("Qwen/Qwen2-VL-7B-Instruct")
```

---

### 2.6 LLaVA (Open Source)
```python
# Modelos locales
models = {
    "llava-1.5-7b": {"size": "7B", "quality": "Buena"},
    "llava-1.5-13b": {"size": "13B", "quality": "Muy buena"},
    "llava-1.6-34b": {"size": "34B", "quality": "Excelente"},
    "llava-next-72b": {"size": "72B", "quality": "State-of-the-art"},
}

# Ejemplo con llama.cpp
from llama_cpp import Llama

model = Llama(model_path="llava-v1.5-7b.gguf", n_ctx=2048)
```

---

### 2.7 InternVL (Open Source)
```python
# Shanghai AI Lab
models = {
    "internvl2-1b": {"size": "1B", "quality": "Buena"},
    "internvl2-8b": {"size": "8B", "quality": "Muy buena"},
    "internvl2-26b": {"size": "26B", "quality": "Excelente"},
    "internvl2-40b": {"size": "40B", "quality": "State-of-the-art"},
}
```

---

## 3. MODELOS PARA ESTRUCTURACIÓN (LLM)

### 3.1 OpenAI
```python
models = {
    "gpt-4o": {"cost": 0.005, "context": 128000, "quality": "Excelente"},
    "gpt-4o-mini": {"cost": 0.00015, "context": 128000, "quality": "Muy buena"},
    "gpt-4-turbo": {"cost": 0.01, "context": 128000, "quality": "Excelente"},
    "o1-preview": {"cost": 0.015, "context": 128000, "quality": "State-of-the-art"},
    "o1-mini": {"cost": 0.003, "context": 128000, "quality": "Excelente"},
}
```

### 3.2 DeepSeek
```python
models = {
    "deepseek-v4": {"cost": 0.0002, "context": 128000, "quality": "Muy buena"},
    "deepseek-chat": {"cost": 0.0002, "context": 128000, "quality": "Muy buena"},
    "deepseek-coder": {"cost": 0.0002, "context": 128000, "quality": "Muy buena"},
}

# Configuración
DEEPSEEK_API_KEY = "..."
DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"

from openai import OpenAI
client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)
```

### 3.3 Mistral
```python
models = {
    "mistral-large-latest": {"cost": 0.002, "context": 128000, "quality": "Muy buena"},
    "mistral-medium-latest": {"cost": 0.0027, "context": 32000, "quality": "Buena"},
    "mistral-small-latest": {"cost": 0.001, "context": 32000, "quality": "Buena"},
    "open-mixtral-8x22b": {"cost": 0.002, "context": 65536, "quality": "Muy buena"},
}
```

### 3.4 Anthropic
```python
models = {
    "claude-3-5-sonnet-20241022": {"cost": 0.003, "context": 200000, "quality": "Excelente"},
    "claude-3-opus-20240229": {"cost": 0.015, "context": 200000, "quality": "State-of-the-art"},
    "claude-3-haiku-20240307": {"cost": 0.00025, "context": 200000, "quality": "Buena"},
}
```

### 3.5 Google
```python
models = {
    "gemini-2.0-flash": {"cost": 0.0001, "context": 1000000, "quality": "Muy buena"},
    "gemini-2.5-pro-exp-03-25": {"cost": 0.00125, "context": 1000000, "quality": "Excelente"},
    "gemini-1.5-pro": {"cost": 0.00125, "context": 2000000, "quality": "Excelente"},
}
```

### 3.6 Qwen (Alibaba)
```python
models = {
    "qwen-max": {"cost": 0.0008, "context": 32000, "quality": "Muy buena"},
    "qwen-plus": {"cost": 0.0004, "context": 131072, "quality": "Buena"},
    "qwen-turbo": {"cost": 0.0002, "context": 131072, "quality": "Buena"},
}
```

### 3.7 GLM-4 (ZhipuAI)
```python
models = {
    "glm-4": {"cost": 0.001, "context": 128000, "quality": "Muy buena"},
    "glm-4-flash": {"cost": 0.0001, "context": 128000, "quality": "Buena"},
    "glm-4-air": {"cost": 0.0007, "context": 128000, "quality": "Buena"},
    "glm-4-long": {"cost": 0.001, "context": 1000000, "quality": "Muy buena"},
}
```

### 3.8 Modelos Locales (Gratis)
```python
# Ollama
ollama_models = {
    "llama3.1": {"size": "8B", "quality": "Buena"},
    "llama3.1:70b": {"size": "70B", "quality": "Muy buena"},
    "mistral": {"size": "7B", "quality": "Buena"},
    "mixtral": {"size": "8x7B", "quality": "Muy buena"},
    "codellama": {"size": "7B", "quality": "Buena (código)"},
    "phi3": {"size": "3.8B", "quality": "Buena"},
    "qwen2": {"size": "7B", "quality": "Muy buena"},
    "gemma2": {"size": "9B", "quality": "Buena"},
}

# LM Studio
lmstudio_models = {
    "local-model": {"quality": "Variable"},
}
```

### 3.9 OpenRouter (Multi-provider)
```python
# Acceso a múltiples proveedores
OPENROUTER_API_KEY = "..."

models = {
    "openai/gpt-4o": {"cost": 0.005, "quality": "Excelente"},
    "anthropic/claude-3.5-sonnet": {"cost": 0.003, "quality": "Excelente"},
    "google/gemini-2.0-flash": {"cost": 0.0001, "quality": "Muy buena"},
    "meta-llama/llama-3.1-405b-instruct": {"cost": 0.003, "quality": "Excelente"},
    "mistralai/mixtral-8x22b-instruct": {"cost": 0.002, "quality": "Muy buena"},
}

from openai import OpenAI
client = OpenAI(
    api_key=OPENROUTER_API_KEY,
    base_url="https://openrouter.ai/api/v1"
)
```

### 3.10 Groq (Ultra-rápido, gratis tier)
```python
GROQ_API_KEY = "..."

models = {
    "llama-3.1-70b-versatile": {"cost": 0, "quality": "Muy buena", "speed": "Ultra rápido"},
    "llama-3.1-8b-instant": {"cost": 0, "quality": "Buena", "speed": "Ultra rápido"},
    "mixtral-8x7b-32768": {"cost": 0, "quality": "Buena", "speed": "Ultra rápido"},
    "gemma2-9b-it": {"cost": 0, "quality": "Buena", "speed": "Ultra rápido"},
}

from openai import OpenAI
client = OpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1"
)
```

### 3.11 Together AI
```python
TOGETHER_API_KEY = "..."

models = {
    "meta-llama/Llama-3-70b-chat-hf": {"cost": 0.0009, "quality": "Muy buena"},
    "meta-llama/Llama-3-8b-chat-hf": {"cost": 0.0002, "quality": "Buena"},
    "mistralai/Mixtral-8x22B-Instruct-v0.1": {"cost": 0.0012, "quality": "Muy buena"},
    "Qwen/Qwen2-72B-Instruct": {"cost": 0.0009, "quality": "Excelente"},
}
```

### 3.12 Fireworks AI
```python
FIREWORKS_API_KEY = "..."

models = {
    "accounts/fireworks/models/llama-v3p1-70b-instruct": {"cost": 0.0009, "quality": "Muy buena"},
    "accounts/fireworks/models/mixtral-8x22b-instruct": {"cost": 0.001, "quality": "Muy buena"},
    "accounts/fireworks/models/qwen2-72b-instruct": {"cost": 0.0009, "quality": "Excelente"},
}
```

### 3.13 Azure OpenAI
```python
AZURE_OPENAI_ENDPOINT = "https://your-resource.openai.azure.com/"
AZURE_OPENAI_API_KEY = "..."

# Configuración
from openai import AzureOpenAI
client = AzureOpenAI(
    api_key=AZURE_OPENAI_API_KEY,
    api_version="2024-02-15-preview",
    azure_endpoint=AZURE_OPENAI_ENDPOINT
)

models = {
    "gpt-4o": {"cost": "Variable", "quality": "Excelente"},
    "gpt-4o-mini": {"cost": "Variable", "quality": "Muy buena"},
    "gpt-4-turbo": {"cost": "Variable", "quality": "Excelente"},
}
```

### 3.14 Amazon Bedrock
```python
import boto3

bedrock = boto3.client('bedrock-runtime')

models = {
    "anthropic.claude-3-5-sonnet-20241022-v2:0": {"quality": "Excelente"},
    "anthropic.claude-3-opus-20240229-v1:0": {"quality": "State-of-the-art"},
    "amazon.titan-text-express-v1": {"quality": "Buena"},
    "meta.llama3-70b-instruct-v1:0": {"quality": "Muy buena"},
    "mistral.mixtral-8x7b-instruct-v0:1": {"quality": "Muy buena"},
    "cohere.command-text-v14": {"quality": "Buena"},
}
```

### 3.15 xAI (Grok)
```python
XAI_API_KEY = "..."

from openai import OpenAI
client = OpenAI(
    api_key=XAI_API_KEY,
    base_url="https://api.x.ai/v1"
)

models = {
    "grok-2": {"cost": 0.01, "quality": "Excelente"},
    "grok-2-mini": {"cost": 0.002, "quality": "Muy buena"},
}
```

---

## 4. CREDENCIALES Y CONFIGURACIÓN

### Archivo .env
```env
# OCR Backends
ZHIPUAI_API_KEY=your_zhipuai_key
MISTRAL_API_KEY=your_mistral_key
GOOGLE_VISION_CREDENTIALS=path/to/service-account.json
OPENAI_API_KEY=your_openai_key
ANTHROPIC_API_KEY=your_anthropic_key

# LLM Providers
DEEPSEEK_API_KEY=your_deepseek_key
QWEN_API_KEY=your_qwen_key
GROQ_API_KEY=your_groq_key
TOGETHER_API_KEY=your_together_key
FIREWORKS_API_KEY=your_fireworks_key
OPENROUTER_API_KEY=your_openrouter_key

# Azure
AZURE_OPENAI_ENDPOINT=your_endpoint
AZURE_OPENAI_API_KEY=your_key

# AWS
AWS_ACCESS_KEY_ID=your_key
AWS_SECRET_ACCESS_KEY=your_secret
AWS_REGION=us-east-1

# Google
GOOGLE_API_KEY=your_google_key

# Local
OLLAMA_BASE_URL=http://localhost:11434
LM_STUDIO_BASE_URL=http://localhost:1234
```

---

## 5. PATRÓN DE FALLBACK

```python
class LLMFallbackChain:
    """Cadena de fallback para LLMs"""
    
    def __init__(self):
        self.providers = [
            # Orden: mejor calidad/precio primero
            ("groq", "llama-3.1-70b-versatile"),      # Gratis, rápido
            ("deepseek", "deepseek-v4"),               # Muy barato
            ("gemini", "gemini-2.0-flash"),             # Muy barato
            ("qwen", "qwen-max"),                      # Barato
            ("mistral", "mistral-large-latest"),       # Medio
            ("openai", "gpt-4o"),                      # Caro, mejor calidad
            ("anthropic", "claude-3-5-sonnet"),        # Caro, mejor calidad
        ]
    
    async def complete(self, prompt: str) -> str:
        for provider, model in self.providers:
            try:
                result = await self._call_provider(provider, model, prompt)
                return result
            except Exception as e:
                logger.warning(f"Provider {provider} failed: {e}")
                continue
        
        raise Exception("All LLM providers failed")
```

---

## 6. RECOMENDACIONES

### Para OCR (Visión)
1. **Gratis:** PaddleOCR + Surya (local)
2. **Barato:** Gemini Flash ($0.0001/imagen)
3. **Calidad:** GPT-4V o Claude 3.5 ($0.003-$0.01/imagen)

### Para Estructuración
1. **Gratis:** Groq (Llama 3.1 70B) o Ollama (local)
2. **Barato:** DeepSeek V4 ($0.0002/1K tokens)
3. **Calidad:** GPT-4o ($0.005/1K tokens)

### Para Producción
- **Alto volumen:** Groq + DeepSeek + Gemini
- **Calidad máxima:** GPT-4o + Claude 3.5
- **Presupuesto:** PaddleOCR + DeepSeek

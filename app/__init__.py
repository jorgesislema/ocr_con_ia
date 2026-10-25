"""OCR Con IA — Capa SaaS.

Paquete nuevo que convierte la aplicación de escritorio original en un
servicio SaaS multi-tenant de extracción de documentos con IA:

    app/
    ├── core/        Configuración, secretos, esquema canónico y modelos DB
    ├── ai/          Patrón Factory de proveedores IA (Gemini / Mistral)
    ├── validation/  Motor de validación determinista + consolidador multipágina
    ├── workers/     Cola asíncrona (Celery + Redis) para la extracción
    ├── api/         API REST FastAPI (subida, estado, revisión, exportación)
    ├── services/    Exportación a Excel / CSV / Word / PDF
    └── frontend/    SPA web con flujo de 4 pasos

La app de escritorio original (``src/``) se mantiene intacta y sigue siendo
funcional; el SaaS reutiliza el mismo dominio pero con arquitectura de
servicio desacoplada de la UI.
"""
__version__ = "1.0.0"

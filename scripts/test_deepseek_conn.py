"""Prueba de conexión a DeepSeek usando `StructuringEngine`.
Lee la API key desde la variable de entorno `TEST_DEEPSEEK_KEY`.
No imprime la clave.
"""
import os
import sys

key = os.environ.get("TEST_DEEPSEEK_KEY")
if not key:
    print("ERROR: TEST_DEEPSEEK_KEY no definida", file=sys.stderr)
    sys.exit(2)

try:
    from src.core.structuring_engine import StructuringEngine
except Exception as e:
    print(f"ERROR: no se pudo importar StructuringEngine: {e}", file=sys.stderr)
    sys.exit(2)

engine = None
try:
    engine = StructuringEngine(provider="DeepSeek", api_key=key, model="deepseek-v4-flash")
except Exception as e:
    print(f"ERROR: fallo inicializando StructuringEngine: {e}", file=sys.stderr)
    sys.exit(2)

sample = "Cash Inv No.: TEST123\nDate: 2020-01-01\nTotal Payable: 123.45\n"
try:
    result, pt, ct = engine.structure(sample, "Prueba simple: devuelve JSON con numero_factura, fecha_emision y total.")
    if result:
        # no mostrar la respuesta completa si es larga
        preview = result[:1000]
        print("OK: recibido respuesta LLM, chars=", len(result))
        print("PREVIEW:\n" + preview)
        print(f"TOKENS: prompt={pt} completion={ct}")
        sys.exit(0)
    else:
        print("EMPTY: la respuesta fue vacía (resultado vacío)")
        sys.exit(3)
except Exception as e:
    print(f"ERROR: llamada a engine.structure falló: {e}", file=sys.stderr)
    sys.exit(2)

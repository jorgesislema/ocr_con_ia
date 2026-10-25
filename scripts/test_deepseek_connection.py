#!/usr/bin/env python3
"""Prueba simple de conexión a DeepSeek.
Uso:
  python scripts/test_deepseek_connection.py --key <API_KEY>
O usa la variable de entorno DEEPSEEK_API_KEY.
Devuelve JSON con resultado y tokens si es exitoso.
"""
from __future__ import annotations
import argparse
import json
import sys

try:
    import requests
except Exception:
    print(json.dumps({"ok": False, "error": "requests no instalado"}, ensure_ascii=False))
    sys.exit(2)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--key", help="DeepSeek API key")
    p.add_argument("--model", default="deepseek-v4-flash", help="Modelo a usar")
    p.add_argument("--base-url", default="https://api.deepseek.com/v1", help="Base URL del endpoint")
    args = p.parse_args()

    api_key = (args.key or "").strip()
    # Prefer env var if provided
    if not api_key:
        import os
        api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()

    if not api_key:
        print(json.dumps({"ok": False, "error": "No API key proporcionada (usar --key o DEEPSEEK_API_KEY)"}, ensure_ascii=False))
        sys.exit(1)

    url = args.base_url.rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": args.model,
        "messages": [{"role": "user", "content": "Responde solo OK"}],
        "temperature": 0,
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        # Extraer contenido y uso si existen
        choice = (data.get("choices") or [{}])[0] or {}
        message = choice.get("message") or {}
        content = message.get("content") or ""
        usage = data.get("usage") or {}
        out = {
            "ok": True,
            "model": data.get("model") or args.model,
            "reply": content,
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "raw": data,
        }
        print(json.dumps(out, ensure_ascii=False))
        sys.exit(0)
    except Exception as exc:
        try:
            err_text = str(exc)
            body = getattr(exc, 'response', None)
            print(json.dumps({"ok": False, "error": err_text}, ensure_ascii=False))
        except Exception:
            print(json.dumps({"ok": False, "error": "unknown error"}, ensure_ascii=False))
        sys.exit(1)


if __name__ == "__main__":
    main()

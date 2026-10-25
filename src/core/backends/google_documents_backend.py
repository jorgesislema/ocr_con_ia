from __future__ import annotations

import os
from typing import Tuple

import requests


class GoogleDocumentsBackend:
    """Adapter for a generic Google Documents / Document AI endpoint.

    Configure `GOOGLE_DOCS_URL` and `GOOGLE_API_KEY` (or include auth in URL).
    This is a thin wrapper that posts the base64 image and tries to extract text.
    """

    def __init__(self) -> None:
        self.url = os.getenv("GOOGLE_DOCS_URL")
        self.key = os.getenv("GOOGLE_API_KEY")
        if not self.url:
            raise RuntimeError("Google Documents backend requires GOOGLE_DOCS_URL env var")

    def process_base64(self, b64: str) -> Tuple[str, int, int]:
        headers = {"Content-Type": "application/json"}
        if self.key:
            headers["Authorization"] = f"Bearer {self.key}"

        payload = {"image_base64": b64}
        resp = requests.post(self.url, headers=headers, json=payload, timeout=90)
        if resp.status_code != 200:
            raise RuntimeError(f"Google Documents error {resp.status_code}: {resp.text}")
        data = resp.json()
        # Best-effort parse
        text = ""
        if isinstance(data, dict):
            # Try common keys
            text = data.get("text") or data.get("document", {}).get("text") or data.get("response", {}).get("text", "")
        return text, 0, 0


try:
    from src.core.ocr_backends import register_backend

    register_backend("google-documents", lambda: GoogleDocumentsBackend())
except Exception:
    pass

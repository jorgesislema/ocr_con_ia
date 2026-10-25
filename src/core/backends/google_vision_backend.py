from __future__ import annotations

import os
import json
import base64
from typing import Tuple

import requests
import os
import base64 as _b64


class GoogleVisionBackend:
    """Adapter for Google Cloud Vision REST API using API key.

    Requires env var `GOOGLE_API_KEY`.
    """

    def __init__(self) -> None:
        # Support two auth modes:
        # 1) API key via env var GOOGLE_API_KEY (legacy, REST)
        # 2) Service account JSON via GOOGLE_APPLICATION_CREDENTIALS and google-cloud-vision client
        self.key = os.getenv("GOOGLE_API_KEY")
        self.sa_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        self.client = None
        if self.sa_path:
            try:
                from google.cloud import vision

                self.client = vision.ImageAnnotatorClient()
            except Exception:
                # google-cloud-vision not installed; will fallback to REST if API key present
                self.client = None

        if not self.key and not self.client:
            raise RuntimeError("GoogleVision backend requires GOOGLE_API_KEY or GOOGLE_APPLICATION_CREDENTIALS (with google-cloud-vision installed)")

        if self.key:
            self.url = f"https://vision.googleapis.com/v1/images:annotate?key={self.key}"
        else:
            self.url = None

    def process_base64(self, b64: str) -> Tuple[str, int, int]:
        # Google expects base64 content without data: prefix
        # If we have a google-cloud client, use it (sa JSON auth)
        if self.client:
            try:
                from google.cloud.vision import types  # type: ignore
            except Exception:
                pass
            img_bytes = _b64.b64decode(b64)
            image = {
                "content": img_bytes,
            }
            # Use document_text_detection for best OCR results
            resp = self.client.document_text_detection(image=image)
            try:
                text = resp.full_text_annotation.text or ""
            except Exception:
                text = ""
            return text or "", 0, 0

        # Fallback to REST API using API key
        payload = {
            "requests": [
                {
                    "image": {"content": b64},
                    "features": [{"type": "DOCUMENT_TEXT_DETECTION", "maxResults": 1}],
                }
            ]
        }
        resp = requests.post(self.url, json=payload, timeout=60)
        if resp.status_code != 200:
            raise RuntimeError(f"Google Vision error {resp.status_code}: {resp.text}")
        data = resp.json()
        text = ""
        try:
            resp0 = data.get("responses", [])[0]
            text = resp0.get("fullTextAnnotation", {}).get("text") or resp0.get("textAnnotations", [{}])[0].get("description", "")
        except Exception:
            text = ""
        # Google Vision does not report tokens; return 0 usage
        return text or "", 0, 0


# register
try:
    from src.core.ocr_backends import register_backend
    register_backend("google-vision", lambda: GoogleVisionBackend())
except Exception:
    pass

"""Seguridad del proyecto: almacenamiento cifrado de credenciales.

Proporciona una capa mínima usando cryptography.fernet cuando esté disponible
y un fallback (archivo JSON plano) si no lo está. Nunca asume keyring.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

_KEY_PATH = Path.home() / '.ocr_glm_key'
_SECRETS_PATH = Path.home() / '.ocr_glm_secrets.enc'


def _ensure_fernet_key() -> Optional[bytes]:
    try:
        from cryptography.fernet import Fernet
    except Exception:
        return None
    if not _KEY_PATH.exists():
        key = Fernet.generate_key()
        try:
            _KEY_PATH.write_bytes(key)
            try:
                _KEY_PATH.chmod(0o600)
            except Exception:
                pass
        except Exception:
            return None
        return key
    try:
        return _KEY_PATH.read_bytes()
    except Exception:
        return None


def save_credentials(ocr_token: str = "", ocr_json: str = "", postocr_token: str = "", postocr_json: str = "", google_processor_id: str = "", postocr_free_only: bool = False) -> bool:
    data = {
        "ocr_token": ocr_token or "",
        "ocr_json": ocr_json or "",
        "postocr_token": postocr_token or "",
        "postocr_json": postocr_json or "",
        "google_processor_id": google_processor_id or "",
        "postocr_free_only": bool(postocr_free_only),
    }
    key = _ensure_fernet_key()
    if key is None:
        try:
            _SECRETS_PATH.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
            try:
                _SECRETS_PATH.chmod(0o600)
            except Exception:
                pass
            return True
        except Exception:
            return False
    try:
        from cryptography.fernet import Fernet
        f = Fernet(key)
        token = f.encrypt(json.dumps(data).encode('utf-8'))
        _SECRETS_PATH.write_bytes(token)
        try:
            _SECRETS_PATH.chmod(0o600)
        except Exception:
            pass
        return True
    except Exception:
        return False


def load_credentials() -> dict:
    if not _SECRETS_PATH.exists():
        return {}
    key = _ensure_fernet_key()
    if key is None:
        try:
            txt = _SECRETS_PATH.read_text(encoding='utf-8')
            return json.loads(txt)
        except Exception:
            return {}
    try:
        from cryptography.fernet import Fernet
        f = Fernet(key)
        blob = _SECRETS_PATH.read_bytes()
        data = f.decrypt(blob)
        return json.loads(data.decode('utf-8'))
    except Exception:
        return {}


def delete_credentials() -> bool:
    try:
        if _SECRETS_PATH.exists():
            _SECRETS_PATH.unlink()
        return True
    except Exception:
        return False

"""
Certificate store -- a tiny, file-based record of every certificate Revv issues.

This is what makes a certificate *verifiable*: once a test is scored, the full
certificate is saved under its ID, so anyone with the link or QR can open and
confirm it later. v1 uses a simple JSON file; it swaps for a real database when
volume grows, without changing how the rest of the app calls it.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

_DATA_DIR = Path(__file__).resolve().parent / "data"
_DATA_DIR.mkdir(exist_ok=True)
_STORE_FILE = _DATA_DIR / "certificates.json"
_lock = threading.Lock()


def _load() -> dict:
    if not _STORE_FILE.exists():
        return {}
    try:
        return json.loads(_STORE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _write(data: dict) -> None:
    _STORE_FILE.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")


def save_certificate(cert: dict) -> str:
    """Save (or overwrite) a certificate by its id. Returns the id."""
    cert_id = cert["certificate_id"]
    with _lock:
        data = _load()
        data[cert_id] = cert
        _write(data)
    return cert_id


def get_certificate(cert_id: str) -> dict | None:
    """Fetch a stored certificate by id, or None if we never issued it."""
    with _lock:
        return _load().get(cert_id)


def set_status(cert_id: str, status: str, reason: str | None = None, by: str | None = None) -> bool:
    """Change a certificate's status (e.g. revoke one issued in error). Returns ok."""
    with _lock:
        data = _load()
        c = data.get(cert_id)
        if not c:
            return False
        c["status"] = status
        if status == "revoked":
            c["revoked_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            c["revoke_reason"] = reason or ""
            c["revoked_by"] = by or ""
        _write(data)
        return True


def count() -> int:
    with _lock:
        return len(_load())


def all_certificates() -> list[dict]:
    """Every issued certificate, newest first."""
    with _lock:
        certs = list(_load().values())
    certs.sort(key=lambda c: c.get("issued_at", ""), reverse=True)
    return certs

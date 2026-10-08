"""
Operator authentication -- accounts + signed-cookie sessions.

Only Revv operators (technicians / staff) log in to run tests and see the
dashboard. Buyers never log in -- their certificate page stays public.

Security basics done properly even in v1:
  - passwords are never stored in plain text (PBKDF2-HMAC-SHA256 + per-user salt)
  - sessions are a signed token (HMAC) so the cookie can't be forged
Swaps for a real auth service / database later without changing the callers.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import threading
from base64 import urlsafe_b64encode, urlsafe_b64decode
from datetime import datetime, timezone
from pathlib import Path

_DATA_DIR = Path(__file__).resolve().parent / "data"
_DATA_DIR.mkdir(exist_ok=True)
_USERS_FILE = _DATA_DIR / "operators.json"
_SECRET_FILE = _DATA_DIR / "session.secret"
_DEFAULT_LOGIN_FILE = _DATA_DIR / "DEFAULT_LOGIN.txt"
_lock = threading.Lock()

_PBKDF_ROUNDS = 120_000


# ---------- secret key for signing sessions ----------
def _secret() -> bytes:
    if _SECRET_FILE.exists():
        return _SECRET_FILE.read_bytes()
    key = secrets.token_bytes(32)
    _SECRET_FILE.write_bytes(key)
    return key


# ---------- user store ----------
def _load_users() -> dict:
    if not _USERS_FILE.exists():
        return {}
    try:
        return json.loads(_USERS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_users(users: dict) -> None:
    _USERS_FILE.write_text(json.dumps(users, indent=2), encoding="utf-8")


def _hash(password: str, salt: bytes) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF_ROUNDS).hex()


def user_exists(username: str) -> bool:
    return username.strip().lower() in _load_users()


def find_by_email(email: str) -> str | None:
    email_lc = email.strip().lower()
    for uname, data in _load_users().items():
        if data.get("email", "").lower() == email_lc or uname == email_lc:
            return uname
    return None


def create_operator(username: str, name: str, password: str, email: str = "") -> None:
    username = username.strip().lower()
    with _lock:
        users = _load_users()
        if username in users:
            raise ValueError("Username already taken")
        salt = secrets.token_bytes(16)
        users[username] = {
            "name": name,
            "email": email.strip().lower(),
            "salt": salt.hex(),
            "pwd_hash": _hash(password, salt),
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        _save_users(users)


def create_from_google(email: str, name: str) -> str:
    email_lc = email.strip().lower()
    existing = find_by_email(email_lc)
    if existing:
        return existing
    username = email_lc.split("@")[0]
    base = username
    counter = 1
    with _lock:
        users = _load_users()
        while username in users:
            username = f"{base}{counter}"
            counter += 1
        salt = secrets.token_bytes(16)
        users[username] = {
            "name": name or email_lc.split("@")[0],
            "email": email_lc,
            "salt": salt.hex(),
            "pwd_hash": _hash(secrets.token_urlsafe(32), salt),
            "auth_provider": "google",
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        _save_users(users)
    return username


def verify_credentials(username_or_email: str, password: str) -> str | None:
    """Return the username if credentials are valid, else None."""
    key = (username_or_email or "").strip().lower()
    users = _load_users()
    username = key
    u = users.get(key)
    if not u:
        found = find_by_email(key)
        if found:
            username = found
            u = users.get(found)
    if not u:
        return None
    expected = u["pwd_hash"]
    actual = _hash(password, bytes.fromhex(u["salt"]))
    return username if hmac.compare_digest(expected, actual) else None


def operator_name(username: str) -> str:
    u = _load_users().get((username or "").strip().lower())
    return u["name"] if u else username


# ---------- session tokens (signed cookie value) ----------
def make_token(username: str) -> str:
    username = username.strip().lower()
    body = urlsafe_b64encode(username.encode()).decode().rstrip("=")
    sig = hmac.new(_secret(), body.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{body}.{sig}"


def verify_token(token: str | None) -> str | None:
    """Return the username if the token is valid, else None."""
    if not token or "." not in token:
        return None
    body, sig = token.rsplit(".", 1)
    expected = hmac.new(_secret(), body.encode(), hashlib.sha256).hexdigest()[:32]
    if not hmac.compare_digest(expected, sig):
        return None
    try:
        pad = "=" * (-len(body) % 4)
        username = urlsafe_b64decode(body + pad).decode()
    except Exception:
        return None
    return username if username in _load_users() else None


# ---------- first-run bootstrap ----------
def ensure_default_operator() -> None:
    """If no operators exist, create one and write its credentials to a file."""
    with _lock:
        if _load_users():
            return
    password = secrets.token_urlsafe(9)
    create_operator("admin", "Revv Admin", password)
    _DEFAULT_LOGIN_FILE.write_text(
        "Revv operator login (change this later)\n"
        "----------------------------------------\n"
        f"Username: admin\n"
        f"Password: {password}\n\n"
        "Open the app at http://localhost:8130 and sign in.\n",
        encoding="utf-8",
    )

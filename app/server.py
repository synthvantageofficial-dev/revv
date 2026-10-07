"""
Revv operator app -- tiny backend.

Ties the whole flow together:  device -> ingest -> engine -> certificate -> store
Uses only the Python standard library, so there is nothing to install.

Run from the app/ folder:

    python server.py            # then open http://localhost:8130

Routes:
  GET  /                 -> operator console
  GET  /c/<id>           -> buyer-facing certificate page (what the QR/link opens)
  GET  /cert.css /cert.js-> shared static assets
  GET  /api/vehicles     -> demo vehicles to scan
  GET  /api/scan?id=...  -> raw dongle payload (the "device" output)
  POST /api/score        -> score a raw payload, save the certificate, return it
  GET  /api/certificate?id=... -> a previously issued certificate (verify)
"""

from __future__ import annotations

import json
import os
import sys
from collections import Counter
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

APP_DIR = Path(__file__).resolve().parent
WEB_DIR = APP_DIR / "web"
ENGINE_DIR = APP_DIR.parent / "engine"
if str(ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(ENGINE_DIR))

import device                               # noqa: E402
import store                                # noqa: E402
import specs                                # noqa: E402
import auth                                 # noqa: E402
import config                               # noqa: E402
import datalog                              # noqa: E402
from ingest import to_reading, validate, ValidationError  # noqa: E402
from revv_engine import score_battery, build_certificate  # noqa: E402

from datetime import datetime, timedelta    # noqa: E402
from http.cookies import SimpleCookie       # noqa: E402

PORT = int(os.environ.get("PORT", 8130))
BASE_URL = os.environ.get("REVV_BASE_URL", f"http://localhost:{PORT}")
SESSION_COOKIE = "revv_session"

_STATIC = {
    "/cert.css": ("cert.css", "text/css; charset=utf-8"),
    "/cert.js": ("cert.js", "application/javascript; charset=utf-8"),
    "/nav.js": ("nav.js", "application/javascript; charset=utf-8"),
}

# Routes anyone can reach without signing in.
# (Buyers open their certificate; assets and the login flow must load.)
_PUBLIC_GET = {"/login", "/login.html", "/cert.css", "/cert.js", "/api/certificate"}
_PUBLIC_POST = {"/api/login", "/api/logout"}

_NOT_FOUND_HTML = (
    "<!doctype html><meta charset=utf-8><title>Revv — Not found</title>"
    "<link rel=stylesheet href=/cert.css>"
    "<div class=wrap style='text-align:center;padding-top:80px'>"
    "<h1 style='font-family:Space Grotesk,sans-serif;font-size:40px'>404</h1>"
    "<p style='color:var(--muted)'>That page doesn't exist.</p>"
    "<p><a href='/' style='color:var(--brand);font-weight:600'>Go to Revv</a></p></div>"
).encode("utf-8")


def _run_test(raw: dict, operator: str | None = None) -> dict:
    """Validate, score, stamp, persist, and log one raw payload."""
    validate(raw)                     # raises ValidationError with a friendly message
    reading = to_reading(raw)
    result = score_battery(reading)
    certificate = build_certificate(reading, result, raw=raw)

    cid = certificate["certificate_id"]
    certificate["verification"]["verify_url"] = f"{config.VERIFY_BASE}/c/{cid}"
    certificate["issued_by"] = operator or "Revv operator"
    certificate["status"] = "active"
    certificate["issuer_company"] = config.COMPANY_NAME
    certificate["support_email"] = config.SUPPORT_EMAIL

    issued = datetime.fromisoformat(certificate["issued_at"])
    certificate["validity"] = {
        "validity_days": config.VALIDITY_DAYS,
        "valid_until": (issued + timedelta(days=config.VALIDITY_DAYS)).isoformat(timespec="seconds"),
    }

    store.save_certificate(certificate)
    reading_dict = asdict(reading)
    datalog.log_test(raw, reading_dict, certificate)
    return {"reading": reading_dict, "certificate": certificate}


def _summary_row(c: dict) -> dict:
    s, v = c["summary"], c["vehicle"]
    return {
        "id": c["certificate_id"], "issued_at": c["issued_at"],
        "model": v.get("model"), "vin": v.get("vin_or_regno"),
        "soh": s["soh_percent"], "verdict": s["verdict"],
        "confidence": s["confidence"], "flags": len(c.get("flags", [])),
        "status": c.get("status", "active"),
        "valid_until": c.get("validity", {}).get("valid_until"),
        "issued_by": c.get("issued_by"),
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _list_certificates(self, query: dict) -> dict:
        """Dashboard data: filtered rows + overview stats over all certificates."""
        certs = store.all_certificates()
        q = (query.get("q") or [""])[0].strip().lower()
        rows = []
        for c in certs:
            v = c["vehicle"]
            hay = f"{c['certificate_id']} {v.get('model') or ''} {v.get('vin_or_regno') or ''}".lower()
            if not q or q in hay:
                rows.append(_summary_row(c))
        total = len(certs)
        avg = round(sum(c["summary"]["soh_percent"] for c in certs) / total, 1) if total else 0
        stats = {
            "total": total,
            "avg_soh": avg,
            "safe": sum(1 for c in certs if c["summary"]["verdict"] in ("Excellent", "Good")),
            "flagged": sum(1 for c in certs if c.get("flags")),
            "revoked": sum(1 for c in certs if c.get("status") == "revoked"),
            "logged": datalog.count(),
            "verdict_counts": dict(Counter(c["summary"]["verdict"] for c in certs)),
        }
        return {"certificates": rows, "stats": stats}

    def _send(self, status: int, body: bytes, content_type: str, extra_headers: list | None = None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra_headers or []):
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, obj, extra_headers: list | None = None) -> None:
        self._send(status, json.dumps(obj, default=str).encode("utf-8"), "application/json", extra_headers)

    def _file(self, name: str, content_type: str) -> None:
        self._send(200, (WEB_DIR / name).read_bytes(), content_type)

    def _redirect(self, location: str) -> None:
        self._send(302, b"", "text/plain", [("Location", location)])

    # ---- session helpers ----
    def _current_user(self) -> str | None:
        raw = self.headers.get("Cookie")
        if not raw:
            return None
        try:
            jar = SimpleCookie(raw)
        except Exception:
            return None
        morsel = jar.get(SESSION_COOKIE)
        return auth.verify_token(morsel.value) if morsel else None

    def _cookie_header(self, token: str, clear: bool = False) -> list:
        if clear:
            return [("Set-Cookie", f"{SESSION_COOKIE}=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax")]
        return [("Set-Cookie", f"{SESSION_COOKIE}={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age=604800")]

    def do_GET(self):
        parsed = urlparse(self.path)
        route = parsed.path

        # --- public routes (no login needed) ---
        if route in ("/login", "/login.html"):
            return self._file("login.html", "text/html; charset=utf-8")

        if route in _STATIC:
            name, ctype = _STATIC[route]
            return self._file(name, ctype)

        if route.startswith("/c/"):
            # buyer-facing certificate page; the page reads the id from the URL
            return self._file("certificate.html", "text/html; charset=utf-8")

        if route == "/api/certificate":
            cid = (parse_qs(parsed.query).get("id") or [""])[0]
            cert = store.get_certificate(cid)
            if cert is None:
                return self._json(404, {"error": "certificate not found"})
            return self._json(200, {"certificate": cert})

        # --- everything below requires a signed-in operator ---
        user = self._current_user()
        if not user:
            if route.startswith("/api/"):
                return self._json(401, {"error": "login required"})
            nxt = self.path
            return self._redirect("/login?next=" + nxt)

        if route in ("/", "/index.html"):
            return self._file("index.html", "text/html; charset=utf-8")

        if route in ("/manual", "/manual.html"):
            return self._file("manual.html", "text/html; charset=utf-8")

        if route in ("/dashboard", "/dashboard.html"):
            return self._file("dashboard.html", "text/html; charset=utf-8")

        if route == "/api/me":
            return self._json(200, {"username": user, "name": auth.operator_name(user)})

        if route == "/api/certificates":
            return self._json(200, self._list_certificates(parse_qs(parsed.query)))

        if route == "/api/vehicles":
            return self._json(200, {"vehicles": device.list_vehicles()})

        if route == "/api/models":
            models = [{"model": m, **specs.get_spec(m)} for m in specs.known_models()]
            return self._json(200, {"models": models})

        if route == "/api/scan":
            vid = (parse_qs(parsed.query).get("id") or [""])[0]
            try:
                return self._json(200, {"raw": device.scan(vid)})
            except KeyError as e:
                return self._json(404, {"error": str(e)})

        if route == "/api/export.csv":
            csv_text = datalog.export_csv().encode("utf-8")
            return self._send(200, csv_text, "text/csv; charset=utf-8",
                              [("Content-Disposition", 'attachment; filename="revv_readings.csv"')])

        if route.startswith("/api/"):
            return self._json(404, {"error": "not found"})
        return self._send(404, _NOT_FOUND_HTML, "text/html; charset=utf-8")

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length) or b"{}")

    def do_POST(self):
        route = urlparse(self.path).path

        if route == "/api/login":
            try:
                d = self._read_json()
            except Exception:
                return self._json(400, {"ok": False, "error": "bad request"})
            if auth.verify_credentials(d.get("username", ""), d.get("password", "")):
                token = auth.make_token(d["username"])
                return self._json(200, {"ok": True}, self._cookie_header(token))
            return self._json(401, {"ok": False, "error": "Wrong username or password."})

        if route == "/api/logout":
            return self._json(200, {"ok": True}, self._cookie_header("", clear=True))

        # --- below requires login ---
        user = self._current_user()
        if not user:
            return self._json(401, {"error": "login required"})

        if route == "/api/score":
            try:
                payload = self._read_json()
                raw = payload.get("raw", payload)
                return self._json(200, _run_test(raw, operator=auth.operator_name(user)))
            except ValidationError as e:
                return self._json(400, {"error": str(e)})
            except Exception as e:
                return self._json(400, {"error": f"{type(e).__name__}: {e}"})

        if route == "/api/revoke":
            try:
                d = self._read_json()
            except Exception:
                return self._json(400, {"error": "bad request"})
            cid = d.get("id", "")
            ok = store.set_status(cid, "revoked", reason=d.get("reason", ""),
                                  by=auth.operator_name(user))
            return self._json(200 if ok else 404, {"ok": ok})

        return self._json(404, {"error": "not found"})


def main() -> None:
    auth.ensure_default_operator()
    host = "0.0.0.0" if os.environ.get("RENDER") else "127.0.0.1"
    server = ThreadingHTTPServer((host, PORT), Handler)
    print(f"Revv operator app -> {BASE_URL}  ({store.count()} certificates on file)")
    print("Operator login required. First-run credentials: app/data/DEFAULT_LOGIN.txt")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()

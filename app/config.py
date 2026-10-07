"""
Central config for the Revv app.

One place for company details, the public verify domain, and certificate
validity. Values can be overridden with environment variables so the same code
runs locally and (later) in production without edits.
"""

import os

COMPANY_NAME = os.environ.get("REVV_COMPANY_NAME", "Revv")
SUPPORT_EMAIL = os.environ.get("REVV_SUPPORT_EMAIL", "hello@revv.example")

# Base URL used in verification links / QR codes. In production set
# REVV_VERIFY_BASE to the real domain, e.g. https://revv.in
VERIFY_BASE = os.environ.get("REVV_VERIFY_BASE", "http://localhost:8130").rstrip("/")

# How long a certificate is considered current before a re-test is recommended.
VALIDITY_DAYS = int(os.environ.get("REVV_VALIDITY_DAYS", "90"))

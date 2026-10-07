"""
Data-logging pipeline.

Every test Revv runs is appended here as one line of JSON (JSONL). This is the
quiet but crucial part of the plan: as real tests start happening, a clean,
growing dataset builds up on its own -- exactly what we need later to CALIBRATE
the engine against reality. Today it logs the mock tests; the format won't change.

Nothing in the app depends on reading this back; it's an append-only record,
plus a CSV export for whoever does the calibration.
"""

from __future__ import annotations

import csv
import io
import json
import threading
from datetime import datetime, timezone
from pathlib import Path

_DATA_DIR = Path(__file__).resolve().parent / "data"
_DATA_DIR.mkdir(exist_ok=True)
_LOG_FILE = _DATA_DIR / "readings_log.jsonl"
_lock = threading.Lock()

# Flat columns captured for calibration (raw signals + what the engine concluded).
_COLUMNS = [
    "logged_at", "certificate_id", "operator", "model", "vin", "chemistry",
    "age_years", "odometer_km", "rated_capacity_kwh", "measured_capacity_kwh",
    "equivalent_full_cycles", "cell_voltage_spread_mv",
    "internal_resistance_mohm", "internal_resistance_baseline_mohm",
    "dc_fastcharge_ratio", "avg_ambient_temp_c",
    "soh_percent", "verdict", "confidence_score", "data_completeness_percent",
]


def log_test(raw: dict, reading: dict, certificate: dict) -> None:
    """Append one test to the log. Never raises into the request path."""
    try:
        s = certificate["summary"]
        rec = {
            "logged_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "certificate_id": certificate.get("certificate_id"),
            "operator": certificate.get("issued_by"),
            "model": reading.get("vehicle_model"),
            "vin": reading.get("vin_or_regno"),
            "chemistry": reading.get("chemistry"),
            "age_years": reading.get("age_years"),
            "odometer_km": reading.get("odometer_km"),
            "rated_capacity_kwh": reading.get("rated_capacity_kwh"),
            "measured_capacity_kwh": reading.get("measured_capacity_kwh"),
            "equivalent_full_cycles": reading.get("equivalent_full_cycles"),
            "cell_voltage_spread_mv": reading.get("cell_voltage_spread_mv"),
            "internal_resistance_mohm": reading.get("internal_resistance_mohm"),
            "internal_resistance_baseline_mohm": reading.get("internal_resistance_baseline_mohm"),
            "dc_fastcharge_ratio": reading.get("dc_fastcharge_ratio"),
            "avg_ambient_temp_c": reading.get("avg_ambient_temp_c"),
            "soh_percent": s.get("soh_percent"),
            "verdict": s.get("verdict"),
            "confidence_score": s.get("confidence_score"),
            "data_completeness_percent": certificate.get("data_quality", {}).get("completeness_percent"),
            "raw": raw,  # full raw payload kept for re-processing later
        }
        with _lock:
            with _LOG_FILE.open("a", encoding="utf-8") as f:
                f.write(json.dumps(rec, default=str) + "\n")
    except Exception:
        pass  # logging must never break a test


def count() -> int:
    if not _LOG_FILE.exists():
        return 0
    with _lock:
        with _LOG_FILE.open(encoding="utf-8") as f:
            return sum(1 for _ in f)


def export_csv() -> str:
    """Flatten the log into CSV text for calibration work."""
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=_COLUMNS, extrasaction="ignore")
    w.writeheader()
    if _LOG_FILE.exists():
        with _lock:
            lines = _LOG_FILE.read_text(encoding="utf-8").splitlines()
        for line in lines:
            try:
                w.writerow(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out.getvalue()

"""
Revv battery health engine.

The heart of the Revv product: it turns an EV battery's raw data into one
independent, trustworthy State-of-Health score and a shareable certificate.

Typical use:

    from revv_engine import BatteryReading, Chemistry, score_battery, build_certificate

    reading = BatteryReading(vehicle_model="Tata Nexon EV", rated_capacity_kwh=30.2,
                             age_years=3, odometer_km=42000, chemistry=Chemistry.NMC)
    result = score_battery(reading)
    cert = build_certificate(reading, result)
"""

from .models import (
    BatteryReading,
    Chemistry,
    Confidence,
    SoHResult,
    Verdict,
)
from .scoring import AgeingParams, score_battery, END_OF_LIFE_SOH
from .certificate import build_certificate, format_certificate

__version__ = "0.1.0"

__all__ = [
    "BatteryReading",
    "Chemistry",
    "Confidence",
    "SoHResult",
    "Verdict",
    "AgeingParams",
    "score_battery",
    "END_OF_LIFE_SOH",
    "build_certificate",
    "format_certificate",
]

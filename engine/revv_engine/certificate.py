"""
Turn a SoHResult into a full, readable certificate -- the document a buyer,
dealer, bank or insurer actually studies before money changes hands.

The certificate is intentionally detailed: it exposes every measurement, how
the score was built, how complete the data was, and the full raw telemetry the
device sent. Transparency is what earns trust when you are not a government
body -- nothing is hidden, and anyone can check the reasoning.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from .models import BatteryReading, SoHResult
from .scoring import (
    END_OF_LIFE_SOH,
    IMBALANCE_WARN_MV,
    IMBALANCE_BAD_MV,
    RESISTANCE_WARN_RATIO,
    RESISTANCE_BAD_RATIO,
)

METHODOLOGY_VERSION = "Revv SoH Engine v0.1 (transparent model)"


def _round(x, n=1):
    return round(x, n) if isinstance(x, (int, float)) else x


def _imbalance_status(spread):
    if spread is None:
        return "not measured"
    if spread >= IMBALANCE_BAD_MV:
        return "High"
    if spread >= IMBALANCE_WARN_MV:
        return "Mild"
    return "Good"


def _resistance_status(ratio):
    if ratio is None:
        return "not measured"
    if ratio >= RESISTANCE_BAD_RATIO:
        return "High"
    if ratio >= RESISTANCE_WARN_RATIO:
        return "Elevated"
    return "Good"


def _data_quality(reading: BatteryReading) -> dict:
    """What did we actually measure vs estimate/miss? Drives trust + confidence."""
    checks = {
        "Measured full-charge capacity": reading.measured_capacity_kwh is not None,
        "Per-cell voltages (imbalance)": reading.cell_voltage_spread_mv is not None,
        "Internal resistance": reading.internal_resistance_mohm is not None
        and reading.internal_resistance_baseline_mohm is not None,
        "Lifetime charge cycles": reading.equivalent_full_cycles is not None,
        "Fast-charging history": reading.dc_fastcharge_ratio is not None,
        "Ambient temperature": reading.avg_ambient_temp_c is not None,
    }
    measured = [k for k, v in checks.items() if v]
    missing = [k for k, v in checks.items() if not v]
    pct = round(len(measured) / len(checks) * 100)
    return {
        "completeness_percent": pct,
        "measured": measured,
        "estimated_or_missing": missing,
    }


def build_certificate(reading: BatteryReading, result: SoHResult, raw: dict | None = None) -> dict:
    """Assemble the full certificate payload (JSON-ready)."""
    issued = datetime.now(timezone.utc)
    seed = f"{reading.vin_or_regno}|{reading.vehicle_model}|{result.soh_percent}|{issued.date()}"
    cert_id = "REVV-" + hashlib.sha1(seed.encode()).hexdigest()[:8].upper()

    # --- derived battery detail ---
    rated = reading.rated_capacity_kwh
    measured_cap = reading.measured_capacity_kwh
    capacity_fade = round(100 - result.capacity_based_soh, 1) if result.capacity_based_soh is not None else None

    spread = reading.cell_voltage_spread_mv
    cell_count = len(raw["cell_voltages_mv"]) if raw and raw.get("cell_voltages_mv") else None
    cell_min = min(raw["cell_voltages_mv"]) if cell_count else None
    cell_max = max(raw["cell_voltages_mv"]) if cell_count else None

    r = reading.internal_resistance_mohm
    r0 = reading.internal_resistance_baseline_mohm
    r_ratio = round(r / r0, 2) if (r is not None and r0) else None

    cycles_source = "measured" if reading.equivalent_full_cycles is not None else "estimated from distance"
    km_per_year = round(reading.odometer_km / reading.age_years) if reading.age_years > 0.3 else None
    cycles_per_year = round(result.estimated_cycles / reading.age_years) if reading.age_years > 0.3 else None

    return {
        "certificate_id": cert_id,
        "issued_at": issued.isoformat(timespec="seconds"),
        "issuer": "Revv — independent battery assessment",
        "methodology": METHODOLOGY_VERSION,
        "validity_note": "Reflects battery condition on the test date. Battery health changes slowly; recommend re-test if older than 3 months.",
        "verification": {
            "verify_id": cert_id,
            "verify_url": f"https://revv.example/verify/{cert_id}",
            "note": "Scan the QR or open the link to confirm this certificate is genuine and unaltered.",
        },

        "vehicle": {
            "model": reading.vehicle_model,
            "vin_or_regno": reading.vin_or_regno or None,
            "chemistry": reading.chemistry.value,
            "age_years": reading.age_years,
            "odometer_km": reading.odometer_km,
            "km_per_year": km_per_year,
            "rated_capacity_kwh": rated,
        },

        "summary": {
            "soh_percent": result.soh_percent,
            "verdict": result.verdict.value,
            "recommendation": result.recommendation,
            "range_retained_percent": result.range_retained_percent,
            "remaining_life_years": result.remaining_life_years,
            "end_of_life_soh": END_OF_LIFE_SOH,
            "confidence": result.confidence.value,
            "confidence_score": result.confidence_score,
        },

        "battery_detail": {
            "capacity": {
                "rated_kwh": rated,
                "measured_full_kwh": measured_cap,
                "capacity_fade_percent": capacity_fade,
                "capacity_based_soh": result.capacity_based_soh,
            },
            "cells": {
                "count_sampled": cell_count,
                "min_mv": cell_min,
                "max_mv": cell_max,
                "spread_mv": spread,
                "imbalance_status": _imbalance_status(spread),
            },
            "internal_resistance": {
                "measured_mohm": r,
                "baseline_mohm": r0,
                "ratio_vs_healthy": r_ratio,
                "status": _resistance_status(r_ratio),
            },
            "cycles": {
                "equivalent_full_cycles": result.estimated_cycles,
                "source": cycles_source,
                "per_year": cycles_per_year,
            },
            "usage": {
                "odometer_km": reading.odometer_km,
                "km_per_year": km_per_year,
                "dc_fastcharge_ratio": reading.dc_fastcharge_ratio,
                "assumed_efficiency_km_per_kwh": reading.efficiency_km_per_kwh,
            },
            "environment": {
                "avg_ambient_temp_c": reading.avg_ambient_temp_c,
            },
        },

        "how_scored": {
            "capacity_based_soh": result.capacity_based_soh,
            "model_based_soh": result.model_based_soh,
            "calendar_loss_percent": result.calendar_loss_pct,
            "cycle_loss_percent": result.cycle_loss_pct,
            "penalty_items": result.penalty_items,
            "total_penalties_percent": result.penalties_applied,
            "final_soh_percent": result.soh_percent,
            "notes": result.notes,
        },

        "flags": result.flags,
        "data_quality": _data_quality(reading),
        "raw_telemetry": raw or {},

        "disclaimer": (
            "Revv is an independent estimate of battery State-of-Health from the data provided. "
            "The v1 engine uses published lithium-ion ageing models, not yet calibrated on Revv's "
            "own measured fleet. Confidence reflects how much of the battery could be measured directly."
        ),
    }


# ----------------------------------------------------------------------------
# Pretty text version for the terminal demo
# ----------------------------------------------------------------------------

def _bar(percent: float, width: int = 24) -> str:
    filled = int(round((percent or 0) / 100 * width))
    return "[" + "#" * filled + "-" * (width - filled) + "]"


def _fmt(v, suffix=""):
    return f"{v}{suffix}" if v is not None else "not measured"


def format_certificate(cert: dict) -> str:
    s = cert["summary"]
    v = cert["vehicle"]
    bd = cert["battery_detail"]
    hs = cert["how_scored"]
    dq = cert["data_quality"]

    L = []
    L.append("=" * 58)
    L.append("  REVV  --  BATTERY HEALTH CERTIFICATE")
    L.append("=" * 58)
    L.append(f"  Certificate : {cert['certificate_id']}")
    L.append(f"  Issued      : {cert['issued_at']}")
    L.append(f"  Issuer      : {cert['issuer']}")
    L.append(f"  Verify      : {cert['verification']['verify_url']}")
    L.append("-" * 58)
    L.append("  VEHICLE")
    L.append(f"    Model        : {v['model']}")
    L.append(f"    VIN / Reg    : {_fmt(v['vin_or_regno'])}")
    L.append(f"    Chemistry    : {v['chemistry']}")
    L.append(f"    Age          : {v['age_years']} yrs")
    L.append(f"    Odometer     : {v['odometer_km']:,.0f} km  ({_fmt(v['km_per_year'],' km/yr')})")
    L.append(f"    Rated pack   : {v['rated_capacity_kwh']} kWh")
    L.append("-" * 58)
    L.append(f"  STATE OF HEALTH : {s['soh_percent']:.1f}%   {_bar(s['soh_percent'])}")
    L.append(f"  Verdict         : {s['verdict']}")
    L.append(f"  {s['recommendation']}")
    L.append(f"    Range retained : ~{s['range_retained_percent']:.0f}%")
    L.append(f"    Life remaining : {s['remaining_life_years']} yrs (to {s['end_of_life_soh']:.0f}% SoH)")
    L.append(f"    Confidence     : {s['confidence']} ({s['confidence_score']:.2f})")
    L.append("-" * 58)
    L.append("  BATTERY DETAIL")
    cap = bd["capacity"]
    L.append(f"    Capacity     : {_fmt(cap['measured_full_kwh'],' kWh')} of {cap['rated_kwh']} kWh"
             f"  (fade {_fmt(cap['capacity_fade_percent'],'%')})")
    ce = bd["cells"]
    L.append(f"    Cells        : {_fmt(ce['count_sampled'])} sampled, "
             f"spread {_fmt(ce['spread_mv'],' mV')}  [{ce['imbalance_status']}]")
    ir = bd["internal_resistance"]
    L.append(f"    Resistance   : {_fmt(ir['measured_mohm'],' mohm')} vs {_fmt(ir['baseline_mohm'],' mohm')}"
             f"  ({_fmt(ir['ratio_vs_healthy'],'x')}) [{ir['status']}]")
    cy = bd["cycles"]
    L.append(f"    Cycles       : {cy['equivalent_full_cycles']:.0f} ({cy['source']}), "
             f"{_fmt(cy['per_year'],'/yr')}")
    us = bd["usage"]
    L.append(f"    Fast-charge  : {_fmt(us['dc_fastcharge_ratio'])}")
    L.append(f"    Avg temp     : {_fmt(bd['environment']['avg_ambient_temp_c'],' C')}")
    L.append("-" * 58)
    L.append("  HOW REVV SCORED IT")
    if hs["capacity_based_soh"] is not None:
        L.append(f"    Capacity-based SoH : {hs['capacity_based_soh']}%")
    L.append(f"    Ageing-model SoH   : {hs['model_based_soh']}%")
    L.append(f"      - calendar loss  : -{hs['calendar_loss_percent']}%")
    L.append(f"      - cycle loss     : -{hs['cycle_loss_percent']}%")
    if hs["penalty_items"]:
        L.append("    Health penalties:")
        for it in hs["penalty_items"]:
            L.append(f"      - {it['label']:<26} -{it['points']}%")
    L.append(f"    => Final SoH       : {hs['final_soh_percent']}%")
    if cert["flags"]:
        L.append("-" * 58)
        L.append("  FLAGS")
        for f in cert["flags"]:
            L.append(f"    ! {f}")
    L.append("-" * 58)
    L.append(f"  DATA QUALITY : {dq['completeness_percent']}% complete")
    L.append(f"    Measured : {', '.join(dq['measured']) or '-'}")
    L.append(f"    Missing  : {', '.join(dq['estimated_or_missing']) or '-'}")
    L.append("=" * 58)
    return "\n".join(L)

"""
Ingestion / translation layer -- the "software" between the device and the engine.

A dongle hands us raw, messy readings. The engine wants a clean BatteryReading.
This layer does that translation and the small bits of real work in between:

  - per-cell voltages      -> cell voltage spread (imbalance)
  - manufacture date       -> age in years
  - lifetime energy + pack -> equivalent full cycles
  - model hint             -> (future) spec lookup / sanity checks

It is deliberately forgiving: any field the dongle couldn't read is left as
None, and the engine simply lowers its confidence instead of failing.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

# Make the engine importable (engine/ is a sibling of app/).
_ENGINE_DIR = Path(__file__).resolve().parent.parent / "engine"
if str(_ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(_ENGINE_DIR))

from revv_engine import BatteryReading, Chemistry  # noqa: E402
from specs import get_spec  # noqa: E402


def _age_years_from(manufacture_date: str | None) -> float:
    """'YYYY-MM' -> age in years (one decimal)."""
    if not manufacture_date:
        return 0.0
    try:
        parts = manufacture_date.split("-")
        y = int(parts[0])
        m = int(parts[1]) if len(parts) > 1 else 1
        made = date(y, m, 1)
        days = (date.today() - made).days
        return round(max(days, 0) / 365.25, 1)
    except (ValueError, IndexError):
        return 0.0


def _cell_spread_mv(cells: list | None) -> float | None:
    """Weakest-to-strongest cell gap -> imbalance signal."""
    if not cells:
        return None
    return float(max(cells) - min(cells))


def _equivalent_cycles(lifetime_energy_kwh, pack_nominal_kwh) -> float | None:
    """One full cycle = using the whole pack once."""
    if not lifetime_energy_kwh or not pack_nominal_kwh:
        return None
    return round(lifetime_energy_kwh / pack_nominal_kwh, 0)


def _chemistry(raw: str | None) -> Chemistry:
    try:
        return Chemistry(raw) if raw else Chemistry.UNKNOWN
    except ValueError:
        return Chemistry.UNKNOWN


class ValidationError(ValueError):
    """Raised when a raw payload has values that can't make a sensible certificate."""


def validate(raw: dict) -> None:
    """
    Check a raw payload for obviously-wrong values before scoring, so the
    operator gets a clear message instead of a nonsense certificate.
    Raises ValidationError with a friendly message listing every problem.
    """
    problems: list[str] = []

    def num(key):
        v = raw.get(key)
        return v if isinstance(v, (int, float)) else None

    odo = num("odometer_km")
    if odo is None:
        problems.append("Odometer (km) is required.")
    elif odo < 0 or odo > 1_000_000:
        problems.append("Odometer looks wrong (must be between 0 and 10,00,000 km).")

    for key, label, lo, hi in [
        ("pack_nominal_kwh", "Rated pack", 1, 400),
        ("pack_energy_full_kwh", "Full-charge capacity", 1, 400),
        ("cell_voltage_spread_mv", "Cell voltage spread", 0, 2000),
        ("dc_internal_resistance_mohm", "Internal resistance", 0, 5000),
        ("ambient_temp_c", "Ambient temperature", -40, 70),
    ]:
        v = num(key)
        if v is not None and (v < lo or v > hi):
            problems.append(f"{label} looks out of range ({lo}–{hi}).")

    fc = num("dc_fastcharge_ratio")
    if fc is not None and (fc < 0 or fc > 1):
        problems.append("Fast-charge share must be between 0 and 100%.")

    full, nominal = num("pack_energy_full_kwh"), num("pack_nominal_kwh")
    if full is not None and nominal is not None and full > nominal * 1.1:
        problems.append("Full-charge capacity can't exceed the rated pack size.")

    made = raw.get("manufacture_date")
    if made:
        age = _age_years_from(made)
        if age == 0.0 and made:  # unparhseable or future date
            try:
                y = int(str(made).split("-")[0])
                if y > date.today().year:
                    problems.append("Manufacture date can't be in the future.")
            except (ValueError, IndexError):
                problems.append("Manufacture date is not a valid month (use YYYY-MM).")

    if problems:
        raise ValidationError(" ".join(problems))


def to_reading(raw: dict) -> BatteryReading:
    """
    Turn one raw dongle payload into a clean BatteryReading for the engine.

    The factory spec (nameplate pack size, chemistry, healthy resistance baseline)
    comes from our own spec database keyed on the model -- the trusted reference --
    and we fall back to what the dongle reported only when the model is unknown.
    """
    spec = get_spec(raw.get("model_hint"))

    # nameplate pack size & chemistry: prefer our spec DB, fall back to the dongle
    rated = (spec["rated_capacity_kwh"] if spec else raw.get("pack_nominal_kwh")) or 0.0
    chemistry = _chemistry(spec["chemistry"]) if spec else _chemistry(raw.get("chemistry"))
    model = spec["model"] if spec else raw.get("model_hint", "Unknown EV")

    # resistance baseline: use what the dongle measured for this pack, else the spec's
    baseline = raw.get("dc_internal_resistance_baseline_mohm")
    if baseline is None and spec:
        baseline = spec.get("resistance_baseline_mohm")

    return BatteryReading(
        vehicle_model=model,
        vin_or_regno=raw.get("vin", ""),
        rated_capacity_kwh=rated,
        age_years=_age_years_from(raw.get("manufacture_date")),
        odometer_km=raw.get("odometer_km", 0.0) or 0.0,
        measured_capacity_kwh=raw.get("pack_energy_full_kwh"),
        equivalent_full_cycles=_equivalent_cycles(
            raw.get("lifetime_energy_kwh"), rated
        ),
        cell_voltage_spread_mv=(
            raw.get("cell_voltage_spread_mv")
            if raw.get("cell_voltage_spread_mv") is not None
            else _cell_spread_mv(raw.get("cell_voltages_mv"))
        ),
        internal_resistance_mohm=raw.get("dc_internal_resistance_mohm"),
        internal_resistance_baseline_mohm=baseline,
        dc_fastcharge_ratio=raw.get("dc_fastcharge_ratio"),
        avg_ambient_temp_c=raw.get("ambient_temp_c"),
        chemistry=chemistry,
    )

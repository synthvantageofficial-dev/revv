"""
Data models for the Revv battery health engine.

These describe the two things the engine deals with:

  BatteryReading  -> the raw facts we collect from (or about) one EV's battery.
  SoHResult       -> the health verdict our algorithm produces from that reading.

Everything the real product does flows between these two objects:
an OBD test (or a connected car's data) fills a BatteryReading, the scoring
engine turns it into a SoHResult, and the certificate layer presents it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Chemistry(str, Enum):
    """Battery cell chemistry. It changes how fast a pack ages."""
    NMC = "NMC"   # Nickel-Manganese-Cobalt: most long-range EVs. Ages a bit faster.
    LFP = "LFP"   # Lithium-Iron-Phosphate: very long cycle life, slower fade.
    UNKNOWN = "UNKNOWN"


@dataclass
class BatteryReading:
    """
    One snapshot of an EV battery's facts.

    Only a few fields are strictly required (rated_capacity_kwh, age_years,
    odometer_km). Everything else is optional: the more we have, the more
    confident and accurate the score becomes. Missing fields never crash the
    engine -- they just lower the confidence of the result.
    """

    # --- identity (for the certificate; not used in scoring) ---
    vehicle_model: str = "Unknown EV"
    vin_or_regno: str = ""

    # --- required basics ---
    rated_capacity_kwh: float = 0.0        # original/nameplate usable pack size
    age_years: float = 0.0                 # years since manufacture
    odometer_km: float = 0.0               # total distance driven

    # --- battery facts (strong signals, usually from an OBD test) ---
    measured_capacity_kwh: Optional[float] = None   # current full-charge usable kWh
    equivalent_full_cycles: Optional[float] = None  # lifetime charge throughput / pack size
    cell_voltage_spread_mv: Optional[float] = None  # imbalance between the weakest/strongest cells
    internal_resistance_mohm: Optional[float] = None          # measured DC internal resistance
    internal_resistance_baseline_mohm: Optional[float] = None # healthy/new resistance for this pack

    # --- usage & environment (weaker signals) ---
    dc_fastcharge_ratio: Optional[float] = None  # 0..1, share of energy taken via DC fast charging
    avg_ambient_temp_c: Optional[float] = None   # average temperature the pack lives in

    # --- context ---
    chemistry: Chemistry = Chemistry.UNKNOWN
    efficiency_km_per_kwh: float = 6.5     # assumed real-world efficiency (Indian city driving)

    def missing_required(self) -> list[str]:
        """Return the names of required fields that are still unset."""
        missing = []
        if self.rated_capacity_kwh <= 0:
            missing.append("rated_capacity_kwh")
        if self.age_years < 0:
            missing.append("age_years")
        if self.odometer_km < 0:
            missing.append("odometer_km")
        return missing


class Verdict(str, Enum):
    """Plain-language buying verdict shown on the certificate."""
    EXCELLENT = "Excellent"
    GOOD = "Good"
    FAIR = "Fair"
    POOR = "Poor"
    INSPECT = "Inspect further"


class Confidence(str, Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"


@dataclass
class SoHResult:
    """The engine's output: one health score plus the reasoning behind it."""

    soh_percent: float                       # headline State-of-Health (0-100)
    verdict: Verdict
    recommendation: str                      # one-line plain-language advice
    range_retained_percent: float            # how much driving range is left vs new
    remaining_life_years: float              # estimated years until end-of-life (70% SoH)
    confidence: Confidence
    confidence_score: float                  # 0..1, how much we trust this result

    # transparency: how we got here
    capacity_based_soh: Optional[float] = None   # SoH from measured capacity (if available)
    model_based_soh: Optional[float] = None      # SoH from the ageing model
    penalties_applied: float = 0.0               # total % knocked off for health flags
    flags: list[str] = field(default_factory=list)   # notable issues found
    notes: list[str] = field(default_factory=list)   # assumptions / caveats

    # detailed breakdown (for a full, readable certificate)
    estimated_cycles: float = 0.0                # equivalent full cycles used in scoring
    calendar_loss_pct: float = 0.0               # capacity lost to age alone
    cycle_loss_pct: float = 0.0                  # capacity lost to usage cycles
    penalty_items: list[dict] = field(default_factory=list)  # [{"label":..., "points":...}]

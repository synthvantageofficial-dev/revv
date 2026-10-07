"""
Revv battery health scoring engine -- v1 (transparent model).

WHY A TRANSPARENT MODEL FIRST
-----------------------------
A truly accurate State-of-Health (SoH) model is learned from thousands of real
battery readings. We don't have that data yet. So v1 is a *physics- and
rules-based* estimator: every number below comes from published lithium-ion
ageing behaviour, and every assumption is a named constant we can re-tune once
real Revv test data starts coming in. Nothing here is a black box.

HOW A SCORE IS BUILT
--------------------
1. Capacity-based SoH   : if we measured the current full-charge capacity, the
                          most direct truth is measured / rated.
2. Model-based SoH      : an independent estimate from calendar age + usage
                          (this is our cross-check on what the car claims).
3. Blend                : if we have both, we lean on the measured value but let
                          the model pull it if they disagree badly.
4. Health penalties     : subtract for real warning signs -- cell imbalance,
                          high internal resistance, heavy fast-charging, heat.
5. Derive outputs       : range retained, remaining life, verdict, confidence.

All tunable constants live in AgeingParams so calibration later is a one-file job.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import (
    BatteryReading,
    Chemistry,
    Confidence,
    SoHResult,
    Verdict,
)

END_OF_LIFE_SOH = 70.0  # industry convention: a traction battery is "end of life" at 70% SoH


@dataclass(frozen=True)
class AgeingParams:
    """
    Tunable ageing constants. v1 values are reasonable published estimates,
    NOT measured from Revv data yet. Calibrate these as real readings arrive.
    """
    # Calendar fade: capacity lost per year just from time/aging (%).
    calendar_fade_pct_per_year: float = 2.0
    # Cycle fade: capacity lost per one full equivalent charge cycle (%).
    cycle_fade_pct_per_cycle: float = 0.006

    @staticmethod
    def for_chemistry(chem: Chemistry) -> "AgeingParams":
        if chem == Chemistry.LFP:
            # LFP ages slower on both counts.
            return AgeingParams(calendar_fade_pct_per_year=1.5, cycle_fade_pct_per_cycle=0.004)
        if chem == Chemistry.NMC:
            return AgeingParams(calendar_fade_pct_per_year=2.0, cycle_fade_pct_per_cycle=0.006)
        # Unknown -> slightly conservative (assume faster NMC-like fade).
        return AgeingParams(calendar_fade_pct_per_year=2.2, cycle_fade_pct_per_cycle=0.007)


# --- thresholds for health flags (v1, calibratable) ---
IMBALANCE_WARN_MV = 50.0      # cell voltage spread above this starts to worry
IMBALANCE_BAD_MV = 120.0      # clearly unhealthy imbalance
RESISTANCE_WARN_RATIO = 1.3   # internal resistance 30% above baseline -> ageing
RESISTANCE_BAD_RATIO = 1.8    # 80% above baseline -> serious
FASTCHARGE_HEAVY = 0.6        # >60% of energy via DC fast charging stresses the pack
HOT_CLIMATE_C = 32.0          # sustained high ambient temperature accelerates fade


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _estimate_equivalent_cycles(reading: BatteryReading) -> float:
    """
    If the pack didn't report lifetime cycles, estimate them from distance.

    One "equivalent full cycle" = using the whole usable pack once. So total
    cycles ~= total energy used / pack size, and total energy used ~= distance
    / efficiency.
    """
    if reading.equivalent_full_cycles is not None:
        return reading.equivalent_full_cycles
    if reading.rated_capacity_kwh <= 0 or reading.efficiency_km_per_kwh <= 0:
        return 0.0
    energy_used_kwh = reading.odometer_km / reading.efficiency_km_per_kwh
    return energy_used_kwh / reading.rated_capacity_kwh


def _model_based_soh(reading: BatteryReading, params: AgeingParams, cycles: float) -> float:
    """Independent SoH estimate from calendar age + usage cycles."""
    calendar_loss = params.calendar_fade_pct_per_year * max(reading.age_years, 0.0)
    cycle_loss = params.cycle_fade_pct_per_cycle * max(cycles, 0.0)
    return _clamp(100.0 - calendar_loss - cycle_loss)


def _health_penalties(reading: BatteryReading) -> tuple[float, list[str], list[str], list[dict]]:
    """
    Subtract capacity for concrete warning signs. Returns
    (total_penalty_percent, flags, notes, itemised_penalties).
    """
    penalty = 0.0
    flags: list[str] = []
    notes: list[str] = []
    items: list[dict] = []

    def add(points: float, label: str):
        nonlocal penalty
        penalty += points
        items.append({"label": label, "points": round(points, 1)})

    # Cell imbalance: a big spread means some cells are failing.
    spread = reading.cell_voltage_spread_mv
    if spread is not None:
        if spread >= IMBALANCE_BAD_MV:
            add(6.0, "High cell imbalance")
            flags.append(f"High cell imbalance ({spread:.0f} mV) -- weak cells in the pack")
        elif spread >= IMBALANCE_WARN_MV:
            add(2.5, "Mild cell imbalance")
            flags.append(f"Mild cell imbalance ({spread:.0f} mV)")

    # Internal resistance: rises as a battery degrades.
    r = reading.internal_resistance_mohm
    r0 = reading.internal_resistance_baseline_mohm
    if r is not None and r0 and r0 > 0:
        ratio = r / r0
        if ratio >= RESISTANCE_BAD_RATIO:
            add(5.0, "High internal resistance")
            flags.append(f"Internal resistance {ratio:.1f}x of healthy -- notable ageing")
        elif ratio >= RESISTANCE_WARN_RATIO:
            add(2.0, "Elevated internal resistance")
            flags.append(f"Internal resistance {ratio:.1f}x of healthy")

    # Heavy DC fast-charging stresses cells over time.
    fc = reading.dc_fastcharge_ratio
    if fc is not None and fc >= FASTCHARGE_HEAVY:
        add(1.5, "Heavy DC fast-charging")
        flags.append(f"Heavy fast-charging ({fc*100:.0f}% of energy via DC)")

    # Hot climate accelerates calendar fade.
    t = reading.avg_ambient_temp_c
    if t is not None and t >= HOT_CLIMATE_C:
        add(1.0, "Hot-climate exposure")
        notes.append(f"Lives in a hot climate (avg {t:.0f}C) -- ageing runs faster here")

    return penalty, flags, notes, items


def _confidence(reading: BatteryReading) -> tuple[Confidence, float]:
    """
    How much should a buyer trust this score? More real measurements -> more
    confidence. Returns (band, 0..1 score).
    """
    score = 0.45  # base: we always have age + odometer + rated capacity
    if reading.measured_capacity_kwh is not None:
        score += 0.25  # the single strongest signal
    if reading.cell_voltage_spread_mv is not None:
        score += 0.10
    if reading.internal_resistance_mohm is not None and reading.internal_resistance_baseline_mohm:
        score += 0.10
    if reading.equivalent_full_cycles is not None:
        score += 0.05
    if reading.dc_fastcharge_ratio is not None:
        score += 0.03
    score = min(score, 0.98)

    if score >= 0.8:
        band = Confidence.HIGH
    elif score >= 0.6:
        band = Confidence.MEDIUM
    else:
        band = Confidence.LOW
    return band, round(score, 2)


def _verdict(soh: float, flags: list[str]) -> tuple[Verdict, str]:
    """Map a score (and any critical flags) to a plain-language verdict."""
    has_critical = any("High cell imbalance" in f or "notable ageing" in f for f in flags)

    if has_critical and soh >= 80:
        # Numbers look fine but a safety signal says stop and check.
        return Verdict.INSPECT, "Score looks healthy, but a warning sign needs a closer look before buying."

    if soh >= 90:
        return Verdict.EXCELLENT, "Excellent battery health -- safe to buy."
    if soh >= 80:
        return Verdict.GOOD, "Good battery health -- safe to buy."
    if soh >= END_OF_LIFE_SOH:
        return Verdict.FAIR, "Fair health -- usable, but negotiate the price for the wear."
    return Verdict.POOR, "Poor battery health -- high risk. Replacement may be near."


def _remaining_life_years(soh: float, age_years: float, cycles: float, params: AgeingParams) -> float:
    """
    Rough years left until the pack hits 70% SoH, at its current ageing rate.
    """
    if soh <= END_OF_LIFE_SOH:
        return 0.0
    annual_cycles = (cycles / age_years) if age_years > 0.5 else cycles
    annual_fade = params.calendar_fade_pct_per_year + params.cycle_fade_pct_per_cycle * annual_cycles
    if annual_fade <= 0:
        return 0.0
    years = (soh - END_OF_LIFE_SOH) / annual_fade
    return round(max(years, 0.0), 1)


def score_battery(reading: BatteryReading) -> SoHResult:
    """
    Turn one BatteryReading into a full SoHResult. This is the function the
    rest of the product (API, certificate, dashboard) calls.
    """
    missing = reading.missing_required()
    if missing:
        raise ValueError(f"Cannot score: missing required fields {missing}")

    params = AgeingParams.for_chemistry(reading.chemistry)
    cycles = _estimate_equivalent_cycles(reading)
    notes: list[str] = []

    # 1 & 2: the two independent estimates
    calendar_loss = round(params.calendar_fade_pct_per_year * max(reading.age_years, 0.0), 1)
    cycle_loss = round(params.cycle_fade_pct_per_cycle * max(cycles, 0.0), 1)
    model_soh = _model_based_soh(reading, params, cycles)

    capacity_soh = None
    if reading.measured_capacity_kwh is not None and reading.rated_capacity_kwh > 0:
        capacity_soh = _clamp(reading.measured_capacity_kwh / reading.rated_capacity_kwh * 100.0)

    # 3: blend
    if capacity_soh is not None:
        # Trust the measurement, but if the two disagree a lot, split the difference
        # a little -- a measured capacity can itself be read optimistically by the car.
        gap = abs(capacity_soh - model_soh)
        if gap > 8:
            base_soh = 0.75 * capacity_soh + 0.25 * model_soh
            notes.append("Measured capacity and the ageing model disagreed; score blended toward the measurement.")
        else:
            base_soh = capacity_soh
    else:
        base_soh = model_soh
        notes.append("No measured capacity available; score is from the ageing model only.")

    # 4: health penalties
    penalty, flags, pnotes, penalty_items = _health_penalties(reading)
    notes.extend(pnotes)
    final_soh = round(_clamp(base_soh - penalty), 1)

    # 5: derived outputs
    verdict, recommendation = _verdict(final_soh, flags)
    confidence_band, confidence_score = _confidence(reading)
    remaining = _remaining_life_years(final_soh, reading.age_years, cycles, params)

    if reading.equivalent_full_cycles is None:
        notes.append(f"Charge cycles estimated from distance (~{cycles:.0f} full cycles).")

    return SoHResult(
        soh_percent=final_soh,
        verdict=verdict,
        recommendation=recommendation,
        range_retained_percent=final_soh,   # to a buyer, range tracks SoH closely
        remaining_life_years=remaining,
        confidence=confidence_band,
        confidence_score=confidence_score,
        capacity_based_soh=round(capacity_soh, 1) if capacity_soh is not None else None,
        model_based_soh=round(model_soh, 1),
        penalties_applied=round(penalty, 1),
        flags=flags,
        notes=notes,
        estimated_cycles=round(cycles, 0),
        calendar_loss_pct=calendar_loss,
        cycle_loss_pct=cycle_loss,
        penalty_items=penalty_items,
    )

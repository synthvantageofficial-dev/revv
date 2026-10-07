"""
Vehicle spec database.

In real use, our software knows each EV's factory spec (nameplate pack size,
chemistry, a healthy internal-resistance baseline) from its model or VIN -- the
operator and buyer don't type these. The dongle reports what the car *claims*;
this table is the trusted reference we check it against.

v1 is a hand-built table of popular Indian EVs. It grows over time and can later
be backed by a proper database or an external spec API. Lookup is forgiving:
a partial, case-insensitive match on the model name.
"""

from __future__ import annotations

# chemistry: "NMC" or "LFP"
# rated_capacity_kwh: usable nameplate pack size
# resistance_baseline_mohm: approx healthy DC internal resistance (for ageing checks)
SPECS: dict[str, dict] = {
    "Tata Nexon EV":        {"rated_capacity_kwh": 40.5, "chemistry": "NMC", "resistance_baseline_mohm": 48},
    "Tata Nexon EV Prime":  {"rated_capacity_kwh": 30.2, "chemistry": "NMC", "resistance_baseline_mohm": 50},
    "Tata Punch EV":        {"rated_capacity_kwh": 35.0, "chemistry": "LFP", "resistance_baseline_mohm": 46},
    "Tata Tiago EV":        {"rated_capacity_kwh": 24.0, "chemistry": "LFP", "resistance_baseline_mohm": 55},
    "Tata Tigor EV":        {"rated_capacity_kwh": 26.0, "chemistry": "LFP", "resistance_baseline_mohm": 54},
    "MG ZS EV":             {"rated_capacity_kwh": 44.5, "chemistry": "NMC", "resistance_baseline_mohm": 44},
    "MG Comet EV":          {"rated_capacity_kwh": 17.3, "chemistry": "LFP", "resistance_baseline_mohm": 62},
    "Mahindra XUV400":      {"rated_capacity_kwh": 39.4, "chemistry": "NMC", "resistance_baseline_mohm": 47},
    "Hyundai Kona Electric":{"rated_capacity_kwh": 39.2, "chemistry": "NMC", "resistance_baseline_mohm": 45},
    "Hyundai Creta Electric":{"rated_capacity_kwh": 51.4, "chemistry": "NMC", "resistance_baseline_mohm": 42},
    "BYD Atto 3":           {"rated_capacity_kwh": 60.5, "chemistry": "LFP", "resistance_baseline_mohm": 38},
    "Citroen eC3":          {"rated_capacity_kwh": 29.2, "chemistry": "NMC", "resistance_baseline_mohm": 52},
}


def get_spec(model_hint: str | None) -> dict | None:
    """
    Find the factory spec for a model name. Case-insensitive; matches if the
    known model name appears in the hint or vice-versa (handles trim suffixes
    like 'Tata Nexon EV Max XZ+'). Returns the spec dict (with 'model' added)
    or None if we don't have it yet.
    """
    if not model_hint:
        return None
    h = model_hint.strip().lower()

    # exact first
    for name, spec in SPECS.items():
        if name.lower() == h:
            return {"model": name, **spec}
    # longest partial match wins (so "Nexon EV Prime" beats "Nexon EV")
    best = None
    for name, spec in SPECS.items():
        nl = name.lower()
        if nl in h or h in nl:
            if best is None or len(name) > len(best[0]):
                best = (name, spec)
    if best:
        return {"model": best[0], **best[1]}
    return None


def known_models() -> list[str]:
    return list(SPECS.keys())

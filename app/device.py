"""
Mock OBD device layer.

In the real product this layer talks to a physical OBD dongle over Bluetooth /
WiFi / SIM and pulls raw data out of the car. We don't have a dongle yet, so
this simulates exactly that: it returns the kind of *raw, messy* payload a real
dongle hands over -- per-cell voltages, a manufacture date, lifetime energy,
etc. -- NOT the clean numbers our engine wants.

The job of turning this raw payload into engine input is done by ingest.py,
so when a real dongle arrives we only replace THIS file.
"""

from __future__ import annotations

import time


# Each entry mimics what a dongle reads off one car. Note it's raw:
#  - cell voltages as a list (spread must be computed)
#  - manufacture_date, not age
#  - lifetime_energy_kwh, not cycles
#  - some fields missing, exactly like a real scan that couldn't read everything.
_RAW_VEHICLES = {
    "healthy": {
        "label": "Tata Nexon EV — 2 yrs, well kept",
        "payload": {
            "vin": "MAT625NEXON0A1234",
            "model_hint": "Tata Nexon EV",
            "chemistry": "NMC",
            "pack_nominal_kwh": 40.5,
            "pack_energy_full_kwh": 38.4,          # dongle could measure full charge
            "cell_voltages_mv": [3905, 3885, 3900, 3898, 3902, 3891],
            "dc_internal_resistance_mohm": 52,
            "dc_internal_resistance_baseline_mohm": 48,
            "odometer_km": 24000,
            "manufacture_date": "2024-07",
            "lifetime_energy_kwh": 15390,          # ~380 full cycles of a 40.5 kWh pack
            "dc_fastcharge_ratio": 0.25,
            "ambient_temp_c": 28,
        },
    },
    "average": {
        "label": "MG ZS EV — 4 yrs, average use",
        "payload": {
            "vin": "MA3ZSEV0004XY4567",
            "model_hint": "MG ZS EV",
            "chemistry": "NMC",
            "pack_nominal_kwh": 44.5,
            "pack_energy_full_kwh": None,          # dongle could NOT read full capacity
            "cell_voltages_mv": [3880, 3835, 3870, 3860, 3842],
            "dc_internal_resistance_mohm": None,   # not available on this scan
            "dc_internal_resistance_baseline_mohm": None,
            "odometer_km": 62000,
            "manufacture_date": "2022-07",
            "lifetime_energy_kwh": None,           # -> cycles will be estimated from odometer
            "dc_fastcharge_ratio": None,
            "ambient_temp_c": 30,
        },
    },
    "worn": {
        "label": "Commercial EV — 5 yrs, heavy use",
        "payload": {
            "vin": "MC9COMMEV0005CD8899",
            "model_hint": "Commercial EV",
            "chemistry": "NMC",
            "pack_nominal_kwh": 30.2,
            "pack_energy_full_kwh": 21.8,
            "cell_voltages_mv": [3900, 3765, 3850, 3820, 3788],   # wide spread -> imbalance
            "dc_internal_resistance_mohm": 98,
            "dc_internal_resistance_baseline_mohm": 50,
            "odometer_km": 145000,
            "manufacture_date": "2021-05",
            "lifetime_energy_kwh": 63420,          # ~2100 cycles of a 30.2 kWh pack
            "dc_fastcharge_ratio": 0.80,
            "ambient_temp_c": 36,
        },
    },
}


def list_vehicles() -> list[dict]:
    """Demo vehicles the operator can 'scan' (stands in for plugging a dongle in)."""
    return [{"id": vid, "label": v["label"]} for vid, v in _RAW_VEHICLES.items()]


def scan(vehicle_id: str, simulate_delay: bool = False) -> dict:
    """
    Pretend to connect to the dongle and read the car. Returns the RAW payload.
    `simulate_delay` adds a short pause like a real Bluetooth read would.
    """
    if vehicle_id not in _RAW_VEHICLES:
        raise KeyError(f"Unknown vehicle '{vehicle_id}'")
    if simulate_delay:
        time.sleep(1.0)
    # Return a copy so callers can't mutate our demo data.
    return dict(_RAW_VEHICLES[vehicle_id]["payload"])

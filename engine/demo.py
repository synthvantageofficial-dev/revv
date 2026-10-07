"""
Revv engine demo.

Run from the engine/ folder:

    python demo.py

It scores three example used EVs -- a healthy one, an average one, and a
worn-out/abused one -- and prints a full battery health certificate for each,
so you can SEE the engine working end to end.
"""

from revv_engine import (
    BatteryReading,
    Chemistry,
    score_battery,
    build_certificate,
    format_certificate,
)


# 1) A well-kept 2-year-old EV, with a proper OBD measurement available.
healthy = BatteryReading(
    vehicle_model="Tata Nexon EV (well-kept)",
    vin_or_regno="DL3CAB1234",
    rated_capacity_kwh=40.5,
    age_years=2,
    odometer_km=24000,
    measured_capacity_kwh=38.4,         # ~95% of rated
    equivalent_full_cycles=380,
    cell_voltage_spread_mv=22,
    internal_resistance_mohm=52,
    internal_resistance_baseline_mohm=48,
    dc_fastcharge_ratio=0.25,
    avg_ambient_temp_c=28,
    chemistry=Chemistry.NMC,
)

# 2) An average 4-year-old EV, limited data (no measured capacity).
average = BatteryReading(
    vehicle_model="MG ZS EV (average use)",
    vin_or_regno="MH12XY4567",
    rated_capacity_kwh=44.5,
    age_years=4,
    odometer_km=62000,
    cell_voltage_spread_mv=45,
    chemistry=Chemistry.NMC,
    avg_ambient_temp_c=30,
)

# 3) A high-mileage, fast-charged, hot-climate EV with warning signs.
worn = BatteryReading(
    vehicle_model="Commercial EV (heavy use)",
    vin_or_regno="TS09CD8899",
    rated_capacity_kwh=30.2,
    age_years=5,
    odometer_km=145000,
    measured_capacity_kwh=21.8,         # ~72% of rated
    equivalent_full_cycles=2100,
    cell_voltage_spread_mv=135,         # bad imbalance
    internal_resistance_mohm=98,
    internal_resistance_baseline_mohm=50,  # ~2x healthy
    dc_fastcharge_ratio=0.8,
    avg_ambient_temp_c=36,
    chemistry=Chemistry.NMC,
)


def main() -> None:
    for reading in (healthy, average, worn):
        result = score_battery(reading)
        cert = build_certificate(reading, result)
        print(format_certificate(cert))
        print()


if __name__ == "__main__":
    main()

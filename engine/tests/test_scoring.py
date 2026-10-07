"""
Tests for the Revv scoring engine. Run from the engine/ folder:

    python -m unittest discover -s tests

These lock in the behaviour we care about so future changes can't silently
break the score. No external libraries needed -- plain unittest.
"""

import unittest

from revv_engine import (
    BatteryReading,
    Chemistry,
    Verdict,
    Confidence,
    score_battery,
    build_certificate,
)


def _new_ev() -> BatteryReading:
    """A nearly-new, healthy EV with full measurements."""
    return BatteryReading(
        vehicle_model="Test EV",
        rated_capacity_kwh=40.0,
        age_years=1,
        odometer_km=12000,
        measured_capacity_kwh=39.0,
        cell_voltage_spread_mv=15,
        internal_resistance_mohm=50,
        internal_resistance_baseline_mohm=48,
        dc_fastcharge_ratio=0.2,
        chemistry=Chemistry.NMC,
    )


class ScoringTests(unittest.TestCase):

    def test_healthy_battery_scores_high(self):
        result = score_battery(_new_ev())
        self.assertGreaterEqual(result.soh_percent, 90)
        self.assertEqual(result.verdict, Verdict.EXCELLENT)

    def test_worn_battery_scores_low_and_flags(self):
        worn = BatteryReading(
            vehicle_model="Worn EV",
            rated_capacity_kwh=30.0,
            age_years=6,
            odometer_km=160000,
            measured_capacity_kwh=19.5,          # 65% of rated
            cell_voltage_spread_mv=140,          # bad imbalance
            internal_resistance_mohm=100,
            internal_resistance_baseline_mohm=50,
            dc_fastcharge_ratio=0.85,
            chemistry=Chemistry.NMC,
        )
        result = score_battery(worn)
        self.assertLess(result.soh_percent, 70)
        self.assertEqual(result.verdict, Verdict.POOR)
        self.assertTrue(result.flags, "worn battery should raise warning flags")
        self.assertGreater(result.penalties_applied, 0)

    def test_soh_is_bounded_0_to_100(self):
        result = score_battery(_new_ev())
        self.assertGreaterEqual(result.soh_percent, 0)
        self.assertLessEqual(result.soh_percent, 100)

    def test_confidence_lower_without_measurements(self):
        """A reading with only the basics should be trusted less than a full one."""
        full = score_battery(_new_ev())
        sparse = score_battery(BatteryReading(
            vehicle_model="Sparse EV",
            rated_capacity_kwh=40.0,
            age_years=1,
            odometer_km=12000,
            chemistry=Chemistry.NMC,
        ))
        self.assertGreater(full.confidence_score, sparse.confidence_score)
        self.assertEqual(sparse.confidence, Confidence.LOW)

    def test_lfp_ages_slower_than_nmc(self):
        """Same usage, LFP chemistry should retain more health than NMC."""
        base = dict(vehicle_model="Chem EV", rated_capacity_kwh=40.0,
                    age_years=5, odometer_km=90000)
        nmc = score_battery(BatteryReading(chemistry=Chemistry.NMC, **base))
        lfp = score_battery(BatteryReading(chemistry=Chemistry.LFP, **base))
        self.assertGreater(lfp.soh_percent, nmc.soh_percent)

    def test_missing_required_field_raises(self):
        with self.assertRaises(ValueError):
            score_battery(BatteryReading(vehicle_model="Empty", rated_capacity_kwh=0))

    def test_certificate_has_id_and_score(self):
        reading = _new_ev()
        cert = build_certificate(reading, score_battery(reading))
        self.assertTrue(cert["certificate_id"].startswith("REVV-"))
        self.assertIn("soh_percent", cert["summary"])
        # detailed sections must be present
        for section in ("vehicle", "battery_detail", "how_scored", "data_quality"):
            self.assertIn(section, cert)


if __name__ == "__main__":
    unittest.main()

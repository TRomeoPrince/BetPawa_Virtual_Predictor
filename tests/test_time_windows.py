import unittest

from backend.time_windows import (
    EAT,
    TIME_SOURCE,
    UTC_OFFSET,
    annotate_support_time,
    apply_time_confirmation,
    estimate_target_datetime_eat,
    estimated_time_context,
    hour_window,
)


def support(family, rule_id, league, market, rate=0.60):
    return {
        "strategy_id": rule_id,
        "rule_id": rule_id,
        "strategy_family": family,
        "league": league,
        "target_market": market,
        "historical_win_rate": rate,
        "wins": 60,
        "tests": 100,
    }


class TimeWindowTests(unittest.TestCase):
    def test_anchor_reconstruction(self):
        dt = estimate_target_datetime_eat(139222, 33)
        self.assertEqual(dt.strftime("%Y-%m-%d %H:%M"), "2026-10-18 15:05")
        self.assertEqual(dt.tzinfo, EAT)

    def test_five_minute_progression_and_season_rollover(self):
        md33 = estimate_target_datetime_eat(139222, 33)
        md34 = estimate_target_datetime_eat(139222, 34)
        next_md1 = estimate_target_datetime_eat(139223, 1)
        self.assertEqual(int((md34 - md33).total_seconds()), 300)
        self.assertEqual(int((next_md1 - md34).total_seconds()), 300)

    def test_current_cycle_example(self):
        self.assertEqual(
            estimate_target_datetime_eat(139240, 1).strftime("%H:%M"),
            "15:25",
        )
        self.assertEqual(
            estimate_target_datetime_eat(139240, 34).strftime("%H:%M"),
            "18:10",
        )
        self.assertEqual(
            estimate_target_datetime_eat(139241, 1).strftime("%H:%M"),
            "18:15",
        )

    def test_midnight_rollover_and_hour_bucket(self):
        dt = estimate_target_datetime_eat(139226, 4)
        self.assertEqual(dt.strftime("%H:%M"), "00:00")
        self.assertEqual(hour_window(dt.hour), "00:00-00:59")

    def test_metadata_is_estimated_eat(self):
        info = estimated_time_context(139240, 1)
        self.assertEqual(info["time_source"], TIME_SOURCE)
        self.assertEqual(info["timezone"], "EAT")
        self.assertEqual(info["utc_offset"], UTC_OFFSET)

    def test_exact_rule_time_stats_do_not_leak_to_another_rule(self):
        very = annotate_support_time(
            support("Pattern 2", "P2-BTTS-03", "Spanish", "BTTS YES"),
            139222, 1,
        )
        # 139222 MD1 = 12:25, so use a season/matchday that reconstructs to 22h.
        # Search deterministically within one cycle for the first 22h matchday.
        found = None
        for season in range(139222, 139240):
            for md in range(1, 35):
                if estimate_target_datetime_eat(season, md).hour == 22:
                    found = (season, md)
                    break
            if found:
                break
        self.assertIsNotNone(found)
        very = annotate_support_time(
            support("Pattern 2", "P2-BTTS-03", "Spanish", "BTTS YES"),
            *found,
        )
        other = annotate_support_time(
            support("Pattern 2", "P2-O25-04", "Spanish", "Over 2.5 FT"),
            *found,
        )
        self.assertEqual(very["time_status"], "VERY STRONG")
        self.assertAlmostEqual(very["time_historical_rate"], 61 / 74)
        self.assertEqual(other["time_status"], "NORMAL")
        self.assertIsNone(other["time_historical_rate"])

    def test_no_percentage_averaging(self):
        # Find a reconstructed 20:xx target for Spanish P2 O2.5.
        found = None
        for season in range(139222, 139240):
            for md in range(1, 35):
                if estimate_target_datetime_eat(season, md).hour == 20:
                    found = (season, md)
                    break
            if found:
                break
        self.assertIsNotNone(found)
        item = {
            "league": "Spanish",
            "target_home": "A",
            "target_away": "B",
            "expected": "Over 2.5 FT",
            "supports": [
                support("Pattern 2", "P2-O25-04", "Spanish", "Over 2.5 FT", 0.6197),
                support("Pattern 1", "unknown-rule", "Spanish", "Over 2.5 FT", 0.70),
            ],
        }
        out = apply_time_confirmation(item, *found)
        self.assertEqual(out["time_status"], "STRONG")
        self.assertAlmostEqual(out["time_historical_rate"], 26 / 35)
        self.assertEqual(len(out["time_supports"]), 2)

    def test_time_layer_does_not_use_target_results(self):
        base = {
            "league": "Dutch",
            "target_home": "AJX",
            "target_away": "PSV",
            "expected": "Over 2.5 FT",
            "supports": [
                support("Pattern 2", "P2-O25-01", "Dutch", "Over 2.5 FT", 0.6859)
            ],
        }
        a = apply_time_confirmation({**base, "ft_home": 0, "ft_away": 0}, 139240, 1)
        b = apply_time_confirmation({**base, "ft_home": 7, "ft_away": 6}, 139240, 1)
        self.assertEqual(a["time_status"], b["time_status"])
        self.assertEqual(a["time_window"], b["time_window"])
        self.assertEqual(a["time_historical_rate"], b["time_historical_rate"])

    def test_pattern_family_identification_is_preserved(self):
        item = {
            "supports": [
                support("Pattern 1", "old-rule", "English", "Over 2.5 FT"),
                support("Pattern 2", "P2-O25-04", "Spanish", "Over 2.5 FT"),
            ]
        }
        out = apply_time_confirmation(item, 139240, 1)
        self.assertEqual(
            [x["strategy_family"] for x in out["time_supports"]],
            ["Pattern 1", "Pattern 2"],
        )


if __name__ == "__main__":
    unittest.main()

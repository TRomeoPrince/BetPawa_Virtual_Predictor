import tempfile
import unittest
from pathlib import Path

from backend import db as dbmod
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

    def test_matching_time_is_explicitly_reported(self):
        found = None
        for season in range(139222, 139240):
            for md in range(1, 35):
                if estimate_target_datetime_eat(season, md).hour == 22:
                    found = (season, md)
                    break
            if found:
                break
        self.assertIsNotNone(found)
        out = annotate_support_time(
            support("Pattern 2", "P2-BTTS-03", "Spanish", "BTTS YES"),
            *found,
        )
        self.assertEqual(out["time_alignment"], "MATCH")
        self.assertEqual(out["time_alignment_window"], "22:00-22:59")
        self.assertAlmostEqual(out["time_historical_rate"], 61 / 74)
        self.assertIn("falls inside", out["time_alignment_note"])
        self.assertEqual(out["time_historical_windows"][0]["time_window"], "22:00-22:59")

    def test_non_matching_time_is_explicitly_reported(self):
        found = None
        for season in range(139222, 139240):
            for md in range(1, 35):
                if estimate_target_datetime_eat(season, md).hour == 20:
                    found = (season, md)
                    break
            if found:
                break
        self.assertIsNotNone(found)
        out = annotate_support_time(
            support("Pattern 2", "P2-O25-04", "Spanish", "Over 2.5 FT"),
            *found,
        )
        self.assertEqual(out["time_alignment"], "MATCH")
        self.assertEqual(out["time_alignment_window"], "20:00-20:59")
        self.assertAlmostEqual(out["time_historical_rate"], 26 / 35)

        no_match = annotate_support_time(
            support("Pattern 2", "P2-O25-04", "Spanish", "Over 2.5 FT"),
            139240,
            1,
        )
        self.assertEqual(no_match["estimated_target_time_eat"], "15:25")
        self.assertEqual(no_match["time_alignment"], "NO MATCH")
        self.assertEqual(no_match["time_status"], "NO ALIGNMENT")
        self.assertIsNone(no_match["time_historical_rate"])
        self.assertIn("does not match", no_match["time_alignment_note"])

    def test_exact_rule_time_stats_do_not_leak_to_another_rule(self):
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
        self.assertEqual(very["time_alignment"], "MATCH")
        self.assertAlmostEqual(very["time_historical_rate"], 61 / 74)
        self.assertEqual(other["time_status"], "NO ALIGNMENT")
        self.assertEqual(other["time_alignment"], "NO MATCH")
        self.assertIsNone(other["time_historical_rate"])

    def test_no_percentage_averaging(self):
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
        self.assertEqual(out["time_alignment"], "MATCH")
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
        self.assertEqual(a["time_alignment"], b["time_alignment"])
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
        self.assertEqual(len(out["time_supports"]), 2)
        self.assertEqual(out["time_alignment"], "NO MATCH")

    def test_database_persists_and_grades_time_supports(self):
        old_db = dbmod.DB
        try:
            with tempfile.TemporaryDirectory() as td:
                dbmod.DB = Path(td) / "predictor.db"
                raw = {
                    "league": "Spanish",
                    "target_position": 1,
                    "target_home": "BAR",
                    "target_away": "RMA",
                    "expected": "BTTS YES",
                    "target_market": "BTTS YES",
                    "selected_team": None,
                    "supports": [
                        support(
                            "Pattern 2", "P2-BTTS-03",
                            "Spanish", "BTTS YES", 0.6305,
                        )
                    ],
                }
                found = None
                for season in range(139222, 139240):
                    for md in range(1, 35):
                        if estimate_target_datetime_eat(season, md).hour == 22:
                            found = (season, md)
                            break
                    if found:
                        break
                self.assertIsNotNone(found)
                season, md = found
                pred = apply_time_confirmation(raw, season, md)
                pred.update({
                    "confidence": 0.6305,
                    "alignment": None,
                    "recent_wins": None,
                    "recent_tests": None,
                })
                result = {
                    "season": str(season),
                    "next_matchday": md,
                    "next_round_id": "r1",
                    "predictions": [pred],
                }
                user_id = "a" * 32
                dbmod.save_user_prediction_batch(user_id, result)

                graded = dbmod.grade_user_predictions(user_id, [{
                    "season": str(season),
                    "matchday": str(md),
                    "leagues": {
                        "Spanish": [{
                            "home": "BAR",
                            "away": "RMA",
                            "ht_home": 1,
                            "ht_away": 1,
                            "ft_home": 2,
                            "ft_away": 1,
                        }]
                    },
                }])
                self.assertEqual(graded, 1)

                hist = dbmod.get_user_history(user_id)
                self.assertEqual(hist["overall"]["wins"], 1)
                self.assertEqual(
                    hist["recent_batches"][0]["predictions"][0]["time_status"],
                    "VERY STRONG",
                )
                rows = hist["by_rule_time_internal"]
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["wins"], 1)
                self.assertEqual(rows[0]["rule_id"], "P2-BTTS-03")
        finally:
            dbmod.DB = old_db


if __name__ == "__main__":
    unittest.main()

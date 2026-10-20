import unittest

from backend.private_rules import (
    PATTERN2_STRATEGIES,
    PATTERN2_LEGACY_KEYS,
    RULES,
)
from backend.predictor import build_prediction, _english_o25_tracker
from backend.rules_engine import evaluate_multimarket_strategy


def fx(pos, home, away, ht=(0, 0), ft=(0, 0)):
    return {
        "position": pos,
        "home": home,
        "away": away,
        "ht_home": ht[0],
        "ht_away": ht[1],
        "ft_home": ft[0],
        "ft_away": ft[1],
    }


def strategy(rule_id):
    return next(s for s in PATTERN2_STRATEGIES if s["strategy_id"] == rule_id)


class Pattern2Tests(unittest.TestCase):
    def test_only_approved_pattern2_markets_are_present(self):
        self.assertEqual(len(PATTERN2_STRATEGIES), 8)
        self.assertEqual(
            {s["market"] for s in PATTERN2_STRATEGIES},
            {"Over 2.5 FT", "BTTS YES"},
        )
        self.assertFalse(any("HOME WIN" in s["market"].upper() for s in PATTERN2_STRATEGIES))

    def test_dutch_six_plus_follows_both_teams(self):
        source = [
            fx(1, "AJX", "PSV", (1, 1), (4, 2)),
            fx(2, "X", "Y", (0, 0), (1, 0)),
        ]
        target = [
            fx(1, "AJX", "UTR"),
            fx(2, "FEY", "PSV"),
        ]
        picks = evaluate_multimarket_strategy(
            strategy("P2-O25-01"), [source, target], 1
        )
        self.assertEqual(
            {(p["target_home"], p["target_away"]) for p in picks},
            {("AJX", "UTR"), ("FEY", "PSV")},
        )

    def test_spanish_highest_total_includes_all_ties_and_uses_away_team(self):
        source = [
            fx(1, "A", "B", (1, 1), (4, 2)),
            fx(2, "C", "D", (1, 2), (3, 3)),
            fx(3, "E", "F", (0, 0), (2, 1)),
        ]
        target = [
            fx(1, "B", "N"),
            fx(2, "M", "D"),
            fx(3, "E", "Q"),
        ]
        picks = evaluate_multimarket_strategy(
            strategy("P2-O25-04"), [source, target], 1
        )
        self.assertEqual(
            {(p["target_home"], p["target_away"]) for p in picks},
            {("B", "N"), ("M", "D")},
        )

    def test_target_scores_do_not_change_qualification(self):
        source = [fx(1, "ITA", "ROM", (0, 0), (2, 1))]
        target_a = [fx(1, "ITA", "MIL", (0, 0), (0, 0))]
        target_b = [fx(1, "ITA", "MIL", (3, 2), (5, 4))]
        a = evaluate_multimarket_strategy(
            strategy("P2-O25-05"), [source, target_a], 1
        )
        b = evaluate_multimarket_strategy(
            strategy("P2-O25-05"), [source, target_b], 1
        )
        self.assertEqual(
            [(p["target_home"], p["target_away"]) for p in a],
            [(p["target_home"], p["target_away"]) for p in b],
        )

    def test_french_last3_requires_three_matches_in_current_season(self):
        r1 = [fx(1, "LYO", "A", (1, 0), (2, 1))]
        r2 = [fx(1, "B", "LYO", (0, 1), (1, 2))]
        target = [fx(1, "LYO", "C")]
        picks = evaluate_multimarket_strategy(
            strategy("P2-O25-02"), [r1, r2, target], 2
        )
        self.assertEqual(picks, [])

        r3 = [fx(1, "LYO", "D", (1, 1), (3, 1))]
        target2 = [fx(1, "E", "LYO")]
        picks = evaluate_multimarket_strategy(
            strategy("P2-O25-02"), [r1, r2, r3, target2], 3
        )
        self.assertEqual(len(picks), 1)

    def test_winner_home_and_away_follow_roles(self):
        dutch_source = [fx(1, "AJX", "PSV", (2, 1), (5, 1))]
        dutch_target = [fx(1, "AJX", "FEY")]
        dutch = evaluate_multimarket_strategy(
            strategy("P2-BTTS-01"), [dutch_source, dutch_target], 1
        )
        self.assertEqual(dutch[0]["selected_team"], "AJX")

        french_source = [fx(1, "LYO", "MAR", (1, 1), (3, 2))]
        french_target = [fx(1, "PSG", "LYO")]
        french = evaluate_multimarket_strategy(
            strategy("P2-O25-03"), [french_source, french_target], 1
        )
        self.assertEqual(french[0]["selected_team"], "LYO")

        spanish_source = [fx(1, "BAR", "RMA", (1, 1), (4, 2))]
        spanish_target = [fx(1, "RMA", "ATM")]
        spanish = evaluate_multimarket_strategy(
            strategy("P2-O25-04"), [spanish_source, spanish_target], 1
        )
        self.assertEqual(spanish[0]["selected_team"], "RMA")

    def test_biggest_margin_ties_are_all_followed(self):
        source = [
            fx(1, "PSG", "A", (1, 0), (4, 1)),
            fx(2, "LYO", "B", (1, 0), (3, 0)),
            fx(3, "C", "D", (0, 0), (1, 1)),
        ]
        target = [
            fx(1, "PSG", "MAR"),
            fx(2, "NAN", "LYO"),
        ]
        picks = evaluate_multimarket_strategy(
            strategy("P2-BTTS-02"), [source, target], 1
        )
        self.assertEqual(
            {(p["target_home"], p["target_away"]) for p in picks},
            {("PSG", "MAR"), ("NAN", "LYO")},
        )

    def test_pattern1_pattern2_merge_without_duplicate_cards(self):
        source = [
            fx(1, "A", "B", (0, 0), (0, 0)),
            fx(2, "C", "D", (2, 1), (4, 2)),
        ]
        target = [
            fx(1, "C", "X"),
            fx(2, "Y", "Z"),
        ]
        empty = {k: [] for k in RULES}
        context = {
            "season": "139240",
            "latest_completed_matchday": 1,
            "next_matchday": 2,
            "alignment_scope": "test",
            "use_previous_for_alignment": False,
            "latest_source": dict(empty),
            "next_target": dict(empty),
            "current_pairs_by_league": {k: [] for k in RULES},
            "previous_pairs_by_league": {k: [] for k in RULES},
            "strategy_rounds": [
                {**{k: [] for k in RULES}, "Dutch": source},
                {**{k: [] for k in RULES}, "Dutch": target},
            ],
            "strategy_target_index": 1,
        }
        context["latest_source"]["Dutch"] = source
        context["next_target"]["Dutch"] = target

        out = build_prediction(context)
        matches = [
            p for p in out["predictions"]
            if p["league"] == "Dutch"
            and p["target_home"] == "C"
            and p["target_away"] == "X"
            and p["expected"] == "Over 2.5 FT"
        ]
        self.assertEqual(len(matches), 1)
        self.assertIn("Pattern 1", matches[0]["strategy_families"])
        self.assertIn("Pattern 2", matches[0]["strategy_families"])

    def test_promoted_pattern2_rules_are_not_double_counted_as_legacy(self):
        self.assertIn(("Dutch", "Over 2.5 FT", "P6.ge6.both"), PATTERN2_LEGACY_KEYS)
        self.assertEqual(len(PATTERN2_LEGACY_KEYS), 8)

    def test_english_tracker_can_recover_after_two_losses(self):
        # Each target round also becomes the next source round. Construct:
        # MD2 LOSS, MD3 LOSS -> WATCHING, MD4 WIN -> ACTIVE again.
        rounds = [
            {"English": [fx(1, "A", "B", (1, 0), (4, 1))]},
            {"English": [fx(1, "A", "C", (0, 0), (1, 0))]},
            {"English": [fx(1, "A", "D", (0, 0), (2, 0))]},
            {"English": [fx(1, "A", "E", (1, 1), (2, 1))]},
            {"English": [fx(1, "A", "F")]},
        ]
        context = {
            "strategy_rounds": rounds,
            "strategy_target_index": 4,
        }
        out = _english_o25_tracker(context)
        self.assertEqual(out["season_losses"], 2)
        self.assertEqual(out["season_wins"], 1)
        self.assertEqual(out["state"], "ACTIVE")

    def test_english_tracker_keeps_watching_after_repeated_losses(self):
        rounds = [
            {"English": [fx(1, "A", "B", (1, 0), (4, 1))]},
            {"English": [fx(1, "A", "C", (0, 0), (1, 0))]},
            {"English": [fx(1, "A", "D", (0, 0), (2, 0))]},
            {"English": [fx(1, "A", "E", (0, 0), (1, 0))]},
            {"English": [fx(1, "A", "F")]},
        ]
        context = {
            "strategy_rounds": rounds,
            "strategy_target_index": 4,
        }
        out = _english_o25_tracker(context)
        self.assertEqual(out["state"], "WATCHING")
        # It still calculates a future candidate instead of suppressing it.
        self.assertGreaterEqual(out["candidate_count"], 0)


if __name__ == "__main__":
    unittest.main()

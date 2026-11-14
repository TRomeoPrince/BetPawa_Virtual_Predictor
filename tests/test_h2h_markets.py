"""Regression tests for independent cross-market paired-fixture research."""
import unittest
from backend.h2h_markets import evaluate_pair_picks
from backend.predictor import build_prediction
from backend.private_rules import RULES
from backend.db import _grade_market


def fixture(home, away, position=1, ft_home=None, ft_away=None):
    return {"home": home, "away": away, "position": position,
            "ft_home": ft_home, "ft_away": ft_away}


class PairedFixtureTests(unittest.TestCase):
    def markets(self, home, away):
        picks = evaluate_pair_picks([fixture(home, away)])
        return {p["target_market"]: p for p in picks}

    def test_all_three_markets_on_same_fixture(self):
        markets = self.markets("Aston Villa", "Crystal Palace")
        self.assertEqual(set(markets), {"HOME WIN", "Over 2.5 FT", "BTTS YES"})
        self.assertEqual(markets["HOME WIN"]["support"]["wins"], 7)
        self.assertEqual(markets["BTTS YES"]["support"]["tests"], 8)

    def test_reverse_is_independent_and_watch_not_promoted(self):
        villa_reverse = self.markets("Crystal Palace", "Aston Villa")
        self.assertEqual(set(villa_reverse), {"AWAY WIN", "BTTS NO"})
        self.assertEqual(villa_reverse["AWAY WIN"]["support"]["research_status"], "watch")
        self.assertEqual(villa_reverse["BTTS NO"]["support"]["research_status"], "screened")
        brentford_reverse = self.markets("Sunderland", "Brentford")
        self.assertEqual(set(brentford_reverse), {"AWAY WIN"})
        self.assertEqual(brentford_reverse["AWAY WIN"]["support"]["wins"], 2)

    def test_btts_over_win_independently(self):
        both = self.markets("Tottenham Hotspur", "Crystal Palace")
        self.assertEqual(set(both), {"HOME WIN", "Over 2.5 FT", "BTTS YES"})
        reverse = self.markets("Crystal Palace", "Tottenham")
        self.assertEqual(set(reverse), {"BTTS YES", "Over 2.5 FT"})
        self.assertEqual(reverse["Over 2.5 FT"]["support"]["research_status"], "watch")
        self.assertEqual(set(self.markets("Chelsea", "Tottenham Hotspur")), {"BTTS YES", "Over 2.5 FT"})
        self.assertEqual(set(self.markets("Tottenham", "Chelsea")), {"BTTS YES", "Over 2.5 FT"})

    def test_unknown_and_other_leagues_not_falsely_matched(self):
        self.assertEqual(evaluate_pair_picks([fixture("Arsenal", "Newcastle")]), [])
        self.assertEqual(evaluate_pair_picks([fixture("Sunderland", "Aston Villa")]), [])

    def test_future_score_does_not_change_pick(self):
        pending = evaluate_pair_picks([fixture("Brentford", "Sunderland")])
        finished = evaluate_pair_picks([fixture("Brentford", "Sunderland", ft_home=0, ft_away=5)])
        self.assertEqual([p["target_market"] for p in pending],
                         [p["target_market"] for p in finished])
        self.assertTrue(_grade_market("BTTS YES", {"ft_home": 1, "ft_away": 1}))
        self.assertFalse(_grade_market("Over 2.5 FT", {"ft_home": 1, "ft_away": 1}))
        self.assertFalse(_grade_market("HOME WIN", {"ft_home": 1, "ft_away": 1}))

    def test_build_prediction_keeps_separate_markets(self):
        empty = {name: [] for name in RULES}
        context = {
            "season": "139446", "next_matchday": 6, "latest_completed_matchday": 5,
            "alignment_scope": "test", "latest_source": dict(empty),
            "next_target": {**empty, "English": [
                fixture("Aston Villa", "Crystal Palace"),
                fixture("Tottenham", "Chelsea", position=2),
            ]},
            "current_pairs_by_league": {name: [] for name in RULES},
            "previous_pairs_by_league": {name: [] for name in RULES},
        }
        result = build_prediction(context)
        picks = {(p["target_home"], p["target_away"], p["expected"]): p
                 for p in result["predictions"]}
        self.assertEqual(len(picks), 5)
        self.assertIn(("Aston Villa", "Crystal Palace", "HOME WIN"), picks)
        self.assertIn(("Aston Villa", "Crystal Palace", "BTTS YES"), picks)
        self.assertIn(("Aston Villa", "Crystal Palace", "Over 2.5 FT"), picks)
        self.assertIn(("Tottenham", "Chelsea", "BTTS YES"), picks)
        self.assertIn(("Tottenham", "Chelsea", "Over 2.5 FT"), picks)


if __name__ == "__main__":
    unittest.main()

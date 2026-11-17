"""Regression tests for stricter, honest next-round H2H recommendations."""
import unittest

from backend.recommendation_quality import rank_recommendations


def pick(home, away, market, league="English"):
    return {
        "league": league, "target_home": home, "target_away": away,
        "expected": market, "confidence": 0.82,
    }


class ConservativeRecommendationsTests(unittest.TestCase):
    def test_strong_fixture_direction_and_market_remain_separate(self):
        data = [
            pick("Tottenham", "Chelsea", "BTTS YES"),
            pick("Tottenham", "Chelsea", "Over 2.5 FT"),
            pick("Chelsea", "Tottenham", "Over 2.5 FT"),
            pick("Aston Villa", "Crystal Palace", "HOME WIN"),
            pick("Tottenham", "Crystal Palace", "HOME WIN"),
        ]
        featured, watches = rank_recommendations(data)
        markets = {(p["target_home"], p["target_away"], p["expected"]) for p in featured}
        self.assertEqual(markets, {(p["target_home"], p["target_away"], p["expected"]) for p in data})
        self.assertEqual(watches, [])
        self.assertEqual(featured[0]["research_evidence"]["validation_wins"], 9)
        self.assertEqual(featured[0]["research_evidence"]["validation_tests"], 9)
        self.assertEqual(featured[0]["research_evidence"]["recent_tests"], 2)

    def test_bre_sun_removed_from_featured_both_directions(self):
        data = [
            pick("Brentford", "Sunderland", "HOME WIN"),
            pick("Brentford", "Sunderland", "BTTS YES"),
            pick("Sunderland", "Brentford", "AWAY WIN"),
            pick("Chelsea", "Tottenham", "Over 2.5 FT"),
        ]
        featured, watches = rank_recommendations(data)
        self.assertEqual([(x["target_home"], x["expected"]) for x in featured],
                         [("Chelsea", "Over 2.5 FT")])
        self.assertFalse(watches)

    def test_cry_tot_watch_is_not_called_featured(self):
        featured, watches = rank_recommendations([
            pick("Crystal Palace", "Tottenham", "BTTS YES"),
            pick("Crystal Palace", "Tottenham", "Over 2.5 FT"),
            pick("Tottenham", "Crystal Palace", "BTTS YES"),
        ])
        self.assertEqual(len(featured), 1)
        self.assertEqual(featured[0]["target_home"], "Tottenham")
        self.assertEqual(len(watches), 1)
        self.assertEqual(watches[0]["target_home"], "Crystal Palace")
        self.assertEqual(watches[0]["research_evidence"]["status"], "watch-only")
        self.assertEqual(watches[0]["research_evidence"]["validation_wins"], 7)
        self.assertEqual(watches[0]["research_evidence"]["validation_tests"], 11)

    def test_unknown_fixture_or_market_is_never_fabricated(self):
        data = [
            pick("Arsenal", "Man City", "HOME WIN"),
            pick("Tottenham", "Chelsea", "HOME WIN"),
            pick("Chelsea", "Tottenham", "BTTS YES"),
            pick("Tottenham", "Chelsea", "BTTS YES", league="Dutch"),
        ]
        self.assertEqual(rank_recommendations(data), ([], []))
        self.assertEqual(rank_recommendations([]), ([], []))

    def test_no_future_score_or_fake_odds_needed(self):
        item = pick("Tottenham", "Chelsea", "BTTS YES")
        featured, _ = rank_recommendations([item])
        self.assertNotIn("odds", featured[0])
        self.assertNotIn("ft_home", featured[0])
        self.assertNotIn("ft_away", featured[0])
        self.assertNotIn("probability", featured[0])
        self.assertIn("Small historical samples", featured[0]["research_evidence"]["sample_note"])
        item["ft_home"], item["ft_away"] = 0, 1
        afterward, _ = rank_recommendations([item])
        self.assertEqual(featured[0]["research_evidence"], afterward[0]["research_evidence"])


if __name__ == "__main__":
    unittest.main()

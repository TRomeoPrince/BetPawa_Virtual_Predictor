"""1X2 market integration: historical options and live E011 12/1X.

The page is a combined interface: bookmaker 1X2 and Double Chance are still
different priced markets, with independent candidate selection rules.
"""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend import db, main, one_x_two_market


def context():
    return {
        "season": "139510",
        "next_matchday": 3,
        "next_round_id": "round-3",
        "next_target": {"English": [{"position": 1, "home": "Home", "away": "Away"}]},
        "double_chance_research": [
            {"league": "English", "home": "Home", "away": "Away",
             "selection": "12", "decimal_odds": 1.256,
             "bookmaker_probability_pct": 75.59},
            {"league": "English", "home": "Home", "away": "Away",
             "selection": "1X", "decimal_odds": 1.327,
             "bookmaker_probability_pct": 71.95},
        ],
        "completed_rounds_for_grading": [],
    }


class OneXTwoMarketTests(unittest.TestCase):
    def test_dc_captured_live_quote_maps_to_two_distinct_picks(self):
        picks = one_x_two_market.from_context(context())
        self.assertEqual({p["expected"] for p in picks}, {"12", "1X"})
        self.assertEqual({p["target_position"] for p in picks}, {1})
        self.assertTrue(all(p["research_status"] == "experimental" for p in picks))
        self.assertTrue(all(p["top_historical_win_rate"] > 0.7 for p in picks))

    def test_reject_unmatched_fixture_and_unapproved_selection(self):
        ctx = context()
        ctx["next_target"]["English"][0]["home"] = "Other"
        self.assertFalse(one_x_two_market.from_context(ctx))
        ctx = context()
        ctx["double_chance_research"][0]["selection"] = "X2"
        self.assertEqual([p["expected"] for p in one_x_two_market.from_context(ctx)], ["1X"])

    def test_all_six_result_symbols_grade_correctly(self):
        home = {"ft_home": 2, "ft_away": 1}
        draw = {"ft_home": 1, "ft_away": 1}
        away = {"ft_home": 0, "ft_away": 2}
        truth = {
            "1": (True, False, False),
            "X": (False, True, False),
            "2": (False, False, True),
            "1X": (True, True, False),
            "X2": (False, True, True),
            "12": (True, False, True),
        }
        for selection, expected in truth.items():
            with self.subTest(selection=selection):
                actual = tuple(db._grade_market(selection, row) for row in [home, draw, away])
                self.assertEqual(actual, expected)
                self.assertEqual(main._market_category(selection), "wins")
                self.assertIn(selection, db._CATEGORY_SQL["wins"])

    def test_end_to_end_market_api_saved_picks_and_old_url_redirect(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_db = db.DB
            db.DB = Path(tmp) / "research_test.sqlite"
            account = {"role": "admin", "user_key": "one_x_two_test",
                       "subscription": {"is_active": True}}
            try:
                with patch.object(main, "_require_account", return_value=account), \
                     patch.object(main, "_session_account", return_value=account), \
                     patch.object(main, "_require_active_access", return_value=account), \
                     patch.object(main.feed, "prediction_context", return_value=context()), \
                     patch.object(main, "build_prediction", return_value={"predictions": []}):
                    with TestClient(main.app, follow_redirects=False) as client:
                        self.assertEqual(client.get("/client/1x2").status_code, 200)
                        old = client.get("/client/wins")
                        self.assertEqual(old.status_code, 302)
                        self.assertEqual(old.headers["location"], "/client/1x2")
                        res = client.post("/api/predict/1x2")
                        self.assertEqual(res.status_code, 200, res.text)
                        selections = res.json()["predictions"]
                        self.assertEqual({p["expected"] for p in selections}, {"12", "1X"})
                        self.assertEqual(res.json()["next_matchday"], 3)
                        for name in ("12", "1X"):
                            chosen = client.post("/api/selection", json={
                                "season": "139510", "matchday": "3", "league": "English",
                                "target_home": "Home", "target_away": "Away",
                                "expected": name, "selected": True,
                            })
                            self.assertEqual(chosen.status_code, 200, chosen.text)
                        matched = db.grade_user_predictions(account["user_key"], [{
                            "season": "139510", "matchday": 3,
                            "leagues": {"English": [
                                {"home": "Home", "away": "Away", "ft_home": 1, "ft_away": 1}
                            ]},
                        }])
                        self.assertEqual(matched, 2)
                        history = client.get("/api/history/1x2")
                        self.assertEqual(history.status_code, 200, history.text)
                        picks = client.get("/api/client/picks?scope=all&category=wins")
                        self.assertEqual(picks.status_code, 200, picks.text)
                        self.assertEqual(picks.json()["total"], 2)
                        outcomes = {p["expected"]: p["outcome"] for p in picks.json()["items"]}
                        self.assertEqual(outcomes, {"12": "LOST", "1X": "WON"})
            finally:
                db.DB = old_db

    def test_free_accounts_are_not_given_vip_dc_picks(self):
        restricted = {"role": "client", "email": "",
                      "subscription": {"is_active": False}}
        with patch.object(main, "_require_account", return_value=restricted):
            with TestClient(main.app, follow_redirects=False) as client:
                res = client.post("/api/predict/1x2")
        self.assertEqual(res.status_code, 403)


if __name__ == "__main__":
    unittest.main()

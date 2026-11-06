import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend import access, db


class PicksHubTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_access_db, self.old_db = access.DB, db.DB
        access.DB = db.DB = Path(self.temp.name) / "predictor.db"
        self.env = patch.dict(os.environ, {"PREDICTOR_ADMIN_PASSWORD": "TestAdminPassword123!"})
        self.env.start()
        from backend import main
        self.main = main
        access.ensure_bootstrap_admin()
        self.client = TestClient(main.app, follow_redirects=False)
        self.alice, self.alice_password = access.create_client("alice_picks", "Alice", "weekly")
        self.bob, self.bob_password = access.create_client("bob_picks", "Bob", "weekly")
        self.login("alice_picks", self.alice_password)

    def tearDown(self):
        self.client.close()
        self.env.stop()
        access.DB, db.DB = self.old_access_db, self.old_db
        self.temp.cleanup()

    def login(self, username, password):
        response = self.client.post("/api/auth/login", json={"username": username, "password": password})
        self.assertEqual(response.status_code, 200, response.text)

    def seed(self, season, matchday, markets, user=None):
        user_key = (user or self.alice)["user_key"]
        batch = {"season": str(season), "next_matchday": str(matchday), "next_round_id": "round-"+str(matchday),
                 "predictions": []}
        for i, market in enumerate(markets):
            batch["predictions"].append({
                "league": "ENGLISH", "target_home": "Home"+str(i),
                "target_away": "Away"+str(i), "expected": market,
                "selected_team": "PRIVATE_TEAM", "supports": [{
                    "strategy_family": "Private", "rule_id": "SECRET_RULE",
                    "strategy_name": "PRIVATE_STRATEGY",
                }],
            })
        db.save_user_prediction_batch(user_key, batch)
        for p in batch["predictions"]:
            self.assertTrue(db.set_prediction_selected(
                user_key, str(season), str(matchday), p["league"],
                p["target_home"], p["target_away"], p["expected"], True,
            ))

    def test_login_required_and_private_hub_access(self):
        self.assertEqual(self.client.get("/client/picks").status_code, 200)
        self.assertIn("My Picks Hub", self.client.get("/client/picks").text)
        self.client.post("/api/auth/logout")
        self.assertEqual(self.client.get("/client/picks").status_code, 302)
        self.assertEqual(self.client.get("/api/client/picks").status_code, 401)
        self.assertEqual(self.client.get("/api/client/bet-journal").status_code, 401)

    def test_combines_all_markets_and_shows_older_history(self):
        self.seed("2026", 3, ["Over 2.5 FT", "Under 3.5 FT", "BTTS Yes", "Home Win"])
        self.seed("2026", 4, ["Over 3.5 FT", "BTTS No"])
        latest = self.client.get("/api/client/picks").json()
        self.assertEqual(latest["latest_matchday"], {"season": "2026", "matchday": "4"})
        self.assertEqual(latest["total"], 2)
        self.assertEqual(latest["summary"]["total"], 6)
        self.assertEqual(latest["summary"]["by_category"], {
            "overs": 2, "unders": 1, "btts": 2, "wins": 1,
        })
        self.assertEqual({p["category"] for p in latest["items"]}, {"overs", "btts"})
        self.assertNotIn("PRIVATE", str(latest))
        self.assertNotIn("SECRET", str(latest))
        history = self.client.get("/api/client/picks?scope=history").json()
        self.assertEqual(history["total"], 4)
        self.assertEqual({p["matchday"] for p in history["items"]}, {"3"})
        btts = self.client.get("/api/client/picks?scope=all&category=btts").json()
        self.assertEqual(btts["total"], 2)
        self.assertEqual(self.client.get("/api/client/picks?category=unknown").status_code, 400)
        self.assertEqual(self.client.get("/api/client/picks?outcome=INVALID").status_code, 400)

    def test_results_pagination_and_market_selection_changes(self):
        for day in range(1, 9):
            self.seed("2026", day, ["Over 2.5 FT"])
        page1 = self.client.get("/api/client/picks?scope=all&limit=3").json()
        page2 = self.client.get("/api/client/picks?scope=all&limit=3&offset=3").json()
        self.assertEqual(page1["total"], 8)
        self.assertEqual(len(page1["items"]), 3)
        self.assertEqual(len(page2["items"]), 3)
        self.assertNotEqual(page1["items"][0]["id"], page2["items"][0]["id"])
        self.assertEqual(self.client.get("/api/client/picks?scope=history").json()["total"], 7)
        graded = db.grade_user_predictions(self.alice["user_key"], [{
            "season": "2026", "matchday": 8,
            "leagues": {"ENGLISH": [{"home": "Home0", "away": "Away0", "ft_home": 2, "ft_away": 1}]},
        }])
        self.assertEqual(graded, 1)
        won = self.client.get("/api/client/picks?outcome=WON").json()
        self.assertEqual(won["total"], 1)
        self.assertEqual(won["items"][0]["ft_home"], 2)
        self.assertEqual(won["summary"]["wins"], 1)
        response = self.client.post("/api/selection", json={
            "season": "2026", "matchday": "8", "league": "ENGLISH",
            "target_home": "Home0", "target_away": "Away0",
            "expected": "Over 2.5 FT", "selected": False,
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get("/api/client/picks").json()["summary"]["total"], 7)

    def test_user_isolation(self):
        self.seed("2026", 2, ["Over 2.5 FT"])
        self.client.post("/api/auth/logout")
        self.login("bob_picks", self.bob_password)
        self.assertEqual(self.client.get("/api/client/picks?scope=all").json()["total"], 0)
        self.seed("2026", 2, ["BTTS Yes"], user=self.bob)
        self.assertEqual(self.client.get("/api/client/picks?scope=all").json()["total"], 1)
        self.assertEqual(self.client.get("/api/client/picks?scope=all").json()["items"][0]["category"], "btts")

    def sample_bet(self, **changes):
        base = {
            "bet_date": "2026-10-28", "league": "English",
            "fixture": "A vs B", "category": "overs", "selection": "Over 2.5 FT",
            "stake_ugx": 5000, "decimal_odds": 2.5, "outcome": "WON",
            "notes": "Manual record",
        }
        base.update(changes)
        return base

    def test_manual_bet_journal_create_edit_delete_and_owner_scope(self):
        created = self.client.post("/api/client/bet-journal", json=self.sample_bet())
        self.assertEqual(created.status_code, 200, created.text)
        bet = created.json()["bet"]
        self.assertEqual(bet["net_ugx"], 7500)
        own = self.client.get("/api/client/bet-journal").json()
        self.assertEqual(own["summary"]["net_ugx"], 7500)
        self.assertEqual(own["total"], 1)
        self.assertEqual(self.client.get("/api/client/bet-journal?category=btts").json()["total"], 0)
        self.client.post("/api/auth/logout")
        self.login("bob_picks", self.bob_password)
        self.assertEqual(self.client.get("/api/client/bet-journal").json()["total"], 0)
        self.assertEqual(self.client.put("/api/client/bet-journal/"+str(bet["id"]), json=self.sample_bet()).status_code, 400)
        self.assertEqual(self.client.delete("/api/client/bet-journal/"+str(bet["id"])).status_code, 404)
        self.client.post("/api/auth/logout")
        self.login("alice_picks", self.alice_password)
        edited = self.client.put("/api/client/bet-journal/"+str(bet["id"]), json=self.sample_bet(
            category="btts", selection="BTTS Yes", outcome="LOST",
        ))
        self.assertEqual(edited.status_code, 200, edited.text)
        self.assertEqual(edited.json()["bet"]["net_ugx"], -5000)
        self.assertEqual(self.client.get("/api/client/bet-journal?outcome=LOST").json()["total"], 1)
        self.assertEqual(self.client.get("/api/client/bet-journal").json()["summary"]["net_ugx"], -5000)
        self.assertEqual(self.client.delete("/api/client/bet-journal/"+str(bet["id"])).status_code, 200)
        self.assertEqual(self.client.get("/api/client/bet-journal").json()["total"], 0)

    def test_manual_journal_validates_data(self):
        for invalid in [
            {"stake_ugx": -1}, {"decimal_odds": 0.5}, {"category": "none"},
            {"outcome": "PAID"}, {"bet_date": "2030-01-01"}, {"fixture": ""},
        ]:
            response = self.client.post("/api/client/bet-journal", json=self.sample_bet(**invalid))
            self.assertIn(response.status_code, (400, 422), response.text)
        self.assertEqual(self.client.get("/api/client/bet-journal?category=other").status_code, 400)

    def test_refresh_outcomes_once_for_all_markets(self):
        self.seed("2026", 3, ["Over 2.5 FT", "BTTS Yes"])
        context = {"completed_rounds_for_grading": [{
            "season": "2026", "matchday": 3,
            "leagues": {"ENGLISH": [
                {"home": "Home0", "away": "Away0", "ft_home": 2, "ft_away": 1},
                {"home": "Home1", "away": "Away1", "ft_home": 1, "ft_away": 1},
            ]},
        }]}
        with patch.object(self.main.feed, "prediction_context", return_value=context):
            refreshed = self.client.post("/api/client/picks/refresh")
        self.assertEqual(refreshed.status_code, 200, refreshed.text)
        self.assertEqual(refreshed.json()["graded_now"], 2)
        self.assertEqual(self.client.get("/api/client/picks").json()["summary"]["wins"], 2)


if __name__ == "__main__":
    unittest.main()

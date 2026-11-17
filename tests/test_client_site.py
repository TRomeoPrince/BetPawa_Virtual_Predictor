import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend import access, db


class ClientSiteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_access_db, self.old_db = access.DB, db.DB
        self.old_password = os.environ.get("PREDICTOR_ADMIN_PASSWORD")
        os.environ["PREDICTOR_ADMIN_PASSWORD"] = "StrongTestPassword2026!"
        access.DB = db.DB = Path(self.temp.name) / "predictor.db"

        # Importing the app bootstraps the admin; each later test creates its
        # own admin in the isolated test database.
        from backend import main
        self.main = main
        access.ensure_bootstrap_admin()
        self.client = TestClient(main.app, follow_redirects=False)

    def tearDown(self):
        self.client.close()
        access.DB, db.DB = self.old_access_db, self.old_db
        if self.old_password is None:
            os.environ.pop("PREDICTOR_ADMIN_PASSWORD", None)
        else:
            os.environ["PREDICTOR_ADMIN_PASSWORD"] = self.old_password
        self.temp.cleanup()

    def login(self, username, password):
        response = self.client.post("/api/auth/login", json={
            "username": username, "password": password,
        })
        self.assertEqual(response.status_code, 200, response.text)
        if response.json()["account"]["must_change_password"]:
            new_password = "UpdatedTestPassword2026!" + username
            changed = self.client.post("/api/auth/change-password", json={
                "current_password": password,
                "new_password": new_password,
                "age_confirmed": True,
            })
            self.assertEqual(changed.status_code, 200, changed.text)
            response = self.client.post("/api/auth/login", json={
                "username": username, "password": new_password,
            })
            self.assertEqual(response.status_code, 200, response.text)

    def test_public_landing_and_protected_markets(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Not affiliated with", response.text)
        self.assertIn('href="/login">Sign in</a>', response.text)
        self.assertNotIn("Client sign in", response.text)
        self.assertNotIn("Under 4.5", response.text)
        self.assertEqual(self.client.get("/client").status_code, 302)
        self.assertEqual(self.client.get("/client/overs").status_code, 302)
        self.assertEqual(self.client.get("/api/admin/clients").status_code, 401)

    def test_client_requests_are_account_scoped(self):
        first, first_password = access.create_client("memberone", "Member One")
        _, second_password = access.create_client("membertwo", "Member Two")
        self.login("memberone", first_password)
        request = self.client.post(
            "/api/client/subscription-request", json={"plan_code": "monthly"}
        )
        self.assertEqual(request.status_code, 200, request.text)
        history = self.client.get("/api/client/subscription-requests").json()
        self.assertEqual(len(history["requests"]), 1)
        self.assertEqual(history["requests"][0]["status"], "pending")
        self.client.post("/api/auth/logout")
        self.login("membertwo", second_password)
        other_history = self.client.get("/api/client/subscription-requests").json()
        self.assertEqual(other_history["requests"], [])
        self.assertEqual(self.client.get("/client/overs").status_code, 200)
        self.assertEqual(self.client.post("/api/predict/overs").status_code, 403)
        self.assertFalse(access.get_account(first["id"])["subscription"]["is_active"])

    def test_history_is_market_scoped_and_combo_stats_are_selected_only(self):
        member, password = access.create_client("memberthree", "Member Three", "weekly")
        self.login("memberthree", password)
        user_key = member["user_key"]
        batch = {
            "season": "2026", "next_matchday": "3", "next_round_id": "round-3",
            "predictions": [
                {"league": "ENGLISH", "target_home": "A", "target_away": "B",
                 "expected": "Over 2.5 FT", "supports": []},
                {"league": "SPANISH", "target_home": "C", "target_away": "D",
                 "expected": "Under 3.5 FT", "supports": []},
            ],
        }
        db.save_user_prediction_batch(user_key, batch)
        db.set_prediction_selected(user_key, "2026", "3", "ENGLISH", "A", "B", "Over 2.5 FT", True)
        over = self.client.get("/api/history/overs")
        under = self.client.get("/api/history/unders")
        self.assertEqual(over.status_code, 200, over.text)
        self.assertEqual(under.status_code, 200, under.text)
        self.assertEqual(len(over.json()["last_batch"]["predictions"]), 1)
        self.assertEqual(len(under.json()["last_batch"]["predictions"]), 1)
        self.assertEqual(over.json()["selected_overall"]["pending"], 1)
        self.assertEqual(under.json()["selected_overall"]["pending"], 0)

        db.grade_user_predictions(user_key, [{
            "season": "2026", "matchday": 3,
            "leagues": {
                "ENGLISH": [{"home": "A", "away": "B", "ft_home": 2, "ft_away": 1}],
                "SPANISH": [{"home": "C", "away": "D", "ft_home": 2, "ft_away": 2}],
            },
        }])
        graded_over = self.client.get("/api/history/overs").json()
        graded_under = self.client.get("/api/history/unders").json()
        self.assertEqual(graded_over["selected_overall"]["wins"], 1)
        self.assertEqual(graded_over["selected_overall"]["win_rate"], 1.0)
        self.assertEqual(graded_over["selected_results"][0]["outcome"], "WON")
        self.assertEqual(graded_under["overall"]["losses"], 1)
        self.assertEqual(graded_under["selected_overall"]["graded"], 0)

    def test_predictions_store_private_rules_but_never_expose_them(self):
        _, password = access.create_client("memberfour", "Member Four", "weekly")
        self.login("memberfour", password)
        prediction = {
            "league": "ENGLISH", "target_home": "A", "target_away": "B",
            "selected_team": "SECRET_SELECTED_TEAM",
            "target_position": 1,
            "expected": "Over 2.5 FT", "top_historical_win_rate": .7,
            "supports": [{
                "strategy_id": "SECRET_RULE_2026", "rule_id": "SECRET_RULE_2026",
                "strategy_family": "Pattern 2", "strategy_name": "SECRET_STRATEGY",
                "selected_teams": ["SECRET_SELECTED_TEAM"],
                "source_fixtures": ["SECRET_SOURCE_FIXTURE"],
                "historical_win_rate": .7, "wins": 70, "tests": 100,
            }],
        }
        context = {
            "season": "2026", "next_matchday": "3", "next_round_id": "round-3",
            "next_target": {"ENGLISH": [{"home": "A", "away": "B"}]},
            "completed_rounds_for_grading": [], "round_cache_hits": 0,
            "round_cache_misses": 0, "context_cache_hit": False,
        }
        result = {
            "season": "2026", "next_matchday": "3",
            "latest_completed_matchday": 2, "next_round_id": "round-3",
            "predictions": [prediction], "leagues": [{"rule_id": "SECRET_RULE_2026"}],
        }
        with patch.object(self.main.feed, "prediction_context", return_value=context), \
             patch.object(self.main, "build_prediction", return_value=result):
            response = self.client.post("/api/predict/overs")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["next_target"]["ENGLISH"][0]["home"], "A")
        self.assertNotIn("SECRET", response.text)
        self.assertNotIn("by_rule_internal", response.text)
        history = self.client.get("/api/history/overs")
        self.assertEqual(history.status_code, 200, history.text)
        self.assertNotIn("SECRET", history.text)
        self.assertNotIn("by_rule_internal", history.text)
        all_history = self.client.get("/api/predictions")
        self.assertEqual(all_history.status_code, 200)
        self.assertNotIn("SECRET", all_history.text)
        self.assertNotIn("by_rule_internal", all_history.text)
        con = db.connect()
        rows = con.execute(
            "SELECT rule_id FROM prediction_supports WHERE rule_id='SECRET_RULE_2026'"
        ).fetchall()
        con.close()
        self.assertEqual(len(rows), 1)


if __name__ == "__main__":
    unittest.main()

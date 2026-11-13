"""Premium shortlist regression tests: fixture exactness, EAT timing and access.

The UI and prediction-engine data are intentionally kept separate.
"""
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from backend import premium_picks


class PremiumPickTests(unittest.TestCase):
    def test_nine_curated_entries_and_reverse_fixtures(self):
        snap = premium_picks.snapshot(datetime(2026, 11, 13, 20, 25, tzinfo=premium_picks.EAT))
        rows = snap["items"]
        self.assertEqual(len(rows), 9)
        self.assertEqual([p["matchday"] for p in rows], [7, 11, 13, 20, 26, 30, 32, 1, 5])
        self.assertEqual(rows[0]["window_open_eat"], "20:40")
        self.assertEqual(rows[8]["season"], "139446")
        self.assertEqual(rows[8]["window_close_eat"], "23:25")
        self.assertEqual(rows[3]["kind"], "watch")
        self.assertEqual(rows[3]["selection"], "Win/loss pattern")
        self.assertEqual(rows[5]["fixture"], "TOT – CHE")
        self.assertEqual(rows[6]["fixture"], "CRY – AST")

    def test_clock_status_and_expiry_are_eat(self):
        now = lambda h, m: datetime(2026, 11, 13, h, m, tzinfo=premium_picks.EAT)
        self.assertEqual(premium_picks.snapshot(now(20, 25))["items"][0]["status"], "upcoming")
        self.assertEqual(premium_picks.snapshot(now(20, 38))["items"][0]["status"], "soon")
        self.assertEqual(premium_picks.snapshot(now(20, 40))["items"][0]["status"], "window")
        self.assertEqual(premium_picks.snapshot(now(20, 45))["items"][0]["status"], "closed")
        self.assertEqual(premium_picks.snapshot(now(20, 45))["items"][1]["status"], "upcoming")
        self.assertEqual(premium_picks.snapshot(datetime(2026, 11, 15, 0, 0, tzinfo=premium_picks.EAT))["items"], [])

    def test_active_free_and_vip_are_separately_gated(self):
        from backend import main
        from fastapi.testclient import TestClient

        api = TestClient(main.app)
        self.assertEqual(api.get("/api/premium-picks").status_code, 401)
        free_user = {"role":"client","email":"free@example.com","subscription":{"is_active":False}}
        vip_user = {"role":"client","email":"vip@example.com","subscription":{"is_active":True}}
        with patch.object(main, "_require_account", return_value=free_user):
            with patch.object(main.free_access, "active_release", return_value=None):
                self.assertEqual(api.get("/api/premium-picks").status_code, 403)
            with patch.object(main.free_access, "active_release", return_value={"id":1,"markets":["btts"]}):
                self.assertEqual(api.get("/api/premium-picks").status_code, 200)
        with patch.object(main, "_require_account", return_value=vip_user):
            self.assertEqual(api.get("/api/premium-picks").status_code, 200)
        api.close()


if __name__ == "__main__":
    unittest.main()

import os
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from backend import access, db, growth
from backend.time_windows import EAT


class FreeMembershipTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.previous = (access.DB, db.DB)
        access.DB = db.DB = Path(self.temp.name) / "predictor.db"
        self.env = patch.dict(os.environ, {
            "PREDICTOR_ADMIN_PASSWORD": "LongAdminPasswordForTests2026!",
            "PREDICTOR_SIGNUP_ENABLED": "true",
        })
        self.env.start()
        from backend import main
        self.main = main
        self.http = TestClient(main.app, follow_redirects=False)

    def tearDown(self):
        self.http.close()
        access.DB, db.DB = self.previous
        self.env.stop()
        self.temp.cleanup()

    def register(self, username, email, ref=""):
        return self.http.post("/api/auth/signup", json={
            "username": username, "display_name": username.title(),
            "email": email, "password": "StrongMemberPassword2026!",
            "age_confirmed": True, "referral_code": ref,
        })

    def test_signup_referral_and_free_status(self):
        first = self.register("alpha", "alpha@example.com")
        self.assertEqual(first.status_code, 200, first.text)
        self.assertFalse(first.json()["account"]["subscription"]["is_active"])
        self.assertEqual(self.http.get("/api/account/contact").json()["email"], "alpha@example.com")
        profile = self.http.get("/api/referrals/me").json()
        self.assertTrue(profile["url"].endswith("/r/" + profile["code"]))
        self.assertEqual(self.http.get("/r/" + profile["code"]).status_code, 302)
        self.http.post("/api/auth/logout")
        second = self.register("beta", "beta@example.com", profile["code"])
        self.assertEqual(second.status_code, 200, second.text)
        growth.mark_vip_conversion(second.json()["account"]["id"])
        self.http.post("/api/auth/logout")
        self.assertEqual(self.http.post("/api/auth/login", json={
            "username": "alpha", "password": "StrongMemberPassword2026!",
        }).status_code, 200)
        stats = self.http.get("/api/referrals/me").json()
        self.assertEqual(stats["signups"], 1)
        self.assertEqual(stats["visits"], 1)
        self.assertEqual(stats["vip_conversions"], 1)
        self.assertFalse(stats["rewards_enabled"])
        self.assertEqual(self.http.get("/api/admin/promotions").status_code, 403)

    def test_promotion_and_free_window(self):
        identifier = growth.create_promotion("weekly", 5000, "WEEKLY5K")
        self.assertEqual(growth.quote("weekly")["price_ugx"], 20000)
        self.assertEqual(growth.quote("weekly", "WEEKLY5K")["price_ugx"], 5000)
        growth.set_promotion_enabled(identifier, False)
        with self.assertRaises(ValueError):
            growth.quote("weekly", "WEEKLY5K")
        automatic = growth.create_promotion("weekly", 5000)
        self.assertEqual(growth.quote("weekly")["price_ugx"], 5000)
        growth.set_promotion_enabled(automatic, False)
        self.assertEqual(growth.quote("weekly")["price_ugx"], 20000)
        when = datetime(2026, 10, 18, 22, 0, tzinfo=EAT)
        example = {"season": 139225, "next_matchday": 14}
        self.assertTrue(self.main._free_round_allowed(example, when))
        self.assertFalse(self.main._free_round_allowed(example, when + timedelta(minutes=25)))
        free = self.main._free_market_result({
            "predictions": [{"league": "ENGLISH"}, {"league": "DUTCH"}, {"league": "ITALIAN"}],
            "next_target": {"ENGLISH": [1], "DUTCH": [2], "ITALIAN": [3]},
        })
        self.assertEqual(len(free["predictions"]), 2)
        self.assertEqual(set(free["next_target"]), {"ENGLISH", "DUTCH"})


if __name__ == "__main__":
    unittest.main()

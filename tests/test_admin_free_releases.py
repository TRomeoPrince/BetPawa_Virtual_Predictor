"""Admin-directed one-off Free release tests: no automatic publishing."""
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend import access, db, free_access
from backend.time_windows import EAT


class AdminFreeReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.before = (access.DB, db.DB)
        access.DB = db.DB = Path(self.temp.name) / "predictor.db"
        self.env = patch.dict(os.environ, {"PREDICTOR_ADMIN_PASSWORD": "AdminFreeReleaseTestPassword2026!"})
        self.env.start()
        from backend import main
        self.main = main
        access.ensure_bootstrap_admin()
        self.member = TestClient(main.app, follow_redirects=False)
        self.admin = TestClient(main.app, follow_redirects=False)
        registered = self.member.post("/api/auth/signup", json={
            "username": "freeguest", "display_name": "Free guest",
            "email": "guest@example.com", "password": "MyStrongSignupPassword2026!",
            "age_confirmed": True,
        })
        self.assertEqual(registered.status_code, 200, registered.text)

    def tearDown(self):
        self.member.close()
        self.admin.close()
        access.DB, db.DB = self.before
        self.env.stop()
        self.temp.cleanup()

    def login_admin(self):
        login = self.admin.post("/api/auth/login", json={
            "username": "admin", "password": "AdminFreeReleaseTestPassword2026!"
        })
        self.assertEqual(login.status_code, 200, login.text)
        changed = self.admin.post("/api/auth/change-password", json={
            "current_password": "AdminFreeReleaseTestPassword2026!",
            "new_password": "AdminPasswordChangedForTests2026!",
        })
        self.assertEqual(changed.status_code, 200, changed.text)
        login = self.admin.post("/api/auth/login", json={
            "username": "admin", "password": "AdminPasswordChangedForTests2026!"
        })
        self.assertEqual(login.status_code, 200, login.text)

    def test_initially_closed_and_admin_only_schedule(self):
        self.assertFalse(self.member.get("/api/free-access/status").json()["open"])
        self.assertEqual(self.member.get("/api/admin/free-releases").status_code, 403)
        self.assertEqual(self.member.post("/api/admin/free-releases", json={}).status_code, 403)
        self.assertEqual(self.member.post("/api/predict/overs").status_code, 403)
        self.login_admin()
        future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        scheduled = self.admin.post("/api/admin/free-releases", json={"starts_at": future})
        self.assertEqual(scheduled.status_code, 200, scheduled.text)
        self.assertFalse(self.member.get("/api/free-access/status").json()["open"])
        listed = self.admin.get("/api/admin/free-releases").json()["releases"]
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["state"], "scheduled")
        self.assertEqual(listed[0]["round_count"], 5)

    def test_open_now_and_disable_immediately(self):
        self.login_admin()
        opened = self.admin.post("/api/admin/free-releases", json={})
        self.assertEqual(opened.status_code, 200, opened.text)
        self.assertTrue(self.member.get("/api/free-access/status").json()["open"])
        ref = opened.json()["id"]
        disabled = self.admin.post(f"/api/admin/free-releases/{ref}/enabled", json={"enabled": False})
        self.assertEqual(disabled.status_code, 200, disabled.text)
        self.assertFalse(self.member.get("/api/free-access/status").json()["open"])
        self.assertEqual(self.admin.delete(f"/api/admin/free-releases/{ref}").status_code, 200)
        self.assertFalse(self.member.get("/api/free-access/status").json()["open"])

    def test_random_release_contains_five_rounds_not_six(self):
        start = datetime(2026, 10, 18, 22, 0, tzinfo=EAT)
        release_id = free_access.create_release(start)
        # At 22:00 the five strictly upcoming rounds are MD15..MD19.
        for matchday in range(15, 20):
            self.assertTrue(free_access.allowed_round(
                {"season": 139225, "next_matchday": matchday},
                start + timedelta(minutes=2),
            ))
        self.assertFalse(free_access.allowed_round(
            {"season": 139225, "next_matchday": 14}, start + timedelta(minutes=2)
        ))
        self.assertFalse(free_access.allowed_round(
            {"season": 139225, "next_matchday": 20}, start + timedelta(minutes=2)
        ))
        self.assertFalse(free_access.allowed_round(
            {"season": 139225, "next_matchday": 15}, start + timedelta(minutes=31)
        ))
        self.assertFalse(free_access.allowed_round(
            {"season": 139225, "next_matchday": 15}, start + timedelta(days=1)
        ))
        with self.assertRaises(ValueError):
            free_access.create_release(start + timedelta(minutes=10))
        free_access.set_enabled(release_id, False)
        self.assertEqual(free_access.create_release(start + timedelta(minutes=10)) > release_id, True)


if __name__ == "__main__":
    unittest.main()

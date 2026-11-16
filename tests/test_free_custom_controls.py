"""Custom free release end times, market selection and legacy migration tests."""
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend import access, db, free_access


class AdminFreeMarketControlTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.before = (access.DB, db.DB)
        access.DB = db.DB = Path(self.temp.name) / "predictor.db"
        self.env = patch.dict(os.environ, {
            "PREDICTOR_ADMIN_PASSWORD": "PrivateFreeMarketAdmin2026!",
            "PREDICTOR_SIGNUP_ENABLED": "true"
        })
        self.env.start()
        from backend import main
        self.member = TestClient(main.app, follow_redirects=False)
        self.admin = TestClient(main.app, follow_redirects=False)
        access.ensure_bootstrap_admin()
        registered = self.member.post("/api/auth/signup", json={
            "username": "freevisitor", "display_name": "Free visitor",
            "email": "test@example.com", "password": "FullLongMemberPassword!",
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
        first = self.admin.post("/api/auth/login", json={
            "username": "admin", "password": "PrivateFreeMarketAdmin2026!",
        })
        self.assertEqual(first.status_code, 200, first.text)
        changed = self.admin.post("/api/auth/change-password", json={
            "current_password": "PrivateFreeMarketAdmin2026!",
            "new_password": "DifferentMarketAdminPassword2026!",
        })
        self.assertEqual(changed.status_code, 200, changed.text)
        self.assertEqual(self.admin.post("/api/auth/login", json={
            "username": "admin", "password": "DifferentMarketAdminPassword2026!"
        }).status_code, 200)

    def test_custom_end_time_and_one_selected_market(self):
        self.login_admin()
        start = datetime.now(timezone.utc) - timedelta(minutes=1)
        end = start + timedelta(hours=1)
        req = self.admin.post("/api/admin/free-releases", json={
            "starts_at": start.isoformat(), "ends_at": end.isoformat(),
            "markets": ["btts"], "enabled": True,
        })
        self.assertEqual(req.status_code, 200, req.text)
        listed = self.admin.get("/api/admin/free-releases").json()["releases"][0]
        self.assertEqual(listed["markets"], ["btts"])
        self.assertGreater(listed["round_count"], 5)
        self.assertEqual(listed["state"], "open")
        status = self.member.get("/api/free-access/status").json()
        self.assertTrue(status["open"])
        self.assertEqual(status["markets"], ["btts"])
        self.assertTrue(free_access.allowed_market("btts"))
        self.assertFalse(free_access.allowed_market("overs"))
        self.assertEqual(self.member.post("/api/predict/overs").status_code, 403)
        self.assertEqual(self.member.post("/api/predict/unders").status_code, 403)
        self.assertEqual(self.member.post("/api/predict/wins").status_code, 403)

        changed = self.admin.patch("/api/admin/free-releases/" + str(req.json()["id"]), json={
            "starts_at": start.isoformat(), "ends_at": (end + timedelta(hours=1)).isoformat(),
            "markets": ["overs", "unders"], "enabled": True,
        })
        self.assertEqual(changed.status_code, 200, changed.text)
        after = self.member.get("/api/free-access/status").json()
        self.assertEqual(after["markets"], ["overs", "unders"])
        self.assertEqual(self.member.post("/api/predict/btts").status_code, 403)
        self.assertFalse(free_access.allowed_market("btts"))
        self.assertTrue(free_access.allowed_market("overs"))
        self.assertTrue(free_access.allowed_market("unders"))

    def test_reject_invalid_end_market_and_cross_origin_admin_mutations(self):
        self.login_admin()
        now = datetime.now(timezone.utc)
        start = (now + timedelta(days=1)).isoformat()
        end = (now + timedelta(days=1, hours=1)).isoformat()
        examples = [
            {"starts_at": start, "ends_at": start, "markets": ["btts"]},
            {"starts_at": start, "ends_at": (now + timedelta(days=368)).isoformat(), "markets": ["btts"]},
            {"starts_at": start, "ends_at": end, "markets": []},
            {"starts_at": start, "ends_at": end, "markets": ["wins"]},
            {"starts_at": start, "ends_at": end, "markets": ["btts", "wins"]},
        ]
        for body in examples:
            with self.subTest(body=body):
                self.assertEqual(self.admin.post("/api/admin/free-releases", json=body).status_code, 400)
        self.assertEqual(self.member.post("/api/admin/free-releases", json={
            "starts_at": start, "ends_at": end, "markets": ["overs"],
        }).status_code, 403)
        self.assertEqual(self.admin.post("/api/admin/free-releases",
            headers={"Origin": "https://foreign.example"},
            json={"starts_at": start, "ends_at": end, "markets": ["overs"]},
        ).status_code, 403)
        good = self.admin.post("/api/admin/free-releases", json={
            "starts_at": start, "ends_at": end, "markets": ["btts", "btts"],
        })
        self.assertEqual(good.status_code, 200, good.text)
        self.assertEqual(self.admin.get("/api/admin/free-releases").json()["releases"][0]["markets"], ["btts"])
        self.assertEqual(self.admin.patch("/api/admin/free-releases/" + str(good.json()["id"]),
            json={"markets": []}).status_code, 400)
        self.assertEqual(self.member.patch("/api/admin/free-releases/" + str(good.json()["id"]),
            json={"markets": ["unders"]}).status_code, 403)

    def test_week_long_free_access_and_flexible_edits_keep_signup_open(self):
        self.login_admin()
        start = datetime.now(timezone.utc) - timedelta(minutes=1)
        week_end = start + timedelta(days=7)
        created = self.admin.post("/api/admin/free-releases", json={
            "starts_at": start.isoformat(), "ends_at": week_end.isoformat(),
            "markets": ["btts", "overs", "unders"], "enabled": True,
        })
        self.assertEqual(created.status_code, 200, created.text)
        release_id = created.json()["id"]
        releases = self.admin.get("/api/admin/free-releases").json()["releases"]
        self.assertEqual(len(releases), 1)
        self.assertEqual(releases[0]["state"], "open")
        self.assertGreater(releases[0]["round_count"], 2000)
        self.assertEqual(releases[0]["markets"], ["btts", "overs", "unders"])
        self.assertTrue(free_access.active_release(now=start + timedelta(days=6)))
        self.assertIsNone(free_access.active_release(now=week_end))

        # Release duration is not a registration control.
        rejected = self.member.post("/api/auth/signup", json={
            "username": "test_week_check", "display_name": "Test",
            "email": "weekly-check@example.com", "password": "StrongEnough2026!",
            "age_confirmed": False,
        })
        self.assertEqual(rejected.status_code, 400, rejected.text)
        self.assertIn("25 years", rejected.json()["detail"])

        # An administrator can extend an existing release to a custom nine-day
        # end, including the interval shown in the reported UI screenshot.
        longer_end = start + timedelta(days=9, minutes=26)
        edited = self.admin.patch(f"/api/admin/free-releases/{release_id}", json={
            "ends_at": longer_end.isoformat(), "markets": ["overs"], "enabled": True,
        })
        self.assertEqual(edited.status_code, 200, edited.text)
        updated = self.admin.get("/api/admin/free-releases").json()["releases"][0]
        self.assertEqual(updated["ends_at"], longer_end.isoformat())
        self.assertEqual(updated["markets"], ["overs"])
        self.assertTrue(free_access.active_release(now=start + timedelta(days=8)))
        self.assertFalse(free_access.allowed_market("btts", now=start + timedelta(days=8)))

        # The cap is a year, not a day; invalid spans still give a clear 400.
        invalid = self.admin.patch(f"/api/admin/free-releases/{release_id}", json={
            "ends_at": (start + timedelta(days=366)).isoformat(),
        })
        self.assertEqual(invalid.status_code, 400)
        self.assertIn("365 days", invalid.json()["detail"])
        self.assertTrue(free_access.active_release(now=start + timedelta(days=8)))

    def test_expired_disabled_release_editable_but_not_reenabled_until_retimed(self):
        self.login_admin()
        now = datetime.now(timezone.utc)
        start = now - timedelta(hours=2)
        old_end = now - timedelta(hours=1)
        result = self.admin.post("/api/admin/free-releases", json={
            "starts_at": start.isoformat(), "ends_at": old_end.isoformat(),
            "markets": ["unders"], "enabled": False,
        })
        self.assertEqual(result.status_code, 200, result.text)
        rid = result.json()["id"]
        refused = self.admin.post(f"/api/admin/free-releases/{rid}/enabled",
            json={"enabled": True})
        self.assertEqual(refused.status_code, 400)
        self.assertIn("already ended", refused.json()["detail"])
        updated = self.admin.patch(f"/api/admin/free-releases/{rid}", json={
            "starts_at": (now + timedelta(minutes=2)).isoformat(),
            "ends_at": (now + timedelta(hours=2)).isoformat(),
            "enabled": True, "markets": ["btts", "overs"],
        })
        self.assertEqual(updated.status_code, 200, updated.text)
        listed = self.admin.get("/api/admin/free-releases").json()["releases"][0]
        self.assertEqual(listed["state"], "scheduled")
        self.assertEqual(listed["markets"], ["btts", "overs"])

    def test_migrate_old_table_and_preserve_original_five_round_release(self):
        con = access.connect()
        try:
            con.execute("""
                CREATE TABLE free_release_windows(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    starts_at TEXT NOT NULL,ends_at TEXT NOT NULL,
                    first_target_eat TEXT NOT NULL,
                    round_count INTEGER NOT NULL DEFAULT 5,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    actor_account_id INTEGER,
                    created_at TEXT NOT NULL,
                    CHECK(round_count=5),CHECK(enabled IN (0,1))
                )
            """)
            now = datetime.now(timezone.utc)
            start = now - timedelta(minutes=1)
            first = free_access._first_target(start)
            end = first.astimezone(timezone.utc) + timedelta(minutes=25)
            con.execute("""
                INSERT INTO free_release_windows(
                  starts_at,ends_at,first_target_eat,round_count,enabled,created_at
                ) VALUES(?,?,?,5,1,?)
            """, (start.isoformat(),end.isoformat(),first.isoformat(),now.isoformat()))
            con.commit()
        finally:
            con.close()
        releases = free_access.list_releases()
        self.assertEqual(len(releases),1)
        self.assertEqual(releases[0]["round_count"],5)
        self.assertEqual(releases[0]["markets"],["overs","unders","btts"])
        self.assertEqual(releases[0]["state"],"open")
        again = free_access.list_releases()
        self.assertEqual(again[0]["id"],releases[0]["id"])

    def test_closed_free_access_does_not_expose_schedule(self):
        self.login_admin()
        next_day=datetime.now(timezone.utc)+timedelta(days=1)
        created=self.admin.post("/api/admin/free-releases",json={
            "starts_at":next_day.isoformat(),
            "ends_at":(next_day+timedelta(hours=2)).isoformat(),
            "markets":["overs"],
        })
        self.assertEqual(created.status_code,200,created.text)
        status=self.member.get("/api/free-access/status").json()
        self.assertFalse(status["open"])
        self.assertEqual(status["markets"],[])
        self.assertNotIn("starts_at",status)
        self.assertNotIn("ends_at",status)


if __name__ == "__main__":
    unittest.main()

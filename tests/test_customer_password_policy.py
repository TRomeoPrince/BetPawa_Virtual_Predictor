"""Password policy: customer accounts 8+, administrators 12+."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from backend import access, db


class CustomerPasswordPolicyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = (access.DB, db.DB)
        access.DB = db.DB = Path(self.tmp.name) / "policy.db"
        self.env = patch.dict(os.environ, {
            "PREDICTOR_ADMIN_PASSWORD": "StrongAdminPassword2026!",
            "PREDICTOR_SIGNUP_ENABLED": "true",
        })
        self.env.start()
        from backend import main
        self.http = TestClient(main.app, follow_redirects=False)

    def tearDown(self):
        self.http.close()
        access.DB, db.DB = self.old
        self.env.stop()
        self.tmp.cleanup()

    def test_eight_character_signup_and_password_change(self):
        values = {"username": "member8", "email": "member8@example.com",
                  "password": "Abc1234", "age_confirmed": True}
        rejected = self.http.post("/api/auth/signup", json=values)
        self.assertEqual(rejected.status_code, 400, rejected.text)
        values["password"] = "Abc12345"
        accepted = self.http.post("/api/auth/signup", json=values)
        self.assertEqual(accepted.status_code, 200, accepted.text)
        changed = self.http.post("/api/auth/change-password", json={
            "current_password": "Abc12345", "new_password": "Xyz54321",
        })
        self.assertEqual(changed.status_code, 200, changed.text)
        self.assertEqual(self.http.post("/api/auth/login", json={
            "username": "member8", "password": "Xyz54321",
        }).status_code, 200)

    def test_admin_still_requires_twelve_characters(self):
        access.ensure_bootstrap_admin()
        logged_in = self.http.post("/api/auth/login", json={
            "username": "admin", "password": "StrongAdminPassword2026!",
        })
        self.assertEqual(logged_in.status_code, 200, logged_in.text)
        denied = self.http.post("/api/auth/change-password", json={
            "current_password": "StrongAdminPassword2026!", "new_password": "Abc12345",
        })
        self.assertEqual(denied.status_code, 400, denied.text)
        self.assertIn("12 to 128", denied.json()["detail"])
        allowed = self.http.post("/api/auth/change-password", json={
            "current_password": "StrongAdminPassword2026!",
            "new_password": "AdminSecure12345",
        })
        self.assertEqual(allowed.status_code, 200, allowed.text)


if __name__ == "__main__":
    unittest.main()

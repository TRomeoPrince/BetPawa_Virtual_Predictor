"""The Railway container must not accept signups or payments on ephemeral storage."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from backend import access, db, purchase_requests
from backend.deployment_preflight import validate_railway_environment


class RailwaySafetyTests(unittest.TestCase):
    def test_local_non_railway_still_allowed(self):
        validate_railway_environment({})

    def test_requires_volume_and_private_admin_password(self):
        env = {"RAILWAY_PROJECT_ID": "project",
               "RAILWAY_VOLUME_MOUNT_PATH": "/var/data",
               "PREDICTOR_DB_PATH": "/var/data/predictor.db",
               "PREDICTOR_ADMIN_PASSWORD": "LongPrivateAdminPassword2026!"}
        with self.assertRaises(RuntimeError):
            validate_railway_environment({**env, "RAILWAY_VOLUME_MOUNT_PATH": ""})
        with self.assertRaises(RuntimeError):
            validate_railway_environment({**env, "PREDICTOR_DB_PATH": "/app/data/predictor.db"})
        with self.assertRaises(RuntimeError):
            validate_railway_environment({**env, "PREDICTOR_ADMIN_PASSWORD": "short"})

    def test_payments_off_by_default_on_railway(self):
        with patch.dict(os.environ, {"RAILWAY_PROJECT_ID": "project"}, clear=True):
            self.assertFalse(purchase_requests.purchase_enabled())
            os.environ["PREDICTOR_PURCHASE_ENABLED"] = "true"
            self.assertTrue(purchase_requests.purchase_enabled())

    def test_signup_off_by_default_on_railway(self):
        with tempfile.TemporaryDirectory() as folder:
            original = access.DB, db.DB
            access.DB = db.DB = Path(folder) / "railway.db"
            try:
                from backend import main
                with patch.dict(os.environ, {"RAILWAY_PROJECT_ID": "project",
                                             "PREDICTOR_ADMIN_PASSWORD": "LongPrivateAdminPassword2026!"},
                                clear=True):
                    with TestClient(main.app) as client:
                        body = {"username": "visitor", "display_name": "Visitor",
                                "email": "visitor@example.org", "password": "Password1234",
                                "age_confirmed": True}
                        self.assertEqual(client.post("/api/auth/signup", json=body).status_code, 503)
                        os.environ["PREDICTOR_SIGNUP_ENABLED"] = "true"
                        self.assertEqual(client.post("/api/auth/signup", json=body).status_code, 200)
            finally:
                access.DB, db.DB = original


if __name__ == "__main__":
    unittest.main()

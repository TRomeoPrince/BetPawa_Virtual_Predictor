import base64
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from backend import access, db


class ExistingAccountUpgradeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = (access.DB, db.DB)
        access.DB = db.DB = Path(self.tmp.name) / "test.db"
        self.env = patch.dict(os.environ, {
            "PREDICTOR_ADMIN_PASSWORD": "StrongAdminPassword2026!",
            "PREDICTOR_PURCHASE_ENABLED": "true",
            "PREDICTOR_PUBLIC_BASE_URL": "https://example.test",
            "PREDICTOR_SMTP_HOST": "",
        })
        self.env.start()
        from backend import main
        self.app = main.app
        self.buyer = TestClient(self.app, follow_redirects=False)
        self.admin = TestClient(self.app, follow_redirects=False)

    def tearDown(self):
        self.buyer.close()
        self.admin.close()
        access.DB, db.DB = self.old
        self.env.stop()
        self.tmp.cleanup()

    def purchase(self, reference):
        proof = b"\x89PNG\r\n\x1a\n" + b"sample-content" * 10 + reference.encode("utf-8")
        return self.buyer.post("/api/purchase/requests", json={
            "email": "buyer@example.com", "username": "buyer",
            "display_name": "Buyer", "plan_code": "weekly",
            "payment_method": "airtel", "transaction_ref": reference,
            "proof_base64": base64.b64encode(proof).decode(), "age_confirmed": True,
        })

    def test_manual_upgrade_preserves_account_and_allows_renewal(self):
        signup = self.buyer.post("/api/auth/signup", json={
            "username": "buyer", "display_name": "Buyer",
            "email": "buyer@example.com", "password": "PasswordForBuyer2026!",
            "age_confirmed": True,
        })
        self.assertEqual(signup.status_code, 200, signup.text)
        account_id = signup.json()["account"]["id"]
        self.assertEqual(self.purchase("TX000001").status_code, 200)
        self.assertFalse(self.buyer.get("/api/auth/me").json()["account"]["subscription"]["is_active"])
        access.ensure_bootstrap_admin()
        self.admin.post("/api/auth/login", json={"username": "admin", "password": "StrongAdminPassword2026!"})
        changed = self.admin.post("/api/auth/change-password", json={
            "current_password": "StrongAdminPassword2026!", "new_password": "ChangedAdminPassword2026!",
        })
        self.assertEqual(changed.status_code, 200, changed.text)
        self.admin.post("/api/auth/login", json={"username": "admin", "password": "ChangedAdminPassword2026!"})
        denied = self.admin.post("/api/admin/payment-requests/1/review", json={
            "approve": True, "verified": False,
        })
        self.assertEqual(denied.status_code, 400)
        # No public domain or ngrok URL is needed to upgrade an existing member.
        with patch.dict(os.environ, {"PREDICTOR_PUBLIC_BASE_URL": ""}):
            approved = self.admin.post("/api/admin/payment-requests/1/review", json={
                "approve": True, "verified": True,
            })
        self.assertEqual(approved.status_code, 200, approved.text)
        self.assertTrue(approved.json()["existing_account"])
        self.assertEqual(approved.json()["client_account_id"], account_id)
        current = self.buyer.get("/api/auth/me").json()["account"]
        self.assertEqual(current["id"], account_id)
        self.assertTrue(current["subscription"]["is_active"])
        self.assertEqual(self.purchase("TX000001").status_code, 400)
        self.assertEqual(self.purchase("TX000002").status_code, 200)


if __name__ == "__main__":
    unittest.main()

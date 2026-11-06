import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend import access, db


class SupervisedOnboardingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_access_db, self.old_db = access.DB, db.DB
        access.DB = db.DB = Path(self.tmp.name) / "predictor.db"
        self.env = patch.dict(os.environ, {"PREDICTOR_ADMIN_PASSWORD": "StrongAdminSetupPassword2026!"})
        self.env.start()
        from backend import main
        self.main = main
        access.ensure_bootstrap_admin()
        self.client = TestClient(main.app, follow_redirects=False)

    def tearDown(self):
        self.client.close()
        access.DB, db.DB = self.old_access_db, self.old_db
        self.env.stop()
        self.tmp.cleanup()

    def login(self, username, password):
        return self.client.post("/api/auth/login", json={
            "username": username, "password": password,
        })

    def complete_setup(self, current, new="PrivateClientPassword2026!", age_confirmed=True):
        return self.client.post("/api/auth/change-password", json={
            "current_password": current, "new_password": new,
            "age_confirmed": age_confirmed,
        })

    def admin_login(self):
        password = os.environ["PREDICTOR_ADMIN_PASSWORD"]
        first = self.login("admin", password)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertTrue(first.json()["account"]["must_change_password"])
        self.assertEqual(self.client.get("/admin").headers.get("location"), "/password-setup")
        self.assertEqual(self.client.get("/api/admin/clients").status_code, 403)
        setup = self.complete_setup(password, "ChangedAdminPassword2026!", False)
        self.assertEqual(setup.status_code, 200, setup.text)
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)
        login = self.login("admin", "ChangedAdminPassword2026!")
        self.assertEqual(login.status_code, 200, login.text)
        self.assertFalse(login.json()["account"]["must_change_password"])

    def test_temporary_password_blocks_dashboard_and_apis(self):
        client, temp = access.create_client("testerone", "Tester One", "weekly")
        login = self.login("testerone", temp)
        self.assertEqual(login.status_code, 200)
        self.assertTrue(login.json()["account"]["must_change_password"])
        self.assertEqual(self.client.get("/login").headers["location"], "/password-setup")
        self.assertEqual(self.client.get("/client").headers["location"], "/password-setup")
        self.assertEqual(self.client.get("/client/picks").headers["location"], "/password-setup")
        self.assertEqual(self.client.get("/client/overs").headers["location"], "/password-setup")
        self.assertEqual(self.client.get("/password-setup").status_code, 200)
        for url in ("/api/client/picks", "/api/client/bet-journal", "/api/client/subscription-requests"):
            blocked = self.client.get(url)
            self.assertEqual(blocked.status_code, 403, (url, blocked.text))
        self.assertEqual(self.client.get("/api/auth/me").status_code, 200)
        self.assertEqual(self.client.get("/api/admin/clients").status_code, 403)
        self.assertTrue(access.get_account(client["id"])["subscription"]["is_active"])

    def test_first_login_requires_25_attestation_and_new_password(self):
        client, temp = access.create_client("testertwo", "Tester Two", "weekly")
        self.assertEqual(self.login("testertwo", temp).status_code, 200)
        self.assertEqual(self.complete_setup(temp, age_confirmed=False).status_code, 400)
        self.assertEqual(self.complete_setup(temp, "short").status_code, 400)
        self.assertEqual(self.complete_setup(temp, temp).status_code, 400)
        self.assertEqual(self.complete_setup("incorrect").status_code, 400)
        self.assertTrue(access.get_account(client["id"])["must_change_password"])
        changed = self.complete_setup(temp)
        self.assertEqual(changed.status_code, 200, changed.text)
        self.assertTrue(changed.json()["requires_login"])
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)
        self.assertEqual(self.login("testertwo", temp).status_code, 401)
        new_login = self.login("testertwo", "PrivateClientPassword2026!")
        self.assertEqual(new_login.status_code, 200, new_login.text)
        self.assertFalse(new_login.json()["account"]["must_change_password"])
        self.assertEqual(self.client.get("/client").status_code, 200)
        self.assertEqual(self.client.get("/client/picks").status_code, 200)
        self.assertEqual(self.client.get("/api/client/picks").status_code, 200)
        self.assertEqual(self.client.get("/password-setup").headers["location"], "/client")

    def test_admin_invites_and_resets_client_only(self):
        self.admin_login()
        create = self.client.post("/api/admin/clients", json={
            "username": "newtester", "display_name": "New Tester", "plan_code": "weekly",
        })
        self.assertEqual(create.status_code, 200, create.text)
        payload = create.json()
        self.assertTrue(payload["temporary_password"])
        self.assertNotIn("password_hash", str(payload))
        account_id = payload["account"]["id"]
        old_temp = payload["temporary_password"]
        self.assertTrue(access.verify_password(
            old_temp,
            access.connect().execute("SELECT password_hash FROM accounts WHERE id=?", (account_id,)).fetchone()[0],
        ))
        old_expiry = access.get_account(account_id)["subscription"]["expires_at"]
        reset = self.client.post("/api/admin/clients/"+str(account_id)+"/reset-password")
        self.assertEqual(reset.status_code, 200, reset.text)
        new_temp = reset.json()["temporary_password"]
        self.assertNotEqual(new_temp, old_temp)
        self.assertEqual(access.get_account(account_id)["subscription"]["expires_at"], old_expiry)
        self.assertEqual(self.login("newtester", old_temp).status_code, 401)
        self.assertEqual(self.login("newtester", new_temp).status_code, 200)
        self.assertTrue(self.client.get("/api/auth/me").json()["account"]["must_change_password"])
        self.assertEqual(self.client.post("/api/admin/clients/"+str(account_id)+"/reset-password").status_code, 403)
        self.client.post("/api/auth/logout")
        self.assertEqual(self.login("admin", "ChangedAdminPassword2026!").status_code, 200)
        self.assertEqual(self.client.post("/api/admin/clients/999999/reset-password").status_code, 404)
        admin_id = access.authenticate("admin", "ChangedAdminPassword2026!")["id"]
        self.assertEqual(self.client.post("/api/admin/clients/"+str(admin_id)+"/reset-password").status_code, 404)

    def test_admin_reset_revokes_existing_client_sessions(self):
        self.admin_login()
        created = self.client.post("/api/admin/clients", json={
            "username": "sessiontest", "display_name": "Session Test", "plan_code": "weekly",
        }).json()
        account_id, temp = created["account"]["id"], created["temporary_password"]
        self.client.post("/api/auth/logout")
        self.login("sessiontest", temp)
        self.assertEqual(self.complete_setup(temp).status_code, 200)
        self.login("sessiontest", "PrivateClientPassword2026!")
        client_session = self.client.cookies.get(access.SESSION_COOKIE)
        self.assertTrue(client_session)
        self.client.post("/api/auth/logout")
        self.login("admin", "ChangedAdminPassword2026!")
        self.assertEqual(self.client.post("/api/admin/clients/"+str(account_id)+"/reset-password").status_code, 200)
        self.client.cookies.set(access.SESSION_COOKIE, client_session)
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)

    def test_invalid_invites_do_not_create_clients(self):
        self.admin_login()
        for username,plan in [("a", "weekly"), ("space name", "weekly"), ("newone", "invalid")]:
            response = self.client.post("/api/admin/clients", json={
                "username": username, "display_name": "Test", "plan_code": plan,
            })
            self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(self.client.get("/api/admin/clients").json()["clients"], [])


if __name__ == "__main__":
    unittest.main()

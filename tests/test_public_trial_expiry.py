"""Public trial and exact expiration checks — keep other clients isolated."""
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from backend import access, db


class PublicTrialExpiryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = access.DB, db.DB
        access.DB = db.DB = Path(self.tmp.name) / "predictor.db"
        self.env = patch.dict(os.environ, {"PREDICTOR_ADMIN_PASSWORD": "InitialAdminPassword2026!"})
        self.env.start()
        from backend import main
        self.http = TestClient(main.app, follow_redirects=False)
        access.ensure_bootstrap_admin()
        self.assertEqual(self.login("admin", "InitialAdminPassword2026!").status_code, 200)
        p = self.http.post("/api/auth/change-password",json={
            "current_password":"InitialAdminPassword2026!",
            "new_password":"ChangedAdminPassword2026!",
        })
        self.assertEqual(p.status_code, 200, p.text)
        self.assertEqual(self.login("admin", "ChangedAdminPassword2026!").status_code, 200)

    def tearDown(self):
        self.http.close()
        access.DB,db.DB = self.old
        self.env.stop()
        self.tmp.cleanup()

    def login(self, username, password):
        return self.http.post("/api/auth/login", json={"username":username,"password":password})

    def test_public_trial_password_and_exact_expiry(self):
        future = (datetime.now(timezone.utc)+timedelta(hours=7)).isoformat()
        payload = {
            "username":"PUBLIC TRIAL","display_name":"Public Trial",
            "chosen_password":"AdminChosenTrialPassword2026!",
            "expires_at":future,
        }
        created = self.http.post("/api/admin/clients",json=payload)
        self.assertEqual(created.status_code,200,created.text)
        body = created.json()
        self.assertIsNone(body["activation_token"])
        self.assertFalse(body["account"]["must_change_password"])
        self.assertEqual(body["account"]["subscription"]["plan_label"],"Custom expiry")
        self.assertTrue(body["account"]["subscription"]["is_active"])
        self.assertEqual(datetime.fromisoformat(body["account"]["subscription"]["expires_at"]),
                         datetime.fromisoformat(future))
        self.http.post("/api/auth/logout")
        logged = self.login("PUBLIC TRIAL","AdminChosenTrialPassword2026!")
        self.assertEqual(logged.status_code,200,logged.text)
        self.assertEqual(self.http.get("/client/overs").status_code,200)
        # A public user cannot replace the password and lock everybody else out.
        self.assertEqual(self.http.post("/api/auth/change-password",json={
            "current_password":"AdminChosenTrialPassword2026!",
            "new_password":"AnotherPassword2026!"
        }).status_code,403)

    def test_set_absolute_expiry_overwrites_not_adds(self):
        c = self.http.post("/api/admin/clients",json={
            "username":"normalcustomer","display_name":"Normal","plan_code":"weekly"
        }).json()
        ident = c["account"]["id"]
        first = (datetime.now(timezone.utc)+timedelta(days=2)).isoformat()
        second = (datetime.now(timezone.utc)+timedelta(hours=3)).isoformat()
        endpoint = f"/api/admin/clients/{ident}/subscription/expiry"
        self.assertEqual(self.http.post(endpoint,json={"expires_at":first}).status_code,200)
        self.assertEqual(self.http.post(endpoint,json={"expires_at":second}).status_code,200)
        actual = access.get_account(ident)["subscription"]["expires_at"]
        self.assertEqual(datetime.fromisoformat(actual),datetime.fromisoformat(second))
        self.assertTrue(access.get_account(ident)["subscription"]["is_active"])

    def test_expired_public_trial_is_subscription_gated(self):
        soon = (datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()
        created = self.http.post("/api/admin/clients",json={
            "username":"PUBLIC TRIAL","chosen_password":"AdminChosenTrialPassword2026!",
            "expires_at":soon
        })
        self.assertEqual(created.status_code,200,created.text)
        ident=created.json()["account"]["id"]
        past=(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()
        con=access.connect()
        con.execute("UPDATE subscriptions SET expires_at=? WHERE account_id=?",(past,ident))
        con.commit()
        con.close()
        self.http.post("/api/auth/logout")
        self.assertEqual(self.login("PUBLIC TRIAL","AdminChosenTrialPassword2026!").status_code,200)
        self.assertEqual(self.http.get("/client/overs").status_code,302)
        self.assertEqual(self.http.get("/client/overs").headers["location"],"/client")
        self.assertFalse(self.http.get("/api/auth/me").json()["account"]["subscription"]["is_active"])

    def test_invalid_expiry_and_ordinary_username_protected(self):
        bad=self.http.post("/api/admin/clients",json={
            "username":"PUBLIC TRIAL","chosen_password":"short","expires_at":"2026-01-01T00:00:00+03:00"
        })
        self.assertEqual(bad.status_code,400)
        self.assertEqual(self.http.post("/api/admin/clients",json={
            "username":"PUBLIC TRIAL","chosen_password":"ValidTrialPassword2026!",
            "expires_at":"2020-01-01T00:00:00+03:00"
        }).status_code,400)
        self.assertEqual(self.http.post("/api/admin/clients",json={
            "username":"somebody","chosen_password":"SecretPassword2026!"
        }).status_code,400)
        self.assertEqual(self.http.post("/api/admin/clients",json={
            "username":"PUBLIC TRIAL"
        }).status_code,400)
        self.assertEqual(self.http.get("/api/admin/clients").json()["clients"],[])

    def test_only_admin_sets_expiry(self):
        made=self.http.post("/api/admin/clients",json={
            "username":"somebody","display_name":"Somebody"
        }).json()
        endpoint=f"/api/admin/clients/{made['account']['id']}/subscription/expiry"
        self.http.post("/api/auth/logout")
        self.assertIn(self.http.post(endpoint,json={
            "expires_at":(datetime.now(timezone.utc)+timedelta(days=1)).isoformat()
        }).status_code,(401,403))
        self.assertEqual(self.login("somebody",made["temporary_password"]).status_code,200)
        self.assertEqual(self.http.post(endpoint,json={
            "expires_at":(datetime.now(timezone.utc)+timedelta(days=1)).isoformat()
        }).status_code,403)


if __name__=="__main__":
    unittest.main()

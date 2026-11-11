"""Regression tests for admin-only client deletion and personal-link cleanup."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend import access, db, picks


class ClientDeletionTests(unittest.TestCase):
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
        response = self.http.post("/api/auth/change-password", json={
            "current_password": "InitialAdminPassword2026!",
            "new_password": "ChangedAdminPassword2026!",
        })
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.login("admin", "ChangedAdminPassword2026!").status_code, 200)

    def tearDown(self):
        self.http.close()
        access.DB, db.DB = self.old
        self.env.stop()
        self.tmp.cleanup()

    def login(self, username, password):
        return self.http.post("/api/auth/login", json={"username": username, "password": password})

    def create(self, username):
        response = self.http.post("/api/admin/clients", json={
            "username": username, "display_name": username, "plan_code": "weekly",
        })
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_delete_client_removes_own_data_but_preserves_other_client_and_cache(self):
        first = self.create("delete_me")
        other = self.create("keep_me")
        first_id = first["account"]["id"]
        first_key = access.get_account(first_id)["user_key"]
        other_key = access.get_account(other["account"]["id"])["user_key"]
        con = db.connect()
        con.execute("INSERT INTO round_cache(round_id,payload_json,updated_epoch) VALUES('global','{}',1)")
        for key in (first_key, other_key):
            con.execute(
                "INSERT INTO user_prediction_batches(user_id,season,matchday,checked_at) "
                "VALUES(?,?,?,?)", (key, "100", "2", "2026-01-01T00:00:00+00:00")
            )
        con.commit()
        con.close()
        journal = picks.connect_journal()
        for key in (first_key, other_key):
            journal.execute(
                "INSERT INTO client_bet_journal(user_id,bet_date,league,fixture,category,"
                "selection,stake_ugx,decimal_odds,outcome,notes,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (key, "2026-01-01", "English", "A - B", "overs", "O2.5", 1000, 2.0,
                 "PENDING", "", "2026-01-01", "2026-01-01")
            )
        journal.commit()
        journal.close()

        response = self.http.delete(f"/api/admin/clients/{first_id}")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIsNone(access.get_account(first_id))
        self.assertIsNotNone(access.get_account(other["account"]["id"]))
        self.assertEqual(self.login("delete_me", first["temporary_password"]).status_code, 401)
        self.assertEqual(self.http.post("/api/auth/link-activate", json={
            "token": first["activation_token"], "new_password": "NewPasswordForTesting!", "age_confirmed": True,
        }).status_code, 400)
        con = db.connect()
        try:
            for table in ("user_prediction_batches", "client_bet_journal"):
                self.assertEqual(con.execute(f"SELECT count(*) FROM {table} WHERE user_id=?", (first_key,)).fetchone()[0], 0)
                self.assertEqual(con.execute(f"SELECT count(*) FROM {table} WHERE user_id=?", (other_key,)).fetchone()[0], 1)
            self.assertEqual(con.execute("SELECT count(*) FROM round_cache WHERE round_id='global'").fetchone()[0], 1)
        finally:
            con.close()

    def test_no_client_delete_for_non_admin_and_no_admin_deletion(self):
        test = self.create("normal_client")
        self.assertEqual(self.http.delete("/api/admin/clients/1").status_code, 404)
        self.http.post("/api/auth/logout")
        self.assertIn(self.http.delete(f"/api/admin/clients/{test['account']['id']}").status_code,(401,403))
        self.assertEqual(self.login("normal_client", test["temporary_password"]).status_code, 200)
        self.assertEqual(self.http.delete(f"/api/admin/clients/{test['account']['id']}").status_code, 403)
        self.assertIsNotNone(access.get_account(test["account"]["id"]))


if __name__ == "__main__":
    unittest.main()

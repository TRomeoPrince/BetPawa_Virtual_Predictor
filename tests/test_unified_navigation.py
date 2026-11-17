"""Integration checks: navigation pages remain usable while prediction APIs gate data."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend import access, db, main


class NavigationRoutingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.original = (access.DB, db.DB)
        access.DB = db.DB = Path(self.tmp.name) / "navigation.db"
        self.env = patch.dict(os.environ, {
            "PREDICTOR_ADMIN_PASSWORD": "NavigationTestAdmin2026!",
            "PREDICTOR_SIGNUP_ENABLED": "true",
        })
        self.env.start()
        self.client = TestClient(main.app, follow_redirects=False)
        access.ensure_bootstrap_admin()

    def tearDown(self):
        self.client.close()
        self.env.stop()
        access.DB, db.DB = self.original
        self.tmp.cleanup()

    def test_all_sidebar_destinations_are_real_for_signed_in_member(self):
        registered = self.client.post("/api/auth/signup", json={
            "username": "navvisitor",
            "display_name": "Nav Visitor",
            "email": "navvisitor@example.com",
            "password": "SufficientLengthPassword2026!",
            "age_confirmed": True,
        })
        self.assertEqual(registered.status_code, 200, registered.text)
        routes = [
            "/client", "/client/picks", "/client/overs", "/client/unders",
            "/client/btts", "/client/wins", "/purchase",
        ]
        for route in routes:
            with self.subTest(route=route):
                response = self.client.get(route)
                self.assertEqual(response.status_code, 200, response.text[:220])
        for category in ("overs", "unders", "btts", "wins"):
            with self.subTest(market=category):
                # Pages may be opened; prediction data is still prohibited until
                # the administrator enables an eligible public Free release.
                self.assertEqual(self.client.post("/api/predict/" + category).status_code, 403)

    def test_anonymous_users_still_cannot_open_member_pages(self):
        for path in ("/client", "/client/picks", "/client/overs",
                     "/client/unders", "/client/btts", "/client/wins"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 302)
                self.assertEqual(response.headers.get("location"), "/login")

    def test_theme_asset_does_not_expose_account_content(self):
        response = self.client.get("/bpv-stadium-dashboard.js")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("set-cookie", response.headers)
        self.assertIn("bpv-sidebar", response.text)
        self.assertNotIn("76.4%", response.text)


if __name__ == "__main__":
    unittest.main()

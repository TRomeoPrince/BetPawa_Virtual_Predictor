import tempfile
import unittest
from pathlib import Path

from backend import access


class AccessTests(unittest.TestCase):
    def setUp(self):
        self.old_db = access.DB
        self.tmp = tempfile.TemporaryDirectory()
        access.DB = Path(self.tmp.name) / "access.db"

    def tearDown(self):
        access.DB = self.old_db
        self.tmp.cleanup()

    def test_client_subscription_lifecycle(self):
        account, password = access.create_client("romeo1", "Romeo", "weekly")
        self.assertTrue(access.authenticate("romeo1", password))
        self.assertTrue(account["subscription"]["is_active"])
        access.revoke_subscription(account["id"])
        self.assertFalse(access.get_account(account["id"])["subscription"]["is_active"])

    def test_session_and_password_change(self):
        account, password = access.create_client("client2", "Client Two")
        token = access.create_session(account["id"])
        self.assertEqual(access.account_from_session(token)["username"], "client2")
        access.change_password(account["id"], password, "NewPassword123!")
        self.assertIsNone(access.authenticate("client2", password))
        self.assertIsNotNone(access.authenticate("client2", "NewPassword123!"))

    def test_plan_request_and_approval(self):
        admin, _ = access.create_client("fakeadmin", "Fake Admin")
        con = access.connect()
        con.execute("UPDATE accounts SET role='admin' WHERE id=?", (admin["id"],))
        con.commit(); con.close()
        client, _ = access.create_client("client3", "Client Three")
        req = access.request_subscription(client["id"], "monthly")
        access.review_subscription_request(req["id"], True, admin["id"])
        self.assertTrue(access.get_account(client["id"])["subscription"]["is_active"])

    def test_public_plans_include_longer_options(self):
        codes = {p["code"] for p in access.public_plans()}
        self.assertTrue({"daily","weekly","monthly","quarterly","half_year","annual"} <= codes)


if __name__ == "__main__":
    unittest.main()

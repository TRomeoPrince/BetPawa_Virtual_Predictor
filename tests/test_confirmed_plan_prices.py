"""User-confirmed five plan price schedule and indefinite lifetime access."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from backend import access, db, purchase_requests


class PlanScheduleTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.old_access, self.old_db=access.DB, db.DB
        access.DB=db.DB=Path(self.tmp.name)/"test.db"
        self.env=patch.dict(os.environ,{},clear=False)
        self.env.start()

    def tearDown(self):
        access.DB,db.DB=self.old_access,self.old_db
        self.env.stop()
        self.tmp.cleanup()

    def test_exact_public_prices_and_approved_plan_codes(self):
        self.assertEqual(purchase_requests.prices(),{
            "daily":5000,"weekly":20000,"monthly":60000,
            "annual":500000,"lifetime":1000000,
        })
        self.assertEqual(set(purchase_requests.PRICE_ENV),{"daily","weekly","monthly","annual","lifetime"})

    def test_lifetime_has_no_expiration_but_admin_can_revoke(self):
        a,_=access.create_client("lifetimeuser","Lifetime Customer",plan_code="lifetime")
        self.assertTrue(a["subscription"]["is_active"])
        self.assertEqual(a["subscription"]["plan_code"],"lifetime")
        self.assertIsNone(a["subscription"]["expires_at"])
        self.assertIsNone(a["subscription"]["remaining_seconds"])
        access.revoke_subscription(a["id"])
        self.assertFalse(access.get_account(a["id"])["subscription"]["is_active"])


if __name__=="__main__":
    unittest.main()

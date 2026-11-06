import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend import access, db, payments


class VerifiedPaymentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_access_db, self.old_db = access.DB, db.DB
        access.DB = db.DB = Path(self.temp.name) / "predictor.db"
        self.config = patch.dict(os.environ, {
            "PREDICTOR_ADMIN_PASSWORD": "TestAdminPassword123!",
            "PREDICTOR_PRICE_MONTHLY_UGX": "20000",
            "PREDICTOR_PUBLIC_BASE_URL": "https://predictor.example",
            "FLW_SECRET_KEY": "test-secret-key",
            "FLW_WEBHOOK_HASH": "test-webhook-hash",
        })
        self.config.start()
        from backend import main
        self.main = main
        access.ensure_bootstrap_admin()
        self.client = TestClient(main.app, follow_redirects=False)
        self.account, self.password = access.create_client("paytester", "Payment Tester")
        response = self.client.post("/api/auth/login", json={"username": "paytester", "password": self.password})
        self.assertEqual(response.status_code, 200, response.text)

    def tearDown(self):
        self.client.close()
        self.config.stop()
        access.DB, db.DB = self.old_access_db, self.old_db
        self.temp.cleanup()

    def checkout(self, method="mtn_momo"):
        with patch.object(payments, "_flutterwave_request", return_value={
            "status": "success",
            "data": {"link": "https://checkout.flutterwave.com/v3/hosted/pay/demo"},
        }) as request:
            response = self.client.post("/api/client/payments/checkout", json={
                "plan_code": "monthly", "method": method,
                "email": "customer@example.com", "age_confirmed": True,
            })
        self.assertEqual(response.status_code, 200, response.text)
        payload = request.call_args.args[1]
        self.assertEqual(payload["amount"], 20000)
        self.assertEqual(payload["currency"], "UGX")
        self.assertEqual(payload["payment_options"], "mobilemoneyuganda" if method != "flutterwave" else "card,mobilemoneyuganda")
        return response.json()["reference"]

    @staticmethod
    def verified(ref, amount=20000, currency="UGX", status="successful", tx_id=7001):
        return {"status": "success", "data": {
            "tx_ref": ref, "amount": amount, "currency": currency,
            "status": status, "id": tx_id,
        }}

    def test_checkout_is_not_activation_and_prices_are_configurable(self):
        plans = self.client.get("/api/plans").json()["plans"]
        self.assertEqual(next(p for p in plans if p["code"] == "monthly")["price_ugx"], 20000)
        self.assertIsNone(next(p for p in plans if p["code"] == "annual")["price_ugx"])
        self.assertTrue(next(m for m in self.client.get("/api/payment-methods").json()["methods"] if m["code"] == "mtn_momo")["available"])
        self.assertFalse(next(m for m in self.client.get("/api/payment-methods").json()["methods"] if m["code"] == "binance_pay")["available"])
        ref = self.checkout()
        self.assertFalse(access.get_account(self.account["id"])["subscription"]["is_active"])
        self.assertEqual(payments.get_order(ref)["status"], "checkout_ready")
        history = self.client.get("/api/client/payments").json()["orders"]
        self.assertEqual(len(history), 1)
        self.assertNotIn("checkout_url", history[0])

    def test_verified_payment_activates_once_even_with_repeated_webhooks(self):
        ref = self.checkout("airtel_money")
        event = {"event": "charge.completed", "data": {"tx_ref": ref, "status": "successful"}}
        bad = self.client.post("/api/payments/flutterwave/webhook", json=event)
        self.assertEqual(bad.status_code, 401)
        self.assertFalse(access.get_account(self.account["id"])["subscription"]["is_active"])
        with patch.object(payments, "_flutterwave_request", return_value=self.verified(ref)) as provider:
            first = self.client.post("/api/payments/flutterwave/webhook", json=event, headers={"verif-hash": "test-webhook-hash"})
            self.assertEqual(first.status_code, 200, first.text)
            expiry = access.get_account(self.account["id"])["subscription"]["expires_at"]
            again = self.client.post("/api/payments/flutterwave/webhook", json=event, headers={"verif-hash": "test-webhook-hash"})
            self.assertEqual(again.status_code, 200, again.text)
            self.assertEqual(access.get_account(self.account["id"])["subscription"]["expires_at"], expiry)
            self.assertEqual(provider.call_count, 1)
        self.assertEqual(payments.get_order(ref)["status"], "paid")
        con = payments.connect()
        try:
            count = con.execute("SELECT COUNT(*) FROM access_audit WHERE action='PAYMENT_ACTIVATION'").fetchone()[0]
            self.assertEqual(count, 1)
        finally:
            con.close()

    def test_underpayment_currency_mismatch_and_unverified_redirect_do_not_activate(self):
        ref = self.checkout()
        for response in [
            self.verified(ref, amount=1000),
            self.verified(ref, currency="USD"),
            self.verified(ref, status="pending"),
            self.verified("different-reference"),
        ]:
            with patch.object(payments, "_flutterwave_request", return_value=response):
                check = self.client.post("/api/client/payments/" + ref + "/verify")
            self.assertEqual(check.status_code, 200, check.text)
            self.assertFalse(check.json()["paid"])
        with patch.object(payments, "_flutterwave_request", return_value=self.verified(ref, status="failed")):
            returned = self.client.get("/api/payments/flutterwave/return?tx_ref=" + ref + "&status=successful")
        self.assertEqual(returned.status_code, 303)
        self.assertFalse(access.get_account(self.account["id"])["subscription"]["is_active"])

    def test_checkout_requires_age_valid_method_and_config(self):
        for payload in [
            {"plan_code": "monthly", "method": "crypto", "email": "a@b.com", "age_confirmed": True},
            {"plan_code": "monthly", "method": "mtn_momo", "email": "a@b.com", "age_confirmed": False},
            {"plan_code": "annual", "method": "mtn_momo", "email": "a@b.com", "age_confirmed": True},
        ]:
            response = self.client.post("/api/client/payments/checkout", json=payload)
            self.assertEqual(response.status_code, 400, response.text)
        with patch.dict(os.environ, {"FLW_SECRET_KEY": ""}):
            response = self.client.post("/api/client/payments/checkout", json={
                "plan_code": "monthly", "method": "mtn_momo",
                "email": "a@b.com", "age_confirmed": True,
            })
            self.assertEqual(response.status_code, 400, response.text)

    def test_payment_status_scoped_to_owner_and_transaction_id_not_reused(self):
        ref = self.checkout()
        second, second_password = access.create_client("secondpay", "Second Pay")
        self.client.post("/api/auth/logout")
        self.client.post("/api/auth/login", json={"username": "secondpay", "password": second_password})
        self.assertEqual(self.client.get("/api/client/payments").json()["orders"], [])
        self.assertEqual(self.client.post("/api/client/payments/" + ref + "/verify").status_code, 404)
        ref2 = self.checkout()
        with patch.object(payments, "_flutterwave_request", return_value=self.verified(ref2, tx_id=7001)):
            self.assertTrue(self.client.post("/api/client/payments/" + ref2 + "/verify").json()["paid"])
        self.client.post("/api/auth/logout")
        self.client.post("/api/auth/login", json={"username": "paytester", "password": self.password})
        with patch.object(payments, "_flutterwave_request", return_value=self.verified(ref, tx_id=7001)):
            result = self.client.post("/api/client/payments/" + ref + "/verify")
        self.assertFalse(result.json()["paid"])
        self.assertFalse(access.get_account(self.account["id"])["subscription"]["is_active"])


if __name__ == "__main__":
    unittest.main()

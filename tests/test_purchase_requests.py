import base64
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend import access, db, purchase_requests


class PurchaseRequestTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.previous=(access.DB,db.DB)
        access.DB=db.DB=Path(self.tmp.name)/"predictor.db"
        self.env=patch.dict(os.environ,{
            "PREDICTOR_ADMIN_PASSWORD":"OriginalAdminPassword2026!",
            "PREDICTOR_PUBLIC_BASE_URL":"https://example.ngrok-free.dev",
            "PREDICTOR_SMTP_HOST":"",
            "PREDICTOR_SMTP_FROM":"",
            "PREDICTOR_PRICE_DAILY_UGX":"5000",
        })
        self.env.start()
        from backend import main
        self.http=TestClient(main.app,follow_redirects=False)
        access.ensure_bootstrap_admin()
        self.assertEqual(self.http.post("/api/auth/login",json={
            "username":"admin","password":"OriginalAdminPassword2026!"
        }).status_code,200)
        response=self.http.post("/api/auth/change-password",json={
            "current_password":"OriginalAdminPassword2026!",
            "new_password":"ChangedAdminPassword2026!",
        })
        self.assertEqual(response.status_code,200,response.text)
        self.http.post("/api/auth/login",json={
            "username":"admin","password":"ChangedAdminPassword2026!"
        })

    def tearDown(self):
        self.http.close()
        access.DB,db.DB=self.previous
        self.env.stop()
        self.tmp.cleanup()

    def payload(self,username="buyer1",txref="MOMO123456"):
        image=b"\x89PNG\r\n\x1a\n"+b"receipt-pixel-data"*8
        return {
            "email":"buyer@example.com",
            "username":username,"display_name":"Buyer One",
            "plan_code":"daily","payment_method":"mtn",
            "transaction_ref":txref,
            "proof_base64":base64.b64encode(image).decode(),
            "age_confirmed":True,
        }

    def test_public_catalog_receiving_details(self):
        data=self.http.get("/api/purchase/catalog").json()
        m={x["code"]:x for x in data["methods"]}
        self.assertEqual(m["mtn"]["account"],"0781920398")
        self.assertEqual(m["usdt_trc20"]["address"],"TCcR54xQu4dE3aKQao8PrUn3Nb7d2DVucG")
        self.assertEqual(m["btc_bitcoin"]["address"],"14QTD6Eao9TMeuvStxjgrhyr9Qr4PSQ3rR")
        self.assertEqual(m["usdc_solana"]["address"],"DDq3v8aj28dUw4mMcGUob94YgNQx9qn8XrNUnmQGpgPs")
        self.assertEqual({x["code"]:x["price_ugx"] for x in data["plans"]}["daily"],5000)
        actual={x["code"]:x["price_ugx"] for x in data["plans"]}
        self.assertEqual(actual,{"daily":5000,"weekly":20000,"monthly":60000,"annual":500000,"lifetime":1000000})
        self.assertNotIn("quarterly",actual)
        self.assertNotIn("half_year",actual)
        self.assertEqual(self.http.get("/purchase").status_code,200)

    def test_public_receipt_cannot_approve_and_admin_review_can(self):
        self.http.post("/api/auth/logout")
        response=self.http.post("/api/purchase/requests",json=self.payload())
        self.assertEqual(response.status_code,200,response.text)
        request_ref=response.json()["reference"]
        self.assertTrue(request_ref.startswith("BP-"))
        self.assertEqual(access.list_clients(),[])
        self.assertIn(self.http.get("/api/admin/payment-requests").status_code,(401,403))
        self.assertIn(self.http.get("/api/admin/payment-requests/1/proof").status_code,(401,403))
        self.assertIn(self.http.post("/api/admin/payment-requests/1/review",json={
            "approve":True,"verified":True
        }).status_code,(401,403))
        self.http.post("/api/auth/login",json={
            "username":"admin","password":"ChangedAdminPassword2026!"
        })
        pending=self.http.get("/api/admin/payment-requests").json()["requests"]
        self.assertEqual(len(pending),1)
        self.assertNotIn("proof_blob",pending[0])
        self.assertEqual(pending[0]["reference"],request_ref)
        proof=self.http.get("/api/admin/payment-requests/1/proof")
        self.assertEqual(proof.status_code,200)
        self.assertEqual(proof.headers["content-type"],"application/octet-stream")
        self.assertIn("attachment",proof.headers["content-disposition"])
        no_verification=self.http.post("/api/admin/payment-requests/1/review",json={
            "approve":True,"verified":False,
        })
        self.assertEqual(no_verification.status_code,400)
        self.assertEqual(access.list_clients(),[])
        approved=self.http.post("/api/admin/payment-requests/1/review",json={
            "approve":True,"verified":True,
        })
        self.assertEqual(approved.status_code,200,approved.text)
        self.assertFalse(approved.json()["email_sent"])
        self.assertIn("/activate#",approved.json()["activation_link"])
        self.assertEqual(len(access.list_clients()),1)
        self.assertTrue(access.list_clients()[0]["subscription"]["is_active"])
        self.assertEqual(self.http.post("/api/admin/payment-requests/1/review",json={
            "approve":True,"verified":True,
        }).status_code,400)
        self.assertEqual(len(access.list_clients()),1)
        resend=self.http.post("/api/admin/payment-requests/1/resend")
        self.assertEqual(resend.status_code,200,resend.text)
        self.assertFalse(resend.json()["email_sent"])
        self.assertIn("/activate#",resend.json()["activation_link"])

    def test_duplicate_transaction_and_invalid_uploads(self):
        self.http.post("/api/auth/logout")
        payload=self.payload()
        self.assertEqual(self.http.post("/api/purchase/requests",json=payload).status_code,200)
        self.assertEqual(self.http.post("/api/purchase/requests",json=self.payload("buyer2")).status_code,400)
        invalid=self.payload("buyer3","MOMO98765")
        invalid["proof_base64"]=base64.b64encode(b"<script>alert(1)</script>"*5).decode()
        self.assertEqual(self.http.post("/api/purchase/requests",json=invalid).status_code,400)
        invalid=self.payload("buyer4","MOMO99999")
        invalid["plan_code"]="quarterly"
        self.assertEqual(self.http.post("/api/purchase/requests",json=invalid).status_code,400)
        invalid=self.payload("buyer5","MOMO88888")
        invalid["age_confirmed"]=False
        self.assertEqual(self.http.post("/api/purchase/requests",json=invalid).status_code,400)

    def test_rejected_request_never_creates_account(self):
        self.http.post("/api/auth/logout")
        self.http.post("/api/purchase/requests",json=self.payload())
        self.http.post("/api/auth/login",json={
            "username":"admin","password":"ChangedAdminPassword2026!"
        })
        result=self.http.post("/api/admin/payment-requests/1/review",json={
            "approve":False,"reason":"Payment not found",
        })
        self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(access.list_clients(),[])
        self.assertEqual(self.http.get("/api/admin/payment-requests").json()["requests"][0]["status"],"rejected")


if __name__=="__main__":
    unittest.main()

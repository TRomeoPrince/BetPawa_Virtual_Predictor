"""Referral commission wallet regression tests: every verified VIP purchase."""
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from backend import access, db, growth, purchase_requests, referral_wallet


class ReferralWalletTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.original=access.DB,db.DB
        access.DB=db.DB=Path(self.tmp.name)/"wallet.db"
        self.env=patch.dict(os.environ,{
            "PREDICTOR_ADMIN_PASSWORD":"InitialWalletAdminPassword2026!",
            "PREDICTOR_SIGNUP_ENABLED":"true",
            "PREDICTOR_PURCHASE_ENABLED":"true",
            "PREDICTOR_REFERRAL_WITHDRAWALS_ENABLED":"true",
        })
        self.env.start()
        from backend import main
        self.app=main.app
        self.owner=TestClient(self.app,follow_redirects=False)
        self.buyer=TestClient(self.app,follow_redirects=False)
        self.admin=TestClient(self.app,follow_redirects=False)
        owner=self.signup(self.owner,"owner","owner@example.org")
        self.assertEqual(owner.status_code,200,owner.text)
        self.owner_id=owner.json()["account"]["id"]
        referral=self.owner.get("/api/referrals/me").json()["code"]
        buyer=self.signup(self.buyer,"referred","referred@example.org",referral)
        self.assertEqual(buyer.status_code,200,buyer.text)
        self.buyer_id=buyer.json()["account"]["id"]
        access.ensure_bootstrap_admin()

    def tearDown(self):
        for client in (self.owner,self.buyer,self.admin):
            client.close()
        access.DB,db.DB=self.original
        self.env.stop()
        self.tmp.cleanup()

    @staticmethod
    def signup(http,user,email,ref=""):
        return http.post("/api/auth/signup",json={
            "username":user,"display_name":user.title(),"email":email,
            "password":"SomeLongPassword2026!","age_confirmed":True,"referral_code":ref,
        })

    def login_admin(self):
        entered=self.admin.post("/api/auth/login",json={
            "username":"admin","password":"InitialWalletAdminPassword2026!",
        })
        self.assertEqual(entered.status_code,200,entered.text)
        changed=self.admin.post("/api/auth/change-password",json={
            "current_password":"InitialWalletAdminPassword2026!",
            "new_password":"UpdatedWalletAdminPassword2026!",
        })
        self.assertEqual(changed.status_code,200,changed.text)
        self.assertEqual(self.admin.post("/api/auth/login",json={
            "username":"admin","password":"UpdatedWalletAdminPassword2026!",
        }).status_code,200)

    def buy(self,reference,promo=""):
        return self.buyer.post("/api/purchase/requests",json={
            "email":"referred@example.org","username":"referred","display_name":"Referred",
            "plan_code":"weekly","payment_method":"mtn",
            "transaction_ref":reference,"age_confirmed":True,"promo_code":promo,
        })

    def approve(self,purchase_id,verified=True):
        return self.admin.post(f"/api/admin/payment-requests/{purchase_id}/review",json={
            "approve":True,"verified":verified,
        })

    def test_discount_and_every_verified_renewal(self):
        growth.create_promotion("weekly",5000,"WEEKLY5K")
        self.assertEqual(self.buy("TX-WALLET-0001","WEEKLY5K").status_code,200)
        self.assertEqual(self.owner.get("/api/referrals/wallet").json()["balance_ugx"],0)
        self.assertEqual(self.buyer.get("/api/admin/referral-wallets").status_code,403)
        self.login_admin()
        self.assertEqual(self.approve(1,False).status_code,400)
        self.assertEqual(self.owner.get("/api/referrals/wallet").json()["balance_ugx"],0)
        approved=self.approve(1)
        self.assertEqual(approved.status_code,200,approved.text)
        state=self.owner.get("/api/referrals/wallet").json()
        self.assertEqual(state["balance_ugx"],1000)
        self.assertEqual(state["entries"][0]["commission_rate_bps"],2000)
        self.assertEqual(state["entries"][0]["purchase_amount_ugx"],5000)
        self.assertEqual(self.approve(1).status_code,400)
        self.assertEqual(self.buy("TX-WALLET-0002").status_code,200)
        self.assertEqual(self.approve(2).status_code,200)
        self.assertEqual(self.owner.get("/api/referrals/wallet").json()["balance_ugx"],5000)
        self.assertEqual(self.buyer.get("/api/referrals/wallet").json()["balance_ugx"],0)

    def test_exact_thirty_day_boundary_and_duplicate_credit(self):
        first=datetime(2026,6,1,12,0,tzinfo=timezone.utc)
        def record(ref,when,price,status="approved"):
            con=purchase_requests.connect()
            try:
                con.execute("""
                    INSERT INTO purchase_requests(
                      reference,email,requested_username,display_name,plan_code,expected_ugx,
                      payment_method,transaction_ref,proof_mime,proof_blob,status,
                      submitted_at,reviewed_at,buyer_account_id,client_account_id
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,(ref,"referred@example.org","referred","Referred","weekly",price,
                     "mtn",ref,"",b"",status,when.isoformat(),when.isoformat(),
                     self.buyer_id,self.buyer_id))
                pid=con.execute("SELECT last_insert_rowid()").fetchone()[0]
                con.commit()
            finally:con.close()
            con=referral_wallet.connect()
            try:
                con.execute("BEGIN IMMEDIATE")
                if status=="pending":
                    with self.assertRaises(ValueError):
                        referral_wallet.record_verified_purchase(con,pid,self.buyer_id)
                    con.rollback()
                else:
                    referral_wallet.record_verified_purchase(con,pid,self.buyer_id)
                    referral_wallet.record_verified_purchase(con,pid,self.buyer_id)
                    con.commit()
            finally:con.close()
        record("TX-1",first,5000)
        record("TX-2",first+timedelta(days=29),10000)
        record("TX-3",first+timedelta(days=30),10000)
        record("TX-4",first+timedelta(days=31),10000,"pending")
        entries=referral_wallet.wallet(self.owner_id)["entries"]
        self.assertEqual(len(entries),3)
        self.assertEqual(sorted(x["commission_rate_bps"] for x in entries),[1500,2000,2000])
        self.assertEqual(sum(x["amount_ugx"] for x in entries),4500)

    def test_manual_withdrawal_and_refund_adjustment(self):
        self.assertEqual(self.buy("TX-REFUND-0001").status_code,200)
        self.login_admin()
        self.assertEqual(self.approve(1).status_code,200)
        request=self.owner.post("/api/referrals/withdrawals",json={
            "amount_ugx":4000,"destination_method":"mtn","destination_details":"0781920398",
        })
        self.assertEqual(request.status_code,200,request.text)
        rid=request.json()["id"]
        reserved=self.owner.get("/api/referrals/wallet").json()
        self.assertEqual((reserved["balance_ugx"],reserved["reserved_ugx"],reserved["available_ugx"]), (4000,4000,0))
        self.assertEqual(self.owner.post("/api/referrals/withdrawals",json={
            "amount_ugx":1,"destination_method":"mtn","destination_details":"0781920398",
        }).status_code,400)
        self.assertEqual(self.admin.post(f"/api/admin/referral-withdrawals/{rid}/review",json={
            "paid":True,"payout_reference":"TRANSFER-001","verified":False,
        }).status_code,400)
        paid=self.admin.post(f"/api/admin/referral-withdrawals/{rid}/review",json={
            "paid":True,"payout_reference":"TRANSFER-001","verified":True,
        })
        self.assertEqual(paid.status_code,200,paid.text)
        self.assertEqual(self.admin.post(f"/api/admin/referral-withdrawals/{rid}/review",json={
            "paid":True,"payout_reference":"TRANSFER-001","verified":True,
        }).status_code,400)
        self.assertEqual(self.owner.get("/api/referrals/wallet").json()["withdrawn_ugx"],4000)
        denied=self.admin.post("/api/admin/referral-commissions/1/reverse",json={
            "confirmed_refund":False,"reason":"Verified payment refunded",
        })
        self.assertEqual(denied.status_code,400)
        reversed=self.admin.post("/api/admin/referral-commissions/1/reverse",json={
            "confirmed_refund":True,"reason":"Verified payment refunded",
        })
        self.assertEqual(reversed.status_code,200,reversed.text)
        self.assertEqual(self.admin.post("/api/admin/referral-commissions/1/reverse",json={
            "confirmed_refund":True,"reason":"Verified payment refunded",
        }).status_code,400)
        result=self.owner.get("/api/referrals/wallet").json()
        self.assertEqual(result["balance_ugx"],-4000)
        self.assertEqual(result["available_ugx"],0)

    def test_payout_disabled_and_origin_policy(self):
        self.assertEqual(self.buy("TX-ORIGIN-0001").status_code,200)
        self.login_admin()
        self.assertEqual(self.approve(1).status_code,200)
        with patch.dict(os.environ,{"PREDICTOR_REFERRAL_WITHDRAWALS_ENABLED":"false"}):
            self.assertFalse(self.owner.get("/api/referrals/wallet").json()["withdrawals_enabled"])
            self.assertEqual(self.owner.post("/api/referrals/withdrawals",json={
                "amount_ugx":4000,"destination_method":"mtn","destination_details":"0781920398",
            }).status_code,400)
        self.assertEqual(self.owner.post("/api/referrals/withdrawals",headers={"Origin":"https://evil.example"},json={
            "amount_ugx":4000,"destination_method":"mtn","destination_details":"0781920398",
        }).status_code,403)
        ok=self.owner.post("/api/referrals/withdrawals",json={
            "amount_ugx":1000,"destination_method":"mtn","destination_details":"0781920398",
        })
        self.assertEqual(ok.status_code,200,ok.text)
        rejected=self.admin.post(f"/api/admin/referral-withdrawals/{ok.json()['id']}/review",json={
            "paid":False,"reason":"Incorrect destination details",
        })
        self.assertEqual(rejected.status_code,200,rejected.text)
        self.assertEqual(self.owner.get("/api/referrals/wallet").json()["available_ugx"],4000)


if __name__=="__main__":
    unittest.main()

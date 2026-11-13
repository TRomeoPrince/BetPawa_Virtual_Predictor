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
            "plan_code":"weekly","payment_method":"airtel",
            "transaction_ref":reference,"age_confirmed":True,"promo_code":promo,
        })

    def approve(self,purchase_id,verified=True):
        return self.admin.post(f"/api/admin/payment-requests/{purchase_id}/review",json={
            "approve":True,"verified":verified,
        })


    def test_referral_funnel_counts_link_opens_signups_and_verified_paid_only(self):
        # Referral link opens are counts, not identifiable unique individuals.
        link=self.owner.get("/api/referrals/me").json()
        self.assertEqual(self.owner.get("/r/"+link["code"]).status_code,302)
        self.assertEqual(self.owner.get("/r/"+link["code"]).status_code,302)
        initial=self.owner.get("/api/referrals/people").json()
        self.assertEqual(self.owner.get("/api/referrals/me").json()["visits"],2)
        self.assertEqual(initial["signups"],1)
        self.assertEqual(initial["paid_referrals"],0)
        self.assertEqual(initial["people"][0]["username"],"referred")
        self.assertEqual(initial["people"][0]["status"],"registered")
        self.assertEqual(initial["people"][0]["earned_ugx"],0)
        # No one, including the referred member, can view somebody else's funnel.
        self.assertEqual(self.buyer.get("/api/referrals/people").json()["people"],[])
        self.assertEqual(self.owner.get("/api/referrals/people?limit=1&offset=1").json()["people"],[])
        self.assertEqual(self.buy("TX-FUNNEL-0001").status_code,200)
        self.assertEqual(self.owner.get("/api/referrals/people").json()["paid_referrals"],0)
        self.login_admin()
        self.assertEqual(self.approve(1).status_code,200)
        credited=self.owner.get("/api/referrals/people").json()
        self.assertEqual(credited["paid_referrals"],1)
        self.assertEqual(credited["people"][0]["status"],"paid")
        self.assertEqual(credited["people"][0]["earned_ugx"],4000)
        self.assertEqual(credited["people"][0]["earned_pc"],400000)
        self.assertIsNotNone(credited["people"][0]["last_paid_at"])
        self.assertNotIn("email",credited["people"][0])
        self.assertNotIn("password",str(credited))
        self.assertEqual(self.admin.get("/api/referrals/people").status_code,403)
        self.assertEqual(self.admin.post("/api/admin/referral-commissions/1/reverse",json={
            "confirmed_refund":True,"reason":"Verified payment refunded",
        }).status_code,200)
        reversed=self.owner.get("/api/referrals/people").json()
        self.assertEqual(reversed["paid_referrals"],0)
        self.assertEqual(reversed["people"][0]["status"],"uncredited")
        self.assertEqual(reversed["people"][0]["earned_ugx"],0)

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
        con=referral_wallet.connect()
        try:
            con.execute("UPDATE referral_profiles SET joined_at=? WHERE account_id=?",
                        ((first-timedelta(days=1)).isoformat(),self.buyer_id))
            con.commit()
        finally:con.close()
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
            "amount_ugx":4000,"destination_method":"mtn","destination_details":"0700000000",
        })
        self.assertEqual(request.status_code,200,request.text)
        rid=request.json()["id"]
        reserved=self.owner.get("/api/referrals/wallet").json()
        self.assertEqual((reserved["balance_ugx"],reserved["reserved_ugx"],reserved["available_ugx"]), (4000,4000,0))
        self.assertEqual(self.owner.post("/api/referrals/withdrawals",json={
            "amount_ugx":1,"destination_method":"mtn","destination_details":"0700000000",
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
                "amount_ugx":4000,"destination_method":"mtn","destination_details":"0700000000",
            }).status_code,400)
        self.assertEqual(self.owner.post("/api/referrals/withdrawals",headers={"Origin":"https://evil.example"},json={
            "amount_ugx":4000,"destination_method":"mtn","destination_details":"0700000000",
        }).status_code,403)
        ok=self.owner.post("/api/referrals/withdrawals",json={
            "amount_ugx":1000,"destination_method":"mtn","destination_details":"0700000000",
        })
        self.assertEqual(ok.status_code,200,ok.text)
        rejected=self.admin.post(f"/api/admin/referral-withdrawals/{ok.json()['id']}/review",json={
            "paid":False,"reason":"Incorrect destination details",
        })
        self.assertEqual(rejected.status_code,200,rejected.text)
        self.assertEqual(self.owner.get("/api/referrals/wallet").json()["available_ugx"],4000)


    def test_wallet_vip_uses_promotional_price_once_and_activates_instantly(self):
        growth.create_promotion("weekly",5000,"VIP5K")
        self.assertEqual(self.buy("WALLET-SOURCE-001","VIP5K").status_code,200)
        self.login_admin()
        self.assertEqual(self.approve(1).status_code,200)
        self.assertEqual(self.buy("WALLET-SOURCE-002").status_code,200)
        self.assertEqual(self.approve(2).status_code,200)
        previous=self.owner.get("/api/referrals/wallet").json()
        self.assertEqual(previous["balance_ugx"],5000)
        key="12345678-1234-1234-1234-123456789abc"
        payload={"plan_code":"weekly","promo_code":"VIP5K",
                 "idempotency_key":key,"expected_price_ugx":5000}
        response=self.owner.post("/api/referrals/wallet/purchase-vip",json=payload)
        self.assertEqual(response.status_code,200,response.text)
        self.assertFalse(response.json()["already_processed"])
        self.assertTrue(self.owner.get("/api/auth/me").json()["account"]["subscription"]["is_active"])
        spent=self.owner.get("/api/referrals/wallet").json()
        self.assertEqual(spent["spent_on_vip_ugx"],5000)
        self.assertEqual(spent["balance_ugx"],0)
        self.assertEqual(spent["available_ugx"],0)
        self.assertEqual(spent["earned_ugx"],5000)
        self.assertTrue(any(x["entry_type"]=="vip_wallet_purchase" for x in spent["entries"]))
        duplicate=self.owner.post("/api/referrals/wallet/purchase-vip",json=payload)
        self.assertEqual(duplicate.status_code,200,duplicate.text)
        self.assertTrue(duplicate.json()["already_processed"])
        self.assertEqual(duplicate.json()["id"],response.json()["id"])
        self.assertEqual(duplicate.json()["expires_at"],response.json()["expires_at"])
        self.assertEqual(self.owner.get("/api/referrals/wallet").json()["spent_on_vip_ugx"],5000)
        self.assertEqual(self.buyer.post("/api/referrals/wallet/purchase-vip",json=payload).status_code,400)
        self.assertEqual(self.owner.post("/api/referrals/wallet/purchase-vip",json={
            "plan_code":"weekly","promo_code":"VIP5K",
            "idempotency_key":"aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "expected_price_ugx":5000,
        }).status_code,400)
        con=purchase_requests.connect()
        try:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM purchase_requests").fetchone()[0],2)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM referral_wallet_ledger WHERE entry_type='commission'").fetchone()[0],2)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM referral_wallet_spends").fetchone()[0],1)
        finally:
            con.close()

    def test_withdrawal_reservations_and_insufficient_wallet_block_vip(self):
        self.assertEqual(referral_wallet.minimum_withdrawal(),1000)
        self.assertEqual(self.buy("SOURCE-RESERVED-1").status_code,200)
        self.login_admin()
        self.assertEqual(self.approve(1).status_code,200)
        self.assertEqual(self.owner.get("/api/referrals/wallet").json()["balance_ugx"],4000)
        unaffordable={
            "plan_code":"daily","promo_code":"",
            "idempotency_key":"eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee",
            "expected_price_ugx":5000,
        }
        self.assertEqual(self.owner.post("/api/referrals/wallet/purchase-vip",json=unaffordable).status_code,400)
        self.assertEqual(self.owner.post("/api/referrals/withdrawals",json={
            "amount_ugx":999,"destination_method":"mtn","destination_details":"0700000000",
        }).status_code,400)
        withdrawal=self.owner.post("/api/referrals/withdrawals",json={
            "amount_ugx":1000,"destination_method":"mtn","destination_details":"0700000000",
        })
        self.assertEqual(withdrawal.status_code,200,withdrawal.text)
        self.assertEqual(self.owner.get("/api/referrals/wallet").json()["available_ugx"],3000)
        growth.create_promotion("daily",3500,"DAY3500")
        restricted={
            "plan_code":"daily","promo_code":"DAY3500",
            "idempotency_key":"dddddddd-dddd-dddd-dddd-dddddddddddd",
            "expected_price_ugx":3500,
        }
        self.assertEqual(self.owner.post("/api/referrals/wallet/purchase-vip",json=restricted).status_code,400)
        self.assertEqual(self.admin.post(
            f"/api/admin/referral-withdrawals/{withdrawal.json()['id']}/review",
            json={"paid":False,"reason":"Correcting payout details"},
        ).status_code,200)
        incorrect={**restricted,"expected_price_ugx":3400}
        self.assertEqual(self.owner.post("/api/referrals/wallet/purchase-vip",json=incorrect).status_code,400)
        self.assertEqual(self.owner.post("/api/referrals/wallet/purchase-vip",headers={
            "Origin":"https://another.example"
        },json=restricted).status_code,403)
        result=self.owner.post("/api/referrals/wallet/purchase-vip",json=restricted)
        self.assertEqual(result.status_code,200,result.text)
        balance=self.owner.get("/api/referrals/wallet").json()
        self.assertEqual(balance["balance_ugx"],500)
        self.assertEqual(balance["available_ugx"],500)
        self.assertEqual(balance["spent_on_vip_ugx"],3500)
        self.assertEqual(self.buyer.get("/api/referrals/wallet").json()["spent_on_vip_ugx"],0)

    def test_wallet_vip_renewal_extends_expiry_and_lifetime_prevents_repeat(self):
        # A test-only credited referral balance simulates already verified earnings.
        con=referral_wallet.connect()
        try:
            con.execute("""
                INSERT INTO referral_wallet_ledger(
                    event_key,referrer_account_id,entry_type,amount_ugx,created_at
                ) VALUES(?,?,?,?,?)
            """,("test:verified-credit",self.owner_id,"commission",1100000,datetime.now(timezone.utc).isoformat()))
            con.commit()
        finally:con.close()
        first=self.owner.post("/api/referrals/wallet/purchase-vip",json={
            "plan_code":"weekly","idempotency_key":"11111111-1111-1111-1111-111111111111","expected_price_ugx":20000
        })
        self.assertEqual(first.status_code,200,first.text)
        second=self.owner.post("/api/referrals/wallet/purchase-vip",json={
            "plan_code":"weekly","idempotency_key":"22222222-2222-2222-2222-222222222222","expected_price_ugx":20000
        })
        self.assertEqual(second.status_code,200,second.text)
        self.assertGreater(datetime.fromisoformat(second.json()["expires_at"]),datetime.fromisoformat(first.json()["expires_at"]))
        lifetime=self.owner.post("/api/referrals/wallet/purchase-vip",json={
            "plan_code":"lifetime","idempotency_key":"33333333-3333-3333-3333-333333333333","expected_price_ugx":1000000
        })
        self.assertEqual(lifetime.status_code,200,lifetime.text)
        self.assertIsNone(lifetime.json()["expires_at"])
        self.assertEqual(self.owner.post("/api/referrals/wallet/purchase-vip",json={
            "plan_code":"daily","idempotency_key":"44444444-4444-4444-4444-444444444444","expected_price_ugx":5000
        }).status_code,400)
        self.assertEqual(self.owner.get("/api/referrals/wallet").json()["spent_on_vip_ugx"],1040000)


    def test_contributor_pool_split_coins_idempotence_and_refund(self):
        from backend import main, pattern_partners, contributor_rewards
        with patch.dict(os.environ,{"PREDICTOR_CONTRIBUTOR_REWARDS_ENABLED":"true"}):
            self.login_admin()
            rule=main._admin_strategy_catalog()[0]
            details=("A reproducible virtual football strategy with past-season "
                     "trigger conditions, hit-rate evidence and holdout results.")
            sent=self.owner.post("/api/pattern-partners",json={
                "name":"Pattern Contributor","email":"owner@example.org",
                "username":"owner","league":"epl","market":"overs",
                "details":details,"age_confirmed":True,
            })
            self.assertEqual(sent.status_code,200,sent.text)
            sid=sent.json()["reference"]
            verified=self.admin.post(f"/api/admin/pattern-partners/{sid}/review",json={
                "decision":"accept","verified_and_adopted":True,
                "note":"Independently backtested and adopted in deployed rule catalog",
            })
            self.assertEqual(verified.status_code,200,verified.text)
            linked=self.admin.post(f"/api/admin/pattern-partners/{sid}/reward",json={
                "username":"owner","contributor_verified":True,
                "strategy_family":rule["strategy_family"],"rule_id":rule["rule_id"],
            })
            self.assertEqual(linked.status_code,200,linked.text)
            growth.create_promotion("weekly",5000,"COINTEST5K")
            paid=self.buy("TX-COIN-CONTRIBUTOR-001","COINTEST5K")
            self.assertEqual(paid.status_code,200,paid.text)
            self.assertEqual(self.approve(1).status_code,200)
            init=db.connect()
            init.close()
            con=referral_wallet.connect()
            try:
                period=con.execute("SELECT * FROM contributor_reward_periods WHERE purchase_request_id=1").fetchone()
                self.assertEqual(period["reward_cap_ugx"],250)
                buyer=con.execute("SELECT user_key FROM accounts WHERE id=?",(self.buyer_id,)).fetchone()
                now=datetime.now(timezone.utc)
                start=(now-timedelta(days=3)).isoformat()
                chosen=(now-timedelta(days=2)).isoformat()
                end=(now-timedelta(days=1)).isoformat()
                earlier=(now-timedelta(days=4)).isoformat()
                con.execute("UPDATE contributor_reward_periods SET start_at=?,end_at=? WHERE purchase_request_id=1",(start,end))
                con.execute("UPDATE pattern_partner_attributions SET activated_at=? WHERE submission_id=?",(earlier,sid))
                for n in (1,2):
                    key=f"test|unique|selection|{n}"
                    con.execute("""
                        INSERT INTO user_predictions(
                          user_id,season,matchday,prediction_key,league,target_home,
                          target_away,selected,selected_at,created_at
                        ) VALUES(?,?,?,?,?,?,?,?,?,?)
                    """,(buyer["user_key"],"test-season",f"round-{n}",key,"epl",
                         f"Team {n}","Opponent",1,chosen,chosen))
                    if n==1:
                        con.execute("""
                            INSERT INTO prediction_supports(
                              user_id,season,matchday,prediction_key,strategy_family,
                              rule_id,league,target_home,target_away,market,created_at
                            ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
                        """,(buyer["user_key"],"test-season",f"round-{n}",key,
                             rule["strategy_family"],rule["rule_id"],"epl",
                             f"Team {n}","Opponent",rule["market"],chosen))
                con.commit()
            finally:
                con.close()
            state=self.owner.get("/api/referrals/wallet")
            self.assertEqual(state.status_code,200,state.text)
            wallet=state.json()
            self.assertEqual(wallet["referral_earned_ugx"],1000)
            self.assertEqual(wallet["contributor_earned_ugx"],125)
            self.assertEqual(wallet["balance_ugx"],1125)
            self.assertEqual(wallet["available_coins"],112500)
            second=self.owner.get("/api/referrals/wallet").json()
            self.assertEqual(second["contributor_earned_ugx"],125)
            self.assertEqual(contributor_rewards.admin_status()["due_periods"],0)
            confirmed=self.admin.post("/api/admin/contributor-rewards/1/reverse",json={
                "confirmed_refund":True,"reason":"Test confirmed payment chargeback",
            })
            self.assertEqual(confirmed.status_code,200,confirmed.text)
            reversed_state=self.owner.get("/api/referrals/wallet").json()
            self.assertEqual(reversed_state["balance_ugx"],0)
            self.assertEqual(reversed_state["contributor_reversed_ugx"],125)
            self.assertEqual(self.admin.post(
                "/api/admin/contributor-rewards/1/reverse",
                json={"confirmed_refund":True,"reason":"Duplicate refund attempt"},
            ).status_code,400)



if __name__=="__main__":
    unittest.main()

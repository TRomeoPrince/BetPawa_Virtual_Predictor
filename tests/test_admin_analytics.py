"""Private membership analytics, live activity, and one-time admin recovery tests."""
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from backend import access, db, admin_analytics, purchase_requests, referral_wallet


class AdminAnalyticsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.previous=(access.DB,db.DB)
        access.DB=db.DB=Path(self.tmp.name)/"analytics.db"
        self.env=patch.dict(os.environ,{
            "PREDICTOR_ADMIN_PASSWORD":"PrivateBootstrapPassword2026!",
            "PREDICTOR_SIGNUP_ENABLED":"true",
            "PREDICTOR_PURCHASE_ENABLED":"true",
        })
        self.env.start()
        from backend import main
        self.app=main.app
        self.guest=TestClient(self.app,follow_redirects=False)
        self.admin=TestClient(self.app,follow_redirects=False)
        self.member=TestClient(self.app,follow_redirects=False)
        access.ensure_bootstrap_admin()

    def tearDown(self):
        self.guest.close();self.admin.close();self.member.close()
        access.DB,db.DB=self.previous
        self.env.stop()
        self.tmp.cleanup()

    def sign_up(self,client,name,email,code=""):
        result=client.post("/api/auth/signup",json={
            "username":name,"display_name":name.title(),
            "email":email,"password":"StrongClientPassword2026!",
            "age_confirmed":True,"referral_code":code,
        })
        self.assertEqual(result.status_code,200,result.text)
        return result.json()["account"]

    def login_admin(self):
        first=self.admin.post("/api/auth/login",json={
            "username":"admin","password":"PrivateBootstrapPassword2026!",
        })
        self.assertEqual(first.status_code,200,first.text)
        changed=self.admin.post("/api/auth/change-password",json={
            "current_password":"PrivateBootstrapPassword2026!",
            "new_password":"UpdatedAdminAnalyticsPassword2026!",
        })
        self.assertEqual(changed.status_code,200,changed.text)
        login=self.admin.post("/api/auth/login",json={
            "username":"admin","password":"UpdatedAdminAnalyticsPassword2026!",
        })
        self.assertEqual(login.status_code,200,login.text)

    def test_private_analytics_membership_activity_and_revenue(self):
        self.assertEqual(self.guest.get("/api/admin/analytics").status_code,401)
        self.sign_up(self.member,"memberone","memberone@example.test")
        self.assertEqual(self.member.get("/api/admin/analytics").status_code,403)
        self.assertEqual(self.guest.post("/api/activity/ping").status_code,401)
        self.assertEqual(self.member.post("/api/activity/ping",headers={
            "Origin":"https://evil.example",
        }).status_code,403)
        self.assertEqual(self.member.post("/api/activity/ping").status_code,200)
        self.assertEqual(self.guest.get("/api/admin/analytics").status_code,401)
        self.login_admin()
        snap=self.admin.get("/api/admin/analytics")
        self.assertEqual(snap.status_code,200,snap.text)
        self.assertEqual(snap.headers.get("cache-control"),"no-store, private")
        data=snap.json()
        self.assertEqual(data["signups_total"],1)
        self.assertEqual(data["signups_today"],1)
        self.assertEqual(data["signups_7d"],1)
        self.assertEqual(data["online_now"],1)
        self.assertEqual(data["active_24h"],1)
        self.assertEqual(data["active_7d"],1)
        self.assertEqual(data["free_members"],1)
        self.assertEqual(data["active_vip"],0)
        self.assertEqual(len(data["trend"]),14)
        self.assertEqual(data["trend"][-1]["active"],1)
        self.assertEqual(data["trend"][-1]["signups"],1)
        self.assertIn("signed-in",data["online_definition"])
        self.assertNotIn("password",str(data).lower())
        self.assertNotIn("email",str(data).lower())

        pc=purchase_requests.connect()
        try:
            pc.execute("""
                INSERT INTO purchase_requests(
                    reference,email,requested_username,display_name,plan_code,
                    expected_ugx,payment_method,transaction_ref,proof_mime,proof_blob,
                    status,submitted_at,reviewed_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,("VERIFY001","test@example.test","memberone","Member",
                 "weekly",5000,"mtn","TX-VERIFY001","",b"",
                 "approved",datetime.now(timezone.utc).isoformat(),datetime.now(timezone.utc).isoformat()))
            pc.commit()
        finally:pc.close()
        con=referral_wallet.connect()
        try:
            member=con.execute("SELECT id FROM accounts WHERE username='memberone'").fetchone()["id"]
            con.execute("""
                INSERT INTO referral_wallet_spends(
                  idempotency_key,account_id,plan_code,amount_ugx,purchased_at
                ) VALUES(?,?,?,?,?)
            """,("11111111-1111-1111-1111-111111111111",member,"daily",2000,
                 datetime.now(timezone.utc).isoformat()))
            con.execute("""
                INSERT INTO subscriptions(account_id,plan_code,starts_at,expires_at,status,updated_at)
                VALUES(?,?,?,?,'active',?)
            """,(member,"daily",datetime.now(timezone.utc).isoformat(),
                 (datetime.now(timezone.utc)+timedelta(days=1)).isoformat(),datetime.now(timezone.utc).isoformat()))
            con.commit()
        finally:con.close()
        latest=self.admin.get("/api/admin/analytics").json()
        self.assertEqual(latest["gross_external_paid_ugx"],5000)
        self.assertEqual(latest["verified_external_purchases"],1)
        self.assertEqual(latest["wallet_vip_spent_ugx"],2000)
        self.assertEqual(latest["wallet_vip_purchases"],1)
        self.assertEqual(latest["active_vip"],1)
        self.assertEqual(latest["free_members"],0)

    def test_presence_recovery_from_last_seen_and_daily_trend(self):
        a=self.sign_up(self.member,"membertwo","membertwo@example.test")
        stale=(datetime.now(timezone.utc)-timedelta(minutes=10)).isoformat()
        con=access.connect()
        try:
            con.execute("UPDATE member_activity SET last_seen=? WHERE account_id=?",(stale,a["id"]))
            con.execute("UPDATE sessions SET last_seen=? WHERE account_id=?",(stale,a["id"]))
            con.commit()
        finally:con.close()
        before=admin_analytics.snapshot()
        self.assertEqual(before["online_now"],0)
        self.assertEqual(before["active_24h"],1)
        self.assertEqual(self.member.post("/api/activity/ping").status_code,200)
        after=admin_analytics.snapshot()
        self.assertEqual(after["online_now"],1)
        self.assertEqual(after["active_24h"],1)
        self.assertEqual(after["trend"][-1]["active"],1)

    def test_admin_password_recovery_one_shot_and_preserves_members(self):
        member=self.sign_up(self.member,"keepmember","keepmember@example.test")
        con=access.connect()
        try:
            admin_id=con.execute("SELECT id FROM accounts WHERE username='admin'").fetchone()["id"]
        finally:con.close()
        self.assertIsNotNone(access.authenticate("admin","PrivateBootstrapPassword2026!"))
        access.change_password(admin_id,"PrivateBootstrapPassword2026!","ForgottenAdminPassword2026!")
        self.assertIsNone(access.authenticate("admin","PrivateBootstrapPassword2026!"))
        with patch.dict(os.environ,{"PREDICTOR_ADMIN_RECOVERY_ONCE":"test-recover-run-2026-11-12"}):
            self.assertTrue(access.recover_admin_password_from_env())
            self.assertFalse(access.recover_admin_password_from_env())
            restored=access.authenticate("admin","PrivateBootstrapPassword2026!")
            self.assertIsNotNone(restored)
            self.assertTrue(restored["must_change_password"])
            self.assertIsNone(access.authenticate("admin","ForgottenAdminPassword2026!"))
            access.change_password(admin_id,"PrivateBootstrapPassword2026!","PermanentNewAdminPassword2026!")
            self.assertFalse(access.recover_admin_password_from_env())
            self.assertIsNotNone(access.authenticate("admin","PermanentNewAdminPassword2026!"))
            self.assertIsNone(access.authenticate("admin","PrivateBootstrapPassword2026!"))
        con=access.connect()
        try:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM accounts WHERE id=? AND role='client'",
                                         (member["id"],)).fetchone()[0],1)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM admin_recovery_runs").fetchone()[0],1)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM access_audit WHERE action='ADMIN_PASSWORD_RECOVERED'").fetchone()[0],1)
        finally:con.close()


if __name__=="__main__":
    unittest.main()

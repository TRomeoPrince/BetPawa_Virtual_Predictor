"""Pattern partner public submission and verified Lifetime VIP admin reward tests."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from backend import access, db, pattern_partners


class PatternPartnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.old=(access.DB, db.DB)
        access.DB=db.DB=Path(self.tmp.name)/"partner.db"
        self.env=patch.dict(os.environ,{
            "PREDICTOR_ADMIN_PASSWORD":"AdminForPatternPartners2026!",
            "PREDICTOR_SIGNUP_ENABLED":"true",
        })
        self.env.start()
        from backend import main
        self.guest=TestClient(main.app,follow_redirects=False)
        self.member=TestClient(main.app,follow_redirects=False)
        self.admin=TestClient(main.app,follow_redirects=False)
        access.ensure_bootstrap_admin()
        self.application={
            "name":"Pattern Contributor",
            "email":"contributor@example.org",
            "username":"contributor",
            "league":"epl",
            "market":"btts",
            "details":("In the EPL virtual league, when prior matchdays meet these precise conditions, "
                       "the following matchday produces BTTS. Test against all 34 matchdays, "
                       "report hit rate and season-by-season holdout performance."),
            "evidence_url":"https://example.org/pattern-results",
            "age_confirmed":True,
        }

    def tearDown(self):
        for c in (self.guest,self.member,self.admin):
            c.close()
        access.DB,db.DB=self.old
        self.env.stop()
        self.tmp.cleanup()

    def login_admin(self):
        resp=self.admin.post("/api/auth/login",json={
            "username":"admin","password":"AdminForPatternPartners2026!"
        })
        self.assertEqual(resp.status_code,200,resp.text)
        changed=self.admin.post("/api/auth/change-password",json={
            "current_password":"AdminForPatternPartners2026!",
            "new_password":"ChangedPatternAdminPassword2026!",
        })
        self.assertEqual(changed.status_code,200,changed.text)
        self.assertEqual(self.admin.post("/api/auth/login",json={
            "username":"admin","password":"ChangedPatternAdminPassword2026!",
        }).status_code,200)

    def signup(self,email="contributor@example.org",username="contributor"):
        resp=self.member.post("/api/auth/signup",json={
            "username":username,"display_name":"Pattern Contributor",
            "email":email,"password":"StrongContributorPassword2026!",
            "age_confirmed":True,
        })
        self.assertEqual(resp.status_code,200,resp.text)
        return resp.json()["account"]["id"]

    def test_public_call_and_private_review_queue(self):
        home=self.guest.get("/")
        self.assertEqual(home.status_code,200)
        self.assertIn("Found a pattern worth sharing?",home.text)
        self.assertIn('href="/partners"',home.text)
        self.assertEqual(self.guest.get("/partners").status_code,200)
        self.assertIn("Lifetime VIP",self.guest.get("/partners").text)
        self.assertEqual(self.guest.get("/api/admin/pattern-partners").status_code,401)
        bad=self.guest.post("/api/pattern-partners",headers={
            "Origin":"https://evil.example",
        },json=self.application)
        self.assertEqual(bad.status_code,403)
        invalid=self.guest.post("/api/pattern-partners",json={**self.application,"age_confirmed":False})
        self.assertEqual(invalid.status_code,400)
        sent=self.guest.post("/api/pattern-partners",json=self.application)
        self.assertEqual(sent.status_code,200,sent.text)
        ref=sent.json()["reference"]
        self.assertEqual(self.guest.post("/api/pattern-partners",json=self.application).status_code,400)
        self.login_admin()
        items=self.admin.get("/api/admin/pattern-partners").json()["submissions"]
        self.assertEqual(len(items),1)
        self.assertEqual(items[0]["id"],ref)
        self.assertEqual(items[0]["status"],"pending")
        self.assertEqual(items[0]["email"],self.application["email"])
        self.assertEqual(self.guest.get("/api/admin/pattern-partners").status_code,401)

    def test_accept_and_reward_only_after_manual_verification(self):
        member_id=self.signup()
        sent=self.guest.post("/api/pattern-partners",json=self.application)
        self.assertEqual(sent.status_code,200,sent.text)
        sid=sent.json()["reference"]
        self.login_admin()
        self.assertEqual(self.member.get("/api/admin/pattern-partners").status_code,403)
        rejected_credit=self.admin.post(f"/api/admin/pattern-partners/{sid}/reward",json={
            "username":"contributor","contributor_verified":True,
        })
        self.assertEqual(rejected_credit.status_code,400)
        wrong=self.admin.post(f"/api/admin/pattern-partners/{sid}/review",json={
            "decision":"accept","verified_and_adopted":False,"note":"Tested but not adopted",
        })
        self.assertEqual(wrong.status_code,400)
        adopted=self.admin.post(f"/api/admin/pattern-partners/{sid}/review",json={
            "decision":"accept","verified_and_adopted":True,
            "note":"Independent historical backtest verified and pattern incorporated",
        })
        self.assertEqual(adopted.status_code,200,adopted.text)
        self.assertEqual(self.admin.post(f"/api/admin/pattern-partners/{sid}/reward",json={
            "username":"contributor","contributor_verified":False,
        }).status_code,400)
        awarded=self.admin.post(f"/api/admin/pattern-partners/{sid}/reward",json={
            "username":"contributor","contributor_verified":True,
        })
        self.assertEqual(awarded.status_code,200,awarded.text)
        self.assertEqual(awarded.json()["account_id"],member_id)
        self.assertEqual(self.member.get("/api/auth/me").json()["account"]["subscription"]["plan_code"],"lifetime")
        self.assertTrue(self.member.get("/api/auth/me").json()["account"]["subscription"]["is_active"])
        self.assertEqual(self.admin.post(f"/api/admin/pattern-partners/{sid}/reward",json={
            "username":"contributor","contributor_verified":True,
        }).status_code,400)
        con=access.connect()
        try:
            self.assertEqual(con.execute(
                "SELECT COUNT(*) FROM access_audit WHERE action='PATTERN_PARTNER_LIFETIME'"
            ).fetchone()[0],1)
            self.assertEqual(con.execute(
                "SELECT status FROM pattern_partner_submissions WHERE id=?",(sid,)
            ).fetchone()[0],"rewarded")
        finally:con.close()

    def test_rejection_and_email_mismatch_no_vip(self):
        self.signup("different@example.org","different")
        sent=self.guest.post("/api/pattern-partners",json=self.application)
        self.assertEqual(sent.status_code,200,sent.text)
        sid=sent.json()["reference"]
        self.login_admin()
        self.assertEqual(self.admin.post(f"/api/admin/pattern-partners/{sid}/review",json={
            "decision":"accept","verified_and_adopted":True,
            "note":"Validated and adopted for future predictor release",
        }).status_code,200)
        wrong=self.admin.post(f"/api/admin/pattern-partners/{sid}/reward",json={
            "username":"different","contributor_verified":True,
        })
        self.assertEqual(wrong.status_code,400)
        self.assertIn("email",wrong.json()["detail"])
        self.assertEqual(pattern_partners.list_submissions()[0]["status"],"accepted")
        self.assertFalse(self.member.get("/api/auth/me").json()["account"]["subscription"]["is_active"])

    def test_submission_rate_limit(self):
        for idx in range(3):
            payload={**self.application,"details":self.application["details"]+f" Original test case {idx}"}
            result=self.guest.post("/api/pattern-partners",json=payload)
            self.assertEqual(result.status_code,200,result.text)
        extra=self.guest.post("/api/pattern-partners",json={
            **self.application,"details":self.application["details"]+" Additional test case",
        })
        self.assertEqual(extra.status_code,400)
        self.assertIn("Too many",extra.json()["detail"])


if __name__=="__main__":
    unittest.main()

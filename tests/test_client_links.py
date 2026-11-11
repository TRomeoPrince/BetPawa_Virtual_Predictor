import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from backend import access, access_links, db


class ClientLinkTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.old_access_db,self.old_db=access.DB,db.DB
        access.DB=db.DB=Path(self.tmp.name)/"predictor.db"
        self.env=patch.dict(os.environ,{"PREDICTOR_ADMIN_PASSWORD":"InitialAdminPassword2026!"})
        self.env.start()
        from backend import main
        self.client=TestClient(main.app,follow_redirects=False)
        access.ensure_bootstrap_admin()
        self.login("admin","InitialAdminPassword2026!")
        changed=self.client.post("/api/auth/change-password",json={
            "current_password":"InitialAdminPassword2026!",
            "new_password":"ChangedAdminPassword2026!"
        })
        self.assertEqual(changed.status_code,200,changed.text)
        self.login("admin","ChangedAdminPassword2026!")

    def tearDown(self):
        self.client.close()
        access.DB,db.DB=self.old_access_db,self.old_db
        self.env.stop()
        self.tmp.cleanup()

    def login(self,user,password):
        return self.client.post("/api/auth/login",json={"username":user,"password":password})

    def make(self,username="clientone"):
        response=self.client.post("/api/admin/clients",json={
            "username":username,"display_name":"Test Client","plan_code":"weekly"
        })
        self.assertEqual(response.status_code,200,response.text)
        return response.json()

    def activate(self,token,password="PrivateTestPassword2026!"):
        return self.client.post("/api/auth/link-activate",json={
            "token":token,"new_password":password,"age_confirmed":True
        })

    def test_single_use_activation_and_no_token_in_database(self):
        made=self.make()
        token=made["activation_token"]
        self.assertTrue(token)
        con=access_links.connect()
        stored=con.execute("SELECT token_hash FROM client_access_links").fetchone()["token_hash"]
        con.close()
        self.assertNotEqual(token,stored)
        self.client.post("/api/auth/logout")
        self.assertEqual(self.client.post("/api/auth/link-login",json={"token":token}).status_code,401)
        self.assertEqual(self.client.post("/api/auth/link-activate",json={
            "token":token,"new_password":"PrivateTestPassword2026!","age_confirmed":False
        }).status_code,400)
        result=self.activate(token)
        self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(self.client.get("/client").status_code,200)
        self.assertEqual(self.activate(token).status_code,400)
        self.assertEqual(self.client.get("/api/auth/me").json()["account"]["must_change_password"],False)

    def test_personal_login_rotates_and_revokes(self):
        made=self.make()
        cid=made["account"]["id"]
        self.client.post("/api/auth/logout")
        self.assertEqual(self.activate(made["activation_token"]).status_code,200)
        self.client.post("/api/auth/logout")
        self.login("admin","ChangedAdminPassword2026!")
        issue=lambda:self.client.post(f"/api/admin/clients/{cid}/links",json={"kind":"login"})
        first=issue()
        self.assertEqual(first.status_code,200,first.text)
        old=first.json()["token"]
        self.client.post("/api/auth/logout")
        self.assertEqual(self.client.post("/api/auth/link-login",json={"token":old}).status_code,200)
        self.assertEqual(self.client.get("/client").status_code,200)
        self.client.post("/api/auth/logout")
        self.login("admin","ChangedAdminPassword2026!")
        latest=issue()
        self.assertEqual(latest.status_code,200,latest.text)
        fresh=latest.json()["token"]
        self.client.post("/api/auth/logout")
        self.assertEqual(self.client.post("/api/auth/link-login",json={"token":old}).status_code,401)
        self.assertEqual(self.client.post("/api/auth/link-login",json={"token":fresh}).status_code,200)
        self.client.post("/api/auth/logout")
        self.login("admin","ChangedAdminPassword2026!")
        self.assertEqual(self.client.post(f"/api/admin/clients/{cid}/links/revoke",json={"kind":"login"}).status_code,200)
        self.client.post("/api/auth/logout")
        self.assertEqual(self.client.post("/api/auth/link-login",json={"token":fresh}).status_code,401)

    def test_subscription_revoke_and_password_reset_disable_link(self):
        made=self.make("clienttwo")
        cid=made["account"]["id"]
        self.client.post("/api/auth/logout")
        self.activate(made["activation_token"])
        self.client.post("/api/auth/logout")
        self.login("admin","ChangedAdminPassword2026!")
        token=self.client.post(f"/api/admin/clients/{cid}/links",json={"kind":"login"}).json()["token"]
        self.assertEqual(self.client.post(f"/api/admin/clients/{cid}/subscription/revoke").status_code,200)
        self.client.post("/api/auth/logout")
        self.assertEqual(self.client.post("/api/auth/link-login",json={"token":token}).status_code,401)
        self.login("admin","ChangedAdminPassword2026!")
        self.assertEqual(self.client.post(f"/api/admin/clients/{cid}/subscription",json={"plan_code":"weekly"}).status_code,200)
        self.assertEqual(self.client.post("/api/auth/link-login",json={"token":token}).status_code,200)
        self.client.post("/api/auth/logout")
        self.login("admin","ChangedAdminPassword2026!")
        reset=self.client.post(f"/api/admin/clients/{cid}/reset-password")
        self.assertEqual(reset.status_code,200,reset.text)
        invite=reset.json()["activation_token"]
        self.client.post("/api/auth/logout")
        self.assertEqual(self.client.post("/api/auth/link-login",json={"token":token}).status_code,401)
        self.assertEqual(self.activate(invite,"NewPrivatePassword2026!").status_code,200)

    def test_only_admin_can_issue_links_and_no_admin_bearer(self):
        made=self.make("clientthree")
        self.assertEqual(self.client.post("/api/admin/clients/1/links",json={"kind":"login"}).status_code,400)
        self.assertEqual(self.client.post(f"/api/admin/clients/{made['account']['id']}/links",json={"kind":"login"}).status_code,400)
        self.client.post("/api/auth/logout")
        self.assertIn(self.client.post(f"/api/admin/clients/{made['account']['id']}/links",json={"kind":"activation"}).status_code,(401,403))
        self.assertEqual(self.client.get("/activate").status_code,200)
        self.assertEqual(self.client.get("/access").status_code,200)


if __name__=="__main__":
    unittest.main()

"""Win Proof screenshot submission, authorization, moderation and publication."""
import base64
import io
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image

from backend import access, db, win_proofs


def screenshot():
    stream = io.BytesIO()
    Image.new("RGB", (240, 160), "green").save(stream, "PNG")
    return "data:image/png;base64," + base64.b64encode(stream.getvalue()).decode()


class WinProofTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.before = (access.DB, db.DB)
        access.DB = db.DB = Path(self.tmp.name) / "db.sqlite"
        self.env = patch.dict(os.environ, {"PREDICTOR_ADMIN_PASSWORD":"WinProofTestPassword2026!"})
        self.env.start()
        from backend import main
        self.app = main
        access.ensure_bootstrap_admin()
        self.guest=TestClient(main.app)
        self.member=TestClient(main.app)
        self.admin=TestClient(main.app)
        self.member.post("/api/auth/signup",json={
            "username":"proofuser", "display_name":"Proof member", "email":"proof@example.com",
            "password":"VerySecureProofPassword2026!","age_confirmed":True
        })
        login=self.admin.post("/api/auth/login",json={"username":"admin","password":"WinProofTestPassword2026!"})
        self.assertEqual(login.status_code,200,login.text)
        changed=self.admin.post("/api/auth/change-password",json={
            "current_password":"WinProofTestPassword2026!",
            "new_password":"WinProofTestChangedAdminPassword2026!"
        })
        self.assertEqual(changed.status_code,200,changed.text)
        login=self.admin.post("/api/auth/login",json={
            "username":"admin","password":"WinProofTestChangedAdminPassword2026!"
        })
        self.assertEqual(login.status_code,200,login.text)

    def tearDown(self):
        self.guest.close();self.member.close();self.admin.close()
        access.DB,db.DB=self.before
        self.env.stop();self.tmp.cleanup()

    def test_submission_is_private_until_admin_approval(self):
        img=screenshot()
        self.assertEqual(self.guest.post("/api/win-proofs",json={"image_base64":img,"consent":True}).status_code,401)
        self.assertEqual(self.member.post("/api/win-proofs",json={"image_base64":img,"consent":False}).status_code,400)
        r=self.member.post("/api/win-proofs",json={"image_base64":img,"consent":True})
        self.assertEqual(r.status_code,200,r.text)
        proof_id=r.json()["id"]
        self.assertEqual(self.guest.get("/api/win-proofs").json()["items"],[])
        self.assertEqual(self.guest.get(f"/api/win-proofs/{proof_id}/image").status_code,404)
        self.assertEqual(self.member.get(f"/api/win-proofs/{proof_id}/image").status_code,200)
        self.assertEqual(self.member.get("/api/admin/win-proofs").status_code,403)
        self.assertEqual(self.member.post(f"/api/admin/win-proofs/{proof_id}/review",json={"decision":"approved"}).status_code,403)
        self.assertEqual(self.admin.get("/api/admin/win-proofs").json()["items"][0]["username"],"proofuser")
        self.assertEqual(self.admin.post(f"/api/admin/win-proofs/{proof_id}/review",json={"decision":"approved"}).status_code,200)
        published=self.guest.get("/api/win-proofs").json()["items"]
        self.assertEqual(len(published),1)
        self.assertEqual(published[0]["caption"],"Won by @proofuser")
        self.assertEqual(self.guest.get(f"/api/win-proofs/{proof_id}/image").status_code,200)
        self.assertEqual(self.admin.post(f"/api/admin/win-proofs/{proof_id}/review",json={"decision":"rejected"}).status_code,200)
        self.assertEqual(self.guest.get("/api/win-proofs").json()["items"],[])
        self.assertEqual(self.guest.get(f"/api/win-proofs/{proof_id}/image").status_code,404)

    def test_admin_bulk_import_labels_as_community_without_exposing_admin_as_winner(self):
        image_bytes = base64.b64decode(screenshot().split(",", 1)[1])
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("private-ready-1.png", image_bytes)
            archive.writestr("private-ready-2.png", image_bytes)
            archive.writestr("manifest.json", '{"note":"Not a screenshot; ignore this"}')
        zip_data = base64.b64encode(stream.getvalue()).decode("ascii")
        payload = {"archive_base64": zip_data, "redaction_confirmed": True}
        self.assertIn(
            self.guest.post("/api/admin/win-proofs/import", json=payload).status_code,
            (401, 403),
        )
        self.assertIn(
            self.member.post("/api/admin/win-proofs/import", json=payload).status_code,
            (401, 403),
        )
        self.assertEqual(
            self.admin.post("/api/admin/win-proofs/import",
                            json={**payload, "redaction_confirmed": False}).status_code,
            400,
        )
        accepted = self.admin.post("/api/admin/win-proofs/import", json=payload)
        self.assertEqual(accepted.status_code, 200, accepted.text)
        self.assertEqual(accepted.json()["imported"], 2)
        public = self.guest.get("/api/win-proofs").json()["items"]
        self.assertEqual(len(public), 2)
        self.assertTrue(all(x["caption"] == "Community win" for x in public))
        self.assertTrue(all(x["caption"] != "Won by @admin" for x in public))
        self.assertTrue(all(self.guest.get(x["image_url"]).status_code == 200 for x in public))

    def test_bad_curated_archive_does_not_publish_anything(self):
        invalid = base64.b64encode(b"not a zip").decode("ascii")
        response = self.admin.post("/api/admin/win-proofs/import", json={
            "archive_base64": invalid, "redaction_confirmed": True
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.guest.get("/api/win-proofs").json()["items"], [])

    def test_wrong_image_and_right_to_remove(self):
        self.assertEqual(self.member.post("/api/win-proofs",json={"image_base64":base64.b64encode(b"hello").decode(),"consent":True}).status_code,400)
        r=self.member.post("/api/win-proofs",json={"image_base64":screenshot(),"consent":True})
        proof_id=r.json()["id"]
        self.assertEqual(self.guest.delete(f"/api/win-proofs/{proof_id}").status_code,401)
        self.assertEqual(self.member.delete(f"/api/win-proofs/{proof_id}").status_code,200)
        self.assertEqual(self.member.get("/api/win-proofs/mine").json()["items"],[])
        self.assertEqual(self.guest.get(f"/api/win-proofs/{proof_id}/image").status_code,404)


if __name__=="__main__":
    unittest.main()

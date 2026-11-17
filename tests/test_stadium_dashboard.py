"""Stadium dashboard layout is user-selected, responsive, and truthful."""
from pathlib import Path
import shutil
import subprocess
import unittest

from fastapi.testclient import TestClient

from backend import main

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"


class StadiumDashboardTests(unittest.TestCase):
    def test_only_client_pages_load_dashboard_shell(self):
        for page in ("client", "picks"):
            html = (FRONTEND / (page + ".html")).read_text(encoding="utf-8")
            self.assertEqual(html.count('<script defer src="/bpv-stadium-dashboard.js"></script>'), 1)
        for page in ("index", "signup", "login", "admin", "market"):
            html = (FRONTEND / (page + ".html")).read_text(encoding="utf-8")
            self.assertNotIn('src="/bpv-stadium-dashboard.js"', html)

    def test_stadium_layout_is_opt_in_and_mobile_responsive(self):
        css = (FRONTEND / "bpv-themes.css").read_text(encoding="utf-8")
        self.assertIn(".stadium-shell{display:contents}", css)
        self.assertIn(".stadium-sidebar,.stadium-rail,.stadium-overview{display:none}", css)
        self.assertIn(':root[data-bpv-theme="stadium"] .stadium-shell', css)
        self.assertIn("grid-template-columns:minmax(218px,248px) minmax(0,1fr) minmax(248px,305px)", css)
        for size in ("1050px", "800px", "610px"):
            self.assertIn("@media(max-width:" + size + ")", css)
        script = (FRONTEND / "bpv-stadium-dashboard.js").read_text(encoding="utf-8")
        self.assertIn('page !== "/client" && page !== "/client/picks"', script)
        self.assertIn('document.querySelector("main")', script)
        self.assertIn('stadium-sidebar', script)
        self.assertIn('stadium-rail', script)
        self.assertIn('stadium-overview', script)
        self.assertIn("loadAccount();", script)
        self.assertIn("loadSaved();", script)
        self.assertIn("loadJournal();", script)
        self.assertIn("loadRecommended();", script)

    def test_old_white_client_sections_now_use_theme_variables(self):
        css = (FRONTEND / "bpv-themes.css").read_text(encoding="utf-8")
        for name in ("winSubmitPanel", "winProofOwn", "winProofAgree", "winProofHelp",
                     "referralMetric", "premiumTable th", "referralPeople th"):
            self.assertIn(name, css)
        self.assertIn("background:var(--bpv-surface)", css)
        self.assertIn("background:var(--bpv-raised)", css)

    def test_no_fake_wins_odds_or_betting_data(self):
        source = (FRONTEND / "bpv-stadium-dashboard.js").read_text(encoding="utf-8")
        self.assertNotIn("76.4%", source)
        self.assertNotIn("1,284", source)
        self.assertNotIn("89%", source)
        self.assertNotIn("2.15x", source)
        self.assertIn("not verified wagers", source)
        self.assertIn("/api/client/picks?", source)
        self.assertIn("/api/client/bet-journal?", source)
        self.assertIn("/api/recommended-picks", source)
        self.assertIn("navigator.clipboard.writeText", source)
        self.assertIn("stake.value.trim()", source)
        self.assertIn("odds.value.trim()", source)

    def test_static_asset_public_and_no_private_data_in_response(self):
        with TestClient(main.app, follow_redirects=False) as client:
            js = client.get("/bpv-stadium-dashboard.js")
            self.assertEqual(js.status_code, 200, js.text[:200])
            self.assertIn("javascript", js.headers["content-type"])
            self.assertEqual(js.headers["x-content-type-options"], "nosniff")
            self.assertNotIn("set-cookie", js.headers)
            self.assertIn("stadium-sidebar", js.text)
            self.assertEqual(client.get("/client").status_code, 302)
            self.assertEqual(client.get("/client/picks").status_code, 302)

    def test_javascript_valid_when_node_is_available(self):
        node = shutil.which("node")
        if node:
            subprocess.run(
                [node, "--check", str(FRONTEND / "bpv-stadium-dashboard.js")],
                check=True, capture_output=True, text=True
            )


if __name__ == "__main__":
    unittest.main()

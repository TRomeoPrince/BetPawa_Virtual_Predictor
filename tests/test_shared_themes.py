"""Shared BPV themes: no changes to auth, signup, predictions, or payments."""
from pathlib import Path
import shutil
import subprocess
import unittest

from fastapi.testclient import TestClient

from backend import main

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
PAGES = (
    "index", "login", "signup", "client", "admin", "market", "picks",
    "purchase", "partners", "activate", "access-link", "password-setup",
)
COLOR_THEMES = ("light", "dark", "stadium", "forest", "ocean", "sunset", "violet")


class SharedThemesTests(unittest.TestCase):
    def test_every_page_has_early_bootstrap_and_late_stylesheet(self):
        for name in PAGES:
            with self.subTest(page=name):
                text = (FRONTEND / (name + ".html")).read_text(encoding="utf-8")
                self.assertEqual(text.count('<script src="/bpv-themes.js"></script>'), 1)
                self.assertEqual(text.count('<link rel="stylesheet" href="/bpv-themes.css">'), 1)
                self.assertLess(
                    text.index('<script src="/bpv-themes.js"></script>'),
                    text.index("<style>"),
                )
                self.assertLess(
                    text.rfind("</style>"),
                    text.index('<link rel="stylesheet" href="/bpv-themes.css">'),
                )
                self.assertLess(
                    text.index('<link rel="stylesheet" href="/bpv-themes.css">'),
                    text.index("</head>"),
                )

    def test_style_has_all_six_palettes_and_responsive_picker(self):
        css = (FRONTEND / "bpv-themes.css").read_text(encoding="utf-8")
        for name in COLOR_THEMES:
            self.assertIn(':root[data-bpv-theme="' + name + '"]', css)
        for selector in ("#bpv-theme-toggle", "#bpv-theme-menu", "@media(max-width:570px)"):
            self.assertIn(selector, css)
        script = (FRONTEND / "bpv-themes.js").read_text(encoding="utf-8")
        for name in COLOR_THEMES:
            self.assertIn('id:"' + name + '"', script)
        self.assertIn('id:"system"', script)
        self.assertIn("prefers-color-scheme: dark", script)
        self.assertIn("localStorage.getItem", script)
        self.assertIn("localStorage.setItem", script)
        self.assertIn("aria-pressed", script)
        self.assertIn('event.key === "Escape"', script)

    def test_stadium_theme_matches_football_night_reference_without_demo_data(self):
        css = (FRONTEND / "bpv-themes.css").read_text(encoding="utf-8")
        js = (FRONTEND / "bpv-themes.js").read_text(encoding="utf-8")
        self.assertIn(':root[data-bpv-theme="stadium"]', css)
        self.assertIn("Stadium Neon", js)
        self.assertIn('id:"stadium"', js)
        self.assertIn('[data-bpv-swatch="stadium"]', css)
        self.assertIn('--bpv-gold:#ffd052', css)
        self.assertIn('radial-gradient', css)
        self.assertIn("current === \"stadium\"", js)
        # A theme is cosmetic; odds, ROI, streaks and win rates must not
        # be planted as fictional examples into real user dashboards.
        self.assertNotIn("76.4%", css)
        self.assertNotIn("76.4%", js)
        self.assertNotIn("1,284", css)
        self.assertNotIn("1,284", js)

    def test_public_assets_correct_mime_and_no_auth_required(self):
        with TestClient(main.app, follow_redirects=False) as client:
            css = client.get("/bpv-themes.css")
            js = client.get("/bpv-themes.js")
            self.assertEqual(css.status_code, 200)
            self.assertEqual(js.status_code, 200)
            self.assertIn("text/css", css.headers["content-type"])
            self.assertIn("javascript", js.headers["content-type"])
            self.assertIn("nosniff", js.headers.get("x-content-type-options", ""))
            self.assertNotIn("set-cookie", css.headers)
            self.assertNotIn("set-cookie", js.headers)
            page = client.get("/")
            self.assertEqual(page.status_code, 200)
            self.assertIn('src="/bpv-themes.js"', page.text)

    def test_theme_js_is_syntactically_valid_when_node_is_available(self):
        node = shutil.which("node")
        if node:
            subprocess.run([node, "--check", str(FRONTEND / "bpv-themes.js")],
                           check=True, capture_output=True, text=True)


if __name__ == "__main__":
    unittest.main()

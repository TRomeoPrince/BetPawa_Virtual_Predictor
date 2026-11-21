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
        for page in ("client", "picks", "market"):
            html = (FRONTEND / (page + ".html")).read_text(encoding="utf-8")
            self.assertEqual(html.count('<script defer src="/bpv-stadium-dashboard.js"></script>'), 1)
        for page in ("index", "signup", "login", "admin"):
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
        self.assertIn('bpv-sidebar', script)
        self.assertIn('const sidebar = el(', script)
        self.assertIn('stadium-rail', script)
        self.assertIn('stadium-overview', script)
        self.assertIn("loadAccount();", script)
        self.assertIn("loadSaved();", script)
        self.assertIn("loadJournal();", script)
        self.assertIn("loadRecommended();", script)

    def test_unified_sidebar_links_are_real_and_accessible(self):
        source = (FRONTEND / "bpv-stadium-dashboard.js").read_text(encoding="utf-8")
        css = (FRONTEND / "bpv-themes.css").read_text(encoding="utf-8")
        home = (FRONTEND / "client.html").read_text(encoding="utf-8")
        for label, path in (
            ("Dashboard", "/client"),
            ("My Picks Hub", "/client/picks"),
            ("Overs", "/client/overs"),
            ("Unders", "/client/unders"),
            ("BTTS", "/client/btts"),
            ("1X2", "/client/1x2"),
            ("Win Proof", "/client#winProofSubmit"),
            ("VIP Predictions", "/purchase"),
        ):
            with self.subTest(label=label):
                self.assertIn('"' + label + '","' + path + '"', source)
        self.assertIn('id="winProofSubmit"', home)
        self.assertIn('id="premiumPicksSection"', home)
        self.assertIn('nav.setAttribute("aria-label","BPV primary navigation")', source)
        self.assertIn('anchor.setAttribute("aria-current"', source)
        self.assertIn('adminConsole.href="/admin"', source)
        self.assertIn('adminConsole.hidden=!admin', source)
        self.assertIn('vipLink.href=vip?', source)
        self.assertIn('location.assign("/login")', source)
        self.assertIn('response.ok', source)
        self.assertIn('window.addEventListener("hashchange",()=>', source)
        self.assertIn('scrollIntoView(', source)
        self.assertIn('.bpv-sidebar :is(a,button):focus-visible', css)
        self.assertIn('.bpv-side-nav .bpv-side-link[hidden]', css)
        self.assertIn(':root[data-bpv-theme="stadium"] .bpv-sidebar', css)
        self.assertIn('const sidebar = el(', source)
        self.assertNotIn('"Market Research","/client', source)
        self.assertNotIn('"Live Selections","/client', source)

    def test_navigation_persists_across_every_market_and_uses_live_routes(self):
        source = (FRONTEND / "bpv-stadium-dashboard.js").read_text(encoding="utf-8")
        css = (FRONTEND / "bpv-themes.css").read_text(encoding="utf-8")
        self.assertIn('const isMarket = /^\\/client\\/(overs|unders|btts|1x2)$/.test(page)', source)
        self.assertIn('shell.classList.add("stadium-market-shell")', source)
        self.assertIn(".stadium-shell.stadium-market-shell", css)
        self.assertIn("body:has(.bpv-sidebar) .stadium-content > nav.nav", css)
        self.assertIn("body:has(.bpv-sidebar) > header", css)
        self.assertIn("grid-template-columns:minmax(0,1fr)", css)
        self.assertIn("pointer-events:auto", css)
        with TestClient(main.app, follow_redirects=False) as client:
            for market in ("overs", "unders", "btts", "1x2", "wins"):
                with self.subTest(market=market):
                    self.assertEqual(client.get("/client/" + market).status_code, 302)
            self.assertEqual(client.get("/client/unknown-market").status_code, 404)

    def test_sidebar_is_vertical_complete_and_mobile_collapsible(self):
        source = (FRONTEND / "bpv-stadium-dashboard.js").read_text(encoding="utf-8")
        css = (FRONTEND / "bpv-themes.css").read_text(encoding="utf-8")
        self.assertIn('sidebar.id = "bpv-client-sidebar"', source)
        self.assertIn('el("aside","bpv-sidebar")', source)
        self.assertIn('el("div","bpv-sidebar-heading")', source)
        self.assertIn('el("span","bpv-sidebar-tier"', source)
        self.assertIn('el("button","bpv-menu-toggle","☰  Menu")', source)
        self.assertIn('menuToggle.setAttribute("aria-expanded","false")', source)
        self.assertIn('menuToggle.setAttribute("aria-expanded","true")', source)
        self.assertIn('closeSidebar.addEventListener("click"', source)
        self.assertIn('backdrop.addEventListener("click"', source)
        self.assertIn('event.key==="Escape"', source)
        self.assertIn('nav.addEventListener("click"', source)
        self.assertIn('shell.append(mobileBar,backdrop,sidebar,main,rail)', source)
        self.assertNotIn("shell.append(nav,main", source)
        self.assertIn('grid-template-columns:minmax(205px,245px) minmax(0,1fr) minmax(248px,305px)', css)
        self.assertIn('position:sticky', css)
        self.assertIn('width:min(310px,87vw)', css)
        self.assertIn('transform:translateX(-110%)', css)
        self.assertIn('@media(max-width:760px)', css)

    def test_sidebar_refinement_has_uniform_outline_icons_and_readable_text(self):
        script = (FRONTEND / "bpv-stadium-dashboard.js").read_text(encoding="utf-8")
        css = (FRONTEND / "bpv-themes.css").read_text(encoding="utf-8")
        self.assertIn('function navIcon(name)', script)
        self.assertIn('document.createElementNS(namespace,"svg")', script)
        self.assertIn('svg.setAttribute("width","20")', script)
        self.assertIn('svg.setAttribute("stroke-width","1.85")', script)
        self.assertIn('svg.setAttribute("aria-hidden","true")', script)
        for key in ("dashboard", "picks", "overs", "unders", "btts",
                    "wins", "proof", "vip", "admin", "logout"):
            self.assertIn(key + ':[', script)
        self.assertIn('anchor.append(glyph,document.createTextNode(label))', script)
        self.assertIn('navIcon("admin")', script)
        self.assertIn('navIcon("logout")', script)
        self.assertIn("BPV Sidebar Refresh", css)
        self.assertIn('font:560 15.5px/1.4 Inter', css)
        self.assertIn('font-weight:650', css)
        self.assertIn('border-radius:0;', css)
        self.assertIn('box-shadow:none;', css)
        self.assertIn('background:rgba(0,190,123,.14)', css)
        self.assertIn('@media(max-width:760px)', css)
        self.assertIn('min-height:46px;', css)
        self.assertNotIn('el("span","bpv-side-icon"', script)

    def test_stadium_is_translucent_glass_not_opaque_black(self):
        css = (FRONTEND / "bpv-themes.css").read_text(encoding="utf-8")
        self.assertIn("Stadium Neon — TRANSLUCENT GLASS treatment", css)
        self.assertIn('--stadium-glass:rgba(18,32,43,.72)', css)
        self.assertIn('--stadium-glass-blur:blur(16px) saturate(124%)', css)
        self.assertIn("backdrop-filter:var(--stadium-glass-blur)", css)
        self.assertIn("rgba(29,50,62,.77)", css)
        self.assertIn("rgba(9,23,33,.71)", css)
        self.assertIn("rgba(23,82,72,.68)", css)
        self.assertIn("rgba(11,35,44,.68)", css)
        self.assertIn("background:rgba(11,30,39,.61)", css)
        self.assertIn('rgba(7,20,30,.78)', css)
        # Every glass selector must remain opt-in for Stadium Neon.
        start = css.index("Stadium Neon — TRANSLUCENT GLASS treatment")
        glass = css[start:]
        self.assertNotIn(':root[data-bpv-theme="light"]', glass)
        self.assertNotIn(':root[data-bpv-theme="forest"]', glass)
        self.assertIn(':root[data-bpv-theme="stadium"] .stadium-stat', glass)
        self.assertIn(':root[data-bpv-theme="stadium"] .bpv-sidebar', glass)
        self.assertIn("@media (max-width:760px)", glass)

    def test_market_page_access_is_explained_without_changing_prediction_gate(self):
        market = (FRONTEND / "market.html").read_text(encoding="utf-8")
        self.assertIn('id="marketAccessHint"', market)
        self.assertIn('checkMarketAccess();', market)
        self.assertIn('fetch(\'/api/free-access/status\'', market)
        self.assertIn("not included in the current Free Access release", market)
        self.assertIn("View VIP plans", market)
        css = (FRONTEND / "bpv-themes.css").read_text(encoding="utf-8")
        self.assertIn(".marketAccessHint[hidden]", css)

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
            self.assertIn("bpv-sidebar", js.text)
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

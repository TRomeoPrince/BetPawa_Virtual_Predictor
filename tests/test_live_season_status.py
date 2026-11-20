"""Official current virtual seasons must be separate from historical saved picks."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend import main
from backend.current_seasons import current_season_status
from backend.recommendation_quality import reviewed_h2h_catalog

ROOT=Path(__file__).resolve().parents[1]


def season(sid, start, count=34):
    return {
        "id":str(sid),
        "rounds":[{
            "id":str(sid)+"-"+str(i+1),
            "name":str(i+1),
            "tradingTime":{
                "start":(start+timedelta(minutes=5*i)).isoformat(),
                "end":(start+timedelta(minutes=5*(i+1))).isoformat(),
            }
        }for i in range(count)]
    }


class LiveSeasonSelectionTests(unittest.TestCase):
    def setUp(self):
        self.at=datetime(2026,11,20,15,46,tzinfo=timezone.utc)
        self.epoch=self.at.timestamp()
        self.catalog={"items":[
            season("139502",datetime(2026,11,20,10,40,tzinfo=timezone.utc)),
            season("139503",datetime(2026,11,20,13,30,tzinfo=timezone.utc)),
            season("139504",datetime(2026,11,20,16,20,tzinfo=timezone.utc)),
        ]}

    def test_official_current_season_matches_known_source_round(self):
        report=current_season_status(self.catalog,now_ts=self.epoch)
        self.assertEqual(report["status"],"live")
        self.assertEqual(report["current_season"],"139503")
        self.assertEqual(report["current_matchday"],28)
        self.assertEqual(report["active_round"]["round_id"],"139503-28")
        self.assertEqual(report["active_round"]["round_open_utc"],
                         "2026-11-20T15:45:00+00:00")
        self.assertEqual(report["next_matchday"],29)
        self.assertEqual(report["next_round"]["round_open_utc"],
                         "2026-11-20T15:50:00+00:00")

    def test_no_stale_fallback_when_no_season_contains_current_time(self):
        report=current_season_status({"items":[self.catalog["items"][0]]},
                                     now_ts=self.epoch)
        self.assertEqual(report["status"],"unavailable")
        self.assertIsNone(report["current_season"])
        self.assertIsNone(report["active_round"])

    def test_future_season_is_not_mislabeled_current(self):
        report=current_season_status({"items":[self.catalog["items"][2]]},
                                     now_ts=self.epoch)
        self.assertEqual(report["status"],"unavailable")
        self.assertIsNone(report["current_season"])
        self.assertEqual(report["upcoming_season"],"139504")

    def test_current_endpoint_requires_auth_and_uses_current_catalog(self):
        with TestClient(main.app,follow_redirects=False) as client:
            self.assertEqual(client.get("/api/virtual/season-status").status_code,401)
            with patch.object(main,"_require_account",return_value={"role":"admin"}), \
                 patch.object(main.feed,"_catalog",return_value=(self.catalog,{"seasons":[]},"direct-http")):
                r=client.get("/api/virtual/season-status")
                self.assertEqual(r.status_code,200,r.text)
                # Endpoint uses server clock, so the synthetic timestamp must
                # be supplied by the helper test above, not asserted here.
                self.assertIn("verified_at_utc",r.json())
                self.assertIn("current_season",r.json())

    def test_owner_h2h_watchlist_is_market_specific_and_never_scheduled(self):
        patterns=reviewed_h2h_catalog()
        self.assertEqual(len(patterns),9)
        self.assertEqual(patterns[0]["home"],"TOT")
        self.assertEqual(patterns[0]["away"],"CHE")
        self.assertEqual(patterns[0]["market"],"BTTS YES")
        self.assertTrue(any(x["home"]=="CRY" and x["away"]=="TOT" and
                            x["tier"]=="watch-only" for x in patterns))
        self.assertTrue(any(x["home"]=="AST" and x["away"]=="CRY" and
                            x["market"]=="HOME WIN" for x in patterns))
        self.assertFalse(any((x["home"],x["away"]) in
                             {("BRE","SUN"),("SUN","BRE")} for x in patterns))
        self.assertTrue(all(x["scheduled"] is False for x in patterns))

    def test_frontend_separates_old_saved_history_from_live_picks(self):
        js=(ROOT/"frontend"/"bpv-stadium-dashboard.js").read_text("utf-8")
        css=(ROOT/"frontend"/"bpv-themes.css").read_text("utf-8")
        self.assertIn("/api/virtual/season-status",js)
        self.assertIn("String(item.season)===String(live.current_season)",js)
        self.assertIn('item.round_close_utc && Date.parse(item.round_close_utc)>Date.now()',js)
        self.assertIn("current or upcoming saved selections",js.lower())
        self.assertIn("current_matchday",js)
        self.assertIn("reviewed_h2h_patterns",js)
        self.assertIn("Not currently scheduled",js)
        self.assertIn("sourceVerified=validLiveRound",js)
        self.assertIn("String(data.next_round_id)===String(live.active_round?.round_id)",js)
        self.assertIn("String(data.next_round_id)===String(live.next_round?.round_id)",js)
        self.assertIn("setInterval(async()=>",js)
        self.assertIn(".stadium-h2h-item",css)
        self.assertIn(".stadium-live-feed",css)
        self.assertIn("My Picks Hub",js)

    def test_javascript_parses_when_node_available(self):
        exe=shutil.which("node")
        if not exe:
            self.skipTest("Node not available")
        r=subprocess.run([exe,"--check",str(ROOT/"frontend"/"bpv-stadium-dashboard.js")],
                         capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stderr)


if __name__=="__main__":
    unittest.main()

"""Source round schedules must stay distinct from legacy model estimates."""
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend import db, picks, main
from backend.providers.betpawa import BetPawaFeed

ROOT=Path(__file__).resolve().parent.parent
FRONTEND=ROOT/"frontend"


class RoundScheduleTests(unittest.TestCase):
    def test_feed_uses_source_trading_times_with_explicit_timezone(self):
        # This is a synthetic feed fixture, not a claim about a real kickoff.
        season={"id":"139475","rounds":[
            {"id":"done","tradingTime":{
                "start":"2026-11-17T13:30:00+03:00",
                "end":"2026-11-17T13:35:00+03:00"}},
            {"id":"next","tradingTime":{
                "start":"2026-11-17T13:35:00+03:00",
                "end":"2026-11-17T13:40:00+03:00"}},
        ]}
        feed=BetPawaFeed()
        rounds={"done":{},"next":{}}
        with patch.object(feed,"_catalog",return_value=([],[],"test")), \
             patch.object(feed,"_select_context_seasons",return_value=(season,0,[])), \
             patch.object(feed,"_fetch_rounds",return_value=(
                 rounds,{}, "fixture", "fixture-endpoint", 0, 0
             )), \
             patch.object(feed,"normalize_round",return_value={}):
            result=feed.prediction_context()
        self.assertEqual(result["next_round_open_utc"],"2026-11-17T10:35:00+00:00")
        self.assertEqual(result["next_round_close_utc"],"2026-11-17T10:40:00+00:00")
        self.assertEqual(result["next_matchday"],2)
        self.assertEqual(result["next_round_id"],"next")

    def test_saved_pick_retains_source_round_window_even_on_refresh_without_timestamps(self):
        old=db.DB
        with tempfile.TemporaryDirectory() as directory:
            db.DB=Path(directory)/"client.db"
            try:
                payload={
                    "season":"139475","next_matchday":2,"next_round_id":"source-next",
                    "next_round_open_utc":"2026-11-17T10:35:00+00:00",
                    "next_round_close_utc":"2026-11-17T10:40:00+00:00",
                    "predictions":[{
                        "league":"English","target_home":"CHE","target_away":"TOT",
                        "expected":"Over 2.5 FT","estimated_target_time_eat":"10:20",
                    }]
                }
                db.save_user_prediction_batch("user-example",payload)
                self.assertTrue(db.set_prediction_selected(
                    "user-example","139475","2","English","CHE","TOT","Over 2.5 FT",True
                ))
                rows=picks.get_picks("user-example",scope="all")["items"]
                self.assertEqual(len(rows),1)
                self.assertEqual(rows[0]["round_open_utc"],payload["next_round_open_utc"])
                self.assertEqual(rows[0]["round_close_utc"],payload["next_round_close_utc"])
                self.assertEqual(rows[0]["estimated_target_time_eat"],"10:20")
                db.save_user_prediction_batch("user-example",{
                    **payload,"next_round_open_utc":None,"next_round_close_utc":None
                })
                self.assertEqual(
                    picks.get_picks("user-example",scope="all")["items"][0]["round_close_utc"],
                    payload["next_round_close_utc"]
                )
            finally:
                db.DB=old

    def test_round_formatter_is_read_only_and_present(self):
        with TestClient(main.app,follow_redirects=False) as client:
            response=client.get("/bpv-round-times.js")
            self.assertEqual(response.status_code,200)
            self.assertIn("BPVRoundTime",response.text)
            self.assertIn('Africa/Kampala',response.text)
            self.assertIn('individual kickoff may differ',response.text)
            self.assertIn("historical season anchor",response.text)
            self.assertNotIn("set-cookie",response.headers)
            for page in ("client.html","picks.html","market.html"):
                self.assertIn('src="/bpv-round-times.js"',(FRONTEND/page).read_text())

    def test_new_source_round_fields_reach_prediction_and_public_apis(self):
        predictor=(ROOT/"backend"/"predictor.py").read_text()
        maintext=(ROOT/"backend"/"main.py").read_text()
        for field in ("next_round_open_utc","next_round_close_utc"):
            self.assertIn(field,predictor)
            self.assertIn(field,maintext)
            self.assertIn(field,(FRONTEND/"market.html").read_text())
            self.assertIn(field,(FRONTEND/"bpv-stadium-dashboard.js").read_text())
        picks_html=(FRONTEND/"picks.html").read_text()
        self.assertIn("BPVRoundTime?.savedPick(item)",picks_html)
        self.assertIn("Round window", (FRONTEND/"bpv-round-times.js").read_text())

    def test_stadium_glass_exposes_background_without_hiding_text(self):
        css=(FRONTEND/"bpv-themes.css").read_text()
        self.assertIn("Stadium Glass 2 — visibly translucent",css)
        self.assertIn("rgba(30,56,67,.57)",css)
        self.assertIn("rgba(8,22,31,.46)",css)
        self.assertIn("backdrop-filter:blur(10px)",css)
        self.assertIn("stadium-round-time",css)
        self.assertIn("prefers-reduced-transparency:reduce",css)
        self.assertIn("background-attachment:fixed",css)

    def test_browser_scripts_syntax_when_node_available(self):
        executable=shutil.which("node")
        if not executable:
            self.skipTest("Node not installed")
        for script in ("bpv-round-times.js","bpv-stadium-dashboard.js"):
            p=subprocess.run([executable,"--check",str(FRONTEND/script)],
                             capture_output=True,text=True)
            self.assertEqual(p.returncode,0,p.stderr)


if __name__=="__main__":
    unittest.main()

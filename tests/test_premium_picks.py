"""Premium shortlist regression tests: fixture exactness, EAT timing and access.

The UI and prediction-engine data are intentionally kept separate.
"""
import unittest
import tempfile
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import patch

from backend import premium_picks, access


class PremiumPickTests(unittest.TestCase):
    def test_nine_curated_entries_and_reverse_fixtures(self):
        snap = premium_picks.snapshot(datetime(2026, 11, 13, 20, 25, tzinfo=premium_picks.EAT))
        rows = snap["items"]
        self.assertEqual(len(rows), 9)
        self.assertEqual([p["matchday"] for p in rows], [7, 11, 13, 20, 26, 30, 32, 1, 5])
        self.assertEqual(rows[0]["window_open_eat"], "20:40")
        self.assertEqual(rows[8]["season"], "139446")
        self.assertEqual(rows[8]["window_close_eat"], "23:25")
        self.assertEqual(rows[3]["kind"], "watch")
        self.assertEqual(rows[3]["selection"], "Win/loss pattern")
        self.assertEqual(rows[5]["fixture"], "TOT – CHE")
        self.assertEqual(rows[6]["fixture"], "CRY – AST")
        self.assertEqual(rows[7]["selection"],"BTTS / Over 2.5")
        self.assertTrue(rows[7]["edited_after_open"])
        self.assertEqual(rows[7]["revised_from"],"BRE WIN")

    def test_clock_status_and_expiry_are_eat(self):
        now = lambda h, m: datetime(2026, 11, 13, h, m, tzinfo=premium_picks.EAT)
        self.assertEqual(premium_picks.snapshot(now(20, 25))["items"][0]["status"], "upcoming")
        self.assertEqual(premium_picks.snapshot(now(20, 38))["items"][0]["status"], "soon")
        self.assertEqual(premium_picks.snapshot(now(20, 40))["items"][0]["status"], "window")
        self.assertEqual(premium_picks.snapshot(now(20, 45))["items"][0]["status"], "closed")
        self.assertEqual(premium_picks.snapshot(now(20, 45))["items"][1]["status"], "upcoming")
        self.assertEqual(premium_picks.snapshot(datetime(2026, 11, 15, 0, 0, tzinfo=premium_picks.EAT))["items"], [])


    def test_completed_score_grades_win_and_reverse_away_direction(self):
        source = [
            {"home":"Brentford", "away":"Sunderland", "ft_home":2, "ft_away":0},
            {"home":"Crystal Palace", "away":"Aston Villa", "ft_home":0, "ft_away":1},
        ]
        base = premium_picks.snapshot(datetime(2026, 11, 13, 23, 30, tzinfo=premium_picks.EAT))
        bre = next(p for p in base["items"] if p["season"]=="139445" and p["matchday"]==7)
        villa = next(p for p in base["items"] if p["matchday"]==32)
        self.assertEqual(premium_picks._grade(bre,source)["status"],"won")
        self.assertEqual(premium_picks._grade(villa,source)["status"],"won")
        self.assertIsNone(premium_picks._grade(bre,[
            {"home":"Sunderland","away":"Brentford","ft_home":0,"ft_away":2},
        ]))
        self.assertIsNone(premium_picks._grade(bre,[
            {"home":"Brentford","away":"Sunderland","ft_home":None,"ft_away":None},
        ]))

    def test_btts_and_over_are_independent_and_watch_is_not_a_bet(self):
        snap=premium_picks.snapshot(datetime(2026, 11, 13, 23, 30, tzinfo=premium_picks.EAT))
        combo=next(p for p in snap["items"] if p["matchday"]==11)
        mixed=premium_picks._grade(combo,[{
            "home":"Chelsea","away":"Tottenham Hotspur","ft_home":1,"ft_away":1,
        }])
        self.assertEqual(mixed["status"],"mixed")
        self.assertEqual(mixed["market_results"],{"btts":"WON","over_2_5":"LOST"})
        watch=next(p for p in snap["items"] if p["matchday"]==20)
        result=premium_picks._grade(watch,[{
            "home":"Crystal Palace","away":"Tottenham","ft_home":1,"ft_away":0,
        }])
        self.assertEqual(result["status"],"watch-result")
        self.assertNotIn("WON",result["result_summary"])

    def test_one_minute_grace_and_pending_if_feed_unavailable(self):
        from unittest.mock import Mock
        premium_picks._RESULTS.clear()
        premium_picks._ATTEMPTS.clear()
        feed = Mock()
        moment=lambda h,m: datetime(2026,11,13,h,m,tzinfo=premium_picks.EAT)
        early=premium_picks.attach_results(premium_picks.snapshot(moment(20,45)),feed,now=moment(20,45))
        self.assertEqual(feed.completed_premium_rounds.call_count,0)
        self.assertEqual(early["items"][0]["status"],"closed")
        feed.completed_premium_rounds.return_value = {
            ("139445",7):[{"home":"BRE","away":"SUN","ft_home":2,"ft_away":1}]
        }
        after=premium_picks.attach_results(premium_picks.snapshot(moment(20,46)),feed,now=moment(20,46))
        self.assertEqual(feed.completed_premium_rounds.call_count,1)
        self.assertEqual(after["items"][0]["ft_score"],"2–1")
        self.assertEqual(after["items"][0]["status"],"won")
        feed.completed_premium_rounds.side_effect=RuntimeError("feed offline")
        later=premium_picks.attach_results(premium_picks.snapshot(moment(21,6)),feed,now=moment(21,6))
        second=next(i for i in later["items"] if i["matchday"]==11)
        self.assertEqual(second["status"],"awaiting")
        self.assertNotIn("ft_score",second)
        premium_picks._RESULTS.clear()
        premium_picks._ATTEMPTS.clear()

    @patch("backend.premium_picks.attach_results", side_effect=lambda payload, provider: payload)
    def test_active_free_and_vip_are_separately_gated(self, _mock_attach):
        from backend import main
        from fastapi.testclient import TestClient

        api = TestClient(main.app)
        self.assertEqual(api.get("/api/premium-picks").status_code, 401)
        free_user = {"role":"client","email":"free@example.com","subscription":{"is_active":False}}
        vip_user = {"role":"client","email":"vip@example.com","subscription":{"is_active":True}}
        with patch.object(main, "_require_account", return_value=free_user):
            with patch.object(main.free_access, "active_release", return_value=None):
                self.assertEqual(api.get("/api/premium-picks").status_code, 403)
            with patch.object(main.free_access, "active_release", return_value={"id":1,"markets":["btts"]}):
                self.assertEqual(api.get("/api/premium-picks").status_code, 200)
        with patch.object(main, "_require_account", return_value=vip_user):
            self.assertEqual(api.get("/api/premium-picks").status_code, 200)
        api.close()



class PremiumAdminCrudTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.db_patch=patch.object(access,"DB",Path(self.temp.name)/"premium.sqlite")
        self.db_patch.start()
        premium_picks._RESULTS.clear()
        premium_picks._ATTEMPTS.clear()

    def tearDown(self):
        premium_picks._RESULTS.clear()
        premium_picks._ATTEMPTS.clear()
        self.db_patch.stop()
        self.temp.cleanup()

    def test_edit_current_match_and_keep_after_open_disclosure(self):
        entries=premium_picks.list_entries()
        self.assertEqual(len(entries),9)
        md1=next(p for p in entries if p["season"]=="139446" and p["matchday"]==1)
        self.assertEqual(md1["selection"],"BTTS / Over 2.5")
        self.assertEqual(md1["revised_from"],"BRE WIN")
        self.assertTrue(md1["edited_after_open"])
        data={k:md1[k] for k in ("date_eat","season","matchday","fixture","selection",
             "alarm_eat","window_open_eat","window_close_eat","enabled")}
        data["selection"]="BRE WIN"
        changed=premium_picks.save_entry(data,1,md1["id"])
        self.assertEqual(changed["selection"],"BRE WIN")
        self.assertTrue(changed["edited_after_open"])
        self.assertEqual(changed["revised_from"],"BRE WIN")
        # Store persists across independent connections; no duplicate seed.
        self.assertEqual(len(premium_picks.list_entries()),9)

    def test_admin_create_unpublish_and_republish(self):
        item={
            "date_eat":"2026-11-15","season":"139460","matchday":3,
            "fixture":"MUN – LIV","selection":"BTTS YES",
            "alarm_eat":"19:57","window_open_eat":"20:00","window_close_eat":"20:05",
            "enabled":True,
        }
        made=premium_picks.save_entry(item,1)
        self.assertEqual(len(premium_picks.list_entries()),10)
        self.assertEqual(made["kind"],"pick")
        self.assertEqual(made["selection"],"BTTS YES")
        self.assertTrue(premium_picks.toggle_entry(made["id"],1,False)["enabled"] is False)
        self.assertEqual(len(premium_picks.list_entries()),9)
        self.assertTrue(premium_picks.toggle_entry(made["id"],1,True)["enabled"])
        self.assertEqual(len(premium_picks.list_entries()),10)
        with self.assertRaisesRegex(ValueError,"already exists"):
            premium_picks.save_entry(item,1)

    def test_validation_and_grade_cached_per_selection(self):
        entry={
            "date_eat":"2026-11-15","season":"139460","matchday":3,
            "fixture":"BRE – SUN","selection":"BTTS / Over 2.5",
            "alarm_eat":"19:57","window_open_eat":"20:00","window_close_eat":"20:05",
        }
        good=premium_picks.save_entry(entry,1)
        self.assertFalse(good["edited_after_open"])
        self.assertEqual(premium_picks._grade(good,[{"home":"Brentford","away":"Sunderland",
                 "ft_home":1,"ft_away":1}])["status"],"mixed")
        item=dict(entry,fixture="BRE – BRE")
        with self.assertRaises(ValueError):
            premium_picks.save_entry(item,1)
        item=dict(entry,selection="BRE WIN")
        self.assertEqual(premium_picks._grade(item,[{"home":"Brentford","away":"Sunderland",
                 "ft_home":1,"ft_away":1}])["status"],"lost")


if __name__ == "__main__":
    unittest.main()

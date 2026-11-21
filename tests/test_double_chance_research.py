"""E011 research-only Double Chance integration and safety tests."""
import copy
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend import double_chance_research as dc
from backend import main


def round_payload():
    return {"responses": [{
        "id": "test-event-1",
        "name": "Home - Away",
        "competition": {"id": "7794"},
        "markets": [{"marketType": {"id": "4693"}, "row": [{
            "prices": [
                {"name": "1X", "odds": 1.327, "suspended": False},
                {"name": "X2", "odds": 1.835, "suspended": False},
                {"name": "12", "odds": 1.256, "suspended": False},
            ]
        }]}],
    }]}


class DoubleChanceResearchTests(unittest.TestCase):
    def collect(self, payload):
        return dc.candidates_for_round(payload, {"7794": "English"})

    def test_two_selections_same_fixture_and_correct_dc_mass(self):
        found = self.collect(round_payload())
        self.assertEqual({p["selection"] for p in found}, {"12", "1X"})
        self.assertEqual(len(found), 2)
        self.assertAlmostEqual(next(p["bookmaker_probability_pct"] for p in found if p["selection"] == "12"), 76.02, delta=0.03)
        self.assertAlmostEqual(next(p["bookmaker_probability_pct"] for p in found if p["selection"] == "1X"), 71.95, delta=0.03)
        self.assertTrue(all(p["historical_roi_pct"] < 0 for p in found))
        self.assertTrue(all(p["research_status"] == "experimental" for p in found))

    def test_missing_suspended_or_duplicate_market_fails_closed(self):
        payload = round_payload()
        payload["responses"][0]["markets"][0]["row"][0]["prices"].pop()
        self.assertEqual(self.collect(payload), [])
        payload = round_payload()
        payload["responses"][0]["markets"][0]["row"][0]["prices"][0]["suspended"] = True
        self.assertEqual(self.collect(payload), [])
        payload = round_payload()
        payload["responses"][0]["markets"][0]["row"][0]["prices"][0].pop("suspended")
        self.assertEqual(self.collect(payload), [])
        payload = round_payload()
        payload["responses"][0]["markets"].append(copy.deepcopy(payload["responses"][0]["markets"][0]))
        self.assertEqual(self.collect(payload), [])
        payload = round_payload()
        payload["responses"][0]["markets"][0]["row"][0]["prices"][1]["odds"] = 0
        self.assertEqual(self.collect(payload), [])

    def test_unauthorized_or_unavailable_quotes_never_generate_picks(self):
        payload = round_payload()
        payload["responses"][0]["competition"]["id"] = "not-listed"
        self.assertEqual(self.collect(payload), [])
        payload = round_payload()
        payload["responses"][0]["markets"][0]["row"][0]["prices"] = [
            {"name": "1X", "odds": 1.05, "suspended": False},
            {"name": "X2", "odds": 4.2, "suspended": False},
            {"name": "12", "odds": 1.1, "suspended": False},
        ]
        self.assertEqual(self.collect(payload), [])

    def test_no_result_or_prospective_success_claim(self):
        payload = round_payload()
        original = self.collect(payload)
        payload["responses"][0]["results"] = {"ft_home": 9, "ft_away": 0}
        self.assertEqual(self.collect(payload), original)
        catalog = dc.research_catalog()
        self.assertTrue(all(c["roi_pct"] < 0 for c in catalog))
        self.assertTrue(all(c["status"].startswith("experimental") for c in catalog))

    def test_recommendation_api_separates_research_from_featured_picks(self):
        context = {
            "season": "139509", "next_matchday": 11,
            "double_chance_research": self.collect(round_payload()),
        }
        with patch.object(main, "_require_account", return_value={"role": "admin"}), \
             patch.object(main.feed, "prediction_context", return_value=context), \
             patch.object(main, "build_prediction", return_value={"predictions": []}):
            with TestClient(main.app, follow_redirects=False) as client:
                res = client.get("/api/recommended-picks")
        self.assertEqual(res.status_code, 200, res.text)
        data = res.json()
        self.assertTrue(data["double_chance_access"])
        self.assertEqual(len(data["double_chance_research"]), 2)
        self.assertEqual(data["featured_predictions"], [])
        self.assertEqual(data["predictions"], [])

    def test_admin_strategy_catalog_clearly_labels_negative_roi(self):
        catalog = [p for p in main._admin_strategy_catalog()
                   if p.get("strategy_family") == "Experimental DC research"]
        self.assertEqual({x["market"] for x in catalog},
                         {"Double Chance 12", "Double Chance 1X"})
        self.assertTrue(all(x["historical_roi_pct"] < 0 for x in catalog))
        self.assertTrue(all(x["research_status"] == "experimental" for x in catalog))


if __name__ == "__main__":
    unittest.main()

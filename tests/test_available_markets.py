import unittest

from backend.private_rules import NEW_STRATEGIES, PATTERN2_STRATEGIES


class AvailableMarketTests(unittest.TestCase):
    def test_unavailable_under_45_market_is_not_configured(self):
        strategies = NEW_STRATEGIES + PATTERN2_STRATEGIES
        markets = {strategy["market"] for strategy in strategies}

        self.assertNotIn("Under 4.5 FT", markets)
        self.assertIn("Under 3.5 FT", markets)


if __name__ == "__main__":
    unittest.main()

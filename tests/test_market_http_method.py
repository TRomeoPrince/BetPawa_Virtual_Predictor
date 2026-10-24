from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class MarketHttpMethodContractTests(unittest.TestCase):
    def test_market_check_uses_post_for_prediction_endpoint(self):
        market_html = (ROOT / "frontend" / "market.html").read_text(encoding="utf-8")
        backend_main = (ROOT / "backend" / "main.py").read_text(encoding="utf-8")

        # The backend exposes this action as POST; the browser must match it.
        self.assertIn("json('/api/predict/'+page,{method:'POST'})", market_html)
        self.assertIn('@app.post("/api/predict/{category}")', backend_main)


if __name__ == "__main__":
    unittest.main()

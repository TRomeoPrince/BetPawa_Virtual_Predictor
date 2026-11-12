"""Protect the statutory responsible betting text across customer-facing pages."""
from pathlib import Path
import re
import unittest

ROOT=Path(__file__).resolve().parents[1]
PUBLIC_PAGES=(
    "index.html", "login.html", "signup.html", "purchase.html",
    "client.html", "market.html", "picks.html",
)


class ResponsibleFooterTests(unittest.TestCase):
    def test_warning_is_in_footer_of_all_customer_facing_pages(self):
        for filename in PUBLIC_PAGES:
            with self.subTest(page=filename):
                html=(ROOT/"frontend"/filename).read_text(encoding="utf-8")
                footer=re.search(r"<footer\b[^>]*>[\s\S]*?</footer>",html,re.IGNORECASE)
                self.assertIsNotNone(footer,filename+" has no footer")
                self.assertIn("You have to be 25 years and above to bet.",footer.group(0))
                self.assertIn("Betting is addictive and can be psychologically harmful.",footer.group(0))
                self.assertIn("Responsible betting and age warning",footer.group(0))

    def test_independent_publisher_disclaimer_preserved(self):
        home=(ROOT/"frontend"/"index.html").read_text(encoding="utf-8")
        self.assertIn("Not affiliated with or endorsed by betPawa",home)
        self.assertIn("Predictions are informational, not betting advice or guaranteed outcomes.",home)


if __name__=="__main__":
    unittest.main()

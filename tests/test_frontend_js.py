"""Syntax-check inline frontend JavaScript when Node.js is available."""
import re
import shutil
import subprocess
import unittest
from pathlib import Path


FRONTEND = Path(__file__).resolve().parent.parent / "frontend"


@unittest.skipUnless(shutil.which("node"), "Node.js not installed")
class FrontendSyntaxTests(unittest.TestCase):
    def test_inline_scripts_parse(self):
        for page in sorted(FRONTEND.glob("*.html")):
            scripts = re.findall(
                r"<script(?:\s[^>]*)?>([\s\S]*?)</script>",
                page.read_text(encoding="utf-8"), flags=re.IGNORECASE,
            )
            for index, script in enumerate(scripts):
                if not script.strip():
                    continue
                with self.subTest(page=page.name, script=index):
                    check = subprocess.run(
                        ["node", "--check"], input=script, text=True,
                        capture_output=True, timeout=15, check=False,
                        encoding="utf-8", errors="replace",
                    )
                    self.assertEqual(check.returncode, 0, check.stderr)


if __name__ == "__main__":
    unittest.main()

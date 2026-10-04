"""Node executes actual browser handler code against a deterministic DOM harness."""
from pathlib import Path
import shutil
import subprocess
import unittest


class FrontendRequestTests(unittest.TestCase):
    def test_request_races(self):
        node = shutil.which("node")
        self.assertIsNotNone(node, "Node.js is required for frontend request regression tests")
        completed = subprocess.run(
            [node, "--test", str(Path(__file__).with_name("frontend_requests.test.cjs"))],
            capture_output=True, timeout=30, encoding="utf-8", errors="replace",
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)

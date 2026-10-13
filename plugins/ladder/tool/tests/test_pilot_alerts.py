"""Alerts pilot fixes. Run: python3 -m unittest discover plugins/ladder/tool/tests
- replay: a :time mask writes the time relative to the request (now+0m), not "<not a time>" (since v0.6.4 the echo
  masking replaced the field's own value first, so no time field was ever compared);
- replay: a path written with a space (a route parameter like a group name) is percent-encoded, not a crash."""
import contextlib
import io
import json
import sys
import tempfile
import threading
import unittest
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ladder_extra as X  # noqa: E402


class Handler(BaseHTTPRequestHandler):
    seen: list = []

    def _answer(self):
        Handler.seen.append(self.path)
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        body = json.dumps({"timestamp": now, "message": f"filed at {now}", "path": self.path}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    do_GET = _answer

    def log_message(self, *a):
        pass


class ReplayMasksAndPaths(unittest.TestCase):
    def setUp(self):
        Handler.seen = []
        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def run_replay(self, path, *extra):
        d = Path(tempfile.mkdtemp())
        (d / "s.json").write_text(json.dumps({"requests": [{"step": "x", "method": "GET", "path": path}]}))
        with contextlib.redirect_stdout(io.StringIO()) as out:
            X.replay([str(d / "s.json"), "--base", self.base, "--out", str(d / "traces" / "b"), *extra])
        lines = (d / "traces" / "b" / "s.jsonl").read_text().splitlines()
        exit_ = next(json.loads(l) for l in lines if json.loads(l)["ev"] == "exit")
        return json.loads(exit_["data"]), out.getvalue()

    def test_time_mask_writes_the_relative_time(self):
        got, said = self.run_replay("/a", "--mask", "timestamp:time")
        self.assertEqual(got["body"]["timestamp"], "now+0m")
        self.assertEqual(got["body"]["message"], "filed at now+0m")       # the echo, in its masked form
        self.assertNotIn("not a time", said)

    def test_a_time_mask_on_a_non_time_is_reported(self):
        _, said = self.run_replay("/a", "--mask", "message:time")
        self.assertIn("were not date-times", said)

    def test_path_with_a_space_is_encoded(self):
        got, _ = self.run_replay("/groups/Ladder Group/alerts?division=GW")
        self.assertEqual(Handler.seen, ["/groups/Ladder%20Group/alerts?division=GW"])
        self.assertEqual(got["status"], 200)


if __name__ == "__main__":
    unittest.main()

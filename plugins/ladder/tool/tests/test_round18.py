"""Round 18 fix (alert push trial). Run: python3 -m unittest discover plugins/ladder/tool/tests
- replay never writes a signed token (JWT) to a trace unless --keep-tokens is given; --jwt still records the claims."""
import base64
import contextlib
import io
import json
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ladder_extra as X  # noqa: E402

b64 = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")
TOKEN = f"{b64({'alg': 'HS256', 'typ': 'JWT'})}.{b64({'EmployeeId': '961', 'iat': 1, 'exp': 3601})}.c2lnbmF0dXJlLXNpZ25hdHVyZQ"


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        body = json.dumps({"token": TOKEN, "note": f"Bearer {TOKEN}"}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


class ReplayHidesTokens(unittest.TestCase):
    def setUp(self):
        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()

    def run_replay(self, *extra):
        d = Path(tempfile.mkdtemp())
        (d / "s.json").write_text(json.dumps({"requests": [{"step": "login", "method": "POST", "path": "/login", "body": {}}]}))
        with contextlib.redirect_stdout(io.StringIO()) as out:
            X.replay([str(d / "s.json"), "--base", self.base, "--out", str(d / "traces" / "b"), *extra])
        return (d / "traces" / "b" / "s.jsonl").read_text(), out.getvalue()

    def test_tokens_are_hidden_by_default(self):
        trace, said = self.run_replay()
        self.assertNotIn("eyJ", trace)
        self.assertIn("<token>", trace)
        self.assertIn("signed tokens", said)

    def test_jwt_records_claims(self):
        trace, _ = self.run_replay("--jwt")
        self.assertIn("EmployeeId", trace)
        self.assertNotIn(TOKEN, trace)

    def test_keep_tokens_keeps_them(self):
        trace, _ = self.run_replay("--keep-tokens")
        self.assertIn("eyJ", trace)


if __name__ == "__main__":
    unittest.main()

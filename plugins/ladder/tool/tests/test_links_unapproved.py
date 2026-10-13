"""A step calling into a step its own project has not approved is told so (round 9: the scanner was stamped calling
auth's two new routes, which no stamp covered, and check said nothing). Run: python3 -m unittest discover
plugins/ladder/tool/tests"""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ladder as L  # noqa: E402

API = "[api.1] Answer the alerts\n  in: GET /alerts\n  out: the alerts\n  > answers the alerts\n"
CLIENT = "[c.1] Load the alerts\n  in: nothing\n  out: the alerts\n  calls: api [api.1]\n  > loads them\n"


def projects(root: Path) -> tuple[Path, Path]:
    for name, tree, extra in (("api", API, {}), ("client", CLIENT, {"links": {"api": "../api/ladder.json"}})):
        d = root / name
        d.mkdir()
        (d / f"{name}.ladder").write_text(tree)
        (d / "x.ts").write_text("")
        (d / "ladder.json").write_text(json.dumps({"title": name, "tree": f"{name}.ladder", **extra,
                                                   "builds": [{"name": "x", "lang": "typescript", "files": ["x.ts"]}]}))
    return root / "api" / "ladder.json", root / "client" / "ladder.json"


def unapproved(pj):
    return [w["node"] for w in L.check(pj)["warnings"] if w["kind"] == "linked-unapproved"]


class Unapproved(unittest.TestCase):
    def test_calls_into_an_unapproved_step_warn_until_it_is_stamped(self):
        with tempfile.TemporaryDirectory() as d:
            api, client = projects(Path(d))
            self.assertEqual(unapproved(client), ["c.1"])
            with contextlib.redirect_stdout(io.StringIO()):
                L.stamp(api)
            self.assertEqual(unapproved(client), [])
            (api.parent / "api.ladder").write_text(API.replace("answers the alerts", "answers the active alerts"))
            self.assertEqual(unapproved(client), ["c.1"])


if __name__ == "__main__":
    unittest.main()

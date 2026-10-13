"""Replay masks reach every copy of a masked value and apply at compare time, and an approved change of behaviour can
become the reference (round 9: an incident number inside a message shifted every later result; changing the mask meant
re-recording old commits; after an intended change check failed forever). Run: python3 -m unittest discover
plugins/ladder/tool/tests"""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import ladder as L  # noqa: E402
import ladder_extra as X  # noqa: E402
import sample  # noqa: E402

COMPARE = {"reference": "original", "runs": ["*"]}
BUILDS = [{"name": "code", "lang": "typescript", "mode": "literal", "files": ["code.ts"], "steps": ["s.*"], "traces": "original"},
          {"name": "original", "lang": "typescript", "tagged": False, "files": ["code.ts"]},
          {"name": "after", "lang": "typescript", "tagged": False, "files": ["code.ts"]}]


def ok(rep):
    return all(b["ok"] for run in rep["compare"] for b in run["builds"])


class Masks(unittest.TestCase):
    def test_a_long_masked_value_is_masked_inside_other_text_too(self):
        got = X._mask_echoes({"token": "abc123xyz", "msg": "your token abc123xyz expired", "id": 7, "n": "7 items"},
                             {"token": "value", "id": "value"})
        self.assertEqual(got["msg"], "your token <token> expired")
        self.assertEqual(got["n"], "7 items")     # short values are not echoed: too likely to occur by chance

    def test_text_masks_apply_to_both_sides_at_compare_time(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            pj = sample.make(root, builds=BUILDS, compare=COMPARE)
            sample.trace(root, "original", "r1", {"s.1": "incident (#1) filed"})
            sample.trace(root, "after", "r1", {"s.1": "incident (#2) filed"})
            self.assertFalse(ok(L.check(pj)))
            (root / "traces" / "original" / ".replay.json").write_text(json.dumps({"mask_text": []}))
            (root / "traces" / "after" / ".replay.json").write_text(json.dumps({"mask_text": [r"incident \(#\d+\)=incident (#<n>)"]}))
            self.assertTrue(ok(L.check(pj)))        # the newer recording's pattern masks the older one too
            self.assertEqual([w for w in L.check(pj)["warnings"] if w["kind"] == "replay-settings"], [])


class Reference(unittest.TestCase):
    def test_an_approved_run_becomes_the_reference_and_the_old_one_is_kept(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            pj = sample.make(root, builds=BUILDS, compare=COMPARE)
            sample.trace(root, "original", "r1", {"s.1": 500})
            sample.trace(root, "after", "r1", {"s.1": 200})
            self.assertFalse(ok(L.check(pj)))
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(L.make_reference(pj, "after"), 0)
            self.assertTrue(ok(L.check(pj)))
            old = list((root / "traces" / "history").glob("original-*/r1.jsonl"))
            self.assertEqual(len(old), 1)
            self.assertIn("500", old[0].read_text())
            self.assertEqual([w for w in L.check(pj)["warnings"] if w["kind"] == "traces-unused"], [])


if __name__ == "__main__":
    unittest.main()

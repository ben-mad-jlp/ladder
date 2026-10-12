"""A replay comparison in which no build has its own traces compares nothing, and must say so (round 9: every tagged
build shared the reference's traces, a second recording sat in a folder no build named, and check said "code and
comparison are fine"). Run: python3 -m unittest discover plugins/ladder/tool/tests"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import ladder as L  # noqa: E402
import sample  # noqa: E402

COMPARE = {"reference": "original", "runs": ["*"]}


def builds(*extra):
    return [{"name": "code", "lang": "typescript", "mode": "literal", "files": ["code.ts"], "steps": ["s.*"], "traces": "original"},
            {"name": "original", "lang": "typescript", "tagged": False, "files": ["code.ts"]}, *extra]


class NothingCompared(unittest.TestCase):
    def test_shared_traces_only_compare_nothing_and_an_unnamed_folder_is_reported(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            pj = sample.make(root, builds=builds(), compare=COMPARE)
            sample.trace(root, "original", "r1", {"s.1": 2})
            sample.trace(root, "original-2", "r1", {"s.1": 3})   # a second recording no build names
            rep = L.check(pj)
            self.assertTrue(rep["nothing_compared"])
            self.assertFalse(rep["compared"])
            self.assertEqual([w["node"] for w in rep["warnings"] if w["kind"] == "traces-unused"], ["traces/original-2"])

    def test_a_recording_named_as_a_build_is_compared(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            pj = sample.make(root, builds=builds({"name": "original-2", "lang": "typescript", "tagged": False, "files": ["code.ts"]}),
                             compare=COMPARE)
            sample.trace(root, "original", "r1", {"s.1": 2})
            sample.trace(root, "original-2", "r1", {"s.1": 3})
            rep = L.check(pj)
            self.assertFalse(rep["nothing_compared"])
            self.assertFalse(all(b["ok"] for run in rep["compare"] for b in run["builds"]))   # 3 vs 2: different
            self.assertEqual([w for w in rep["warnings"] if w["kind"] == "traces-unused"], [])


if __name__ == "__main__":
    unittest.main()

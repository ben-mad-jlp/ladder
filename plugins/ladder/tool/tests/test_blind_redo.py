"""`regen --blind --redo=IDS` rewrites only the regions of those steps (round 9: adding two steps to a stamped tree,
`--blind --redo=emp.9,emp.10` rewrote all ten approved regions of the file). Run: python3 -m unittest discover
plugins/ladder/tool/tests"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import ladder as L  # noqa: E402
import regen as R  # noqa: E402
import sample  # noqa: E402


def code(h1, h2):
    return (f"// @node s.1@{h1}\nexport const addOne = (n: number) => n + 1\n// @end\n"
            f"// @node s.2@{h2}\nexport const double = (n: number) => n * 2\n// @end\n")


class BlindRedo(unittest.TestCase):
    def run_blind(self, redo):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            pj = sample.make(root)
            cfg, root, tree, lock, _ = L.load_project(pj)
            (root / "code.ts").write_text(code(tree["s.1"].hash, tree["s.2"].hash))
            log = root / "log"
            (log / "cwd").mkdir(parents=True)
            R.REDO.clear()
            R.REDO.update(redo)
            try:
                out = R.regen_blind(cfg, root, tree, lock, cfg["builds"][0], ["true"], log, dry_run=True)
            finally:
                R.REDO.clear()
            return [k for _, k, msg in out if msg.startswith("dry run")]

    def test_redo_limits_a_blind_run_to_the_named_steps(self):
        self.assertEqual(self.run_blind({"s.2"}), ["node s.2"])

    def test_without_redo_a_blind_run_rewrites_every_region(self):
        self.assertEqual(sorted(self.run_blind(set())), ["node s.1", "node s.2"])


if __name__ == "__main__":
    unittest.main()

"""A project's own behaviour tests are run by `ladder test`, recorded, and go stale when the code they test changes;
an identical command is run once however many subjects name it (round 9: the slice's tests ran by hand, unrecorded;
one link test named by five subjects ran five times). Run: python3 -m unittest discover plugins/ladder/tool/tests"""
import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import ladder as L  # noqa: E402
import ladder_links as K  # noqa: E402
import sample  # noqa: E402


def kinds(rep, kind):
    return [w["node"] for w in rep["warnings"] + [p for b in rep["builds"] for p in b["problems"]] if w["kind"] == kind]


class ProjectTests(unittest.TestCase):
    def test_recorded_then_stale_when_the_code_changes(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            # the command appends to ran.txt without naming it (a file a command names is part of what it tests)
            pj = sample.make(root, extra={"tests": [{"name": "unit", "command": "echo one >> \"$(printf ran).txt\""},
                                                    {"name": "again", "command": "echo one >> \"$(printf ran).txt\""}]})
            self.assertEqual(kinds(L.check(pj), "test-not-run"), ["tests unit", "tests again"])
            with contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(K.run_tests(pj), 0)
            self.assertIn("same command as above, not run again", out.getvalue())
            self.assertEqual((root / "ran.txt").read_text(), "one\n")          # ran once
            rep = L.check(pj)
            self.assertEqual(kinds(rep, "test-not-run") + kinds(rep, "test-stale"), [])
            (root / "code.ts").write_text("export const x = 2\n")
            self.assertEqual(kinds(L.check(pj), "test-stale"), ["tests unit", "tests again"])

    def test_a_project_without_tests_is_told(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(kinds(L.check(sample.make(Path(d))), "untested-project"), ["tests"])


if __name__ == "__main__":
    unittest.main()

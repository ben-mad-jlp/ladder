"""A client relies on everything the called step's English refers to (round 8: a refusal added three steps below
the endpoint reached no client). Run: python3 -m unittest discover plugins/ladder/tool/tests"""
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ladder as L  # noqa: E402
import ladder_links as K  # noqa: E402

TREE = textwrap.dedent("""\
    [ep.1] Create an alert
      in: POST /alerts
      out: what [act.1] answers

    [act.1] Run the creation
      > answers 200 with [svc.1]

    [svc.1] Make the alert
      > checks the name with [svc.2]

    [svc.2] Check a name
      > refuses a name longer than 50 characters

    [other.1] Unrelated
      > nothing
    """)


class Behind(unittest.TestCase):
    def test_transitive_references_with_paths(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "t.ladder"
            p.write_text(TREE)
            tree = L.parse_tree(p)
            paths = K.behind(tree, "ep.1")
            self.assertEqual(set(paths), {"act.1", "svc.1", "svc.2"})
            self.assertEqual(paths["svc.2"], ["ep.1", "act.1", "svc.1", "svc.2"])
            self.assertNotIn("other.1", paths)

    def test_hashes_change_when_a_deep_step_changes(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "t.ladder"
            p.write_text(TREE)
            before = K.behind_hashes(L.parse_tree(p), "ep.1")
            p.write_text(TREE.replace("longer than 50", "longer than 40"))
            after = K.behind_hashes(L.parse_tree(p), "ep.1")
            self.assertEqual([x for x in before if before[x] != after[x]], ["svc.2"])


if __name__ == "__main__":
    unittest.main()

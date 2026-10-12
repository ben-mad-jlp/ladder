"""The generator sees every data block the steps it writes name, not only the build's "data" list
(round 8: a container build listed no data, its step named MyAlertsSnapshot, and the prompt's data section was
empty). Run: python3 -m unittest discover plugins/ladder/tool/tests"""
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ladder as L  # noqa: E402
import regen  # noqa: E402

TREE = textwrap.dedent("""\
    data Snapshot
      rowCount: whole number
      selection: the selected row, or null

    data Unrelated
      x: text

    [s.1] Report the screen to the assistant
      out: a Snapshot
      > the snapshot has the row count and the selection
    """)


class PromptData(unittest.TestCase):
    def test_named_block_is_shown_without_a_data_list(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "t.ladder"
            p.write_text(TREE)
            tree = L.parse_tree(p)
            regen.CTX.update(tree=tree, vocab={}, root=None, lock={}, schemas={})
            text = regen.context_text({"name": "b", "lang": "typescript", "steps": ["s.*"], "data": []}, ["s.1"])
            self.assertIn("data Snapshot", text)
            self.assertIn("selection", text)
            self.assertNotIn("data Unrelated", text)


if __name__ == "__main__":
    unittest.main()

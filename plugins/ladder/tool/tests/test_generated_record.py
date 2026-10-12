"""Code generated in a checkout stays recognised as generated after the committed records are replaced by a sync
(round 8: syncing the English into a scratch copy with git overwrote ladder.code.json, so regen there refused its
own generated code as hand edits). Run: python3 -m unittest discover plugins/ladder/tool/tests"""
import json
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ladder as L  # noqa: E402

CODE = textwrap.dedent("""\
    // @node s.1@aaaaaa
    export function one() { return 1 }
    // @end
    """)


class GeneratedRecord(unittest.TestCase):
    def test_generated_code_is_not_a_hand_edit_after_the_record_is_replaced(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "a.ts").write_text(CODE)
            cfg = {"builds": [{"name": "b", "lang": "typescript", "files": ["a.ts"]}]}
            b = cfg["builds"][0]
            L.record_code(root, cfg)                          # approved: returns 1
            before = L.snapshot(root, cfg)
            (root / "a.ts").write_text(CODE.replace("return 1", "return 2"))
            L.record_code(root, cfg, before=before)           # what regen does after writing
            self.assertTrue((root / ".ladder" / ".gitignore").exists())
            # a sync from the working tree brings back the approved record (return 1)
            (root / L.CODE_FILE).write_text(json.dumps({"b": {"a.ts": {"node s.1": L.code_fingerprints(root, b)["a.ts"]["node s.1"][0] + "x"}}}))
            self.assertEqual(L.hand_edited(root, b), [])      # still recognised: generated here
            (root / "a.ts").write_text(CODE.replace("return 1", "return 3"))   # a real hand edit
            self.assertEqual(len(L.hand_edited(root, b)), 1)


if __name__ == "__main__":
    unittest.main()

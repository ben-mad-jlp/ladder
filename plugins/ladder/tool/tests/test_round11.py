"""Round 11 fixes (employee mail trial). Run: python3 -m unittest discover plugins/ladder/tool/tests
- a changed rule names the steps that cite it (rule-changed), and a rule's value in support code is warned;
- a `@contract rule <name>` region follows the rule's text;
- blind prompts name a hidden region's exported names."""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ladder as L  # noqa: E402
import regen as R  # noqa: E402

TREE = """rule message limit: a message holds at most {n} characters

[c.1] Type the message
  > text past the limit (rule message limit) is ignored

[c.2] Show the screen
  > shows it
"""


def project(root: Path, n: int, code: str) -> Path:
    (root / "t.ladder").write_text(TREE.format(n=n))
    (root / "a.ts").write_text(code)
    pj = root / "ladder.json"
    pj.write_text(json.dumps({"title": "t", "tree": "t.ladder",
                              "builds": [{"name": "a", "lang": "typescript", "files": ["a.ts"], "data": []}]}))
    return pj


def kinds(rep, kind):
    return [p for p in rep["tree"] if p["kind"] == kind] + [w for w in rep["warnings"] if w["kind"] == kind]


class Rules(unittest.TestCase):
    def test_rule_in_support_then_rule_changed_and_the_rule_region(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            pj = project(root, 5000, "")
            tree = L.parse_tree(root / "t.ladder")
            h1, h2 = tree["c.1"].hash, tree["c.2"].hash
            (root / "a.ts").write_text(f"// @support limit\nconst MAX = 5000\n// @end\n// @node c.1@{h1}\nconst f = 1\n// @end\n"
                                       f"// @node c.2@{h2}\nconst g = 2\n// @end\n")
            self.assertEqual(len(kinds(L.check(pj), "rule-in-support")), 1)
            # as a rule region it follows the rule: no warning, and it goes stale when the rule changes
            rh = L.region_contract_hash(tree, None, [], "rule message limit")
            self.assertTrue(rh.startswith("r"))
            (root / "a.ts").write_text((root / "a.ts").read_text().replace("// @support limit", f"// @contract rule message limit@{rh}"))
            self.assertEqual(kinds(L.check(pj), "rule-in-support"), [])
            with contextlib.redirect_stdout(io.StringIO()):
                L.stamp(pj)
            (root / "t.ladder").write_text(TREE.format(n=2000))
            rep = L.check(pj)
            self.assertEqual([p["node"] for p in kinds(rep, "rule-changed")], ["c.1"])
            self.assertTrue(any(p["kind"] == "stale-contract" for b in rep["builds"] for p in b["problems"]))


class PublicNames(unittest.TestCase):
    def test_a_hidden_regions_exports_are_named(self):
        lines = ["// @node c.1@000000", "export interface Props { a: number }", "export function Show() {}", "// @end"]
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "a.ts"
            f.write_text("\n".join(lines) + "\n")
            regions, _, ls, _ = L.parse_regions(f, "typescript")
            note = R.public_names_note(regions, ls, 0, "typescript")
            self.assertIn("Props, Show", note)


if __name__ == "__main__":
    unittest.main()

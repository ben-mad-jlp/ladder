"""Round 10 fixes (Unpick Shipment trial). Run: python3 -m unittest discover plugins/ladder/tool/tests
- contract-misplaced: a labelled @contract region that declares no type, or a block another region's label names
  (blind generation wrote three DTOs into one file; repair emptied the right one; check said ok);
- the contract prompt names the blocks the region holds and where the others live;
- split-step: a step tagged in two regions is written twice by regeneration;
- baseline: a tree that did not exist at a known baseline commit is a first transcription, not a problem;
- binding-not-called: another build of the project that makes the call counts;
- ladder tag writes marker lines from a regions file, comments only;
- replay "raw" bodies."""
import contextlib
import io
import json
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ladder as L  # noqa: E402
import ladder_extra as X  # noqa: E402
import regen as R  # noqa: E402

TREE = textwrap.dedent("""\
    data Order
      id: whole number
      lines: list of OrderLine

    data OrderLine
      sku: text

    [o.1] Read an order
      in: an id
      out: Order
      uses: errors
      > answers the order

    [o.2] Save an order
      in: Order
      out: nothing
      > saves it
    """)

VOCAB = textwrap.dedent("""\
    capability errors
      in: a failure
      out: the error answer
      csharp: (in repository) Errors.cs | throw new ArgumentException("<message>")
    """)


def project(root: Path, order_code: str, line_code: str, svc_code: str = "", ctl_code: str = "") -> Path:
    (root / "o.ladder").write_text(TREE)
    (root / "vocabulary.ladder").write_text(VOCAB)
    (root / "Errors.cs").write_text("// the middleware\n")
    (root / "Order.cs").write_text(order_code)
    (root / "OrderLine.cs").write_text(line_code)
    builds = [{"name": "dtos", "lang": "csharp", "files": ["Order.cs", "OrderLine.cs"], "steps": [],
               "data": ["Order", "OrderLine"]}]
    if svc_code or ctl_code:
        (root / "Svc.cs").write_text(svc_code)
        (root / "Ctl.cs").write_text(ctl_code)
        builds += [{"name": "svc", "lang": "csharp", "files": ["Svc.cs"], "steps": ["o.2"], "data": []},
                   {"name": "ctl", "lang": "csharp", "files": ["Ctl.cs"], "steps": ["o.1"], "data": []}]
    pj = root / "ladder.json"
    pj.write_text(json.dumps({"title": "o", "tree": "o.ladder", "vocabulary": "vocabulary.ladder", "builds": builds}))
    return pj


def kinds(rep, kind):
    return [p for b in rep["builds"] for p in b["problems"] if p["kind"] == kind] + \
           [w for w in rep["warnings"] if w["kind"] == kind] + [t for t in rep["tree"] if t["kind"] == kind]


GOOD_ORDER = "// @contract Order@000000\npublic class OrderDto { public int Id; public List<OrderLineDto> Lines; }\n// @end\n"
GOOD_LINE = "// @contract OrderLine@000000\npublic class OrderLineDto { public string Sku; }\n// @end\n"


class ContractLayout(unittest.TestCase):
    def test_each_labelled_region_holds_its_own_type(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(kinds(L.check(project(Path(d), GOOD_ORDER, GOOD_LINE)), "contract-misplaced"), [])

    def test_a_type_written_into_another_blocks_region_and_an_empty_region_are_reported(self):
        both = GOOD_ORDER.replace("// @end\n", "public class OrderLineDto { public string Sku; }\n// @end\n")
        empty = "// @contract OrderLine@000000\n// (declared elsewhere)\n// @end\n"
        with tempfile.TemporaryDirectory() as d:
            found = kinds(L.check(project(Path(d), both, empty)), "contract-misplaced")
            msgs = " | ".join(p["msg"] for p in found)
            self.assertEqual(len(found), 2, msgs)
            self.assertIn("declares OrderLine, which belongs to the region", msgs)
            self.assertIn("declares no type", msgs)

    def test_a_type_named_differently_from_its_block_is_fine(self):
        other = GOOD_LINE.replace("OrderLineDto", "LineOfOrderProps")
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(kinds(L.check(project(Path(d), GOOD_ORDER, other)), "contract-misplaced"), [])

    def test_the_contract_prompt_says_what_the_region_holds_and_where_the_others_are(self):
        with tempfile.TemporaryDirectory() as d:
            pj = project(Path(d), GOOD_ORDER, GOOD_LINE)
            cfg, root, tree, *_ = L.load_project(pj)
            R.set_context(cfg, root, tree)
            b = cfg["builds"][0]
            regions, _, lines, _ = L.parse_regions(root / "Order.cs", "csharp")
            prompt = R.contract_prompt(b, "Order.cs", lines, regions[0], tree, "")
            self.assertIn("This region holds only the type(s) for: Order.", prompt)
            self.assertIn("OrderLine in OrderLine.cs", prompt)


class SplitStep(unittest.TestCase):
    def test_a_step_in_two_regions_is_warned(self):
        svc = "// @node o.2@000000\nvoid Save() {}\n// @end\n// @support x\nint y;\n// @end\n// @node o.2@000000\nvoid Helper() {}\n// @end\n"
        with tempfile.TemporaryDirectory() as d:
            found = kinds(L.check(project(Path(d), GOOD_ORDER, GOOD_LINE, svc, "// @node o.1@000000\nx();\n// @end\n")), "split-step")
            self.assertEqual([w["node"] for w in found], ["o.2"])


class BindingNotCalled(unittest.TestCase):
    def test_another_build_of_the_project_making_the_call_counts(self):
        ctl = "// @node o.1@000000\nreturn Ok(svc.Read());\n// @end\n"
        uses = TREE.replace("  > saves it", "  uses: errors\n  > saves it")
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            svc_calls = "// @node o.2@000000\nthrow new ArgumentException(\"no\");\n// @end\n"
            pj = project(root, GOOD_ORDER, GOOD_LINE, svc_calls, ctl)
            (root / "o.ladder").write_text(uses)
            self.assertEqual(kinds(L.check(pj), "binding-not-called"), [])
            (root / "Svc.cs").write_text("// @node o.2@000000\nreturn;\n// @end\n")
            self.assertEqual(sorted(w["node"] for w in kinds(L.check(pj), "binding-not-called")), ["o.1", "o.2"])


def git(root: Path, *args):
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


class Baseline(unittest.TestCase):
    def test_a_tree_new_since_a_known_commit_is_not_a_problem(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            git(root, "init", "-q")
            git(root, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "base")
            pj = project(root, GOOD_ORDER, GOOD_LINE)
            cfg = json.loads(pj.read_text())
            cfg["baseline"] = "HEAD"
            pj.write_text(json.dumps(cfg))
            rep = L.check(pj)
            self.assertEqual(kinds(rep, "baseline"), [])
            self.assertEqual(len(kinds(rep, "baseline-new")), 1)
            cfg["baseline"] = "no-such-ref"
            pj.write_text(json.dumps(cfg))
            self.assertEqual(len(kinds(L.check(pj), "baseline")), 1)


class Tag(unittest.TestCase):
    def test_tag_adds_marker_lines_only_with_the_trees_hashes(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            git(root, "init", "-q")
            pj = project(root, "namespace N\n{\n    public class OrderDto { }\n}\n", "public class OrderLineDto { }\n",
                         "using X;\nvoid Save()\n{\n}\n", "x();\n")
            git(root, "add", "-A")
            git(root, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "untagged")
            spec = {"Order.cs": [[1, 2, "support namespace"], [3, 3, "contract Order"], [4, 4, "support end"]],
                    "Svc.cs": [[1, 1, "support usings"], [2, 4, "node o.2"]]}
            (root / "regions.json").write_text(json.dumps(spec))
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(X.tag([str(pj), str(root / "regions.json")]), 0)
            cfg, root2, tree, *_ = L.load_project(pj)
            svc = (root / "Svc.cs").read_text()
            self.assertIn(f"// @node o.2@{tree['o.2'].hash}\nvoid Save()", svc)
            self.assertIn("    // @contract Order@", (root / "Order.cs").read_text())
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(X.adopt_check([str(pj)]), 0)
                # re-running rebuilds from the base: the same result, no doubled markers
                X.tag([str(pj), str(root / "regions.json")])
            self.assertEqual((root / "Svc.cs").read_text(), svc)


class NewTopLevelStep(unittest.TestCase):
    def test_a_new_top_level_step_is_found_missing_and_gets_an_insert_prompt(self):
        tree_text = TREE.replace("  > saves it", "  > checks it ([o.3]), then saves it") + \
            "\n[o.3] Check an order\n  in: Order\n  out: nothing\n  > checks it\n"
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            svc = "// @node o.2@000000\nvoid Save() {}\n// @end\n"
            pj = project(root, GOOD_ORDER, GOOD_LINE, svc, "// @node o.1@000000\nx();\n// @end\n")
            (root / "o.ladder").write_text(tree_text)
            cfg = json.loads(pj.read_text())
            cfg["builds"][1]["steps"] = ["o.2", "o.3"]
            pj.write_text(json.dumps(cfg))
            cfg, root, tree, *_ = L.load_project(pj)
            R.set_context(cfg, root, tree)
            b = cfg["builds"][1]
            self.assertEqual(R.find_missing(b, root, tree), ["o.3"])
            lines = (root / "Svc.cs").read_text().splitlines()
            prompt = R.insert_prompt(b, "Svc.cs", lines, 3, tree["o.3"], tree["o.2"], tree, None)
            self.assertIn("This build's top-level steps, in order:", prompt)
            self.assertIn("[o.3] Check an order   <- NEW", prompt)
            self.assertIn("Steps whose English uses it: [o.2]", prompt)


class ReferenceRetire(unittest.TestCase):
    def test_retire_moves_old_recordings_to_history_and_drops_their_builds(self):
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import sample
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            builds = [{"name": "code", "lang": "typescript", "files": ["code.ts"], "traces": "original"},
                      {"name": "original", "lang": "typescript", "tagged": False, "files": ["code.ts"]},
                      {"name": "new", "lang": "typescript", "tagged": False, "files": ["code.ts"]},
                      {"name": "old-scratch", "lang": "typescript", "tagged": False, "files": ["code.ts"]}]
            pj = sample.make(root, builds=builds, compare={"reference": "original", "runs": ["*"]})
            for f, v in (("original", 1), ("new", 2), ("old-scratch", 1)):
                sample.trace(root, f, "r1", {"s.1": v})
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(L.make_reference(pj, "new", ["old-scratch"]), 0)
            names = [b["name"] for b in json.loads(pj.read_text())["builds"]]
            self.assertNotIn("old-scratch", names)
            self.assertFalse((root / "traces" / "old-scratch").exists())
            hist = sorted(p.name.rsplit("-", 2)[0] for p in (root / "traces" / "history").iterdir())
            self.assertEqual(hist, ["old-scratch", "original"])


if __name__ == "__main__":
    unittest.main()

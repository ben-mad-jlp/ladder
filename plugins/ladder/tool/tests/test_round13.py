"""Round 13 fixes (scanner scale trial). Run: python3 -m unittest discover plugins/ladder/tool/tests
- a step's tag hash covers the rules it cites: code generated under another version of a rule is stale, also after
  the rule is changed back; tags written before v0.6.8 still hold while the rules are as approved;
- check warns when a rule's value sits in the code of a step that does not cite the rule (rule-uncited);
- stamp refuses while a region is stale;
- a trace without step results ("ev": "exit") says so instead of "no trace for this run";
- --help prints the usage on every command."""
import contextlib
import io
import json
import tempfile
import textwrap
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ladder as L  # noqa: E402


def tree_text(limit: int, cite_both: bool) -> str:
    return textwrap.dedent(f"""\
        rule weight range: a weight is from 0 to {limit}, both included

        [p.1] Read the generic format
          out: a weight
          > outside the weight range (rule weight range): not valid

        [p.2] Read the Avery format
          out: a weight
          > outside the weight range{" (rule weight range)" if cite_both else ""}: not valid
        """)


def project(root: Path, limit: int = 1000, cite_both: bool = False) -> Path:
    (root / "t.ladder").write_text(tree_text(limit, cite_both))
    pj = root / "ladder.json"
    pj.write_text(json.dumps({"title": "t", "tree": "t.ladder",
                              "builds": [{"name": "a", "lang": "typescript", "files": ["a.ts"], "steps": ["p.*"]}]}))
    return pj


def write_code(root: Path, limit: int) -> None:
    _, _, tree, _, _ = L.load_project(root / "ladder.json")
    (root / "a.ts").write_text(
        f"// @node p.1@{tree['p.1'].hash}\nexport function g(w: number) {{ return w <= {limit}; }}\n// @end\n"
        f"// @node p.2@{tree['p.2'].hash}\nexport function a(w: number) {{ return w <= {limit}; }}\n// @end\n")


def quiet(fn, *a, **k):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        r = fn(*a, **k)
    return r, out.getvalue()


def kinds(pj: Path) -> list[str]:
    rep = L.check(pj)
    return [p["kind"] for b in rep["builds"] for p in b.get("problems", [])] + [w["kind"] for w in rep["warnings"]]


class RuleInHash(unittest.TestCase):
    def test_rule_text_is_part_of_the_hash_of_citing_steps_only(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            _, _, t1, _, _ = L.load_project(project(root, 1000))
            _, _, t2, _, _ = L.load_project(project(root, 500))
            self.assertNotEqual(t1["p.1"].hash, t2["p.1"].hash)
            self.assertEqual(t1["p.2"].hash, t2["p.2"].hash)   # does not cite the rule

    def test_code_generated_under_a_reverted_rule_is_stale(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            pj = project(root, 1000)
            write_code(root, 1000)
            quiet(L.stamp, pj)
            project(root, 500)
            write_code(root, 500)      # regenerated under the changed rule
            project(root, 1000)        # the rule changed back: the lock agrees with the tree again
            self.assertIn("stale", kinds(pj))

    def test_tags_from_before_v068_hold_while_the_rule_is_as_approved(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            pj = project(root, 1000)
            write_code(root, 1000)
            quiet(L.stamp, pj)
            _, _, tree, _, _ = L.load_project(pj)
            code = (root / "a.ts").read_text().replace(tree["p.1"].hash, tree["p.1"].legacy_hash)
            (root / "a.ts").write_text(code)
            self.assertNotIn("stale", kinds(pj))
            project(root, 500)         # the rule changed since approval: the old tag no longer holds
            self.assertIn("stale", kinds(pj))


class RuleUncited(unittest.TestCase):
    def test_value_in_a_step_that_does_not_cite_the_rule(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            pj = project(root, 1000)
            write_code(root, 1000)
            rep = L.check(pj)
            hits = [w for w in rep["warnings"] if w["kind"] == "rule-uncited"]
            self.assertEqual(len(hits), 1)
            self.assertIn("[p.2]", hits[0]["msg"])
            project(root, 1000, cite_both=True)
            write_code(root, 1000)
            self.assertNotIn("rule-uncited", kinds(pj))


class StampRefusesStale(unittest.TestCase):
    def test_stamp_refuses_then_force(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            pj = project(root, 1000, cite_both=True)
            write_code(root, 1000)
            (root / "t.ladder").write_text(tree_text(1000, True).replace("Read the Avery format", "Read an Avery scale"))
            status, out = quiet(L.stamp, pj)
            self.assertEqual(status, 1)
            self.assertIn("not stamped", out)
            self.assertFalse((root / "ladder.lock.json").exists())
            status, _ = quiet(L.stamp, pj, force=True)
            self.assertEqual(status, 0)


class TraceWithoutExits(unittest.TestCase):
    def test_says_why_nothing_was_compared(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            pj = project(root, 1000, cite_both=True)
            write_code(root, 1000)
            cfg = json.loads(pj.read_text())
            cfg["builds"].append({"name": "other", "lang": "typescript", "tagged": False, "files": ["a.ts"]})
            cfg["compare"] = {"reference": "original", "runs": ["s*"]}
            pj.write_text(json.dumps(cfg))
            for b in ("original", "other"):
                (root / "traces" / b).mkdir(parents=True)
                (root / "traces" / b / "s1.jsonl").write_text(json.dumps({"step": "p.1", "ev": "call", "data": "1"}) + "\n")
            rep = L.check(pj)
            whys = [b.get("why", "") for run in rep["compare"] for b in run["builds"]]
            self.assertTrue(any("no step results" in w for w in whys), whys)


class Help(unittest.TestCase):
    def test_help_on_a_command(self):
        status, out = quiet(L.main, ["ladder", "accept", "--help"])
        self.assertEqual(status, 0)
        self.assertIn("Commands", out)


if __name__ == "__main__":
    unittest.main()

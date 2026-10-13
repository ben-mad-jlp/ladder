"""Round 15 fixes (Update Piece Weight trial). Run: python3 -m unittest discover plugins/ladder/tool/tests
- regen warns when a region gains type escapes (casts through unknown/any, ignore comments); the repair prompt forbids them;
- check: rule-diverged across linked projects (also through a middle project), uncalled-reference (another tree's step
  named without a calls: line; notes do not count), link-unused;
- reference-stale says nothing when the code here is not the approved code (a scratch copy's regeneration)."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ladder as L  # noqa: E402
import ladder_links as K  # noqa: E402
import regen as R  # noqa: E402


def project(root: Path, name: str, tree: str, links: dict | None = None) -> Path:
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "t.ladder").write_text(tree)
    pj = d / "ladder.json"
    pj.write_text(json.dumps({"title": name, "tree": "t.ladder", "links": links or {}, "builds": []}))
    return pj


API = "rule limit: under 10%\n\n[api.1] Save\n  out: nothing\n  > refuses 10% or more (rule limit)\n"
LIB = "[lib.1] Call save\n  out: nothing\n  calls: api [api.1]\n  > posts\n"
APP = "rule limit: under 10%\n\n[app.1] Save from the screen\n  out: nothing\n  > [lib.1], refusing 10% or more first (rule limit)\n  note: the API's [api.1] refuses too\n"


def three(root: Path, app_tree: str = APP, api_tree: str = API) -> tuple[Path, Path, Path]:
    api = project(root, "api", api_tree, {"library": "../lib/ladder.json"})
    lib = project(root, "lib", LIB, {"api": "../api/ladder.json", "app": "../app/ladder.json"})
    app = project(root, "app", app_tree, {"library": "../lib/ladder.json"})
    return api, lib, app


def kinds(pj: Path) -> list[str]:
    cfg, root, tree, _, _ = L.load_project(pj)
    return [w["kind"] for w in K.link_shape_warnings(tree, cfg, root)]


class LinkShape(unittest.TestCase):
    def test_rule_diverged_through_the_middle_project(self):
        with tempfile.TemporaryDirectory() as d:
            api, _, app = three(Path(d), api_tree=API.replace("under 10%", "under 15%"))
            self.assertIn("rule-diverged", kinds(app))
            self.assertIn("rule-diverged", kinds(api))

    def test_same_rules_agree(self):
        with tempfile.TemporaryDirectory() as d:
            api, _, app = three(Path(d))
            self.assertNotIn("rule-diverged", kinds(app))

    def test_uncalled_reference_and_unused_link(self):
        with tempfile.TemporaryDirectory() as d:
            _, _, app = three(Path(d))
            k = kinds(app)
            self.assertIn("uncalled-reference", k)   # [lib.1] in a > line; [api.1] only in a note: not reported
            self.assertEqual(k.count("uncalled-reference"), 1)
            self.assertIn("link-unused", k)
            fixed = APP.replace("  > [lib.1]", "  calls: library [lib.1]\n  > [lib.1]")
            _, _, app = three(Path(d) / "b", app_tree=fixed)
            self.assertNotIn("uncalled-reference", kinds(app))
            self.assertNotIn("link-unused", kinds(app))


class TypeEscapes(unittest.TestCase):
    def test_added_cast_is_reported(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "t.ladder").write_text("[a.1] Weigh\n  out: a number\n  > the scale's weight\n")
            pj = root / "ladder.json"
            pj.write_text(json.dumps({"title": "t", "tree": "t.ladder",
                                      "builds": [{"name": "a", "lang": "typescript", "files": ["a.ts"], "steps": ["a.*"]}]}))
            cfg, _, tree, _, _ = L.load_project(pj)
            (root / "a.ts").write_text(f"// @node a.1@{tree['a.1'].hash}\nconst w = scale.currentWeight;\n// @end\n")
            before = L.region_texts(root, cfg)
            (root / "a.ts").write_text(f"// @node a.1@{tree['a.1'].hash}\nconst w = (scale as unknown as {{ weight: number }}).weight;\n// @end\n")
            warns = L.type_escape_warnings(root, cfg, before)
            self.assertEqual(len(warns), 1)
            self.assertIn("[node a.1]", warns[0])

    def test_repair_prompt_forbids_silencing(self):
        self.assertIn("never hide it", R.REPAIR_RULE)


class ReferenceStaleOnlyForApprovedCode(unittest.TestCase):
    def test_scratch_regeneration_is_not_reported(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "t.ladder").write_text("[a.1] Answer\n  out: a number\n  > answers 1\n")
            pj = root / "ladder.json"
            pj.write_text(json.dumps({"title": "t", "tree": "t.ladder", "compare": {"reference": "original", "runs": ["*"]},
                                      "builds": [{"name": "a", "lang": "typescript", "files": ["a.ts"], "steps": ["a.*"],
                                                  "traces": "original"}]}))
            cfg, _, tree, _, _ = L.load_project(pj)
            (root / "a.ts").write_text(f"// @node a.1@{tree['a.1'].hash}\nexport const a = () => 1;\n// @end\n")
            L.record_code(root, cfg)                      # the approved code
            out = root / "traces" / "original"
            out.mkdir(parents=True)
            (out / ".replay.json").write_text(json.dumps({"code": L.code_fingerprint(root, cfg)}))
            (root / "a.ts").write_text((root / "a.ts").read_text().replace("=> 1", "=> 2"))
            self.assertEqual(L.reference_stale_warnings(root, cfg), [])   # not the approved code: a regeneration
            L.record_code(root, cfg)                      # approved now, and the reference is from the old code
            self.assertEqual(len(L.reference_stale_warnings(root, cfg)), 1)


if __name__ == "__main__":
    unittest.main()

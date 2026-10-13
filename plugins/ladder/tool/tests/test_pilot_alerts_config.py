"""Alerts pilot fixes (configuration and checks). Run: python3 -m unittest discover plugins/ladder/tool/tests
- "extra_vocabulary" adds an area's capabilities to the shared vocabulary; a changed copy is an error, an identical one a
  warning;
- "generated": a file another tool writes is refused by tag and reported by check;
- a @contract rule region no longer counts as the data contract a build lists (missing-contract);
- a capability test naming a file that does not exist says so (test-missing);
- `ladder --version`."""
import contextlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ladder as L  # noqa: E402
import ladder_extra as X  # noqa: E402

CAP = "capability {name}\n  in: a value\n  out: a value\n  typescript: (built in) lib | {call}\n"


def quiet(fn, *a):
    with contextlib.redirect_stdout(io.StringIO()) as out:
        try:
            code = fn(*a)
        except SystemExit as e:
            code = e.code
    return code, out.getvalue()


class Base(unittest.TestCase):
    def setUp(self):
        L._REPO.clear()
        L._LINKED.clear()
        self.root = Path(tempfile.mkdtemp())
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        self.p = self.root / "area"
        self.p.mkdir()
        (self.p / "t.ladder").write_text("[t.1] Step\n  in: a\n  out: b\n  uses: shared thing\n  > answers b\n")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def project(self, **extra):
        cfg = {"title": "t", "tree": "t.ladder", "builds": [{"name": "c", "lang": "typescript", "files": ["c.ts"]}], **extra}
        (self.p / "ladder.json").write_text(json.dumps(cfg))
        return self.p / "ladder.json"


class ExtraVocabulary(Base):
    def setUp(self):
        super().setUp()
        (self.root / "shared.ladder").write_text(CAP.format(name="shared thing", call="shared()"))

    def test_layers_add_and_identical_copies_warn(self):
        (self.p / "v.ladder").write_text(CAP.format(name="area thing", call="area()") +
                                         "\n" + CAP.format(name="shared thing", call="shared()"))
        pj = self.project(vocabulary="../shared.ladder", extra_vocabulary=["v.ladder"])
        cfg, root = L.read_config(pj), pj.parent
        self.assertEqual(sorted(L.load_vocabulary(cfg, root)), ["area thing", "shared thing"])
        w = L.vocabulary_copy_warnings(cfg, root)
        self.assertEqual([x["node"] for x in w], ["shared thing"])

    def test_a_changed_copy_is_refused(self):
        (self.p / "v.ladder").write_text(CAP.format(name="shared thing", call="shared(1)"))
        pj = self.project(vocabulary="../shared.ladder", extra_vocabulary=["v.ladder"])
        with self.assertRaises(SystemExit) as e:
            L.load_vocabulary(L.read_config(pj), pj.parent)
        self.assertIn("says something else", str(e.exception))


class GeneratedFiles(Base):
    def test_check_and_tag_refuse_a_generated_file(self):
        (self.p / "c.ts").write_text("export const x = 1\n")
        subprocess.run(["git", "-C", str(self.root), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(self.root), "-c", "user.email=a@b", "-c", "user.name=a", "commit", "-qm", "x"],
                       check=True)
        (self.root / "ladder.repo.json").write_text(json.dumps({"generated": ["area/*.ts"]}))
        pj = self.project()
        rep = L.check(pj)
        kinds = [p["kind"] for b in rep["builds"] for p in b["problems"]]
        self.assertIn("generated-file", kinds)
        (self.p / "regions.json").write_text(json.dumps({"c.ts": [[1, 1, "node t.1"]]}))
        code, out = quiet(X.tag, [str(pj), str(self.p / "regions.json")])
        self.assertEqual(code, 1)
        self.assertIn("another tool writes this file", out)
        self.assertEqual((self.p / "c.ts").read_text(), "export const x = 1\n")


class RuleRegionIsNotADataContract(Base):
    def test_missing_contract_is_reported_beside_a_rule_region(self):
        (self.p / "t.ladder").write_text("rule limit: at most 3\n\ndata Row\n  a: text\n\n"
                                         "[t.1] Step\n  in: a\n  out: Row\n  > answers at most 3 (rule limit)\n")
        pj = self.project()
        cfg = json.loads(pj.read_text())
        cfg["builds"][0]["data"] = ["Row"]
        pj.write_text(json.dumps(cfg))
        _, _, tree, *_ = L.load_project(pj)
        h = L.contract_hash(tree, L.read_config(pj)["builds"][0])
        (self.p / "c.ts").write_text(f"// @contract rule limit@{h}\nconst LIMIT = 3\n// @end\n"
                                     f"// @node t.1@{tree['t.1'].hash}\nexport const f = () => LIMIT\n// @end\n")
        rep = L.check(pj)
        kinds = [p["kind"] for b in rep["builds"] for p in b["problems"]]
        self.assertIn("missing-contract", kinds)


class TestMissingAndVersion(Base):
    def test_capability_test_naming_a_missing_file(self):
        (self.root / "shared.ladder").write_text(CAP.format(name="shared thing", call="shared()") +
                                                 "  test: typescript | npx vitest run harness/nowhere.test.ts\n")
        pj = self.project(vocabulary="../shared.ladder")
        rep = L.check(pj)
        self.assertIn("test-missing", [w["kind"] for w in rep["warnings"]])

    def test_version(self):
        code, out = quiet(L.main, ["ladder", "--version"])
        self.assertEqual(code, 0)
        self.assertRegex(out.strip(), r"^\d+\.\d+\.\d+$")


class BlindRunKeepsWhatCallersUse(unittest.TestCase):
    def test_multi_line_declaration_is_kept_whole(self):
        import regen as R
        own = ["export function dataset(", "  name: string,", "  input: { a: number },", "): Rows {", "  return []", "}"]
        self.assertEqual(R.declarations(own), ["export function dataset( name: string, input: { a: number }, ): Rows {"])

    def test_csharp_public_and_internal_members_are_named(self):
        import regen as R
        lines = ["// @node x.1@abc", "public static bool IsDue(DateTime a, int b)", "{", "  return true;", "}",
                 "internal string Name { get; set; }", "// @end"]
        regions, *_ = L.parse_regions_text(lines, "csharp") if hasattr(L, "parse_regions_text") else (None,)
        if regions is None:
            p = Path(tempfile.mkdtemp()) / "a.cs"
            p.write_text("\n".join(lines) + "\n")
            regions, _, flines, _ = L.parse_regions(p, "csharp")
        note = R.public_names_note(regions, flines, 0, "csharp")
        self.assertIn("IsDue", note)
        self.assertIn("Name", note)
        self.assertIn("public static bool IsDue(DateTime a, int b)", note)


if __name__ == "__main__":
    unittest.main()

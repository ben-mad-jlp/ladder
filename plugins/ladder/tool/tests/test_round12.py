"""Round 12 fixes (SKU History trial). Run: python3 -m unittest discover plugins/ladder/tool/tests
- prompts show the data blocks the shown blocks name (transitively);
- blind regeneration writes a @contract region around a step region it holds, instead of crashing;
- blind prompts give exported declarations;
- check warns about an exported type in a step region that other files use;
- --repair stops when the errors are in other builds' files."""
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
import regen as R  # noqa: E402

TREE = textwrap.dedent("""\
    data History
      sku: text
      properties: list of Property

    data Property
      parameter: text

    [h.1] Read the history
      in: a name
      out: a History
      > reads it

    [h.2] Make the answer
      in: a History
      out: a History
      > copies it
    """)


def project(root: Path, code: str) -> Path:
    (root / "t.ladder").write_text(TREE)
    (root / "A.cs").write_text(code)
    pj = root / "ladder.json"
    pj.write_text(json.dumps({"title": "t", "tree": "t.ladder",
                              "builds": [{"name": "a", "lang": "csharp", "files": ["A.cs"], "steps": ["h.*"], "data": ["History"]}]}))
    return pj


class Prompts(unittest.TestCase):
    def test_blocks_named_by_shown_blocks_are_shown(self):
        with tempfile.TemporaryDirectory() as d:
            pj = project(Path(d), "")
            cfg, root, tree, *_ = L.load_project(pj)
            R.set_context(cfg, root, tree)
            text = R.context_text(cfg["builds"][0], ["h.1"], conventions=False)
            self.assertIn("data Property", text)

    def test_exported_declarations_are_named(self):
        lines = ["// @node h.1@000000", "export function dataset(input: { sku: string }): Rows {", "  return []", "}", "// @end"]
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "a.ts"
            f.write_text("\n".join(lines) + "\n")
            regions, _, ls, _ = L.parse_regions(f, "typescript")
            self.assertIn("export function dataset(input: { sku: string }): Rows {", R.public_names_note(regions, ls, 0, "typescript"))


class ContractAroundStep(unittest.TestCase):
    def test_a_contract_holding_a_step_region_is_written_last_around_it(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            pj = project(root, "")
            cfg, root, tree, lock, _ = L.load_project(pj)
            h2 = tree["h.2"].hash
            (root / "A.cs").write_text(f"// @contract History@000000\npublic class HistoryDto {{\n    public string Sku;\n"
                                       f"    // @node h.2@{h2}\n    public static HistoryDto From(HistoryDto s) => s;\n    // @end\n}}\n// @end\n"
                                       f"// @node h.1@{tree['h.1'].hash}\nvoid Read() {{}}\n// @end\n")
            log = root / "log"
            (log / "cwd").mkdir(parents=True)
            R.REDO.clear()
            R.set_context(cfg, root, tree)
            out = R.regen_blind(cfg, root, tree, lock, cfg["builds"][0], ["true"], log, dry_run=True)
            msgs = {k: m for _, k, m in out}
            self.assertIn("own lines, around nested regions", msgs["contract History"])
            self.assertTrue(msgs["node h.2"].startswith("dry run"))


def git(root, *a):
    subprocess.run(["git", "-C", str(root), *a], check=True, capture_output=True)


class ExportedTypeInStep(unittest.TestCase):
    def test_an_exported_type_in_a_step_region_used_elsewhere_is_warned(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            git(root, "init", "-q")
            (root / "package.json").write_text("{}")
            (root / "t.ladder").write_text("[v.1] Show it\n  > shows it\n")
            h = L.parse_tree(root / "t.ladder")["v.1"].hash
            (root / "View.tsx").write_text(f"// @node v.1@{h}\nexport interface ViewProps {{ a: number }}\nexport function View() {{}}\n// @end\n")
            (root / "fixture.ts").write_text("import type { ViewProps } from './View'\n")
            git(root, "add", "-A")
            pj = root / "ladder.json"
            pj.write_text(json.dumps({"title": "t", "tree": "t.ladder", "builds": [{"name": "v", "lang": "typescript", "files": ["View.tsx"]}]}))
            warns = [w for w in L.check(pj)["warnings"] if w["kind"] == "exported-type-in-step"]
            self.assertEqual([w["node"] for w in warns], ["ViewProps"])
            self.assertIn("fixture.ts", warns[0]["msg"])


class RepairStops(unittest.TestCase):
    def test_errors_outside_the_build_stop_the_repair_loop(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "A.cs").write_text("")
            cfg = {"builds": [{"name": "a", "lang": "csharp", "files": ["A.cs"]}], "check_command": ["bash", "-c", "echo 'B.cs(3,1): error CS1: x'; exit 1"]}
            with contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(L.repair_until_builds(root / "ladder.json", cfg, root, "a", 3), 1)
            self.assertIn("none in a's files", out.getvalue())


if __name__ == "__main__":
    unittest.main()

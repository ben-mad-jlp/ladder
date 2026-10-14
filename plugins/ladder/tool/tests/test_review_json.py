"""JSON output for the Ladder Review app (v0.8.0). Run: python3 -m unittest discover plugins/ladder/tool/tests
- `ladder check --json`: the report as JSON with the same exit code, and nothing else on stdout;
- `ladder check --all --json`: one row per project;
- `ladder projects`: from ladder.repo.json, else every ladder.json git tracks below the folder;
- `ladder export --regions`: each build's regions, with the check problems that fall inside each."""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ladder as L  # noqa: E402
from test_round20 import project, quiet, tag  # noqa: E402


class ReviewJson(unittest.TestCase):
    def setUp(self):
        L._REPO.clear()
        self.root = Path(tempfile.mkdtemp())
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        self.a = project(self.root / "areas" / "a", "a")
        self.b = project(self.root / "areas" / "b", "b")
        tag(self.a)
        tag(self.b)
        quiet(L.stamp, self.a)
        quiet(L.stamp, self.b)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)
        L._REPO.clear()

    def run_tool(self, *args) -> tuple[int, str]:
        return quiet(L.main, ["ladder", *map(str, args)])

    def test_check_json_is_the_report_with_the_same_exit_code(self):
        code, out = self.run_tool("check", self.a, "--json")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["status"], "ok")
        (self.a.parent / "t.ladder").write_text((self.a.parent / "t.ladder").read_text().replace("plus one", "plus two"))
        code, out = self.run_tool("check", self.a, "--json")
        rep = json.loads(out)                                   # stdout holds only the JSON
        self.assertEqual(code, 1)                               # the tagged code is now stale
        self.assertIn("edited", [p["kind"] for p in rep["tree"]])
        self.assertIn("stale", [p["kind"] for b in rep["builds"] for p in b["problems"]])

    def test_projects_without_a_repo_file_are_the_tracked_ladder_json_files(self):
        subprocess.run(["git", "-C", str(self.root), "add", "-A"], check=True)
        (self.root / "node_modules" / "x").mkdir(parents=True)
        (self.root / "node_modules" / "x" / "ladder.json").write_text("{}")
        (self.root / ".gitignore").write_text("node_modules/\n")
        code, out = self.run_tool("projects", self.root)
        rows = json.loads(out)
        self.assertIsNone(rows["repoFile"])
        self.assertEqual([p["name"] for p in rows["projects"]], ["areas/a", "areas/b"])
        self.assertEqual(rows["projects"][0]["builds"][0]["files"], ["c.ts"])

    def test_projects_and_check_all_follow_ladder_repo_json(self):
        (self.root / "ladder.repo.json").write_text(json.dumps({"projects": ["areas/a/ladder.json"]}))
        L._REPO.clear()
        _, out = self.run_tool("projects", self.root / "areas")
        rows = json.loads(out)
        self.assertTrue(rows["repoFile"].endswith("ladder.repo.json"))
        self.assertEqual([p["name"] for p in rows["projects"]], ["areas/a"])
        code, out = self.run_tool("check", "--all", self.root, "--json")
        self.assertEqual(code, 0)
        self.assertEqual([(p["name"], p["status"]) for p in json.loads(out)["projects"]], [("areas/a", "ok")])

    def test_export_regions_marks_the_region_a_problem_falls_in(self):
        (self.a.parent / "t.ladder").write_text((self.a.parent / "t.ladder").read_text().replace("plus one", "plus two"))
        _, out = self.run_tool("export", self.a, "--regions")
        f = json.loads(out)["builds"][0]["files"][0]
        self.assertTrue(f["exists"])
        (r,) = f["regions"]
        self.assertEqual((r["steps"], r["start"], r["end"]), (["a.1"], 1, 3))
        self.assertEqual(r["current"], [False])
        self.assertEqual(r["problems"], ["stale"])
        rep = json.loads(out)["check"]                          # the report it read them from comes along
        self.assertEqual(rep["status"], "problems")
        self.assertEqual({p["kind"]: p["level"] for p in rep["tree"]}, {"edited": "approval"})


if __name__ == "__main__":
    unittest.main()

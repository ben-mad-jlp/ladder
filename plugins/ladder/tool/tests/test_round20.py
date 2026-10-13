"""Round 20 fixes (whole-repository scale). Run: python3 -m unittest discover plugins/ladder/tool/tests
- ladder.repo.json: settings every project shares (defaults, build_defaults), paths relative to it;
- an edited step names the projects that call it, found through ladder.repo.json's "projects" when it does not link back;
- `ladder check --all`: every project in one run, one line each."""
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
import ladder_links as K  # noqa: E402


def quiet(fn, *a):
    with contextlib.redirect_stdout(io.StringIO()) as out:
        try:
            code = fn(*a)
        except SystemExit as e:
            code = e.code
    return code, out.getvalue()


def project(d: Path, prefix: str, links: dict | None = None, calls: str = "") -> Path:
    """A one-step project with its code tagged at the tree's hash."""
    d.mkdir(parents=True)
    (d / "t.ladder").write_text(f"[{prefix}.1] Add one\n  in: a number\n  out: the number plus one\n"
                                f"  > answers the number plus one\n" + (f"  calls: {calls}\n" if calls else ""))
    cfg = {"title": prefix, "tree": "t.ladder", "builds": [{"name": "code", "lang": "typescript", "files": ["c.ts"]}]}
    if links:
        cfg["links"] = links
    (d / "ladder.json").write_text(json.dumps(cfg))
    return d / "ladder.json"


def tag(pj: Path) -> None:
    _, _, tree, *_ = L.load_project(pj)
    nid = next(iter(tree))
    (pj.parent / "c.ts").write_text(f"// @node {nid}@{tree[nid].hash}\nexport const f = (x: number) => x + 1\n// @end\n")


class RepoBase(unittest.TestCase):
    def setUp(self):
        L._REPO.clear()
        L._LINKED.clear()
        K._REVERSE.clear()
        K._PENDING.clear()
        self.root = Path(tempfile.mkdtemp())
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def repo(self, spec: dict) -> None:
        (self.root / "ladder.repo.json").write_text(json.dumps(spec))
        L._REPO.clear()


class RepoDefaults(RepoBase):
    def test_defaults_fill_and_paths_are_rebased(self):
        pj = project(self.root / "areas" / "notes" / "api", "n")
        self.repo({"defaults": {"vocabulary": "shared/vocabulary.ladder", "generator": {"command": ["gen"]},
                                "schemas": {"db": {"kind": "json", "source": "shared/db.json"}}},
                   "build_defaults": {"*": {"mode": "literal", "conventions": ["shared/all.md"]},
                                      "typescript": {"conventions": ["shared/ts.md"], "adopted": True}}})
        cfg = L.read_config(pj)
        self.assertEqual(cfg["vocabulary"], "../../../shared/vocabulary.ladder")
        self.assertEqual(cfg["schemas"]["db"]["source"], "../../../shared/db.json")
        self.assertEqual(cfg["generator"], {"command": ["gen"]})
        b = cfg["builds"][0]
        self.assertEqual(b["mode"], "literal")
        self.assertEqual(b["conventions"], ["../../../shared/ts.md"])   # the language's layer wins over "*"
        self.assertTrue(b["adopted"])

    def test_the_project_wins_and_untagged_builds_take_no_build_defaults(self):
        pj = project(self.root / "p", "p")
        cfg = json.loads(pj.read_text())
        cfg["generator"] = {"command": ["mine"]}
        cfg["builds"].append({"name": "recording", "lang": "typescript", "tagged": False, "files": []})
        pj.write_text(json.dumps(cfg))
        self.repo({"defaults": {"generator": {"command": ["gen"]}}, "build_defaults": {"*": {"mode": "literal"}}})
        got = L.read_config(pj)
        self.assertEqual(got["generator"], {"command": ["mine"]})
        self.assertEqual(got["builds"][0]["mode"], "literal")
        self.assertNotIn("mode", got["builds"][1])

    def test_project_only_keys_are_refused(self):
        pj = project(self.root / "p", "p")
        self.repo({"defaults": {"tree": "x.ladder"}})
        with self.assertRaises(SystemExit) as e:
            L.read_config(pj)
        self.assertIn("belongs in each project", str(e.exception))

    def test_no_repo_file_changes_nothing(self):
        pj = project(self.root / "p", "p")
        self.assertEqual(L.read_config(pj), json.loads(pj.read_text()))

    def test_init_leaves_out_what_the_repo_supplies(self):
        self.repo({"defaults": {"vocabulary": "v.ladder", "generator": {"command": ["gen"]}},
                   "build_defaults": {"*": {"mode": "literal", "conventions": ["c.md"]}}})
        quiet(X.init, [str(self.root / "new"), "--name", "New", "--lang", "typescript"])
        cfg = json.loads((self.root / "new" / "ladder.json").read_text())
        self.assertNotIn("vocabulary", cfg)
        self.assertNotIn("generator", cfg)
        self.assertNotIn("mode", cfg["builds"][0])
        self.assertNotIn("conventions", cfg["builds"][0])
        self.assertFalse((self.root / "new" / "vocabulary.ladder").exists())
        self.assertFalse((self.root / "new" / "conventions").exists())


class CallersAcrossTheRepo(RepoBase):
    def setUp(self):
        super().setUp()
        self.api = project(self.root / "api", "a")
        self.screens = [project(self.root / f"s{i}", f"s{i}", links={"api": "../api/ladder.json"}, calls="api [a.1]")
                        for i in range(3)]
        for pj in [self.api, *self.screens]:
            tag(pj)
        for pj in [self.api, *self.screens]:
            self.assertEqual(quiet(L.stamp, pj)[0], 0)
        t = self.api.parent / "t.ladder"
        t.write_text(t.read_text().replace("plus one", "plus one, rounded down"))

    def warnings(self):
        return [w for w in L.check(self.api)["warnings"] if w["kind"] == "has-callers"]

    def test_without_a_repo_file_the_api_cannot_know_its_callers(self):
        self.assertEqual(self.warnings(), [])

    def test_with_the_repo_file_one_warning_names_every_caller(self):
        self.repo({"projects": ["*/ladder.json"]})
        w = self.warnings()
        self.assertEqual(len(w), 1)
        for i in range(3):
            self.assertIn(f"s{i} [s{i}.1]", w[0]["msg"])

    def test_check_all_lists_each_project_and_exits_as_the_worst(self):
        self.repo({"projects": ["*/ladder.json"]})
        code, out = quiet(L.check_all, self.root)
        self.assertEqual(code, 1)                      # the api's code is stale now
        self.assertIn("4 projects", out)
        self.assertIn("api ", out)
        # the callers see the changed out: line at once (linked-changed); the api has stale code
        self.assertIn("0 ok, 3 awaiting approval, 1 with problems", out)
        self.assertIn("linked-changed 3", out)

    def test_check_all_needs_projects(self):
        self.repo({"defaults": {}})
        with self.assertRaises(SystemExit) as e:
            L.check_all(self.root)
        self.assertIn("no \"projects\"", str(e.exception))


if __name__ == "__main__":
    unittest.main()

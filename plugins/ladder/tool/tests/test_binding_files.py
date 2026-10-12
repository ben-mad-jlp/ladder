"""The generator sees an in-repository capability's binding, and check notices code that calls none of the binding's
calls (round 9: the cache build wrote storageService.getItem for storageService.get; the repair then imported the
storage library directly; it compiled, and only a behaviour test noticed). Run: python3 -m unittest discover
plugins/ladder/tool/tests"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ladder as L  # noqa: E402
import regen as R  # noqa: E402

TREE = """[k.1] Keep a list on the device
  in: a list
  out: nothing
  uses: device storage
  > stores the list under "k"
"""
VOCAB = """capability device storage
  in: a key, a value
  out: the stored value, or nothing
  typescript: (in repository) app/src/storage.ts on some-storage 1.0 | await storage.get<T>(key); await storage.set(key, value)
"""
STORAGE = "export const storage = {\n  async get<T>(key: string): Promise<T | null> { return null },\n  async set(key: string, value: unknown) {},\n}\n"


def project(root: Path, code: str) -> Path:
    (root / "app" / "src").mkdir(parents=True)
    (root / "app" / "src" / "storage.ts").write_text(STORAGE)
    proj = root / "ladder" / "k"
    proj.mkdir(parents=True)
    (proj / "k.ladder").write_text(TREE)
    (proj / "vocab.ladder").write_text(VOCAB)
    (root / "app" / "src" / "keep.ts").write_text(code)
    cfg = {"title": "k", "tree": "k.ladder", "vocabulary": "vocab.ladder", "check_cwd": "../../app",
           "builds": [{"name": "keep", "lang": "typescript", "mode": "literal", "files": ["../../app/src/keep.ts"], "steps": ["k.*"]}]}
    (proj / "ladder.json").write_text(json.dumps(cfg))
    return proj / "ladder.json"


class BindingFiles(unittest.TestCase):
    def test_call_names_and_files(self):
        b = "(in repository) app/src/storage.ts on some-storage 1.0 | await storage.get<T>(key); await storage.set(key, value)"
        self.assertEqual(L.binding_call_names(b), {"get", "set"})
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            pj = project(root, "")
            cfg, proot, *_ = L.load_project(pj)
            self.assertEqual(L.binding_files(b, L.project_bases(cfg, proot)), [(root / "app/src/storage.ts").resolve()])
        self.assertEqual(L.binding_files("Microsoft.EntityFrameworkCore 9 | x.ToListAsync()", [Path("/")]), [])

    def test_the_prompt_shows_the_binding_file(self):
        with tempfile.TemporaryDirectory() as d:
            pj = project(Path(d), "")
            cfg, root, tree, lock, _ = L.load_project(pj)
            R.set_context(cfg, root, tree)
            text = R.context_text(cfg["builds"][0], ["k.1"], conventions=False)
            self.assertIn("the binding of capability 'device storage'", text)
            self.assertIn("async get<T>(key: string)", text)

    def test_check_warns_when_no_binding_call_is_made(self):
        with tempfile.TemporaryDirectory() as d:
            bad = "// @node k.1@000000\nexport async function keep(l: string[]) { await storage.setItem('k', l) }\n// @end\n"
            rep = L.check(project(Path(d), bad))
            self.assertEqual([w["kind"] for w in rep["warnings"] if w["kind"] == "binding-not-called"], ["binding-not-called"])
        with tempfile.TemporaryDirectory() as d:
            good = "// @node k.1@000000\nexport async function keep(l: string[]) { await storage.set('k', l) }\n// @end\n"
            rep = L.check(project(Path(d), good))
            self.assertEqual([w for w in rep["warnings"] if w["kind"] == "binding-not-called"], [])


if __name__ == "__main__":
    unittest.main()

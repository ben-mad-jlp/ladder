"""Shipping round fixes (v0.7.2). Run: python3 -m unittest discover plugins/ladder/tool/tests
- tag keeps a CRLF file's line endings; adopt-check reports changed line endings;
- a test record ignores marker lines (a retag does not make a passed test stale);
- `ladder test`: a run that ran no tests fails; a silent pass is warned; the count is recorded;
- calls: an item may name several steps; a target may be a data block, and its change reaches the caller;
- a step naming a step of a repository project it does not link to is warned."""
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

GIT = ["-c", "user.email=a@b", "-c", "user.name=a"]


def quiet(fn, *a):
    with contextlib.redirect_stdout(io.StringIO()) as out:
        try:
            code = fn(*a)
        except SystemExit as e:
            code = e.code
    return code, out.getvalue()


class Base(unittest.TestCase):
    def setUp(self):
        for cache in (L._REPO, L._LINKED, K._REVERSE, K._PENDING, getattr(K, "_STEP_OWNERS", {})):
            cache.clear()
        self.root = Path(tempfile.mkdtemp())
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def commit(self):
        subprocess.run(["git", "-C", str(self.root), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(self.root), *GIT, "commit", "-qm", "x"], check=True)

    def project(self, folder: str, tree: str, extra: dict | None = None, code: str = "export const x = 1\n") -> Path:
        d = self.root / folder
        d.mkdir(parents=True)
        (d / "t.ladder").write_text(tree)
        (d / "c.ts").write_bytes(code.encode())
        cfg = {"title": folder, "tree": "t.ladder",
               "builds": [{"name": "c", "lang": "typescript", "files": ["c.ts"], "adopted": True}], **(extra or {})}
        (d / "ladder.json").write_text(json.dumps(cfg))
        return d / "ladder.json"


class LineEndings(Base):
    def test_tag_keeps_crlf_and_adopt_check_sees_lf(self):
        pj = self.project("p", "[p.1] One\n  in: a\n  out: b\n  > answers b\n", code="const a = 1\r\nconst b = 2\r\n")
        self.commit()
        (pj.parent / "regions.json").write_text(json.dumps({"c.ts": [[1, 2, "node p.1"]]}))
        code, out = quiet(X.tag, [str(pj), str(pj.parent / "regions.json"), "--base", "HEAD"])
        self.assertEqual(code, 0, out)
        data = (pj.parent / "c.ts").read_bytes()
        self.assertNotIn(b"\n", data.replace(b"\r\n", b""))           # every line still ends CRLF
        self.assertEqual(quiet(X.adopt_check, [str(pj), "--base", "HEAD"])[0], 0)
        (pj.parent / "c.ts").write_bytes(data.replace(b"\r\n", b"\n"))
        code, out = quiet(X.adopt_check, [str(pj), "--base", "HEAD"])
        self.assertEqual(code, 1)
        self.assertIn("line endings changed from CRLF to LF", out)


class TestRecords(Base):
    def test_marker_lines_do_not_change_the_code_hash(self):
        a = self.root / "a.ts"
        a.write_text("// @node p.1@aaaaaa\nexport const x = 1\n// @end\n")
        h1 = K.code_hash(a)
        a.write_text("// @node p.1@bbbbbb\nexport const x = 1\n// @end\n")
        self.assertEqual(h1, K.code_hash(a))
        a.write_text("// @node p.1@bbbbbb\nexport const x = 2\n// @end\n")
        self.assertNotEqual(h1, K.code_hash(a))

    def test_no_tests_ran_fails_and_silence_is_warned(self):
        pj = self.project("p", "[p.1] One\n  in: a\n  out: b\n  > answers b\n",
                          extra={"tests": [{"name": "none", "command": "echo 'No test files found, exiting with code 0'"},
                                           {"name": "quiet", "command": "true"},
                                           {"name": "counted", "command": "echo '      Tests  7 passed (7)'"}]})
        code, out = quiet(K.run_tests, pj)
        self.assertEqual(code, 1)
        self.assertIn("no tests ran", out)
        self.assertIn("7 tests", out)
        rep = L.check(pj)
        self.assertIn("test-silent", [w["kind"] for w in rep["warnings"]])


class Links(Base):
    def setUp(self):
        super().setUp()
        self.api = self.project("api", "data Row\n  a: text\n\n[a.1] One\n  in: a\n  out: Row\n  > answers b\n\n"
                                       "[a.2] Two\n  in: a\n  out: b\n  > answers b\n")

    def test_several_ids_in_one_item(self):
        n = type("N", (), {"calls": ["api [a.1] [a.2]"]})()
        self.assertEqual([t for _, t, _ in K.parse_calls(n)], ["a.1", "a.2"])

    def test_a_data_block_target_reaches_the_caller(self):
        ui = self.project("ui", "[u.1] Show\n  in: a Row\n  out: nothing\n  calls: api [Row]\n  > shows it\n",
                          extra={"links": {"api": "../api/ladder.json"}})
        self.assertNotIn("link", [p["kind"] for p in L.check(ui)["tree"]])
        quiet(L.stamp, self.api)
        quiet(L.stamp, ui)
        (self.api.parent / "t.ladder").write_text((self.api.parent / "t.ladder").read_text().replace("  a: text",
                                                                                                    "  a: text\n  b: number"))
        L._LINKED.clear()
        K._PENDING.clear()
        changed = [p for p in L.check(ui)["tree"] if p["kind"] == "linked-changed"]
        self.assertTrue(changed)
        self.assertIn("gained field b", changed[0]["msg"])

    def test_naming_an_unlinked_repository_project_is_warned(self):
        (self.root / "ladder.repo.json").write_text(json.dumps({"projects": ["*/ladder.json"]}))
        L._REPO.clear()
        ui = self.project("ui", "[u.1] Show\n  in: a\n  out: nothing\n  > shows what [a.1] answers\n")
        w = [x for x in L.check(ui)["warnings"] if x["kind"] == "uncalled-reference"]
        self.assertTrue(w)
        self.assertIn("does not link to", w[0]["msg"])


if __name__ == "__main__":
    unittest.main()

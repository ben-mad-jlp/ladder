"""`ladder edit`, `ladder answer` and `ladder stamp --steps` (v0.8.0, for editing and approving in the Ladder Review
app). Run: python3 -m unittest discover plugins/ladder/tool/tests
- an edit rewrites only the lines that change; comments, blank lines and other steps keep their exact text;
- an edit is refused when the step changed since it was read, or when the result would not parse or say what was asked;
- an answer keeps the question; stamp --steps approves only the chosen steps and records who."""
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
import ladder_edit as E  # noqa: E402

TREE = """\
data Item
  name: text

[a.1] Add one
  in: a number
  out: the number plus one
  > checks the number
  # a comment the author wrote
  > answers the number plus one
  note: QUESTION: what about NaN?

  [a.1.1] Check the number
    in:   a number
    > answers 400 when it is not a number

[a.2] Double
  in: a number
  out: twice the number
  > answers twice the number
"""


class EditBase(unittest.TestCase):
    def setUp(self):
        L._REPO.clear()
        self.root = Path(tempfile.mkdtemp())
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        subprocess.run(["git", "-C", str(self.root), "config", "user.name", "Pat"], check=True)
        (self.root / "t.ladder").write_text(TREE)
        (self.root / "c.ts").write_text("")
        self.pj = self.root / "ladder.json"
        self.pj.write_text(json.dumps({"title": "t", "tree": "t.ladder",
                                       "builds": [{"name": "code", "lang": "typescript", "files": ["c.ts"]}]}))

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def text(self) -> str:
        return (self.root / "t.ladder").read_text()

    def tag_all(self):
        _, _, tree, *_ = L.load_project(self.pj)
        (self.root / "c.ts").write_text("".join(f"// @node {n}@{tree[n].hash}\nexport const f{i} = 1\n// @end\n"
                                                for i, n in enumerate(["a.1.1", "a.2"])))


class Edit(EditBase):
    def test_only_the_changed_lines_are_rewritten(self):
        res = E.apply_edit(self.pj, "a.1", {"outputs": "the number plus two",
                                            "how": ["checks the number", "answers the number plus two"]}, None, False)
        want = TREE.replace("out: the number plus one", "out: the number plus two") \
                   .replace("> answers the number plus one", "> answers the number plus two")
        self.assertEqual(self.text(), want)          # the comment, blank lines and [a.1.1]'s odd spacing are kept
        self.assertEqual(res["parts"], ["how", "out"])

    def test_parts_are_added_removed_and_reordered_in_place(self):
        E.apply_edit(self.pj, "a.2", {"effects": "writes a log line", "inputs": "",
                                      "how": ["logs it", "answers twice the number"], "notes": ["kept short"]},
                     None, False)
        block = self.text().split("[a.2] Double\n")[1]
        self.assertEqual(block, "  out: twice the number\n  effects: writes a log line\n  > logs it\n"
                                "  > answers twice the number\n  note: kept short\n")
        E.apply_edit(self.pj, "a.2", {"how": ["answers twice the number", "logs it"]}, None, False)
        self.assertIn("  > answers twice the number\n  > logs it\n", self.text())

    def test_a_stale_read_and_a_bad_result_are_refused_and_nothing_is_written(self):
        with self.assertRaises(E.Refused) as e:
            E.apply_edit(self.pj, "a.1", {"title": "Add two"}, "000000", False)
        self.assertIn("changed since it was read", str(e.exception))
        with self.assertRaises(E.Refused):
            E.apply_edit(self.pj, "a.1", {"how": ["two\nlines"]}, None, False)
        with self.assertRaises(E.Refused) as e:                  # would read back as a note, not a how-line
            E.apply_edit(self.pj, "a.1", {"outputs": "x", "how": ["ok"], "title": ""}, None, False)
        self.assertEqual(self.text(), TREE)

    def test_dry_run_reports_the_reach_and_writes_nothing(self):
        self.tag_all()
        res = E.apply_edit(self.pj, "a.2", {"how": ["answers the number times two"]}, None, True)
        self.assertFalse(res["written"])
        self.assertEqual([r["steps"] for r in res["stale"]], [["a.2"]])
        self.assertTrue(res["contractChanged"] is False)
        self.assertEqual(self.text(), TREE)
        res = E.apply_edit(self.pj, "a.2", {"outputs": "two times the number"}, None, True)
        self.assertTrue(res["contractChanged"])                   # in:/out: lines are the contract


class AnswerAndStamp(EditBase):
    def test_an_answer_keeps_the_question_and_says_who(self):
        code, _ = run(["answer", self.pj, "a.1", "1", "keep as is"])
        self.assertEqual(code, 0)
        _, _, tree, *_ = L.load_project(self.pj)
        note = tree["a.1"].notes[0]
        self.assertRegex(note, r"^ANSWERED: keep as is \(Pat, \d{4}-\d\d-\d\d\); question: what about NaN\?$")
        code, _ = run(["answer", self.pj, "a.1", "1", "again"])  # no longer open
        self.assertEqual(code, 1)

    def test_stamp_steps_approves_only_those_and_records_who(self):
        self.tag_all()
        code, out = run(["stamp", self.pj, "--steps", "a.2", "--json"])
        self.assertEqual(code, 0, out)
        lock = json.loads((self.root / "ladder.lock.json").read_text())
        self.assertEqual(sorted(k for k in lock if not k.startswith("@")), ["a.2"])
        self.assertEqual(lock["a.2"]["approved_by"], "Pat")
        rep = L.check(self.pj)
        self.assertEqual(sorted(p["node"] for p in rep["tree"] if p["kind"] == "new"), ["a.1", "a.1.1"])
        # editing a.2 makes its code stale; approving it is refused until it is regenerated or retagged
        E.apply_edit(self.pj, "a.2", {"how": ["answers the number times two"]}, None, False)
        code, out = run(["stamp", self.pj, "--steps", "a.2", "--json"])
        self.assertEqual(code, 1)
        self.assertIn("refused", json.loads(out))


def run(args):
    with contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()):
        code = L.main(["ladder", *map(str, args)])
    return code, out.getvalue()


if __name__ == "__main__":
    unittest.main()

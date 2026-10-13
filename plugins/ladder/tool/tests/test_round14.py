"""Round 14 fixes (Split / Merge Container trial). Run: python3 -m unittest discover plugins/ladder/tool/tests
- replay records a fingerprint of the project's code; check warns `reference-stale` when the reference was recorded
  from other code (comments and markers do not count);
- the code fingerprint is not a replay setting (builds differ by design);
- the observe command is recorded relative to the repository, so two checkouts record the same settings."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ladder as L  # noqa: E402
import ladder_extra as X  # noqa: E402

TREE = "[a.1] Answer\n  out: a number\n  > answers 1\n"


def project(root: Path) -> Path:
    (root / "t.ladder").write_text(TREE)
    _, _, tree, _, _ = L.load_project(_write_cfg(root))
    (root / "a.ts").write_text(f"// @node a.1@{tree['a.1'].hash}\nexport const a = () => 1;\n// @end\n")
    return root / "ladder.json"


def _write_cfg(root: Path) -> Path:
    pj = root / "ladder.json"
    pj.write_text(json.dumps({"title": "t", "tree": "t.ladder", "compare": {"reference": "original", "runs": ["*"]},
                              "builds": [{"name": "a", "lang": "typescript", "files": ["a.ts"], "steps": ["a.*"],
                                          "traces": "original"},
                                         {"name": "other", "lang": "typescript", "tagged": False, "files": ["a.ts"]}]}))
    return pj


def record(root: Path, folder: str, observe: str = "") -> None:
    out = root / "traces" / folder
    out.mkdir(parents=True, exist_ok=True)
    (out / "s1.jsonl").write_text(json.dumps({"step": "a.1", "ev": "exit", "info": "200", "data": "1"}) + "\n")
    X._write_replay_meta(out, {}, [], False, [], observe, X._replay_project(out, None))


def warned(pj: Path, kind: str) -> list[dict]:
    return [w for w in L.check(pj)["warnings"] if w["kind"] == kind]


class ReferenceStale(unittest.TestCase):
    def test_code_changed_after_recording(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            pj = project(root)
            record(root, "original")
            self.assertEqual(warned(pj, "reference-stale"), [])
            (root / "a.ts").write_text((root / "a.ts").read_text().replace("=> 1", "=> 2"))
            hits = warned(pj, "reference-stale")
            self.assertEqual(len(hits), 1)
            self.assertIn("a.ts", hits[0]["msg"])

    def test_markers_and_comments_do_not_count(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            pj = project(root)
            record(root, "original")
            code = (root / "a.ts").read_text().replace("@node a.1@", "@node a.1@x").replace("export", "// a note\nexport")
            (root / "a.ts").write_text(code)
            self.assertEqual(warned(pj, "reference-stale"), [])


class ReplaySettings(unittest.TestCase):
    def test_code_is_not_a_setting_and_paths_are_repo_relative(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            pj = project(root)
            record(root, "original", observe=f"{root.resolve()}/env/rows.sh")
            record(root, "other", observe=f"{root.resolve()}/env/rows.sh")
            (root / "a.ts").write_text((root / "a.ts").read_text().replace("=> 1", "=> 2"))
            record(root, "other", observe=f"{root.resolve()}/env/rows.sh")
            meta = json.loads((root / "traces" / "other" / ".replay.json").read_text())
            self.assertEqual(meta["observe"], "<repo>/env/rows.sh")
            self.assertEqual(warned(pj, "replay-settings"), [])


if __name__ == "__main__":
    unittest.main()

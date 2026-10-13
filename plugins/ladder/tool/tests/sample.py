"""A small sample project for the tool's tests: one tree, one TypeScript build, optional traces."""
import json
import textwrap
from pathlib import Path

TREE = textwrap.dedent("""\
    [s.1] Add one
      in: a number
      out: the number plus one
      > answers the number plus one

    [s.2] Double
      in: a number
      out: twice the number
      > answers twice the number
    """)


def make(root: Path, builds=None, compare=None, extra=None) -> Path:
    """Write the project under root and return its ladder.json path."""
    (root / "sample.ladder").write_text(TREE)
    (root / "code.ts").write_text("export const x = 1\n")
    cfg = {"title": "sample", "tree": "sample.ladder",
           "builds": builds or [{"name": "code", "lang": "typescript", "mode": "literal", "files": ["code.ts"], "steps": ["s.*"]}]}
    if compare:
        cfg["compare"] = compare
    cfg.update(extra or {})
    pj = root / "ladder.json"
    pj.write_text(json.dumps(cfg, indent=2))
    return pj


def trace(root: Path, folder: str, run: str, results: dict) -> None:
    """traces/<folder>/<run>.jsonl with one exit per step: {step: value}."""
    d = root / "traces" / folder
    d.mkdir(parents=True, exist_ok=True)
    lines = []
    for step, val in results.items():
        lines.append(json.dumps({"step": step, "ev": "enter", "ms": 0}))
        lines.append(json.dumps({"step": step, "ev": "exit", "ms": 0, "data": json.dumps(val)}))
    (d / f"{run}.jsonl").write_text("\n".join(lines) + "\n")

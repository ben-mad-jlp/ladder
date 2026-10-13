"""Build a synthetic repository for timing Ladder at whole-repo scale.
usage: gen.py <out dir> <projects> <steps per project> <vocabulary terms> <links per project>
Each project: one tree of <steps> steps (groups of 5 under parents), one TypeScript file with one tagged region per
leaf step, a shared vocabulary, links to the previous <links> projects with one calls: line each. Committed and stamped."""
import json, subprocess, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "plugins" / "ladder" / "tool"))
import ladder as L  # noqa: E402

out, N, S, V, K = Path(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5])
LADDER = str(Path(__file__).resolve().parents[2] / "plugins" / "ladder" / "bin" / "ladder")
out.mkdir(parents=True)
subprocess.run(["git", "init", "-q", str(out)], check=True)

voc = ["# synthetic vocabulary\n"]
for v in range(V):
    voc.append(f"capability thing {v}\n  in: a value\n  out: a value\n  typescript: (built in) lib | thing{v}(x)\n")
(out / "vocabulary.ladder").write_text("\n".join(voc))


def tree_text(p: int) -> str:
    lines, leaves = [], []
    for g in range(S // 5):
        lines.append(f"[p{p}.{g + 1}] Group {g + 1} of project {p}\n  in: a value\n  out: a value\n  > does the four parts in order\n")
        for c in range(4):
            sid = f"p{p}.{g + 1}.{c + 1}"
            leaves.append(sid)
            calls = ""
            if g == 0 and c < K and p - c - 1 >= 0:
                calls = f"\n  calls: up{c} [p{p - c - 1}.1.1]"
            lines.append(f"  [{sid}] Part {c + 1}\n    in: a value\n    out: a value\n    uses: thing {(p * 7 + g * 4 + c) % V}{calls.replace(chr(10) + '  ', chr(10) + '    ')}\n    > answers the value changed by part {c + 1}\n")
    return "\n".join(lines), leaves


projects = []
for p in range(N):
    d = out / f"p{p}"
    d.mkdir()
    text, leaves = tree_text(p)
    (d / "tree.ladder").write_text(text)
    links = {f"up{c}": f"../p{p - c - 1}/ladder.json" for c in range(K) if p - c - 1 >= 0}
    cfg = {"title": f"project {p}", "tree": "tree.ladder", "vocabulary": "../vocabulary.ladder",
           "builds": [{"name": "code", "lang": "typescript", "mode": "literal", "files": ["code.ts"], "adopted": True}]}
    if links:
        cfg["links"] = links
    (d / "ladder.json").write_text(json.dumps(cfg, indent=2))
    (d / "code.ts").write_text("export {}\n")
    projects.append((d, leaves))

# Tag with the real hashes now that every linked project exists.
for d, leaves in projects:
    _, _, tree, *_ = L.load_project(d / "ladder.json")
    body = ["// @support header", "export {}", "// @end"]
    for sid in leaves:
        fn = "f_" + sid.replace(".", "_")
        body += [f"// @node {sid}@{tree[sid].hash}", f"export function {fn}(x: number): number {{",
                 f"  return x + {len(sid)};", "}", "// @end"]
    (d / "code.ts").write_text("\n".join(body) + "\n")

subprocess.run(["git", "-C", str(out), "add", "-A"], check=True)
subprocess.run(["git", "-C", str(out), "-c", "user.email=s@s", "-c", "user.name=s", "commit", "-qm", "synthetic"], check=True)
for d, _ in projects:
    subprocess.run([LADDER, "stamp", str(d / "ladder.json")], check=True, stdout=subprocess.DEVNULL)
subprocess.run(["git", "-C", str(out), "add", "-A"], check=True)
subprocess.run(["git", "-C", str(out), "-c", "user.email=s@s", "-c", "user.name=s", "commit", "-qm", "stamped"], check=True)
print(f"{N} projects x {S} steps, {V} terms, {K} links each, in {out}")

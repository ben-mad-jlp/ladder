"""Links between trees, and tests for the claims Ladder cannot check by reading.

Links: a step in one tree (a React client) says which step of another tree (the API) it calls:

    [authsvc.1] Sign in
      calls: api [api.1.1]

with ladder.json naming the other project:

    "links": {"api": "../../api/ladder.json"}
    "links": {"api": {"project": "../../api/ladder.json", "test": "npx vitest run harness/seam_login.test.tsx"}}

`check` resolves every link, and `stamp` records the contract of each called step (its in:, out:
and effects: lines, plus the data blocks those lines name). When the called step's contract changes,
the calling step shows as `linked-changed` until it is re-read and approved. The project being
called learns its callers from its own "links" (if it lists the calling project) and warns when an
edited step has callers.

Tests: a claim about a library (a vocabulary capability's binding and `known:` lines) or about the
seam between two trees is only as good as the code that checks it. Capabilities say how to check
their claims with `test:` lines; links with a "test" command. `ladder test` runs them and records the
result against what was tested; `check` then reports failed tests as problems, and missing or
out-of-date ones as warnings.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path

import ladder as L

CALL_RE = re.compile(r"^\s*([A-Za-z][\w-]*)\s*\[([A-Za-z0-9_.\-]+)\]\s*$")


def parse_calls(n) -> list[tuple[str, str, str]]:
    """(alias, step id, as written) for each item of a step's calls: lines."""
    out = []
    for item in getattr(n, "calls", []):
        m = CALL_RE.match(item)
        out.append((m.group(1), m.group(2), item) if m else ("", "", item))
    return out


def link_spec(cfg: dict, alias: str) -> dict | None:
    v = (cfg.get("links") or {}).get(alias)
    if v is None:
        return None
    return {"project": v} if isinstance(v, str) else dict(v)


def load_linked(cfg: dict, root: Path) -> dict[str, tuple[dict, Path, L.Tree] | str]:
    """alias -> (cfg, root, tree) of the linked project, or an error message."""
    out = {}
    for alias in (cfg.get("links") or {}):
        spec = link_spec(cfg, alias)
        pj = (root / spec["project"]).resolve()
        if not pj.exists():
            out[alias] = f"links.{alias}: {spec['project']} not found"
            continue
        try:
            c2 = json.loads(pj.read_text())
            out[alias] = (c2, pj.parent, L.parse_tree(pj.parent / c2["tree"]))
        except (SystemExit, ValueError, KeyError) as e:
            out[alias] = f"links.{alias}: cannot read {spec['project']}: {e}"
    return out


def tree_at(cfg2: dict, root2: Path, ref: str) -> L.Tree | None:
    """The linked project's tree as it was at a git ref (None if it did not exist)."""
    path = (root2 / cfg2["tree"]).resolve()
    top = subprocess.run(["git", "-C", str(path.parent), "rev-parse", "--show-toplevel"],
                         capture_output=True, text=True)
    if top.returncode != 0:
        return None
    rel = path.relative_to(Path(top.stdout.strip()).resolve()).as_posix()
    old = subprocess.run(["git", "-C", top.stdout.strip(), "show", f"{ref}:{rel}"], capture_output=True)
    if old.returncode != 0:
        return None
    with tempfile.NamedTemporaryFile("wb", suffix=".ladder", delete=False) as f:
        f.write(old.stdout)
    try:
        return L.parse_tree(Path(f.name))
    finally:
        Path(f.name).unlink()


def contract_text(tree: L.Tree, nid: str) -> str:
    """What a caller relies on: the called step's in:/out:/effects: lines and the data blocks they name."""
    n = tree[nid]
    lines = [f"[{n.id}] {n.title}"]
    for key, val in (("in", n.inputs), ("out", n.outputs), ("effects", n.effects)):
        if val:
            lines.append(f"  {key}: {' '.join(val.split())}")
    said = " ".join([n.inputs, n.outputs, n.effects])
    for name, d in getattr(tree, "data", {}).items():
        if re.search(rf"\b{re.escape(name)}\b", said):
            lines.append(d.text())
    return "\n".join(lines)


def check_links(tree: L.Tree, cfg: dict, root: Path, lock: dict, since: str | None = None):
    """Problems, approval items, warnings and the facts `stamp` records ({step: {"alias:id": text}})."""
    problems, approvals, warnings, facts = [], [], [], {}
    callers = {nid: parse_calls(n) for nid, n in tree.items() if getattr(n, "calls", None)}
    linked = load_linked(cfg, root) if (callers or cfg.get("links")) else {}
    for alias, v in linked.items():
        if isinstance(v, str):
            problems.append(dict(kind="link", node=alias, msg=v))
    old_trees: dict[str, L.Tree | None] = {}
    was_all = lock.get("@links", {})
    for nid, calls in callers.items():
        for alias, tid, written in calls:
            if not alias:
                problems.append(dict(kind="link", node=nid,
                                     msg=f"calls: '{written}' should be '<project> [<step id>]', e.g. api [api.1.1]"))
                continue
            got = linked.get(alias)
            if got is None:
                problems.append(dict(kind="link", node=nid,
                                     msg=f"calls: {written}: ladder.json has no \"links\" entry '{alias}' "
                                         f"(has {', '.join(cfg.get('links') or {}) or 'none'})"))
                continue
            if isinstance(got, str):
                continue
            c2, r2, t2 = got
            if tid not in t2:
                problems.append(dict(kind="link", node=nid, msg=f"calls: {written}: the {alias} tree has no step [{tid}]"))
                continue
            key = f"{alias}:{tid}"
            now = contract_text(t2, tid)
            facts.setdefault(nid, {})[key] = now
            if since:
                if alias not in old_trees:
                    old_trees[alias] = tree_at(c2, r2, since)
                ot = old_trees[alias]
                was = contract_text(ot, tid) if ot is not None and tid in ot else None
                when = f"since {since}"
            else:
                was = was_all.get(nid, {}).get(key)
                when = "since approval"
            if was is not None and was != now:
                approvals.append(dict(kind="linked-changed", node=nid,
                                      msg=f"calls {key}, whose contract changed {when}: " + diff_text(was, now)
                                          + "; re-read this step (and the code that handles the answer), then approve"))
    # Steps in this tree that rely on a linked-changed step: they name it ("signs in through
    # [authsvc.1]"), or they are its parent. They handle the same answer, one step removed.
    flagged = {a["node"]: a for a in approvals}
    frontier = list(flagged)
    while frontier:
        src = frontier.pop()
        for nid, n in tree.items():
            if nid in flagged:
                continue
            text = " ".join([n.title, n.inputs, n.outputs, n.effects, *n.steps, *n.notes])
            if f"[{src}]" in text or tree[src].parent == nid:
                why = "is its parent" if tree[src].parent == nid else f"refers to [{src}]"
                flagged[nid] = dict(kind="linked-changed", node=nid,
                                    msg=f"{why}, which is affected by a change in another tree "
                                        f"({flagged[src]['msg'].split(',')[0].replace('calls ', 'it calls ')}); "
                                        f"re-read this step too, then approve")
                approvals.append(flagged[nid])
                frontier.append(nid)
    # The other direction: steps here that projects we link to call.
    for alias, got in linked.items():
        if isinstance(got, str):
            continue
        c2, r2, t2 = got
        back = [a for a in (c2.get("links") or {}) if
                (r2 / link_spec(c2, a)["project"]).resolve() == (root / "ladder.json").resolve()
                or (r2 / link_spec(c2, a)["project"]).resolve().parent == root.resolve()]
        if not back:
            continue
        own_old = tree_at(cfg, root, since) if since else None
        for cid, cn in t2.items():
            for a, tid, _ in parse_calls(cn):
                if a not in back or tid not in tree:
                    continue
                if since:
                    # compare the contract callers rely on with this tree as it was at the ref
                    changed = own_old is not None and tid in own_old and \
                        contract_text(own_old, tid) != contract_text(tree, tid)
                    when = f"since {since}"
                else:
                    was = lock.get(tid, {}).get("hash") if isinstance(lock.get(tid), dict) else None
                    changed = bool(was) and was != tree[tid].hash
                    when = "since approval"
                if changed:
                    warnings.append(dict(kind="has-callers", node=tid,
                                         msg=f"{'its contract changed' if since else 'edited'} {when}, and it is called by "
                                             f"{alias} [{cid}]: that step shows as linked-changed until re-read and approved; "
                                             f"update its English in the same change, or tell whoever owns it"))
    return problems, approvals, warnings, facts


def diff_text(was: str, now: str) -> str:
    a, b = was.splitlines(), now.splitlines()
    gone = [l.strip() for l in a if l not in b]
    new = [l.strip() for l in b if l not in a]
    parts = []
    if gone:
        parts.append("was " + " | ".join(gone))
    if new:
        parts.append("now " + " | ".join(new))
    return "; ".join(parts) or "reordered"


def prompt_text(ids: list[str], tree: L.Tree, cfg: dict, root: Path) -> str:
    """For a generator prompt: the contracts of the steps in other trees that these steps call."""
    wanted = [(nid, c) for nid in ids if nid in tree for c in parse_calls(tree[nid]) if c[0]]
    if not wanted:
        return ""
    linked = load_linked(cfg, root)
    out = ["=== Steps in other trees that these steps call (what they accept and answer; the code must "
           "match them exactly):"]
    seen = set()
    for nid, (alias, tid, _) in wanted:
        got = linked.get(alias)
        if isinstance(got, tuple) and tid in got[2] and (alias, tid) not in seen:
            seen.add((alias, tid))
            out.append(f"--- {alias} {contract_text(got[2], tid)}")
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------- tests

def capability_tests(cap) -> list[tuple[str, str]]:
    """(binding key or '*', command) for each `test:` line: 'test: typescript | npx vitest run x.test.ts'."""
    out = []
    for t in getattr(cap, "tests", []):
        key, sep, cmd = t.partition("|")
        out.append((key.strip(), cmd.strip()) if sep else ("*", t.strip()))
    return out


def command_files_hash(cmd: str, cwd: Path | None) -> str:
    """Hash of the files a test command names (scripts and test files), so editing a test makes its
    recorded result stale. Arguments that are not files under cwd are ignored."""
    import shlex
    if cwd is None:
        return ""
    try:
        words = shlex.split(cmd)
    except ValueError:
        words = cmd.split()
    h = hashlib.sha1()
    for w in words:
        p = (cwd / w)
        try:
            if p.is_file() and p.stat().st_size < 5_000_000:
                h.update(w.encode() + b"\0" + p.read_bytes())
        except OSError:
            continue
    return h.hexdigest()[:8]


def capability_test_hash(cap, key: str, cmd: str, cwd: Path | None = None) -> str:
    t = "\n".join([cap.inputs, cap.outputs, cap.bindings.get(key, "") if key != "*" else
                   json.dumps(cap.bindings, sort_keys=True), *cap.known, cmd, command_files_hash(cmd, cwd)])
    return hashlib.sha1(" ".join(t.split()).encode()).hexdigest()[:8]


def link_test_hash(tree: L.Tree, alias: str, linked, cmd: str, cwd: Path | None = None) -> str:
    got = linked.get(alias)
    parts = [cmd, command_files_hash(cmd, cwd)]
    for nid, n in tree.items():
        for a, tid, _ in parse_calls(n):
            if a == alias:
                parts.append(f"{nid}@{n.hash}")
                if isinstance(got, tuple) and tid in got[2]:
                    parts.append(contract_text(got[2], tid))
    return hashlib.sha1("\n".join(parts).encode()).hexdigest()[:8]


def build_keys(cfg: dict) -> set[str]:
    """The binding keys this project's builds answer to: each build's name and language."""
    return {k for b in cfg.get("builds", []) if b.get("tagged", True) is not False
            for k in (b.get("name"), b.get("lang")) if k}


def all_tests(cfg: dict, root: Path, tree: L.Tree) -> list[dict]:
    """Every test this project declares: {key, what, cmd, hash, users}. A capability's tests count only
    when this project's steps use it, and only for bindings its builds have ("*" for all): with a
    vocabulary shared by an API and a client project, each runs and reports its own."""
    cwd = root / cfg.get("check_cwd", ".")   # where `ladder test` runs the commands
    out = []
    vocab = L.load_vocabulary(cfg, root) or {}
    users: dict[str, list[str]] = {}
    for nid, n in tree.items():
        for u in n.uses:
            users.setdefault(u, []).append(nid)
    keys = build_keys(cfg)
    for name, cap in vocab.items():
        if name not in users:
            continue
        for key, cmd in capability_tests(cap):
            if key != "*" and key not in keys:
                continue
            out.append(dict(key=f"capability {name} [{key}]", what=f"capability '{name}' ({key})", cmd=cmd,
                            hash=capability_test_hash(cap, key, cmd, cwd), users=users.get(name, [])))
    linked = load_linked(cfg, root) if cfg.get("links") else {}
    for alias in (cfg.get("links") or {}):
        spec = link_spec(cfg, alias)
        callers = [nid for nid, n in tree.items() if any(a == alias for a, _, _ in parse_calls(n))]
        if spec.get("test"):
            out.append(dict(key=f"link {alias}", what=f"the seam with {alias}", cmd=spec["test"],
                            hash=link_test_hash(tree, alias, linked, spec["test"], cwd), users=callers))
    return out


def check_tests(cfg: dict, root: Path, tree: L.Tree, code: dict) -> tuple[list[dict], list[dict]]:
    """(problems, warnings) about tests: failed ones are problems; missing or stale ones warnings."""
    problems, warnings = [], []
    results = code.get("@tests", {})
    tests = all_tests(cfg, root, tree)
    tested_caps = {t["key"].split(" [")[0][len("capability "):] for t in tests if t["key"].startswith("capability ")}
    vocab = L.load_vocabulary(cfg, root) or {}
    used = {u for n in tree.values() for u in n.uses}
    for name in sorted(used & set(vocab) - tested_caps):
        # Only claims need a test: a capability with no known: lines has nothing beyond its binding to check.
        if vocab[name].known:
            warnings.append(dict(kind="untested-capability", node=name,
                                 msg="nothing checks that the binding behaves as its known: lines say; add a "
                                     "`test: <build or language> | <command>` line and run `ladder test`"))
    for alias in (cfg.get("links") or {}):
        spec = link_spec(cfg, alias)
        callers = [nid for nid, n in tree.items() if any(a == alias for a, _, _ in parse_calls(n))]
        if callers and not spec.get("test"):
            warnings.append(dict(kind="untested-link", node=alias,
                                 msg=f"{', '.join(callers)} call {alias}, but no test runs both sides together; "
                                     f"add \"test\": \"<command>\" to links.{alias}"))
    for t in tests:
        r = results.get(t["key"])
        if r is None:
            warnings.append(dict(kind="test-not-run", node=t["key"], msg=f"never run; `ladder test` runs `{t['cmd']}`"))
        elif r.get("hash") != t["hash"]:
            warnings.append(dict(kind="test-stale", node=t["key"],
                                 msg=f"what it tests changed since it last ran ({r.get('at', '?')}); run `ladder test`"))
        elif not r.get("ok"):
            problems.append(dict(kind="test-failed", node=t["key"],
                                 msg=f"failed when last run ({r.get('at', '?')}): {r.get('tail', '')[:600]}"))
    return problems, warnings


ASSERT_RE = re.compile(r"(AssertionError|Assert\.|expected|Expected|received|Received|Actual|actual:|"
                       r"\bFAIL\b|FAILED|^Failed |Error:|Exception:|✗|×)")


def failure_lines(output: str, limit: int = 10) -> list[str]:
    """The lines that say why a test failed: assertion messages with their expected and received
    values (vitest, jest, xunit, pytest), then the last lines of output. Source excerpts are skipped."""
    noise = re.compile(r"^(\d*\s*\||❯|at |[-+] (Expected|Received)$|[⎯─=\-\s\[\]\d/]+$)")
    lines = [l.strip() for l in output.strip().splitlines() if l.strip() and not noise.match(l.strip())]
    picked = [l for l in lines if ASSERT_RE.search(l)]
    seen, out = set(), []
    for l in picked + lines[-3:]:
        if l not in seen:
            seen.add(l)
            out.append(l)
    return out[:limit]


def run_tests(pj: Path, only: list[str] | None = None) -> int:
    import datetime
    cfg, root, tree, _, _ = L.load_project(pj)
    tests = all_tests(cfg, root, tree)
    if only:
        tests = [t for t in tests if any(o in t["key"] for o in only)]
    if not tests:
        print("no tests declared (capability `test:` lines, or \"test\" on a links entry)")
        return 0
    code = L.load_code(root)
    results = code.setdefault("@tests", {})
    cwd = root / cfg.get("check_cwd", ".")
    failed = 0
    for t in tests:
        print(f"{t['what']}: {t['cmd']}")
        res = subprocess.run(t["cmd"], shell=True, cwd=cwd, capture_output=True, text=True)
        tail = failure_lines(res.stdout + res.stderr)
        ok = res.returncode == 0
        failed += not ok
        print(f"  {'ok' if ok else 'FAILED (exit ' + str(res.returncode) + ')'}")
        if not ok:
            print("    " + "\n    ".join(tail))
        results[t["key"]] = dict(hash=t["hash"], ok=ok, at=datetime.date.today().isoformat(),
                                 tail=" / ".join(tail)[:600] if not ok else "")
    (root / L.CODE_FILE).write_text(json.dumps(code, indent=2, sort_keys=True) + "\n")
    print(f"\n{len(tests) - failed} of {len(tests)} passed; results recorded in ladder.code.json")
    return 1 if failed else 0

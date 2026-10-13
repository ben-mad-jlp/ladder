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
called learns its callers from its own "links" (if it lists the calling project), or from every project a
ladder.repo.json lists, and warns when an edited step has callers.

Tests: a claim about a library (a vocabulary capability's binding and `known:` lines) or about the
seam between two trees is only as good as the code that checks it. Capabilities say how to check
their claims with `test:` lines; links with a "test" command. `ladder test` runs them and records the
result against what was tested; `check` then reports failed tests as problems, and missing or
out-of-date ones as warnings.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

import ladder as L

CALL_RE = re.compile(r"^\s*([A-Za-z][\w-]*)\s*\[([A-Za-z0-9_.\-]+)\]\s*$")


MULTI_CALL_RE = re.compile(r"^\s*([A-Za-z][\w-]*)\s*((?:\[[A-Za-z0-9_.\-]+\]\s*)+)$")


def parse_calls(n) -> list[tuple[str, str, str]]:
    """(alias, step id, as written) for each item of a step's calls: lines. An item may name several steps of one
    tree: `scanner [shc.20.13] [shc.20.14]` (shipping round: the natural way to write it was refused)."""
    out = []
    for item in getattr(n, "calls", []):
        m = CALL_RE.match(item)
        if m:
            out.append((m.group(1), m.group(2), item))
            continue
        mm = MULTI_CALL_RE.match(item)
        if mm:
            out += [(mm.group(1), tid, item) for tid in re.findall(r"\[([A-Za-z0-9_.\-]+)\]", mm.group(2))]
            continue
        out.append(("", "", item))
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
            c2 = L.linked_config(pj)
            out[alias] = (c2, pj.parent, L.linked_tree(pj.parent / c2["tree"]))
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


def is_target(tree, tid: str) -> bool:
    """Whether a calls: target exists in a tree: a step, or a data block (a type the caller uses: shipping round)."""
    return tid in tree or tid in getattr(tree, "data", {})


def data_text(tree, name: str) -> str:
    d = tree.data[name]
    lines = [f"data {name}"]
    lines += [f"  {name}.{k}: {' '.join(v.split())}" for k, v in d.fields]
    lines += [f"  {name} rule: {' '.join(r.split())}" for r in d.rules]
    return "\n".join(lines)


def contract_text(tree: L.Tree, nid: str) -> str:
    """What a caller relies on: the called step's in:/out:/effects: lines and the data blocks they name; for a data
    block named in calls:, the block itself."""
    if nid not in tree and nid in getattr(tree, "data", {}):
        return data_text(tree, nid)
    n = tree[nid]
    lines = [f"[{n.id}] {n.title}"]
    for key, val in (("in", n.inputs), ("out", n.outputs), ("effects", n.effects)):
        if val:
            lines.append(f"  {key}: {' '.join(val.split())}")
    for name, d in contract_data(tree, nid).items():
        lines.append(f"  data {name}")
        # notes render as before (`Name.note: ...`), so contracts recorded by earlier stamps still match
        lines += [f"  {name}.{k}: {' '.join(v.split())}" for k, v in d.fields]
        lines += [f"  {name} rule: {' '.join(r.split())}" for r in d.rules]
    return "\n".join(lines)


STEP_REF = re.compile(r"\[([A-Za-z0-9_.\-]+)\]")


def behind(tree: L.Tree, nid: str) -> dict[str, list[str]]:
    """The steps a step's English relies on, transitively ("answers what [sa.4] answers", "checks it with
    [as.9]"), each with the path that reaches it: {step: [nid, ..., step]}. The called step's own contract is
    compared separately; these are what produce its answer."""
    paths: dict[str, list[str]] = {}
    frontier = [(nid, [nid])]
    while frontier:
        cur, path = frontier.pop()
        n = tree[cur]
        text = " ".join([n.title, n.inputs, n.outputs, n.effects, *n.steps, *n.notes])
        for ref in STEP_REF.findall(text):
            if ref in tree and ref != nid and ref not in paths:
                paths[ref] = path + [ref]
                frontier.append((ref, path + [ref]))
    return paths


def behind_hashes(tree: L.Tree, nid: str) -> dict[str, str]:
    return {x: tree[x].hash for x in behind(tree, nid)}


def contract_data(tree: L.Tree, nid: str) -> dict:
    """The data blocks a step's in:/out:/effects: lines name (its request and answer shapes)."""
    n = tree[nid]
    said = " ".join([n.inputs, n.outputs, n.effects])
    return {name: d for name, d in getattr(tree, "data", {}).items()
            if re.search(rf"\b{re.escape(name)}\b", said)}


TYPE_DECL_RE = re.compile(r"\b(?:interface|type|class|record|struct|enum)\s+([A-Z][A-Za-z0-9_]*)")


def hand_written_types(cfg: dict, root: Path, name: str) -> list[tuple[str, str, int]]:
    """(file, type name, line) for types in this project's hand-written files (builds' "reads") whose
    name starts with a data block's name: ClockInRequestDTO for data ClockInRequest."""
    out = []
    for b in cfg.get("builds", []):
        for f in b.get("reads", []):
            try:
                lines = (root / f).read_text().splitlines()
            except OSError:
                continue
            for i, l in enumerate(lines, 1):
                for m in TYPE_DECL_RE.finditer(l):
                    t = m.group(1)
                    if t == name or (t.startswith(name) and t[len(name):] in ("DTO", "Dto", "Model", "Body", "Type", "Data")):
                        out.append((f, t, i))
    return out


def only_block(text: str, name: str) -> str:
    return "\n".join(l for l in text.splitlines()
                     if l.strip().startswith((f"{name}.", f"{name} rule:", f"data {name}")))


def changed_data(was: str, now: str) -> list[str]:
    """Names of data blocks whose lines differ between two contract texts."""
    a, b = set(was.splitlines()), set(now.splitlines())
    names = set()
    for l in a ^ b:
        m = re.match(r"^\s+(?:data )?([A-Z][A-Za-z0-9_]*)[. ]", l)
        if m:
            names.add(m.group(1))
    return sorted(names)


def linked_pending(c2: dict, r2: Path, t2: L.Tree, since: str | None, depth: int) -> dict[str, str]:
    """Steps of a linked project that are themselves waiting on a change in a further tree
    ({step id: why}), so a change reaches callers more than one link away (api -> library -> screen)."""
    if depth <= 0:
        return {}
    lp = r2 / "ladder.lock.json"
    key = (str(r2.resolve()), since, depth, L._stamp(r2 / c2["tree"]), L._stamp(lp) if lp.exists() else None)
    if key in _PENDING:
        return _PENDING[key]
    lock2 = L.linked_lock(r2)
    if since is None and not any(not k.startswith("@") for k in lock2) and c2.get("baseline"):
        since = c2["baseline"]
    try:
        _, appr, _, _ = check_links(t2, c2, r2, lock2, since, depth - 1)
    except Exception:
        _PENDING[key] = {}
        return {}
    _PENDING[key] = {a["node"]: a["msg"] for a in appr if a["kind"] == "linked-changed"}
    return _PENDING[key]


# linked_pending's answers for this run, keyed by the linked project's tree and lock as they are on disk: `check --all`
# asks about the same projects from many callers. (A project further along may change in the same run only when a
# command writes it, which no command that follows links does.)
_PENDING: dict = {}


STEP_REF_RE = re.compile(r"\[([A-Za-z][A-Za-z0-9_-]*(?:\.[0-9]+)+)\]")


def link_shape_warnings(tree: L.Tree, cfg: dict, root: Path) -> list[dict]:
    """Round 15: links that carry nothing.
    - rule-diverged: a named rule with the same name in a linked project says something else (a change made in one tree only);
    - uncalled-reference: a step names another tree's step ([upl.2.1]) without a `calls:` line, so changes there never reach it;
    - link-unused: a link that no `calls:` line uses, in either direction."""
    out: list[dict] = []
    linked = {a: v for a, v in load_linked(cfg, root).items() if not isinstance(v, str)}
    # (no early return without links: a project that links to nothing may still name other projects' steps)
    norm = lambda t: " ".join(t.split()).lower()
    rules = getattr(tree, "rules", {})
    # every project reachable through links (an API and its scanner are often linked only through the library)
    me_pj = (root / "ladder.json").resolve()
    seen, queue, reach = {me_pj}, [(cfg, root, "")], []
    while queue:
        c, r, path = queue.pop(0)
        for a in (c.get("links") or {}):
            pj = (r / link_spec(c, a)["project"]).resolve()
            if pj in seen or not pj.exists():
                continue
            seen.add(pj)
            try:
                c2 = L.linked_config(pj)
                t2 = L.linked_tree(pj.parent / c2["tree"])
            except (SystemExit, ValueError, KeyError, OSError):
                continue
            name2 = f"{path}{a}" if not path else f"{path} -> {a}"
            reach.append((name2, t2))
            queue.append((c2, pj.parent, name2))
    for where, t2 in reach:
        for name, text in rules.items():
            other = getattr(t2, "rules", {}).get(name)
            if other is not None and norm(other) != norm(text):
                out.append(dict(kind="rule-diverged", node=name,
                                msg=f"rule {name} says \"{' '.join(text.split())}\" here and \"{' '.join(other.split())}\" in "
                                    f"{where}: a change made in one tree has not reached the other; make them agree (or give "
                                    f"them different names when they are different rules)"))
    called_aliases = set()
    for nid, n in tree.items():
        targets = {tid for _, tid, _ in parse_calls(n)}
        called_aliases |= {a for a, _, _ in parse_calls(n) if a}
        foreign, unlinked = [], []
        # what the step does (not its notes, which may point at another tree to explain something)
        said = "\n".join([n.title, n.inputs, n.outputs, n.effects, *n.steps])
        for ref in dict.fromkeys(STEP_REF_RE.findall(said)):
            if ref in tree or ref in targets:
                continue
            owner = next((a for a, (_, _, t2) in linked.items() if ref in t2), None)
            if owner:
                foreign.append(f"{owner} [{ref}]")
            elif ref not in tree:
                # a step of a project this one does not link to yet (shipping round: ~100 calls were invisible
                # until the first link existed)
                where = repo_step_owner(root, ref)
                if where:
                    unlinked.append(f"[{ref}] of {where}")
        if unlinked:
            out.append(dict(kind="uncalled-reference", node=nid,
                            msg=f"[{nid}] names {', '.join(unlinked)}, a project this one does not link to: changes there "
                                f"are never reported here; add a \"links\" entry and a `calls:` line"))
        if foreign:
            out.append(dict(kind="uncalled-reference", node=nid,
                            msg=f"[{nid}] names {', '.join(foreign)} without a `calls:` line: changes there are never "
                                f"reported here; add `calls: {', '.join(foreign)}`"))
    me = (root / "ladder.json").resolve()
    for alias, (c2, r2, t2) in linked.items():
        if alias in called_aliases:
            continue
        back = {a for a in (c2.get("links") or {}) if (r2 / link_spec(c2, a)["project"]).resolve() == me}
        if any(a in back for n in t2.values() for a, _, _ in parse_calls(n)):
            continue
        out.append(dict(kind="link-unused", node=alias,
                        msg=f"the link to {alias} carries nothing: no step here calls it and none of its steps calls this "
                            f"project, so changes on either side are never reported on the other; add `calls:` lines to the "
                            f"steps that use it"))
    return out


def check_links(tree: L.Tree, cfg: dict, root: Path, lock: dict, since: str | None = None, depth: int = 3):
    """Problems, approval items, warnings and the facts `stamp` records ({step: {"alias:id": text}})."""
    problems, approvals, warnings, facts = [], [], [], {}
    pending_cache: dict[str, dict[str, str]] = {}
    callee_locks: dict[str, dict] = {}
    callers = {nid: parse_calls(n) for nid, n in tree.items() if getattr(n, "calls", None)}
    linked = load_linked(cfg, root) if (callers or cfg.get("links")) else {}
    for alias, v in linked.items():
        if isinstance(v, str):
            problems.append(dict(kind="link", node=alias, msg=v))
    old_trees: dict[str, L.Tree | None] = {}
    drift_seen: set = set()
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
            if not is_target(t2, tid):
                problems.append(dict(kind="link", node=nid, msg=f"calls: {written}: the {alias} tree has no step or "
                                                                 f"data block [{tid}]"))
                continue
            is_data = tid not in t2
            key = f"{alias}:{tid}"
            if alias not in callee_locks:
                lp = r2 / "ladder.lock.json"
                try:
                    callee_locks[alias] = json.loads(lp.read_text()) if lp.exists() else {}
                except ValueError:
                    callee_locks[alias] = {}
            approved = callee_locks[alias].get(tid, {}).get("hash")
            if not is_data and (approved is None or not t2[tid].tag_matches(approved)):
                warnings.append(dict(kind="linked-unapproved", node=nid,
                                     msg=f"calls {key}, which the {alias} project has "
                                         + ("never approved" if approved is None else "changed since its approval")
                                         + f": its English may still change; stamp {alias} first, or re-read this step "
                                           f"after {alias} is approved"))
            now = contract_text(t2, tid)
            facts.setdefault(nid, {})[key] = now
            now_behind = behind_hashes(t2, tid) if not is_data else {}
            facts[nid][key + "#behind"] = json.dumps(now_behind, sort_keys=True)
            if since:
                if alias not in old_trees:
                    old_trees[alias] = tree_at(c2, r2, since)
                ot = old_trees[alias]
                was = contract_text(ot, tid) if ot is not None and is_target(ot, tid) else None
                was_behind = behind_hashes(ot, tid) if ot is not None and tid in ot else None
                when = f"since {since}"
            else:
                was = was_all.get(nid, {}).get(key)
                raw = was_all.get(nid, {}).get(key + "#behind")
                was_behind = json.loads(raw) if raw else None
                when = "since approval"
            if alias not in pending_cache:
                pending_cache[alias] = linked_pending(c2, r2, t2, since, depth)
            if was == now and tid in pending_cache[alias]:
                approvals.append(dict(kind="linked-changed", node=nid,
                                      msg=f"calls {key}, which is itself waiting on a change in another tree "
                                          f"({pending_cache[alias][tid].split(';')[0]}); its answers may differ: re-read it "
                                          f"and this step, then approve"))
            if was is not None and was == now and was_behind is not None:
                paths = behind(t2, tid)
                moved = sorted(x for x in set(now_behind) | set(was_behind) if now_behind.get(x) != was_behind.get(x))
                if moved:
                    via = "; ".join(f"[{x}]" + (f" (through {' -> '.join('[' + p + ']' for p in paths[x][1:-1])})"
                                                if x in paths and len(paths[x]) > 2 else "")
                                    + ("" if x in now_behind else " (no longer referred to)") for x in moved)
                    approvals.append(dict(kind="linked-changed", node=nid,
                                          msg=f"calls {key}, whose contract is unchanged, but steps its English relies on "
                                              f"changed {when}: {via}; its answers may differ (a new refusal, a changed "
                                              f"message): re-read those steps in the {alias} tree and this one, then approve"))
            if was is not None and was != now:
                approvals.append(dict(kind="linked-changed", node=nid,
                                      msg=f"calls {key}, whose contract changed {when}: " + diff_text(was, now)
                                          + "; re-read this step (and the code that handles the answer), then approve"))
                for name in changed_data(was, now):
                    for f, tname, line in hand_written_types(cfg, root, name):
                        if (f, tname) in drift_seen:
                            continue
                        drift_seen.add((f, tname))
                        warnings.append(dict(kind="type-drift", node=f"{f}:{line}",
                                             msg=f"declares {tname}, which looks like the {alias} tree's data {name} "
                                                 f"({diff_text(only_block(was, name), only_block(now, name))}). This file is read, not "
                                                 f"generated, so nothing updates it: change it by hand, or give it a "
                                                 f"build whose data blocks follow the {alias} tree's"))
    # Steps in this tree that rely on a linked-changed step: their English names it ("signs in
    # through [authsvc.1]"). They handle the same answer, one step removed.
    flagged = {a["node"]: a for a in approvals}
    frontier = list(flagged)
    while frontier:
        src = frontier.pop()
        for nid, n in tree.items():
            if nid in flagged:
                continue
            text = " ".join([n.title, n.inputs, n.outputs, n.effects, *n.steps, *n.notes])
            if f"[{src}]" in text:     # its English names the step (not merely its parent: round 6's F9)
                why = f"refers to [{src}]"
                flagged[nid] = dict(kind="linked-changed", node=nid,
                                    msg=f"{why}, which is affected by a change in another tree "
                                        f"({flagged[src]['msg'].split(',')[0].replace('calls ', 'it calls ')}); "
                                        f"re-read this step too, then approve")
                approvals.append(flagged[nid])
                frontier.append(nid)
    # The other direction: steps here that other projects call.
    # One warning per changed step, naming every caller (round 20: an API step called from many screens).
    direct: dict[str, list[str]] = {}
    indirect: dict[tuple[str, str, str], list[str]] = {}
    when = f"since {since}" if since else "since approval"
    own_old = None
    for alias, c2, r2, t2, back in caller_projects(cfg, root, linked):
        if since and own_old is None:
            own_old = tree_at(cfg, root, since)
        for cid, cn in t2.items():
            for a, tid, _ in parse_calls(cn):
                if a not in back or tid not in tree:
                    continue
                if since:
                    # compare the contract callers rely on with this tree as it was at the ref
                    changed = own_old is not None and tid in own_old and \
                        contract_text(own_old, tid) != contract_text(tree, tid)
                else:
                    was = lock.get(tid, {}).get("hash") if isinstance(lock.get(tid), dict) else None
                    changed = bool(was) and not tree[tid].tag_matches(was)
                if not changed:
                    # a step the called step relies on changed: callers see a different answer too
                    for x, path in behind(tree, tid).items():
                        if since:
                            moved = own_old is not None and (x not in own_old or own_old[x].hash != tree[x].hash)
                        else:
                            wx = lock.get(x, {}).get("hash") if isinstance(lock.get(x), dict) else None
                            moved = bool(wx) and not tree[x].tag_matches(wx)
                        if moved:
                            key = (x, tid, " -> ".join("[" + p + "]" for p in path))
                            indirect.setdefault(key, []).append(f"{alias} [{cid}]")
                if changed:
                    direct.setdefault(tid, []).append(f"{alias} [{cid}]")

    def who(names: list[str]) -> str:
        return ", ".join(names[:8]) + (f" and {len(names) - 8} more" if len(names) > 8 else "")
    for (x, tid, path), names in indirect.items():
        warnings.append(dict(kind="has-callers", node=x,
                             msg=f"edited {when}, and [{tid}] relies on it ({path}), which {who(names)} "
                                 f"call{'s' if len(names) == 1 else ''}: "
                                 f"{'that step shows' if len(names) == 1 else 'those steps show'} as linked-changed "
                                 f"until re-read and approved"))
    for tid, names in direct.items():
        warnings.append(dict(kind="has-callers", node=tid,
                             msg=f"{'its contract changed' if since else 'edited'} {when}, and it is called by "
                                 f"{who(names)}: {'that step shows' if len(names) == 1 else 'those steps show'} as "
                                 f"linked-changed until re-read and approved; update their English in the same change, "
                                 f"or tell whoever owns them"))
    return problems, approvals, warnings, facts


def links_here(c2: dict, r2: Path, root: Path) -> list[str]:
    """The aliases of project c2 (in folder r2) that point at the project in `root`."""
    me = (root / "ladder.json").resolve()
    out = []
    for a in (c2.get("links") or {}):
        spec = link_spec(c2, a)
        if not spec or "project" not in spec:
            continue
        p = (r2 / spec["project"]).resolve()
        if p == me or p.parent == root.resolve():
            out.append(a)
    return out


def caller_projects(cfg: dict, root: Path, linked: dict) -> list[tuple[str, dict, Path, L.Tree, list[str]]]:
    """Projects whose steps may call this one: (name, cfg, folder, tree, their aliases for this project). The projects
    this one links to, when they link back; and, under a ladder.repo.json with "projects", every project there that
    links here (round 20: an API called by many screens lists none of them, so an edited step warned no one)."""
    out, seen = [], set()
    for alias, got in linked.items():
        if isinstance(got, str):
            continue
        c2, r2, t2 = got
        back = links_here(c2, r2, root)
        if back:
            out.append((alias, c2, r2, t2, back))
            seen.add(r2.resolve())
    found = L.find_repo(root)
    if not found or not found[0].get("projects"):
        return out
    me = root.resolve()
    for r2, c2, back in reverse_links(*found).get(me, []):
        if r2 in seen:
            continue
        try:
            t2 = L.linked_tree(r2 / c2["tree"])
        except (SystemExit, OSError, KeyError):
            continue
        seen.add(r2)
        out.append((os.path.relpath(r2, me), c2, r2, t2, back))
    return out


_STEP_OWNERS: dict = {}


def repo_step_owner(root: Path, ref: str) -> str | None:
    """The project (folder, relative to this one) whose tree has step `ref`, among those ladder.repo.json lists."""
    found = L.find_repo(root)
    if not found or not found[0].get("projects"):
        return None
    repo, rdir = found
    if rdir not in _STEP_OWNERS:
        owners: dict[str, Path] = {}
        for pj in L.repo_projects(repo, rdir):
            try:
                c2 = L.linked_config(pj)
                for sid in L.linked_tree(pj.parent / c2["tree"]):
                    owners.setdefault(sid, pj.parent.resolve())
            except (SystemExit, OSError, KeyError, ValueError):
                continue
        _STEP_OWNERS[rdir] = owners
    owner = _STEP_OWNERS[rdir].get(ref)
    if owner is None or owner == root.resolve():
        return None
    return os.path.relpath(owner, root.resolve())


_REVERSE: dict = {}


def reverse_links(repo: dict, rdir: Path) -> dict[Path, list[tuple[Path, dict, list[str]]]]:
    """For a repository: each project folder -> the projects that link to it (folder, config, their aliases for it).
    Built once per run; a check that follows links several levels deep asks for it many times."""
    if rdir in _REVERSE:
        return _REVERSE[rdir]
    index: dict[Path, list] = {}
    for other in L.repo_projects(repo, rdir):
        r2 = other.parent.resolve()
        try:
            c2 = L.linked_config(other)
        except SystemExit:
            continue
        targets: dict[Path, list[str]] = {}
        for a in (c2.get("links") or {}):
            spec = link_spec(c2, a)
            if spec and "project" in spec:
                targets.setdefault((r2 / spec["project"]).resolve().parent, []).append(a)
        for t, aliases in targets.items():
            if t != r2:
                index.setdefault(t, []).append((r2, c2, aliases))
    _REVERSE[rdir] = index
    return index


def diff_text(was: str, now: str) -> str:
    """What changed between two contract texts, line by line: `out: A -> B`, `added
    ClockInRequest.source: ...` (a new field of a data block the step takes or answers)."""
    def keyed(text):
        out = {}
        for l in text.splitlines():
            t = l.strip()
            k = t.split(": ", 1)[0] if ": " in t else t
            out[k] = t.split(": ", 1)[1] if ": " in t else ""
        return out
    a, b = keyed(was), keyed(now)
    parts = []
    for k in a:
        if k in b and a[k] != b[k]:
            parts.append(f"{k}: was {a[k]}; now {b[k]}")
        elif k not in b:
            parts.append(f"removed {k}" + (f": {a[k]}" if a[k] else ""))
    for k in b:
        if k not in a and not k.startswith("data "):
            field = re.match(r"^([A-Z][A-Za-z0-9_]*)\.(\w+)$", k)
            what = f"data {field.group(1)} gained field {field.group(2)}" if field else f"added {k}"
            parts.append(what + (f": {b[k]}" if b[k] else ""))
    return " | ".join(parts) or "reordered"


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
        if isinstance(got, tuple) and is_target(got[2], tid) and (alias, tid) not in seen:
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


def capability_test_hash(cap, key: str, cmd: str, cwd: Path | None = None, schema_facts: str = "") -> str:
    t = "\n".join([cap.inputs, cap.outputs, cap.bindings.get(key, "") if key != "*" else
                   json.dumps(cap.bindings, sort_keys=True), *cap.known, cmd, command_files_hash(cmd, cwd),
                   schema_facts])
    return hashlib.sha1(" ".join(t.split()).encode()).hexdigest()[:8]


def link_test_hash(tree: L.Tree, alias: str, linked, cmd: str, cwd: Path | None = None) -> str:
    got = linked.get(alias)
    parts = [cmd, command_files_hash(cmd, cwd)]
    for nid, n in tree.items():
        for a, tid, _ in parse_calls(n):
            if a == alias:
                parts.append(f"{nid}@{n.hash}")
                if isinstance(got, tuple) and is_target(got[2], tid):
                    parts.append(contract_text(got[2], tid))
    return hashlib.sha1("\n".join(parts).encode()).hexdigest()[:8]


MARKER_LINE = re.compile(r"^\s*(?://|#|--)\s*@(?:node|contract|support|end)\b")


def code_hash(p: Path) -> str:
    """A code file's hash for test records: without Ladder's marker lines and with line endings normalised, so a
    retag or a stamp (markers only) does not make a passed test stale (shipping round: twice in one project)."""
    text = p.read_text(errors="surrogateescape")
    kept = "\n".join(l for l in text.splitlines() if not MARKER_LINE.match(l))
    return hashlib.sha1(kept.encode(errors="surrogateescape")).hexdigest()


def project_test_hash(root: Path, cmd: str, files: list[str], cwd: Path | None = None) -> str:
    parts = [cmd, command_files_hash(cmd, cwd)]
    for f in sorted(files):
        p = root / f
        parts.append(f + ":" + (code_hash(p) if p.exists() else "missing"))
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
    schemas = None
    for name, cap in vocab.items():
        if name not in users:
            continue
        for key, cmd in capability_tests(cap):
            if key != "*" and key not in keys:
                continue
            facts = ""
            if cap.tables and cfg.get("schemas"):
                # a test that touches tables goes stale when their schema changes (round 6: a new
                # required column broke the test's own insert)
                import ladder_schema as S
                if schemas is None:
                    schemas = S.load_schemas(cfg, root)
                for t in cap.tables:
                    m = S.ENTITY_REF_RE.match(t)
                    if m:
                        sname, e, _, _ = S.resolve(S.Ref(t, m.group(1), m.group(2), None, "reads"), schemas)
                        if e is not None:
                            facts += f"{sname}:{e.name} {S.members_fact(e)}\n"
            out.append(dict(key=f"capability {name} [{key}]", what=f"capability '{name}' ({key})", cmd=cmd,
                            hash=capability_test_hash(cap, key, cmd, cwd, facts), users=users.get(name, [])))
    for t in cfg.get("tests") or []:
        # The project's own behaviour tests (the slice's unit or integration tests). They test the code, so a
        # change to any file of the builds they name (all tagged builds by default) makes their result stale.
        names = t.get("builds") or [b["name"] for b in cfg.get("builds", []) if b.get("tagged", True) is not False]
        files = [f for b in cfg.get("builds", []) if b["name"] in names for f in b.get("files", [])]
        out.append(dict(key=f"tests {t['name']}", what=f"the project's tests '{t['name']}'", cmd=t["command"],
                        hash=project_test_hash(root, t["command"], files, cwd), users=[]))
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
    if not cfg.get("tests") and any(b.get("tagged", True) is not False and b.get("steps") for b in cfg.get("builds", [])):
        warnings.append(dict(kind="untested-project", node="tests",
                             msg="no \"tests\" in ladder.json: nothing records that this code passes the slice's own "
                                 "tests; add {\"name\": ..., \"command\": ...} for each (run from check_cwd)"))
    cwd = root / cfg.get("check_cwd", ".")
    found = L.find_repo(root)
    also = [root] + ([found[1]] if found else []) + [g for g in [_git_root(root)] if g]
    for t in tests:
        r = results.get(t["key"])
        gone = missing_files(t["cmd"], cwd, also)
        if gone:
            # A test line copied from another area may name a harness that is not here (pilot): say so, not "never run".
            warnings.append(dict(kind="test-missing", node=t["key"],
                                 msg=f"`{t['cmd']}` names {', '.join(gone)}, which does not exist (from {cwd}, the "
                                     f"project or the repository root); "
                                     f"fix the path, or write that test for this project"))
            continue
        if r is None:
            warnings.append(dict(kind="test-not-run", node=t["key"], msg=f"never run; `ladder test` runs `{t['cmd']}`"))
        elif r.get("hash") != t["hash"]:
            warnings.append(dict(kind="test-stale", node=t["key"],
                                 msg=f"what it tests changed since it last ran ({r.get('at', '?')}): the capability or link, its test "
                                     f"files, the code of the builds it tests, or the schema of tables it touches (after a "
                                     f"Ladder upgrade, possibly only how that is recorded); run `ladder test`"))
        elif not r.get("ok"):
            problems.append(dict(kind="test-failed", node=t["key"],
                                 msg=f"failed when last run ({r.get('at', '?')}): {r.get('tail', '')[:600]}"))
        elif r.get("silent"):
            warnings.append(dict(kind="test-silent", node=t["key"],
                                 msg=f"passed with no output ({r.get('at', '?')}): nothing shows that any test ran (a filter "
                                     f"that matches nothing exits 0); make `{t['cmd']}` print its runner's summary"))
    return problems, warnings


ASSERT_RE = re.compile(r"(AssertionError|Assert\.|expected|Expected|received|Received|Actual|actual:|"
                       r"\bFAIL\b|FAILED|^Failed |Error:|Exception:|\w+Exception\b|Error Number|Cannot insert|"
                       r"violat|constraint failed|✗|×)")


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


TEST_FILE_RE = re.compile(r"^[\w./-]*/[\w.-]+\.(?:sh|ts|tsx|js|mjs|cjs|py|cs|json)$")


def missing_files(cmd: str, cwd: Path, also: list[Path] | None = None) -> list[str]:
    """Words of a test command that look like a file path (a folder and a file name with an extension) and exist
    neither from the folder the command runs in nor from the other folders given (the project, the repository root:
    a runner script often resolves its arguments from the repository root)."""
    bases = [cwd, *(also or [])]
    out = []
    for word in cmd.split():
        w = word.strip("'\"")
        if TEST_FILE_RE.match(w) and not any((b / w).exists() for b in bases):
            out.append(w)
    return out


def _git_root(path: Path) -> Path | None:
    try:
        res = subprocess.run(["git", "-C", str(path), "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    except OSError:
        return None
    return Path(res.stdout.strip()) if res.returncode == 0 and res.stdout.strip() else None


NO_TESTS_RE = re.compile(r"No test files found[^\n]*|No test matches the given testcase filter[^\n]*|"
                         r"Total tests: 0\b|no tests ran[^\n]*|0 tests? (?:collected|found)", re.I)
COUNT_RES = [re.compile(r"Tests\s+(\d+) passed"), re.compile(r"Total tests:\s*(\d+)"),
             re.compile(r"Passed!\s*-\s*Failed:\s*\d+,\s*Passed:\s*(\d+)"), re.compile(r"\b(\d+) passed\b")]


def tests_run(out: str) -> int | None:
    """How many tests a run reports (vitest, jest, dotnet test, pytest summaries; summed over several), or None."""
    for rx in COUNT_RES:
        hits = rx.findall(out)
        if hits:
            return sum(int(h) for h in hits)
    return None


def run_tests(pj: Path, only: list[str] | None = None) -> int:
    import datetime
    cfg, root, tree, _, _ = L.load_project(pj)
    tests = all_tests(cfg, root, tree)
    if only:
        tests = [t for t in tests if any(o in t["key"] or o in t["what"] for o in only)]   # the name it prints too
    if not tests:
        print("no tests declared (capability `test:` lines, \"test\" on a links entry, or the project's \"tests\")")
        return 0
    code = L.load_code(root)
    results = code.setdefault("@tests", {})
    cwd = root / cfg.get("check_cwd", ".")
    found = L.find_repo(root)
    also = [root] + ([found[1]] if found else []) + [g for g in [_git_root(root)] if g]
    ran_info: dict[str, tuple[int | None, bool]] = {}
    failed = 0
    ran: dict[str, tuple[bool, int, list[str]]] = {}   # one run per distinct command (round 9: one link test named
    first: dict[str, str] = {}                          # by five subjects started the API five times)
    for t in tests:
        if t["cmd"] in ran:
            ok, rc, tail = ran[t["cmd"]]
            print(f"{t['what']}: same command as {first[t['cmd']]}, not run again")
        else:
            print(f"{t['what']}: {t['cmd']}")
            gone = missing_files(t["cmd"], cwd, also)
            if gone:
                # check reports these as test-missing; running them only fails on the missing file (shipping round)
                print(f"  not run: names {', '.join(gone)}, which does not exist")
                continue
            res = subprocess.run(t["cmd"], shell=True, cwd=cwd, capture_output=True, text=True)
            out = res.stdout + res.stderr
            tail = failure_lines(out)
            ok, rc = res.returncode == 0, res.returncode
            none_ran = NO_TESTS_RE.search(out)
            if ok and none_ran:
                # a filter that matches nothing exits 0 (shipping round: a misspelt class name recorded as a pass)
                ok, tail = False, [f"no tests ran: {none_ran.group(0).strip()}"]
            count = tests_run(out)
            ran[t["cmd"]] = (ok, rc, tail)
            ran_info[t["cmd"]] = (count, not out.strip())
            first[t["cmd"]] = t["what"]
        failed += not ok
        count, silent = ran_info.get(t["cmd"], (None, False))
        print(f"  {'ok' if ok else 'FAILED (exit ' + str(rc) + ')'}" + (f", {count} tests" if ok and count else "")
              + (" (no output: nothing shows that a test ran)" if ok and silent else ""))
        if not ok:
            print("    " + "\n    ".join(tail))
        results[t["key"]] = dict(hash=t["hash"], ok=ok, at=datetime.date.today().isoformat(),
                                 tail=" / ".join(tail)[:600] if not ok else "",
                                 **({"count": count} if count else {}), **({"silent": True} if ok and silent else {}))
    (root / L.CODE_FILE).write_text(json.dumps(code, indent=2, sort_keys=True) + "\n")
    print(f"\n{len(tests) - failed} of {len(tests)} passed; results recorded in ladder.code.json")
    return 1 if failed else 0

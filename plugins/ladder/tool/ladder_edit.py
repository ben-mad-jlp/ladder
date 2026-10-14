"""Small changes to the English, made by the tool so every writer agrees (the Ladder Review app, Claude, scripts):
`ladder edit` (one step's parts), `ladder answer` (a note's answer) and `ladder stamp --steps` (approve chosen steps).

Each rewrites only the lines that change: untouched lines keep their exact text and spacing, so git diffs stay small."""
from __future__ import annotations

import contextlib
import datetime
import difflib
import io
import json
import re
import subprocess
import sys
from pathlib import Path

import ladder as L

# The parts of a step, in the order a new line is placed among the existing ones.
SCALARS = {"title": None, "in": "inputs", "out": "outputs", "effects": "effects"}
LISTS = {"how": "steps", "note": "notes"}                              # one line per item
KEYED = {"uses": "; ", "reads": ", ", "writes": ", ", "calls": ", ", "compare": "; "}   # items joined on a line
RANK = {k: i for i, k in enumerate(["title", "in", "out", "effects", "uses", "reads", "writes", "calls", "how",
                                    "note", "compare"])}
# Edit JSON keys, as `ladder export` names the parts of a step.
SPEC_KEYS = {"title": "title", "inputs": "in", "outputs": "out", "effects": "effects", "how": "how", "notes": "note",
             "uses": "uses", "reads": "reads", "writes": "writes", "calls": "calls", "compare": "compare"}


class Refused(Exception):
    pass


def step_block(lines: list[str], node: L.Node) -> tuple[int, int]:
    """[start, end) indexes of the lines that belong to the step itself: its header up to the next step, data block or
    rule (its children are steps of their own)."""
    start = node.line - 1
    end = start + 1
    while end < len(lines):
        raw = lines[end]
        if L.NODE_RE.match(raw) or L.DATA_RE.match(raw) or L.RULE_RE.match(raw):
            break
        end += 1
    # Blank lines and comments before the next step stay where they are, outside the block.
    while end > start + 1 and (not lines[end - 1].strip() or lines[end - 1].lstrip().startswith("#")):
        end -= 1
    return start, end


def entries(block: list[str]) -> list[list]:
    """[kind, value, raw] for each line of a step's block; kind "other" for blank and comment lines."""
    out = []
    for i, raw in enumerate(block):
        if i == 0:
            out.append(["title", L.NODE_RE.match(raw).group(3), raw])
        elif not raw.strip() or raw.lstrip().startswith("#"):
            out.append(["other", None, raw])
        elif m := L.ATTR_RE.match(raw):
            out.append(["how" if m.group(1) == ">" else m.group(1), m.group(2), raw])
        elif m := L.STEP_RE.match(raw):
            out.append(["how", m.group(1), raw])
        else:
            out.append(["other", None, raw])
    return out


def keyed_items(kind: str, value: str) -> list[str]:
    if kind == "uses":
        return L.split_uses(value)
    if kind == "compare":
        return [c.strip() for c in value.split(";") if c.strip()]
    return [x.strip() for x in re.split(r"[,;]", value) if x.strip()]


def rewrite_step(block: list[str], node: L.Node, want: dict) -> list[str]:
    """The step's block with `want`'s parts changed and every other line kept as it is."""
    head = L.NODE_RE.match(block[0])
    hindent, ind = head.group(1), head.group(1) + "  "
    ents = entries(block)

    def render(kind: str, value: str) -> str:
        if kind == "title":
            return f"{hindent}[{node.id}] {value}"
        if kind == "how":
            return f"{ind}> {value}"
        return f"{ind}{kind}: {value}"

    def anchor(kind: str) -> int:
        """Where a part the step does not have yet goes: after the last line of a part that comes before it."""
        pos = 1
        for i, e in enumerate(ents):
            if e[0] in RANK and RANK[e[0]] <= RANK[kind]:
                pos = i + 1
        return pos

    for kind, new in want.items():
        if isinstance(new, str) and "\n" in new or isinstance(new, list) and any("\n" in x for x in new):
            raise Refused(f"{kind}: one line per item (no line breaks)")
        if kind in SCALARS:
            new = " ".join(new.split()) if kind == "title" else new.strip()
            if kind == "title" and not new:
                raise Refused("a step needs a title")
            at = [i for i, e in enumerate(ents) if e[0] == kind]
            if at and ents[at[0]][1] == new or not at and not new:
                continue
            if at and new:
                ents[at[0]] = [kind, new, render(kind, new)]
            elif at:
                del ents[at[0]]
            else:
                ents.insert(anchor(kind), [kind, new, render(kind, new)])
        elif kind in LISTS:
            new = [x.strip() for x in new if x.strip()]
            old_idx = [i for i, e in enumerate(ents) if e[0] == kind]
            old = [ents[i][1] for i in old_idx]
            if old == new:
                continue
            # Keep the lines whose text is unchanged; put changed and new ones where the old ones were.
            before: dict[int, list] = {}      # ents index -> new entries that go just before it
            drop: set[int] = set()
            for tag, a0, a1, b0, b1 in difflib.SequenceMatcher(a=old, b=new, autojunk=False).get_opcodes():
                if tag == "equal":
                    continue
                drop.update(old_idx[a0:a1])
                if a1 > a0:
                    pos = old_idx[a0]                    # replaced: where the first old line was
                elif a0 > 0:
                    pos = old_idx[a0 - 1] + 1            # inserted: after the line before it
                else:
                    pos = old_idx[0] if old_idx else anchor(kind)
                before.setdefault(pos, []).extend([kind, x, render(kind, x)] for x in new[b0:b1])
            ents = [e for i in range(len(ents) + 1)
                    for e in before.get(i, []) + ([ents[i]] if i < len(ents) and i not in drop else [])]
        elif kind in KEYED:
            new = [x.strip() for x in new if x.strip()]
            at = [i for i, e in enumerate(ents) if e[0] == kind]
            old = [x for i in at for x in keyed_items(kind, ents[i][1])]
            if old == new:
                continue
            line = [kind, KEYED[kind].join(new), render(kind, KEYED[kind].join(new))]
            pos = at[0] if at else anchor(kind)
            ents = [e for i, e in enumerate(ents) if i not in at]
            if new:
                ents.insert(pos, line)
        else:
            raise Refused(f"unknown part '{kind}' (title, inputs, outputs, effects, how, notes, uses, reads, writes, "
                          f"calls, compare)")
    return [e[2] for e in ents]


def git_name(root: Path) -> str:
    r = subprocess.run(["git", "-C", str(root), "config", "user.name"], capture_output=True, text=True)
    return r.stdout.strip() or "unknown"


def stale_regions(root: Path, cfg: dict, ids: set[str]) -> list[dict]:
    """The tagged regions of these steps in every build: what goes stale when their hash changes."""
    out = []
    for b in cfg.get("builds", []):
        if b.get("tagged") is False or b.get("lang") not in L.COMMENT:
            continue
        for f in b.get("files", []):
            path = root / f
            if not path.exists():
                continue
            regions, *_ = L.parse_regions(path, b["lang"])
            for r in regions:
                if r.kind == "node" and any(t in ids for t, _ in r.tags):
                    out.append(dict(build=b["name"], file=f, line=r.start, steps=[t for t, _ in r.tags]))
    return out


def apply_edit(pj: Path, nid: str, spec: dict, expect: str | None, dry_run: bool) -> dict:
    """Change one step's parts. Refused when the step's text is no longer what the caller read (`expect`, the step's
    review hash from `ladder export`), so a change Claude or git made in between is never overwritten."""
    cfg, root, tree, *_ = L.load_project(pj)
    if nid not in tree:
        raise Refused(f"no step [{nid}] in {cfg['tree']}")
    node = tree[nid]
    if expect and expect != node.review_hash:
        raise Refused(f"[{nid}] changed since it was read (now {node.review_hash}, read as {expect}); reload and "
                      f"make the change again")
    want = {}
    for k, v in spec.items():
        if k not in SPEC_KEYS:
            raise Refused(f"unknown part '{k}' (use {', '.join(SPEC_KEYS)})")
        want[SPEC_KEYS[k]] = v
    path = root / cfg["tree"]
    text = path.read_text()
    nl = "\r\n" if "\r\n" in text else "\n"
    lines = text.split(nl)
    trailing = lines and lines[-1] == ""
    if trailing:
        lines = lines[:-1]
    start, end = step_block(lines, node)
    new_block = rewrite_step(lines[start:end], node, want)
    new_lines = lines[:start] + new_block + lines[end:]
    new_text = nl.join(new_lines) + (nl if trailing else "")
    # The result must parse, and say what was asked: never write a file the tool itself cannot read.
    tmp = path.with_name(path.name + ".edit-check")
    try:
        tmp.write_text(new_text)
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                new_tree = L.parse_tree(tmp)
        except SystemExit as e:
            raise Refused(f"the change would not parse: {str(e).replace(str(tmp), cfg['tree'])}")
    finally:
        tmp.unlink(missing_ok=True)
    after = new_tree[nid]
    for part, attr in [("title", "title"), ("in", "inputs"), ("out", "outputs"), ("effects", "effects"),
                       ("how", "steps"), ("note", "notes"), ("uses", "uses"), ("reads", "reads"),
                       ("writes", "writes"), ("calls", "calls"), ("compare", "compare")]:
        if part in want:
            got = getattr(after, attr)
            asked = want[part]
            asked = ([x.strip() for x in asked if x.strip()] if isinstance(asked, list)
                     else " ".join(asked.split()) if part == "title" else asked.strip())
            if got != asked:
                raise Refused(f"{part}: the file would say {got!r}, not {asked!r} (a line that reads as another part?)")
    diff = "".join(difflib.unified_diff([x + "\n" for x in lines], [x + "\n" for x in new_lines],
                                        cfg["tree"], cfg["tree"], n=1))
    changed = new_text != text
    code_changed = after.hash != node.hash
    contract_before, contract_after = L.contract_hash(tree), L.contract_hash(new_tree)
    parts = {"title": "title", "in": "inputs", "out": "outputs", "effects": "effects", "how": "steps", "note": "notes",
             "uses": "uses", "reads": "reads", "writes": "writes", "calls": "calls", "compare": "compare"}
    changed_parts = {k for k, attr in parts.items() if getattr(after, attr) != getattr(node, attr)}
    only_notes = changed_parts == {"note"}
    result = dict(step=nid, changed=changed, parts=sorted(changed_parts), written=False, diff=diff, hashBefore=node.hash, hashAfter=after.hash,
                  reviewHashAfter=after.review_hash, codeChanged=code_changed,
                  stale=stale_regions(root, cfg, {nid}) if code_changed else [],
                  contractChanged=contract_before != contract_after, notesOnly=only_notes)
    if code_changed and only_notes:
        result["suggest"] = f"only a note changed: if the code still does what the step says, `ladder retag " \
                            f"{pj} {nid}` instead of regenerating"
    if changed and not dry_run:
        path.write_text(new_text)
        result["written"] = True
    return result


def answer_text(note: str, answer: str, who: str, plain: bool) -> str:
    """The note after it is answered. The question stays, after the answer, so later readers know what was asked."""
    kind, _, asked = note.partition(":")
    asked = asked.strip()
    if plain:
        return asked if not answer else f"{answer} ({who}, {datetime.date.today().isoformat()}); was {kind.strip()}: {asked}"
    return f"ANSWERED: {answer} ({who}, {datetime.date.today().isoformat()}); {kind.strip().lower()}: {asked}"


def edit_main(argv: list[str]) -> int:
    """ladder edit <ladder.json> <step id> [--from FILE] [--expect HASH] [--dry-run] [--json]
    The new parts come as JSON on stdin (or --from FILE): any of title, inputs, outputs, effects, how, notes, uses, reads,
    writes, calls, compare, as `ladder export` names them; parts left out are kept."""
    pos = [a for a in argv if not a.startswith("--")]
    opt = lambda name: next((argv[i + 1] for i, a in enumerate(argv[:-1]) if a == name), None)
    src = opt("--from")
    pos = [a for a in pos if a not in (src, opt("--expect"))]
    if len(pos) < 2:
        raise SystemExit("usage: ladder edit <ladder.json> <step id> [--from FILE] [--expect HASH] [--dry-run] [--json]")
    try:
        spec = json.loads(Path(src).read_text() if src else sys.stdin.read())
        res = apply_edit(Path(pos[0]), pos[1], spec, opt("--expect"), "--dry-run" in argv)
    except (Refused, ValueError) as e:
        return refuse(argv, str(e))
    return report(argv, res)


def answer_main(argv: list[str]) -> int:
    """ladder answer <ladder.json> <step id> <note number> <answer...> [--plain] [--by NAME] [--expect HASH]
    [--dry-run] [--json]: write the answer to an open note (numbered from 1 among the step's notes)."""
    opt = lambda name: next((argv[i + 1] for i, a in enumerate(argv[:-1]) if a == name), None)
    skip = {opt("--by"), opt("--expect")}
    pos = [a for a in argv if not a.startswith("--") and a not in skip]
    if len(pos) < 3 or not pos[2].isdigit():
        raise SystemExit("usage: ladder answer <ladder.json> <step id> <note number> <answer...> [--plain] [--by NAME]")
    pj, nid, k, answer = Path(pos[0]), pos[1], int(pos[2]), " ".join(pos[3:]).strip()
    try:
        cfg, root, tree, *_ = L.load_project(pj)
        if nid not in tree:
            raise Refused(f"no step [{nid}]")
        notes = list(tree[nid].notes)
        if not 1 <= k <= len(notes):
            raise Refused(f"[{nid}] has {len(notes)} notes; no note {k}")
        note = notes[k - 1].strip()
        if not re.match(r"^(QUESTION|DIFFERS|DECISION):", note):
            raise Refused(f"note {k} of [{nid}] is not an open QUESTION, DIFFERS or DECISION: {note[:80]}")
        if not answer and "--plain" not in argv:
            raise Refused("give the answer (e.g. \"keep as is\", \"bug: <what it should do>\", \"web wins\")")
        notes[k - 1] = answer_text(note, answer, opt("--by") or git_name(root), "--plain" in argv)
        res = apply_edit(pj, nid, {"notes": notes}, opt("--expect"), "--dry-run" in argv)
    except Refused as e:
        return refuse(argv, str(e))
    return report(argv, res)


def stamp_steps(pj: Path, ids: list[str], dry_run: bool, force: bool = False, by: str | None = None) -> dict:
    """Approve chosen steps and data blocks, keeping the rest of the lock as it was. A removed step or data block is
    approved by naming it (its entry leaves the lock). Refused while a chosen step's code is stale."""
    with contextlib.redirect_stdout(io.StringIO()):
        rep = L.check(pj)
    cfg, root, tree, lock, lock_path = L.load_project(pj)
    who = by or git_name(root)
    when = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    data_now = L.data_texts(tree)
    data_was = dict(lock.get("@data", {}))
    unknown = [i for i in ids if i not in tree and i not in lock and i not in data_now and i not in data_was]
    if unknown:
        raise Refused(f"not a step or data block of this project, now or in the lock: {', '.join(unknown)}")
    wanted = set(ids)
    stale = [p for b in rep["builds"] for p in b.get("problems", [])
             if p.get("kind") == "stale" and set(p.get("node", "").split("+")) & wanted]
    if stale and not force:
        raise Refused("these steps' code was generated from another version of the English; regenerate it, or "
                      "`ladder retag` if the English was only reworded: "
                      + "; ".join(f"[{p.get('node')}] {p.get('file')}:{p.get('line')}" for p in stale))
    recorded, still_open = [], []
    new_lock = {k: v for k, v in lock.items()}
    for i in ids:
        if i in tree:
            n = tree[i]
            was = lock.get(i)
            what = "new" if was is None else ("edited" if was.get("review_hash") != n.review_hash else "unchanged")
            new_lock[i] = {"hash": n.hash, "review_hash": n.review_hash,
                           "parent_hash": tree[n.parent].hash if n.parent else None, "text": n.own_text(),
                           "compare": n.compare, "approved_by": who, "approved_at": when}
            recorded.append(dict(id=i, kind="step", what=what))
        elif i in data_now or i in data_was:
            d = dict(new_lock.get("@data", {}))
            if i in data_now:
                what = "new" if i not in data_was else ("edited" if data_was[i] != data_now[i] else "unchanged")
                d[i] = data_now[i]
            else:
                what = "removed"
                d.pop(i, None)
            new_lock["@data"] = d
            recorded.append(dict(id=i, kind="data", what=what))
        else:
            new_lock.pop(i, None)
            recorded.append(dict(id=i, kind="step", what="removed"))
    # Schema and link facts are recorded per step: take the chosen steps' facts, keep the others' as they were.
    import ladder_links as K
    import ladder_schema as S
    if cfg.get("schemas"):
        _, sfacts, _ = S.check_refs(tree, S.load_schemas(cfg, root))
        merged = {k: v for k, v in lock.get("@schema", {}).items() if k not in wanted}
        merged.update({k: v for k, v in sfacts.items() if k in wanted})
        if merged:
            new_lock["@schema"] = merged
    _, _, _, lfacts = K.check_links(tree, cfg, root, {})
    merged = {k: v for k, v in lock.get("@links", {}).items() if k not in wanted}
    merged.update({k: v for k, v in lfacts.items() if k in wanted})
    if merged:
        new_lock["@links"] = merged
    elif "@links" in new_lock:
        del new_lock["@links"]
    approval_items = [p for p in rep["tree"] if p["kind"] in L.APPROVAL_KINDS]
    remaining = [dict(kind=p["kind"], node=p["node"], msg=p["msg"]) for p in approval_items
                 if not set(re.split(r"[,+]\s*", p["node"])) <= wanted]
    result = dict(recorded=recorded, stillOpen=remaining, by=who, at=when, written=False)
    if not dry_run:
        lock_path.write_text(json.dumps(new_lock, indent=2) + "\n")
        # The approved steps' code is what a person has now seen: record it, so later edits show as hand edits.
        keys = set()
        for b in cfg["builds"]:
            if b.get("tagged") is False:
                continue
            for f, regs in L.code_fingerprints(root, b).items():
                for key in regs:
                    if key.startswith("node ") and set(key[5:].split(" #")[0].split("+")) & wanted:
                        keys.add((b["name"], f, key))
        if keys:
            L.record_code(root, cfg, keys=keys)
        result["written"] = True
    return result


def stamp_main(pj: Path, argv: list[str]) -> int:
    ids = [x for a in argv if a.startswith("--steps=") for x in a.split("=", 1)[1].split(",") if x]
    if "--steps" in argv:
        i = argv.index("--steps")
        ids += [x for x in argv[i + 1].split(",") if x] if i + 1 < len(argv) else []
    by = next((argv[i + 1] for i, a in enumerate(argv[:-1]) if a == "--by"), None)
    if not ids:
        raise SystemExit("usage: ladder stamp <ladder.json> --steps ID[,ID...] [--dry-run] [--json] [--by NAME]")
    try:
        res = stamp_steps(pj, ids, "--dry-run" in argv, "--force" in argv, by)
    except Refused as e:
        return refuse(argv, str(e))
    if "--json" in argv:
        print(json.dumps(res, indent=2))
        return 0
    verb = "approved" if res["written"] else "would approve"
    for r in res["recorded"]:
        print(f"  {verb} {r['kind']} {r['id']} ({r['what']})")
    print(f"{verb} {len(res['recorded'])} item(s) as {res['by']}"
          + (f"; still waiting: {len(res['stillOpen'])}" if res["stillOpen"] else ""))
    return 0


def refuse(argv: list[str], msg: str) -> int:
    if "--json" in argv:
        print(json.dumps(dict(refused=msg)))
    else:
        print(f"refused: {msg}", file=sys.stderr)
    return 1


def report(argv: list[str], res: dict) -> int:
    if "--json" in argv:
        print(json.dumps(res, indent=2))
        return 0
    if not res["changed"]:
        print(f"[{res['step']}] unchanged")
        return 0
    print(res["diff"], end="")
    verb = "wrote" if res["written"] else "would write"
    print(f"{verb} [{res['step']}]" + (f": {len(res['stale'])} code region(s) become stale" if res["stale"] else
                                         ": wording only, no code goes stale" if not res["codeChanged"] else ""))
    if res.get("suggest"):
        print(res["suggest"])
    return 0

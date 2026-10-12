"""ladder regen: regenerate stale code regions with an LLM, then verify them mechanically.

Flow for each build (reference build first):
  1. find regions whose tags point at an older version of a step
  2. build a prompt: the step's English before and after the edit, its parent, the
     build's rules (literal or optimized), the whole current file, and the region to replace.
     Non-reference builds also get the reference build's freshly generated region to match.
  3. call the generator command (stdin = prompt, stdout = the replacement region)
  4. accept the answer only if it starts with the exact marker line (ids + new hashes),
     ends with @end, and the spliced file passes the tag checks. Otherwise keep the old code.
Every prompt and answer is saved under .ladder/regen/<time>/ so a person can review them.
"""
from __future__ import annotations

import fnmatch

import json
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import ladder as L

SYSTEM = """You are the code generator for a "ladder" project. Programs are written as a tree of
plain-English steps; code in several languages is generated from those steps. Every region of
generated code is wrapped in marker comments naming the step(s) it implements.

Each request asks for ONE region of code: a replacement for a region whose step's English (or
types, or sub-steps) changed, or a new region for a step that was just added.
Reply with ONLY that region: the opening marker line exactly as specified, the code, and the
closing @end line. No explanation, no Markdown fences, nothing before or after.
Change only what the English change requires. Keep function names, signatures, trace spans
and helper usage the same unless the step's in:/out: contract changed.

Code outside your region (imports, includes, forward declarations) lives in labeled @support
regions you cannot edit directly. If your code needs a line added to one of them, put a request
BEFORE the marker line, naming the support region by the start of its label:
@add-to-support <label start, e.g. "includes" or "forward declarations">
<the lines to add>
@end-add
Only request lines that are truly needed and not already present."""

MODE_RULES = {
    "literal": "This is a LITERAL build: one region per step, laid out as the build profile says "
               "(usually one function per step), readable over fast. Trace each step exactly as the "
               "build profile and the surrounding code do (some builds trace nothing in code). Do not "
               "merge steps or move logic into other steps.",
    "optimized": "This is an OPTIMIZED build: steps may be merged inside one region when that makes "
                 "the code faster, as the existing region already does. Keep the trace spans that the "
                 "existing region emits (one per attempt/step it can still tell apart). Avoid needless "
                 "allocation; reuse buffers where the existing code does.",
}


CTX: dict = {"tree": None, "vocab": None, "root": None, "lock": {}, "schemas": {}}   # set by regen/generate/repair before prompts are built


def set_context(cfg: dict, root: Path, tree) -> None:
    CTX["tree"] = tree
    CTX["vocab"] = L.load_vocabulary(cfg, root)
    CTX["root"] = root
    try:
        import ladder_schema as S
        CTX["schemas"] = S.load_schemas(cfg, root) if cfg.get("schemas") else {}
    except SystemExit as e:
        print(f"warning: schemas not loaded: {e}")
        CTX["schemas"] = {}
    try:
        CTX["lock"] = json.loads((root / "ladder.lock.json").read_text())
    except (OSError, ValueError):
        CTX["lock"] = {}


def new_log_dir(root: Path, suffix: str = "") -> Path:
    """A fresh folder for one run's prompts and replies; unique even for runs started in the same second."""
    import os
    d = root / ".ladder" / "regen" / f"{time.strftime('%Y%m%d-%H%M%S')}-{os.getpid()}{suffix}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def conventions_text(build: dict) -> str:
    root = CTX["root"]
    if root is None or not build.get("conventions"):
        return ""
    return "\n\n".join((root / c).read_text() for c in build["conventions"] if (root / c).exists())


def context_text(build: dict, ids: list[str] | None = None, conventions: bool = True) -> str:
    """The build profile, data blocks, named rules and the capabilities (with this build's binding)
    the steps use. Every prompt that writes code gets the profile: names, constructors and file
    layout live there, and a region written without it guesses them."""
    tree, vocab = CTX["tree"], CTX["vocab"]
    out = []
    conv = conventions_text(build) if conventions else ""
    if conv:
        out += ["=== Conventions for this build (follow them exactly: names, signatures, layout):", conv, ""]
    if tree is not None and getattr(tree, "data", None):
        was = CTX["lock"].get("@data", {})
        out += ["=== Data the English refers to:"]
        for k, d in L.build_data(tree, build).items():
            out.append(d.text())
            before = was.get(f"data {k}")
            if before is not None and before != d.text():
                out += ["  (CHANGED since approval. Before:)", *("  | " + l for l in before.splitlines())]
        out.append("")
    if tree is not None and getattr(tree, "rules", None):
        out += ["=== Named rules:", *(f"rule {k}: {v}" for k, v in tree.rules.items()), ""]
    if vocab and tree is not None:
        wanted = {u for nid in (ids or list(tree)) if nid in tree for u in tree[nid].uses}
        if wanted:
            out += [f"=== Capabilities these steps use, with the binding for {build['name']} ({build['lang']}). "
                    "Use exactly this library, version and call; do not substitute another:"]
            out += [vocab[u].text_for(build) for u in sorted(wanted) if u in vocab] + [""]
    if CTX["root"] is not None and build.get("reads"):
        out.append(read_files_text(CTX["root"], build))
    if CTX.get("schemas") and tree is not None:
        import ladder_schema as S
        out.append(S.prompt_text(ids or list(tree), tree, CTX["schemas"]))
    return "\n".join(out)


def step_block(n: L.Node) -> str:
    lines = [f"[{n.id}] {n.title}"]
    if n.inputs:
        lines.append(f"  in: {n.inputs}")
    if n.outputs:
        lines.append(f"  out: {n.outputs}")
    if n.effects:
        lines.append(f"  effects: {n.effects}")
    lines += [f"  > {s}" for s in n.steps] + [f"  note: {t}" for t in n.notes]
    if n.uses:
        lines.append(f"  uses: {'; '.join(n.uses)}")
    if getattr(n, "reads", None):
        lines.append(f"  reads: {', '.join(n.reads)}")
    if getattr(n, "writes", None):
        lines.append(f"  writes: {', '.join(n.writes)}")
    return "\n".join(lines)


def old_block(lock_entry: dict | None) -> str:
    if not lock_entry or "text" not in lock_entry:
        return "(previous wording not recorded)"
    out = []
    for i, line in enumerate(lock_entry["text"].splitlines()):
        m = re.match(r"^(in|out|effects|note|uses|reads|writes):(.*)$", line)
        if m and not m.group(2).strip():
            continue
        out.append(line if i == 0 else "  " + (f"{m.group(1)}: {m.group(2).strip()}" if m else line))
    return "\n".join(out)


DISCARD_HAND_EDITS = False   # set by `--discard-hand-edits`
OUT: str | None = None       # set by `generate --out=PATH`
BLIND = False                # set by `regen --blind`


def protected(root: Path, b: dict) -> set[tuple[str, str]]:
    """(file, region key) of regions edited by hand since the generator or a person last recorded
    them. Regenerating those would silently throw the edit away, so they are skipped."""
    if DISCARD_HAND_EDITS:
        return set()
    return {(f, k) for f, k, _ in L.hand_edited(root, b)}


HAND_EDIT_MSG = ("REFUSED: this region was edited by hand since it was generated; regenerating it would "
                 "throw the edit away. Move the change into the English, or `ladder accept` it, or pass "
                 "--discard-hand-edits")


REDO: set[str] = set()   # step ids to regenerate even though their hash still matches


def stale_regions(file: Path, lang: str, tree: dict[str, L.Node]):
    regions, _, lines, _ = L.parse_regions(file, lang)
    out = []
    for i, r in enumerate(regions):
        if r.kind == "node" and any(nid in tree and (h != tree[nid].hash or nid in REDO) for nid, h in r.tags):
            # If a stale region sits inside another stale region, the outer one covers it.
            p, covered = r.parent, False
            while p is not None:
                pr = regions[p]
                if any(nid in tree and h != tree[nid].hash for nid, h in pr.tags):
                    covered = True
                p = pr.parent
            if not covered:
                out.append((i, r))
    return regions, lines, out


def expected_marker(r: L.Region, tree: dict[str, L.Node], lang: str) -> str:
    c = L.COMMENT[lang]
    return f"{c} @node " + " ".join(f"{nid}@{tree[nid].hash}" for nid, _ in r.tags)


def support_labels(lines: list[str], lang: str) -> str:
    c = re.escape(L.COMMENT[lang])
    labels = [m.group(1).strip() for l in lines if (m := re.match(rf"^\s*{c}\s*@support\b(.*)$", l))]
    named = [x for x in labels if x]
    text = "; ".join(f'"{x}"' for x in named) or "(none with a label)"
    if len(named) < len(labels):
        text += f" ({len(labels) - len(named)} unlabeled support region(s) cannot receive additions)"
    return "=== Support regions in this file (for @add-to-support): " + text


def nested_regions(regions: list, idx: int) -> list:
    """Regions inside regions[idx], at any depth, in file order."""
    out = []
    for j, rr in enumerate(regions):
        p = rr.parent
        while p is not None and p != idx:
            p = regions[p].parent
        if p == idx:
            out.append(rr)
    return out


def nested_markers(nested: list, tree, build: dict) -> list[str]:
    """The marker line each nested @node/@contract region must carry after regeneration."""
    c = L.COMMENT[build["lang"]]
    out = []
    for rr in nested:
        if rr.kind == "node":
            out.append(f"{c} @node " + " ".join(f"{nid}@{tree[nid].hash}" for nid, _ in rr.tags if nid in tree))
        elif rr.kind == "contract":
            out.append(f"{c} @{rr.label}@{L.contract_hash(tree, build)}")
    return out


def build_prompt(build: dict, file_rel: str, lines: list[str], r: L.Region,
                 tree: dict[str, L.Node], lock: dict, reference: dict | None,
                 reason: str | None = None, nested: list | None = None) -> str:
    ids = [nid for nid, _ in r.tags]
    nested = nested or []
    nested_ids = [nid for rr in nested if rr.kind == "node" for nid, _ in rr.tags if nid in tree]
    changed = [nid for nid, h in r.tags if h != tree[nid].hash]
    parts = [f"LANGUAGE: {build['lang']}    BUILD: {build['name']}    FILE: {file_rel}",
             MODE_RULES.get(build.get("mode", "literal"), MODE_RULES["literal"]), ""]
    redo = [nid for nid, _ in r.tags if nid in REDO and nid not in changed]
    if redo:
        parts += [f"=== Regenerate this region for step(s) {', '.join(redo)} against the file as it is now "
                  "(its types or helpers may have changed). Use the file's own types; do not widen or "
                  "re-declare them locally.", ""]
    if reason:
        parts += ["=== This region is being regenerated because the build or run FAILED with the errors "
                  "below. Fix the cause. If the fix needs a line outside this region (an import, include "
                  "or declaration), request it with @add-to-support.", reason, ""]
    for nid in changed:
        n = tree[nid]
        parts += [f"=== Step [{nid}] CHANGED. Before:", old_block(lock.get(nid)), "",
                  f"=== Step [{nid}] now:", step_block(n), ""]
    for nid in ids:
        if nid not in changed:
            parts += [f"=== Step [{nid}] (unchanged, also covered by this region):", step_block(tree[nid]), ""]
    for nid in nested_ids:
        n = tree[nid]
        h = next(h for rr in nested for t, h in rr.tags if t == nid)
        if h != n.hash:
            parts += [f"=== Nested step [{nid}] CHANGED (its region sits inside this one). Before:",
                      old_block(lock.get(nid)), "", f"=== Nested step [{nid}] now:", step_block(n), ""]
        else:
            parts += [f"=== Nested step [{nid}] (unchanged; keep its code unless the steps above require otherwise):",
                      step_block(n), ""]
    parents = {tree[nid].parent for nid in ids if tree[nid].parent and tree[nid].parent not in ids}
    for pid in parents:
        parts += [f"=== Parent step [{pid}] (context):", step_block(tree[pid]), ""]
    if reference:
        parts += [f"=== The reference build ({reference['build']}, {reference['lang']}) was just regenerated "
                  f"for this change. Match its behavior exactly (same constants, same number of attempts, "
                  f"same order), written idiomatically for {build['lang']}:",
                  reference["text"], ""]
    numbered = "\n".join(f"{i + 1:4d}  {l}" for i, l in enumerate(lines))
    region = "\n".join(lines[r.start - 1:r.end])
    parts += [context_text(build, ids)]
    parts += [f"=== Whole current file (for context; line numbers are not part of the code):", numbered, "",
              support_labels(lines, build["lang"]), "",
              f"=== REGION TO REPLACE (lines {r.start}-{r.end}):", region, "",
              "=== Your reply must start with exactly this line (same indentation as the old marker):",
              expected_marker(r, tree, build["lang"]),
              f"and end with the line: {L.COMMENT[build['lang']]} @end"]
    if nested:
        parts += ["=== This region contains nested regions. Keep every one of them, in the same order, each "
                  "opened with exactly these marker lines (hashes updated) and closed with its own @end:",
                  *nested_markers(nested, tree, build)]
    return "\n".join(parts)


ADD_RE = re.compile(r"^@add-to-support\s+(.+?)\s*\n(.*?)\n@end-add\s*$", re.M | re.S)


def split_reply(text: str) -> tuple[list[str], list[tuple[str, list[str]]]]:
    """Returns (region lines, [(support label start, lines to add)])."""
    t = text.strip("\n")
    t = re.sub(r"^```[a-zA-Z+#]*\n", "", t)
    t = re.sub(r"\n```\s*$", "", t)
    adds = [(m.group(1).strip().strip('"'), m.group(2).splitlines()) for m in ADD_RE.finditer(t)]
    t = ADD_RE.sub("", t)
    return t.strip("\n").splitlines(), adds


def clean_reply(text: str) -> list[str]:
    return split_reply(text)[0]


IMPORT_LIKE = re.compile(r"^\s*(import |from \S+ import |#include |using [A-Z]\w*[.;]|using System)")


def apply_support_adds(lines: list[str], lang: str, adds) -> tuple[list[str], list[str]]:
    """Add requested lines to the named @support regions. Import-like lines go after the
    last import-like line in the region; others go just before its @end. Returns the new
    lines and a human-readable note per addition (for the log and the summary)."""
    if not adds:
        return lines, []
    c = re.escape(L.COMMENT[lang])
    notes = []
    for label, add in adds:
        add = [a for a in add if a.strip()]
        start = next((i for i, l in enumerate(lines)
                      if re.match(rf"^\s*{c}\s*@support\s+{re.escape(label)}", l, re.I)), None)
        if start is None:
            if not all(IMPORT_LIKE.match(a) for a in add):
                notes.append(f"IGNORED request for support region '{label}' (no such region)")
                continue
            # No such region, but these are imports: open a support region for them at the top of
            # the file, after any leading comment lines that are not region markers.
            at = 0
            while at < len(lines) and re.match(rf"^\s*{c}(?!\s*@)", lines[at]):
                at += 1
            block = [f"{L.COMMENT[lang]} @support {label}", *add, f"{L.COMMENT[lang]} @end", ""]
            lines = lines[:at] + block + lines[at:]
            notes.append(f"created support region '{label}' at the top of the file with: "
                         + " | ".join(a.strip() for a in add))
            continue
        end = next(i for i in range(start + 1, len(lines)) if re.match(rf"^\s*{c}\s*@end\b", lines[i]))
        present = {l.strip() for l in lines[start:end]}
        new = [a for a in add if a.strip() not in present]
        if not new:
            continue
        if all(IMPORT_LIKE.match(a) for a in new):
            last = max((i for i in range(start + 1, end) if IMPORT_LIKE.match(lines[i])), default=start)
            at = last + 1
        else:
            at = end
        lines = lines[:at] + new + lines[at:]
        notes.append(f"added to support '{label}': " + " | ".join(a.strip() for a in new))
    return lines, notes


def call_generator(cmd: list[str], prompt: str, cwd: Path) -> str:
    res = subprocess.run(cmd, input=prompt, capture_output=True, text=True, cwd=cwd, timeout=600)
    if res.returncode != 0:
        raise RuntimeError(f"generator failed ({res.returncode}): {res.stderr.strip()[:300]}")
    return res.stdout


def validate_and_splice(file: Path, lang: str, lines: list[str], r: L.Region, reply: list[str],
                        tree: dict[str, L.Node], expect_nested: list[str] | None = None) -> tuple[list[str] | None, str]:
    want = expected_marker(r, tree, lang)
    body = [l for l in reply]
    while body and not body[0].strip():
        body.pop(0)
    while body and not body[-1].strip():
        body.pop()
    if not body or body[0].strip() != want:
        return None, f"first line must be '{want}', got '{body[0].strip() if body else ''}'"
    end_re = re.compile(rf"^\s*{re.escape(L.COMMENT[lang])}\s*@end\b")
    if not end_re.match(body[-1]):
        return None, "last line is not an @end marker"
    if expect_nested:
        got = [l.strip() for l in body[1:] if re.match(rf"^\s*{re.escape(L.COMMENT[lang])}\s*@(node|contract)\b", l)]
        if got != expect_nested:
            missing = [m for m in expect_nested if m not in got]
            return None, ("nested region markers must be, in order: " + " | ".join(expect_nested)
                          + (f"; missing or with an old hash: {' | '.join(missing)}" if missing else ""))
    indent = lines[r.start - 1][: len(lines[r.start - 1]) - len(lines[r.start - 1].lstrip())]
    body = reindent(body, indent)
    new_lines = lines[: r.start - 1] + body + lines[r.end:]
    tmp = file.with_name(file.name + ".regen-tmp")
    tmp.write_text("\n".join(new_lines) + "\n")
    try:
        regions, _, _, probs = L.parse_regions(tmp, lang)
    finally:
        tmp.unlink()
    if probs:
        return None, "tag check failed: " + "; ".join(p["msg"] for p in probs[:3])
    ids_now = sorted(nid for rr in regions if rr.kind == "node" for nid, _ in rr.tags)
    ids_before = sorted(nid for rr in L.parse_regions(file, lang)[0] if rr.kind == "node" for nid, _ in rr.tags)
    if ids_now != ids_before:
        return None, f"step tags changed: {ids_before} -> {ids_now}"
    return new_lines, "ok"


# ---------------------------------------------------------------- new steps


def reindent(body: list[str], indent: str) -> list[str]:
    """Put the marker line at the region's indentation. The other lines are shifted only when the
    generator wrote them relative to column 0; lines already at the file's indentation stay."""
    if not body:
        return body
    rest = body[1:]
    filled = [l for l in rest if l.strip()]
    if indent and filled and not all(l.startswith(indent) for l in filled):
        rest = [indent + l if l.strip() else l for l in rest]
    return [indent + body[0].lstrip()] + rest


def find_missing(build: dict, root: Path, tree: dict[str, L.Node]) -> list[str]:
    """Leaf steps no region in this build is tagged with, in tree order."""
    tagged = set()
    for f in build["files"]:
        for r in L.parse_regions(root / f, build["lang"])[0]:
            tagged |= {nid for nid, _ in r.tags}
    return [n.id for n in tree.values()
            if n.is_leaf and n.id not in tagged and n.parent and in_scope(build, n.id)]


def region_for(build: dict, root: Path, nid: str):
    """(file, regions, lines, index) of the innermost region tagged with nid, or None."""
    for f in build["files"]:
        regions, _, lines, _ = L.parse_regions(root / f, build["lang"])
        hits = [i for i, r in enumerate(regions) if any(t == nid for t, _ in r.tags)]
        if hits:
            # innermost = the one with the most ancestors
            def depth(i):
                d, p = 0, regions[i].parent
                while p is not None:
                    d, p = d + 1, regions[p].parent
                return d
            return f, regions, lines, max(hits, key=depth)
    return None


def splice_check(path: Path, lang: str, new_lines: list[str], expect_ids: list[str]) -> str:
    tmp = path.with_name(path.name + ".regen-tmp")
    tmp.write_text("\n".join(new_lines) + "\n")
    try:
        regions, _, _, probs = L.parse_regions(tmp, lang)
    finally:
        tmp.unlink()
    if probs:
        return "tag check failed: " + "; ".join(p["msg"] for p in probs[:3])
    ids = sorted(nid for r in regions if r.kind == "node" for nid, _ in r.tags)
    if ids != sorted(expect_ids):
        return f"step tags are {ids}, expected {sorted(expect_ids)}"
    return "ok"


def body_from_reply(reply: str, marker: str, lang: str) -> tuple[list[str] | None, str]:
    body = clean_reply(reply)
    while body and not body[0].strip():
        body.pop(0)
    while body and not body[-1].strip():
        body.pop()
    if not body or body[0].strip() != marker:
        return None, f"first line must be '{marker}', got '{body[0].strip() if body else ''}'"
    if not re.match(rf"^\s*{re.escape(L.COMMENT[lang])}\s*@end\b", body[-1]):
        return None, "last line is not an @end marker"
    return body, "ok"


def insert_prompt(build, file_rel, lines, after_line, new: L.Node, prev: L.Node, tree, ref_text):
    parent = tree[new.parent]
    order = "\n".join(f"  [{c}] {tree[c].title}" + ("   <- NEW" if c == new.id else "")
                       for c in parent.children)
    parts = [f"LANGUAGE: {build['lang']}    BUILD: {build['name']}    FILE: {file_rel}",
             MODE_RULES.get(build.get("mode", "literal"), MODE_RULES["literal"]), "",
             f"=== A NEW step was added to the English:", step_block(new), "",
             f"=== Its parent [{parent.id}] now runs these sub-steps, in order:", order, "",
             f"=== The step just before it, [{prev.id}]:", step_block(prev), "",
             "Write the code for the new step as ONE new region. It will be inserted into the file at "
             f"exactly one spot: right after line {after_line}, which ends the region for [{prev.id}]. "
             "It must be valid code at that spot (if that spot is inside a function body, write "
             "statements, not a new function). In a literal build write a new function in the style of "
             "the others, with its own trace span using the new step id; a separate edit will make the "
             "parent call it. In an optimized build that runs steps inline, write the inline code and "
             "its trace span, so the flow continues correctly into the code that follows.", ""]
    if ref_text:
        parts += [f"=== The reference build already implements the new step like this. Match its behavior "
                  f"exactly (same checks, same constants), written idiomatically for {build['lang']}:",
                  ref_text, ""]
    numbered = "\n".join(f"{i + 1:4d}  {l}" for i, l in enumerate(lines))
    parts += [context_text(build, [new.id, new.parent])]
    parts += ["=== Whole current file (line numbers are not part of the code):", numbered, "",
              support_labels(lines, build["lang"]), "",
              "=== Your reply must start with exactly this line:",
              f"{L.COMMENT[build['lang']]} @node {new.id}@{new.hash}",
              f"and end with the line: {L.COMMENT[build['lang']]} @end"]
    return "\n".join(parts)


def parent_prompt(build, file_rel, lines, r: L.Region, new: L.Node, new_region: str, tree, ref_text, lock=None):
    parent = tree[new.parent]
    order = "\n".join(f"  [{c}] {tree[c].title}" + ("   <- NEW" if c == new.id else "")
                       for c in parent.children)
    changed = any(nid == parent.id and h != parent.hash for nid, h in r.tags)
    wording = ([f"=== Step [{parent.id}] CHANGED. Before:", old_block((lock or {}).get(parent.id)), "",
                f"=== Step [{parent.id}] now:", step_block(parent), ""] if changed
               else [f"=== Step [{parent.id}] (its own wording did not change):", step_block(parent), ""])
    parts = [f"LANGUAGE: {build['lang']}    BUILD: {build['name']}    FILE: {file_rel}",
             MODE_RULES.get(build.get("mode", "literal"), MODE_RULES["literal"]), "",
             *wording,
             f"=== It now has a NEW sub-step. It must run its sub-steps in this order:", order, "",
             f"=== The new sub-step's code, already in the file:", new_region, "",
             "Update the region below so it calls the new sub-step in the right place and passes its "
             "result on. Keep everything else the same. If the language needs a declaration of the new "
             "function before it is used here, request it with @add-to-support.", ""]
    if ref_text:
        parts += ["=== The reference build's updated version of this region (match its order and data flow):",
                  ref_text, ""]
    numbered = "\n".join(f"{i + 1:4d}  {l}" for i, l in enumerate(lines))
    parts += ["=== Whole current file (line numbers are not part of the code):", numbered, "",
              support_labels(lines, build["lang"]), "",
              f"=== REGION TO REPLACE (lines {r.start}-{r.end}):", "\n".join(lines[r.start - 1:r.end]), "",
              "=== Your reply must start with exactly this line:", expected_marker(r, tree, build["lang"]),
              f"and end with the line: {L.COMMENT[build['lang']]} @end"]
    return "\n".join(parts)


def contract_prompt(build, file_rel, lines, r: L.Region, tree, conv: str) -> str:
    contracts = "\n".join(f"[{n.id}] {n.title}\n  in: {n.inputs}\n  out: {n.outputs}" for n in tree.values()
                          if L.build_in_scope(build, n.id))
    numbered = "\n".join(f"{i + 1:4d}  {l}" for i, l in enumerate(lines))
    marker_name = lines[r.start - 1].split("@contract", 1)[1].strip().rpartition("@")[0]
    return "\n".join([
        f"LANGUAGE: {build['lang']}    BUILD: {build['name']}    FILE: {file_rel}",
        "This region holds the data types that spell out the steps' in:/out: contracts (the names in "
        "backticks are field names). One or more contracts changed. Update the types so they match the "
        "contracts exactly: add, remove or rename fields as the English now says. Keep imports, constants "
        "and anything else in the region unless the contract change requires otherwise.", "",
        "=== Conventions:", conv, "",
        "=== Every step's contract, as it is now:", contracts, "",
        context_text(build, conventions=False),
        "=== Whole current file:", numbered, "",
        f"=== REGION TO REPLACE (lines {r.start}-{r.end}):", "\n".join(lines[r.start - 1:r.end]), "",
        "=== Your reply must start with exactly this line:",
        f"{L.COMMENT[build['lang']]} @contract {marker_name}@{L.contract_hash(tree, build)}",
        f"and end with the line: {L.COMMENT[build['lang']]} @end"])


def regen_contracts(b: dict, root: Path, tree, gen, log_dir) -> list:
    """Regenerate every stale @contract region of one build, before any step regions."""
    results = []
    conv = "\n\n".join((root / c).read_text() for c in b.get("conventions", []))
    keep = protected(root, b)
    want_hash = L.contract_hash(tree, b)
    for f in b["files"]:
        fpath = root / f
        tried: set[str] = set()
        while True:   # re-read after each splice: line numbers move
            regions, _, lines, _ = L.parse_regions(fpath, b["lang"])
            todo = [(r, key) for r, key in zip(regions, L.region_keys(regions))
                    if r.kind == "contract" and not (r.tags and r.tags[0][1] == want_hash) and key not in tried]
            if not todo:
                break
            r, key = todo[0]
            tried.add(key)
            if (f, key) in keep:
                results.append((f, key, HAND_EDIT_MSG))
                continue
            prompt = contract_prompt(b, f, lines, r, tree, conv)
            tag = f"{b['name']}__{key.replace(' ', '-')}"
            (log_dir / f"{tag}.prompt.txt").write_text(SYSTEM + "\n\n" + prompt)
            reply = call_generator(gen + ["--system-prompt", SYSTEM], prompt, log_dir / "cwd")
            (log_dir / f"{tag}.reply.txt").write_text(reply)
            want = lines[r.start - 1].split("@contract", 1)[1].strip().rpartition("@")[0]
            body, why = body_from_reply(reply, f"{L.COMMENT[b['lang']]} @contract {want}@{want_hash}", b["lang"])
            if body is None:
                results.append((f, key, f"REJECTED: {why}"))
                continue
            indent = lines[r.start - 1][: len(lines[r.start - 1]) - len(lines[r.start - 1].lstrip())]
            body = reindent(body, indent)
            new = lines[:r.start - 1] + body + lines[r.end:]
            tmp = fpath.with_name(fpath.name + ".regen-tmp")
            tmp.write_text("\n".join(new) + "\n")
            try:
                probs = L.parse_regions(tmp, b["lang"])[3]
            finally:
                tmp.unlink()
            if probs:
                results.append((f, key, "REJECTED: " + "; ".join(p["msg"] for p in probs[:3])))
                continue
            fpath.write_text("\n".join(new) + "\n")
            results.append((f, key, f"contract types regenerated ({len(body)} lines)"))
    return results


def blinded(lines: list[str], regions: list, hide: set[int]) -> list[str]:
    """The file as the generator may see it: the bodies of regions in `hide` replaced by blank
    lines (one placeholder line each), so line numbers stay valid and no old code leaks."""
    out = list(lines)
    for i in hide:
        r = regions[i]
        if r.end - r.start < 2:
            continue
        ids = ", ".join(t for t, _ in r.tags) if r.kind == "node" else r.label
        indent = lines[r.start - 1][: len(lines[r.start - 1]) - len(lines[r.start - 1].lstrip())]
        out[r.start] = f"{indent}{L.COMMENT_FOR_HIDDEN} [hidden: code for {ids} will be written from the English]"
        for k in range(r.start + 1, r.end - 1):
            out[k] = ""
    return out


def regen_blind(cfg: dict, root: Path, tree, lock, b: dict, gen, log_dir, dry_run: bool) -> list:
    """Regenerate every @contract region and every innermost @node region of one build from the
    English alone, keeping @support code and regions that hold other regions. The generator never
    sees the code it replaces: regions not yet regenerated are hidden in every prompt. Runs one
    region at a time, top of file first, so later regions see the names earlier ones chose."""
    results = []
    L.COMMENT_FOR_HIDDEN = L.COMMENT[b["lang"]]
    conv = conventions_text(b)
    keep = protected(root, b)
    for f in b["files"]:
        fpath = root / f
        regions, _, lines, _ = L.parse_regions(fpath, b["lang"])
        keys = L.region_keys(regions)
        has_child = {rr.parent for rr in regions if rr.parent is not None and rr.kind in ("node", "contract")}

        def todo_keys(regs, ks):
            return [k for r, k, i in zip(regs, ks, range(len(regs)))
                    if k and (r.kind == "contract" or (r.kind == "node" and i not in has_child
                              and all(in_scope(b, t) for t, _ in r.tags)))]
        pending = todo_keys(regions, keys)
        for i, (r, k) in enumerate(zip(regions, keys)):
            if r.kind == "node" and i in has_child:
                results.append((f, r.label, "kept: holds nested regions (regenerate it afterwards with --redo)"))
        for k in [k for k in pending if (f, k) in keep]:
            results.append((f, k, HAND_EDIT_MSG))
        pending = [k for k in pending if (f, k) not in keep]
        while pending:
            regions, _, lines, _ = L.parse_regions(fpath, b["lang"])
            keys = L.region_keys(regions)
            has_child = {rr.parent for rr in regions if rr.parent is not None and rr.kind in ("node", "contract")}
            idx = next(i for i, k in enumerate(keys) if k == pending[0])
            hide = {i for i, k in enumerate(keys) if k in pending}
            view = blinded(lines, regions, hide)
            r = regions[idx]
            key = pending.pop(0)
            tag = f"{b['name']}__blind-{key.replace(' ', '-')}"
            if r.kind == "contract":
                prompt = contract_prompt(b, f, view, r, tree, conv)
                want = lines[r.start - 1].split("@contract", 1)[1].strip().rpartition("@")[0]
                marker = f"{L.COMMENT[b['lang']]} @contract {want}@{L.contract_hash(tree, b)}"
            else:
                REDO.update(t for t, _ in r.tags)
                prompt = build_prompt(b, f, view, r, tree, lock, None)
                marker = None
            prompt += ("\n\n=== BLIND REGENERATION: the region's old code is hidden on purpose. Write it from "
                       "the English, the conventions and the visible code only. Hidden regions elsewhere will "
                       "be written later; call what the English and the conventions name, not what you guess.")
            (log_dir / f"{tag}.prompt.txt").write_text(SYSTEM + "\n\n" + prompt)
            if dry_run:
                results.append((f, key, "dry run: prompt written"))
                continue
            reply = call_generator(gen + ["--system-prompt", SYSTEM], prompt, log_dir / "cwd")
            (log_dir / f"{tag}.reply.txt").write_text(reply)
            if marker:
                body, why = body_from_reply(reply, marker, b["lang"])
                if body is None:
                    results.append((f, key, f"REJECTED: {why}"))
                    continue
                indent = lines[r.start - 1][: len(lines[r.start - 1]) - len(lines[r.start - 1].lstrip())]
                new = lines[:r.start - 1] + reindent(body, indent) + lines[r.end:]
            else:
                new, why = validate_and_splice(fpath, b["lang"], lines, r, clean_reply(reply), tree)
                if new is None:
                    results.append((f, key, f"REJECTED: {why}"))
                    continue
            new, notes = apply_support_adds(new, b["lang"], split_reply(reply)[1])
            fpath.write_text("\n".join(new) + "\n")
            results.append((f, key, f"written blind ({len(clean_reply(reply))} lines)"))
            results += [(f, "support", n) for n in notes]
    return results


def regen(pj: Path, only: str | None = None, dry_run: bool = False) -> int:
    cfg, root, tree, lock, _ = L.load_project(pj)
    set_context(cfg, root, tree)
    gen = cfg.get("generator", {}).get("command")
    if not gen and not dry_run:
        print("no generator.command in project file")
        return 2
    ref_name = cfg.get("compare", {}).get("reference")
    builds = sorted(cfg["builds"], key=lambda b: b["name"] != ref_name)
    if only:
        builds = [b for b in builds if b["name"] == only]
    log_dir = new_log_dir(root, "-blind" if BLIND else "")
    scratch = log_dir / "cwd"
    scratch.mkdir(exist_ok=True)

    reference_text: dict[str, dict] = {}   # step-set key -> reference region text
    summary = []

    def key(r):
        return "+".join(sorted(nid for nid, _ in r.tags if tree[nid].is_leaf or True))

    def do_build(b: dict):
        if BLIND:
            return b["name"], regen_blind(cfg, root, tree, lock, b, gen, log_dir, dry_run)
        results = regen_contracts(b, root, tree, gen, log_dir) if not dry_run else []
        # Parents that get a new sub-step are rewritten once, by the parent update below
        # (which also sees their changed wording), not twice.
        parents_of_new = {tree[n].parent for n in find_missing(b, root, tree)}
        keep = protected(root, b)
        for f in b["files"]:
            fpath = root / f
            regions, lines, stale = stale_regions(fpath, b["lang"], tree)
            keys = L.region_keys(regions)
            for i, r in [(i, r) for i, r in stale if (f, keys[i]) in keep]:
                results.append((f, r.label, HAND_EDIT_MSG))
            stale = [(i, r) for i, r in stale if (f, keys[i]) not in keep]
            stale = [(i, r) for i, r in stale
                     if not (any(t in parents_of_new for t, _ in r.tags)
                             and not any(rr.parent == i and rr.kind == "node" for rr in regions))]
            if not stale:
                continue
            jobs = []
            for idx, r in stale:
                ref = None
                if b["name"] != ref_name:
                    # Use the reference's text for the changed steps, whatever region they sit in.
                    changed = {nid for nid, h in r.tags if h != tree[nid].hash}
                    texts = [v for k, v in reference_text.items() if changed & set(k.split("+"))]
                    if texts:
                        ref = dict(build=ref_name, lang=texts[0]["lang"],
                                   text="\n\n".join(t["text"] for t in texts))
                nest = nested_regions(regions, idx)
                prompt = build_prompt(b, f, lines, r, tree, lock, ref, nested=nest)
                tag = f"{b['name']}__{r.label.replace(' + ', '+')}"
                (log_dir / f"{tag}.prompt.txt").write_text(SYSTEM + "\n\n" + prompt)
                jobs.append((r, prompt, tag, nested_markers(nest, tree, b)))
            if dry_run:
                results += [(f, r.label, "dry run: prompt written") for r, _, _, _ in jobs]
                continue
            with ThreadPoolExecutor(max_workers=4) as pool:
                replies = list(pool.map(
                    lambda j: call_generator(gen + ["--system-prompt", SYSTEM], j[1], scratch), jobs))
            # Splice bottom-up so earlier line numbers stay valid.
            order = sorted(zip(jobs, replies), key=lambda x: -x[0][0].start)
            cur = lines
            pending_adds = []
            for (r, prompt, tag, nest_m), reply in order:
                (log_dir / f"{tag}.reply.txt").write_text(reply)
                new, why = validate_and_splice(fpath, b["lang"], cur, r, clean_reply(reply), tree, nest_m)
                if new is None:
                    # One more try, told what was wrong.
                    retry = prompt + f"\n\n=== Your previous reply was rejected: {why}\nFix that."
                    (log_dir / f"{tag}.retry.prompt.txt").write_text(SYSTEM + "\n\n" + retry)
                    reply = call_generator(gen + ["--system-prompt", SYSTEM], retry, scratch)
                    (log_dir / f"{tag}.retry.reply.txt").write_text(reply)
                    new, why = validate_and_splice(fpath, b["lang"], cur, r, clean_reply(reply), tree, nest_m)
                if new is None:
                    results.append((f, r.label, f"REJECTED: {why}"))
                    continue
                fpath.write_text("\n".join(new) + "\n")
                cur = new
                pending_adds += split_reply(reply)[1]
                if b["name"] == ref_name:
                    start = r.start - 1
                    body = clean_reply(reply)
                    reference_text["+".join(nid for nid, _ in r.tags)] = dict(
                        lang=b["lang"], text="\n".join(body))
                results.append((f, r.label, f"regenerated ({len(clean_reply(reply))} lines)"))
            if pending_adds:
                cur, notes = apply_support_adds(cur, b["lang"], pending_adds)
                fpath.write_text("\n".join(cur) + "\n")
                results += [(f, "support", n) for n in notes]

        # New steps: insert a region after the previous sibling's region, then update the parent.
        for nid in find_missing(b, root, tree):
            new = tree[nid]
            sibs = tree[new.parent].children
            prev_id = next((c for c in reversed(sibs[:sibs.index(nid)]) if region_for(b, root, c)), None)
            loc = region_for(b, root, prev_id) if prev_id else None
            if not loc:
                results.append(("?", nid, "REJECTED: no earlier sibling region to insert after"))
                continue
            f, regions, lines, idx = loc
            fpath = root / f
            prev_r = regions[idx]
            # Insert after the outermost region that covers the previous sibling but not the parent.
            while prev_r.parent is not None and not any(t == new.parent for t, _ in regions[prev_r.parent].tags):
                prev_r = regions[prev_r.parent]
            ref = reference_text.get("insert:" + nid) if b["name"] != ref_name else None
            prompt = insert_prompt(b, f, lines, prev_r.end, new, tree[prev_id], tree, ref and ref["text"])
            tag = f"{b['name']}__new-{nid}"
            (log_dir / f"{tag}.prompt.txt").write_text(SYSTEM + "\n\n" + prompt)
            if dry_run:
                results.append((f, nid, "dry run: insert prompt written"))
                continue
            reply = call_generator(gen + ["--system-prompt", SYSTEM], prompt, scratch)
            (log_dir / f"{tag}.reply.txt").write_text(reply)
            body, why = body_from_reply(reply, f"{L.COMMENT[b['lang']]} @node {nid}@{new.hash}", b["lang"])
            if body is None:
                results.append((f, nid, f"REJECTED: {why}"))
                continue
            indent = lines[prev_r.start - 1][: len(lines[prev_r.start - 1]) - len(lines[prev_r.start - 1].lstrip())]
            body = reindent(body, indent)
            gap = [""] if indent else ["", ""]
            new_lines = lines[:prev_r.end] + gap + body + lines[prev_r.end:]
            new_lines, add_notes = apply_support_adds(new_lines, b["lang"], split_reply(reply)[1])
            before_ids = [t for r in regions if r.kind == "node" for t, _ in r.tags]
            why = splice_check(fpath, b["lang"], new_lines, before_ids + [nid])
            if why != "ok":
                results.append((f, nid, f"REJECTED: {why}"))
                continue
            fpath.write_text("\n".join(new_lines) + "\n")
            if b["name"] == ref_name:
                reference_text["insert:" + nid] = dict(lang=b["lang"], text="\n".join(body))
            results.append((f, nid, f"new step inserted ({len(body)} lines)"))
            results += [(f, "support", n) for n in add_notes]

            # Parent orchestration: only when the parent is its own function (no nested regions).
            ploc = region_for(b, root, new.parent)
            if not ploc:
                continue
            pf, pregions, plines, pidx = ploc
            pr = pregions[pidx]
            if (pf, L.region_keys(pregions)[pidx]) in keep:
                results.append((pf, new.parent, HAND_EDIT_MSG + " (the parent was not updated to call the new step)"))
                continue
            nested = any(rr.parent == pidx and rr.kind == "node" for rr in pregions)
            if nested:
                results.append((pf, new.parent, "parent runs its steps inline; no separate update needed"))
                continue
            ref = reference_text.get("parent:" + new.parent) if b["name"] != ref_name else None
            prompt = parent_prompt(b, pf, plines, pr, new, "\n".join(body), tree, ref and ref["text"], lock)
            tag = f"{b['name']}__parent-{new.parent}"
            (log_dir / f"{tag}.prompt.txt").write_text(SYSTEM + "\n\n" + prompt)
            reply = call_generator(gen + ["--system-prompt", SYSTEM], prompt, scratch)
            (log_dir / f"{tag}.reply.txt").write_text(reply)
            new_p, why = validate_and_splice(root / pf, b["lang"], plines, pr, clean_reply(reply), tree)
            if new_p is None:
                results.append((pf, new.parent, f"REJECTED parent update: {why}"))
                continue
            new_p, add_notes = apply_support_adds(new_p, b["lang"], split_reply(reply)[1])
            (root / pf).write_text("\n".join(new_p) + "\n")
            results += [(pf, "support", n) for n in add_notes]
            if b["name"] == ref_name:
                reference_text["parent:" + new.parent] = dict(lang=b["lang"], text="\n".join(clean_reply(reply)))
            results.append((pf, new.parent, "parent updated to call the new step"))
        return b["name"], results

    # Reference first (others need its text), then the rest in parallel.
    first = [b for b in builds if b["name"] == ref_name]
    rest = [b for b in builds if b["name"] != ref_name]
    for b in first:
        summary.append(do_build(b))
    with ThreadPoolExecutor(max_workers=4) as pool:
        summary += list(pool.map(do_build, rest))

    bad = 0
    for name, results in summary:
        if not results:
            print(f"{name:<20} nothing to regenerate")
        for f, label, status in results:
            print(f"{name:<20} {f}  [{label}]  {status}")
            bad += status.startswith(("REJECTED", "REFUSED"))
    print(f"\nprompts and replies: {log_dir.relative_to(root)}")
    return 1 if bad else 0


ERR_LOC = re.compile(r"""([\w./\\-]+\.(?:py|cpp|hpp|cs|ts))(?:"?, line |[:(])(\d+)""")


def repair(pj: Path, build_name: str, errors: str) -> int:
    """Map build/run errors to the regions they point at and regenerate those regions,
    with the error text in the prompt. Errors inside @support regions are reported, not touched."""
    cfg, root, tree, lock, _ = L.load_project(pj)
    set_context(cfg, root, tree)
    gen = cfg["generator"]["command"]
    b = next(x for x in cfg["builds"] if x["name"] == build_name)
    log_dir = new_log_dir(root, "-repair")
    (log_dir / "cwd").mkdir(exist_ok=True)
    status = 0
    for f in b["files"]:
        fpath = root / f
        regions, owner, lines, _ = L.parse_regions(fpath, b["lang"])
        hits: dict[int, list[str]] = {}
        err_lines = errors.splitlines()
        if "Traceback (most recent call last)" in errors:
            # A traceback lists every caller; only the innermost frame in this file is the fault.
            ours = [l for l in err_lines if ERR_LOC.search(l) and Path(ERR_LOC.search(l).group(1)).name == fpath.name]
            last = ours[-1:] if ours else []
            err_lines = last + [l for l in err_lines if not ERR_LOC.search(l)][-3:]
        for line in err_lines:
            for m in ERR_LOC.finditer(line):
                if not str(fpath).endswith(m.group(1).lstrip("./")) and Path(m.group(1)).name != fpath.name:
                    continue
                ln = int(m.group(2))
                if not 1 <= ln <= len(lines):
                    continue
                idx = owner[ln - 1]
                while idx is not None and regions[idx].kind not in ("node", "contract"):
                    idx = regions[idx].parent
                if idx is None:
                    print(f"{build_name:<20} {f}:{ln}  error in support code, not regenerated: {line.strip()[:100]}")
                    status = 1
                    continue
                hits.setdefault(idx, []).append(line.strip())
        keep = protected(root, b)
        keys = L.region_keys(regions)
        for idx in [i for i in hits if (f, keys[i]) in keep]:
            print(f"{build_name:<20} {f}  [{regions[idx].label}]  {HAND_EDIT_MSG}")
            status = 1
        hits = {i: v for i, v in hits.items() if (f, keys[i]) not in keep}
        # Repair bottom-up so line numbers stay valid; re-read between repairs.
        for idx in sorted(hits, key=lambda i: -regions[i].start):
            regions, _, lines, _ = L.parse_regions(fpath, b["lang"])
            r = regions[idx]
            reason = "\n".join(dict.fromkeys(hits[idx] + [l.strip() for l in err_lines if l.strip() and not ERR_LOC.search(l)][-3:]))
            tag = f"{build_name}__repair-{r.label.replace(' + ', '+').replace(' ', '-')}"
            if r.kind == "contract":
                conv = conventions_text(b)
                prompt = (contract_prompt(b, f, lines, r, tree, conv) + "\n\n=== This region is being regenerated because "
                          "the build FAILED with the errors below. Fix the cause; if the fix needs an import, request "
                          "it with @add-to-support.\n" + reason)
                want = lines[r.start - 1].split("@contract", 1)[1].strip().rpartition("@")[0]
                marker = f"{L.COMMENT[b['lang']]} @contract {want}@{L.contract_hash(tree, b)}"
            else:
                nest = nested_regions(regions, idx)
                prompt = build_prompt(b, f, lines, r, tree, lock, None, reason=reason, nested=nest)
                marker = None
            (log_dir / f"{tag}.prompt.txt").write_text(SYSTEM + "\n\n" + prompt)
            reply = call_generator(gen + ["--system-prompt", SYSTEM], prompt, log_dir / "cwd")
            (log_dir / f"{tag}.reply.txt").write_text(reply)
            if marker:
                body, why = body_from_reply(reply, marker, b["lang"])
                if body is None:
                    new = None
                else:
                    indent = lines[r.start - 1][: len(lines[r.start - 1]) - len(lines[r.start - 1].lstrip())]
                    new, why = lines[:r.start - 1] + reindent(body, indent) + lines[r.end:], "ok"
            else:
                new, why = validate_and_splice(fpath, b["lang"], lines, r, clean_reply(reply), tree,
                                               nested_markers(nest, tree, b))
            if new is None:
                print(f"{build_name:<20} {f}  [{r.label}]  REJECTED: {why}")
                status = 1
                continue
            new, notes = apply_support_adds(new, b["lang"], split_reply(reply)[1])
            fpath.write_text("\n".join(new) + "\n")
            print(f"{build_name:<20} {f}  [{r.label}]  repaired")
            for n in notes:
                print(f"{build_name:<20} {f}  [support]  {n}")
    print(f"prompts and replies: {log_dir.relative_to(root)}")
    return status


GEN_SYSTEM = """You are the code generator for a "ladder" project. Programs are written as a tree of
plain-English steps; code is generated from those steps. You will write ONE WHOLE SOURCE FILE.
Reply with ONLY the file's contents. No explanation, no Markdown fences.
Every step in the tree gets its own region, opened with its exact marker line (given below) and
closed with an @end line. Types and fields that spell out the data blocks go in @contract regions
(marker given below); imports and helpers go in labeled @support regions. Nothing may sit
outside a region except blank lines and comments. Do exactly what each step's English says:
its in:/out: lines are a contract, its > lines say how."""


def in_scope(b: dict, nid: str) -> bool:
    scope = b.get("steps")
    return not scope or any(fnmatch.fnmatchcase(nid, pat) for pat in scope)


def tree_for_prompt(tree: dict, lang: str, b: dict | None = None) -> str:
    out = []
    for n in tree.values():
        pad = "  " * n.depth
        out.append(pad + step_block(n).replace("\n", "\n" + pad))
        if b is None or in_scope(b, n.id):
            out.append(f"{pad}  marker: {L.COMMENT[lang]} @node {n.id}@{n.hash}")
        else:
            out.append(f"{pad}  (implemented in another file of this program; do not write it here, only call it)")
        out.append("")
    return "\n".join(out)


def read_files_text(root: Path, b: dict) -> str:
    """Files the generator may read but never writes (hand-written types, helpers), from the build's "reads"."""
    parts = []
    for f in b.get("reads", []):
        parts += ["", f"=== {f} (exists already; read only, do not repeat or change it):", (root / f).read_text()]
    return "\n".join(parts)


def run_build_check(cfg: dict, root: Path, target: Path) -> str:
    """Run the project's "check_command" (e.g. ["npx", "tsc", "--noEmit"]) and return the error
    lines that point at `target` (other files may be mid-generation). Empty when it builds, or when
    no command is configured."""
    cmd = cfg.get("check_command")
    if not cmd:
        return ""
    cwd = (root / cfg.get("check_cwd", ".")).resolve()
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, timeout=600)
    except (OSError, subprocess.TimeoutExpired) as e:
        return f"(check command failed to run: {e})"
    if res.returncode == 0:
        return ""
    rel = str(target.resolve().relative_to(cwd)) if target.resolve().is_relative_to(cwd) else target.name
    all_lines = [l for l in (res.stdout + res.stderr).splitlines() if re.search(r"\berror\b|Error|FAIL", l)]
    mine = [l for l in all_lines if rel in l or target.name in l]
    others = list(dict.fromkeys(l for l in all_lines if l not in mine))
    out = mine[:20]
    if others:
        # A rename or a changed signature in this file breaks its callers and tests: their errors are
        # this file's problem too.
        out += ["(errors in other files; they may be caused by this one, for example a renamed member "
                "or a changed constructor:)"] + others[:12]
    return "\n".join(out) if out else (res.stdout + res.stderr)[-2000:]


def generate(pj: Path, build_name: str, attempts: int = 2) -> int:
    """Write a build's file from scratch (for a new build or language)."""
    cfg, root, tree, lock, _ = L.load_project(pj)
    set_context(cfg, root, tree)
    gen = cfg["generator"]["command"]
    b = next(x for x in cfg["builds"] if x["name"] == build_name)
    if len(b["files"]) != 1:
        print("generate handles one-file builds only")
        return 2
    target = root / b["files"][0]
    if OUT:
        target = Path(OUT).resolve()
    edited = protected(root, b) if not OUT else set()
    if edited:
        print(f"{build_name}: REFUSED: generate rewrites the whole file, and these regions were edited by hand: "
              + ", ".join(k for _, k in sorted(edited)) + ". Move the changes into the English, `ladder accept` "
              "them, or pass --discard-hand-edits")
        return 1
    log_dir = new_log_dir(root, f"-generate-{build_name}")
    (log_dir / "cwd").mkdir(parents=True, exist_ok=True)
    conv = "\n\n".join((root / c).read_text() for c in b.get("conventions", []))
    ref_name = cfg.get("compare", {}).get("reference")
    parts = [f"LANGUAGE: {b['lang']}    BUILD: {b['name']}    FILE: {b['files'][0]}",
             MODE_RULES.get(b.get("mode", "literal"), MODE_RULES["literal"]), "",
             "=== Conventions for this build:", conv, "",
             f"=== Types and fields that spell out the data blocks below go in regions opened with "
             f"`{L.COMMENT[b['lang']]} @contract <label>@{L.contract_hash(tree, b)}` (label: types, state, ...), "
             f"laid out as the conventions say.",
             "=== The English tree (every step with a marker line needs a region with that marker):",
             tree_for_prompt(tree, b["lang"], b), context_text(b, conventions=False)]
    ref = next((x for x in cfg["builds"] if x["name"] == ref_name), None) if ref_name else None
    # Port from the reference only when it implements the same steps and its file has code in it.
    if (ref and ref_name != build_name and ref.get("steps") == b.get("steps")
            and (root / ref["files"][0]).exists() and (root / ref["files"][0]).read_text().strip()):
        parts += ["", f"=== The reference build ({ref_name}, {ref['lang']}) already implements this tree. "
                  f"Port it: same behavior, same constants, same order of requests and results, same "
                  f"data keys, written idiomatically for {b['lang']}:", (root / ref["files"][0]).read_text()]
    prompt = "\n".join(parts)
    feedback = ""
    for attempt in range(1, attempts + 1):
        full = prompt + (f"\n\n=== Your previous attempt was rejected: {feedback}\nFix that." if feedback else "")
        (log_dir / f"attempt{attempt}.prompt.txt").write_text(GEN_SYSTEM + "\n\n" + full)
        reply = call_generator(gen + ["--system-prompt", GEN_SYSTEM], full, log_dir / "cwd")
        (log_dir / f"attempt{attempt}.reply.txt").write_text(reply)
        lines = clean_reply(reply)
        tmp = target.with_name(target.name + ".gen-tmp")
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text("\n".join(lines) + "\n")
        try:
            regions, _, _, probs = L.parse_regions(tmp, b["lang"])
        finally:
            tmp.unlink()
        tagged = {}
        contract_tags = []
        for r in regions:
            if r.kind == "contract":
                contract_tags += [h for _, h in r.tags]
                continue
            for nid, h in r.tags:
                tagged.setdefault(nid, []).append(h)
        issues = [p["msg"] for p in probs]
        issues += [f"@contract region has hash {h}, expected {L.contract_hash(tree, b)}"
                   for h in contract_tags if h != L.contract_hash(tree, b)]
        if b.get("data") and not contract_tags:
            issues.append("the data blocks need at least one @contract region")
        issues += [f"step [{nid}] has no region" for nid in tree if nid not in tagged and in_scope(b, nid)]
        issues += [f"step [{nid}] belongs to another file; remove its region" for nid in tagged
                   if nid in tree and not in_scope(b, nid)]
        issues += [f"step [{nid}] has {len(v)} regions; it needs exactly one" for nid, v in tagged.items() if len(v) > 1]
        issues += [f"step [{nid}] marker has hash {v[0]}, expected {tree[nid].hash}"
                   for nid, v in tagged.items() if nid in tree and v[0] != tree[nid].hash]
        issues += [f"region tagged with unknown step [{nid}]" for nid in tagged if nid not in tree]
        if not issues:
            target.write_text("\n".join(lines) + "\n")
            if OUT and cfg.get("check_command"):
                # Build with the generated file swapped into the real path, then put the original back.
                # A lock keeps two --out generations in one tree from building each other's output.
                import fcntl
                real = root / b["files"][0]
                saved = real.read_bytes() if real.exists() else None
                (root / ".ladder").mkdir(exist_ok=True)
                lock_f = open(root / ".ladder" / "build.lock", "w")
                fcntl.flock(lock_f, fcntl.LOCK_EX)
                try:
                    real.write_text("\n".join(lines) + "\n")
                    build_errors = run_build_check(cfg, root, real)
                finally:
                    if saved is None:
                        real.unlink(missing_ok=True)
                    else:
                        real.write_bytes(saved)
                    fcntl.flock(lock_f, fcntl.LOCK_UN)
                    lock_f.close()
            else:
                build_errors = "" if OUT else run_build_check(cfg, root, target)
            if build_errors and attempt < attempts:
                feedback = "the file was written but does not build:\n" + build_errors
                print(f"{build_name}: attempt {attempt} does not build; retrying with the errors")
                continue
            print(f"{build_name}: generated {target} ({len(lines)} lines, attempt {attempt})"
                  + (" -- STILL DOES NOT BUILD, run `ladder repair` with:\n" + build_errors if build_errors else ""))
            print(f"prompts and replies: {log_dir.relative_to(root)}")
            return 1 if build_errors else 0
        feedback = "; ".join(issues[:8])
        print(f"{build_name}: attempt {attempt} rejected: {feedback}")
    print(f"prompts and replies: {log_dir.relative_to(root)}")
    return 1


if __name__ == "__main__":
    args = sys.argv[1:]
    sys.exit(regen(Path(args[0]), only=next((a.split("=", 1)[1] for a in args if a.startswith("--build=")), None),
                   dry_run="--dry-run" in args))

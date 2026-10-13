#!/usr/bin/env python3
"""ladder: keep an English step tree and generated code in sync.

Commands
  ladder check  <project.json> [--builds=A,B] [--all-differences] [--since=GIT_REF]
                                   verify tags, coverage, staleness, vocabulary, links, comparisons
                                   exit 0 ok · 1 problems · 3 only awaiting a person's approval
                                   --since: report schema and linked-step changes since GIT_REF
                                   instead of since approval (before the first stamp)
  ladder test   <project.json> [NAME...]   run the tests capabilities (test: lines) and links
                                   ("test") declare, and record the results for check
  ladder hashes <project.json>   print each step's current hash (for whoever generates code)
  ladder stamp  <project.json>   approve the tree as it is now (writes ladder.lock.json)
  ladder view   <project.json> [out.html]   build the side-by-side viewer
  ladder export <project.json> [out.json]   the parsed tree, data, rules and vocabulary as JSON
  ladder init   <folder> --name NAME --build NAME:LANG [--build ...] [--adopted]   start a project
                                   (or --lang LANG to name a build after its language)
  ladder tag    <project.json> <regions.json> [--base GIT_REF]
                                   transcription: add the marker lines a regions file lists (line
                                   ranges of the file at GIT_REF, default HEAD), with the tree's hashes
  ladder adopt-check <project.json> [--base GIT_REF]
                                   transcription check: tagged files differ from GIT_REF (default HEAD)
                                   only by added comment lines
  ladder adopt-check --original A --tagged B --lang LANG      same check for one pair of files
  ladder replay <scenario.json|folder> --base URL --out traces/<build> [--mask id,token:presence,at:time]
                   [--header "K: V"] [--before-each "command to reset test data"] [--jwt]
                   [--record-headers set-cookie] [--observe "command run after each request"]
                                   send recorded requests to a running service; save each response as
                                   a trace, so an existing API and a generated one can be compared
  ladder regen  <project.json> [--build=NAME] [--dry-run] [--blind] [--redo=IDS] [--repair=N]
                                   regenerate stale regions with the project's generator (an LLM);
                                   --repair=N: then run check_command and repair what it reports,
                                   at most N rounds, until the code builds
  ladder generate <project.json> --build=NAME [--out=PATH]
                                   write a build's whole file from the tree (new build or language);
                                   --out writes elsewhere, to try regeneration without touching the file
  ladder repair <project.json> <errors.txt> --build=NAME
                                   regenerate the regions that build or run errors point at
  ladder schema <project.json> [ENTITY]
                                   the database schema the English can refer to ([[Entity.Property]]),
                                   read from the project's "schemas" (EF Core model snapshot or JSON)
  ladder retag  <project.json> <STEP IDS> [--build=NAME]
                                   the English was reworded without changing behavior: update the
                                   markers' hashes instead of regenerating (a person's call)
  ladder reference <project.json> --from=BUILD [--retire=A,B]
                                   an approved change of behaviour: BUILD's recording (made from the
                                   approved code) becomes the comparison's reference; the old reference
                                   traces move to traces/history/; --retire=A,B moves builds recorded
                                   from the old code that cannot be recorded again to history too
  ladder accept <project.json> [--build=NAME] [STEP IDS] [--exports] [--from=SCRATCH/ladder.json]
                                   accept hand edits to regions: the English still describes them
                                   (regen and repair refuse to overwrite hand-edited regions unless
                                   given --discard-hand-edits)
                                   --from: accept regions copied from a scratch copy, when each is
                                   exactly what that scratch project recorded as generated (copy the
                                   build files over first; accept does not copy)

check, hashes, stamp, view, export, init, adopt-check and replay never call an LLM: they are the
mechanical checks around it. generate, regen and repair call the project's generator command:
the LLM writes code and tags it, this tool decides whether the tags hold up.
"""
from __future__ import annotations

import fnmatch
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------- tree


@dataclass
class Node:
    id: str
    title: str
    depth: int
    line: int
    parent: str | None = None
    children: list[str] = field(default_factory=list)
    inputs: str = ""
    outputs: str = ""
    effects: str = ""
    steps: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    uses: list[str] = field(default_factory=list)
    compare: list[str] = field(default_factory=list)   # how results are compared; not in the hash
    reads: list[str] = field(default_factory=list)     # schema entities the step reads
    writes: list[str] = field(default_factory=list)    # schema entities the step writes
    calls: list[str] = field(default_factory=list)     # steps in other trees it calls: "api [api.1.1]"

    @property
    def is_leaf(self) -> bool:
        return not self.children

    def own_text(self, with_calls: bool = True) -> str:
        """Everything that defines this step, excluding its children.
        Whitespace is normalised so re-indenting never counts as an edit."""
        parts = [self.title, "in:" + self.inputs, "out:" + self.outputs,
                 "effects:" + self.effects, *("> " + s for s in self.steps),
                 *("note:" + n for n in self.notes), *("uses:" + u for u in self.uses)]
        # reads:/writes: are behavior too, but only steps that have them hash them (older trees keep their hashes)
        parts += [*("reads:" + r for r in self.reads), *("writes:" + w for w in self.writes)]
        if with_calls:
            parts += [*("calls:" + c for c in self.calls)]
        return "\n".join(" ".join(p.split()) for p in parts)

    @property
    def hash(self) -> str:
        """What the code is generated from (tags carry it). `calls:` lines are left out: declaring that a
        step calls another tree changes what a person reviews, not what the code must do."""
        return hashlib.sha1(self.own_text(with_calls=False).encode()).hexdigest()[:6]

    @property
    def review_hash(self) -> str:
        """What a person approves: the step's whole text, `calls:` included."""
        return hashlib.sha1(self.own_text().encode()).hexdigest()[:6]


NODE_RE = re.compile(r"^(\s*)\[([A-Za-z0-9_.\-]+)\]\s+(.+?)\s*$")
ATTR_RE = re.compile(r"^\s*(in|out|effects|note|uses|compare|reads|writes|calls):\s*(.*)$")
STEP_RE = re.compile(r"^\s*>\s?(.*)$")
DATA_RE = re.compile(r"^data\s+([A-Z][A-Za-z0-9_]*)\s*$")
RULE_RE = re.compile(r"^rule\s+([A-Za-z][A-Za-z0-9_ -]*?)\s*:\s*(.+)$")
FIELD_RE = re.compile(r"^\s+([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.*)$")


@dataclass
class DataBlock:
    name: str
    line: int
    fields: list[tuple[str, str]] = field(default_factory=list)
    rules: list[str] = field(default_factory=list)

    def real_fields(self) -> list[tuple[str, str]]:
        """The fields, without the block's `note:` lines."""
        return [(k, v) for k, v in self.fields if k != "note"]

    def text(self) -> str:
        return "\n".join([f"data {self.name}", *(f"  {k}: {' '.join(v.split())}" for k, v in self.fields),
                          *(f"  rule: {' '.join(r.split())}" for r in self.rules)])


class Tree(dict):
    """Steps by id, in file order, plus the file's data blocks and named rules."""
    def __init__(self):
        super().__init__()
        self.data: dict[str, DataBlock] = {}
        self.rules: dict[str, str] = {}
        self.warnings: list[tuple[int, str]] = []   # (line, message) for lines that parse but look wrong


def split_uses(text: str) -> list[str]:
    return [u.strip() for u in re.split(r"[;,]", text) if u.strip()]


def parse_tree(path: Path) -> Tree:
    nodes = Tree()
    stack: list[Node] = []
    current: Node | None = None
    block: DataBlock | None = None
    for i, raw in enumerate(path.read_text().splitlines(), 1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if m := DATA_RE.match(raw):
            name = m.group(1)
            if name in nodes.data:
                raise SystemExit(f"{path}:{i}: data {name} is defined twice")
            block = nodes.data[name] = DataBlock(name, i)
            current = None
            continue
        if m := RULE_RE.match(raw):
            name = " ".join(m.group(1).split())
            if name in nodes.rules:
                raise SystemExit(f"{path}:{i}: rule '{name}' is defined twice")
            nodes.rules[name] = m.group(2).strip()
            block = current = None
            continue
        m = NODE_RE.match(raw)
        if m:
            block = None
            indent, nid, title = m.groups()
            depth = len(indent.replace("\t", "  ")) // 2
            if nid in nodes:
                raise SystemExit(f"{path}:{i}: step id [{nid}] is used twice")
            while stack and stack[-1].depth >= depth:
                stack.pop()
            node = Node(nid, title, depth, i, parent=stack[-1].id if stack else None)
            if stack:
                stack[-1].children.append(nid)
            nodes[nid] = node
            stack.append(node)
            current = node
            continue
        if block is not None:
            if m := FIELD_RE.match(raw):
                key, val = m.groups()
                if key == "rule":
                    block.rules.append(val.strip())
                else:
                    # `note:` lines are notes, not fields (round 11: two notes in one block failed as a repeated field,
                    # and one became a field named "note"); they keep their place, so the block's text is unchanged
                    if key != "note" and any(k == key for k, _ in block.fields):
                        raise SystemExit(f"{path}:{i}: data {block.name} has field '{key}' twice")
                    block.fields.append((key, val.strip()))
                continue
            raise SystemExit(f"{path}:{i}: inside data {block.name}, expected 'field: description' or 'rule: ...': {raw.strip()}")
        if current is None:
            raise SystemExit(f"{path}:{i}: expected a [step], 'data Name' or 'rule name: ...' line: {raw.strip()}")
        if ATTR_RE.match(raw) or STEP_RE.match(raw):
            want = "  " * (current.depth + 1)
            got = raw[: len(raw) - len(raw.lstrip())].replace("\t", "  ")
            if got != want:
                nodes.warnings.append((i, f"indented {len(got)} spaces; lines of [{current.id}] need {len(want)}"))
        if m := ATTR_RE.match(raw):
            key, val = m.groups()
            if key == "note":
                current.notes.append(val)
            elif key == "uses":
                current.uses.extend(split_uses(val))
            elif key == "compare":
                current.compare.extend(c.strip() for c in val.split(";") if c.strip())
            elif key == "calls":
                current.calls.extend(x.strip() for x in re.split(r"[,;]", val) if x.strip())
            elif key in ("reads", "writes"):
                getattr(current, key).extend(x.strip() for x in re.split(r"[,;]", val) if x.strip())
            else:
                setattr(current, {"in": "inputs", "out": "outputs"}.get(key, key), val)
        elif m := STEP_RE.match(raw):
            current.steps.append(m.group(1))
        else:
            raise SystemExit(f"{path}:{i}: not a step, contract line, 'uses:' or '>' line: {raw.strip()}")
    return nodes


# ---------------------------------------------------------------- vocabulary

CAP_RE = re.compile(r"^capability\s+(.+?)\s*$")
CAP_ATTR_RE = re.compile(r"^\s+([A-Za-z][A-Za-z0-9_+#.\-]*)\s*:\s*(.*)$")
CAP_KEYS = {"in", "out", "known", "check", "note", "test", "reads", "writes"}


@dataclass
class Capability:
    name: str
    line: int
    inputs: str = ""
    outputs: str = ""
    bindings: dict[str, str] = field(default_factory=dict)   # language or build name -> binding
    known: list[str] = field(default_factory=list)
    checks: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    tests: list[str] = field(default_factory=list)       # "typescript | npx vitest run x.test.ts"
    tables: list[str] = field(default_factory=list)      # reads:/writes: schema entities its tests touch

    def contract_hash(self) -> str:
        t = f"{self.name}\nin:{' '.join(self.inputs.split())}\nout:{' '.join(self.outputs.split())}"
        return hashlib.sha1(t.encode()).hexdigest()[:6]

    def binding_hash(self, key: str) -> str:
        return hashlib.sha1(" ".join(self.bindings.get(key, "").split()).encode()).hexdigest()[:6]

    def binding_for(self, build: dict) -> tuple[str, str] | None:
        for key in (build["name"], build["lang"]):
            if key in self.bindings:
                return key, self.bindings[key]
        return None

    def text_for(self, build: dict | None = None) -> str:
        out = [f"capability {self.name}"]
        if self.inputs:
            out.append(f"  in: {self.inputs}")
        if self.outputs:
            out.append(f"  out: {self.outputs}")
        if build is None:
            out += [f"  {k}: {v}" for k, v in self.bindings.items()]
        elif (b := self.binding_for(build)):
            out.append(f"  {b[0]}: {b[1]}")
        out += [f"  known: {k}" for k in self.known] + [f"  note: {n}" for n in self.notes]
        return "\n".join(out)


PATHLIKE_RE = re.compile(r"[\w.@-]+(?:/[\w.@-]+)+\.\w+|[\w.-]+\.(?:py|cs|ts|tsx|js|jsx|mjs|go|rs|java|kt|rb|php|cpp|cc|h|hpp|swift|dart)\b")
CALL_KEYWORDS = {"await", "new", "return", "typeof", "sizeof", "if", "for", "foreach", "while", "switch", "catch",
                 "using", "lock", "var", "let", "const", "function", "async", "def", "fn", "func", "throw", "yield"}
CALL_NAME_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*(?:<[^<>()]*>)?\s*\(")
JSX_NAME_RE = re.compile(r"(?<![A-Za-z0-9_])<([A-Z][A-Za-z0-9_]*)[\s/>]")   # a component a binding renders: <DataGrid ... /> (not a generic: f<Row>())


def uses_name(text: str, name: str) -> bool:
    """Whether code calls `name(...)` or renders `<name ...>`."""
    return bool(re.search(r"\b" + re.escape(name) + r"\s*(?:<[^<>()]*>)?\s*\(", text)
                or re.search(r"(?<![A-Za-z0-9_])<" + re.escape(name) + r"[\s/>]", text))


def binding_parts(binding: str) -> tuple[str, str]:
    """(where, call) of a binding line: "(in repository) src/x.ts on lib 1.2 | await x.get(key)"."""
    where, _, call = binding.partition("|")
    return where.strip(), call.strip()


def binding_files(binding: str, bases: list[Path]) -> list[Path]:
    """The source files an "(in repository)" binding names, resolved against the first base where each exists.
    A binding for a published library or the platform names none."""
    where, _ = binding_parts(binding)
    if "(in repository)" not in where:
        return []
    out = []
    for tok in PATHLIKE_RE.findall(where.replace("(in repository)", " ")):
        for base in bases:
            p = (base / tok).resolve()
            if p.is_file():
                if p not in out:
                    out.append(p)
                break
    return out


def binding_call_names(binding: str) -> set[str]:
    """The names a binding's call part calls ("await storageService.get<T>(key)" -> {"get"}): code that uses the
    capability calls at least one of them."""
    _, call = binding_parts(binding)
    return ({m.group(1) for m in CALL_NAME_RE.finditer(call)} | {m.group(1) for m in JSX_NAME_RE.finditer(call)}) - CALL_KEYWORDS


def project_bases(cfg: dict, root: Path) -> list[Path]:
    """Where a binding's paths may be written from: the project folder, its check_cwd, and every folder above."""
    bases = [root.resolve()]
    if cfg.get("check_cwd"):
        bases.append((root / cfg["check_cwd"]).resolve())
    bases += list(root.resolve().parents)
    return list(dict.fromkeys(bases))


def parse_vocabulary(path: Path) -> dict[str, Capability]:
    caps: dict[str, Capability] = {}
    cur: Capability | None = None
    for i, raw in enumerate(path.read_text().splitlines(), 1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if m := CAP_RE.match(raw):
            name = " ".join(m.group(1).split())
            if name in caps:
                raise SystemExit(f"{path}:{i}: capability '{name}' is defined twice")
            cur = caps[name] = Capability(name, i)
            continue
        if cur is None or not (m := CAP_ATTR_RE.match(raw)):
            raise SystemExit(f"{path}:{i}: expected 'capability <name>' or an indented 'key: value' line: {raw.strip()}")
        key, val = m.groups()
        val = val.strip()
        if key == "in":
            cur.inputs = val
        elif key == "out":
            cur.outputs = val
        elif key == "known":
            cur.known.append(val)
        elif key == "check":
            cur.checks.append(val)
        elif key == "note":
            cur.notes.append(val)
        elif key == "test":
            cur.tests.append(val)
        elif key in ("reads", "writes"):
            cur.tables.extend(x.strip() for x in re.split(r"[,;]", val) if x.strip())
        else:
            cur.bindings[key] = val
    return caps


def load_vocabulary(cfg: dict, root: Path) -> dict[str, Capability] | None:
    v = cfg.get("vocabulary")
    return parse_vocabulary(root / v) if v else None


# ---------------------------------------------------------------- code regions

COMMENT_FOR_HIDDEN = "//"   # set by regen --blind for the placeholder line
COMMENT = {"python": "#", "cpp": "//", "c": "//", "csharp": "//", "typescript": "//",
           "javascript": "//", "rust": "//", "go": "//"}
BLOCK_COMMENT_LANGS = {"cpp", "c", "csharp", "typescript", "javascript", "rust", "go"}


@dataclass
class Region:
    kind: str                 # "node" or "support"
    tags: list[tuple[str, str]]  # (node id, hash written at generation time)
    label: str
    file: str
    start: int                # line of the @node marker
    end: int = 0              # line of the @end marker
    parent: int | None = None  # index of enclosing region
    code_lines: int = 0


def parse_regions(path: Path, lang: str):
    """Returns (regions, line_owner, problems). line_owner[i] = innermost region index for line i+1."""
    c = re.escape(COMMENT[lang])
    open_re = re.compile(rf"^\s*{c}\s*@(node|support|contract)\b\s*(.*)$")
    end_re = re.compile(rf"^\s*{c}\s*@end\b")
    comment_re = re.compile(rf"^\s*{c}")
    lines = path.read_text().splitlines()
    regions: list[Region] = []
    owner: list[int | None] = [None] * len(lines)
    problems: list[dict] = []
    stack: list[int] = []
    in_block = False
    for i, raw in enumerate(lines, 1):
        if m := open_re.match(raw):
            kind, rest = m.groups()
            tags, label = [], rest.strip()
            if kind == "node":
                tags = []
                for tok in rest.split():
                    if "@" not in tok:
                        problems.append(dict(kind="bad-tag", file=str(path), line=i,
                                             msg=f"tag '{tok}' has no @hash"))
                        continue
                    nid, h = tok.split("@", 1)
                    tags.append((nid, h))
                label = " + ".join(t[0] for t in tags)
            elif kind == "contract":
                # "@contract <label>@<hash>": types generated from every step's in:/out: lines
                tok = rest.strip()
                name, _, h = tok.rpartition("@")
                tags = [("@contract", h)] if name else []
                if not name:
                    problems.append(dict(kind="bad-tag", file=str(path), line=i,
                                         msg="@contract region needs '<label>@<hash>'"))
                label = f"contract {name}"
            regions.append(Region(kind, tags, label, str(path), i,
                                  parent=stack[-1] if stack else None))
            stack.append(len(regions) - 1)
            owner[i - 1] = stack[-1]
            continue
        if end_re.match(raw):
            if not stack:
                problems.append(dict(kind="bad-tag", file=str(path), line=i, msg="@end with nothing open"))
            else:
                owner[i - 1] = stack[-1]
                regions[stack.pop()].end = i
            continue
        owner[i - 1] = stack[-1] if stack else None
        s = raw.strip()
        # Track /* */ comments so they are not counted as code.
        if lang in BLOCK_COMMENT_LANGS:
            if in_block:
                if "*/" in s:
                    in_block = False
                continue
            if s.startswith("/*"):
                in_block = "*/" not in s
                continue
        if not s or comment_re.match(raw):
            continue
        if lang == "python" and (s.startswith('"""') or s.startswith("'''")):
            continue  # docstring line; good enough for a prototype
        if stack:
            regions[stack[-1]].code_lines += 1
        else:
            problems.append(dict(kind="untagged", file=str(path), line=i,
                                 msg=f"code outside any @node or @support region: {s[:60]}"))
    for idx in stack:
        problems.append(dict(kind="bad-tag", file=str(path), line=regions[idx].start,
                             msg=f"region '{regions[idx].label}' never closed with @end"))
    return regions, owner, lines, problems


# ---------------------------------------------------------------- checks


def load_project(pj: Path):
    cfg = json.loads(pj.read_text())
    root = pj.parent
    tree = parse_tree(root / cfg["tree"])
    lock_path = root / "ladder.lock.json"
    lock = json.loads(lock_path.read_text()) if lock_path.exists() else {}
    return cfg, root, tree, lock, lock_path


def group_untagged(probs: list[dict]) -> list[dict]:
    """Merge untagged lines that follow each other (blank and comment lines between them allowed)
    into one problem per stretch, so an untagged file reads as a few ranges, not hundreds of lines."""
    out, run = [], None
    for p in probs:
        if p["kind"] != "untagged":
            out.append(p)
            continue
        if run and run["file"] == p["file"] and p["line"] - run["last"] <= 12:
            run["last"], run["count"] = p["line"], run["count"] + 1
            continue
        run = dict(p, last=p["line"], count=1, first_text=p["msg"])
        out.append(run)
    for p in out:
        if p.get("kind") == "untagged" and p["count"] > 1:
            p["msg"] = (f"{p['count']} lines of code outside any region (lines {p['line']}-{p['last']}), "
                        f"starting: {p['first_text'].split(': ', 1)[-1]}")
    return out


def build_data(tree, build: dict | None) -> dict:
    """The data blocks a build's @contract regions spell out: those named by the build's "data"
    patterns, or every data block when it has none."""
    data = getattr(tree, "data", {})
    pats = (build or {}).get("data")
    if pats is None:
        return data          # no "data" key: every data block
    if not pats:
        return {}            # "data": [] means none
    return {k: d for k, d in data.items() if any(fnmatch.fnmatchcase(k, p) for p in pats)}


def build_in_scope(build: dict | None, nid: str) -> bool:
    scope = (build or {}).get("steps")
    if scope is None:
        return True          # no "steps" key: every step
    return any(fnmatch.fnmatchcase(nid, pat) for pat in scope)   # "steps": [] means none (support only)


def contract_hash(tree: dict[str, Node], build: dict | None = None) -> str:
    """Hash of the in:/out: lines of the steps a build implements, plus the data blocks it spells
    out and the named rules: the contract its @contract regions are generated from. Without a
    build (or for a build with no "steps" or "data"), every step and data block."""
    text = "\n".join(f"{n.id} in:{' '.join(n.inputs.split())} out:{' '.join(n.outputs.split())}"
                     for n in tree.values() if build_in_scope(build, n.id))
    data = build_data(tree, build)
    rules = getattr(tree, "rules", {})
    if build and ("steps" in build or "data" in build):
        # A scoped build depends only on the named rules its steps or data blocks mention.
        text_in = "\n".join([n.own_text() for n in tree.values() if build_in_scope(build, n.id)]
                            + [d.text() for d in data.values()]).lower()
        rules = {k: v for k, v in rules.items() if k.lower() in text_in}
    if data:   # only trees that have data blocks or rules hash them, so older trees keep their hash
        text += "\n" + "\n".join(d.text() for d in data.values())
    if rules:
        text += "\n" + "\n".join(f"rule {k}: {' '.join(v.split())}" for k, v in rules.items())
    return hashlib.sha1(text.encode()).hexdigest()[:6]


CONTRACT_DECL_RE = re.compile(r"\b(?:class|interface|record|struct|type|enum)\s+([A-Z][A-Za-z0-9_]*)\b")


def region_contract_hash(tree, build: dict | None, code: list[str], label: str = "") -> str:
    """The hash a @contract region carries: from the data blocks its code declares (a region that
    declares ClockInRequest depends on data ClockInRequest and the rules it names), so editing one
    block marks only the regions that spell it out stale. A region that declares no data block
    depends on the whole build contract (contract_hash)."""
    # A region labelled "rule <name>" holds a named rule's code (a constant): it follows that rule's text.
    if label.replace("contract ", "", 1).startswith("rule "):
        rname = label.replace("contract ", "", 1)[5:].strip()
        rtext = getattr(tree, "rules", {}).get(rname)
        if rtext is not None:
            return "r" + hashlib.sha1(f"rule {rname}: {' '.join(rtext.split())}".encode()).hexdigest()[:5]
    data = build_data(tree, build)
    def base(t: str) -> str:   # ICircuitOptions / ClockInRequestDto / ClockInRequestDTO -> the block name
        t = re.sub(r"(Dto|DTO)$", "", t)
        return t[1:] if len(t) > 2 and t[0] == "I" and t[1].isupper() and t[1:] in data else t
    declared = {base(m.group(1)) for l in code for m in CONTRACT_DECL_RE.finditer(l)}
    # the region's label names its block when the class name doesn't (@contract ClockStatus@... over
    # class ClockStatusResponseDto)
    declared |= {w for w in re.split(r"[\s,+]+", label.replace("contract ", "", 1)) if w}
    declared = sorted(declared & set(data))
    if not declared:
        return contract_hash(tree, build)
    text = "\n".join(data[k].text() for k in declared).lower()
    rules = {k: v for k, v in getattr(tree, "rules", {}).items() if k.lower() in text}
    t = "\n".join([data[k].text() for k in declared] + [f"rule {k}: {' '.join(v.split())}" for k, v in rules.items()])
    return "d" + hashlib.sha1(t.encode()).hexdigest()[:5]


def label_blocks(tree, build: dict | None, label: str) -> list[str]:
    """The data blocks a @contract region's label names (`@contract ClockInRequest@...`, or several joined
    with + or commas), among the blocks the build spells out."""
    data = build_data(tree, build)
    return [w for w in re.split(r"[\s,+]+", label.replace("contract ", "", 1)) if w in data]


def declared_blocks(tree, build: dict | None, code: list[str]) -> set[str]:
    """The build's data blocks a piece of code declares a type for (class ClockInRequestDto -> ClockInRequest)."""
    data = build_data(tree, build)
    def base(t: str) -> str:
        t = re.sub(r"(Dto|DTO)$", "", t)
        return t[1:] if len(t) > 2 and t[0] == "I" and t[1].isupper() and t[1:] in data else t
    return {base(m.group(1)) for l in code for m in CONTRACT_DECL_RE.finditer(l)} & set(data)


def contract_layout(root: Path, build: dict, tree) -> list[tuple[str, str, list[str]]]:
    """Where a build's @contract regions are: (file, label, the data blocks the label names)."""
    out = []
    for f in build.get("files", []):
        fpath = root / f
        if not fpath.exists():
            continue
        for r in parse_regions(fpath, build["lang"])[0]:
            if r.kind == "contract":
                out.append((f, r.label, label_blocks(tree, build, r.label)))
    return out


def contract_region_ok(tree, build, tag_hash: str, code: list[str], label: str = "") -> bool:
    """A @contract region is current when its tag matches what its code depends on now (per region),
    or the whole build contract (regions written before per-region hashes)."""
    return tag_hash in (region_contract_hash(tree, build, code, label), contract_hash(tree, build))


def restamp_contracts(root: Path, cfg: dict) -> int:
    """After generation: give each @contract region carrying the build-wide hash its per-region hash."""
    n = 0
    for b in cfg.get("builds", []):
        if b.get("tagged") is False:
            continue
        whole = None
        for f in b.get("files", []):
            fpath = root / f
            if not fpath.exists():
                continue
            regions, _, lines, _ = parse_regions(fpath, b["lang"])
            changed = False
            for r in regions:
                if r.kind != "contract" or not r.tags:
                    continue
                whole = whole or contract_hash(root_tree(root, cfg), b)
                if r.tags[0][1] != whole:
                    continue
                own = region_own_code(regions, lines, regions.index(r))
                h = region_contract_hash(root_tree(root, cfg), b, own, r.label)
                if h != whole:
                    lines[r.start - 1] = lines[r.start - 1].replace(f"@{whole}", f"@{h}", 1)
                    changed = True
                    n += 1
            if changed:
                fpath.write_text("\n".join(lines) + "\n")
    return n


_TREES: dict = {}


def root_tree(root: Path, cfg: dict):
    key = (str(root), cfg["tree"])
    if key not in _TREES:
        _TREES[key] = parse_tree(root / cfg["tree"])
    return _TREES[key]


def region_own_code(regions: list, lines: list[str], idx: int) -> list[str]:
    """A region's lines, without its marker lines and without nested regions."""
    r = regions[idx]
    inner = set()
    for j, rr in enumerate(regions):
        p = rr.parent
        while p is not None and p != idx:
            p = regions[p].parent
        if p == idx:
            inner.update(range(rr.start - 1, rr.end))
    return [lines[k] for k in range(r.start, r.end - 1) if k not in inner]


def rule_citers(tree, name: str) -> list[str]:
    """Steps whose English cites a named rule ("(rule message limit)")."""
    rx = re.compile(r"\brule\s+" + re.escape(name) + r"\b", re.I)
    return [n.id for n in tree.values() if rx.search(n.own_text())]


def changed_rules(tree, lock: dict) -> list[str]:
    """Named rules whose text differs from the approved text (new ones included)."""
    was = (lock or {}).get("@data")
    if was is None:
        return []
    return [k for k, v in getattr(tree, "rules", {}).items() if was.get(f"rule {k}") != " ".join(v.split())]


def rule_in_support_warnings(root: Path, cfg: dict, tree, lock: dict | None = None) -> list[dict]:
    """A value a named rule states (a number, a quoted text) written in a @support region of a build that implements
    steps citing the rule: regeneration never rewrites support code, so a change to the rule cannot reach it (round 11:
    the 5000-character limit lived in support constants in both apps)."""
    out = []
    was = (lock or {}).get("@data", {})
    for name, text in getattr(tree, "rules", {}).items():
        text = text + " " + was.get(f"rule {name}", "")   # the approved value too: support code keeps the old one
        # numbers of three digits or more, and quoted texts of more than one word (a key name like "message" is not one)
        values = set(re.findall(r"\b\d{3,}\b", text)) | {q for q in re.findall(r'"([^"]{4,})"', text) if re.search(r"[\s.]", q)}
        users = rule_citers(tree, name)
        if not values or not users:
            continue
        for b in cfg.get("builds", []):
            if b.get("tagged") is False:      # any build: a constant in one file is imported by another's steps
                continue
            for f in b.get("files", []):
                if not (root / f).exists():
                    continue
                regions, _, lines, _ = parse_regions(root / f, b["lang"])
                for i, r in enumerate(regions):
                    if r.kind != "support":
                        continue
                    cm = COMMENT[b["lang"]]
                    own = "\n".join(l for l in region_own_code(regions, lines, i)
                                    if not l.lstrip().startswith((cm, "/*", "*", '"""')))
                    hit = sorted(v for v in values if re.search(r"(?<![\w.])" + re.escape(v) + r"(?![\w.])", own))
                    if hit:
                        out.append(dict(kind="rule-in-support", node=name,
                                        msg=f"rule {name}'s value {', '.join(hit)} is written in the @support region "
                                            f"'{r.label}' of {f} (line {r.start}): regeneration never rewrites support "
                                            f"code, so a change to the rule cannot reach it. Tag that code with a step "
                                            f"that cites the rule ({', '.join(users[:3])})"))
    return out


def data_texts(tree) -> dict[str, str]:
    """Data blocks and named rules by name ("data Note", "rule tag name"), as approved text."""
    out = {f"data {k}": d.text() for k, d in getattr(tree, "data", {}).items()}
    out.update({f"rule {k}": " ".join(v.split()) for k, v in getattr(tree, "rules", {}).items()})
    return out


def baseline_lock(cfg: dict, root: Path, ref: str) -> dict | None:
    """What a stamp at `ref` would have recorded for the tree's steps and data (None if the tree
    is not in git at that ref)."""
    import ladder_links as K
    old = K.tree_at(cfg, root, ref)
    if old is None:
        return None
    out = {n.id: {"hash": n.hash, "review_hash": n.review_hash,
                  "parent_hash": old[n.parent].hash if n.parent else None,
                  "text": n.own_text(), "compare": n.compare} for n in old.values()}
    if data_texts(old):
        out["@data"] = data_texts(old)
    return out


def check(pj: Path, only_builds: list[str] | None = None, schema_since: str | None = None,
          links_since: str | None = None, review_since: str | None = None) -> dict:
    cfg, root, tree, lock, _ = load_project(pj)
    if only_builds:
        ref = cfg.get("compare", {}).get("reference")
        cfg["builds"] = [b for b in cfg["builds"] if b["name"] in only_builds or b["name"] == ref]
    report = {"tree": [], "builds": []}
    # Nothing approved yet? Compare with the project's baseline commit instead of a lock, so a review
    # shows what changed, not every step as new. An explicit --since wins; a stamp always wins.
    base = None
    if review_since:
        base = review_since          # --since: review everything against that commit, stamp or not
    elif not any(not k.startswith("@") for k in lock) and cfg.get("baseline") and not (schema_since or links_since):
        base = cfg["baseline"]
    if base:
        old = baseline_lock(cfg, root, base)
        known = subprocess.run(["git", "-C", str((root / cfg["tree"]).resolve().parent), "rev-parse", "--verify",
                                "--quiet", f"{base}^{{commit}}"], capture_output=True).returncode == 0
        if old is None and known:
            # A first transcription: the tree is new since the baseline, which is what the skill sets up.
            report["tree"].append(dict(kind="baseline-new", node=base,
                                       msg=f"the tree did not exist at {base}: every step is new since the baseline"))
        elif old is None:
            report["tree"].append(dict(kind="baseline", node=base,
                                       msg=f"{base} is not a commit git knows here; every step shows as new "
                                           f"(git fetch, or fix the ref)"))
        else:
            lock = {**{k: v for k, v in lock.items() if k.startswith("@") and k not in ("@data",)}, **old}
            schema_since = schema_since or base
            links_since = links_since or base
            report["baseline"] = base

    # Tree review: what changed since the tree was last approved?
    for n in tree.values():
        was = lock.get(n.id)
        if was is None:
            report["tree"].append(dict(kind="new", node=n.id, msg="new step, not yet approved"))
            continue
        if was.get("review_hash", was["hash"]) != (n.review_hash if "review_hash" in was else n.hash):
            report["tree"].append(dict(kind="edited", node=n.id, msg="edited since last approval"))
        if n.parent and was.get("parent_hash") != tree[n.parent].hash:
            report["tree"].append(dict(kind="parent-changed", node=n.id,
                                       msg=f"parent [{n.parent}] changed; re-check that this step still fits it"))
    vocab = load_vocabulary(cfg, root)
    vlock = lock.get("@vocabulary", {})
    users: dict[str, list[str]] = {}
    for n in tree.values():
        for u in n.uses:
            users.setdefault(u, []).append(n.id)
            if vocab is None:
                report["tree"].append(dict(kind="no-vocabulary", node=n.id,
                                           msg=f"uses '{u}', but the project has no vocabulary file"))
            elif u not in vocab:
                report["tree"].append(dict(kind="unknown-capability", node=n.id,
                                           msg=f"uses '{u}', which the vocabulary does not define"))
    if vocab:
        for name, c in vocab.items():
            was = vlock.get(name)
            if was and was.get("contract") != c.contract_hash() and name in users:
                report["tree"].append(dict(kind="capability-changed", node=",".join(users[name]),
                                           msg=f"capability '{name}' changed its in:/out: since approval; re-check steps {', '.join(users[name])}"))
    for n in tree.values():
        _, bad = parse_compare(n.compare)
        for clause in bad:
            report["tree"].append(dict(kind="compare-rule", node=n.id,
                                       msg=f"compare: '{clause}' is not understood (use: ignore <fields>; any order; "
                                           f"<field> in any order; numbers within <n>; any timing; final result only)"))
        was = lock.get(n.id)
        if was is not None and "compare" in was and was["compare"] != n.compare:
            report["tree"].append(dict(kind="compare-edited", node=n.id,
                                       msg="its compare: lines changed since approval (what counts as the same result)"))
        elif was is not None and "compare" not in was and n.compare:
            report["tree"].append(dict(kind="compare-edited", node=n.id,
                                       msg="compare: lines added since approval (what counts as the same result)"))
    for i, msg in getattr(tree, "warnings", []):
        report["tree"].append(dict(kind="format", node=f"line {i}", msg=msg))
    # Schema references: [[Entity.Property]] and reads:/writes: against the project's schemas.
    report["warnings"] = []
    import ladder_schema as S
    if cfg.get("schemas") or any(n.reads or n.writes or "[[" in n.own_text() for n in tree.values()):
        schemas = S.load_schemas(cfg, root)
        sproblems, sfacts, swarn = S.check_refs(tree, schemas)
        report["tree"] += sproblems
        report["warnings"] += swarn
        if schema_since:
            # Compare with the schema as it was at a git ref, without needing a stamp.
            _, was_all, _ = S.check_refs(tree, S.load_schemas_at(cfg, root, schema_since))
            since = f"since {schema_since}"
        else:
            was_all, since = lock.get("@schema", {}), "since approval"
        writers_seen: set = set()
        known = S.attrs_known(was_all)     # attributes the old facts never carry are not compared
        for nid, now in sfacts.items():
            was = was_all.get(nid, {})
            named, table = [], []
            for k, v in now.items():
                if k in was:
                    for c in S.fact_changes(k, was[k], v, known):
                        (table if ".*" in k else named).append(c)
            named = list(dict.fromkeys(named))
            # a change seen both by name and through the whole table is reported once
            table = [c for c in dict.fromkeys(table) if c not in named]
            if named or any("inserts must now set it" in c for c in table):
                changed = named + table
            else:
                changed = []
                if table:
                    report["warnings"].append(dict(
                        kind="schema-changed-table", node=nid,
                        msg=f"refers to a whole table (reads:/writes:) in which something changed {since} ("
                            + "; ".join(table) + "); it names none of those columns, so this is only a warning. If "
                                                 "the step does use one, name it with [[Entity.Member]] so changes to it "
                                                 "are reviewed"))
            for c in changed:
                if "inserts must now set it" in c:
                    ent_key = c.split(" added", 1)[0].rsplit(".", 1)[0]          # qbs:Dbo_Timeclock
                    sname, _, ename = ent_key.partition(":")
                    e = schemas.get(sname, {}).get(ename)
                    if e is not None and ent_key not in writers_seen:
                        writers_seen.add(ent_key)
                        found = S.other_writers(root, cfg, e)
                        if found:
                            shown = found[:10]
                            more = ""
                            if len(found) > 10:
                                listing = root / ".ladder" / f"other-writers-{ename}.txt"
                                listing.parent.mkdir(exist_ok=True)
                                listing.write_text("\n".join(found) + "\n")
                                more = f", and {len(found) - 10} more (all {len(found)} in {listing.relative_to(root)})"
                            report["warnings"].append(dict(
                                kind="other-writers", node=ename,
                                msg=f"{len(found)} places outside this project create {ename} rows and must set the new "
                                    f"required column too (tests and seeders included): {', '.join(shown)}{more}"))
            if changed:
                report["tree"].append(dict(kind="schema-changed", node=nid,
                                           msg=f"the schema it refers to changed {since} (" + "; ".join(changed)
                                               + "); re-read the step, then regenerate its code with --redo"))
        if schema_since:
            report["schema_since"] = schema_since
    # Links to steps in other trees (calls:), and tests of claims that reading cannot check.
    import ladder_links as K
    lproblems, lapprovals, lwarn, _ = K.check_links(tree, cfg, root, lock, links_since)
    report["tree"] += lproblems + lapprovals
    report["warnings"] += lwarn
    tproblems, twarn = K.check_tests(cfg, root, tree, load_code(root))
    report["tree"] += tproblems
    report["warnings"] += twarn
    if "@data" in lock:
        now = data_texts(tree)
        was_d = lock["@data"]
        for name in now:
            if name not in was_d:
                report["tree"].append(dict(kind="data-new", node=name, msg="added since last approval; any @contract region is now stale"))
            elif was_d[name] != now[name]:
                report["tree"].append(dict(kind="data-edited", node=name, msg="edited since last approval; any @contract region is now stale, and steps that use it may need --redo"))
        # A step's code follows the rules it cites, but a rule's text is not in the step's hash: name the steps
        # (round 11: a limit changed in a rule reached no code until --redo named them).
        for rule in changed_rules(tree, lock):
            citers = rule_citers(tree, rule)
            if citers:
                report["tree"].append(dict(
                    kind="rule-changed", node=",".join(citers),
                    msg=f"cite rule {rule}, which changed since approval: `ladder regen` rewrites them (or --redo="
                        f"{','.join(citers)}); read their code against the new rule before approving"))
        for name in was_d:
            if name not in now:
                report["tree"].append(dict(kind="data-removed", node=name, msg="removed since last approval"))
    for nid in lock:
        if nid.startswith("@"):
            continue
        if nid not in tree:
            report["tree"].append(dict(kind="removed", node=nid, msg="step removed since last approval"))

    for b in cfg["builds"]:
        br = dict(name=b["name"], lang=b["lang"], mode=b.get("mode", ""), problems=[], coverage={},
                  scope=b.get("steps"))
        covered: dict[str, list[str]] = {nid: [] for nid in tree}
        if b.get("tagged") is False:
            # compared by behavior only (an outside implementation, or a build not under Ladder)
            br["untagged_build"] = True
            report["builds"].append(br)
            continue
        has_contract = False
        for f in b["files"]:
            fpath = root / f
            if not fpath.exists():
                br["problems"].append(dict(kind="missing-file", file=f, line=0,
                                           msg="file not found (generate it with `ladder generate`, or fix the path in ladder.json)"))
                continue
            regions, _, flines, probs = parse_regions(fpath, b["lang"])
            br["problems"] += group_untagged(probs)
            for r in regions:
                if r.kind == "contract":
                    h = r.tags[0][1] if r.tags else ""
                    has_contract = True
                    own = region_own_code(regions, flines, regions.index(r))
                    if not contract_region_ok(tree, b, h, own, r.label):
                        br["problems"].append(dict(kind="stale-contract", file=f, line=r.start,
                                                   msg=f"contract types were generated from older in:/out: lines or data blocks (tag {h}, now {region_contract_hash(tree, b, own, r.label)}); regenerate this region"))
                    # A region whose label names data blocks must declare those, and no block another region's label
                    # names: blind generation once wrote three DTOs into one file and repair then emptied the right one.
                    named = label_blocks(tree, b, r.label)
                    if named:
                        declared = declared_blocks(tree, b, own)
                        elsewhere = {blk: (ff, lab) for ff, lab, blks in contract_layout(root, b, tree)
                                     if (ff, lab) != (f, r.label) for blk in blks}
                        # (the type's own name may differ from the block's: the label is what ties them)
                        lacking = named if not any(CONTRACT_DECL_RE.search(l) for l in own) else []
                        foreign = sorted(d for d in declared if d in elsewhere and d not in named)
                        if lacking or foreign:
                            parts = ([f"declares no type (for {', '.join(lacking)})"] if lacking else []) + \
                                    [f"declares {d}, which belongs to the region '{elsewhere[d][1]}' in {elsewhere[d][0]}" for d in foreign]
                            br["problems"].append(dict(
                                kind="contract-misplaced", file=f, line=r.start,
                                msg=f"contract region '{r.label}' {'; '.join(parts)}; each labelled region holds the "
                                    f"types its label names: regenerate this build's contract regions"))
                    continue
                if r.kind != "node":
                    continue
                theirs = foreign_ids(root, b)
                for nid, h in r.tags:
                    if nid not in tree and nid in theirs:
                        continue          # another project's region in a shared file ("shared_with")
                    if nid not in tree:
                        br["problems"].append(dict(kind="unknown-step", file=f, line=r.start,
                                                   msg=f"tag refers to [{nid}], which is not in the tree"
                                                       + ("" if b.get("shared_with") else "; if another project tags "
                                                          "this file, name it in the build's \"shared_with\"")))
                        continue
                    covered[nid].append(f"{f}:{r.start}")
                    if h != tree[nid].hash:
                        br["problems"].append(dict(kind="stale", file=f, line=r.start, node=nid,
                                                   msg=f"generated from an older [{nid}] (tag {h}, tree now {tree[nid].hash}); regenerate this region, "
                                                       f"or, if the English was only reworded, `ladder retag <ladder.json> {nid}`"))
                if r.code_lines == 0 and not any(
                        rr.parent == regions.index(r) for rr in regions):
                    br["problems"].append(dict(kind="empty", file=f, line=r.start,
                                               msg=f"region '{r.label}' contains no code"))

        br["has_contract"] = has_contract
        if b.get("data") and not has_contract:
            br["problems"].append(dict(kind="missing-contract", node="data",
                                       msg=f"no @contract region spells out the data blocks this build lists "
                                           f"({', '.join(build_data(tree, b)) or 'none match'})"))
        for f, added, removed in export_changes(root, b):
            parts = ([f"adds {', '.join(added)}"] if added else []) + ([f"removes {', '.join(removed)}"] if removed else [])
            br["problems"].append(dict(
                kind="exports-changed", file=f, line=1,
                msg=f"the file's exports changed since approval (before the first stamp: since the git baseline): "
                    f"{'; '.join(parts)}. Generated code must not add or drop "
                    f"public names the English doesn't ask for; if the English does, `ladder accept --exports` (or stamp)"))
            for cf in b.get("consumers", []):
                text = (root / cf).read_text() if (root / cf).exists() else ""
                for name in added:
                    if name != "default" and not name.startswith("* from") and not re.search(rf"\b{re.escape(name)}\b", text):
                        br["problems"].append(dict(
                            kind="consumer-missing", file=cf, line=1,
                            msg=f"new export {name} of {f} is not mentioned in {cf}, which re-exports this build "
                                f"(listed in \"consumers\"); add it there if callers should see it"))
        adopted = b.get("adopted", False)
        for f, key, line in hand_edited(root, b):
            what = key.split(" ", 1)[1].split(" #")[0] if key.startswith("node ") else key
            br["problems"].append(dict(
                kind="hand-edited", file=f, line=line, node=what,
                msg=(f"code for [{what}] changed since it was last approved or generated; if behavior changed, update the "
                     f"English (ladder-write), then `ladder accept`; if not (refactor, formatting), just `ladder accept`; "
                     f"if it was regenerated in a scratch copy and copied here, `ladder accept --from=<scratch ladder.json>`")
                if adopted else
                (f"code for [{what}] was edited by hand since it was last generated or approved; regenerating would throw the edit away. "
                 f"Move the change into the English and regenerate, or `ladder accept` it if it changes no behavior; "
                 f"if it was regenerated in a scratch copy and copied here, `ladder accept --from=<scratch ladder.json>`")))

        def is_covered(nid: str) -> bool:
            if covered[nid]:
                return True
            n = tree[nid]
            return bool(n.children) and all(is_covered(c) for c in n.children)

        if vocab:
            for name, ids in users.items():
                c = vocab.get(name)
                ids = [i for i in ids if build_in_scope(b, i)]
                if not c or not ids:
                    continue
                bind = c.binding_for(b)
                if bind is None:
                    br["problems"].append(dict(kind="unbound-capability", node=ids[0],
                                               msg=f"capability '{name}' (used by {', '.join(ids)}) has no binding for {b['name']} / {b['lang']}"))
                    continue
                # Only for code in this repository whose files resolve: a published library's binding is checked by
                # its version and tests, and a binding naming a folder says too little to look for.
                names = binding_call_names(bind[1]) if binding_files(bind[1], project_bases(cfg, root)) else set()
                def calls(build: dict) -> bool:
                    text = "\n".join((root / f).read_text() for f in build["files"] if (root / f).exists())
                    return any(uses_name(text, n) for n in names)
                # A step can rely on a capability another build of the project calls (a controller relies on the error
                # answer its service throws into): that build's call counts.
                others = [ob for ob in cfg["builds"] if ob is not b and ob.get("tagged") is not False
                          and c.binding_for(ob) == bind]
                if names and b.get("tagged") is not False and not calls(b) and not any(calls(ob) for ob in others):
                    if True:
                        report["warnings"].append(dict(
                            kind="binding-not-called", node=ids[0],
                            msg=f"capability '{name}' (used by {', '.join(ids)}): no file of build '{b['name']}' calls "
                                f"{', '.join(sorted(names))}, the calls its binding names, and no other build of this "
                                f"project does. If these steps rely on it without calling it, drop it from their uses:; "
                                f"otherwise the code may call an API that does not exist or another library: regenerate "
                                f"those steps"))
                was = vlock.get(name, {}).get("bindings", {}).get(bind[0])
                if was and was != c.binding_hash(bind[0]):
                    br["problems"].append(dict(kind="binding-changed", node=ids[0],
                                               msg=f"binding '{bind[0]}' of '{name}' changed since approval: if the code must "
                                                   f"change, regenerate with --redo={','.join(ids)}; if the approved code "
                                                   f"still fits the new binding (another area added a call or a claim to "
                                                   f"a shared capability), read it against the binding and `ladder stamp`"))

        scope = b.get("steps")   # optional: glob patterns of step ids this build implements

        def in_scope(nid: str) -> bool:
            return build_in_scope(b, nid)

        for nid, n in tree.items():
            br["coverage"][nid] = covered[nid]
            if n.is_leaf and in_scope(nid) and not is_covered(nid):
                br["problems"].append(dict(kind="missing", node=nid,
                                           msg=f"no code is tagged with [{nid}]"))
            if n.is_leaf and len(covered[nid]) > 1 and b.get("tagged") is not False:
                # Regeneration writes each region from the whole step, so a step split over two regions is written
                # twice (round 10: a helper tagged as a second region of its caller's step became a duplicate method).
                report["warnings"].append(dict(
                    kind="split-step", node=nid,
                    msg=f"[{nid}]'s code is in {len(covered[nid])} regions of build '{b['name']}' "
                        f"({', '.join(covered[nid])}): regeneration writes each region from the whole step, so the "
                        f"code would be written twice. Give the separate part its own step (a helper the English "
                        f"names), or tag it as @support if no step owns it"))
        report["builds"].append(br)
    report["warnings"] += rule_in_support_warnings(root, cfg, tree, lock)
    report["compare"] = compare_runs(root, cfg, tree)
    report["warnings"] += replay_settings_warnings(root, cfg)
    report["warnings"] += unused_trace_warnings(root, cfg)
    # Mutants (builds with "mutant": true) are broken on purpose: they must differ somewhere.
    mutants = {b["name"] for b in cfg["builds"] if b.get("mutant")}
    report["mutants"] = {}
    for m in sorted(mutants):
        caught = sum(1 for run in report["compare"] for b in run["builds"]
                     if b["build"] == m and not b["missing"] and not b["ok"])
        report["mutants"][m] = caught
        first = next(((run["run"], r) for run in report["compare"] for bb in run["builds"]
                      if bb["build"] == m and not bb["missing"] for r in bb["rows"] if r["status"] == "different"), None)
        if first:
            report.setdefault("mutant_first", {})[m] = dict(run=first[0], step=first[1]["step"],
                                                           ref=first[1]["ref"], val=first[1]["val"])
        for run in report["compare"]:
            for b in run["builds"]:
                if b["build"] == m:
                    b["ok"] = True
    if mutants and not report["compare"]:
        report["mutants"] = {m: 0 for m in mutants}
    unknown = sorted({st for run in report["compare"] for st in run.get("unknown_steps", [])})
    if unknown:
        report["tree"].append(dict(kind="trace-steps", node=", ".join(unknown[:8]),
                                   msg="traces name steps that are not in the tree (a typo?); list harness-only "
                                       "names in compare.extra_steps"))
    approval_kinds = {"new", "baseline-new", "edited", "rule-changed", "parent-changed", "removed", "capability-changed",
                      "data-new", "data-edited", "data-removed", "compare-edited", "schema-changed",
                      "linked-changed"}
    real_tree = [p for p in report["tree"] if p["kind"] not in approval_kinds]
    real = (real_tree or any(b["problems"] for b in report["builds"])
            or any(v == 0 for v in report.get("mutants", {}).values())
            or not all(b["ok"] for run in report["compare"] for b in run["builds"])
            or any(run.get("missing_reference") for run in report["compare"]))
    report["status"] = "problems" if real else ("awaiting-approval" if report["tree"] else "ok")
    report["compared"] = bool(report["compare"])
    # Runs are configured but no build has its own traces to set against the reference's (every tagged build
    # shares them): nothing was compared, so the result must not say the comparison is fine.
    report["nothing_compared"] = bool(report["compare"]) and not any(run["builds"] for run in report["compare"])
    if report["nothing_compared"]:
        report["compared"] = False
    report["ok"] = report["status"] == "ok"
    return report


NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")

# ---------------------------------------------------------------- compare: lines
# A step's `compare:` lines say which differences between builds do not matter for that step.
# They change verification only, never code, so they are not in the step hash; they are in the
# lock, because loosening a comparison is a decision a person approves.

COMPARE_CLAUSES = [
    (re.compile(r"^ignore\s+(.+)$", re.I), "ignore"),                       # ignore id, createdUtc
    (re.compile(r"^any order$", re.I), "any-order"),                         # this step's results, as a set
    (re.compile(r"^(.+?)\s+in any order$", re.I), "list-any-order"),         # `items` in any order
    (re.compile(r"^numbers within\s+([0-9.]+)$", re.I), "numbers"),         # numbers within 0.01
    (re.compile(r"^any timing$", re.I), "any-timing"),                       # vs other steps' results
    (re.compile(r"^final result only$", re.I), "final-only"),                # only the last result
]


def parse_compare(lines: list[str]) -> tuple[dict, list[str]]:
    """Rules from a step's compare: clauses, plus the clauses that were not understood."""
    rules: dict = {"ignore": set(), "lists": set(), "any_order": False, "tolerance": None,
                   "any_timing": False, "final_only": False}
    bad = []
    names = lambda t: {x.strip().strip("`") for x in re.split(r",|\band\b", t) if x.strip()}
    for clause in lines:
        c = " ".join(clause.split())
        for rx, kind in COMPARE_CLAUSES:
            m = rx.match(c)
            if not m:
                continue
            if kind == "ignore":
                rules["ignore"] |= names(m.group(1))
            elif kind == "list-any-order":
                rules["lists"] |= names(m.group(1))
            elif kind == "any-order":
                rules["any_order"] = True
            elif kind == "numbers":
                rules["tolerance"] = float(m.group(1))
            elif kind == "any-timing":
                rules["any_timing"] = True
            elif kind == "final-only":
                rules["final_only"] = True
            break
        else:
            bad.append(clause)
    return rules, bad


def apply_compare(value: str, rules: dict) -> str:
    """Rewrite one result so differences the step's compare: lines allow disappear."""
    if not rules or (not rules["ignore"] and not rules["lists"]):
        return value
    try:
        v = json.loads(value)
    except (ValueError, TypeError):
        return value

    def walk(x):
        if isinstance(x, dict):
            out = {}
            for k, val in x.items():
                if k in rules["ignore"]:
                    out[k] = "<ignored>"
                    continue
                val = walk(val)
                if k in rules["lists"] and isinstance(val, list):
                    val = sorted(val, key=lambda e: json.dumps(e, sort_keys=True))
                out[k] = val
            return out
        if isinstance(x, list):
            return [walk(e) for e in x]
        return x
    return json.dumps(walk(v), sort_keys=True, separators=(",", ":"))


def match_info(ref: str, val: str, tol: float) -> tuple[str, float]:
    """'same' if identical; 'close' if only numbers differ and each by at most tol;
    otherwise 'different'. Returns (status, largest numeric difference)."""
    if ref == val:
        return "same", 0.0
    if NUM_RE.sub("#", ref) != NUM_RE.sub("#", val):
        return "different", float("inf")
    diffs = [abs(float(x) - float(y)) for x, y in zip(NUM_RE.findall(ref), NUM_RE.findall(val))]
    worst = max(diffs, default=0.0)
    return ("close" if worst <= tol else "different"), worst


def trace_exits(path: Path, order: list[str] | None = None,
                labels: dict[str, list[str]] | None = None) -> dict[str, list[str]]:
    """Each step's results in order. If `order` is given, it receives the step of every result,
    in the order the results happened (for the strict order check). If `labels` is given, it
    receives, per step, where each result sits in the run ("#15 POST /login") for reports."""
    out: dict[str, list[str]] = {}
    entered: dict[str, str] = {}
    n = 0
    for l in path.read_text().splitlines():
        if not l.strip():
            continue
        e = json.loads(l)
        if e["ev"] == "enter":
            entered[e["step"]] = e.get("info", "")
        if e["ev"] == "exit":
            n += 1
            if labels is not None:
                labels.setdefault(e["step"].split("+")[-1], []).append(
                    f"#{n}" + (f" {entered.get(e['step'])}" if entered.get(e["step"]) else ""))
            # A fused span ("qr.1.1+qr.1.2") ends where its last step ends,
            # so its output is comparable with that step's output.
            # Builds that record the full value ("data") are compared on it; otherwise the summary.
            step = e["step"].split("+")[-1]
            out.setdefault(step, []).append(e["data"] if "data" in e else e.get("info", ""))
            if order is not None:
                order.append(step)
    return out


def recorded_mask_text(folder: Path) -> list[tuple[str, str]]:
    """The --mask-text patterns a trace folder was recorded with (its .replay.json), as (pattern, replacement)."""
    try:
        meta = json.loads((folder / ".replay.json").read_text())
    except (OSError, ValueError):
        return []
    out = []
    for item in meta.get("mask_text", []):
        pat, sep, rep_ = item.rpartition("=")
        if sep and pat:
            out.append((pat, rep_))
    return out


def apply_mask_text(value: str, patterns: list[tuple[str, str]]) -> str:
    for pat, rep_ in patterns:
        try:
            value = re.sub(pat, rep_, value)
        except re.error:
            pass
    return value


def run_names(root: Path, c: dict, cfg: dict | None = None) -> list[str]:
    """compare.runs, with "*" meaning every trace the reference build has."""
    ref_b = next((x for x in (cfg or {}).get("builds", []) if x["name"] == c["reference"]), {})
    folder = ref_b.get("traces", c["reference"])
    runs = []
    for r in c.get("runs", []):
        if "*" in r:
            runs += sorted(p.stem for p in (root / "traces" / folder).glob(f"{r}.jsonl"))
        else:
            runs.append(r)
    return runs


def unused_trace_warnings(root: Path, cfg: dict) -> list[dict]:
    """Folders under traces/ holding recordings (*.jsonl) that no build's traces name: check never reads them,
    so a recording made there (a second run, a regenerated build) is silently not compared."""
    tdir = root / "traces"
    if not cfg.get("compare") or not tdir.is_dir():
        return []
    named = {b.get("traces", b["name"]) for b in cfg.get("builds", [])}
    out = []
    for d in sorted(p for p in tdir.iterdir() if p.is_dir()):
        if d.name not in named and any(d.glob("*.jsonl")):
            out.append(dict(kind="traces-unused", node=f"traces/{d.name}",
                            msg="recordings no build names, so they are never compared; add a build "
                                f"{{\"name\": \"{d.name}\", \"tagged\": false, ...}} to compare them, or move them out of traces/"))
    return out


def replay_settings_warnings(root: Path, cfg: dict) -> list[dict]:
    """Traces that `ladder replay` recorded with different settings (masks, --jwt, --observe) or a
    different Ladder version than the reference's: their differences may come from the recording."""
    c = cfg.get("compare") or {}
    ref = c.get("reference")
    if not ref:
        return []
    folder = {b["name"]: b.get("traces", b["name"]) for b in cfg.get("builds", [])}

    def meta(name):
        p = root / "traces" / folder.get(name, name) / ".replay.json"
        try:
            return json.loads(p.read_text())
        except (OSError, ValueError):
            return None
    want = meta(ref)
    out = []
    for b in cfg.get("builds", []):
        if b["name"] == ref or folder.get(b["name"]) == folder.get(ref):
            continue
        got = meta(b["name"])
        if want is None and got is None:
            continue
        if want is None or got is None:
            which = ref if want is None else b["name"]
            out.append(dict(kind="replay-settings", node=b["name"],
                            msg=f"traces/{folder.get(which, which)} have no .replay.json (recorded by a Ladder older than "
                                f"0.6.1, or not by replay) while the other side has one; if they differ, re-record with "
                                f"the same settings before trusting the comparison"))
            continue
        diffs = [f"{k}: {want.get(k)} vs {got.get(k)}" for k in sorted(set(want) | set(got))
                 if k not in ("recorded", "mask_text") and want.get(k) != got.get(k)]   # mask_text: applied to both at compare
        if diffs:
            out.append(dict(kind="replay-settings", node=b["name"],
                            msg=f"recorded with different replay settings than {ref} (" + "; ".join(diffs)
                                + "); differences may come from the recording, not the code"))
    return out


def compare_runs(root: Path, cfg: dict, tree: dict | None = None) -> list[dict]:
    """Differential check across builds. Every build ran on the same inputs; at each step
    boundary that exists in both a build and the reference build, compare what the step
    handed back. traces/<build>/<run>.jsonl holds each run. Each step's `compare:` lines
    (ignore fields, any order, numbers within, any timing, final result only) loosen its
    comparison. With "order": "strict", the order of results across steps must match too,
    except for steps marked `any timing`."""
    c = cfg.get("compare")
    if not c:
        return []
    ref, tol = c["reference"], float(c.get("number_tolerance", 0))
    strict = c.get("order") == "strict"
    rules = {nid: parse_compare(n.compare)[0] for nid, n in (tree or {}).items() if n.compare}
    out = []
    for run in run_names(root, c, cfg):
        ref_b = next((x for x in cfg["builds"] if x["name"] == ref), {})
        ref_path = root / "traces" / ref_b.get("traces", ref) / f"{run}.jsonl"
        entry = dict(run=run, reference=ref, tolerance=tol, builds=[])
        ref_order: list[str] = []
        ref_labels: dict[str, list[str]] = {}
        ref_ex = trace_exits(ref_path, ref_order, ref_labels) if ref_path.exists() else {}
        # Text masks either recording was made with apply to both sides now, so adding a pattern to the harness
        # does not mean re-recording every older run (round 9: an incident number inside a message).
        ref_patterns = recorded_mask_text(ref_path.parent)
        entry["missing_reference"] = not ref_path.exists()
        if tree:
            allowed = set(c.get("extra_steps", [])) | {"http"}
            entry["unknown_steps"] = sorted(st for st in ref_ex if st not in tree and st not in allowed)
        for b in cfg["builds"]:
            if b["name"] == ref:
                continue
            if b.get("traces") and b.get("traces") == ref_b.get("traces", ref):
                continue   # shares the reference's traces (one harness for several per-file builds)
            path = root / "traces" / b.get("traces", b["name"]) / f"{run}.jsonl"
            if not path.exists() or not ref_ex:
                entry["builds"].append(dict(build=b["name"], ok=False, missing=True, rows=[],
                                            not_comparable=[]))
                continue
            order: list[str] = []
            ex = trace_exits(path, order)
            pats = ref_patterns + [p for p in recorded_mask_text(path.parent) if p not in ref_patterns]
            if pats:
                ref_ex_b = {st: [apply_mask_text(v, pats) for v in vs] for st, vs in ref_ex.items()}
                ex = {st: [apply_mask_text(v, pats) for v in vs] for st, vs in ex.items()}
            else:
                ref_ex_b = ref_ex
            rows = []
            for step in ref_ex_b:
                if step not in ex:
                    continue
                note = ""
                rl = rules.get(step)
                step_tol = rl["tolerance"] if rl and rl["tolerance"] is not None else tol
                if rl and rl["final_only"]:
                    pairs = [(ref_ex_b[step][-1], ex[step][-1])]
                    note = "compared the final result only (compare: final result only)"
                elif rl and rl["any_order"]:
                    rs = sorted(apply_compare(v, rl) for v in ref_ex_b[step])
                    vs = sorted(apply_compare(v, rl) for v in ex[step])
                    if len(rs) != len(vs):
                        note = f"{len(vs)} results here, {len(rs)} in {ref}"
                    pairs = list(zip(rs, vs)) if len(rs) == len(vs) else [("\n".join(rs), "\n".join(vs))]
                elif len(ref_ex_b[step]) != len(ex[step]):
                    # e.g. an optimized build opens one span per retry where the literal build
                    # opens one for the whole step: compare what the step finally handed back.
                    note = f"{len(ex[step])} spans here, {len(ref_ex_b[step])} in {ref}; compared final values"
                    pairs = [(ref_ex_b[step][-1], ex[step][-1])]
                else:
                    pairs = list(zip(ref_ex_b[step], ex[step]))
                if rl:
                    pairs = [(apply_compare(r, rl), apply_compare(v, rl)) for r, v in pairs]
                results = [match_info(r, v, step_tol) for r, v in pairs]
                status = ("different" if any(r[0] == "different" for r in results)
                          else "close" if any(r[0] == "close" for r in results) else "same")
                worst = max(r[1] for r in results)
                # Show the first result that is not the same (the one to investigate), with its position.
                at = next((i for i, r in enumerate(results) if r[0] != "same"), len(results) - 1)
                lab = ref_labels.get(step, []) if len(pairs) == len(ref_labels.get(step, [])) and not (rl and rl["any_order"]) else []
                diffs = [dict(at=i + 1, ref=pairs[i][0], val=pairs[i][1], status=r[0], label=lab[i] if lab else "")
                         for i, r in enumerate(results) if r[0] != "same"]
                rows.append(dict(step=step, ref=pairs[at][0], val=pairs[at][1], status=status, at=at + 1,
                                 count=len(pairs), same=sum(r[0] == "same" for r in results),
                                 worst=None if worst == float("inf") else worst, note=note, diffs=diffs))
            if strict:
                free = {nid for nid, rl in rules.items() if rl["any_timing"]}
                final = {nid for nid, rl in rules.items() if rl["final_only"]}

                def seq(o: list[str], other: dict) -> list[str]:
                    # steps compared on their final result only keep just their last position
                    last = {st: i for i, st in enumerate(o)}
                    return [st for i, st in enumerate(o) if st not in free and st in other
                            and (st not in final or last[st] == i)]
                a, bseq = seq(ref_order, ex), seq(order, ref_ex_b)
                if a != bseq:
                    i = next((k for k in range(min(len(a), len(bseq))) if a[k] != bseq[k]), min(len(a), len(bseq)))
                    show = lambda seq: " ".join(seq[max(0, i - 2): i + 3]) or "(end)"
                    rows.append(dict(step="(order)", status="different", at=i + 1, count=len(a), same=i,
                                     ref=f"... {show(a)} ...", val=f"... {show(bseq)} ...", worst=None,
                                     note=f"results came in a different order from result {i + 1}; if the step "
                                          f"there may answer earlier or later, mark it `compare: any timing`"))
            entry["builds"].append(dict(
                build=b["name"], missing=False, rows=rows,
                not_comparable=sorted(set(ref_ex_b) ^ set(ex)),
                ok=all(r["status"] != "different" for r in rows)))
        out.append(entry)
    return out


def clip_pair(a: str, b: str, width: int = 200) -> tuple[str, str]:
    """Two long values cut to the same window around where they first differ, so the difference
    is always on screen (not hidden past the first 200 characters)."""
    if len(a) <= width and len(b) <= width:
        return a, b
    i = next((k for k in range(min(len(a), len(b))) if a[k] != b[k]), min(len(a), len(b)))
    start = max(0, i - width // 3)

    def cut(x: str) -> str:
        return ("…" if start > 0 else "") + x[start:start + width] + ("…" if start + width < len(x) else "")
    return cut(a), cut(b)


SHOW_ALL = False    # --all-differences: list every differing result, not the first DIFF_LIMIT per step
DIFF_LIMIT = 10


def print_report(rep: dict, tree: dict[str, Node]) -> None:
    def where(p):
        return f"{p['file']}:{p['line']}  " if "file" in p else ""
    base = rep.get("baseline")
    print("Tree" + (f" (compared with {base}, not with the last approval)" if base else ""))
    if not rep["tree"]:
        print("  ok: " + (f"no changes since {base}" if base else "matches the last approved version"))
    for p in rep["tree"]:
        msg = p["msg"]
        if base:
            msg = msg.replace("since last approval", f"since {base}").replace("since approval", f"since {base}")
        print(f"  {p['kind']:<15} [{p['node']}] {msg}")
    for b in rep["builds"]:
        scope = b.get("scope")
        leaves = [n for n in tree.values() if n.is_leaf
                  and (scope is None or any(fnmatch.fnmatchcase(n.id, pat) for pat in scope))]
        direct = sum(1 for n in leaves if b["coverage"].get(n.id))
        print(f"\nBuild '{b['name']}' ({b['lang']}{', ' + b['mode'] if b['mode'] else ''})")
        if b.get("untagged_build"):
            print("  compared by behavior only (\"tagged\": false): no tag or coverage checks")
            continue
        if scope == [] and b.get("has_contract"):
            print("  contract only (\"steps\": []): its @contract regions spell out data blocks; implements no steps")
        elif scope == []:
            print("  support only (\"steps\": []): checks tags, hand edits and exports; implements no steps")
        else:
            print(f"  {direct}/{len(leaves)} leaf steps {'in its scope ' if scope else ''}tagged directly")
        if not b["problems"]:
            print("  ok: every line of code is tagged, every step is covered, nothing is stale")
        for p in b["problems"]:
            print(f"  {p['kind']:<15} {where(p)}{p['msg']}")
    mutant_names = set(rep.get("mutants", {}))
    runs = [dict(r, builds=[b for b in r["builds"] if b["build"] not in mutant_names]) for r in rep.get("compare", [])]
    clean = [r for r in runs if not r.get("missing_reference") and all(
        not b["missing"] and all(x["status"] == "same" for x in b["rows"]) for b in r["builds"])]
    if len(runs) > 10:
        # Many runs (differential testing): summarize the identical ones, show the rest.
        if clean:
            print(f"\nSame input, {len(runs)} runs: {len(clean)} identical in every build "
                  f"({', '.join(b['build'] for b in clean[0]['builds'])} vs {clean[0]['reference']})")
        per_build: dict[str, int] = {}
        for r in runs:
            for b in r["builds"]:
                if b["missing"] or any(x["status"] == "different" for x in b["rows"]):
                    per_build[b["build"]] = per_build.get(b["build"], 0) + 1
        all_builds = [b["build"] for b in runs[0]["builds"]] if runs else []
        for name in all_builds:
            k = per_build.get(name, 0)
            print(f"  {name:<20} " + (f"identical in all {len(runs)} runs" if not k
                                      else f"differs in {k} of {len(runs)} runs (first ones below)"))
        shown = 0
        rest = []
        for r in runs:
            if r in clean:
                continue
            shown += 1
            if shown <= 5:
                rest.append(r)
        runs = rest
    compact = len(rep.get("compare", [])) > 10
    for run in runs:
        print(f"\nSame input '{run['run']}': each build vs {run['reference']}"
              f" (numbers may differ by up to {run['tolerance']:g})")
        if run.get("missing_reference"):
            print(f"  no reference trace: traces/{run['reference']}/{run['run']}.jsonl (record it first)")
            continue
        for b in run["builds"]:
            if b["missing"]:
                print(f"  {b['build']:<20} no trace for this run")
                continue
            if compact and all(r["status"] == "same" for r in b["rows"]):
                continue
            steps_rows = [r for r in b["rows"] if r["step"] != "(order)"]
            total = sum(r.get("count", 1) for r in steps_rows)
            same_results = sum(r.get("same", r.get("count", 1) if r["status"] == "same" else 0) for r in steps_rows)
            print(f"  {b['build']:<20} {same_results}/{total} results identical across {len(steps_rows)} steps")
            for r in b["rows"]:
                if r["status"] == "same":
                    continue
                where_ = f"result {r.get('at', '?')} of {r.get('count', '?')}"
                if r["step"] == "(order)":
                    print(f"    order of results: DIFFERENT from result {r['at']} (of {r['count']} in sequence)")
                    va, ra = clip_pair(r['val'], r['ref'])
                    print(f"      {b['build']}: {va}")
                    print(f"      {run['reference']}: {ra}")
                    print(f"      ({r['note']})")
                    continue
                if r["status"] == "close":
                    print(f"    {r['step']}: close ({where_}, off by {r['worst']:g}): {r['val'][:160]}")
                else:
                    diffs = [d for d in r.get("diffs") or [dict(at=r["at"], ref=r["ref"], val=r["val"])]
                             if d.get("status", "different") == "different"]
                    shown_d = diffs if SHOW_ALL else diffs[:DIFF_LIMIT]
                    print(f"    {r['step']}: DIFFERENT in {len(diffs)} of {r.get('count', '?')} results")
                    for d in shown_d:
                        print(f"      result {d['at']}" + (f" (request {d['label']})" if d.get("label") else "") + ":")
                        va, ra = clip_pair(d['val'], d['ref'])
                        print(f"        {b['build']}: {va}")
                        print(f"        {run['reference']}: {ra}")
                    if len(diffs) > len(shown_d):
                        print(f"      ... {len(diffs) - len(shown_d)} more (ladder check --all-differences)")
                if r.get("note"):
                    print(f"      ({r['note']})")
    if any(not b["ok"] and not b["missing"] for run in rep.get("compare", []) for b in run["builds"]):
        print("\n  If a difference is an approved change of behaviour, make the run recorded from the approved code the "
              "reference: `ladder reference <ladder.json> --from=<build>` (the old reference moves to traces/history/).")
    if rep.get("mutants"):
        total = len(rep.get("compare", []))
        print("\nMutants (broken on purpose; each must differ somewhere)")
        for m, caught in rep["mutants"].items():
            print(f"  {m:<20} " + (f"caught: differs in {caught} of {total} runs" if caught
                                   else f"NOT CAUGHT in {total} runs: the runs never reach this code, or the change "
                                        f"cannot be observed (then drop the mutant)"))
            d = rep.get("mutant_first", {}).get(m)
            if d:
                print(f"    first difference: run '{d['run']}', {d['step']}")
                va, ra = clip_pair(d['val'], d['ref'], 160)
                print(f"      {m}: {va}")
                print(f"      reference: {ra}")
    if rep.get("warnings"):
        print("\nWarnings (not failures)")
        for w in rep["warnings"]:
            print(f"  {w['kind']:<15} [{w['node']}] {w['msg']}")
    status = rep.get("status", "ok" if rep["ok"] else "problems")
    print("\nRESULT:", {"ok": "ok", "problems": "problems found",
                        "awaiting-approval": "awaiting approval (code and comparison are fine; "
                                             "a person must review the English, then `ladder stamp`)"}[status]
          .replace("code and comparison are fine", "code is fine" if not rep.get("compared", True) else "code and comparison are fine"))
    if rep.get("nothing_compared"):
        print("note: nothing was compared: every build shares the reference's traces, so no other recording is "
              "set against them; add each recording to compare as a build with its own traces "
              "({\"name\": \"<folder under traces/>\", \"tagged\": false, ...})")
    elif not rep.get("compared", True):
        print("note: no comparison runs are configured (compare.runs), so behavior was not checked")


def stamp(pj: Path) -> None:
    cfg, root, tree, _, lock_path = load_project(pj)
    lock = {n.id: {"hash": n.hash, "review_hash": n.review_hash, "parent_hash": tree[n.parent].hash if n.parent else None,
                   "text": n.own_text(), "compare": n.compare}
            for n in tree.values()}
    vocab = load_vocabulary(cfg, root)
    if vocab:
        lock["@vocabulary"] = {name: {"contract": c.contract_hash(),
                                      "bindings": {k: c.binding_hash(k) for k in c.bindings}}
                               for name, c in vocab.items()}
    if data_texts(tree):
        lock["@data"] = data_texts(tree)
    import ladder_schema as S
    if cfg.get("schemas"):
        _, sfacts, _ = S.check_refs(tree, S.load_schemas(cfg, root))
        if sfacts:
            lock["@schema"] = sfacts
    import ladder_links as K
    _, _, _, lfacts = K.check_links(tree, cfg, root, {})
    if lfacts:
        lock["@links"] = lfacts
    lock_path.write_text(json.dumps(lock, indent=2) + "\n")
    print(f"approved {len(tree)} steps -> {lock_path}")
    n = record_code(root, cfg)
    record_exports(root, cfg)
    print(f"recorded the approved code of every region -> {root / CODE_FILE}" + (f" ({n} regions new or changed)" if n else ""))


# ---------------------------------------------------------------- hand edits
# ladder.code.json records a fingerprint of each @node and @contract region's own code (not its
# nested regions, comments, blank lines or spacing) as it was when a person approved it (stamp,
# accept) or the generator last wrote it (generate, regen, repair). A region whose code no longer
# matches was edited by hand: the English may no longer describe it, and regenerating it would
# throw the edit away.

CODE_FILE = "ladder.code.json"
# What the generator wrote in THIS checkout (regen, repair), apart from what was approved (CODE_FILE):
# local, never committed, so syncing a scratch copy from the working tree (git checkout) cannot
# overwrite it, and code generated there is still recognised as generated (round 8).
GEN_FILE = ".ladder/generated.json"


def local_dir(root: Path) -> Path:
    """The project's .ladder folder, which holds only local files (logs, generated.json): ignored by git."""
    d = root / ".ladder"
    d.mkdir(exist_ok=True)
    gi = d / ".gitignore"
    if not gi.exists():
        gi.write_text("# Ladder's local files: logs and what was generated in this checkout. Never commit them.\n*\n")
    return d


def load_generated(root: Path) -> dict:
    p = root / GEN_FILE
    return json.loads(p.read_text()) if p.exists() else {}


def region_keys(regions: list) -> list[str | None]:
    """A stable name for each @node/@contract region ("node api.1.2", "contract types"), by index;
    None for support regions. Hashes are left out, so a region keeps its name when regenerated."""
    seen: dict[str, int] = {}
    out: list[str | None] = []
    for r in regions:
        if r.kind == "support":
            out.append(None)
            continue
        base = ("node " + "+".join(t for t, _ in r.tags)) if r.kind == "node" else r.label
        seen[base] = seen.get(base, 0) + 1
        out.append(base if seen[base] == 1 else f"{base} #{seen[base]}")
    return out


_SHARED: dict = {}


def foreign_ids(root: Path, b: dict) -> set[str]:
    """Step ids of the projects a build shares its files with (`"shared_with"`: other ladder.json files whose builds
    tag regions in the same files, like an API module every area adds functions to). Their regions in this build's
    files are theirs: not unknown steps here, not recorded as this project's code, never regenerated by it."""
    out: set[str] = set()
    for rel in b.get("shared_with", []):
        p = (root / rel).resolve()
        if p not in _SHARED:
            try:
                other = json.loads(p.read_text())
                _SHARED[p] = set(parse_tree(p.parent / other["tree"]).keys())
            except (OSError, ValueError, KeyError, SystemExit) as e:
                raise SystemExit(f"shared_with: cannot read {rel}: {e}")
        out |= _SHARED[p]
    return out


def code_fingerprints(root: Path, b: dict) -> dict[str, dict[str, tuple[str, int]]]:
    """{file: {region key: (fingerprint, marker line)}} for one build's @node and @contract regions."""
    out: dict[str, dict[str, tuple[str, int]]] = {}
    theirs = foreign_ids(root, b)
    comment_re = re.compile(rf"^\s*{re.escape(COMMENT[b['lang']])}")
    for f in b.get("files", []):
        path = root / f
        if not path.exists():
            continue
        regions, owner, lines, _ = parse_regions(path, b["lang"])
        out[f] = {}
        for idx, (r, key) in enumerate(zip(regions, region_keys(regions))):
            if key is None or (r.kind == "node" and theirs and all(t in theirs for t, _ in r.tags)):
                continue
            own = [" ".join(l.split()) for i, l in enumerate(lines)
                   if owner[i] == idx and l.strip() and not comment_re.match(l)]
            out[f][key] = (hashlib.sha1("\n".join(own).encode()).hexdigest()[:8], r.start)
    return out


EXPORT_TS = re.compile(r"^\s*export\s+(?:declare\s+)?(?:abstract\s+)?(?:async\s+)?"
                       r"(?:function\*?|class|const|let|var|interface|type|enum|namespace)\s+([A-Za-z_$][\w$]*)", re.M)
EXPORT_TS_DEFAULT = re.compile(r"^\s*export\s+default\b", re.M)
EXPORT_TS_LIST = re.compile(r"^\s*export\s+(?:type\s+)?\{([^}]*)\}", re.M | re.S)
EXPORT_TS_STAR = re.compile(r"^\s*export\s+(?:type\s+)?\*\s*(?:as\s+([\w$]+)\s*)?from\s*['\"]([^'\"]+)['\"]", re.M)
EXPORT_CS = re.compile(r"^\s*public\s+(?:(?:static|sealed|abstract|partial|readonly|unsafe|new)\s+)*"
                       r"(?:record\s+(?:class|struct)\s+|class\s+|interface\s+|record\s+|struct\s+|enum\s+|delegate\s+\S+\s+)"
                       r"([A-Za-z_]\w*)", re.M)
EXPORT_PY = re.compile(r"^(?:async\s+)?(?:def|class)\s+([A-Za-z]\w*)|^([A-Za-z]\w*)\s*(?::[^=]*)?=", re.M)


def text_export_names(text: str, lang: str) -> list[str]:
    """The names a piece of code exports (see export_names), for one region's lines."""
    names: set[str] = set()
    if lang in ("typescript", "javascript"):
        names |= set(EXPORT_TS.findall(text))
        if EXPORT_TS_DEFAULT.search(text):
            names.add("default")
    elif lang == "csharp":
        names |= set(EXPORT_CS.findall(text))
    return sorted(names)


def export_names(path: Path, lang: str) -> list[str] | None:
    """The names a file makes available to other files: its export surface. None when the
    language has no simple notion of it here (the check is skipped)."""
    if not path.exists():
        return None
    text = path.read_text()
    names: set[str] = set()
    if lang in ("typescript", "javascript"):
        names |= set(EXPORT_TS.findall(text))
        if EXPORT_TS_DEFAULT.search(text):
            names.add("default")
        for block in EXPORT_TS_LIST.findall(text):
            for item in block.split(","):
                item = re.sub(r"^\s*type\s+", "", item.strip())
                if item:
                    names.add(item.split(" as ")[-1].strip())
        for alias, mod in EXPORT_TS_STAR.findall(text):
            names.add(alias or f"* from {mod}")
    elif lang == "csharp":
        names |= set(EXPORT_CS.findall(text))
    elif lang == "python":
        names |= {a or b for a, b in EXPORT_PY.findall(text) if not (a or b).startswith("_")}
    else:
        return None
    return sorted(names)


def record_exports(root: Path, cfg: dict, builds: list[str] | None = None) -> None:
    """Remember each file's export surface as approved (stamp, accept --exports)."""
    saved = load_code(root)
    ex = saved.setdefault("@exports", {})
    for b in cfg["builds"]:
        if b.get("tagged") is False or (builds and b["name"] not in builds):
            continue
        for f in b.get("files", []):
            names = export_names(root / f, b["lang"])
            if names is not None:
                ex.setdefault(b["name"], {})[f] = names
    (root / CODE_FILE).write_text(json.dumps(saved, indent=2, sort_keys=True) + "\n")


def export_changes(root: Path, b: dict) -> list[tuple[str, list[str], list[str]]]:
    """(file, added, removed) against the approved export surface, for files that have one."""
    was = load_code(root).get("@exports", {}).get(b["name"], {})
    out = []
    for f in b.get("files", []):
        if f not in was and b.get("adopted"):
            # Nothing approved yet: an adopted file's surface is the one git has (round 11: blind regeneration dropped
            # two exported props interfaces a barrel re-exports, and nothing said so before the first stamp).
            import ladder_extra as X
            pj = root / "ladder.json"
            ref = (json.loads(pj.read_text()).get("baseline") if pj.exists() else None) or "HEAD"
            try:
                orig = X._git_original(root, f, ref)
            except SystemExit:
                orig = None
            if orig is not None:
                tmp = root / ".ladder" / "exports-base.tmp"
                local_dir(root)
                tmp.write_text(orig)
                try:
                    was = {**was, f: export_names(tmp, b["lang"]) or []}
                finally:
                    tmp.unlink()
        if f not in was:
            continue
        now = export_names(root / f, b["lang"]) or []
        added = [n for n in now if n not in was[f]]
        removed = [n for n in was[f] if n not in now]
        if added or removed:
            out.append((f, added, removed))
    return out


def load_code(root: Path) -> dict:
    p = root / CODE_FILE
    return json.loads(p.read_text()) if p.exists() else {}


def record_code(root: Path, cfg: dict, builds: list[str] | None = None, keys: set | None = None,
                before: dict | None = None) -> int:
    """Record fingerprints. builds: limit to these builds. keys: limit to (build, file, key).
    before: fingerprints taken before a generator run; only regions that run changed are recorded."""
    saved = load_code(root)
    gen = load_generated(root) if before is not None else {}
    n = 0
    for b in cfg["builds"]:
        if b.get("tagged") is False or (builds and b["name"] not in builds):
            continue
        now = code_fingerprints(root, b)
        for f, regs in now.items():
            for key, (fp, _) in regs.items():
                if keys is not None and (b["name"], f, key) not in keys:
                    continue
                if before is not None and before.get(b["name"], {}).get(f, {}).get(key, (None,))[0] == fp:
                    continue
                if saved.get(b["name"], {}).get(f, {}).get(key) != fp:
                    saved.setdefault(b["name"], {}).setdefault(f, {})[key] = fp
                    n += 1
                if before is not None:
                    gen.setdefault(b["name"], {}).setdefault(f, {})[key] = fp
    (root / CODE_FILE).write_text(json.dumps(saved, indent=2, sort_keys=True) + "\n")
    if before is not None:
        local_dir(root)
        (root / GEN_FILE).write_text(json.dumps(gen, indent=2, sort_keys=True) + "\n")
    return n


def hand_edited(root: Path, b: dict) -> list[tuple[str, str, int]]:
    """(file, region key, line) for regions whose code differs from the recorded fingerprint and from
    what the generator last wrote in this checkout."""
    saved = load_code(root).get(b["name"], {})
    gen = load_generated(root).get(b["name"], {})
    out = []
    for f, regs in code_fingerprints(root, b).items():
        for key, (fp, line) in regs.items():
            was = saved.get(f, {}).get(key)
            if was is not None and was != fp and gen.get(f, {}).get(key) != fp:
                out.append((f, key, line))
    return out


def snapshot(root: Path, cfg: dict) -> dict:
    return {b["name"]: code_fingerprints(root, b) for b in cfg["builds"] if b.get("tagged") is not False}


def run_formatter(root: Path, cfg: dict, before: dict) -> None:
    """Run the project's "format_command" (e.g. ["npx", "prettier", "--write"]) on files the
    generator changed. Formatting never counts as a hand edit (fingerprints ignore spacing)."""
    cmd = cfg.get("format_command")
    if not cmd:
        return
    changed = []
    for b in cfg["builds"]:
        if b.get("tagged") is False:
            continue
        now = code_fingerprints(root, b)
        for f, regs in now.items():
            if regs != before.get(b["name"], {}).get(f):
                changed.append(str((root / f).resolve()))
    if changed:
        import subprocess
        res = subprocess.run(cmd + changed, capture_output=True, text=True, cwd=root)
        print(f"formatted {len(changed)} file(s) with {' '.join(cmd)}" + ("" if res.returncode == 0
              else f" (it reported a problem: {(res.stderr or res.stdout).strip()[:200]})"))


def retag(pj: Path, args: list[str]) -> int:
    """Mark code current for steps whose English was reworded without changing behavior (a typo,
    a clearer sentence, a resolved DECISION note): rewrite their markers' hashes, no regeneration.
    A person's call, like approval."""
    cfg, root, tree, _, _ = load_project(pj)
    ids = {x for a in args if not a.startswith("--") for x in a.split(",") if x}
    if not ids:
        raise SystemExit("usage: ladder retag <ladder.json> <step ids> [--build=NAME]   (only for rewording that changes no behavior)")
    build = next((a.split("=", 1)[1] for a in args if a.startswith("--build=")), None)
    n = 0
    for b in cfg["builds"]:
        if b.get("tagged") is False or (build and b["name"] != build):
            continue
        c = re.escape(COMMENT[b["lang"]])
        for f in b["files"]:
            path = root / f
            if not path.exists():
                continue
            lines = path.read_text().splitlines()
            changed = False
            for i, l in enumerate(lines):
                m = re.match(rf"^(\s*{c}\s*@node\s+)(.*)$", l)
                if not m:
                    continue
                toks = []
                for tok in m.group(2).split():
                    nid, _, h = tok.partition("@")
                    if nid in ids and nid in tree and h != tree[nid].hash:
                        tok = f"{nid}@{tree[nid].hash}"
                        changed = True
                        n += 1
                        print(f"retagged  {b['name']}  {f}:{i + 1}  [{nid}] {h} -> {tree[nid].hash}")
                    toks.append(tok)
                lines[i] = m.group(1) + " ".join(toks)
            if changed:
                path.write_text("\n".join(lines) + "\n")
    if not n:
        print("nothing to retag: no stale markers for those steps")
        return 1
    return 0


def accept(pj: Path, args: list[str]) -> int:
    """Accept hand edits: the English still describes the code as it is now (a refactor, a
    formatting change, or the English was updated to match)."""
    cfg, root, _, _, _ = load_project(pj)
    build = next((a.split("=", 1)[1] for a in args if a.startswith("--build=")), None)
    ids = {x for a in args if not a.startswith("--") for x in a.split(",") if x}
    if "--exports" in args:
        record_exports(root, cfg, [build] if build else None)
        print("accepted the current exports" + (f" of {build}" if build else " of every build"))
        if not ids:
            return 0
    src = next((a.split("=", 1)[1] for a in args if a.startswith("--from=")), None)
    if src:
        return accept_from(root, cfg, Path(src), build, ids)
    keys = set()
    for b in cfg["builds"]:
        if b.get("tagged") is False or (build and b["name"] != build):
            continue
        for f, key, line in hand_edited(root, b):
            region_ids = set(key.split(" ", 1)[1].split(" #")[0].split("+")) if key.startswith("node ") else {key}
            if not ids or region_ids & ids or key in ids:
                keys.add((b["name"], f, key))
                print(f"accepted  {b['name']}  {f}:{line}  {key}")
    if not keys:
        print("nothing to accept: no hand-edited regions match")
        return 1
    record_code(root, cfg, keys=keys)
    return 0


def accept_from(root: Path, cfg: dict, src_pj: Path, build: str | None, ids: set[str]) -> int:
    """Regions generated in a scratch copy and copied here: accept each one whose code is exactly what
    the scratch project recorded as generated (its ladder.code.json). Anything else stays hand-edited."""
    src_root = src_pj.parent if src_pj.suffix == ".json" else src_pj
    theirs = load_code(src_root)
    for bn, files in load_generated(src_root).items():      # what scratch generated, even if a sync
        for f, regs in files.items():                         # overwrote its ladder.code.json
            theirs.setdefault(bn, {}).setdefault(f, {}).update(regs)
    if not theirs:
        print(f"no {CODE_FILE} in {src_root}: nothing was generated there")
        return 1
    keys, refused = set(), []
    for b in cfg["builds"]:
        if b.get("tagged") is False or (build and b["name"] != build):
            continue
        for f, key, line in hand_edited(root, b):
            region_ids = set(key.split(" ", 1)[1].split(" #")[0].split("+")) if key.startswith("node ") else {key}
            if ids and not (region_ids & ids or key in ids):
                continue
            mine = code_fingerprints(root, b).get(f, {}).get(key, (None,))[0]
            if theirs.get(b["name"], {}).get(f, {}).get(key) == mine:
                keys.add((b["name"], f, key))
                print(f"accepted  {b['name']}  {f}:{line}  {key}  (generated in {src_root})")
            else:
                refused.append(f"{f}:{line}  {key}")
    for r in refused:
        print(f"still hand-edited  {r}  (differs from what {src_root} generated)")
    if keys:
        record_code(root, cfg, keys=keys)
    if not keys and not refused:
        if not any(v for k, v in load_code(root).items() if not k.startswith("@")):
            print("nothing to accept: this project has no approved code recorded yet (no stamp), so code copied here "
                  "is not a hand edit; check and stamp it as it is")
        else:
            print(f"nothing to accept: no region here differs from the approved code. `accept --from` does not copy: "
                  f"copy the regenerated build files from {src_root} first, then run it again")
        return 0
    return 0 if keys and not refused else 1


# ---------------------------------------------------------------- viewer


def build_view(pj: Path, out: Path) -> None:
    cfg, root, tree, lock, _ = load_project(pj)
    rep = check(pj)
    builds = []
    for b in cfg["builds"]:
        files = []
        for f in b["files"]:
            regions, owner, lines, _ = parse_regions(root / f, b["lang"])
            files.append(dict(
                path=f,
                lines=lines,
                owner=owner,
                regions=[dict(kind=r.kind, tags=[t[0] for t in r.tags], hashes=[t[1] for t in r.tags],
                              label=r.label, start=r.start, end=r.end, parent=r.parent)
                         for r in regions]))
        traces = []
        for tp in sorted((root / "traces" / b["name"]).glob("*.jsonl")):
            events = [json.loads(l) for l in tp.read_text().splitlines() if l.strip()]
            traces.append(dict(name=tp.stem, events=events))
        builds.append(dict(name=b["name"], lang=b["lang"], mode=b.get("mode", ""),
                           uses=b.get("uses", ""), files=files, traces=traces))
    data = dict(
        title=cfg.get("title", pj.stem),
        tree=[dict(id=n.id, title=n.title, depth=n.depth, parent=n.parent, children=n.children,
                   inputs=n.inputs, outputs=n.outputs, effects=n.effects, steps=n.steps,
                   notes=n.notes, hash=n.hash) for n in tree.values()],
        builds=builds,
        report=rep,
    )
    template = (Path(__file__).parent / "viewer_template.html").read_text()
    payload = json.dumps(data).replace("</", "<\\/")
    out.write_text(template.replace("/*__LADDER_DATA__*/null", payload))
    print(f"viewer -> {out}")


def make_reference(pj: Path, src: str | None, retire: list[str] | None = None) -> int:
    """After a reviewed, intended change of behaviour: the recording of build `src` (made from the approved code)
    becomes the comparison's reference. The old reference traces move to traces/history/, so nothing is lost.
    `retire`: builds recorded from the old code that cannot be recorded again (an earlier scratch copy): their traces
    move to traces/history/ too and they leave ladder.json's builds."""
    import shutil
    from datetime import datetime
    cfg, root = json.loads(pj.read_text()), pj.parent
    c = cfg.get("compare") or {}
    if not c.get("reference"):
        raise SystemExit("ladder reference: this project has no compare.reference")
    folder = {b["name"]: b.get("traces", b["name"]) for b in cfg.get("builds", [])}
    def retire_builds() -> None:
        stamp_ = f"{datetime.now():%Y%m%d-%H%M%S}"
        for name in retire:
            if name not in folder or name == c["reference"]:
                raise SystemExit(f"ladder reference: cannot retire '{name}' (not a build, or the reference)")
            d = root / "traces" / folder[name]
            if d.exists() and not any(b.get("traces", b["name"]) == folder[name]
                                      for b in cfg["builds"] if b["name"] not in retire):
                dest = root / "traces" / "history" / f"{d.name}-{stamp_}"
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(d), str(dest))
                print(f"moved   traces/{d.name} -> {dest.relative_to(root)}")
        cfg["builds"] = [b for b in cfg["builds"] if b["name"] not in retire]
        pj.write_text(json.dumps(cfg, indent=2) + "\n")
        print(f"retired {', '.join(retire)} (removed from ladder.json builds)")

    if retire and not src:
        retire_builds()
        return 0
    if src not in folder:
        raise SystemExit(f"ladder reference: no build '{src}' (builds: {', '.join(folder)})")
    ref_dir, src_dir = root / "traces" / folder.get(c["reference"], c["reference"]), root / "traces" / folder[src]
    if src_dir == ref_dir:
        raise SystemExit(f"ladder reference: build '{src}' already records into the reference's traces")
    if not any(src_dir.glob("*.jsonl")):
        raise SystemExit(f"ladder reference: traces/{folder[src]} has no recordings")
    if ref_dir.exists():
        dest = root / "traces" / "history" / f"{ref_dir.name}-{datetime.now():%Y%m%d-%H%M%S}"
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(ref_dir), str(dest))
        print(f"moved   traces/{ref_dir.name} -> {dest.relative_to(root)}")
    shutil.copytree(src_dir, ref_dir)
    print(f"copied  traces/{src_dir.name} -> traces/{ref_dir.name} (the reference now)")
    if retire:
        retire_builds()   # after the copy, so the build the reference came from can be retired too
    print("Other builds are now compared with this run: re-record any whose recording came from the old code, or, when\n"
          "that code is gone (an earlier scratch copy), retire them: `ladder reference <ladder.json> --retire=A,B`.")
    return 0


# ---------------------------------------------------------------- main


def run_after_generate(cfg: dict, root: Path) -> int:
    """ladder.json "after_generate": commands that rebuild files derived from the code (an API's committed OpenAPI
    contract, client types generated from it), run from check_cwd once generation changed code. Round 11: a change to
    a message limit regenerated the API, and only the contract snapshot test said the contract was now stale."""
    cmds = cfg.get("after_generate") or []
    cwd = (root / cfg.get("check_cwd", ".")).resolve()
    bad = 0
    for c in cmds:
        res = subprocess.run(c, shell=isinstance(c, str), cwd=cwd, capture_output=True, text=True)
        shown = c if isinstance(c, str) else " ".join(c)
        print(f"after_generate: {shown}: " + ("ok" if res.returncode == 0 else
              f"FAILED (exit {res.returncode}): {(res.stderr or res.stdout).strip()[-300:]}"))
        bad += res.returncode != 0
    return 1 if bad else 0


def repair_until_builds(pj: Path, cfg: dict, root: Path, build: str | None, rounds: int) -> int:
    """`regen --repair=N`: run the project's check_command; while it fails, repair the regions its errors point at
    (in the given build, or every tagged build), at most N rounds. 0 when it builds, 1 when it still does not."""
    import regen as R
    targets = [build] if build else [b["name"] for b in cfg["builds"] if b.get("tagged") is not False]
    for r in range(rounds + 1):
        errs = R.project_check_errors(cfg, root)
        if errs is None:
            print("--repair: no check_command in ladder.json, so nothing tells whether the code builds")
            return 1
        if not errs:
            print("builds: clean" + (f" after {r} repair round(s)" if r else " without repair"))
            return 0
        n = len(errs.splitlines())
        if r == rounds:
            print(f"STILL DOES NOT BUILD after {rounds} repair round(s) ({n} error lines):\n" + errs[:3000])
            return 1
        print(f"build errors ({n} lines); repair round {r + 1} of {rounds}")
        before = snapshot(root, cfg)
        for t in targets:
            R.repair(pj, t, errs)
        run_formatter(root, cfg, before)
        restamp_contracts(root, cfg)
        record_code(root, cfg, before=before)
    return 1


def main(argv: list[str]) -> int:
    if len(argv) >= 3 and argv[1] in {"adopt-check", "replay", "init", "export", "tag"}:
        import ladder_extra as X
        return {"adopt-check": X.adopt_check, "replay": X.replay, "init": X.init, "export": X.export,
                "tag": X.tag}[argv[1]](argv[2:])
    if len(argv) >= 3 and argv[1] == "accept":
        return accept(Path(argv[2]), argv[3:])
    if len(argv) >= 3 and argv[1] == "schema":
        import ladder_schema as S
        cfg, root = json.loads(Path(argv[2]).read_text()), Path(argv[2]).parent
        schemas = S.load_schemas(cfg, root)
        want = argv[3] if len(argv) > 3 else None
        for sname, ents in schemas.items():
            for e in sorted(ents.values(), key=lambda x: x.name):
                if want and want not in (e.name, e.table, e.table_name()):
                    continue
                print(f"[{sname}] " + e.describe() + "\n")
        return 0
    if len(argv) >= 3 and argv[1] == "test":
        import ladder_links as K
        return K.run_tests(Path(argv[2]), [a for a in argv[3:] if not a.startswith("--")] or None)
    if len(argv) >= 3 and argv[1] == "reference":
        src = next((a.split("=", 1)[1] for a in argv[3:] if a.startswith("--from=")), None)
        retire = next((a.split("=", 1)[1].split(",") for a in argv[3:] if a.startswith("--retire=")), None)
        if not src and not retire:
            raise SystemExit("usage: ladder reference <ladder.json> --from=BUILD [--retire=A,B]")
        return make_reference(Path(argv[2]), src, retire)
    if len(argv) >= 3 and argv[1] == "retag":
        return retag(Path(argv[2]), argv[3:])
    if len(argv) >= 3 and argv[1] in {"generate", "repair", "regen"}:
        import regen as R
        pj = Path(argv[2])
        cfg, root = json.loads(pj.read_text()), pj.parent
        R.DISCARD_HAND_EDITS = "--discard-hand-edits" in argv
        R.OUT = next((a.split("=", 1)[1] for a in argv[3:] if a.startswith("--out=")), None)
        build = next((a.split("=", 1)[1] for a in argv[3:] if a.startswith("--build=")), None)
        before = snapshot(root, cfg)
        if argv[1] == "generate":
            status = R.generate(pj, build)
        elif argv[1] == "repair":
            errfile = next((a for a in argv[3:] if not a.startswith("--")), None)
            if not errfile:
                raise SystemExit("usage: ladder repair <ladder.json> <errors.txt> --build=NAME")
            status = R.repair(pj, build, Path(errfile).read_text())
        else:
            R.REDO.update(x for a in argv[3:] if a.startswith("--redo=") for x in a.split("=", 1)[1].split(","))
            R.BLIND = "--blind" in argv
            if R.BLIND and not build:
                raise SystemExit("ladder regen --blind needs --build=NAME (and is meant for a scratch copy of the repo)")
            status = R.regen(pj, only=build, dry_run="--dry-run" in argv)
        if "--dry-run" not in argv and not any(a.startswith("--out=") for a in argv):
            run_formatter(root, cfg, before)
            restamp_contracts(root, cfg)
            # Regions the generator just wrote are its code now, not hand edits.
            record_code(root, cfg, before=before)
        rounds = next((a.split("=", 1)[1] for a in argv[3:] if a.startswith("--repair=")), None)
        if argv[1] == "regen" and rounds and "--dry-run" not in argv:
            status = max(status, repair_until_builds(pj, cfg, root, build, int(rounds)))
        if "--dry-run" not in argv and not any(a.startswith("--out=") for a in argv) and snapshot(root, cfg) != before:
            status = max(status, run_after_generate(cfg, root))
        return status
    if len(argv) < 3 or argv[1] not in {"check", "hashes", "stamp", "view"}:
        print(__doc__)
        return 2
    cmd, pj = argv[1], Path(argv[2])
    if cmd == "check":
        only = next((a.split("=", 1)[1].split(",") for a in argv[3:] if a.startswith("--builds=")), None)
        since = next((a.split("=", 1)[1] for a in argv[3:] if a.startswith("--since=")), None)
        schema_since = next((a.split("=", 1)[1] for a in argv[3:] if a.startswith("--schema-since=")), since)
        links_since = next((a.split("=", 1)[1] for a in argv[3:] if a.startswith("--links-since=")), since)
        global SHOW_ALL
        SHOW_ALL = "--all-differences" in argv[3:]
        rep = check(pj, only, schema_since, links_since, since)
        print_report(rep, load_project(pj)[2])
        # 0 ok · 1 problems · 3 only waiting for a person's approval
        return {"ok": 0, "problems": 1, "awaiting-approval": 3}[rep["status"]]
    if cmd == "hashes":
        cfg, _, tree, _, _ = load_project(pj)
        for n in tree.values():
            print(f"{'  ' * n.depth}{n.id}@{n.hash}  {n.title}")
        scoped = [b for b in cfg["builds"] if "steps" in b or "data" in b]
        if scoped:
            print("contract hash per build (for @contract regions):")
            for b in scoped:
                print(f"  {b['name']:<24} {contract_hash(tree, b)}  data: {', '.join(build_data(tree, b)) or '-'}")
        else:
            print(f"contract hash (for @contract regions): {contract_hash(tree)}")
        return 0
    if cmd == "stamp":
        stamp(pj)
        return 0
    build_view(pj, Path(argv[3]) if len(argv) > 3 else pj.parent / "viewer.html")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv))
    except BrokenPipeError:          # output piped into `head` and closed early: not an error
        sys.stderr.close()
        sys.exit(0)

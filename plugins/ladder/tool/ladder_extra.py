"""ladder commands for working on existing codebases: adopt-check, replay, init, export."""
from __future__ import annotations

import difflib
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

import ladder as L


def opt(argv: list[str], name: str, required: bool = False, default: str | None = None) -> str | None:
    """The value after `name`, with a clear error when it is required and missing."""
    if name in argv:
        i = argv.index(name)
        if i + 1 >= len(argv) or argv[i + 1].startswith("--"):
            raise SystemExit(f"ladder: {name} needs a value")
        return argv[i + 1]
    if required:
        raise SystemExit(f"ladder: {name} is required (see `ladder` for usage)")
    return default


def opts(argv: list[str], name: str) -> list[str]:
    return [argv[i + 1] for i, a in enumerate(argv[:-1]) if a == name]

# ---------------------------------------------------------------- adopt-check


def _is_comment(line: str, lang: str) -> bool:
    s = line.strip()
    if not s:
        return True
    c = L.COMMENT.get(lang, "//")
    if s.startswith(c):
        return True
    return lang in L.BLOCK_COMMENT_LANGS and (s.startswith("/*") or s.startswith("*") or s.endswith("*/"))


def compare_tagging(original: str, tagged: str, lang: str) -> dict:
    """Transcription may only ADD comment or blank lines. Everything else is a violation."""
    a, b = original.splitlines(), tagged.splitlines()
    removed, added_code, added_comments = [], [], 0
    sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op in ("delete", "replace"):
            removed += [(i + 1, a[i]) for i in range(i1, i2)]
        if op in ("insert", "replace"):
            for j in range(j1, j2):
                if _is_comment(b[j], lang):
                    added_comments += 1
                else:
                    added_code.append((j + 1, b[j]))
    return dict(removed=removed, added_code=added_code, added_comments=added_comments,
                ok=not removed and not added_code)


def _git_original(root: Path, rel: str, ref: str) -> str | None:
    top = subprocess.run(["git", "-C", str(root), "rev-parse", "--show-toplevel"],
                         capture_output=True, text=True)
    if top.returncode != 0:
        raise SystemExit("adopt-check: the project is not inside a git repository; use --original/--tagged")
    path = (root / rel).resolve().relative_to(Path(top.stdout.strip()).resolve())
    res = subprocess.run(["git", "-C", top.stdout.strip(), "show", f"{ref}:{path.as_posix()}"],
                         capture_output=True, text=True)
    return res.stdout if res.returncode == 0 else None


def _print_result(name: str, r: dict) -> None:
    if r["ok"]:
        print(f"  ok   {name}: only comment lines added ({r['added_comments']})")
        return
    print(f"  FAIL {name}")
    for ln, text in r["removed"][:10]:
        print(f"         removed or changed original line {ln}: {text.strip()[:90]}")
    for ln, text in r["added_code"][:10]:
        print(f"         added non-comment line {ln}: {text.strip()[:90]}")


def adopt_check(argv: list[str]) -> int:
    if "--original" in argv:
        tagged_path = opt(argv, "--tagged", required=True)
        r = compare_tagging(Path(opt(argv, "--original", required=True)).read_text(),
                            Path(tagged_path).read_text(), opt(argv, "--lang", required=True))
        _print_result(tagged_path, r)
        return 0 if r["ok"] else 1
    if not argv or argv[0].startswith("--"):
        raise SystemExit("usage: ladder adopt-check <ladder.json> [--base GIT_REF]")
    pj = Path(argv[0])
    ref = opt(argv, "--base", default="HEAD")
    cfg, root, *_ = L.load_project(pj)
    bad = 0
    print(f"Transcription check against {ref} (tagging may only add comments):")
    for b in cfg["builds"]:
        if not b.get("adopted"):
            continue
        for f in b["files"]:
            orig = _git_original(root, f, ref)
            if orig is None:
                print(f"  skip {f}: not in {ref} (new file)")
                continue
            r = compare_tagging(orig, (root / f).read_text(), b["lang"])
            _print_result(f, r)
            bad += not r["ok"]
    print("RESULT:", "ok" if not bad else f"{bad} file(s) changed code")
    return 1 if bad else 0


# ---------------------------------------------------------------- replay


def _mask_one(v, kind: str, sent_at):
    """How a masked value is written to the trace. value: hidden entirely. presence: only whether it
    is null, empty or set (and its JSON type). time: a date-time made relative to when the request
    was sent, rounded to the minute (time:s for seconds), e.g. "now+120m"."""
    if kind == "presence":
        if v is None:
            return "<null>"
        if v in ("", [], {}):
            return "<empty>"
        names = {str: "text", bool: "yes/no", int: "number", float: "number", dict: "object", list: "list"}
        return f"<{names.get(type(v), 'set')}>"
    if kind.startswith("time"):
        from datetime import datetime, timezone
        if not isinstance(v, str):
            return "<null>" if v is None else "<not a time>"
        try:
            t = datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError:
            return "<not a time>"
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        secs = (t - sent_at).total_seconds()
        if kind == "time:s":
            return f"now{'+' if secs >= 0 else '-'}{abs(round(secs))}s"
        return f"now{'+' if secs >= 0 else '-'}{abs(round(secs / 60))}m"
    return "<masked>"


def _mask(v, keys, sent_at=None):
    """keys: a set of names (hidden entirely) or {name: kind}."""
    kinds = keys if isinstance(keys, dict) else {k: "value" for k in keys}
    if isinstance(v, dict):
        return {k: (_mask_one(x, kinds[k], sent_at) if k in kinds else _mask(x, kinds, sent_at)) for k, x in v.items()}
    if isinstance(v, list):
        return [_mask(x, kinds, sent_at) for x in v]
    return v


def _parse_mask(text: str) -> dict:
    out = {}
    for item in (x.strip() for x in text.split(",")):
        if not item:
            continue
        name, _, kind = item.partition(":")
        kind = kind or "value"
        if kind not in ("value", "presence", "time", "time:s"):
            raise SystemExit(f"replay: --mask {item}: kinds are value (default), presence, time, time:s")
        out[name] = kind
    return out


JWT_RE = re.compile(r"^[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]*$")
VAR_RE = re.compile(r"\{\{\s*(env|var|now)\s*(?::\s*([^}]*?))?\s*\}\}")


def _jwt_claims(token: str) -> dict | None:
    """A JWT's claims, with its times made relative (lifetime = exp - iat), so two runs compare."""
    import base64
    try:
        part = token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))
    except Exception:
        return None
    if not isinstance(claims, dict):
        return None
    iat = claims.get("iat")
    out = {}
    for k, v in claims.items():
        if k in ("iat", "nbf"):
            continue
        if k == "exp" and isinstance(v, (int, float)) and isinstance(iat, (int, float)):
            out["lifetime_s"] = v - iat
        elif k == "exp":
            out["exp"] = "<time>"
        else:
            out[k] = v
    return {"jwt": out}


def _jwts(v, on: bool):
    """Replace JWT strings anywhere in a value by their claims (when --jwt is given)."""
    if not on:
        return v
    if isinstance(v, dict):
        return {k: _jwts(x, on) for k, x in v.items()}
    if isinstance(v, list):
        return [_jwts(x, on) for x in v]
    if isinstance(v, str) and JWT_RE.match(v):
        return _jwt_claims(v) or v
    return v


def _subst(v, env: dict, saved: dict):
    """Fill {{env:NAME}}, {{var:name}} and {{now}} / {{now+30s}} / {{now-2d}} in strings, recursively."""
    import os
    from datetime import datetime, timedelta, timezone

    def one(m):
        kind, arg = m.group(1), (m.group(2) or "").strip()
        if kind == "env":
            if arg not in os.environ and arg not in env:
                raise SystemExit(f"replay: environment variable {arg} is not set (scenarios read secrets from the environment)")
            return env.get(arg, os.environ.get(arg, ""))
        if kind == "var":
            if arg not in saved:
                raise SystemExit(f"replay: {{{{var:{arg}}}}} used before a request saved it")
            return str(saved[arg])
        t = datetime.now(timezone.utc)
        mm = re.fullmatch(r"([+-])(\d+)([smhd])", arg.replace(" ", "")) if arg else None
        if mm:
            n = int(mm.group(2)) * {"s": 1, "m": 60, "h": 3600, "d": 86400}[mm.group(3)]
            t = t + timedelta(seconds=n if mm.group(1) == "+" else -n)
        return t.isoformat().replace("+00:00", "Z")
    if isinstance(v, str):
        whole = VAR_RE.fullmatch(v.strip())
        if whole and whole.group(1) == "var" and (whole.group(2) or "").strip() in saved:
            return saved[whole.group(2).strip()]          # keep the saved value's type
        return VAR_RE.sub(one, v)
    if isinstance(v, dict):
        return {k: _subst(x, env, saved) for k, x in v.items()}
    if isinstance(v, list):
        return [_subst(x, env, saved) for x in v]
    return v


def _pick(result: dict, path: str):
    """A value from a result by path: status, body.a.b.0, header.location, cookie.refresh_token."""
    head, _, rest = path.partition(".")
    if head not in ("status", "header", "cookie", "body"):
        head, rest = "body", path           # a bare path means the body: "accessToken" = "body.accessToken"
    if head == "status":
        return result["status"]
    if head in ("header", "cookie"):
        return result["_" + head + "s"].get(rest.lower() if head == "header" else rest)
    cur = result.get("body")
    for k in rest.split(".") if rest else []:
        if isinstance(cur, list) and k.isdigit():
            cur = cur[int(k)] if int(k) < len(cur) else None
        elif isinstance(cur, dict):
            cur = cur.get(k)
        else:
            return None
    return cur


def replay(argv: list[str]) -> int:
    """Send each scenario's requests to a running service, in order; one trace per scenario.
    Each request becomes a traced step (its "step" field, default "http") whose result is
    {status, body} plus any recorded headers and cookies. Comparing these traces across builds is
    a black-box check that needs no changes to the service's code.

    Per request: "wait" (seconds to sleep first; a {"wait": n} entry alone just pauses), "headers",
    "body", "save" ({"name": "body.token"} or just "token" for later {{var:name}}), "record_headers"
    (names). A scenario may list "mask" entries too. --mask name[:kind]: value hides it, presence keeps
    null / empty / set, time keeps it relative to when the request was sent. --observe runs a command
    after each request (e.g. a SQL command count) and compares what it prints. Anywhere in a request: {{env:NAME}} for
    secrets kept out of scenario files, {{var:name}}, {{now}} / {{now+30s}}. Cookies are kept per
    scenario like a browser and every Set-Cookie is recorded by name and attributes."""
    import http.cookiejar
    import time as _time
    if not argv or argv[0].startswith("--"):
        raise SystemExit("usage: ladder replay <scenario.json|folder> --base URL --out traces/<build> "
                         "[--mask a,b:presence,c:time] [--header 'K: V'] [--before-each 'command'] [--record-headers a,b] [--jwt] "
                         "[--observe 'command']")
    src = Path(argv[0])
    base = opt(argv, "--base", required=True).rstrip("/")
    out = Path(opt(argv, "--out", required=True))
    mask = _parse_mask(opt(argv, "--mask", default=""))
    observe = opt(argv, "--observe")
    before_each = opt(argv, "--before-each")
    record_default = [h.strip().lower() for h in opt(argv, "--record-headers", default="").split(",") if h.strip()]
    jwt_on = "--jwt" in argv
    headers = {"Content-Type": "application/json"}
    for h in opts(argv, "--header"):
        k, _, v = h.partition(":")
        headers[k.strip()] = v.strip()
    files = sorted(src.glob("*.json")) if src.is_dir() else [src]
    out.mkdir(parents=True, exist_ok=True)
    for f in files:
        if before_each:
            # e.g. reset and reseed the test database (and its caches), so every scenario starts the same
            res = subprocess.run(before_each, shell=True)
            if res.returncode != 0:
                raise SystemExit(f"replay: --before-each command failed ({res.returncode}) before {f.name}")
        sc = json.loads(f.read_text())
        env = sc.get("env", {})
        saved: dict = {}
        jar = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar),
                                             urllib.request.HTTPRedirectHandler())
        events = []
        mask_f = {**mask, **_parse_mask(",".join(sc.get("mask", [])))}
        for raw_r in sc["requests"]:
            if raw_r.get("wait"):
                _time.sleep(float(raw_r["wait"]))
            if "path" not in raw_r:
                continue        # {"wait": 32} on its own: a pause between requests, nothing traced
            from datetime import datetime, timezone
            sent_at = datetime.now(timezone.utc)
            r = _subst({k: v for k, v in raw_r.items() if k != "save"}, env, saved)
            step = r.get("step", "http")
            data = None if "body" not in r else json.dumps(r["body"]).encode()
            # A request's own headers override the defaults; an empty value removes that header.
            hdrs = {k: v for k, v in {**_subst(headers, env, saved), **r.get("headers", {})}.items() if v != ""}
            req = urllib.request.Request(base + r["path"], data=data, method=r["method"], headers=hdrs)
            try:
                resp = opener.open(req, timeout=60)
                status, rawb, rh = resp.status, resp.read(), resp.headers
            except urllib.error.HTTPError as e:
                status, rawb, rh = e.code, e.read(), e.headers
            except urllib.error.URLError as e:
                raise SystemExit(f"replay: cannot reach {base}: {e.reason}")
            text = rawb.decode("utf-8", "replace")
            try:
                body = json.loads(text) if text.strip() else None
            except ValueError:
                body = text
            # Cookies the response set: name -> value, and their attributes for the trace.
            set_cookies, cookie_vals = {}, {}
            for line in rh.get_all("Set-Cookie") or []:
                parts = [p.strip() for p in line.split(";")]
                name, _, value = parts[0].partition("=")
                attrs = sorted(p.split("=")[0].lower() + ("=" + p.split("=", 1)[1] if "=" in p and
                               p.split("=")[0].lower() in ("path", "samesite", "max-age", "domain") else "")
                               for p in parts[1:] if p)
                cookie_vals[name] = value
                set_cookies[name] = {"value": _jwts(value, jwt_on) if value else "", "attrs": attrs}
            hdr_map = {k.lower(): v for k, v in rh.items()}
            full = {"status": status, "body": body, "_headers": hdr_map, "_cookies": cookie_vals}
            for name, path in (raw_r.get("save") or {}).items():
                saved[name] = _pick(full, path)
            result = {"status": status, "body": _jwts(body, jwt_on)}
            wanted = record_default + [h.lower() for h in r.get("record_headers", [])]
            if wanted:
                if any(h != "set-cookie" for h in wanted):
                    result["headers"] = {h: hdr_map.get(h) for h in wanted if h != "set-cookie"}
                if "set-cookie" in wanted:
                    result["set_cookie"] = {k: (v if jwt_on and isinstance(v["value"], dict) else
                                                {"value": "<set>" if v["value"] else "<empty>", "attrs": v["attrs"]})
                                            for k, v in set_cookies.items()}
            if observe:
                # e.g. count the SQL commands this request ran; whatever the command prints is compared too
                ob = subprocess.run(observe, shell=True, capture_output=True, text=True)
                if ob.returncode != 0:
                    raise SystemExit(f"replay: --observe command failed ({ob.returncode}): {ob.stderr.strip()[:200]}")
                result["observed"] = ob.stdout.strip()
            result = _mask(result, mask_f, sent_at)
            info = f"{raw_r['method']} {raw_r['path']}"
            events.append({"step": step, "ev": "enter", "ms": 0, "info": info})
            events.append({"step": step, "ev": "exit", "ms": 0, "info": f"{status}",
                           "data": json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=False)})
        (out / f"{f.stem}.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events))
        print(f"  {f.stem}: {len(events) // 2} requests -> {out / (f.stem + '.jsonl')}")
    return 0


# ---------------------------------------------------------------- init / export

TREE_TEMPLATE = """# {name}
#
# Steps:      [id] Title, indented under their parent
# Contract:   in: / out: / effects:   (field names in `backticks` are exact)
# How:        > one plain sentence per line
# Notes:      note: something a reviewer should know
# Libraries:  uses: a capability from vocabulary.ladder
# Data:       data Name, then indented `field: description` lines and `rule:` lines
# Rules:      rule name: a rule several steps refer to

[{prefix}.1] Describe the first thing this part of the system does
  in: what comes in
  out: what goes out
  > how, in one plain sentence per line
"""

VOCAB_TEMPLATE = """# Vocabulary: what the English may ask libraries to do, and how each build does it.
#
# capability <words the English uses>
#   in: / out:          the capability's contract
#   <language>: <package> <exact version> | <the call to use>      one line per language or build
#   known: a quirk worth knowing
#   check: how to verify the binding
"""


def init(argv: list[str]) -> int:
    if not argv or argv[0].startswith("--"):
        raise SystemExit("usage: ladder init <folder> --name NAME (--build NAME:LANG[:FILE] ... | --lang LANG ...) "
                         "[--steps NAME=GLOB ...] [--tree FILE] [--prefix ID] [--adopted]")
    folder = Path(argv[0])
    name = opt(argv, "--name", default=folder.name)
    # builds: --build api:csharp --build web:typescript (or --lang csharp, named after the language)
    # --build NAME:LANG[:FILE]  (FILE relative to the project folder, e.g. ../../src/Bulkhead.ts)
    specs = [b.split(":", 2) for b in opts(argv, "--build") if ":" in b]
    pairs = [(s_[0], s_[1]) for s_ in specs]
    files = {s_[0]: s_[2] for s_ in specs if len(s_) == 3}
    pairs += [(lang, lang) for lang in opts(argv, "--lang")]
    pairs = pairs or [("typescript", "typescript")]
    # --steps NAME=GLOB: the step ids a build implements, when builds share one tree
    scopes: dict[str, list[str]] = {}
    for sp in opts(argv, "--steps"):
        if "=" not in sp:
            raise SystemExit(f"ladder init: --steps needs NAME=GLOB, got '{sp}'")
        k, v = sp.split("=", 1)
        scopes.setdefault(k, []).append(v)
    adopted = "--adopted" in argv
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "project"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "conventions").mkdir(exist_ok=True)
    tree_file = opt(argv, "--tree", default=None) or f"{slug}.ladder"
    if not (folder / tree_file).exists():
        prefix = opt(argv, "--prefix", default=None) or (scopes and next(iter(scopes.values()))[0].split(".")[0].rstrip("*")) or slug.split("-")[0] or "s"
        (folder / tree_file).write_text(TREE_TEMPLATE.format(name=name, prefix=prefix))
    if not (folder / "vocabulary.ladder").exists():
        (folder / "vocabulary.ladder").write_text(VOCAB_TEMPLATE)
    if not (folder / "conventions" / "shared.md").exists():
        (folder / "conventions" / "shared.md").write_text("# Conventions shared by every build\n\n(fill in with the ladder-profile skill)\n")
    builds = []
    for bname, lang in pairs:
        conv = folder / "conventions" / f"{lang}.md"
        if not conv.exists():
            conv.write_text(f"# {lang} build profile\n\n(fill in with the ladder-profile skill)\n")
        b = {"name": bname, "lang": lang, "mode": "literal", "files": [files[bname]] if bname in files else [],
             "conventions": ["conventions/shared.md", f"conventions/{lang}.md"]}
        if bname in scopes:
            b["steps"] = scopes[bname]
        if adopted:
            b["adopted"] = True
        builds.append(b)
    cfg = {"title": name, "tree": tree_file, "vocabulary": "vocabulary.ladder",
           "generator": {"command": ["claude", "-p", "--output-format", "text", "--tools", ""]},
           "builds": builds,
           "compare": {"reference": builds[0]["name"], "runs": [], "number_tolerance": 0}}
    pj = folder / "ladder.json"
    if pj.exists():
        print(f"{pj} already exists; left it alone")
    else:
        pj.write_text(json.dumps(cfg, indent=2) + "\n")
    print(f"ladder project in {folder}: {tree_file}, vocabulary.ladder, conventions/, ladder.json")
    print(f"compare.reference is '{builds[0]['name']}' (the first build); change it in ladder.json if another build is the reference")
    return 0


def export(argv: list[str]) -> int:
    if not argv:
        raise SystemExit("usage: ladder export <ladder.json> [out.json]")
    pj = Path(argv[0])
    cfg, root, tree, *_ = L.load_project(pj)
    vocab = L.load_vocabulary(cfg, root) or {}
    data = {
        "title": cfg.get("title"),
        "contractHash": L.contract_hash(tree),
        "steps": [dict(id=n.id, title=n.title, parent=n.parent, children=n.children, depth=n.depth,
                       inputs=n.inputs, outputs=n.outputs, effects=n.effects, how=n.steps, notes=n.notes, compare=n.compare, reads=n.reads, writes=n.writes, calls=n.calls,
                       uses=n.uses, hash=n.hash, line=n.line) for n in tree.values()],
        "data": [dict(name=d.name, fields=[dict(name=k, description=v) for k, v in d.fields], rules=d.rules)
                 for d in tree.data.values()],
        "rules": tree.rules,
        "vocabulary": [dict(name=c.name, inputs=c.inputs, outputs=c.outputs, bindings=c.bindings,
                            known=c.known, checks=c.checks, tests=c.tests) for c in vocab.values()],
    }
    text = json.dumps(data, indent=2)
    if len(argv) > 1:
        Path(argv[1]).write_text(text + "\n")
        print(f"exported -> {argv[1]}")
    else:
        print(text)
    return 0

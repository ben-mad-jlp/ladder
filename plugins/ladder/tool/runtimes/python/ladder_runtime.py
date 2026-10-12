"""Ladder runtime for Python builds (hand-written support code, never generated).
Tracing (@step), canonical JSON and a fixable clock; the database helpers are an example for
sqlite3 and can be replaced by whatever the vocabulary binds "save data" to.
Mirrors the C# and TypeScript runtimes so traces from every build compare."""
import functools
import json
import sqlite3
import threading
import time

_conn = None
_lock = threading.Lock()
_fixed_now = None
_events: list = []
_t0 = time.perf_counter()
tracing = True


class DbConstraintError(Exception):
    pass


def open_db(path: str) -> None:
    global _conn
    _conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)


def db_query(sql: str, *args) -> list:
    with _lock:
        cur = _conn.execute(sql, args)
        cols = [c[0] for c in cur.description] if cur.description else []
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def db_execute(sql: str, *args) -> dict:
    with _lock:
        try:
            cur = _conn.execute(sql, args)
        except sqlite3.IntegrityError as e:
            raise DbConstraintError(str(e)) from e
        return {"changes": cur.rowcount if cur.rowcount >= 0 else 0, "lastId": cur.lastrowid or 0}


def fix_now(seconds: int) -> None:
    global _fixed_now
    _fixed_now = seconds


def now() -> int:
    return _fixed_now if _fixed_now is not None else int(time.time())


def response(status: int, body) -> dict:
    return {"status": status, "body": body}


def canonical(v) -> str:
    return json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def describe(v) -> str:
    if v is None:
        return "nothing"
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, (int, float)):
        if isinstance(v, float) and v.is_integer():
            v = int(v)
        return str(v) if isinstance(v, int) else f"{v:.2f}"
    if isinstance(v, str):
        return "'" + (v[:37] + "..." if len(v) > 40 else v) + "'"
    if isinstance(v, dict):
        def nested(x):
            if isinstance(x, str):
                return describe(x)
            if isinstance(x, dict):
                return "{...}"
            if isinstance(x, (list, tuple)):
                return f"{len(x)} items"
            return describe(x)
        return ", ".join(f"{k}={nested(v[k])}" for k in sorted(v))
    if isinstance(v, (list, tuple)):
        s = f"{len(v)} items"
        first = v[0] if v else None
        if isinstance(first, dict) and "title" in first:
            s += f", first {describe(first['title'])}"
        elif isinstance(first, int) and not isinstance(first, bool):
            s += f", first {first}"
        return s
    return type(v).__name__


def _record(step_id, ev, info, data=None):
    if not tracing:
        return
    e = {"step": step_id, "ev": ev, "ms": round((time.perf_counter() - _t0) * 1000, 2), "info": info}
    if data is not None:
        e["data"] = data
    _events.append(e)


def step(step_id: str):
    def wrap(fn):
        @functools.wraps(fn)
        def inner(*args):
            _record(step_id, "enter", ", ".join(describe(a) for a in args))
            try:
                result = fn(*args)
            except Exception:
                _record(step_id, "exit", "crashed", "crashed")
                raise
            _record(step_id, "exit", "done" if result is None else describe(result), canonical(result))
            return result
        return inner
    return wrap


def reset_trace() -> None:
    global _t0
    _events.clear()
    _t0 = time.perf_counter()


def save_trace(path) -> None:
    with open(path, "w") as f:
        for e in _events:
            f.write(canonical(e) + "\n")

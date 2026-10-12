// Ladder runtime for TypeScript builds (hand-written support code, never generated).
// Tracing for steps (step(), traceEvents(), canonical()), plus optional "ports" so generated logic
// reaches the network and the clock through functions a test can replace.
// Tracing adopted client code from a test: wrap the functions you call, e.g.
//   const add = step("client.1.3", hook.add);  ... then write traceEvents() to traces/<build>/<run>.jsonl

export interface Ports {
  /** Ask the service for a path such as "notes?page=1"; resolves to parsed JSON. */
  fetchJson(path: string): Promise<unknown>;
  /** Milliseconds since the Unix epoch. */
  now(): number;
  sleep(ms: number): Promise<void>;
}

export interface TraceEvent { step: string; ev: "enter" | "exit"; ms: number; info: string; data?: string; }

let ports: Ports | null = null;
const events: TraceEvent[] = [];
const listeners = new Set<(e: TraceEvent) => void>();
let t0 = Date.now();

export function configure(p: Ports): void { ports = p; }
function need(): Ports {
  if (!ports) throw new Error("ladder runtime: call configure() before running steps");
  return ports;
}

export const api = (path: string): Promise<unknown> => need().fetchJson(path);
export const wait = (ms: number): Promise<void> => need().sleep(ms);
export const now = (): number => need().now();

export class StepFailure extends Error {
  constructor(message: string) { super(message); this.name = "StepFailure"; }
}

// ---- tracing -------------------------------------------------------------

/** One short phrase per value. Identical rules in the Python runtime, so traces compare. */
export function describe(v: unknown): string {
  if (v === null || v === undefined) return "nothing";
  if (typeof v === "boolean") return v ? "yes" : "no";
  if (typeof v === "number") return Number.isInteger(v) ? String(v) : v.toFixed(2);
  if (typeof v === "string") return `'${v.length > 40 ? v.slice(0, 37) + "..." : v}'`;
  if (Array.isArray(v)) {
    let s = `${v.length} items`;
    const first = v[0];
    if (first && typeof first === "object" && !Array.isArray(first) && "title" in first) {
      s += `, first ${describe((first as { title: unknown }).title)}`;
    } else if (typeof first === "number") s += `, first ${first}`;
    return s;
  }
  if (typeof v === "object") {
    return Object.keys(v as object).sort().map((k) => {
      const x = (v as Record<string, unknown>)[k];
      const d = Array.isArray(x) ? `${x.length} items` : x && typeof x === "object" ? "{...}" : describe(x);
      return `${k}=${d}`;
    }).join(", ");
  }
  return typeof v;
}

/** The full value as JSON with sorted keys; the cross-build check compares this exactly. */
export function canonical(v: unknown): string {
  const sort = (x: unknown): unknown =>
    Array.isArray(x) ? x.map(sort)
      : x && typeof x === "object"
        ? Object.fromEntries(Object.keys(x as object).sort().map((k) => [k, sort((x as Record<string, unknown>)[k])]))
        : x === undefined ? null : x;
  return JSON.stringify(sort(v));
}

function record(step: string, ev: "enter" | "exit", info: string, data?: string): void {
  const e: TraceEvent = { step, ev, ms: Math.round((Date.now() - t0) * 100) / 100, info };
  if (data !== undefined) e.data = data;
  events.push(e);
  listeners.forEach((fn) => fn(e));
}

export function step<A extends unknown[], R>(id: string, fn: (...args: A) => Promise<R> | R) {
  return async (...args: A): Promise<R> => {
    record(id, "enter", args.map(describe).join(", "));
    try {
      const result = await fn(...args);
      record(id, "exit", describe(result), canonical(result));
      return result;
    } catch (err) {
      const msg = err instanceof StepFailure ? `failed: ${err.message}` : `crashed: ${String(err)}`;
      record(id, "exit", msg, msg);
      throw err;
    }
  };
}

/** Synchronous version of step(): keeps the call synchronous, so tracing doesn't change timing
 *  (use it for hooks, reducers, selectors and anything React calls during render). */
export function stepSync<A extends unknown[], R>(id: string, fn: (...args: A) => R) {
  return (...args: A): R => {
    record(id, "enter", args.map(describe).join(", "));
    try {
      const result = fn(...args);
      record(id, "exit", describe(result), canonical(result));
      return result;
    } catch (err) {
      const msg = `threw: ${err instanceof Error ? `${err.name}: ${err.message}` : String(err)}`;
      record(id, "exit", msg, canonical({ threw: msg.slice(7) }));
      throw err;
    }
  };
}

/** Record one observation under a step id (a callback fired, a state seen, a render). */
export function log(step: string, data: unknown): void {
  record(step, "exit", describe(data), canonical(data));
}

let ids = new WeakMap<object, number>();
let nextId = 1;
/** A stable label per object for this run ("#1", "#2", ...): put it in traces to compare
 *  identity ("the same list" vs "a new list") without depending on memory addresses. */
export function identity(v: unknown): string {
  if (v === null || typeof v !== "object" && typeof v !== "function") return canonical(v);
  let n = ids.get(v as object);
  if (n === undefined) { n = nextId++; ids.set(v as object, n); }
  return `#${n}`;
}

/** Replace Math.random and crypto.randomUUID with seeded versions; returns a restore function. */
export function seedRandom(seed: number): () => void {
  let s = (seed * 2654435761) >>> 0 || 1;
  const next = () => { s ^= s << 13; s >>>= 0; s ^= s >>> 17; s ^= s << 5; s >>>= 0; return s / 4294967296; };
  const oldRandom = Math.random;
  const c = (globalThis as { crypto?: { randomUUID?: () => string } }).crypto;
  const oldUuid = c?.randomUUID;
  Math.random = next;
  if (c) {
    c.randomUUID = () => {
      const h = Array.from({ length: 32 }, () => Math.floor(next() * 16).toString(16)).join("");
      return `${h.slice(0, 8)}-${h.slice(8, 12)}-4${h.slice(13, 16)}-a${h.slice(17, 20)}-${h.slice(20, 32)}`;
    };
  }
  return () => { Math.random = oldRandom; if (c && oldUuid) c.randomUUID = oldUuid; };
}

/** The trace as JSON lines, ready to write to traces/<build>/<run>.jsonl. */
export function traceJsonl(): string { return events.map((e) => JSON.stringify(e)).join("\n") + (events.length ? "\n" : ""); }

export function traceEvents(): TraceEvent[] { return [...events]; }
export function resetTrace(): void { events.length = 0; t0 = Date.now(); ids = new WeakMap(); nextId = 1; }
export function onTrace(fn: (e: TraceEvent) => void): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

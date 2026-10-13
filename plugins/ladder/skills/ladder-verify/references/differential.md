# Differential runs for libraries

A test suite checks what its authors thought of. A differential run checks that two builds do the
same thing on inputs nobody thought of: generate many random sequences of public calls from a seed,
run each sequence against the reference build and against the new build, log everything observable,
and compare the logs line by line.

## The harness

One script, given a build's folder and a seed range, prints one JSON line per seed:
`{"seed": 17, "log": [...]}`. Run it once per build, then compare the files.

```ts
// node --import=tsx/esm harness.ts <build folder> <from seed> <to seed>
import {mock} from 'node:test';
const {default: Lib} = await import(pathToFileURL(path.resolve(dir, 'source/index.ts')).href);

function rng(seed) { /* xorshift: same seed, same sequence, in every build */ }
const flush = async () => { for (let i = 0; i < 30; i++) await Promise.resolve(); };

async function scenario(seed) {
  const r = rng(seed);
  mock.timers.enable({apis: ['setTimeout', 'setInterval', 'Date'], now: 0});
  const log = [];
  // 1. Random options, including a few invalid ones: log a throw as {threw: `${name}: ${message}`}.
  // 2. Subscribe to every event; log {t: Date.now(), ev, arg, state} where state is a short string
  //    of the public getters (size/pending/flags).
  // 3. 5 to 20 random actions: calls with random arguments, awaits attached without blocking
  //    (log when they settle), and time steps. Log each call's return value or throw.
  //    Track every returned promise and log how it settles, so nothing goes unhandled.
  // 4. Advance time 1 ms at a time, flushing microtasks between ticks, until everything has settled.
  mock.timers.reset();
  return log;
}
```

Rules that keep it honest:
- **Deterministic.** Run the reference twice and confirm the two files are identical before trusting
  any difference.
- **Fake time, advanced in 1 ms ticks with a microtask flush after each tick.** Advancing 100 ms at
  once fires timers back to back without the microtasks between them, which hides ordering bugs.
- **Log order, not just values.** Events, settlements and state in the order they happened.
- **Messages verbatim**, errors as `name: message`.
- **Weight the random choices** toward the behavior being verified (after an English change, call
  the changed method more often).

## Feeding `ladder check`

Write each seed as `traces/<build>/s0001.jsonl`, one line per logged event, naming each event after
the step of the English that produces it. Every line is a step result, `"ev": "exit"`: `check` compares only those
and ignores other events (put the event's kind in `info` and first in `data`, e.g. `["threw", "..."]`). Harness
bookkeeping steps (setup, time ticks) go in `"extra_steps"`.

```json
{"step": "pq.1.28", "ev": "exit", "ms": 91, "info": "", "data": "{\"e\":\"boom-1\",\"onError\":\"#7\"}"}
```

Then in ladder.json: `"compare": {"reference": "original", "runs": ["s*"], "order": "strict"}`, and
`"tagged": false` on builds that are only compared. `ladder check` summarizes many runs in one line
per build and shows the first few that differ, applying each step's `compare:` lines.

## Reading the comparison

For each differing seed print the options, the first differing log line in both builds, and a few
lines around it. Group the differences by kind (first differing key) before reading them: one root
cause usually explains a whole group. Then classify as in the main skill (generated code wrong,
English ambiguous, reference surprising, environment).

**Mutation check.** Copy a build, change one comparison or constant, run the harness on it: it must
differ on some seeds. If it doesn't, the action mix doesn't reach that code; add actions until it does.

**Locality after an English change.** Compare the build before and after the change: every
differing seed should involve the changed behavior, and removing the expected new lines (a new
rejection, a new event) should make the logs identical. Anything left over is an unintended change.

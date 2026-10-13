---
name: ladder-verify
description: Verify laddered code by running it - write scenarios from the Ladder English, record traces from the reference build (often the existing system, via HTTP replay) and every other build, compare them step by step, explain each difference, and prepare the review and approval (ladder view, ladder stamp). Use this after code is generated or regenerated from Ladder, before approving an English change, when adopting existing code (to record its reference behavior), when two builds (C# and TypeScript, web and Android) might disagree, or when someone asks "does the generated code really match?"
---

# Verify laddered code

Markers and hashes prove code is *tagged* with the English; only running it proves it *behaves* like
the English. Verification runs every build on the same recorded inputs and compares what each step
handed back against a reference build: another language, or the existing system before the change.

Format: section 9 of `${CLAUDE_PLUGIN_ROOT}/reference/ladder-format.md`. Scenario format and examples:
`references/scenarios.md`. Run the tool as `ladder <command>` (or `python3
${CLAUDE_PLUGIN_ROOT}/tool/ladder.py <command>`).

## 1. Write scenarios from the English

Every `>` line and every error case in the steps being verified should be exercised by at least one
scenario request. Before writing new scenarios, check the project's existing ones and its runner:
reuse their format and folder. Include boundaries (exactly at a limit and one past it), empty and missing input,
not found, someone else's data, paging edges, repeated requests. Group requests into scenario files
by story ("create_and_list", "validation_errors", "archive"), each starting from a known state.
Name each request's `step` after the step that answers it (`notes.1.2`), so differences point at
English. Put files in `scenarios/` and list their names in ladder.json `compare.runs`.

## 2. Make runs repeatable

- A fresh test database per run, seeded the same way (for SQL Server, a container or a disposable
  database; avoid substituting SQLite, whose case sensitivity, types and ordering differ).
- **Before starting a real API, find everything it touches:** every connection string and outbound
  URL (report databases, devices, payment or e-commerce services), hosted background services, startup
  seeders that write, and caches outside the database (Redis). Point each at a test instance or turn it
  off, and reset caches together with the database in the `--before-each` command.
- **Counting SQL per request:** EF Core logs commands only if the DbContext is built with the app's
  logger, which many apps don't do. A SQL Server Extended Events session on the test server (filtered
  to the test database) counts reliably without touching the code.
- A fixed clock where the code allows it, otherwise `--mask` the time fields.
- `--mask` ids that the database assigns if two builds might assign them differently.
- Test credentials only; never point replay at production.
- Seams between trees: when a client tree `calls:` the API tree, also write one test that runs the
  real client code against the running API (a success, a failure, each error the client handles)
  and put it in the link's `"test"` in ladder.json. Replaying the API alone can't see what the
  client's HTTP layer does with an answer. A client that can talk to a real host (its default may be
  production) gets a guard in that test: replace `fetch` before the client loads with one that refuses
  every URL outside the test API, and fail at once when the test API's URL is missing.
- One runner script per repository (reset the test data, start the API on 127.0.0.1, run one test file
  of a given app, stop the API), taking the app folder, the reset command and the port as arguments, so
  every area's link and behaviour tests use it rather than a copy.
- A consumer that compiles against a built package (an app importing a library's `dist`) does not see a
  regenerated library until the package is built again: build it before the consumer's check and tests
  (in its `check_command` or the runner), or a regenerated library goes untested by its callers.
- The slice's own tests (the existing unit tests for those files, and behaviour tests you write for the
  states the English describes) go in ladder.json `"tests"`, so `ladder test` runs and records them and
  `check` sees when the code changed after they ran. A generated build that compiles can still use the
  wrong library or answer `undefined` for `null`; in the trials only these tests caught it. Include the
  repository's own guards on what the slice touches: a committed API contract (OpenAPI) snapshot, generated
  client types. In round 10 a change made through the English four rounds earlier had altered an API type
  without updating the committed contract, and nothing in Ladder noticed.

## 3. Record traces

- **Services (any build, including existing code):** start the build, then
  `ladder replay scenarios --base <url> --out traces/<build> [--mask id,updatedUtc] [--header "Authorization: Bearer ..."]`.
  For sign-in flows: passwords come from the environment (`{{env:TEST_PASSWORD}}`), a request can
  `"save"` a value (`{"token": "body.accessToken"}`) for later ones (`{{var:token}}`), cookies are
  kept per scenario like a browser, `--record-headers set-cookie,location` records them (cookie
  values hidden, attributes compared), `--jwt` replaces tokens by their claims (lifetime instead of
  timestamps) so two runs compare, and `"wait": 31` sleeps before a request for time windows
  (`{"wait": 31}` alone is a pause). Mask by kind: `--mask traceId,refreshToken:presence,expiresAt:time`
  hides `traceId`, keeps whether `refreshToken` is null or set, and compares `expiresAt` as "now+120m".
  `--observe "<command>"` runs after each request and compares what it prints (a SQL command count
  from an Extended Events session, a queue length), so a build that answers the same with ten times
  the queries shows up.
- **Logic with in-code tracing** (builds that wrap steps with the Ladder runtime): run the project's
  scenario runner so each build writes `traces/<build>/<scenario>.jsonl`.
- **Client logic that is not traced inside** (adopted React or React Native hooks and API clients):
  write a small test (Vitest, Jest) per scenario that replaces the network with recorded API
  responses, calls the logic's functions in order, and wraps each call with the runtime's
  `step("<id>", fn)` from `${CLAUDE_PLUGIN_ROOT}/tool/runtimes/typescript/ladder_runtime.ts`; at the end
  it writes `traceEvents()` as JSON lines to `traces/<build>/<scenario>.jsonl`. Run the same test
  against web's and mobile's code to compare the two apps; differences here are the DIFFERS notes
  becoming visible. Hooks, reducers and anything React calls during render use `stepSync` (so tracing
  doesn't make them async) or `log(step, data)`. For rendering, `tool/runtimes/typescript/ladder_react.tsx`
  has `useRenderProbe` / `RenderProbe` (render counts and object identity per render), `TraceBoundary`
  (records render-time throws), `captureConsole` (console output as behavior) and `strict()` (StrictMode);
  the runtime's `identity()` labels objects `#1`, `#2` so "same list" vs "new list" compares, and
  `seedRandom()` makes `Math.random` and `crypto.randomUUID` repeatable.
- **One harness, several per-file builds:** when one harness exercises files that are separate builds,
  record one trace folder (say `traces/original`) and give each build `"traces": "original"` instead of
  copying or linking folders.
- **Mutants and old rounds:** add each as a build with `"tagged": false, "mutant": true` and its own
  `"traces"`; `check` then requires each mutant to differ somewhere ("NOT CAUGHT" is a problem) instead of
  reporting the differences as failures. `ladder check <ladder.json> --builds=a,b` compares only those
  builds with the reference. Harness-only trace names (`input`, `harness`) go in `compare.extra_steps`;
  any other name not in the tree is reported, which catches a mistyped step id.

- **Libraries (no HTTP boundary):** a project's own test suite is a floor, not a comparison: in the
  p-queue trial, two regenerated builds passed all 209 tests while one of them still changed when a
  promise rejected, and a one-character mutation (`===` to `>=`) passed all 209 too. Add a
  *differential* run: a seeded generator of random sequences of public calls, run under fake time,
  logging every event, result and state, compared line by line between the reference and each build.
  `references/differential.md` has the pattern. It caught every mutation tried in that trial. Write
each run as a Ladder trace, so `ladder check` compares it with the step names and `compare:` lines.
Builds that exist only to be compared (the original before laddering, a mutant) get `"tagged": false`.

- **New behavior with no reference:** there is nothing to compare against, so use two things.
  Acceptance tests written from the English alone by someone who hasn't seen the code (each test
  named after the step it checks), and several independent generations of the build compared with
  each other by the differential run: in the cockatiel trial three regenerations agreed in 600 of
  600 runs and passed all 49 acceptance tests. Agreement alone isn't proof: generations from the
  same model share defaults, so the acceptance tests are what anchor the behavior to the English.
- **Boundaries need targeted scenarios.** Random runs rarely land exactly on a limit (a delay that
  has *just* elapsed, a count *exactly* at the threshold). In the cockatiel trial a `<` changed to `<=`
  on the half-open delay passed 600 random runs; the existing tests caught it. Add scenarios at each
  limit and one past it alongside the random ones.

For an adopted system, record the existing build's traces *before* regenerating anything. They are
the reference that later builds must match. Record it twice and add the second run as a build
(`{"name": "original-2", "tagged": false, ...}`): identical runs show the scenarios and masks are
deterministic. Every recording you want compared must be a build: tagged builds that share the
reference's traces compare nothing, and `check` says "nothing was compared" and warns `traces-unused`
for a folder no build names.

Masks: a value the response carries twice (an incident id, and the same number inside its message)
needs both a key mask and, for short values, a `--mask-text` pattern; text masks also apply when
comparing, so adding one to a newer recording covers the older ones.

## 4. Compare and explain

`ladder check <ladder.json>` compares each build with the reference on every run. For every step
it prints how many results were identical and every result that differs (its position, the request
it answered for replayed traces, and both values; the first 10 per step, all with
`--all-differences`). Run `ladder test <ladder.json>` too: it runs the vocabulary's `test:` lines and
the links' seam tests, and `check` reports failed ones. Exit codes: 0 all good, 1 problems, 3 only
waiting for a person's approval. For each difference, decide which kind it is, because each has a different fix:

| Difference | Fix |
|---|---|
| Generated code doesn't do what the English says | `ladder repair` or regenerate (ladder-generate) |
| The intended change (the English was changed and stamped) | record the approved code as a build, then `ladder reference <ladder.json> --from=<build>`; the old reference moves to `traces/history/`. Re-record the other builds from the approved code (`original-2`); retire recordings whose code is gone (an earlier scratch copy) with `--retire=A,B` |
| The English allows both behaviors | tighten the English (ladder-write), then regenerate |
| The reference itself is surprising | a `note: QUESTION:` for the person; don't copy or fix silently |
| Library or environment difference (versions, decoder, collation) | pin it or record it in the vocabulary (`known:`); set `number_tolerance` only for real numeric noise |
| A real difference nobody can rely on (generated ids, the order of a set, timing within one tick) | propose a `compare:` line on that step (ladder-write); the person approves it |

A `compare:` line is how the English says "this difference doesn't matter". It never changes code,
but it does make a comparison pass, so it is the person's decision: propose it with the evidence
(the differing values and why no caller can depend on them), and in an unattended run add it with a
`note: DECISION:` and list it. Never add one just to make a failing comparison go green.
For libraries and event-driven code, set `"order": "strict"` in `compare`: per-step comparison alone
misses results that arrive in a different order (in the p-queue trial it missed the only real
difference the spec-built version had).

Read the actual values, not only the pass/fail. Run a quick mutation check now and then: change one
constant or comparison in a generated region, confirm the comparison catches it, and change it back.
After an English change, check *locality* too: every difference between the old and new build should
be explained by the change (in the p-queue trial, all 119 changed runs were runs that called `clear()`). A comparison
that never fails proves nothing.

## 5. Prepare the review

Run `ladder view <ladder.json>` to build the side-by-side page (English, code by step, traces,
comparison table) and give it to the person. Approval is theirs: after they have read the English,
the generated code and the comparison, they run (or ask you to run) `ladder stamp <ladder.json>`.
Don't stamp on your own initiative.

## Hand back

Scenarios written, builds run, the comparison result per scenario, each difference with its
classification and recommended fix, the mutation check if you did one, and where the viewer page is.

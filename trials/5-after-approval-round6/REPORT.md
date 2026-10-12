# Ladder round 6 report: after approval, on the timeclock slice

2026-10-12 · for Ben · qbs branch `ladder-trial-r6` in `~/code/qbs-ladder-trial` (push disabled) · plugin
v0.5.3 (ladder 26107fe), installed in the session this time.

**Nothing was stamped.** Ben's direction during the round: "the goal of all this is to harden ladder. theres
no need to stamp. find friction. find problems." The two stamp stops became v0.5.3's `"baseline"`:
- `61b231cbd8` for the first approval;
- `79304322d0` for the second, by moving the baseline.

`check` treats a baseline as the approved state, so every flag below came from it, not from `--since`. The
real lock path (`ladder stamp`, then `check`) is still untested.

Short version: the after-approval cycle works on a second slice, and the round found 23 problems
(section 5).
- **Flags across the trees.** An API change flagged its caller in the library, the scanner steps that call
  that library step (indirectly), and `has-callers` on the API side.
- **The link test caught the change.** The old link test failed against the regenerated API, with clear
  assertion lines.
- **The required column.** It flagged only the step that INSERTs: not the update-only step, and not the
  readers.
- **Clean after the second approval.** Moving the baseline left `check` clean on both projects.

Most of the 21 are small. The serious ones:
- the documented `{{now+90m}}` doesn't work (F4);
- masks can't hide a time inside text, so a response that embeds a time is never repeatable (F10);
- a client type outside the slice silently drifts from the API's request (F14);
- switching schema exporters raises six false `schema-changed` (F17).

## 1. Slice

| Tree | Files | Steps |
| --- | --- | --- |
| API (`ladder/timeclock/api`) | `TimeclockController.cs`, `TimeclockService.cs` (whole files), 6 DTO files (contract regions), `Dbo_Timeclock.cs` (support only) | `tc.1` (4 endpoints), `tcs.1` (8 members); 8 data blocks |
| Clients (`ladder/timeclock/clients`) | library `timeclock-service.ts` (whole), scanner `src/lib/api.ts` (8 functions; the rest `@support`) | `tcl.1` (4 calls, each `calls: api [...]`), `scn.1`–`scn.8` (name the `tcl` steps) |

- **One clients project with two builds**, not a third project for the scanner. The scanner functions name the
  library steps (`clocks in with [tcl.1.2]`), which is what v0.5.2's indirect `linked-changed` follows.
- **Shared with auth:** the vocabulary and its capability tests, the HTTP runner (`with_api.sh`), the probe,
  the containers and the schema JSON. Timeclock got its own C# and TypeScript profiles: auth's `csharp.md` is
  full of auth names (F3).
- **Found while transcribing** (QUESTION notes):
  - a failed clock-in or clock-out answers `400 {"message": "result", "details": "<class name>"}`, so the reason
    never reaches a client;
  - an open row of any type blocks clocking in, so the scanner's lunch and break can never start;
  - the scanner's timeclock functions have no callers: the clock buttons' `HomeScreen` is only rendered in
    tests;
  - any signed-in caller can clock any employee in or out.

## 2. Numbers

| Measure | Round 5 | Round 6 |
| --- | --- | --- |
| `linked-changed` from the approved state (no `--since`), of the steps that call the changed API step | 1 / 1 with `--since` | **1 / 1** (`[tcl.1.2]`), from the baseline |
| Indirect callers flagged (the scanner wrapper) | not flagged | **yes**: `[scn.2]`, `[scn.5]`, `[scn.6]` (the three that clock in); `[scn.3]` (clock-out) correctly not. Also the parent `[tcl.1]`, a false alarm (F9) |
| `has-callers` shown on the API side | never (needs a stamp) | **yes**, from the baseline |
| Required column: INSERT step flagged; UPDATE-only step flagged; read-only steps flagged | INSERT n/a; UPDATE flagged (false alarm) | **yes; no; no** (`writes: Dbo_Timeclock (updates only)` on clock-out). An optional column flagged nothing |
| `check` clean after the second approval (baseline moved) | n/a | **yes**, exit 0 on both projects (after rerunning `ladder test`, see F20) |
| Timeclock: replay of the original repeatable (two recordings, masks, SQL counts) | auth: yes | **yes, 21 / 21**. After change (a), 1 request is never repeatable (F10) |
| Timeclock: link test passes after change (a), both sides regenerated | auth: 3 / 3 | **5 / 5**. Before the client side was updated, the old link test **failed** against the regenerated API, with `expected 409 to be 400` |
| Capabilities with a `test:` line, of those with `known:` lines (timeclock) | auth: 5 / 7 | **2 / 2** (HTTP client, and the new `clock rows`, whose test also caught F16) |

Other numbers:
- **Transcription:** adopt-check ok on 11 files.
- **Regeneration** (normal `regen`, in scratch):
  - change (a): the controller (1 region) and the library (1 region, a doc comment only);
  - change (b): 6 DTO contract regions (5 of them no-ops, F12), the service (1 region) and the scanner
    (1 region).
  - Every result built and typechecked, with 0 repair rounds.
- **Filtered qbs timeclock tests:**
  - 9 / 9 after change (a);
  - after change (b), **7 of 9 fail** on the regenerated code, and 8 of 9 on the original.
  - Every failure is `NOT NULL constraint failed: TIMECLOCK.SOURCE`: the tests' own seeders insert timeclock
    rows without the new required column. Adding the database's default to the EF model
    (`HasDefaultValue("unknown")`) didn't change that; I stopped there, since it's EF and test setup, not Ladder.
  - Ladder warned about none of it (F23).
- **Replay vs the original:**
  - after change (a): 18 / 21, the 3 intended refusals;
  - after change (b): the same 3, plus the new scenario. The unchanged code, run against the new required
    column, fails every clock-in (6 differences, `original-b`). That's the break `schema-changed` predicted.
- **Database:** after change (b), `SOURCE` holds "scanner" when the client sends it and "unknown" otherwise.

## 3. The messages, as printed

After change (a), API English only, before touching the clients:

```
linked-changed  [tcl.1.2] calls api:tc.1.1, whose contract changed since 61b231cbd8: was out: 200 with ClockInResponse; 400 with ValidationError; 500 with `success` and `message`; now out: 200 with ClockInResponse; 409 with ValidationError when already clocked in; 400 with ValidationError for other refusals; 500 with `success` and `message`; re-read this step (and the code that handles the answer), then approve
linked-changed  [tcl.1] is its parent, which is affected by a change in another tree (it calls api:tc.1.1); re-read this step too, then approve
linked-changed  [scn.2] refers to [tcl.1.2], which is affected by a change in another tree (it calls api:tc.1.1); re-read this step too, then approve
linked-changed  [scn.5] refers to [tcl.1.2], which is affected by a change in another tree (it calls api:tc.1.1); re-read this step too, then approve
linked-changed  [scn.6] refers to [tcl.1.2], which is affected by a change in another tree (it calls api:tc.1.1); re-read this step too, then approve
test-stale      [link api] what it tests changed since it last ran (2026-10-12); run `ladder test`
has-callers     [tc.1.1] its contract changed since 61b231cbd8, and it is called by clients [tcl.1.2]: that step shows as linked-changed until re-read and approved; update its English in the same change, or tell whoever owns it
```

The regenerated API, before the client English changed:

```
test-failed     [link api] failed when last run (2026-10-12): → expected 409 to be 400 // Object.is equality / → expected 'INVALID_CLOCK_TYPE' to be 'OPERATION_ERROR' // Object.is equality / FAIL  src/__ladder__/link.test.ts > timeclock, library to API > already clocked in: the API refuses with 400 OPERATION_ERROR and the message "result" / AssertionError: expected 409 to be 400 ...
```

The required column, before any English:

```
schema-changed  [tcs.1.1] the schema it refers to changed since 61b231cbd8 (qbs:Dbo_Timeclock.Source added, column SOURCE, varchar(20), required, max 20 (inserts must now set it; if this step only updates rows, write `writes: Dbo_Timeclock (updates only)`)); re-read the step, then regenerate its code with --redo
```

All of these told me what to do, except:
- the parent `[tcl.1]` (nothing to re-read: it's the class declaration);
- the data-block part of `[tcl.1.2]`'s message after change (b), which appears only as a trailing
  `| source: optional text, the app that clocks in (...)`, without saying it's a new field of the request body
  (F13).

## 4. Auth, unchanged, under v0.5.3

Run with `check --since=2f58c53fb3` (round 5's last commit) and `ladder test`:

- **New:** 6 `schema-changed` on auth steps, all for `Employee_Role.Id: ... required -> ... required,
  generated by the database`. Nothing in the database changed. The plugin's exporter records `generated` and
  round 4's didn't, so switching exporters flags every step that names the member (F17).
- **New:** `test-stale` on all 4 C# capability tests and on the HTTP client and link tests.
  - The C# ones are correct: they share the probe, whose source changed this round (F16).
  - The HTTP client and link ones are a one-time upgrade cost: v0.5.2 put the test's files into its hash.
- **Same as before:** `untested-capability` for console warning and session store, which do have `known:`
  lines.
- **Changed:** all 31 API steps and 29 client steps show as `new`. `--since` reviews schema and link changes
  only, unlike `baseline` (F18).
- **The auth link test now fails:** `expected undefined to be 401`. That's correct. Its missing-permission case
  asserts round 5's change (a), which was only ever regenerated in scratch; auth's working files still hold the
  original code and are marked stale.

## 5. Friction and problems, in the order I hit them

- **F1 (slice) Dead client code.** The scanner's timeclock functions have no callers in the app. I kept them, since
  the code is throwaway, but "the scanner shows the message" in change (a) had nothing to attach to. Not a Ladder
  problem.
- **F2 (setup) Times relative to the host.** The API compares with `DateTime.Today` (host local time) while the
  container's `getdate()` is UTC. The timeclock seed takes the host's local time from the reset script. Not a
  Ladder problem.
- **F3 (profile) Profiles carry slice-specific names.** Auth's `csharp.md` is half general rules and half auth's
  names, so a second slice needs its own copy of the general half. Suggestion: allow several convention files per
  build, a shared general one plus one per slice, and say so in the profile skill. (A build already takes a
  list; the skill doesn't suggest splitting.)
- **F4 (replay) `{{now+90m}}`, the documented form, isn't substituted.** The pattern needs a colon:
  `{{now:+90m}}` works. The skill (`scenarios.md`), the format reference and the docstring all show
  `{{now+30s}}`. The API got the literal text and answered 400, which looks like an API bug.
- **F5 (replay) The `time` mask reads times without a zone as UTC.** The API sends local times without an offset,
  so "2 hours ago" records as `now-420m`. It's consistent between runs, so it compares, but it's misleading.
  Suggestion: `time:local`, or treat zone-less times as the machine's local time.
- **F6 (env) A symlinked `node_modules` isn't ignored.** `.gitignore`'s `**/node_modules/` doesn't match it, so I
  added a local exclude. Not a Ladder problem.
- **F7 (env) The scanner typechecks against the main checkout's library build.** It resolves
  `qbs-library-react` through a symlinked `node_modules`, so a regenerated library type would not be seen by
  the scanner's typecheck. It didn't matter this round, because the library's types didn't change.
- **F8 (design) Change (a) needed a compromise.** Keeping the edit inside `[tc.1.1]` meant the controller tells
  the two refusals apart by the answer's `timeclockId` and a message prefix. A cleaner change would add a `code`
  to the service's answer, but that changes a DTO and both trees. Not a Ladder problem.
- **F9 (links) The parent is flagged as an indirect caller.** `[tcl.1]` is flagged because its child `[tcl.1.2]`
  is affected. It's the class declaration and constructor, with nothing to re-read. Suggestion: follow `[id]`
  references and `calls:`, not the parent relation, or only flag a parent whose own text names the child.
- **F10 (replay) Masks can't reach a time inside text.**
  - The new 409's message is "Already clocked in since 10:55", with the time in `details` too, so the request
    differs on every run.
  - `--mask` works by key: masking `message` would hide the thing under test, and `details:time` would cover
    only the field.
  - Suggestion: pattern masks, for example `--mask-text '\d\d:\d\d=<hh:mm>'`.
- **F11 (regen) A wording-only change forces a regeneration.** Clarifying `[tcl.1.2]`'s English (no behavior
  change) made it stale. Regeneration added only a doc comment. That's cheap, but Ladder can't tell; `retag`
  exists, but you have to know to use it.
- **F12 (contracts) One data block marks every contract region stale.** Adding a field to `ClockInRequest` marked
  all 6 DTO files' contract regions stale, because the contract hash is per build. Regeneration rewrote all 6 with
  an LLM call each, and 5 came back identical. Suggestion: hash each `@contract` region from the data blocks it
  spells out.
- **F13 (links) A data-block change reads as a trailing fragment.** After change (b), `[tcl.1.2]`'s
  `linked-changed` ends with `| source: optional text, the app that clocks in ("scanner", "dashboard")`, without
  saying that `ClockInRequest`, the request body of `[tc.1.1]`, gained it.
- **F14 (seam, types) A client type outside the slice drifts silently.**
  - The scanner now sends `source: 'scanner'`, but the library's `ClockInRequestDTO` (in `reads`, never generated)
    has no `source`. Ladder had no way to say the client type no longer matches the API's request block.
  - The generator made it compile with an intersection type: `Parameters<typeof timeclockService.clockIn>[0] & { source: 'scanner' }`.
  - The honest fix is a build for `dtos/time-clock.ts`, with data blocks matching the API's. Suggestion: when a
    linked step's data block changes, warn about client files in `reads` that declare the same type.
- **F15 (support) Hand edits to support code aren't tracked before a stamp.** I added two properties to the entity
  class, in a support-only build, and `check` said nothing. Without a stamp there's no recorded code to compare
  with, and the baseline doesn't record code. Probably fine: support code is hand-written by definition.
- **F16 (tests) A schema change broke a capability test, and the message hid why.**
  - The `clock rows` probe inserts a row. The new required column made it fail, which is good, but the
    `test-failed` line showed `DbUpdateException ... Error Number:515` and not "Cannot insert the value NULL into
    column 'SOURCE'".
  - My v0.5.1 failure filter matches `Exception:`, not `SqlException (0x80131904):`.
  - Also, a capability test isn't marked stale by a schema change to the tables it touches.
- **F17 (schema) Changing exporter raises false `schema-changed`.** On auth, 6 steps were flagged when only the
  exporter changed: `generated by the database` appeared on `Employee_Role.Id`. Suggestion: a schema file records
  its exporter and version, and `check` says "the exporter changed" instead of flagging steps; or ignore facts
  the old export didn't carry.
- **F18 (check) `--since` and `baseline` review different things.** `--since=REF` compares the schema and links
  with REF, but the step review still shows every step as `new`, while `"baseline"` covers all three. It's
  surprising that the flag does less than the setting.
- **F19 (tests) One-time `test-stale` after upgrading to v0.5.2.** Expected, since the test's files joined the
  hash, but nothing says "stale because Ladder changed how it hashes".
- **F20 (my mistake, a tool gap) Nothing protects the reference traces.**
  - I re-recorded `traces/original` while the database had the new required column, so the "original" became the
    broken build. I restored it from git.
  - Also, checking the ladder folder out into scratch overwrote its `ladder.code.json` test results, so a correct
    project showed `test-stale` until I reran `ladder test`.
  - Suggestion: `ladder replay --out` refuses to overwrite the `compare.reference` trace folder without `--force`.
- **F21 (labels) A build with data blocks is labelled "support only".** The `dtos` build has `"steps": []` and 7
  data blocks with `@contract` regions, and `check` calls it "support only (...): implements no steps". True, but
  it generates contract regions; "contract only" would be clearer.

- **F22 (exporter) The plugin's exporter ignores column defaults.** It sets `generated` only for
  database-generated primary keys
  (`p.ValueGenerated == OnAdd && p.IsPrimaryKey() && not Guid`). So `SOURCE`, required but defaulted in both the
  database and the EF model (`HasDefaultValue("unknown")`), is still reported as "required", and `check` still
  says "inserts must now set it". Suggestion: export `default` (from `GetDefaultValue` /
  `GetDefaultValueSql`), and don't flag inserts for a required column that has one.
- **F23 (schema) Ladder warns about steps, not about everything else that writes the table.** The required column
  broke 7–8 existing qbs timeclock tests: their seeders insert rows without it. `schema-changed` flagged the one
  step that inserts; the tests, the seeders and any other code outside the slice that writes `dbo.TIMECLOCK` are
  invisible to Ladder. Suggestion: on a new required column, list the files in the repository that construct the
  entity (a cheap grep for `new Dbo_Timeclock` or `.Dbo_Timeclock.Add`), even outside the slice.

No `REFUSED` or `REJECTED` messages. I wanted no hand edits to generated code. I hand-edited only support code
(the entity) and trial harness files: the link test's two refusal cases, and the probe's insert after the schema
change. Each is noted in a commit and in its file.

## 6. Steps awaiting approval

Nothing is stamped; the baseline is `79304322d0` in scratch, `61b231cbd8` on the branch.

- **Timeclock API:** `[tc.1.1]` (change (a)), `[tcs.1.1]` (change (b)), data block `ClockInRequest` (`source`).
  The rest is as transcribed: `tc.1`–`tc.1.4`, `tcs.1`–`tcs.1.8`, and 7 other data blocks.
- **Timeclock clients:** `[tcl.1.2]` (reworded for change (a)), `[scn.2]` (sends `source`); the rest as
  transcribed.
- **Vocabulary:** capability `clock rows` (new, tested).
- **Migrations (trial only):** `ladder/timeclock/api/migrations/20261012_AddTimeclockSource.sql` (required, with a
  default for old rows) and `20261012_AddTimeclockDeviceNote.sql` (optional). The EF model also has
  `HasDefaultValue("unknown")` for `Source`.
- **Auth:** unchanged since round 5.

## 7. Files (qbs repo, branch `ladder-trial-r6`, local only)

- `ladder/timeclock/`:
  - `api/timeclock.ladder`, `api/ladder.json` (baseline, links, schemas);
  - `api/env/` (reset, host-relative seed), `api/harness/record.sh`, `api/scenarios/s01`–`s03`;
  - `api/traces/{original,original-b,regen-a,regen-b}`, `api/migrations/`.
- `ladder/timeclock/clients/`:
  - `timeclock-clients.ladder`, `ladder.json`;
  - `harness/link.test.ts`, `harness/typecheck.sh`.
- `ladder/timeclock/conventions/{csharp,typescript}.md`.
- `ladder/timeclock/trial/`: `tag_timeclock.py`, `gen/a`, `gen/b` (regenerated files with prompts and replies).
- `ladder/auth/`: the vocabulary (`clock rows`), the probe (`clock-rows` case), and the schema JSON (plugin
  exporter, plus `SOURCE` and `DEVICE_NOTE`).
- **Still running or on disk:**
  - the trial containers; the trial database now has `SOURCE` and `DEVICE_NOTE` on `dbo.TIMECLOCK`;
  - the scratch worktree `~/code/qbs-ladder-r6-scratch`, which holds the regenerated code with both changes.

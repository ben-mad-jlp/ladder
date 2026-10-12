# Ladder round 6 handoff: after approval, on a second slice

2026-10-12 · from Ben (drafted by Claude for Ben to edit)

## Goal

Rounds 4 and 5 ran entirely without a stamp, because approval is Ben's. Round 6 tests what day-to-day
use looks like:
1. Ben approves the trees.
2. Changes come in.
3. Ladder flags them from the lock, without `--since`.
4. A second approval clears them.

It also runs on a second slice, the timeclock, to see whether what worked on auth holds elsewhere.

The code is throwaway, as in rounds 4 and 5: judge every result by what it says about Ladder.

Round 5 (`../4-seam-round5/REPORT.md`) and v0.5.1 left these to measure here:

- `has-callers`, `linked-changed` and `schema-changed` from a real stamp. Round 5 saw `has-callers` never.
- The v0.5.1 fixes in normal use:
  - `calls:` no longer makes code stale;
  - capability tests are scoped per project;
  - `untested-capability` fires only when there are `known:` lines;
  - `test-failed` shows the assertion;
  - the EF exporter's `LadderTargetFramework` and `--ctor-arg`.
- F14 from round 5: a new required column should flag a step that INSERTs, and the round 5 report asks
  whether it also flags one that only UPDATEs.

## The slice: timeclock

| File | Lines | In the slice |
| --- | --- | --- |
| `qbs_api/qb_api/Controllers/Employees/TimeclockController.cs` | 123 | all: clock-in, clock-out, status, all |
| `qbs_api/qb_api_services/Employees/TimeclockService.cs` | 336 | all |
| `qbs_api/qb_api_dtos/` timeclock DTOs | | the request and response classes the four endpoints use |
| `qbs_library_react/src/system/monitoring/services/timeclock-service.ts` | 72 | all |
| `qbs_scanner_react/src/lib/api.ts` | | only `clockIn`, `clockOut` and the status wrapper; the rest `@support` |

Database:
- Clock-in INSERTs a `Dbo_Timeclock` row (`dbo.TIMECLOCK`).
- Clock-out UPDATEs that row.
- Both read `Employee_MainTable`, which the auth trees also refer to.

Three trees:
- the API tree under `ladder/timeclock/api`;
- the library tree under `ladder/timeclock/clients`;
- the scanner's wrapper, either as a third project or as a second build of the clients project. Your
  choice; say which and why.

Today's behavior worth knowing before transcribing: when clock-in fails ("Already clocked in since 07:05",
or an invalid clock type), the service builds a clear message, but the controller answers
`400 {"message": "result", "code": "OPERATION_ERROR", "details": "<the response class name>"}`, so the
message never reaches the scanner. Transcribe that as it is, with a QUESTION; change (a) fixes it.

## Ground rules

As in round 5:
- **Test database and test users only.** Never point anything at production or a shared service.
- **Secrets come from the environment.** They never go into git, traces, logs or the report.
- **Approval is Ben's.** The agent never runs `ladder stamp`. The phases below stop twice for Ben
  to stamp; wait for him, then go on.
- **No hand edits to generated code.** Change the English and regenerate, or use `ladder repair`.
  If a fix can only be made by hand, stop and report it as friction.
- **Don't edit qbs tests** to make them pass. Trial harness files are yours; say when you change one.
- **Work on a branch with push disabled** in the qbs repo. Regeneration happens in a scratch copy, never
  over the working files.
- **Migrations:** allowed on the trial database only.

## Phases

Each phase ends with `ladder check` on every project and a line in the report.

0. **Set up.**
    - Plugin v0.5.1 or later (`claude plugin marketplace update ladder`, then
      `claude plugin install ladder@ladder`); note the commit. If you can't install from inside the session,
      run the tool from a clone and say so.
    - Branch `ladder-trial-r6` from `ladder-trial-r5`, push disabled.
    - Recreate the trial containers if needed (`ladder/auth/api/env/containers.sh`), and seed timeclock test
      data for the five test employees: one clocked in, one clocked out, one with no rows.
1. **Transcribe the timeclock slice.**
    - Point `"schemas"` at the same JSON exports as auth. Re-export with the plugin's exporter:
      `-p:LadderTargetFramework=net9.0`, and `--ctor-arg year=2025` for the two archive contexts.
      Record any difference from round 5's files.
    - Write the English with `reads:` / `writes:` and `[[...]]`.
    - Link the trees with `calls:` and `"links"` both ways.
    - Give the timeclock's capabilities with `known:` lines a `test:`.
    - Write a link test: the library's real `TimeclockService` against the running API: clock in,
      already clocked in, invalid type, clock out, status.
    - Write replay scenarios and record the original twice with
      `--mask ...:time --observe env/sqlcount.sh`. The times the client sends must be fixed in the
      scenario, or relative (`{{now}}`).
    - Run `ladder test` on every project.
    - Retag the auth `[authsvc.1]` once if v0.5.1 shows it stale (the upgrade note in PR #3), and record it.
2. **Stop: Ben stamps** the auth trees (`ladder/auth/api`, `ladder/auth/clients`) and the timeclock trees.
   List in the report exactly what he approved (commit and projects). After the stamp, `check` on every
   project should be clean except for warnings you can explain. Record each remaining warning.
3. **Change (a), across the trees, with no `--since`.**
    - Edit only the API English: a failed clock-in answers 409 for "already clocked in" (`code`
      `ALREADY_CLOCKED_IN`, the clock-in time) and 400 for an invalid clock type (`code`
      `INVALID_CLOCK_TYPE`), each with the service's message.
    - Run `check` on every project before touching the client English. Record:
      - whether every calling step shows `linked-changed`, including the scanner's wrapper, which calls
        the library rather than the API;
      - whether the API shows `has-callers`, and the exact text of both.
    - Then update the client English: the library passes the code and message through (the HTTP client
      keeps a 400's and a 409's message; `known:` line); the scanner shows the message.
    - Regenerate both sides (normal `regen`, in scratch).
    - Run `ladder test` and replay.
4. **Change (b), the schema, with no `--since`.**
    - Add a required column that clock-in must now set (for example `source`, the app that clocked in:
      `scanner` or `dashboard`), with its migration on the trial database.
    - Re-export, then `check`. Record:
      - that the clock-in step (INSERT) is flagged `schema-changed`;
      - whether the clock-out step (UPDATE only) is flagged too (round 5's F14);
      - that no read-only step is flagged.
    - Then write the English for the new column, regenerate, replay, and confirm the column is written.
    - Also add an optional column and confirm nothing is flagged.
5. **Stop: Ben approves again.**
    - Before he does, list in the report everything `check` shows. He reviews the changed steps, then
      stamps.
    - After the stamp, `check` must be clean of `linked-changed`, `has-callers`, `schema-changed` and
      `edited`. Record anything left.
6. **Auth, unchanged since the stamp.** Run `check` and `ladder test` on both auth projects with v0.5.1.
   Record any warning that wasn't there in round 5 and any that disappeared.
7. **Report.** Leave everything awaiting Ben's next approval; do not stamp.

## Decisions for Ben before the round starts

- **Indirect callers (round 5's F9).** Should `check` flag a step that calls a `linked-changed` step in its own
  tree (the scanner's wrapper calling the library's `clockIn`)?
  - If yes, v0.5.2 needs that before round 6.
  - If no, round 6 records what happens and leaves it to the link test.
- **What to stamp in phase 2.** The auth trees as they stand after round 5 (their working files are stale by
  design: the regenerated code is only in scratch), or only the timeclock trees. Stamping auth tests
  `has-callers` on a tree with history; stamping only timeclock keeps the round small.

## What to report

Write `REPORT.md` in this folder (`trials/5-after-approval-round6/`) on a branch
`trial/5-after-approval-round6`, and open a pull request.

| Measure | Round 5 | Round 6 |
| --- | --- | --- |
| `linked-changed` from the lock (no `--since`), of the steps that call the changed API step | 1 / 1 with `--since` | |
| Indirect callers flagged (the scanner wrapper) | not flagged | |
| `has-callers` shown on the API side | never (needs a stamp) | |
| Required column: INSERT step flagged; UPDATE-only step flagged; read-only steps flagged | INSERT n/a; UPDATE flagged (false alarm) | |
| `check` clean after the second stamp | n/a | |
| Timeclock: replay of the original repeatable (two recordings, masks, SQL counts) | auth: yes | |
| Timeclock: link test passes after change (a), both sides regenerated | auth: 3 / 3 | |
| Capabilities with a `test:` line, of those with `known:` lines (timeclock) | auth: 5 / 7 | |

Also include:

- **The messages themselves**: paste each `linked-changed`, `has-callers`, `schema-changed`, `edited` and
  `test-*` line exactly as `check` printed it, and say whether it told you what to do.
- **False alarms** and warnings you'd turn off.
- **Friction**, in the order you hit it, with every workaround and `REFUSED` message.
- **Anything about the timeclock slice that auth didn't show**: things that worked on auth and didn't
  here, and the reverse.
- **Steps awaiting approval**, listed for Ben.

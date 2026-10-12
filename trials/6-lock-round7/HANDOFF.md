# Ladder round 7 handoff: v0.6.0 fixes, and the real lock

2026-10-12 · from Ben (drafted by Claude; Ben: "draft the handoff and get it done")

## Goal

Two things, on the timeclock slice from round 6 (`../5-after-approval-round6/REPORT.md`):

1. **Confirm v0.6.0's fixes for round 6's 23 problems,** each against the case that found it.
2. **Exercise the real lock.** No round has run `ladder stamp` yet: rounds 4 to 6 used `--since` or
   `"baseline"`. This round stamps the timeclock trees, makes changes, and checks that every flag comes from
   `ladder.lock.json`:
   - `edited`, `linked-changed`, `has-callers`, `schema-changed`;
   - hand-edit detection on generated code;
   - `test-stale`.

   Then it stamps again and checks that the flags clear.

The code is throwaway: judge every result by what it says about Ladder.

## Ground rules

- **Test database and test users only.** Never point anything at production or a shared service.
- **Secrets come from the environment.** They never go into git, traces, logs or the report.
- **Stamping is allowed in this round,** in the trial branch only, because the lock is what's being tested
  (Ben, 2026-10-12). Stamp only where a phase says so.
- **No hand edits to generated code,** except the one deliberate hand edit in phase 4. Change the English and
  regenerate, or use `ladder repair`.
- **Don't edit qbs tests.** Trial harness files are yours; say when you change one.
- **Work on a branch with push disabled** in the qbs repo (`ladder-trial-r7` from `ladder-trial-r6`).
  Regeneration happens in a scratch copy.
- **Migrations:** allowed on the trial database only.

## Phases

Each phase ends with `ladder check` on every timeclock project and a line in the report.

0. **Set up.**
    - Plugin v0.6.0 (ladder 97b3fe9): installed, or run from a clone by path. Say which.
    - Branch `ladder-trial-r7` from `ladder-trial-r6`. Start the trial containers if they're stopped.
1. **Re-check round 6's 23 problems on v0.6.0.** For each F1 to F23, rerun the case that found it and record
   fixed, still there, or not a Ladder problem. Include:
    - `{{now+90m}}` and the zone-less `time` mask;
    - `--mask-text` on change (a)'s 409 message;
    - the parent false alarm;
    - the type-drift warning for `ClockInRequestDTO`;
    - the exporter's defaults and version;
    - `other-writers` for `dbo.TIMECLOCK`;
    - the per-region contract hashes;
    - `--since` reviewing steps;
    - the guard against overwriting reference traces;
    - the SqlException line in `test-failed`.
2. **Stamp.**
    - Bring the working files up to date with the English: copy round 6's regenerated files in, or regenerate in
      place. Say which, and why it isn't a hand edit.
    - Remove `"baseline"`, run `ladder test`, and `ladder stamp` both timeclock projects.
    - `check` must be clean (exit 0). Record the lock's contents: steps, `@schema`, links, tests, code
      fingerprints.
3. **Change (c), across the trees, from the lock.**
    - Clock-out refusals get a code, as clock-in's did: no open row answers 409 `NOT_CLOCKED_IN` with the
      service's message.
    - Edit only the API English first, and record what `check` prints on both projects from the lock:
      `edited`, `linked-changed` (`[tcl.1.3]` and the scanner steps that clock out), `has-callers`, and
      `test-stale`.
    - Then update the client English, regenerate both sides, run `ladder test` and replay.
4. **Hand edit, from the lock.**
    - Edit one generated region by hand in the working files (a log message, say).
    - Record whether `check` reports it, and what `regen` does with it: it should refuse, and say how to accept
      or discard the edit.
    - Then discard it.
5. **Schema change, from the lock.**
    - Change a column the stamped steps rely on: for example, widen `DIVISION` from `char(10)` to
      `varchar(20)`, with its migration on the trial database.
    - Re-export, then record which steps show `schema-changed`. They should be the steps that refer to
      `Dbo_Timeclock` or `[[Dbo_Timeclock.Division]]`.
    - Record whether the capability tests that touch the table go stale.
6. **Approve again.** Stamp both projects. `check` must be clean of `edited`, `linked-changed`, `has-callers`,
   `schema-changed` and hand edits. Record anything left.
7. **Report.**

## What to report

Write `REPORT.md` in this folder on the branch `trial/6-lock-round7`, and open a pull request.

| Measure | Round 6 | Round 7 |
| --- | --- | --- |
| Round 6 problems fixed in v0.6.0, of 23 | n/a | |
| `check` clean right after the first stamp | n/a (baseline) | |
| Flags after change (c), from the lock: `edited`, `linked-changed` (direct and indirect), `has-callers`, `test-stale` | from the baseline | |
| Hand edit in a generated region: reported by `check`, refused by `regen` | not testable | |
| Schema change: steps flagged, of those that rely on the changed column | n/a | |
| `check` clean after the second stamp | yes (baseline moved) | |

Also include the messages as printed, the false alarms, friction in the order you hit it, and what's left
unapproved.

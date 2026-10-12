# Ladder round 7 report: v0.6.0 fixes, and the real lock

2026-10-12 · for Ben · qbs branch `ladder-trial-r7` in `~/code/qbs-ladder-trial` (push disabled) · plugin v0.6.0
(ladder 97b3fe9), run by path from a clone (the session's installed plugin is v0.5.3). `ladder stamp` was run
this round, on the timeclock trees in the trial branch only, as the handoff allows.

Short version:
- **Round 6 fixes:** 15 of the 18 Ladder problems are fixed, 2 partly (F12, F23). F22 is fixed for its case but
  introduced a regression (N1).
- **The lock works end to end.**
  - After the first stamp, `check` is clean.
  - From the lock alone, it flags an API change on both sides (direct and indirect callers), a hand edit
    (`regen` refuses it, and says why), and a column change.
  - A second stamp clears everything.
- **New:** 9 problems (section 5). One is serious: the v0.6.0 exporter writes a made-up default for every
  non-nullable value-type column (`default 0`, the zero GUID), so a new required number, yes/no or GUID column
  never flags inserts (N1).

## 1. Numbers

| Measure | Round 6 | Round 7 |
| --- | --- | --- |
| Round 6 problems fixed in v0.6.0, of 23 | n/a | **15 fixed, 2 partly, 1 fixed with a regression**; 5 were not Ladder problems (section 2) |
| `check` clean right after the first stamp | n/a (baseline) | **yes**, exit 0 on both projects |
| Flags after change (c), from the lock | from the baseline | **all present:** `edited` on `[tc.1.2]`; `linked-changed` on `[tcl.1.3]` and, indirectly, `[scn.3]`, `[scn.7]`, `[scn.8]`; `has-callers`; `test-stale` |
| Hand edit in a generated region: reported by `check`, refused by `regen` | not testable | **yes and yes**, with clear options. Two false hand-edit reports for code regenerated in scratch and copied in (N4) |
| Schema change: steps flagged, of those that rely on the changed column | n/a | **5 flagged**: 2 name the column (`[[Dbo_Timeclock.TimePaid]]`), 3 only refer to the whole table (N6). The capability test that writes the table went stale |
| `check` clean after the second stamp | yes (baseline moved) | **yes**, exit 0 on both projects |

Other numbers:
- **Change (c)** (clock-out refusals get a code): the controller and the library were regenerated in scratch and
  copied in.
  - Build 0 errors, typecheck ok, `ladder test` 3 / 3.
  - The link test's new case (409 `NOT_CLOCKED_IN`) passes.
  - Replay against the original code recorded with v0.6.0: 19 / 24, with 5 intended differences (3 from change
    (a), 2 from change (c)).
- **The lock** after the first stamp:
  - API: 14 steps, 8 data blocks, schema facts for the 5 steps that refer to the table, 13 capabilities;
  - clients: 13 steps, 4 links, 13 capabilities.
  - Both locks hold the whole shared vocabulary, auth's capabilities included.

## 2. Round 6's 23 problems on v0.6.0

| # | Round 6 problem | v0.6.0 |
| --- | --- | --- |
| F1 | dead scanner code | not Ladder |
| F2 | host vs UTC time in the seed | not Ladder |
| F3 | profiles carry slice-specific names | the profile skill now says general plus per-area files. Docs only; not exercised |
| F4 | `{{now+90m}}` not substituted | **fixed** |
| F5 | `time` mask read zone-less times as UTC | **fixed** ("2 hours ago" now records `now-120m`). But see N7 |
| F6 | symlinked `node_modules` not ignored | not Ladder |
| F7 | the scanner typechecks against main's library build | not Ladder |
| F8 | change (a) design compromise | not Ladder |
| F9 | parent flagged as an indirect caller | **fixed** (no `[tcl.1]`) |
| F10 | masks can't reach a time inside text | **fixed**: `--mask-text` made the 409 repeatable, 24 / 24. Pattern order matters (N8) |
| F11 | a wording-only change forces regeneration | **fixed**: the stale message suggests `ladder retag` |
| F12 | one data block stales every contract region | **partly**: regions now carry their own hash after regeneration, but a class whose name isn't the block name plus a suffix keeps the build hash and still goes stale (N2) |
| F13 | data-block change shown as a trailing fragment | **fixed**: "data ClockInRequest gained field source: ..." |
| F14 | a client type drifts silently | **fixed**: `type-drift` names `ClockInRequestDTO` in `dtos/time-clock.ts` and says how to resolve it |
| F15 | support-code hand edits untracked before a stamp | by design; **after a stamp, hand edits are tracked** (section 4) |
| F16 | the failure message hid the SQL error; a schema change didn't stale tests | **fixed**: the SqlException line is kept, and with `writes: Dbo_Timeclock` on the capability, the schema change made its test stale |
| F17 | an exporter switch raised false `schema-changed` | **fixed**: auth `--since` round 5 shows none |
| F18 | `--since` didn't review steps | **fixed** |
| F19 | unexplained one-time `test-stale` after an upgrade | **fixed**: the message now says "(after a Ladder upgrade, possibly only how that is recorded)" |
| F20 | nothing protected the reference traces | **fixed**: replay refuses committed traces without `--force`, with a good message |
| F21 | "support only" label on a build with contracts | **fixed**: "contract only" |
| F22 | the exporter ignored column defaults | **fixed for real defaults** (`SOURCE` shows `default 'unknown'` and no longer flags inserts), **but N1** |
| F23 | no warning about writers outside the slice | **fixed, but noisy** (N3): `other-writers` lists `TimeEntryService.cs` and four test files, plus Ladder's own prompt logs and my trial copies |

## 3. The messages, as printed (from the lock)

After change (c), API English only:

```
linked-changed  [tcl.1.3] calls api:tc.1.2, whose contract changed since approval: out: was 200 with ClockOutResponse; 400 with ValidationError; 500 with `success` and `message`; now 200 with ClockOutResponse; 409 with ValidationError when not clocked in; 400 with ValidationError for other refusals; 500 with `success` and `message`; re-read this step (and the code that handles the answer), then approve
linked-changed  [scn.3] refers to [tcl.1.3], which is affected by a change in another tree (it calls api:tc.1.2); re-read this step too, then approve
has-callers     [tc.1.2] edited since approval, and it is called by clients [tcl.1.3]: that step shows as linked-changed until re-read and approved; update its English in the same change, or tell whoever owns it
```

The hand edit:

```
hand-edited     ../../../qbs_api/qb_api_services/Employees/TimeclockService.cs:180  code for [tcs.1.3] changed since it was last approved or generated; if behavior changed, update the English (ladder-write), then `ladder accept`; if not (refactor, formatting), just `ladder accept`
service  ../../../qbs_api/qb_api_services/Employees/TimeclockService.cs  [tcs.1.3]  REFUSED: this region was edited by hand since it was generated; regenerating it would throw the edit away. Move the change into the English, or `ladder accept` it, or pass --discard-hand-edits
```

The `REFUSED` came from a scratch copy where the step was also stale, so that `regen` had something to do. The
hand edit survived it.

The schema change:

```
schema-changed  [tcs.1.2] the schema it refers to changed since approval (qbs:Dbo_Timeclock.TimePaid: column TIME_PAID, decimal(18,2), required, default 0 -> column TIME_PAID, decimal(18,4), required, default 0; qbs:Dbo_Timeclock.TimePaid: ...same again...); re-read the step, then regenerate its code with --redo
```

## 4. The lock, phase by phase

1. **Stamp.** I brought the working files up to the English by copying in the files round 6 regenerated in
   scratch, which are generator output, not hand edits. Then I removed `"baseline"`, ran `ladder test` (3 / 3)
   and stamped both projects. `check`: exit 0.
2. **Change (c).** With the API English edited, both projects flagged it from the lock, with messages as above.
   - I changed the client English and added a link-test case (a harness edit).
   - I regenerated the controller and the library in scratch and copied them in. Tests pass and replay shows 5
     intended differences.
3. **Hand edit.**
   - I changed one log message in `[tcs.1.3]`. `check` reported `hand-edited` and exited 1.
   - On its own, `regen` says "nothing to regenerate", because the region isn't stale.
   - With the step's wording also changed, in scratch, `regen` refused, and the hand edit survived.
   - I then discarded the edit with git.
4. **Schema change.** `TIME_PAID` went from decimal(18,2) to decimal(18,4), with its migration on the trial
   database, the entity updated, and the schema re-exported.
   - All 5 steps that refer to `Dbo_Timeclock` were flagged, and the `clock rows` test went stale.
   - My first choice, widening `DIVISION`, was blocked: a schema-bound view (`Notification_VIEW`) locks it. My
     first migration also wasn't transactional and dropped an index before failing. The backup was untouched;
     `reset.sh --apply` now stops on a failed script, and the migration runs in a transaction.
5. **Second stamp.** After `ladder test` and stamping both projects, `check` exited 0, with no `edited`,
   `linked-changed`, `has-callers`, `schema-changed`, `hand-edited` or test warnings.

## 5. New problems, in the order I hit them

- **N1 (exporter, serious) Made-up defaults for every non-nullable value type.** The v0.6.0 exporter writes
  `default` for 10,227 properties: `Employee_MainTable.Id` "default 0", `Dbo_Timeclock.UniqueId` "default
  00000000-...", every `bool` false. Most are the C# type's zero value, not a database or model default.
  - Because v0.6.0 skips inserts for "a required column with a default", a new required `int` column with no
    default (`PUNCH_COUNT`, in a throwaway branch) exported as `default 0` and flagged nothing.
  - At runtime EF writes 0 rather than failing, so it's a review gap rather than a crash: the inserting step is
    never asked what the value should be.
  - Suggestion: export only `GetDefaultValue()` when the property has one configured (`HasDefaultValue` /
    `HasDefaultValueSql`, or a database default), never `default(T)`.
- **N2 (contracts) Per-region hashes need a matching class name.** `ClockStatus` is declared by
  `ClockStatusResponseDto`, which isn't the block name plus a suffix, so its region keeps the build-wide hash.
  Adding a field to `ClockOutRequest` made both `ClockOutRequestDto.cs` and `ClockStatusResponseDto.cs` stale.
  Suggestion: map the region's label (`@contract ClockStatus@…`) to its block when the label is a block name.
- **N3 (schema) `other-writers` is noisy and cut short.** It lists Ladder's own prompt and reply logs (`*.txt`
  under `.ladder/regen` and trial copies) and my copies of regenerated files, then stops at "..." without a
  count. The tests that actually broke in round 6 (`TimeclockServiceEmployeeKeyTests`) may be in the hidden part.
  Suggestion: skip `.ladder/`, non-source extensions and folders that hold copies; print a count and a file with
  the full list.
- **N4 (lock) Code regenerated in scratch looks hand-edited once copied in.**
  - The handoffs say to regenerate in a scratch copy, but the record of generated code
    (`ladder.code.json`) is the scratch project's.
  - The working project then reports the copied regions (`[tc.1.2]`, `[tcl.1.3]`) as `hand-edited` until the next
    stamp or `ladder accept`.
  - Suggestion: `ladder regen --out <scratch>` (generate elsewhere, record here), or an
    `ladder accept --from <scratch project>` that checks the code matches what scratch generated.
- **N5 (schema) The same fact repeats.** When a step refers to a column both by name (`[[Dbo_Timeclock.TimePaid]]`)
  and through `reads:`/`writes:` of its table, `schema-changed` lists the change twice.
- **N6 (schema) Whole-table references flag steps that never use the column.** `[tcs.1.3]`, `[tcs.1.4]` and
  `[tcs.1.6]` were flagged for `TIME_PAID`, which none of them reads. That's the documented design, but 3 of 5
  flags were noise. Suggestion: a weaker kind (`schema-changed-table`, a warning) when only the table is
  referenced.
- **N7 (replay) An upgrade can invalidate recorded references, silently.** v0.6.0 reads zone-less times as local
  time. Round 6's `original` traces, recorded by v0.5.3, differ from a v0.6.0 recording of the same code in 4 of 21
  requests, and nothing says the traces came from an older replay. Suggestion: record the replay version and mask
  rules in the trace folder, and warn when they differ.
- **N8 (replay) `--mask-text` patterns apply in order.** I needed the ISO date-time pattern before the `hh:mm`
  one, or the time inside the date was replaced first. Worth one line in the docs.
- **N9 (lock) The lock holds every capability in a shared vocabulary.** Both timeclock locks hold all 13
  capabilities, auth's too. Untested: whether editing an auth-only capability flags the timeclock projects.

## 6. Friction (mine and the environment's)

- The plugin couldn't be installed in-session (as before); I ran v0.6.0 from the clone by path.
- A schema-bound view blocked the first schema change, and my non-transactional migration half-applied (fixed in
  the harness).

## 7. What's approved, and what's left

Both timeclock projects are stamped at the trial branch's last commit (`0d147a7521`). Nothing is pending there.
Auth is unchanged and unstamped. The trial database now also has `TIME_PAID` as decimal(18,4).

Still running or on disk:
- the trial containers;
- the scratch worktree `~/code/qbs-ladder-r6-scratch`;
- branches `ladder-trial-r4` to `-r7` in `~/code/qbs-ladder-trial`.

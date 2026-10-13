# Ladder round 13 report: scanner scale (v0.6.7, then v0.6.8)

2026-10-13 · trial branch `ladder-trial-r13` in `~/code/qbs-ladder-trial` (commits `3e41b58168` to `89018a58ae`),
plugin v0.6.7 (PR #16) with no tool change during the round, then v0.6.8 (this round's fixes, PR to follow).

## Handoff (short)

The bar in `CLAUDE.md`, on a shape Ladder had not tried: client-only logic with no HTTP at all.

**The slice** (`qbs_scanner_react`):
- **The weight parser:** Avery, Digi and a generic read; three scale services use it.
- **The scale store** (Zustand, 580 lines). It covers:
  - connecting to a device;
  - ZERO and TARE, refused when the scale isn't responding or the weight isn't settled;
  - the count and its reliability;
  - snapping to a target count;
  - a 5-second "responding" timer.
- **The Counting Scale screen's container:**
  - weighing a sample;
  - adding to the running total (refused through ZERO);
  - the saved scale, connecting and reconnecting.

**Verification:** the verify skill's library route.
- **The differential harness:**
  - 200 seeded random sequences of parser and store calls, run under fake time (1 ms ticks);
  - out-of-process stand-ins only: the scale device, the saved scale, the breadcrumb log, the console;
  - the reference was recorded twice, and both recordings are identical;
  - 7 of 7 mutants were caught.
- **The existing qbs tests:** store (47), scale services (96, which parse through the parser), Counting Scale (25).

**The phases:** transcribe, link and test, regenerate blind, stamp, change through the English, regenerate, accept,
move the reference, stamp.

## 1. Verdict

**The bar is not met.** No tool change was needed to get through the round, but the change phase found two
**serious** problems, both silent. Both concern named rules.

- **F1. A rule change reached one of three steps.**
  - The rule "weight range" (0 to 1000) is used by three parsers, and only one cited it.
  - Changing the rule regenerated that parser only.
  - `check`, `regen`, the qbs tests and the differential run's expected differences all passed.
  - The qbs tests passed *because* the change did not reach the other two parsers. Those tests pin weights above 500
    as valid.
- **F2. Code generated under a rule that was later changed back passed every check.**
  - I set the rule to 500 and regenerated, then set it back to 1000.
  - `regen` said "nothing to regenerate", and `check` said "code and comparison are fine". The code still refused
    500 to 1000.
  - Only a qbs test showed it.

**The rest of the loop was clean:**
- **blind regeneration:** 3 of 3 builds compiled with no repair (parser, store with 20 nested steps, container with
  13);
- **the differential run:** one difference, caused by my English (an unreachable branch written as reachable, see
  T1). Once that was fixed, all 200 runs are identical to the reference;
- **the change** (the count follows a new target; Add refuses an empty scale; the rule): 3 regions plus the parsers,
  18 lines added and 10 removed, no repair, no hand edits;
- **locality:** every difference from the reference is explained by the change.

**v0.6.8** fixes both serious problems so that Ladder reports them; round 14 is the next try at the bar.

## 2. Results

| Measure | Round 12 | Round 13 |
| --- | --- | --- |
| Transcription, comments only | yes (11 files) | yes (3 files, `ladder tag`, 90 marker lines) |
| Blind, first run | crash, then cascading errors | 3 of 3 build, no repair |
| Tests after blind | 2/2, 3/3, 5/5 + replay 10/10 | qbs 3/3 sets; differential 118 of 200 runs differ (T1), then 200/200 identical |
| Mutation check | n/a | 7 of 7 caught |
| The change | 5 builds, 37 lines | 3 builds, 18+/10− lines, locality 0 unexplained, but see F1 and F2 |
| Hand edits to generated code | 0 | 0 |
| Tool changes during the round | 4 | 0 |

## 3. Findings

### Serious (silent), fixed in v0.6.8

**F1. A step that uses a rule's value without citing the rule never hears of a change to it.**
- **The shape:** `[swp.2]` said "outside the weight range (rule weight range)". `[swp.3]` and `[swp.4]` said
  "outside the weight range" without citing the rule.
- **Before the change, nothing warned:**
  - `rule-in-support` looks only at support code;
  - `rule-changed` lists only the steps that cite the rule.
- **The change** regenerated `[swp.2]` alone; Avery and Digi kept 1000.
- **Fix:**
  - `check` warns `rule-uncited` when a rule's value (a number of 3+ digits, or a quoted text of several words) is in
    the code of a step that does not cite the rule. On the round 13 base it names `[swp.3]` and `[swp.4]`, and it
    raises no alarm in the 19 trial projects;
  - the transcribe skill says to cite the rule wherever its value is used.

**F2. Tags did not record which version of a rule the code was generated under.**
- **What happened:**
  1. The rule changed to 500 and was regenerated.
  2. The rule changed back to 1000. That matches the lock, so `rule-changed` was quiet, and the step text was
     unchanged, so the tag matched.
  3. The code with 500 passed as current.
- **Fix:** a step's tag hash now covers the text of the rules the step cites, so a changed or reverted rule makes the
  code stale.
- **Compatibility:**
  - tags written before v0.6.8 still hold while the rules they cite are as approved;
  - `check` output on all 19 trial projects is identical to v0.6.7's.
- **Workaround in this round:** `regen --redo=swp.2,swp.3,swp.4`.

### Moderate, fixed in v0.6.8

- **F3. `check` reads only step results (`"ev": "exit"`).**
  - My harness logged `call`, `state` and `threw` events.
  - `check` said "no trace for this run" for 200 runs whose traces existed.
  - It now says the trace has no step results. The differential reference says every line is an `exit`, with the
    kind in `info`.
- **F5. `stamp` approved while a region was stale.**
  - I reworded `[swp.3]`, then stamped without regenerating or retagging.
  - The region stayed stale, and `check` reported it only later.
  - `stamp` now refuses and lists the stale regions (`--force` stamps anyway).

### Minor, fixed in v0.6.8

- **F4.** `ladder accept --help` crashed with a traceback. `--help` and `-h` now print the usage on every command.

### Transcription (mine), caught by the loop

- **T1.** "no pieces: error 'No tokens in Avery data'":
  - the original code never reaches this branch, because a JavaScript split always yields a piece;
  - the blind build filtered out empty pieces, so blank text got the other error;
  - the differential run caught it in 118 of 200 runs.

  The English now says the branch never fires and why. The transcribe skill gains "Branches that never run".
- **T2.** The parsers didn't cite the rule (F1). That was my omission; Ladder now flags it.
- **T3.** The store's rule values were in support code (`rule-in-support` caught it before tagging was done). They are
  now `@contract rule` regions. The store's exported type `UseScaleStore` was in a step region
  (`exported-type-in-step` caught it). It is now a contract.

### qbs, not Ladder

- **QUESTION:**
  - `setPieceWeight` drops a typed-in count, while `_recompute` keeps it.
  - `setTargetCount` and `setSnapThresholds` change only the snapped flag, not the count shown. The trial branch
    changed `setTargetCount` (DECISION, trial only).
- **QUESTION:**
  - A negative weight counts as "high" reliability, because the JavaScript remainder is negative.
  - `setPieceWeight(NaN)` is accepted.
- **DECISION (trial branch only):** Add on an empty scale alerts "Nothing to Add" and neither zeroes nor adds.

## 4. Next

- v0.6.8: 47 tool tests pass (the 7 new ones fail on v0.6.7); `check` output on all 19 trial projects is identical
  to v0.6.7's.
- **Round 14:** an unseen slice with v0.6.8 and no tool change during the round. The change phase includes a rule
  change, which is where round 13's problems hid. If it needs no tool change and finds no serious problem, the bar is
  met.

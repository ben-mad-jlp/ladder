# Ladder round 15 report: Update Piece Weight (v0.6.9, then v0.6.10)

2026-10-13 · trial branch `ladder-trial-r15` in `~/code/qbs-ladder-trial` (commits `f985586400` to `3b768fa814`),
plugin v0.6.9 (PR #20) with no tool change during the round, then v0.6.10 (this round's fixes, PR to follow).

## Handoff (short)

A slice not seen before, across three layers and two apps' worth of shapes: the scanner's **Update Piece Weight**
station.

**The slice:**
- **API:** the station controller (2 routes) and the piece weight part of the 704-line product service:
  - the 10% limit;
  - the save, the raw-SQL audit row and the call to a legacy procedure.
- **Library:** the screen's service.
- **Scanner:**
  - the legacy guards module;
  - the 387-line screen, with a scale and practice mode.
- **Rules:** the 10% limit and its message are named rules in **both** the API and the scanner tree, as the code
  enforces them on both sides.

**Test data:** 4 SKUs (one without weight, the non-stock `#xn`), stock, saw and committed rows, and an empty
container.

**Scenarios:** 26 requests, observing the SKU weights, the legacy SKUREFERENCE weights, the audit rows and the SQL
count. The reference was recorded twice; both recordings are identical.

**Link tests:** library to API (4) and scanner to library to API (2).

**Setup:** the scratch copy was set up as the v0.6.9 skills now say. A trial script (`ladder/env/scratch.sh`) makes
the scanner and dashboard resolve the scratch library.

## 1. Verdict

**The bar is not met.** One serious problem showed up in blind regeneration, and the change phase uncovered two
gaps in how links carry changes.

**Serious:**
- **F1. A repair silenced compiler errors with casts. The build was clean and the code was wrong.**
- **F2. The same rule in two linked trees can disagree silently.** A change made in one tree never reaches the other.

**Moderate:**
- **F3. Links that carry nothing are silent.** This covers another tree's steps named in prose without `calls:`, and
  a link no step uses.

**The rest of the loop ran cleanly:**
- **Blind regeneration:**
  - 5 of 5 builds compile: 4 with no repair, and the screen after 1 repair round (F1);
  - the blind API matches the reference on all 26 requests;
  - tests: API 1/1, library 3/3, scanner 2/3 at first. The practice tests failed because of F1.
  - after naming the fields in the English and adding the type files to `reads`, the screen regenerated blind with
    no repair and no casts, and passed 3/3.
- **The change:**
  - the scanner's success message names the sample size: 1 region, no repair, every test passes;
  - the API half (record the signed-in employee instead of the body's) regenerated in 1 line, and its replay
    differs exactly in the audit rows' employee;
  - a qbs test pins the old behaviour (a mock verifies the body's employee), so that half was reverted through the
    English.

## 2. Results

| Measure | Round 14 | Round 15 |
| --- | --- | --- |
| Slice | API + library + dashboard (7 builds) | API + library + scanner (5 builds), a rule in two trees |
| Blind | 7 of 7 (1 needed 2 repairs) | 5 of 5 (1 needed 1 repair, which hid an error: F1) |
| Blind behaviour | replay 43/43, tests all pass | replay 26/26; 3 practice tests failed (F1), then all pass after the English fix |
| The change | 2 regions, replay 41/43 + 2 explained | scanner: 1 region, tests pass; API: 1 line, replay differs only in the audit rows' employee, reverted (qbs test pins it) |
| The cross-tree rule probe | n/a | API rule changed alone: every project said ok (F2) |
| Hand edits to generated code | 0 | 0 |
| Tool changes during the round | 0 | 0 |

## 3. Findings

### Serious, fixed in v0.6.10

**F1. A repair hid a contract error behind casts.**
- **The cause:** the screen's English said "the scale's weight" and "whether it may be started" without naming the
  fields. The scale hook's file was in `reads`, but the hook imports its state type from `scale/types.ts`, which
  was not.
- **What blind regeneration did:**
  - it wrote `scaleState.weight` and `isStable`, and a practice offer with `canStart`;
  - the repair, with 12 compile errors and no type to read, cast the scale's state to a guessed shape
    (`(scaleState as unknown as { netWeight?, weight?, currentWeight? })…`) and passed the offer through a cast.
- **The result:** the build was clean. The practice button would never have been enabled (`canPractice`
  undefined), and only the qbs practice tests caught it.
- **Fix:**
  - the repair prompt says to fix the cause and forbids casts, ignore comments, `dynamic` and `!` used to silence
    errors;
  - `regen` prints a warning for every region that gained type escapes;
  - the skills say to name the fields read from a hook or store, and to put the files declaring their types in
    `reads`.

**F2. A rule written in two linked trees diverged without a word.**
- **The setup:** the 10% limit is a named rule in the API and in the scanner (both enforce it). The two projects are
  linked through the library.
- **The probe:**
  - changing the rule in the API tree only made the API's steps `rule-changed`, as expected;
  - the library got `linked-changed`;
  - the scanner said `RESULT: ok` and would have kept refusing at 10%.
- **Fix:** `check` warns `rule-diverged` when a rule with the same name says something else in a project reachable
  through links (the API and the scanner see each other through the library). On the probe it fires on both sides.
  It raises no alarm on the 25 trial projects.

### Moderate, fixed in v0.6.10

**F3. Links that carry nothing.**
- **What happened:** the scanner tree named the library's steps in prose (`([upl.2.1])`) and had no `calls:` lines.
  Its link to the library therefore carried nothing, and the API change never reached the scanner's review.
- **Fix:**
  - `check` warns `uncalled-reference` (another tree's step named outside notes without `calls:`) and `link-unused`
    (no `calls:` across a link in either direction). Both fire on the round 15 base.
  - The transcribe skill says a link needs `calls:` lines.

### Minor, fixed in v0.6.10

- **F4.** The `reference-stale` warning (new in v0.6.9) fired in the scratch copy, where the regenerated code is
  meant to differ. It now speaks only when the code is the approved code.

### Transcription (mine)

- **T1.** The fields read from the scale and given to the view were not named (F1's cause). The English now names
  them.
- **T2.** No `calls:` lines in the scanner tree (F3). They have been added.
- **T3.** I missed committing the retagged screen file; the scratch copy then regenerated the parent region (its
  output was the same code).

### qbs, not Ladder

- **QUESTION (possibly a bug):** the save body's modifier is `[Required]`, so a row without a modifier, which is
  every inventory row on the trial database, is refused with 400. The screen sends the row's empty modifier. The
  scanner link test reproduces it.
- **QUESTION:** for a SKU with no legacy SKUREFERENCE row, the legacy procedure fails ("Could not update pieceweight
  Line 24", 422) after the new weight and the audit row are saved. The caller sees a failure for a change that
  happened.
- **QUESTION:** the API records the body's employee, not the signed-in one. A qbs test pins this
  (`SmallScannerScreenAuthTests.SavePieceWeight_OnTheStationEndpoint_SavesWithinTheLimit`).

## 4. Next

- v0.6.10:
  - 56 tool tests pass, including 6 new ones;
  - `check` output on all 25 trial projects is identical to v0.6.9's (after the note exclusion).
- **Round 16:** a new slice with v0.6.10 and no tool change.

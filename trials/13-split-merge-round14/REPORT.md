# Ladder round 14 report: Split / Merge Container (v0.6.8, then v0.6.9)

2026-10-13 · trial branch `ladder-trial-r14` in `~/code/qbs-ladder-trial` (commits `27155f1866` to `bc170b2a97`),
plugin v0.6.8 (PR #18) with no tool change during the round, then v0.6.9 (this round's fixes, PR to follow).

## Handoff (short)

The bar in `CLAUDE.md`, on a slice not seen before, through all three layers: the dashboard's **Split / Merge
Container** screen.

**The slice:**
- **API:**
  - the screen's controller (4 routes);
  - the split and merge controller steps two controllers share;
  - the split, merge and weighing methods of the 3,815-line container service;
  - three DTO files.
- **Library:** the screen's service (4 calls).
- **Dashboard:** the hooks and the 329-line container (including the assistant's handlers and snapshot).

**Rules named in the English:**
- the screen permission;
- the "Invalid Split" message (in both the API and dashboard trees);
- the commit types a merge takes (cited twice in the merge step);
- the weight cap message;
- the printer message.

**Test data:**
- employees 941 (screen) and 942 (none);
- 15 containers covering:
  - split: plain, sealed, two rows, uncommitted, a pallet's child;
  - merge: same lot, other serial, restock, over the order's 30 lb cap, over the 45 lb constant, empty, unknown.

**Scenarios:** 43 requests in 3 files, recorded with the rows written and the SQL count. The reference was recorded
twice, and both recordings are identical.

**Link tests:** library to API (4) and dashboard to library to API (3), both against the trial API.

## 1. Verdict

**No serious Ladder problem, and no tool change was needed.** The whole loop ran with no hand edits to generated
code:
- **blind regeneration:**
  - 7 of 7 builds compile: 6 with no repair, the container after 2 repair rounds (merge request field names, see T1);
  - the blind API matches the reference on all 43 requests: answers, rows written and SQL counts;
  - all tests pass: API 1/1 (21 qbs tests plus the OpenAPI snapshot), library 3/3, dashboard 5/5;
- **the change:**
  - a rule cited twice in one step changed, plus a dashboard fix;
  - v0.6.8 made the merge step stale directly;
  - `regen` rewrote 2 regions, 18 lines, with no repair;
  - the replay differs on exactly the 2 requests the change explains (41/43 identical);
  - every test passes, and review notices propagated through the links to the library and dashboard steps.

**Strictly, the second condition of the bar was not met.** I needed two workarounds the skills did not describe:
- **F1.** The scratch copy's dashboard resolved the original library (a linked package).
- **F2.** A recording ran the service's old binaries. Ladder had no way to notice that the reference came from other
  code.

Both are general: a scratch copy with linked packages, and any service that has to be built before it is recorded.
v0.6.9 documents the first and makes Ladder detect the second.

**Round 15** checks the bar again with v0.6.9.

## 2. Results

| Measure | Round 13 | Round 14 |
| --- | --- | --- |
| Slice | scanner, client only (3 files) | API + library + dashboard (9 files, 7 builds) |
| Transcription, comments only | yes | yes (`ladder tag`, `adopt-check` ok on all three) |
| Blind | 3 of 3, no repair | 7 of 7 (6 no repair, 1 after 2 rounds) |
| Blind behaviour | differential 200/200 after 1 English fix | replay 43/43 (rows and SQL count too), tests 1/1, 3/3, 5/5 |
| The change | rule change missed 2 of 3 steps (F1, round 13) | rule cited twice: both sites changed; 18 lines; replay 41/43 + 2 explained |
| Hand edits to generated code | 0 | 0 |
| Tool changes during the round | 0 | 0 |

## 3. Findings

### Moderate, fixed in v0.6.9

**F2. Nothing tied a reference recording to the code it was recorded from.**
- **What happened:** after the change, I re-recorded the reference from the trial's service without building it
  (the script starts the API without a build), so the reference held the old answers.
- **How it was caught:** I happened to compare it with the scratch copy's recording. `check` would have accepted
  it, and the error would have surfaced only at the next regeneration, as an unexplained difference.
- **Fix:**
  - `replay` writes a fingerprint of the project's code (tagged files, without comments and markers) into the
    traces' `.replay.json`;
  - `check` warns `reference-stale` when the reference was recorded from other code;
  - the transcribe skill says to build the service from the checkout being recorded.
- **Limits:** a fingerprint of the source cannot tell stale binaries from fresh ones. Building first is still the
  recorder's job (the trial's `record.sh` now builds). The fingerprint catches the more common slip, a reference
  never re-recorded after an accepted change.

### Minor, fixed in v0.6.9

- **F1. Linked packages in a scratch copy.**
  - The scratch dashboard's `node_modules` was a link to the original checkout's, so `qbs-library-react`
    resolved to the original library.
  - A library change would never have reached the dashboard.
  - I made the consumer resolve the scratch library. The generate skill now describes this, with a one-line check
    (`readlink -f`).
- **F3. A false `replay-settings` warning across checkouts.**
  - The `--observe` command was recorded with its absolute path, so the scratch copy's recording "differed" from
    the reference's.
  - It is now recorded relative to the git repository, and older recordings are compared the same way.
- **F4. Two `check` runs on one project at once crashed** (`FileNotFoundError` on `.ladder/exports-base.tmp`).
  Each run now uses a temporary file of its own.

### Transcription (mine)

- **T1.** The English named the split request's fields but not the merge request's. Blind regeneration guessed
  `destinationContainerName` and `containerNames`; the compiler caught both, and repair fixed them in 2 rounds. The
  English now names the fields (`retag`, since the original code already matched).
- **T2.** "Named exactly" was wrong: the database compares container names ignoring case (`sm-a` splits). The first
  recording showed it, and the English now says so.

### qbs, not Ladder

- **QUESTION:**
  - Print All printed the source container's label twice (the split's names already end with the source). The
    trial branch fixed it (DECISION, trial only).
  - A split answers "Container split into 1 containers." when given no divisions, and "Successfully merged 0
    containers" when given no containers.
- **QUESTION:** the "Invalid Split" message is written in both the API and the dashboard. Each tree names it as its
  own rule, and nothing ties the two together. Fine while the texts are meant to match; a change to one would not
  reach the other.
- **DECISION (trial branch only):** a merge takes restock commits too.

## 4. Next

- v0.6.9:
  - 50 tool tests pass;
  - `check` output on all 22 trial projects is identical to v0.6.8's.
- **Round 15:** a new slice with v0.6.9 and no tool change, run from a scratch set up as the skills now say. If it
  needs no tool change and no workaround the skills don't describe, and finds no serious problem, the bar is met.

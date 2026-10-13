# Ladder round 10 report: Unpick Shipment, dashboard to API (v0.6.4, then v0.6.5)

2026-10-12 · trial branch `ladder-trial-r10` in `~/code/qbs-ladder-trial` (commits `54280fc422` to `33ac4eb7c7`), plugin v0.6.4
(PR #10), then v0.6.5 (this round's fixes, PR to follow).

## 1. Verdict

**The bar is not met in this round.** The whole loop ran with no hand edits to generated code:
1. transcribe;
2. link and test;
3. regenerate blind;
4. stamp;
5. change through the English in two trees;
6. regenerate;
7. accept;
8. move the reference;
9. stamp again.

But v0.6.4 had two serious problems, both fixed in v0.6.5:
- **F1:** a check that cannot be trusted. Blind generation wrote three DTOs into one region, and repair then emptied the right one. `check` said "ok".
- **F2:** a change that reaches nothing. The documented way to add a step to an approved tree (`regen --blind --redo=<new ids>`) never wrote the new step, and plain `regen` never writes a new top-level step. `check` did report it missing, but the skill's workflow could not complete it.

**The good news, with the v0.6.5 fixes** (used for the rest of the round):

| | v0.6.4 (first blind run) | v0.6.5 (second blind run, and the change) |
| --- | --- | --- |
| Blind builds clean without repair | 5 of 9 | **9 of 9** |
| Tests after blind regeneration | API 3/3; library 3/3; dashboard 2/6 (two gaps in my English, see F9 and F15) | API 3/3, library 3/3, dashboard 7/7 |
| Blind API replay | 28/28 identical (SQL counts and rows written) | 28/28 identical |
| Change regenerated | | 3 builds, all clean without repair; diffs of 60, 17 and 8 lines; every replay difference explained by the change |

The rest of v0.6.5 worked as intended:
- **Approved run as reference:** `ladder reference` made the approved run the reference, and the old runs moved to history.
- **Tags:** `ladder tag` wrote the markers from a `regions.json`; the earlier rounds each copied a script for this.
- **Build and repair:** `regen --repair=3` ran the build-and-repair loop the trial had scripted three times.

**Next:** round 11, on a new slice with v0.6.5, decides whether the bar is met.

## 2. The slice

| Tree | Steps | Builds | Files |
| --- | --- | --- | --- |
| `ladder/unpick/api` | 8 (`unp.1`, `.1.1`, `.1.2`; `unps.1`–`unps.5`, `unps.4` and `unps.5` added this round) | controller, service, dtos | `UnpickShipmentScreenController.cs`, `ShipmentService.Unpick.cs` (one part of a partial class), 3 DTO files |
| `ladder/unpick/library` | 3 (`unl.1`, `.1.1`, `.1.2`) | library-service | `unpick-shipment-screen-service.ts` |
| `ladder/unpick/dashboard` | 15 (`upa`, `uph`, `upc`, `ups`, `upv`) | api-module, hooks, container, assistant, view | `api.ts`, `types.ts`, `hooks.ts`, `UnpickScreen.tsx`, `sofia.ts`, `UnpickScreenView.tsx` |

**Shapes not tried before:**
- one part of a partial class whose collaborators come from factories;
- two capabilities living in large services outside the slice (*committed container unpick*, *container move*), each committing its own transaction, called once per container;
- a presentational view, with its stories, as a build;
- an assistant screen definition (declarative data);
- a three-tree chain (dashboard → library → API) changed at the bottom.

**Vocabulary** (shared file):
- **New capabilities:** *committed container unpick* and *container move* (tested by the qbs tests that own them); *assistant wait*, *assistant screen definition* and *screen kit* (tested by trial tests).
- **Widened:** *auth state* gained the employee's authorizations.
- ***API error answer*** gained the 400/404/422 user failures that the replay showed.

**Trial harness files** (mine, not qbs tests):
- `ladder/unpick/api/env/`: seed with employees 911/912, order 99001 with Wait, Entered and Voided shipments, six containers and four locations; the reset; the `rows.sh` observer, which also reads the inventory and container logs;
- `api/harness/record.sh`;
- `api/scenarios/`: 28 requests;
- link tests: `library/harness/link.test.ts` (8 cases) and `dashboard/harness/link.test.tsx` (5 cases), both with the 127.0.0.1 fetch guard;
- `dashboard/harness/view.test.tsx` (11 cases, from the story fixtures);
- `dashboard/vocab/assistant-wait-and-auth.test.ts`;
- `regions.json` per project;
- the repository's one runner pair, as the v0.6.4 verify skill asks: `ladder/env/app-test.sh` and `qbs-api-tests.sh`.

**Outside the harness:**
- **Contract and generated types:** the committed `contracts/qbs-api.openapi.json` and the generated TS types were regenerated (stale since round 6, see F11).
- **Story and fixture:** `UnpickScreenView.stories.tsx` and its fixture gained the "Unpicked" state.

## 3. Results

| Measure | Round 9 | Round 10 |
| --- | --- | --- |
| Transcription, comments only (`adopt-check`) | yes | yes (12 files) |
| Blind regeneration clean without repair | 9 of 10 | v0.6.4: 5 of 9 (dtos 2 repairs, service 1, view 2, container 3); **v0.6.5: 9 of 9** |
| Tests after blind regeneration | 31/31, 11/11, 9/9 | v0.6.5: API 3/3 (10 qbs tests incl. the OpenAPI snapshot), library 3/3, dashboard 7/7 |
| Replay after blind regeneration | 24/24 | 28/28 both runs (SQL counts, rows, inventory and container logs) |
| Change through the English | 2 trees | 2 trees changed, the third (library) re-read through `linked-changed`; 3 builds regenerated clean |
| Replay after the change | 23/24 | 22/28: the 6 differences are the change (refused before writing; the containers stay; one more statement for the check) |
| Approved behaviour as the reference | by hand (F15) | `ladder reference --from`, old runs `--retire`d to history; `original-2` re-recorded 28/28 |
| Stamped clean (`check` exit 0) | 2 projects | library and dashboard; API exit 1 only for the qbs test that asserts the old behaviour (left for the owner, as the skills say) |
| Hand edits to generated code | 0 | 0 |

## 4. Findings, by severity

### Serious (both fixed in v0.6.5)

**F1. A misplaced contract passed `check`.**
- **What happened:** the dtos build has three files, each with one labelled `@contract` region. The blind contract prompt listed every data block and didn't say which one the region holds. The generator wrote all three types into `UnpickShipmentDto.cs`, so the build declared each type twice.
- **Repair made it worse:** the errors pointed at the right files, so `repair` emptied the region in `UnpickShipmentRequestDto.cs`. It also wrote a comment claiming the type "is already declared ... `[JsonIgnore]`", which was invented.
- **`check` couldn't tell:** the result compiled, and v0.6.4's `check` said "ok: every line of code is tagged".
- **Evidence:** in the trial branch, `ladder/unpick/trial/gen/first-run-evidence/`.
- **Fix:**
  - the contract prompt (generation and repair) says which blocks the region holds and where the build's other blocks are;
  - `check` reports `contract-misplaced` for a labelled region that declares no type, or that declares a block another region's label names (no false alarm on the eight earlier projects).
- **Result:** the second run wrote one type per region, clean.

**F2. New steps in an approved tree were never written.**
- **The documented flow fails:** the generate skill says "`regen --build=X --blind --redo=<new step ids>`" for new steps in an approved tree. `regen_blind` only rewrites existing regions, so `[unps.5]` was never written. `[unps.3]` then called a method that didn't exist, and `repair` inlined the check into `[unps.3]`.
- **Plain `regen` has the same gap:** `find_missing` skips top-level steps, so a new top-level step was never written by plain `regen` either. `check` kept saying "missing", but nothing in the tool could fill it.
- **Fix:**
  - blind runs first insert the new steps among `--redo` (top-level steps after the build's previous top-level step), then rewrite the named regions, which now see the new method;
  - plain `regen` inserts top-level steps;
  - the insert prompt names the steps whose English uses the new one.
- **Result:** the change then regenerated clean without repair.

### Moderate (fixed in v0.6.5 unless noted)

**F3. One step tagged in two regions is written twice.**
- **What happened:** I tagged a helper as a second region of `[unps.3]`. The profile says helpers are their own steps, but nothing warned. Blind generation wrote the whole step into both regions, which gave a duplicate method; repair then emptied one.
- **Fix:** `check` warns `split-step` (no false alarm on the earlier projects). I gave the helper its own step, `[unps.4]`.

**F4. Editing a shared capability flags other areas with only "regenerate".**
- **What happened:** adding a binding alternative to *API error answer* and an output to *auth state* turned round 9's binstock API and round 8's My Alerts dashboard into "problems found", with "regenerate with --redo". Their code didn't need to change; a review and `ladder stamp` was the right action.
- **Fix:** the message and the format say so.
- **Not fixed:** on a whole repository with one shared vocabulary, every such edit will ask every user for that review. Consider per-claim granularity later.

**F5. `binding-not-called` false alarm.**
- **What happened:** a controller step relies on the error answer its service throws into, but the warning looked only at the step's own build.
- **Fix:** another build of the same project making the call counts.

**F6. The skill's `baseline` made a first transcription fail.**
- **What happened:** the transcribe skill says to set `"baseline": "origin/main"`. For a tree that didn't exist there, `check` reported a problem (exit 1, not 3).
- **Fix:** a known commit without the tree is `baseline-new` (an approval item); an unknown ref is still a problem.

**F7. No command regenerates until the code builds.**
- **What happened:** rounds 8, 9 and 10 each scripted regen → `check_command` → `repair` loops.
- **Fix:** `ladder regen ... --repair=N`.

**F8. Tagging is a copied script** (round 9's F2, again).
- **Fix:** `ladder tag <ladder.json> regions.json --base REF` rebuilds each file from the untagged commit with the tree's hashes. It reproduced round 10's script output exactly, plus per-region contract hashes. The transcribe skill now uses it.

**F9. Component bindings were invisible.**
- **What happened:** the *screen kit* binding named the workspace package, not its files. The generator guessed `variant="warning"` (it's `tone="warn"`), missed a dialog field's `type`, and dropped the grid's `enableVirtualScrolling={false}`, so jsdom rendered no rows. Calls written as JSX also didn't count as calls.
- **Fix:**
  - JSX element names count as binding calls, in `check` and in the prompt's binding files;
  - the vocabulary skill says a workspace package is `(in repository)`.
- **Trial:** the binding now names its files and the grid switch.

**F10. Old recordings had no exit after `ladder reference`.**
- **What happened:** the round's two blind recordings came from scratch code that no longer exists. After the reference moved they failed the comparison, and the only advice was "re-record".
- **Fix:** `ladder reference --retire=A,B` moves them to history and drops their builds.

**F11. The repository's own guards weren't in the slice's tests.**
- **What happened:** the committed OpenAPI contract had been stale since round 6's change through the English (a `source` field). qbs's `ApiContractSnapshotTests` failed on main of the trial branch, and Ladder never saw it.
- **Fix:** the verify skill says to include such guards in `"tests"`. Round 10's API tests now include the snapshot test, and the contract was regenerated.

### Minor (fixed in v0.6.5 unless noted)

- **F12.** Scenarios couldn't send a body that isn't JSON. `"raw"` was added.
- **F13.** `ladder test` printed "same command as above" for a command that wasn't above, and `ladder test NAME` didn't match the name it prints ("seam"). Fixed both.
- **F14.** A consumer that compiles against a built package (the dashboard against the library's `dist`) doesn't see a regenerated library until that package is built. The trial's regen script rebuilt it. The verify skill now says so; Ladder has no ordering between projects for this.
- **F15.** An attribute another system finds on the page (`data-sofia-target`) was described only as "the assistant's target", and regeneration wrote `data-assistant-target`. The qbs Sofia tests caught it. A transcribe skill line and the *assistant screen* vocabulary now say so.

### My transcription errors, caught by the loop

- The area profile called the DTOs "read only" while making them a build.
- The helper was split across two regions (F3).
- The view's English didn't name the grid switch or the attribute (F9, F15).

Each was fixed in the English or profile, never in generated code.

### qbs, not Ladder

- **QUESTION, now a DECISION:**
  - **Before the change:** a location missing in a container's division unpicked that container and then failed with 422, leaving it unpicked where it was.
  - **The round 10 change:** the location is now checked first, in every division; this is in the trial branch only.
- **QUESTION:** the screen shows the API's "InvalidQBOperation:" marker for a deactivated location; this hook doesn't strip it, unlike the dashboard's shared helper.
- **Rows of one container** (several tasks) have no order of their own.
- **For the owner:** `ShipmentUnpickTests.Unpick_VoidedShipment_...` seeds no `Location.Main` rows, so with the change it fails with "Location SHIP-1 does not exist in division GW.". Per the ground rules, the test was not edited.
- **Stale since round 6:** the committed OpenAPI contract and generated types (F11), regenerated in the trial branch.

## 5. What to fix next

All of F1–F15 are addressed in v0.6.5:
- 30 tool tests pass, including `test_round10.py`;
- `check` exit codes are unchanged on all 12 trial projects.

Still open:
- **F4's scale question:** shared vocabulary churn.
- **F14:** no build ordering between projects.

**Round 11:** an unseen slice with v0.6.5, including:
- a change that adds steps to an approved tree;
- a library that two apps consume.

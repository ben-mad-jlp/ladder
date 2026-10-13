# Ladder round 12 report: SKU History (v0.6.6, then v0.6.7)

2026-10-13 · trial branch `ladder-trial-r12` in `~/code/qbs-ladder-trial` (commits `308d546483` to `fce580bc92`), plugin
v0.6.6 (PR #14), then v0.6.7 (this round's fixes, PR to follow).

## Handoff (short)

The bar in `CLAUDE.md`, on a slice chosen without the earlier fixes in mind: the dashboard's **SKU History** screen.

**The slice:**
- **The route:** it hides a cost field without a second permission.
- **The service:** one method of the 2,238-line SKU service, which three routes share.
- **The screen's DTO:** its `From` method (the cost hiding) sits inside the DTO class.
- **The library's service.**
- **The dashboard:** the hook, the container, the view, a content component the purchase orders dialog shares, and
  the assistant contract.

**Test data:**
- employees 931 (screen and cost) and 932 (screen only);
- three SKUs (every property; diameter only; length only), lots with and without vendor and cost;
- stock in the legacy inventory table.

**The phases:** transcribe, link and test, regenerate blind, stamp, change through the English (a new top-level step
and new fields in three trees), regenerate, accept, move the reference, stamp.

## 1. Verdict

**Strictly, the bar is not met:**
- v0.6.6 crashed on this slice (F1);
- the first blind run needed four more tool fixes before it would build.

**This round found no serious problem:**
- no wrong code generated silently;
- no check that could not be trusted;
- no change that reached nothing.

Every problem was loud: a crash, a failed build, or a refused region. With the fixes, the loop ran with no hand
edits to generated code:
- **blind regeneration:** all 11 builds compile; tests pass (API 2/2 with the OpenAPI snapshot, library 3/3,
  dashboard 5/5); the blind API replay matches 10/10;
- **the change:** plain `regen --repair=3` regenerated six regions in five builds without repair (37 lines);
  `after_generate` updated the OpenAPI contract and client types; the replay shows exactly the new field.

**Round 13** with v0.6.7 should need no tool change to pass. If it does, the bar is met.

## 2. Results

| Measure | Round 11 | Round 12 |
| --- | --- | --- |
| Transcription, comments only | yes | yes (11 files, `ladder tag`) |
| Blind, first run | 11 of 12 build | crash in one build, then cascading errors (F1–F3) |
| Blind, after fixes | 12 of 12 | 11 of 11 build (8 at once, content 3 repairs, view 1); tests 2/2, 3/3, 5/5 |
| Blind API replay | 28/28 | 10/10 (with and without the cost permission) |
| The change | 5 builds clean | 5 builds, 6 regions clean without repair, 37 lines; replay: only the new field |
| Stamped clean | 3 of 3 | 3 of 3 |
| Hand edits to generated code | 0 | 0 |

## 3. Findings (all fixed in v0.6.7)

### Moderate: loud failures that needed a tool fix

**F1. A step region inside a contract region crashed blind regeneration.**
- **The shape:** the screen DTO's `From` method is a step (the cost hiding) inside the DTO class.
- **What failed:** blind mode wrote the contract first, the reply dropped the nested markers, and the next lookup
  raised `StopIteration`.
- **Plain `regen` had a related failure:** rewriting the contract changed the nested method, which then counted as a
  hand edit, so its own regeneration was refused.
- **Fix:**
  - blind mode writes such a contract last, around the nested regions;
  - plain `regen` puts nested regions back verbatim after a contract rewrite;
  - a vanished region is reported instead of crashing.

**F2. Prompts left out data blocks named by data blocks.**
- **What happened:** the service's prompt had `SkuHistory` but not `SkuProperty` ("list of SkuProperty"). It guessed
  the field names, and three repairs never fixed it.
- **Fix:** prompts include named blocks transitively.

**F3. Exported shapes that other files use were renamed.**
- **What happened:** the view's props, an exported interface described only in prose, were rewritten. The container,
  the story fixtures and the purchase orders dialog stopped compiling. The dataset function came back with three
  arguments where its caller passes one object.
- **Fix:**
  - `check` warns `exported-type-in-step`. It found this one, and two in round 11's scanner dialog, with no false
    alarms elsewhere;
  - blind prompts include the declarations of exported functions;
  - the transcribe skill says that component props and exported types other files import are data blocks.

**F4. `--repair` spent three rounds on errors it could not reach.**
- **What happened:** one broken build made every later build report "STILL DOES NOT BUILD". Errors in fixtures and
  tests (no build owns them) gave the same message.
- **Fix:** it stops at once and says whose the errors are, or that they are in files no build generates. Update
  those by hand, or make the field optional.

**F5. Blind mode had no retry for a rejected reply.**
- **What happened:** the content region's reply wrote its import request as a comment
  (`// @add-to-support imports`). The parser rejected it, and the old code stayed.
- **Fix:**
  - commented markers are accepted;
  - blind mode retries once with the reason, as plain `regen` does.

### Minor

- **F6. Unused imports in support code** (round 9's F12). A regenerated region stopped using `EmptyState`, and the
  unused import broke a strict TypeScript build. Repair now removes an import the compiler reports unused from a
  support region, and nothing else there.
- **F7. A shared binding named one call.** The *HTTP client* binding listed only `post`, so `binding-not-called` fired
  on a service that uses `get`. The check was right; the vocabulary now lists `get`/`post`/`put`/`delete`. Four
  stamped projects were reviewed and re-stamped, the path round 10 added.

### Transcription (mine), caught by the loop

- The view's and the content's props were prose, not data blocks (F3).
- The service build did not read the DTO file.
- The library's new `totalStock` was required, which broke two story fixtures and a qbs Sofia test that build the
  type. It is now optional ("test data written before it may not have it").

### qbs, not Ladder

- **QUESTION:**
  - The API answers `sku` as asked (`q1a`) while its "SKU" property is the stored `Q1A`.
  - The dashboard compares the unit cost permission exactly (case matters), while the API ignores case.
  - Numbers are formatted with the server's culture.
- **DECISION (trial branch only):** the history now answers a total stock.

## 4. Next

- v0.6.7:
  - 40 tool tests pass;
  - `check` exit codes match v0.6.6 on all 18 trial projects.
- **Round 13:** an unseen slice with v0.6.7, with no tool change allowed during the round. If none is needed and it
  finds no serious problem, the bar is met.

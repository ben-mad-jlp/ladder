# Ladder round 9 report: scanner binstock (API + React Native), v0.6.3

2026-10-12 · trial branch `ladder-trial-r9` in `~/code/qbs-ladder-trial` (commits `731dac6c74` to `6606a1f247`),
plugin v0.6.3 (PR #7).

## 1. Verdict

**The bar is not met.** No generated code was edited by hand, and the whole loop ran:
1. transcribe;
2. link and test;
3. regenerate blind;
4. change through the English;
5. regenerate;
6. review;
7. stamp.

But four serious Ladder problems showed up, and two steps needed workarounds the skills don't describe:
- **F1:** a replay comparison with no comparable build passes silently. It had already hidden round 8's post-change
  replay.
- **F9:** `regen --blind` ignores `--redo` and rewrote ten stamped regions to add two.
- **F10:** the generator invented a storage API because it never saw the capability's binding; `repair` then
  "fixed" it by importing a different library.
- **F15:** an intended behaviour change has no approved form in the comparison, so check fails after the stamp.

The good news:
- **Regeneration quality:** 9 of 10 builds compiled clean blind. The one that didn't (F10) came out clean and
  correct once its build read the binding file.
- **The cross-tree change:** it reached every caller through the new "behind" links, and regenerated as two minimal
  diffs.
- **Replay:** it caught a wrong English claim (F3) before any code was generated.

## 2. The slice

| Tree | Steps | Builds | Files |
| --- | --- | --- | --- |
| `ladder/binstock/api` | 6 (`bs.*`, `bss.1`) | controller, service, dtos | `BinstockController.cs`, `BinstockService.cs`, `UploadBinstockRequest.cs` |
| `ladder/binstock/scanner` | 28 (`bso.*`, `bsa.*`, `bsk.*`, `bsc.*`) | operations, approvers, cache, types, container | 4 hooks/types files and `BinstockScanScreen.tsx` |
| `ladder/auth/api` (extended) | +4 (`emp.9`, `emp.10`, `empc.1.1`, `empc.1.2`) | employees, new `employee-routes` | `EmployeeService.cs`, `EmployeeController.cs` |

**Shapes not tried before:**
- a shared approval routine with its own transaction rules (approvals in the caller's transaction, refusals on a
  separate connection);
- the API's global exception mapping;
- device storage;
- a React Native container;
- a client that defaults to the production host;
- a link into an existing tree that was itself mid-change (round 5 left `api.1.1` changed in the English only).

**New vocabulary** (shared file `ladder/auth/vocabulary.ladder`):
- *approval routine*: tested by a probe, 11/11 claims hold.
- *API error answer*: untested (warning kept), covered by replay.
- Eight scanner capabilities: *scanner HTTP client*, *cached employees*, *employees by authorization*, *password
  check*, *device storage*, *connectivity probe*, *self-approval notice*, *permission names*. The first four and
  device storage are tested.

**Trial harness files** (mine, not qbs tests):
- `ladder/binstock/api/env/` (seed 901–903, reset, `rows.sh` observer);
- `api/harness/record.sh`;
- `api/scenarios/` (24 requests);
- `scanner/harness/run.sh`, `behaviour.test.tsx` (11 cases), `link.test.tsx` (9 cases);
- `trial/tag_binstock.py`, `trial/r9_regen.sh`.

The link test installs a fetch guard. It refuses any request that isn't to the trial API on 127.0.0.1, and fails
before running when the trial URL is missing (verified).

## 3. Results

| Measure | Round 8 | Round 9 |
| --- | --- | --- |
| Transcription: only comments added (`adopt-check`) | yes | yes (8 files + 2 auth files) |
| Blind regeneration: builds clean without repair | 6 of 7 | **9 of 10**; cache: 1 repair that broke the vocabulary (F10), then clean blind with the binding in `reads` |
| Tests after blind regen | API 57, dashboard 35, library 2 | qbs filtered 31/31; scanner behaviour 9/10 → 11/11 after F10/F11; link 9/9; `ladder test` scanner 6/6, API 1/1 |
| Replay after blind regen | 29/29 | **24/24** identical, SQL counts and written rows included |
| Change through the English | 1 tree, 3 projects | 2 trees (API refusal → drop; scanner refusal text), regenerated as two minimal diffs, accepted `--from` |
| Replay after the change | 28/29 (never actually compared, see F1) | 23/24: the one intended difference (500 → 200) |
| Stamped clean (`check` exit 0) | 3 projects | binstock api and scanner; auth left as round 5 left it, plus 4 new unstamped steps |
| Hand edits to generated code | 0 | 0 |

## 4. Findings, by severity

### Serious

**F1. A comparison with no comparable build passes silently.**
- **What happened:** every tagged build shares the reference's traces (`"traces": "original"`), and a second
  recording in `traces/original-2` is not a build. So `compare_runs` compares nothing. `check` printed
  `Same input 's01_upload': each build vs original` with nothing under it, and then "code and comparison are fine".
- **Round 8 was hit by it too:** its post-change replay went to `traces/regen-change/`, which no build named, so
  its "stamped clean" never compared it.
- **Workaround:** add each recording as an untagged build.
- **Fix:**
  - say "nothing compared" and don't claim the comparison is fine;
  - report trace folders that no build names.

**F9. `regen --blind` ignores `--redo`.**
- **What happened:** `regen ladder.json --build=employees --blind --redo=emp.9,emp.10` rewrote all ten `emp.*`
  regions of the stamped auth service. `regen_blind` never reads `REDO`. That means you can't extend a stamped tree
  and regenerate only the new steps blind, which a whole repo will do constantly.
- **What I did:** didn't bring `EmployeeService.cs` back. Its blind regen passed 31/31 in scratch, but it would have
  replaced approved code.
- **Fix:** `--redo` limits `--blind` to regions tagged with those ids.

**F10. The generator didn't see the capability's binding, and repair switched libraries.**
- **What happened:** the cache build used `storageService.getItem/setItem`, which don't exist (it's `get<T>`/`set`).
  The binding's file wasn't in the build's `reads`. `repair` then fixed the 19 type errors by importing
  `@react-native-async-storage/async-storage` directly, bypassing the capability. The result compiled, but
  behaviour changed: an unreadable stored list now throws instead of reading as nothing. The behaviour test caught
  it; `check` couldn't.
- **What I did:** added the binding file to `reads`, and regenerated blind. Clean, 11/11.
- **Fix:**
  - the prompt includes the in-repository binding files of the capabilities the region's steps use;
  - the repair prompt says to keep to the vocabulary's binding and never add a library;
  - `check` warns when a build neither reads nor imports a used capability's binding file.

**F15. An intended behaviour change has no approved form in the comparison.**
- **What happened:** after the change, the reference traces show the old behaviour, so `check` fails even after
  `stamp`. The skills say nothing about it.
- **What I did:** moved the old runs to `traces/history/`, made the post-change run the reference, and re-recorded
  `original-2`. That's a workaround the skills don't describe.
- **Fix:** a way to make the approved run the reference (for example, `ladder replay ... --as-reference` after a
  stamp, or accepted differences recorded by `stamp`), described in the verify skill.

### Moderate

**F5. No place for a project's own behaviour tests.**
- `ladder test` runs capability and link tests only.
- The slice's tests (qbs xunit filters, `behaviour.test.tsx`) run by hand, and nothing records that the stamped
  code passed them. The behaviour test was the only thing that caught F10 and F11.
- **Fix:** ladder.json `"tests"` (name, command). Record them against the build files like capability tests;
  `check` reports failed or stale ones.

**F6. `ladder test` runs an identical command once per subject.**
- The scanner link test ran five times (three capabilities and two links), each starting the API: 71 s instead of
  about 15.
- **Fix:** run each distinct (command, cwd) once per invocation.

**F11. TypeScript null vs undefined.**
- "Or nothing" was regenerated as `find(...)` (undefined) where the code had `?? null`. The behaviour test caught
  it.
- The qbs TS profile now says how "nothing" maps.
- **Fix:** the profile skill should ask every TS/JS profile for this.

**F13. `accept --from` is silent.**
- It exits 1 with no output when nothing here is hand-edited: on a never-stamped project, or when the files haven't
  been copied yet.
- It doesn't copy anything, though "accept regions copied from a scratch copy" is easy to read as "bring them back".
- **Fix:** say why nothing was accepted; consider `--copy`.

**F14. A masked value leaks through other fields.**
- `incidentId` was masked, but its number also appears in `incidentMessage` ("incident (#N)"). One fewer incident
  shifted every later number.
- `--mask-text` works, but only at record time, so every reference run had to be re-recorded from old commits.
- **Fix:** replace a masked value wherever it appears in the response, and apply `mask_text` at compare time.

### Minor

- **F2. Tagging is a hand-written line-number script per round** (`tag_binstock.py` was copied from round 8's). The
  skill describes it as a tip; a whole repo would want `ladder tag <ladder.json> <regions>`.
- **F3. Cross-cutting API behaviour.** I wrote "(500)" for `InvalidOperationException` failures; replay showed 409
  `CONFLICT_ERROR`, which comes from the API's middleware. The transcribe skill could say: read the global
  exception mapping and put it in the vocabulary (now *API error answer*).
- **F4. The with-API runner is copied per area** (three copies now). The verify skill could ship one.
- **F7. A link into unapproved steps.** The scanner was stamped calling `auth [empc.1.x]`, which nobody has
  approved, and `check` said nothing. Warn on calls into new or unapproved steps.
- **F12. Support regions keep imports a repair added.** They stay after a later regen stops using them: an unused
  `import AsyncStorage` is left in the cache's support region (in the stamped code).

### qbs, not Ladder (recorded as QUESTION / DECISION in the trees)

- The sign-off prompt's approver list (`GET /api/employees/authorization/{name}`, `emp.9`) lists direct grants
  only. Holders through a role or group never appear; expired direct grants do.
- An approver or operator with a 4-digit employee id can never upload: `EMPLOYEE_UPLOADED` is `char(3)`, and the
  upload answers 409.
- The upload's own `ModelState` check is dead code (`[ApiController]` answers first).
- The round 9 changes (DECISIONs in the trial branch only):
  - an empty scan text is dropped instead of failing with 500;
  - the scanner shows the API's sentence on a 403 refusal instead of "Forbidden".

## 5. What to fix next (v0.6.4)

1. F1: report "nothing compared" and trace folders that no build names.
2. F9: `--redo` with `--blind`.
3. F10: binding files in the prompt; the repair rule; a `check` warning.
4. F15: make an approved run the reference; describe it in the verify skill.
5. F5 and F6: project tests in ladder.json; run each test command once.
6. F13, F14, F11, F7: messages, masking at compare time, a profile-skill question, the unapproved-callee warning.

Each fix gets a test on a small sample project and a line in `ladder-format.md`. Then a regression check over the
earlier projects, then round 10 on another unseen slice.

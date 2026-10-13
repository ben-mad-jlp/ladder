# Pilot report: the whole alerts area (v0.7.0, then v0.7.1)

2026-10-13 · qbs clone `~/code/qbs-ladder-trial`, branch `ladder-pilot-alerts` (from qbs main `9f8905db38`) ·
handoff: [HANDOFF.md](HANDOFF.md).

## What was done

The whole loop on one complete feature area, at full scale, with four projects:

| Project | Files | Lines | Steps | Regions |
|---|---|---|---|---|
| `ladder/alerts/api` (services, controllers, DTOs) | 22 | 3,188 | 132 | 198 |
| `ladder/alerts/library` (services, DTOs) | 6 | 695 | 48 | 76 |
| `ladder/alerts/dashboard` (Alerts, My Alerts, Alert System) | 16 | 3,165 | 115 | 152 |
| `ladder/alerts/scanner` (the alerts screen) | 9 | 645 | 21 | 39 |
| **Total** | **53** | **7,693** | **316** | **465** |

**The loop, in order:**
1. **Transcribe and tag:** four agents in parallel, one per project.
2. **Merge and link:** merge the vocabularies, then link the trees (73 `calls:` lines in a chain from dashboard to
   library to API).
3. **Review and stamp.**
4. **Regenerate blind:** every build, in a scratch copy.
5. **Verify:**
   - build each app;
   - run the area's own qbs tests;
   - replay 111 recorded API requests over all 47 alerts routes against the original.
6. **Change through the English:** one change across the API, library and dashboard (alert definitions show their
   subscriber count).

## Measurements

| What | Measured |
|---|---|
| Transcription (all four projects) | 20 min wall clock in parallel; 48 agent-minutes; about 0.97M agent tokens |
| English written | 3,092 lines of tree for 7,693 lines of code (0.40 lines per line) |
| Linking (vocabulary merge, `calls:`, links) | about 15 min, with two small scripts reading each project's CALLS.md |
| Review before stamping | sampled, not every step; every sampled claim matched the code |
| Blind regeneration, one clean pass | about 2 h of build time: API about 60 min, dashboard about 45, library 9, scanner 6 |
| Blind regeneration, with reruns after Ladder fixes | 179 min, 730 generator calls |
| A generator call | 10 to 20 s; a view build with 18 regions took 353 s and 1.6M characters of prompt |
| The change through the English (three projects) | 8 min from edit to new reference, excluding the Ladder bugs it found |

**Human review:** a careful person reading 3,092 lines of English against the code would take a working day or more
for this area. That's an estimate, not a measurement. The sampled review found no errors; the blind runs found the
three gaps listed under "Gaps in the English" below.

## Verification of the blind regeneration

| Project | Build | Tests | Replay |
|---|---|---|---|
| API | clean | 79/79 alerts API tests | 110/111 identical to the original |
| library | clean | 7/7 | (calls the API: covered by the API replay) |
| dashboard | clean, no type errors in either feature | 78/78 alerts and alert-system tests | n/a |
| scanner | clean | (the area has no tests) | n/a |

**The one remaining replay difference:** `GET /api/AlertNotifications/unread` returns the same answer with 2 SQL
commands instead of 4. The regenerated code makes one joined query, as qbs's EF Core guidelines ask. Accepted as an
efficiency difference.

**Gaps in the English:** the blind runs and the replay found three places where the English didn't say what the code
does. All three were fixed in the English, and the code then came back right:
- **A required column left unset.** When it creates an alert definition, the original sets only name and display.
  The required `description` stays null and the request answers 500. The generator, seeing the schema, set it to
  empty and "fixed" it; only the replay showed it.
- **A CSS class a test asserts** (`animate-blink-colours`). The English left it out as styling.
- **An unwritten qbs rule** that `[RequireAuthorization]` goes on each action, not on the controller. It is now in
  the qbs C# conventions.

## Ladder findings (all general, all fixed in v0.7.1 with tests)

### Serious
1. **Time masks never worked (since v0.6.4).**
   - Problem: `_mask_echoes` replaced a masked value everywhere, including its own field, before the time mask ran.
     So every `:time` value was recorded as `<not a time>`, and no comparison ever checked a time field.
   - Fix: masks now run first. An echo of a time is written as the time's relative form, and `replay` says so when a
     `:time` mask meets something that isn't a time.
2. **Repair rewrote the wrong file.**
   - Problem: build errors were matched to files by file name. An error at line 41 of `features/developer/hooks.ts`
     made repair rewrite line 41's region in `features/alerts/hooks.ts`, a region nothing was wrong with. The same
     name match let repair rounds run on another feature's errors.
   - Fix: errors are matched by resolved path.
3. **Blind runs dropped names other files use.**
   - Problem: for C# only type names were kept, not public methods, constants or tuple-returning helpers (a test's
     `IsScheduledDue`, a controller's `ScreenAuthorization` constant). A multi-line signature was kept only as its
     first line, so `alertsDataset(name, input)` came back with six parameters (round 12 hit the same symptom; its
     fix covered one-line signatures only).
   - Fix: public and internal members, constants included, are kept with their whole declarations.
4. **New imports landed inside a multi-line `import type { ... }`**, and the file no longer parsed.
   - Fix: they now go after the end of that import.

### Loud or minor
5. **`replay` crashed on a path with a space** (`/groups/Ladder Group/alerts`). Paths are now percent-encoded.
6. **A fixed date masked as a relative time** drifts by the gap between two recordings (`now-17707m` against
   `now-17780m`). `.replay.json` now records each run's start, and the comparison allows exactly that gap.
7. **Tagging a generated file broke its generator's own check.**
   - Fix: a `"generated"` setting (repository or project) makes `tag` refuse such files and `check` report them; the
     generator goes in `after_generate`.
8. **An area vocabulary replaced the shared one,** so four areas copied shared capabilities and one copy drifted.
   - Fix: `"extra_vocabulary"` adds to the shared vocabulary. A capability defined again with different text is an
     error; a word-for-word copy gets a warning.
9. **Repair couldn't fit a type it never saw.**
   - Fix: the prompt now shows the declarations of the types the errors name (`missing ... from type
     'MeasureDecl'`). Two repair rounds had guessed `DimensionDecl`'s fields and failed.
10. **Restoring the approved code after a bad run** (`git checkout`) made `regen` refuse the regions as hand edits.
    The committed code no longer counts as a hand edit.
11. **A `@contract rule` region counted as the build's data contract,** hiding `missing-contract`. Its stale message
    also wrongly spoke of "in:/out: lines"; both fixed.
12. **`regen` tried to write into builds compared by behaviour only** (`"tagged": false`). It now skips them.
13. **A capability or link test naming a missing file** said "never run". It is now `test-missing`, looked up from
    the test's folder, the project and the repository root (no false alarms over the 28 earlier projects).
14. **`ladder --version`** printed the help text.
15. **`regen` didn't report generator use.** It now prints calls, seconds and prompt size, and writes `usage.json` in
    the run's log, for sizing a whole-repository run.

### Skills
- **Transcribe:**
  - what an insert leaves out is behaviour;
  - a value a test asserts belongs in the English;
  - don't tag generated files.
- **Generate:** kept names, repair type declarations, path matching.
- **Format:** `"generated"`, `"extra_vocabulary"`, time drift.

### Noted, not changed
- **A rule's citers all go stale with it.** When a rule's value lives in a `@contract rule` constant, every step that
  cites the rule goes stale too (7 regions for one constant). That's by design since v0.6.8, to catch a rule
  reaching only part of the code.
- **`binding-not-called`** is judged over the whole project, not per step.
- **`[[Entity.Prop]]`** cannot tell a real column that is the wrong one (`ShipNo` where the code joins on `SoShip`).
- **Per-file builds sharing one recording** each need `"traces"`; a project-level default would help.
- **`init`** can't write most of a real project's settings. Under `ladder.repo.json` it now writes less, but the four
  agents still generated ladder.json with scripts.
- **Literal data** (assistant screen definitions, sample fixtures) has to be copied string by string into the English.
  The English is as long as the code there.

## Not Ladder

- **qbs `main`'s generated API contract checks are already out of date** at the base commit
  (`scripts/generate-contract-checks.py --check` fails).
- **The main checkout's library `dist` was older than its sources,** so 24 unrelated type errors appeared in the
  dashboard's type-check.
- **The transcription agents recorded about 20 apparent bugs in the alerts code** as QUESTION notes, not fixes.
  Examples:
  - a second notification for the same alert answers 500 on the primary key;
  - notification acknowledgements are stored in UTC but `/mark-completed` writes local time into the same table;
  - marking a notification read invalidates a cache key pattern that matches nothing;
  - the dashboard's `toAlert` always sets `acknowledged` false.

## Verdict

**The loop holds at area scale.** 7,700 lines and four linked projects were transcribed in 20 minutes of wall-clock
time. Regenerated blind, they build and pass all their tests and 110 of 111 recorded API answers, and a change made
through the English reaches exactly the code and answers it should.

**Scale found what the small rounds couldn't:** 15 general Ladder bugs, four of them serious. Three of the serious
ones (the blind run's names, the repair's file matching and the imports) only appear with many files that share
names, signatures and import blocks.

**What I'd do before the whole repository:**
1. **Merge v0.7.1.**
2. **Write the qbs repository's `ladder.repo.json`.** Include the generated files, the C# convention found here, and
   the area runner scripts (`ladder/env`).
3. **Run a second area on v0.7.1** with no Ladder changes in between: a trading-desk area like sales entry or
   shipping, a different shape from alerts. It's the check that the 15 fixes hold and that no new class of bug
   appears at this scale.
4. **Plan review time explicitly.** It, not generation, is the cost per area (an estimated day per 3,000 lines of
   English).

# Area 2 report: the shipping station (v0.7.1, then v0.7.2)

2026-10-13/14 · qbs clone `~/code/qbs-ladder-trial`, branch `ladder-area-shipping` (from qbs main `72d0cb468e`) ·
handoff: [HANDOFF.md](HANDOFF.md). **Paused by the owner before verification** (token use); this report says what
was done and found, and what was not.

## What was done

| Project | Files | Lines | Steps | Data blocks | Regions | Area tests (qbs) |
|---|---|---|---|---|---|---|
| `ladder/ship/api-station` | 12 | 3,218 | 91 | 21 | 128 | 87 pass |
| `ladder/ship/api-assembly` | 3 | 1,887 | 41 | 23 | 79 | 135 pass |
| `ladder/ship/library` | 14 | 772 | 16 | 34 | 65 | 11 pass |
| `ladder/ship/scanner-station` | 46 | 7,151 | 205 | 90 | 361 | 150 pass |
| `ladder/ship/scanner-navigation` | 10 | 1,926 | 74 | 4 | 95 | 78 pass |
| **Total** | **85** | **14,954** | **427** | **172** | **728** | **461 pass** |

**Steps:**
1. **Transcription:** five agents in parallel on v0.7.1 took 20 minutes of wall-clock time (about 75 agent-minutes).
   The English is 5,234 lines for 14,954 lines of code (0.35 per line).
2. **Linking:** one agent wrote 100 `calls:` lines across the five projects in 3.5 minutes.
3. **Review and stamp:** sampled review, then all five stamped; `check --all` clean.
4. **API reference:** 60 requests over all 41 controller routes. The trial database has stations but no orders, so
   these cover stations, login and logout, the lists without orders, and the refusals for unknown shipments and
   pallets.
5. **Blind regeneration:**
   - library: 6 of 6 builds clean;
   - the rest: blocked three times by the generator's usage limit and twice by Ladder bugs (below).
   - On the last run, 24 of the scanner station's 46 builds regenerated before the limit, 4 of them with a props
     mismatch between a regenerated container and its view.
   - Not completed: the API, navigation, and the rest of the station.
6. **Not done:** build and test of the regenerated code, the API replay comparison, a change through the English.

**Cost:** blind regeneration across both rounds made about 2,000 generator calls. The shipping prompts total about 150 MB
of text, roughly 40M input tokens. Much of it came from rerunning whole projects after a usage limit or a Ladder bug.
For the next areas: regenerate a sample of builds, rerun only what failed, and don't run unattended overnight.

## Ladder findings (fixed in v0.7.2, each with a test; 95 tool tests)

### From transcription and linking
1. **`tag` rewrote CRLF files as LF, and `adopt-check` said "only comment lines added"** while git showed every line
   changed. `tag` now reads the original as bytes and keeps its line endings, and `adopt-check` reports changed line
   endings.
2. **A retag (markers only) made passed tests stale,** twice in one project. Test records now hash the code without
   marker lines. Records made by v0.7.1 still count while the code is unchanged, so the upgrade doesn't make 30
   projects' tests stale.
3. **A misspelt test filter recorded as a pass:**
   - a run that says no test ran ("No test files found", "No test matches the given testcase filter", "Total tests:
     0") is now a failure;
   - a pass with no output at all is warned (`test-silent`);
   - the number of tests is recorded and printed.
4. **`ladder test` failed on a test whose files are missing,** while `check` only warned. Such a test is now skipped
   with a message, consistent with `check`'s `test-missing`.
5. **No way to link to another tree's type.** Navigation depends on about 15 of the station's data blocks, and a change
   to them reached no review. A `calls:` target can now be a data block (`calls: scanner [ShippingContext]`), and its
   change makes the calling step `linked-changed`, with the fields that changed.
6. **Missing links were invisible until the first link existed.** About 100 calls were silent. Under a
   `ladder.repo.json`, a step that names a step of a project it doesn't link to is now warned.
7. **`calls: scanner [a] [b]` was refused.** One item may now name several steps.
8. **`check --all` hid warnings.** It now prints a warning total by kind, and per project with `--warnings`.

### From regeneration
9. **A failing generator gave a Python traceback with an empty message,** and every later region failed the same way
   (60 builds "failed" in seconds). The run now stops at the first failure with the generator's own words; the last
   run showed "You've hit your session limit · resets 4:50pm".
10. **An unresolvable import the generation added could never be removed** (`using qb_api_services.Exceptions;`): repair
    doesn't touch support code, so the 1,569-line service never built.
    - Fix: an import line not in the committed file, which the compiler rejects, is now removed, also once more after
      the last repair round.
    - Related bug: C# `using` lines starting lower case weren't recognised as imports at all.
11. **A public C# constant came back private.** Blind runs named it, but said "keep it exported" (meaningless in C#)
    and gave no declaration, so a test that reads it stopped compiling. The note now says "public (or internal)" and
    carries the declarations of constants and properties too.

## Gaps in the English and the setup (not Ladder)

- **The shared "API error answer" binding** listed no call for the 422 exception (`InvalidQBOperationException`). The
  blind run invented `UnprocessableEntityException`. Fixed in the vocabulary.
- **The shared vocabulary's capability tests named harnesses of other trial areas,** which my setup hadn't copied.
  One, the mail round's own screen test, tested mail behaviour that qbs main has since changed; removed from the
  shared "scanner screen kit". Skill note: a capability's test checks only the binding's claims.
- **The trial database has no orders,** so the API replay covers only paths without orders. A full shipping replay
  needs seeded orders, line items and containers.

## Noted, not changed

- **A contract region's label may differ from the type it declares** (two exported types shared a name). Blind runs
  keep exported names, so this is left as it is.
- **Behaviour inline in JSX** (four handlers in the special-order prompt) can't have its own step; it lives in the
  render step.
- **`rule-uncited` raises false positives** inside longer strings and on short common values ("100").
- **Step globs match by prefix** (`shc.7*` also matches `shc.70`).
- **`init` still can't write a real project's settings;** the agents wrote ladder.json by hand or by script.
- **Several shared bindings** ("shipping workflow service", "session flag") name fewer calls than the code makes.
  `binding-not-called` is judged per project, so it stays quiet.

## Next

1. Merge v0.7.1 (#33, #32), then v0.7.2.
2. With the owner's go-ahead: finish this round's verification on what was regenerated, and regenerate only a sample
   of the remaining builds, not all of them.

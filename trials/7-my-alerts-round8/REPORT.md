# Ladder round 8 report: an unseen slice, the whole loop (My Alerts)

2026-10-12 · for Ben · qbs branch `ladder-trial-r8` (push disabled) · plugin v0.6.2 from the ladder clone, then
the v0.6.3 fixes made during the round (PR #7). Stamped in the trial branch.

Short version: the whole loop ran on a slice Ladder had never seen:
1. transcribe three trees (C# API over three files, TS library, React container with an AI assistant);
2. link and test them (capability tests, two link tests, replay);
3. regenerate blind;
4. stamp;
5. make a change through the English;
6. regenerate, review, stamp.

It needed no hand edits to generated code. It did **not** meet the `CLAUDE.md` bar as v0.6.2: three serious
Ladder problems surfaced, all fixed in v0.6.3 during the round and verified on the slice.
1. `repair` silently did nothing for `.tsx` files.
2. The generator was not shown a data block its step named, so it invented an assistant snapshot's keys.
3. A rule added three steps below an endpoint reached neither client tree.

The workarounds I needed are now in the skills. **The next round, on another unseen slice with v0.6.3, is
the real test of the bar.**

## 1. Slice

| Tree | Files | Steps |
| --- | --- | --- |
| API (`ladder/my-alerts/api`) | `MyAlertsScreenController.cs` (all), `SharedAlertActions.cs` (9 of its members), `AlertService.cs` (15 members, lines 716–936), `MyAlertDtos.cs` (4 contracts) | `ma.1` (7 endpoints), `sa.1`–`sa.9`, `as.1`–`as.15`; 4 data blocks |
| Library (`ladder/my-alerts/library`) | `my-alerts-screen-service.ts` (all) | `mal.1` (7 calls, each `calls: api [...]`) |
| Dashboard (`ladder/my-alerts/dashboard`) | `screen-hooks.ts` (8 hooks), `MyAlertsScreen.tsx` (container: helpers, form wiring, the Sofia assistant wiring, render) | `mah.1`–`mah.8` (`calls: library [...]`), `mac.1`–`mac.4.4` |

- **Profiles:** v0.6.2's way, general (`ladder/conventions/{csharp,typescript}.md`) plus per-area
  (`ladder/my-alerts/conventions/`).
- **Capabilities, 4 new:**
  - `scheduled alert due rule`: tested. Its test **caught my own wrong claim** about weeks: the threshold is
    the Monday of a Sunday-started week, so a weekly alert is due all Sunday.
  - `error message for display`: tested.
  - `server state`, `auth state`, `assistant screen`: no claims to test.
- **Link tests:**
  - library → API: 5 cases, plus 1 for the change;
  - dashboard → library: 2 cases, the real hooks with react-query through the real library to the running
    API.
- **Replay:** 29 requests over 2 scenarios. Two recordings identical, SQL counts included.
- **Found while transcribing:** a display longer than about 40 characters makes an alert name the database
  refuses. The answer is a 500 with an incident filed, recorded as a QUESTION; it's this round's change.

## 2. Numbers

| Measure | Round 7 | Round 8 |
| --- | --- | --- |
| Serious Ladder problems | 1 | **3** (S1–S3), all fixed in v0.6.3 and verified on this slice |
| Workarounds the skills didn't describe | — | **3** (W1–W3), now described in the skills |
| Hand edits to generated code | 0 | **0** |
| Blind regeneration: builds clean without repair | 4 / 4 (timeclock, round 6) | **6 of 7** (4 API, library, hooks); the container needed 1 repair round once S1 was fixed, and one English fix plus S2 for its tests |
| Blind regeneration: tests and replay | — | API 57 / 57, dashboard 35 / 35, library 2 / 2, link tests 3 / 3 projects; **replay 29 / 29** identical, SQL counts included |
| Change through the English: flagged on every tree from the lock | yes | **no with v0.6.2** (S3: the API only); **yes with v0.6.3**: API `has-callers`, library 2 steps, dashboard 2 hooks plus 2 container steps, each naming the path; verified from the lock and with `--since` |
| Whole loop completed | yes | **yes**: transcribe, link, test, blind regen, stamp, change, regen, accept, stamp; both stamps clean (exit 0) |

## 3. Serious problems (fixed in v0.6.3)

- **S1. `repair` silently did nothing for `.tsx`.** Its error-location pattern listed `py|cpp|hpp|cs|ts`, so
  `MyAlertsScreen.tsx(43,29): error TS2322` matched nothing.
  - Three repair rounds printed only their log folder, and the container's 7 errors stayed.
  - Fixed: common source extensions in every format, and a message when no error points into the build's
    files. With the fix, one repair round cleared all 7.
- **S2. The generator didn't see a data block its step named.** The prompt's "Data the English refers to"
  showed only the build's `"data"` list, which governs `@contract` regions. The container build has none.
  - After I named the assistant snapshot as `data MyAlertsSnapshot`, the prompt still showed an empty section,
    and the generator declared its own `MyAlertsSnapshot` with different keys (`selected`, `reset`, `values`).
  - It compiled, and the assistant's tests failed 4 / 35.
  - Fixed: every data block the steps being written name is shown. Regenerated, all 35 pass.
- **S3. A change below the endpoint reached nothing.** The change (a name-length refusal) lives in `[as.11]`.
  The endpoints the library calls say `out: what [sa.4] answers`, and their own contract text didn't change.
  - With v0.6.2, the API showed `edited [as.11]` and nothing else: no `has-callers`, and nothing in the library
    or the dashboard. Yet every client's answer changed, from a 500 to a 400 with a message.
  - Fixed:
    - `stamp` records the hashes of every step the called step's English names, transitively.
    - A change there flags the caller as `linked-changed` with the path.
    - Callers of a step that is itself waiting on a further tree are flagged too.
    - `has-callers` names the edited step and the path.
  - With the fix:

    ```
    has-callers     [as.11] edited since approval, and [ma.1.2] relies on it ([ma.1.2] -> [sa.4] -> [as.2] -> [as.11]), which library [mal.1.2] calls: ...
    linked-changed  [mal.1.2] calls api:ma.1.2, whose contract is unchanged, but steps its English relies on changed since approval: [as.11] (through [sa.4] -> [as.2]); its answers may differ ...
    linked-changed  [mah.3] calls library:mal.1.2, which is itself waiting on a change in another tree (calls api:ma.1.2, ...)
    linked-changed  [mac.4] refers to [mah.3], which is affected by a change in another tree ...
    ```

    Only the two create calls are flagged: the update paths don't name new alerts, which is correct. A
    wording edit to `[as.9]` (the description check, used by all four saves) flagged all four library calls,
    four hooks and the container.

## 4. Workarounds the skills didn't describe (now described)

- **W1. A check command that depends on another package's build output.** The dashboard type-checks against
  the library's `dist/` (a tsconfig path). The fresh scratch copy had no `dist`, so its check failed with 20
  errors in files outside the slice, and `repair` chased them for three rounds. I built the library in scratch.
  The generate skill now says to build sibling packages in the check command and confirm it passes on
  untouched code.
- **W2. Syncing the English into scratch made scratch's own generated code look hand-edited.** `git checkout`
  brought the working tree's `ladder.code.json`, so `regen` refused (`REFUSED: this region was edited by
  hand`) and `accept --from` couldn't vouch for the regions. I used `--discard-hand-edits` in scratch and a
  plain `accept`. Fixed in the tool: `.ladder/generated.json`, local and git-ignored.
- **W3. A binding with a callback-object shape.** The assistant hook takes `{ handlers: { name: { prefill } },
  snapshot: () => …, dataset: () => … }`. The binding gave only the call, so the generator passed bare
  functions (6 of the 7 errors). The vocabulary skill now says to write the shape.

## 5. English gaps (mine), found by the loop

- **The snapshot handed to the assistant had no exact keys.** It's a contract with another system. Fixed as
  `data MyAlertsSnapshot`; the transcribe skill now says so in general.
- **The dataset's loading flag** didn't say "fetching" (`isFetching`, not `isLoading`).
- **The due-rule week claim** (W above): its test caught it before any code was generated.

## 6. Other observations

- The "word for word in the conventions" warning fired on 16 API regions. The lines are the area profile's
  signatures and expression-bodied actions, which the profile fixes on purpose. The warning says so; it's a lot
  of lines for a deliberate profile, though.
- `ladder accept --from` behaved correctly. An "inconsistency" I first noted was my own truncated output.
- The scanner, dashboard and library share one vocabulary across three projects. Scoping (v0.5.1) kept every
  project's tests and warnings to its own steps.
- Not Ladder:
  - the qbs dashboard compiles against the library's built `dist/`;
  - the trial database's alert incident filing;
  - the `Notification_VIEW`-style schema-bound views (round 7).

## 7. What's approved

All three projects are stamped at `f020018e92` (after the change), clean. The change is in the working files
(`AlertService.cs`, accepted). The blind-regenerated files are kept in `ladder/my-alerts/trial/gen/blind`.

## 8. Next

Round 9: another unseen slice, with v0.6.3, against the `CLAUDE.md` bar. Candidates with shapes not yet tried:
- a scanner (React Native) station flow with a state machine;
- a report or export endpoint that streams a file;
- a background service.

# Ladder round 16 report: shipping station core (v0.6.10): the bar is met

2026-10-13 · trial branch `ladder-trial-r16` in `~/code/qbs-ladder-trial` (commits `179082b04e` to `45274b9256`),
plugin v0.6.10 (PR #22) with no tool change during the round.

## Handoff (short)

A slice not seen before, of a shape Ladder had not tried: a scanner station built on the station state machine.

**The slice** (`qbs_scanner_react/src/features/shipping`):
- the machine's state, event and context types;
- the transition function, with the assemblable-status rule and the logout from any state;
- the async login operation and its retry wrapper (backoff with random jitter);
- the state-to-screen map;
- three of the screens it maps:
  - the session check, which resumes only a station this employee holds;
  - the shipment choice, which opens a shipment handed over from another screen;
  - the error screen.

**Verification:**
- **The differential harness:**
  - 120 seeded random event sequences through the transitions, merged as the station machine merges them;
  - seeded calls of the login and the retry wrapper under fake time, with a seeded `Math.random`;
  - the reference was recorded twice, and both recordings are identical;
  - 5 of 5 mutants were caught.
- **A screens behaviour test** (7 cases: the session check and the hand-off; no qbs test covered the hand-off).
- **qbs tests:** the shipping machine, the screen maps, the station types, the session resume.

**The scratch copy** was made as the v0.6.9 skills describe (`ladder/env/scratch.sh`).

## 1. Verdict

**The bar in `CLAUDE.md` is met:**
- **no serious Ladder problem:**
  - no wrong code generated silently;
  - no change that reached nothing;
  - no check that could not be trusted;
  - v0.6.10's new checks raised nothing false on this slice or on the 25 earlier projects;
- **no workaround the skills don't describe:**
  - the scratch copy and its linked library are set up as `ladder-generate` now says;
  - the harness follows `differential.md`;
- **the whole loop with no hand edits to generated code:** transcribe, link and test, regenerate blind, stamp, change
  through the English (including a rule change), regenerate, review (locality), accept, move the reference, stamp.

**No tool change was needed during the round.**

| Phase | Result |
| --- | --- |
| Transcription | 7 files, comments only (`ladder tag`, `adopt-check` ok); 26 projects keep their exit codes |
| Blind regeneration | 5 of 5 builds clean without repair; no type-escape warnings |
| Blind behaviour | differential 120/120 identical; 7 of 7 test sets pass |
| The change | rule "assemblable statuses" + `[shm.1.5]`: the rule change made `[shm.1.3]` stale directly (v0.6.8); 2 regions regenerated, 2 lines, no repair |
| Locality | 16 seeds differ, all 16 explained (12 a CountNeeded shipment, 4 a dismiss with a shipment selected) |
| After accept | reference re-recorded (identical twice, identical to the scratch copy's), 7 of 7 test sets, stamped |

## 2. Findings

### Ladder

None needed a tool change.
- **Docs, added to v0.6.10 (PR #22):** a differential run should log what callers observe.
  - The first blind comparison differed in 8 seeds only because a transition answered `{nextState}` where the
    original answered `{nextState, context: {}}`. The station machine treats both the same.
  - My harness logged the raw result. It now logs the result as the machine reads it.
  - `differential.md` now says this.
- **Vocabulary, not the tool:** the scanner HTTP client's binding named only `post`, and `binding-not-called`
  correctly fired for `get`. The binding now lists `get`/`post`/`put`/`delete`, and `binstock/scanner` was reviewed
  and re-stamped (`binding-changed`), as in round 12.

### Transcription (mine)

- The session check's `uses:` named the screen kit; the spinner screen doesn't use it (`binding-not-called` said so).
- A region end was off by one (`untagged` said so).
- The harness needed its inputs weighted twice: toward valid logins, and toward the coming change (`CountNeeded`).
  Each time the reference was re-recorded from the same code, and the two recordings were identical.

### qbs, not Ladder

- **QUESTION:** the shipping `withRetry` and `loginShippingAsync` are exported but nothing in the app calls them;
  receiving and assembly keep their own copies of `withRetry`.
- **DECISION (trial branch only):**
  - a shipment whose status is CountNeeded can be assembled;
  - dismissing an error during assembly returns to that shipment.

## 3. Rounds 13 to 16 together

| Round | Shape | Serious problems | Fixed in |
| --- | --- | --- | --- |
| 13 | scanner store + parser + container (no HTTP) | a rule change reached 1 of 3 steps; code under a reverted rule passed `check` | v0.6.8 |
| 14 | API + library + dashboard | none (two undescribed workarounds: linked packages in a scratch copy, a reference recorded from stale binaries) | v0.6.9 |
| 15 | API + library + scanner, a rule in two trees | a repair hid a contract error behind casts; a rule diverged across linked trees silently | v0.6.10 |
| 16 | scanner station machine, async retry, screens | none | none needed |

## 4. Recommendation

**Ladder is ready to start the whole-repository transcription.** Things to watch, none blocking:
- **Type-escape warnings:**
  - they are a pattern count (casts through `unknown`/`any`, ignore comments, `dynamic`), so they can miss a cast
    to a specific wrong type;
  - read every repaired region; v0.6.10 makes the repair prompt forbid casts.
- **Shared rules:** these rely on the same rule name in each tree. `rule-diverged` checks linked projects only,
  including through a middle project.
- **The trial's environment scripts** are in `ladder/env` of the trial branch:
  - `scratch.sh`;
  - `app-test.sh`;
  - `qbs-api-tests.sh`;
  - the auth env (an isolated SQL Server and Redis).

  The full transcription needs the same.
- **Merge order:** #7, #10, #12, #14, #16, #18, #20, #22 (each builds on the one before). The reports are #8, #9, #11,
  #13, #15, #17, #19, #21 and this one.

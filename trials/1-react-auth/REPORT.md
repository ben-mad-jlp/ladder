# Ladder trial report: qbs_library_react auth and session slice

2026-10-11 · for Ben · branch `ladder-trial` in `~/code/qbs-ladder-trial` (push disabled) · nothing stamped

## 1. Slice

| File | Lines | Why |
| --- | --- | --- |
| `src/system/auth/store.ts` | 260 | permission rules: one / any / all, case-insensitive, signed-out defaults |
| `src/context/AuthContext.tsx` | 106 | provider + `useAuthStore` / `useAuthStoreEmployee` |
| `src/hooks/useRequirePermission.ts` | 110 | hook: result with `missingPermissions`, throws on a missing argument |
| `src/components/auth/RequirePermission.tsx` | 149 | gate component: ANY/ALL, sign-in-only mode, fallback, console warnings |
| `src/context/SessionContext.tsx` | 63 | provider with an effect that follows a zustand store |

688 lines, 5 files. Chosen because it is real React (a store, two contexts, a hook, a component, an
effect), has real rules, has tests that pass, and only gates UI (the API enforces permissions).
The HTTP client was the first proposal and was dropped because it is not React code.
Read but not transcribed (`reads`): `core/employee/dtos/employee.ts`, `components/auth/UnauthorizedPage.tsx`,
`system/communications/store/session-store.ts` (plus the other slice files where one imports another).

## 2. Numbers

| Measure | Result |
| --- | --- |
| Baseline tests (pass / fail) | 98 / 0 (4 files); tsc 0 errors; lint: none exists in the library |
| Tree size (steps, data blocks, lines) | 27 steps, 7 data blocks (6 at transcription), 1 named rule, 3 capabilities; auth.ladder 223 lines |
| QUESTION / DIFFERS / DECISION notes | 10 / 1 / 3 |
| Trial regeneration: rounds until tests pass | 2 (round 1: 2 tsc errors, 95/98 tests, plus 2 silent problems) |
| Tests after regeneration (pass / fail) | 98 / 0 |
| Differential runs identical to the original | 300 of 300 (round 2) |
| Mutants caught: by tests / by differential runs | 1 of 3 / 3 of 3 |
| The change: regions regenerated, acceptance tests passed | contract + `hook.1` (holding `hook.1.4`) regenerated, then `hook.1` again after clarifying; 26 of 26 acceptance tests (3 of them fail on the original, as they should) |
| Time per phase | baseline ~3 min · transcribe ~5 min · regenerate ~2 min (each generation 11–20 s) · compare ~3 min · change ~6 min · report ~5 min |

Mutants (one line each): m1 `getRoles` returns a copy (tests 98/98 missed it; differential 44 runs differ);
m2 ALL/ANY swapped in the denial warning (6 tests failed; differential 188 runs); m3 signed-out hook
copies the list instead of returning it (tests missed it; differential 44 runs).

The change (owner left the pick to me): `useRequirePermission(permission, { requireAll })`, so the hook can
require every name in a list, as `RequirePermission` already can. Locality: without the option, the new
build is identical to the original in 300 of 300 runs; with random options (315 `requireAll: true` calls),
19 runs differ in 20 results and every one is a `requireAll` call on a list the employee does not fully
hold; 0 unexplained. Hand-edit check: changing `options?.requireAll === true` to `options?.requireAll` by
hand made `ladder check` report `hand-edited` on `hook.1.4`; restored.

Existing tests that assert old behavior: none (the option is additive). Follow-up outside Ladder's reach:
`src/index.ts` exports the hook and `UseRequirePermissionResult` by name but not the new
`UseRequirePermissionOptions` type; one line to add if the change is kept.

## 3. Notes for you to decide

QUESTION (existing behavior that looks off):
1. `store.1.1`: "an employee whose `authorizations` is missing makes building the checker fail with an error instead of treating them as having no permissions"
2. `store.1.4`: "unlike [store.1.3], an empty name is not refused here; it is found only when the employee's own list contains an empty name"
3. `store.1.5`: "as in [store.1.4], an empty name is not refused here"
4. `store.1.7`: "names here keep their case and "Pick" and "pick" are separate keys, while permission checks follow rule permission match"
5. `store.1.9`: "answers exactly what [store.1.2] answers; the code comment says it may check more later"
6. `ctx.1`: "nothing is kept between renders, so every render of the provider gives a new checker and a new context value, and every component that reads the context renders again even when `employee` did not change"
7. `gate.1.3`: "the warnings are written on every render while access is denied, so a screen that re-renders repeats them (twice per render in React StrictMode development)"
8. `gate.1.3`: "the employee's full name and id go to the console on every denial"
9. `session.1`: "the store is read on every render although only the first read is used"
10. `session.1.1`: "every store change, even one that leaves these three values the same, gives a new context value, so every component reading the session renders again"

DIFFERS:
- `hook.1`: "[hook.1] and [gate.1] both decide access from a permission input. [hook.1] fails when given nothing, while [gate.1] treats nothing as "signed in is enough"; [gate.1] writes console warnings when denying, [hook.1] writes none" (the ALL-mode difference was removed by the change)

DECISION (made without you; all in the phase 5 change):
- `hook.1`: "the options come as a second argument holding `requireAll`, left out by every existing caller, so their behavior does not change; the name matches [gate.1]'s prop"
- `hook.1`: ""exactly yes" was the generator's reading of yes/no and is now written down; [gate.1] instead treats any truthy `requireAll` as on, which only plain JavaScript callers can tell apart"
- `hook.1.4`: "an empty list is still not authorized when `requireAll` is yes, matching [store.1.5]; `requireAll` makes no difference for a single name or when no one is signed in"

Also yours: whether render counts are behavior. They are compared today (the harness logs renders and
store identity) and nothing in this trial changed them; QUESTION 6 and 10 would.

## 4. Friction, most serious first

1. **Silent wrong code passes everything** (generate, round 1). The generator added `export { createContext }`
   to AuthContext.tsx and `void createContext;` to SessionContext.tsx. tsc, 98 tests and the differential
   run all passed them; only reading the code found them. Prevent: an export-surface check in `ladder check`
   (compare each module's exported names with the reference build's).
2. **Per-file builds vs one harness** (verify, `check`). With one build per file (as the transcribe skill says
   for libraries), `check` wants a trace folder per build; the harness exercises all five files together, so
   the five builds reported "differs in 300 of 300" until their trace folders were symlinked to `original`.
   Prevent: a project-level comparison, or `"traces": "original"` on a build.
3. **`generate --out` doesn't compile the scratch file** (generate). `check_command` is the retry loop the
   brief relies on, but with `--out` the compile error only showed up after swapping files in by hand.
   Prevent: run `check_command` against a temp copy with the `--out` file swapped in.
4. **Plain English is ambiguous about TypeScript shapes** (format/profile). "a map" became a plain object
   (Map expected: 3 tests failed); identity ("the same list" vs "a new list") had to be spelled out in 4
   places; "yes/no" left `=== true` vs truthy open. Prevent: a short shapes section in the TS profile
   template (Map vs object, identity, null vs undefined, absent key vs undefined).
5. **No React support in the runtime** (verify). Render probes, an error boundary for render-time throws,
   console spies, StrictMode wrapping and seeded `crypto.randomUUID` were all hand-written (200-line
   harness). Prevent: a small React kit in `runtimes/typescript` (renderProbe, captureConsole, boundary).
6. **Mutants and old rounds have to be added to and removed from ladder.json by hand** (check), or `check`
   stays "problems found". Prevent: `ladder check --compare-only <builds>` or an "expected to differ" flag.
7. **Files outside the slice that the change needs** (generate). The new options type should be exported from
   `src/index.ts`; Ladder can't see that file and the profile forbids writing it. Prevent: a "consumers"
   list per build that `check` greps for the build's exports.
8. **Setup** (install). The first zip was the old prototype; installing the plugin was blocked by the agent's
   auto-mode classifier, so you ran the install. The library has no prettier, so `format_command` was left unset.
9. **`hand-edited` message says "since it was approved"** though nothing was ever stamped (it means "since
   generated"). Wording only.
10. **Steps not in the tree are accepted in traces silently** (`input`, `harness` in our traces); a typo in a
    step id would pass too.
11. **Data blocks have no words for "a method on an object"** (format); wrote "action, takes X, answers Y".
12. **Contract and node regions interleave** in AuthContext.tsx (a JSDoc for the provider sits above the props
    interface); solved by nesting `@contract` inside `@node`, which the skill doesn't mention.
13. `init` names the tree after `--name` (long file name); `compare.reference` silently defaults to the first build.

React behavior the skills did not prepare for: identity of returned arrays and objects; render counts and
context-value identity (provider rebuilds on every render); console output as observable behavior (tests
count `console.warn`); effects that set state on mount (an extra render); a store listener that fires on
unrelated changes; StrictMode double render and double effect; render-time throws needing an error boundary
to observe; tests that `vi.spyOn` a module's named export (works only if the code calls the named import).

## 5. Where the English was hard to write

- Identity: "the input list itself (the same list, even when empty)" vs "a new list", needed in hook.1.2,
  hook.1.4, store.1.6. Written once, then sharpened after the independent reader asked.
- "Only present when..." for an optional key: first wording let a reader assume `undefined` would do; became
  "the key is left off the answer, not set to nothing".
- Render behavior (ctx.1, session.1): describing "every render builds a new value, so every consumer renders
  again" in plain words took two tries and still reads as a note more than a rule.
- The session effect's order (seed state at first render, then set it again after mount, then subscribe) only
  reads clearly as three separate `>` lines.
- What could not be said in plain English: nothing outright, but "calls the checker's own methods, so a caller
  that replaces them changes this answer" (method dispatch through `this`) is really a shape fact.
- The independent reader (26 tests, never saw the code) listed 10 guesses; 6 were real gaps and went back
  into the English (non-text entries, duplicates and case in `missingPermissions`, signed-out odd input,
  absent key, what turns `requireAll` on). The rest were already answered.

## 6. Files

- Branch: `ladder-trial` in `~/code/qbs-ladder-trial` (a clone; push URL disabled). Scratch copy for swaps:
  `~/code/qbs-ladder-scratch` (git worktree of the clone).
- Ladder project: `qbs_library_react/ladder/auth/` (`ladder.json`, `auth.ladder`, `vocabulary.ladder`,
  `conventions/`, `ladder.code.json`, `.ladder/regen/` with every prompt and reply).
- Harness: `ladder/auth/harness/` (`differential.test.tsx`, `run.sh`, `locality.py`).
- Acceptance tests: `ladder/auth/acceptance/useRequirePermission.acceptance.test.tsx`.
- Traces: `ladder/auth/traces/` (`original`, `regen-r1`, `regen-r2`, `m1`–`m3`, `change`, `opts-original`,
  `opts-change`). Generated rounds and mutants: `ladder/auth/trial/gen/`, `trial/mutants/`.
- Log written during the run: `ladder/auth/trial/log.md`.
- Not done (yours): `ladder stamp`, and the `src/index.ts` export line.

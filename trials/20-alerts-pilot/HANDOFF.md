# Pilot: one whole area (alerts) on Ladder v0.7.0

2026-10-13. The rounds so far transcribed 1 to 9 files each. This pilot transcribes one whole feature area of
qbs at full scale: the API, the library, the dashboard and the scanner, about 7,700 lines. It answers what a
whole-repository run will cost: hours, generator time and money, and review time per thousand lines. Like every
trial, its main job is still to find where Ladder breaks. **The code is throwaway; the goal is to harden Ladder.**
Read `../../CLAUDE.md` first.

## Where

- **qbs clone:** `~/code/qbs-ladder-trial`, branch `ladder-pilot-alerts` (push disabled). Its code is qbs `main` at
  `9f8905db38`; commit `8fc4fa4b02` added only `ladder/` setup and `ladder.repo.json`.
- **Ladder:** `~/code/ladder` at v0.7.0. Run the tool as `~/code/ladder/plugins/ladder/bin/ladder`. Read the
  skills and reference from `~/code/ladder/plugins/ladder/` (`skills/ladder-transcribe/SKILL.md`,
  `skills/ladder-vocabulary/SKILL.md`, `skills/ladder-write/SKILL.md`, `reference/ladder-format.md`), not from any
  older installed copy.
- **Shared settings:** `ladder.repo.json` at the qbs root. It supplies:
  - the vocabulary `ladder/vocabulary.ladder`;
  - the generator;
  - the schema `ladder/qbs-schema.json` (fresh export of main's models; `ladder schema <ladder.json> <Entity>`);
  - conventions `ladder/conventions/<lang>.md`;
  - `mode: literal` and `adopted: true` for every build.

  Don't repeat these in a project's ladder.json.

## Projects (one agent each, in parallel)

| Project folder | Step prefix | Files (repository-relative) |
|---|---|---|
| `ladder/alerts/api` | `al` (service), `als` (alert system), `alc` (cache), `aln` (notifier), `alk` (controllers), `sa` (shared actions) | `qbs_api/qb_api_services/Alerts/*.cs`, `qbs_api/qb_api/Services/AlertNotificationService.cs`, `qbs_api/qb_api/Controllers/Alerts/*.cs`, `qbs_api/qb_api/Controllers/Common/SharedAlertActions.cs`, `qbs_api/qb_api_dtos/Alert/*.cs` |
| `ladder/alerts/library` | `all` | `qbs_library_react/src/system/monitoring/services/alerts/*.ts`, `qbs_library_react/src/system/monitoring/dtos/alerts.ts`, `qbs_library_react/src/contract/alerts.contract.ts` |
| `ladder/alerts/dashboard` | `ald` (alerts, my alerts), `ads` (alert system) | `qbs_dashboard_react/src/features/alerts/**`, `qbs_dashboard_react/src/features/alert-system/**` (not tests, not stories) |
| `ladder/alerts/scanner` | `alsc` | `qbs_scanner_react/src/features/alerts/**` (not tests, not stories) |

- **Builds:** one build per source file, each with a `steps` scope and, where a file only declares types, a
  contract-only build (`"steps": []` with `"data"`).
- **Interfaces:** `I*.cs` interfaces are contract builds, or `reads` of the build that implements them.
- **Ignore every `.pseudo` file** (owner decision): never read, compare, update or report on them.

## What each transcription agent does

1. **Set up the project.** Under the repository file, `ladder init` leaves out what the repository supplies. Set
   `"baseline": "8fc4fa4b02"` and `check_command` / `check_cwd`:
   - C#: `dotnet build ../ladder/auth/api/auth-check.slnx --nologo -v q`, from `qbs_api`;
   - library: `npx tsc --noEmit -p .`, from `qbs_library_react`;
   - dashboard: `npx tsc --noEmit -p tsconfig.app.json`, from `qbs_dashboard_react` (check which tsconfig really
     checks `src`; the root one checks nothing);
   - scanner: `npx tsc --noEmit -p .`, from `qbs_scanner_react`.
2. **Write the tree** from the code, following the transcribe skill: what the code does today, including its odd
   parts. Use named rules for literals and policies that more than one step relies on, and `[[Entity.Prop]]`
   references for database columns. Keep vocabulary capabilities for the libraries the code calls.
3. **Vocabulary.** Write the capabilities your project needs in your own project's `vocabulary.ladder`, and set
   `"vocabulary": "vocabulary.ladder"` in your ladder.json. This is the only repository setting you override; four
   agents edit at once, and the coordinator merges them into `ladder/vocabulary.ladder` afterwards. Start by
   reading `ladder/vocabulary.ladder` and reuse its capability names where they fit.
4. **Links come later.** Don't write `calls:` lines into other projects' trees. In your project folder, write
   `CALLS.md`, one line per step that calls another project's code:
   `[ald.3.2] -> library: alertsService.getMyAlerts (qbs_library_react/src/.../alerts-service.ts)`.
   The coordinator adds the links once every tree exists.
5. **Tag** with `regions.json` and `ladder tag <ladder.json> regions.json --base 8fc4fa4b02`. Then:
   - `ladder adopt-check <ladder.json> --base 8fc4fa4b02` must pass: the code changes by comment lines only;
   - `ladder check <ladder.json>` must have no problems except "new" steps awaiting approval.
6. **Do not stamp.** The coordinator reviews and stamps, and that review time is one of the things this pilot
   measures.
7. **Do not commit.** Four agents share one checkout; the coordinator commits.
8. **Stay inside your project.** Don't edit other projects' folders, `ladder.repo.json`, `ladder/vocabulary.ladder`
   or `ladder/conventions/` (area conventions go in your own folder, listed in your builds' `conventions`). Edit
   code files only by adding marker comments through `ladder tag`. Never edit qbs tests.
9. **Write `NOTES.md` in your project folder:**
   - start and end time;
   - files and lines transcribed, steps, data blocks, rules and regions;
   - **every friction with Ladder,** with the command and its output: a check that was wrong or unclear, something
     the skills didn't say, a workaround. This is the main product.
   - anything about the code that a reviewer must know (odd behaviour, apparent bugs; don't fix them).

## Ground rules

- No database, API or network is needed for transcription. Don't start containers.
- No secrets in any file.
- Filtered runs only; never a whole test suite.
- Don't push. Don't touch `~/code/qbs` (the main checkout).

## After transcription (the coordinator)

1. **Merge the vocabularies.** Write `calls:` lines and `links` from each project's `CALLS.md`.
2. **Check:** `ladder check --all` until only approval remains.
3. **Review and stamp each project,** timed.
4. **Regenerate blind** in a scratch copy (`ladder/env/scratch.sh`). Build, run the area's own filtered tests (API
   `FullyQualifiedName~Alert`, the alerts vitest files) and a replay of recorded API scenarios against the
   original. Record the generator's time and cost.
5. **Make one real change through the English** that crosses the API, library and dashboard, and see it reach
   everything it should.
6. **Report:** `trials/20-alerts-pilot/REPORT.md`, with the measurements and the Ladder findings.

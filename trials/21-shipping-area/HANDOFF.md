# Area 2: the shipping station (v0.7.1, unchanged)

2026-10-13. The second whole area, after the alerts pilot ([../20-alerts-pilot/REPORT.md](../20-alerts-pilot/REPORT.md)).
It runs on **v0.7.1 with no Ladder changes during the round**, to check that the pilot's 15 fixes hold and that no new
class of bug appears on a different shape of code: a scanner state machine, large screen adapters (one of 1,420
lines that an earlier round avoided), and a 1,569-line assembly service. About 15,000 lines.
**The code is throwaway; the goal is to harden Ladder.** Read `../../CLAUDE.md` first.

## Where

- **qbs clone:** `~/code/qbs-ladder-trial`, branch `ladder-area-shipping` (push disabled). Its code is qbs `main` at
  `72d0cb468e`; commit `efd6f1b408` added only `ladder/` setup and `ladder.repo.json`.
- **Ladder v0.7.1, pinned:** `~/code/ladder-v071` (a worktree of `fix/v0.7.1-pilot`). Run
  `~/code/ladder-v071/plugins/ladder/bin/ladder` and read the skills and reference under
  `~/code/ladder-v071/plugins/ladder/`. Do not use `~/code/ladder` or an installed plugin.
- **Shared settings:** `ladder.repo.json` at the qbs root supplies:
  - the vocabulary (`ladder/vocabulary.ladder`);
  - the generator;
  - the schema (`ladder/qbs-schema.json`, fresh export);
  - conventions per language;
  - `mode`/`adopted`;
  - the `"generated"` files.

  Put your area's capabilities in your own `vocabulary.ladder` and list it in `"extra_vocabulary"`. Never copy a
  shared capability: `check` warns on copies and refuses changed ones. If a shared capability is wrong or incomplete,
  write it in `NOTES.md` for the coordinator.

## Projects (one agent each, in parallel)

| Project folder | Prefix | Files (repository-relative; never tests, stories, mocks or `.pseudo`) |
|---|---|---|
| `ladder/ship/api-station` | `shs` (services), `shk` (controller) | `qbs_api/qb_api_services/Stations/Shipping/{ShippingService.cs, ShippingService.Board.cs, ShippingStationService.cs, IShippingService.cs, IShippingStationService.cs, AxionControlNumber.cs}`, `qbs_api/qb_api/Controllers/Stations/Shipping/ShippingController.cs`, `qbs_api/qb_api_dtos/ShippingDtos.cs`, `qbs_api/qb_api_dtos/Stations/Shipping/{LoginRequest,LoginResponseWithRefresh,LogoutRequest,LogoutResponseWithRefresh}.cs` |
| `ladder/ship/api-assembly` | `sha` | `qbs_api/qb_api_services/Stations/Shipping/{ShippingAssemblyService.cs, IShippingAssemblyService.cs}`, `qbs_api/qb_api_dtos/Stations/Shipping/ShippingAssemblyDtos.cs` |
| `ladder/ship/library` | `shl` | `qbs_library_react/src/warehouse/shipping/` files for the station only: `index.ts`, `dtos/{index,shipment,shipping}.ts`, `dtos/shipments/*.ts`, `services/{index,shipping-workflow-service}.ts`, `services/shipments/*.ts` (not truck-driver, transfer-driver, freight-bill, carrier, assembly-location or delivery-viewer) |
| `ladder/ship/scanner-station` | `shc` | `qbs_scanner_react/src/features/shipping/{components,state,hooks,utils,stores}/**`, `guide/shipping.guide.ts`, `types.ts`, `index.ts` |
| `ladder/ship/scanner-navigation` | `shn` | `qbs_scanner_react/src/features/shipping/navigation/**` (including `ShippingAssemblyActionScreenAdapter.tsx`) |

- **Two pairs share code and call each other:**
  - the API controller calls the assembly service;
  - the navigation adapters call the station's components, state machine and hooks.

  Write those calls in `CALLS.md` like every other cross-project call.
- **`check_command` / `check_cwd`:** the same as the pilot (C#: `dotnet build ../ladder/auth/api/auth-check.slnx
  --nologo -v q` from `qbs_api`; library: `npx tsc --noEmit -p .` from `qbs_library_react`; scanner: `npx tsc
  --noEmit -p .` from `qbs_scanner_react`). Set `"baseline": "efd6f1b408"`.
- **`"tests"`:** add the area's own qbs tests to `"tests"`, as filtered runs only:
  - API: the test classes that cover these services and the controller, through `../ladder/env/qbs-api-tests.sh
    <Class> ...`;
  - scanner and library: the named vitest files, through `npx vitest run <files>`.

  Never a whole suite.

## What each transcription agent does

Follow the pilot handoff's steps 2 to 9 ([../20-alerts-pilot/HANDOFF.md](../20-alerts-pilot/HANDOFF.md)) with
v0.7.1's skills. Two points are new since the pilot:
- **Inserts:** what an insert leaves out is behaviour (transcribe skill).
- **Test-asserted values:** grep the area's tests for the literals they assert (CSS classes, test ids, texts) and put
  them in the English.

Don't stamp, don't commit, and stay inside your project folder plus marker comments in your own files.

**`NOTES.md`:**
- start and end time;
- counts;
- **every friction with Ladder,** with the exact command and output;
- whether a friction looks like one the pilot already fixed coming back.

## After transcription (the coordinator)

The same as the pilot:
1. merge the vocabularies;
2. link the projects;
3. `check --all`;
4. review and stamp (timed);
5. regenerate blind in a scratch copy;
6. verify: build, the area's tests, and a replay of recorded API scenarios;
7. make one change through the English across the API, library and scanner;
8. write the report in `trials/21-shipping-area/REPORT.md`.

During the round, a Ladder bug is recorded in the report, worked around if possible, and fixed only afterwards, in
v0.7.2.

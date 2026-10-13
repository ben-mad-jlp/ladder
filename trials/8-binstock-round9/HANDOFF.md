# Ladder round 9 handoff: an unseen slice across two apps (scanner binstock)

2026-10-12 · from Ben (drafted by Claude: "we need to keep iterating until we think that a full qbs repo
ladder version will be smooth")

## Goal

The same bar as round 8 (`CLAUDE.md`), on a slice with shapes not tried yet:
1. transcribe;
2. link and test;
3. regenerate blind;
4. make a change through the English;
5. regenerate;
6. review;
7. stamp.

No hand edits to generated code and no workaround the skills don't describe. Record every place the loop isn't
smooth.

The slice is the scanner's **Binstock Replenishment** upload: an offline-first React Native screen and its API.

| Layer | File | In the slice |
| --- | --- | --- |
| API controller | `qb_api/Controllers/Binstock/BinstockController.cs` | all (two routes, one shared upload) |
| API service | `qb_api_services/Binstock/BinstockService.cs` | all (one method: sign-off, transaction, rows) |
| DTOs | `qb_api_dtos/Binstock/UploadBinstockRequest.cs` | contract regions |
| Scanner hooks | `features/binstock/hooks/useBinstockOperations.ts`, `useSignOffApprovers.ts` | all |
| Scanner cache | `features/binstock/offline/useBinstockCache.ts`, `types.ts` | all |
| Scanner container | `features/binstock/components/BinstockScanScreen.tsx` | all (the view stays support) |
| Auth API (existing tree) | `EmployeeController.cs`, `EmployeeService.cs` | two routes and two methods the scanner calls, added to the round 4–5 tree |

New shapes: a cross-cutting approval routine (a shared service with its own transaction rules), the API's global
exception mapping, device storage, a React Native container, a client that defaults to production, and a link from
a new area into an existing tree that is itself mid-change (round 5 left `api.1.1` changed in the English only).

## Ground rules

As in round 8:
- Test database and test users only (new: employees 901–903 in `ladder/binstock/api/env/binstock-seed.sql`).
- Secrets from the environment.
- Stamping allowed in the trial branch only.
- Regeneration in a scratch copy, brought back with `ladder accept --from`.
- No edits to qbs tests; trial harness files are fine and listed in the report.
- The scanner's link test must refuse any request that isn't to the trial API on 127.0.0.1.

Plugin v0.6.3 (PR #7), run by path from its worktree.

## Phases

Each phase ends with `ladder check` on every project and a line in the report.

0. **Set up.** Branch `ladder-trial-r9` from `ladder-trial-r8`. Seed 901 (holds both sign-offs), 902 (operator
   only), 903 (holds the upload sign-off, no `dbo.EMPLOYEES` row).
1. **Transcribe** the API and scanner trees and the auth additions; per-area profiles; capabilities with tests for
   the approval routine and the scanner's storage, approver list and password check; a behaviour test for the
   container and cache; a link test scanner → API (both projects); replay scenarios recorded twice.
2. **Regenerate blind**, every build, in scratch. Record repair rounds, the qbs tests, the behaviour and link tests
   and the replay match.
3. **Stamp** the API and scanner projects.
4. **Change through the English** across both trees, regenerate in scratch, accept, test, stamp.
5. **Report**: findings by severity, what is general, what to fix in Ladder next.

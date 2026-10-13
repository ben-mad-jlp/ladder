# Ladder round 10 handoff: Unpick Shipment, dashboard to API (v0.6.4)

2026-10-12 · from Ben ("keep iterating until we think that a full qbs repo ladder version will be smooth";
"You keep going. Go until it's satisfactory"), drafted by Claude.

## Goal

The bar in `CLAUDE.md`, on a slice Ladder has not seen:
1. transcribe;
2. link and test;
3. regenerate blind;
4. change through the English;
5. regenerate;
6. review;
7. stamp.

No hand edits to generated code and no workaround the skills don't describe. This round also tries the
v0.6.4 fixes on new code:
- `ladder reference` for an approved change;
- project `"tests"`;
- `--blind --redo` on a stamped tree;
- binding files in the prompt;
- one shared with-API runner per repository.

## The slice

The dashboard's **Unpick Shipment** screen (route `/unpick`) and its API: load a shipment's committed containers,
tick them by scanning, and return them to restock at a location.

| Tree | Files | In the slice |
| --- | --- | --- |
| API | `Controllers/Logistics/UnpickShipmentScreenController.cs` | all |
| | `qb_api_services/Logistics/ShipmentService.Unpick.cs` | all (one part of the partial `ShipmentService`) |
| | the unpick DTOs | contract regions |
| Library | `commercial/sales/services/unpick-shipment-screen/unpick-shipment-screen-service.ts` | all |
| Dashboard | `features/unpick/api.ts`, `hooks.ts`, `UnpickScreen.tsx`, `sofia.ts`, `types.ts` | all |
| | `UnpickScreenView.tsx` | all (a presentational view, in the slice for the first time) |

**Shapes not tried before:**
- one part of a partial class, whose collaborators come from factories;
- two capabilities that live in large services outside the slice (unpick a committed container, move a container),
  each with its own transaction, called once per container;
- a presentational React view with its Storybook stories;
- an assistant (Sofia) screen definition, which is declarative data rather than steps.

## Ground rules (as before)

- **Test data only:** the trial database (`qbs_mssql_ladder` on 127.0.0.1:1436) only. Round 10 data is in
  `ladder/unpick/api/env/unpick-seed.sql`:
  - employees 911 (screen and unpick) and 912 (screen only);
  - sales order 99001 with shipments in Wait, Entered and Voided;
  - six containers;
  - four locations.
- **Secrets:** from `~/.qbs-ladder.env`, never in git.
- **Stamping:** allowed in the trial branch only.
- **Regeneration:** in a scratch copy, brought back with `ladder accept --from`.
- **qbs tests:** no edits; trial harness files are listed in the report.
- **Link tests:** they refuse any request outside the trial API on 127.0.0.1.

Plugin v0.6.4 (PR #10), run by path from its worktree.

## Phases

Each phase ends with `ladder check` on every project and a line in the report.

0. **Set up.** Branch `ladder-trial-r10` from `ladder-trial-r9`, then the seed, the reset and one shared
   with-API runner.
1. **Transcribe** the three trees:
   - the capabilities for the container services, with tests;
   - the slice's qbs tests and a behaviour test in `"tests"`;
   - link tests: dashboard to library to API;
   - replay scenarios, recorded twice, with the written rows observed.
2. **Regenerate blind**, every build, in scratch. Record the repair rounds, the tests and the replay match.
3. **Stamp** all three projects.
4. **Change through the English** across the trees, using `--redo` on the stamped trees. Then accept, test,
   `ladder reference` and stamp.
5. **Report:** findings by severity, what is general, and what to fix in Ladder next.

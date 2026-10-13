# Ladder round 8 handoff: an unseen slice, the whole loop (My Alerts)

2026-10-12 · from Ben (drafted by Claude: "we need to keep iterating until we think that a full qbs repo
ladder version will be smooth")

## Goal

Test the "good enough" bar in `CLAUDE.md` on a slice Ladder has never seen. Run the whole loop:
1. transcribe;
2. link and test;
3. regenerate blind;
4. make a change through the English;
5. regenerate;
6. review;
7. stamp.

No hand edits to generated code, and no workaround the skills don't describe. Record every place the loop
isn't smooth: that is what decides whether qbs can be transcribed as a whole.

The slice is the dashboard's **My Alerts** screen, a live, permission-gated screen. It has shapes the earlier
slices didn't:

| Layer | File | In the slice |
| --- | --- | --- |
| API controller | `qb_api/Controllers/Alerts/MyAlertsScreenController.cs` | all (7 one-line actions) |
| Shared actions | `qb_api/Controllers/Common/SharedAlertActions.cs` | `AlertEmployee`, `RunForAlertEmployeeAsync` and the 7 My Alerts actions (extension methods); the rest support |
| Service | `qb_api_services/Alerts/AlertService.cs` | the 7 My Alerts methods and their helpers (lines 716–957); the rest support |
| DTOs | the request and response types those use | contract regions |
| Library | `qbs_library_react/src/system/monitoring/services/alerts/my-alerts-screen-service.ts` | all |
| Dashboard | `qbs_dashboard_react/src/features/alerts/MyAlertsScreen.tsx` (container) and the My Alerts parts of `screen-hooks.ts` | container steps; the view stays support (presentational) |

New shapes here: behavior spread over three C# files, extension methods, an employee taken from the token, legacy
validation messages, a React container with react-query mutations, and three trees (API, library, dashboard).

## Ground rules

As in round 7:
- Test database and test users only.
- Secrets from the environment.
- Stamping allowed in the trial branch only.
- Regeneration in a scratch copy, brought back with `ladder accept --from` (v0.6.1).
- No edits to qbs tests.
- Migrations on the trial database only.

Plugin v0.6.2 or later.

## Phases

Each phase ends with `ladder check` on every project and a line in the report.

0. **Set up.** Branch `ladder-trial-r8` from `ladder-trial-r7`. Give the test users the My Alerts screen
   permission, and seed a few alerts.
1. **Transcribe** the three trees.
    - Write the profiles the v0.6.2 profile skill's way: general plus per-area files.
    - Use schema references for the alert tables, `calls:` across the trees, and capability tests for every
      `known:` line.
    - Write a link test for library and API, and one for dashboard and library if practical.
    - Write replay scenarios for all 7 endpoints (validation failures, missing alerts and permission included).
      Record twice.
2. **Regenerate blind**, all builds, in scratch. Record repair rounds per file, the replay match, and the qbs tests
   that cover the slice (filtered).
3. **Stamp** what the blind regeneration confirmed (the English is enough), with the working files untouched.
4. **Change through the English.** A rule that crosses all three trees:
    - the API refuses a scheduled alert whose description is longer than the column allows, with a clear
      message;
    - the library and the screen show it.

   Write the English, then check from the lock (record every flag), regenerate, test, replay, and stamp.
5. **Report**, against the `CLAUDE.md` bar:
    - Serious problems found: wrong code generated silently, a change that reached nothing, a check that couldn't
      be trusted.
    - Workarounds the skills don't describe.
    - Hand edits.

## What to report

| Measure | Round 7 | Round 8 |
| --- | --- | --- |
| Serious Ladder problems | 1 (N1) | |
| Workarounds the skills don't describe | | |
| Hand edits to generated code | 0 | |
| Blind regeneration: files clean without repair; replay match | 4 / 4; 60 / 67 (round 4, auth) | |
| Change through the English: flagged on every tree from the lock | yes | |
| Whole loop completed | yes, with copied-in regeneration | |

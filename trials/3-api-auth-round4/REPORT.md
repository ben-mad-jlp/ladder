# Ladder trial report, round 4: qbs_api auth with schema references

2026-10-12 · for Ben · qbs branch `ladder-trial-r4` in `~/code/qbs-ladder-trial` (push disabled) · nothing stamped ·
plugin at ladder commit 97efe96 (identical to ladder-plugin-3.zip; the session's installed plugin is still v2,
so the v4 tool was run from the clone and the v4 skills were read from it).

Short version: blind regeneration converged on the first try. All four generated files built cleanly with
tests, with no repair. 60 of 67 replayed requests are identical, and the other 7 are the case-insensitivity
decision you made in phase 3. Schema references made the round 3 failure (camelCase columns) impossible, and
a real migration went through `check` with no false `schema-changed`. Two problems remain. Ladder still can't
see across the API/React seam: an end-to-end run caught a wrong vocabulary entry that `check` passed. And the
`schema-changed` check can't be exercised until you stamp.

## 1. Slice

Same as round 3, plus two library members added to the React tree for change (a).

| File | In the slice |
| --- | --- |
| `qb_api/Controllers/Auth/AuthController.cs` | all: 5 endpoints + 4 cookie helpers (build `controller`) |
| `qb_api_services/Infrastructure/JwtService.cs` | all (build `jwt`) |
| `qb_api_services/Employees/EmployeeService.cs` | 8 of ~60 members; the rest `@support` (build `employees`) |
| `qb_api_dtos/AuthDtos.cs` | 8 of 12 classes (build `dtos`) |
| `qb_api_models/Models/Employee_MainTable.cs` | now `@support` only, never generated; no build (see F3) |
| `qbs_library_react/src/core/auth/services/auth-service.ts` | new: `login` ([authsvc.1]); the rest `@support` |
| `qbs_library_react/src/components/LoginModal.tsx` | new: the form submit ([login.1]); the rest `@support` |

## 2. Numbers

| Measure | Round 3 | Round 4 |
| --- | --- | --- |
| Replay runs matching after blind regeneration | 14 of 67 | **60 of 67**. All 7 differences come from the phase 3 DECISION (names match ignoring case); 60 of 60 requests whose intended behavior did not change are identical |
| Files clean after regeneration, without repair | 0 of 5 (tests did not compile) | **4 of 4** generated files (dtos, controller, jwt, employees): whole build including all 4 test projects 0 errors; filtered auth tests 45 / 45. The entity is support code now, so it is not generated |
| Repair rounds, per file | 3 `repair` runs (entity, controller ×2) | **0** for every file |
| Mutants caught | tests 0 / 3, replay 3 / 3 (+ m4: tests 1, replay 0) | same: tests 0 / 3, built-in replay 3 / 3; m4 (grace window 30 → 31 s): tests caught it, replay 67 / 67 identical, not caught |
| Schema references written; problems `check` found | n/a | 8 `reads:` lines (22 entity names), 1 `writes:`; 54 `[[...]]` (21 distinct), 55 after change (b). `check` found **0 problems on the first pass**; in phase 6(b), 1 problem on purpose (the unknown `LastSignInUtc`), gone after the migration |
| Steps wrongly marked `schema-changed` after the migration | n/a | **0**. Measured from the facts `stamp` would record, before and after; `check` itself cannot show it without a stamp (F11) |

Other numbers:
- Built-in replay is repeatable: the original API recorded twice gave byte-identical traces for all 6 files.
  No password, JWT key or SA password appears anywhere in the trial folder (grep of `~/.qbs-ladder.env` values).
- Blind regeneration took about 7 minutes for 4 builds, one at a time: dtos 19 s, controller 1 min 54 s,
  jwt 2 min 0 s, employees 1 min 1 s, plus a full build after each (about 25 s).
- No `REFUSED` messages and no `REJECTED` regions in round 4.
- Time: setup and schema 6 min · English to schema 3 · decisions 2 · regenerate 8 · replay and mutants 15
  (alongside the regeneration) · phase 6: 15 · report 8.

### Phase by phase (each ended with `ladder check`)

0. **Set up.** Unpacked ladder-plugin-3.zip, then switched to the `ben-mad-jlp/ladder` clone when it appeared
   (same files, commit 97efe96). New branch `ladder-trial-r4` from round 3's `ladder-trial-api`, push disabled.
   Check: tree new (unapproved), code ok.
1. **Schema.** qbs_api has no EF migrations (its migrations are guarded SQL scripts), so there is no
   `ModelSnapshot.cs`. I wrote a small exporter (`ladder/auth/api/schema-export`) that builds each DbContext's
   model offline and writes Ladder's `json` kind: qbs 850 entities, reports 1, the two archive contexts 2 each.
   `ladder schema` lists every entity the auth code uses with the right tables and columns (`Employee.Main_TABLE`,
   `first_name`, `user_name varchar(10)`, the skip navigation `Authorizations` through `EmployeeAuthorization`, ...).
   Check: ok.
2. **Refer, don't describe.** Removed data block `Employee` (34 lines restating the table). Added `reads:` to the
   8 steps that query and `[[Entity.Member]]` on filters, ordering and what is loaded. Tagged the entity class
   `@support`. Retagged from the base commit: adopt-check ok (comments only). Check: 0 `schema-ref` problems,
   0 `two-databases` warnings (nothing in the slice writes yet).
3. **Case decisions.** QUESTION 7 ([emp.2]) and 13 ([emp.7]) are now DECISIONs: names match ignoring case. Seam S1
   is marked settled in `seam.md`; the React rule already said so. This is a behavior change: the code matched
   with case in C#, and the database is not involved in that comparison. Check: [emp.2] and [emp.7] stale in
   the working files (expected; regenerated only in scratch).
4. **Blind regeneration.** `check_command` now builds `auth-check.slnx` (the API plus all four test projects;
   qbs_api has no solution file). `regen --blind` per build in the scratch worktree: all clean, no repair.
   Check in scratch: every build ok, nothing stale.
5. **Replay.** Round 3's 67 requests run through the built-in `ladder replay` with `{{env:}}`, `save`/`{{var:}}`,
   the cookie jar, `--jwt`, `--record-headers set-cookie`, `--before-each env/reset.sh` and
   `--mask traceId,expiresAt,refreshToken`. Original vs regenerated: 60 / 67. Mutants re-recorded the same way.
   Check: comparisons and mutants as above.
6. **Two changes in English, then regenerate:** results in section 4.

## 3. Every replay difference

Blind regeneration (`regen-r4`) vs the original. All 7 come from the English (the phase 3 DECISION); none come
from the generator or the comparison.

| Request | Original | Regenerated | Cause |
| --- | --- | --- | --- |
| s01 #15 login 9001 with `["dashboard.alerts"]` (holds `Dashboard.Alerts`) | 401 no permission | 200 | English: [emp.7] ignores case |
| s01 #20 login 9002 with `["Dashboard.Alerts"]` (holds `dashboard.alerts`) | 401 | 200 | English: [emp.7] |
| s04 #5 validate 9002, `authType` `Dashboard.Alerts` | `valid: false` | `valid: true` | English: [emp.7] |
| s05 #2 picker `?authorizations=Dashboard.Alerts` | 9001, 9005 | + 9002 | English: [emp.2] |
| s05 #3 picker `?authorizations=dashboard.alerts` | 9002 | + 9001, 9005 | English: [emp.2] |
| s05 #4 picker `Dashboard.Automation,Dashboard.AlertSystem` | 9001 | + 9005 (holds `dashboard.alertsystem`) | English: [emp.2] |
| s05 #9 picker `" Dashboard.Alerts ,,Nope"` | 9001, 9005 | + 9002 | English: [emp.2] |

After changes (a) and (b), the regenerated API vs the blind-regenerated one: 65 / 67. The 2 differences are
the two missing-permission sign-ins in s01 (#17, #19), which now carry `code` and `missingAuthorizations` and
name the permission. Change (b) is not visible in any response (by design); the column was checked in the
database (section 4). Against the original, the changed API matches 58 / 67 (7 + 2).

## 4. Phase 6 results

**(a) A clear missing-permission error, API and React.**
- API English [api.1.1]: still a 401, plus `"code": "MISSING_PERMISSION"`, `missingAuthorizations` (the names as
  sent), and a message naming them ("You need the permission X to sign in. ..." / "You need one of these
  permissions to sign in: A, B. ..."). DECISION note: stays 401, so status-only callers keep working;
  settles seam S2.
- React English: transcribed two new steps first ([authsvc.1] `AuthService.login`, [login.1] the form submit;
  adopt-check ok), then changed them. `login` now rethrows a 401 with that code, and the form shows the API's text.
- **Flagged on both sides? Only on the side whose English changed.** Editing the API English flagged
  [api.1.1] and the controller's contract region; the React tree stayed "ok, nothing stale". Ladder has no link
  between the trees. It flagged the React steps only once I edited the React English myself.
- **Did the seam agree? Not at first, and Ladder could not tell.** I added a vocabulary capability
  `HTTP client` saying an ApiException's `message` is the body's `message`. `check` was satisfied, regeneration
  followed it, and it typechecked. An end-to-end vitest (the real `AuthService` and `LoginModal` against the
  regenerated API on the trial database) showed the library's HTTP client replaces the message of every 401
  with "Unauthorized". The API's text is only in `responseData`. I corrected the vocabulary
  (`known: ... a 401 always says "Unauthorized"`) and the React English, then regenerated. The test passed
  3 / 3: missing permission thrown with the API's text, wrong password still `null`, and the form showing
  "You need the permission Dashboard.Nope to sign in. Please contact your administrator.". The test is
  `ladder/auth/clients/harness/seam_login.test.tsx` on the qbs branch. The multi-name message was checked
  by hand with a request: 401 with "You need one of these permissions to sign in: Dashboard.Alerts,
  Scanner.Picking. ...".

**(b) Last sign-in time.**
- English first: [api.1.1] got `writes: Employee_MainTable` and "sets [[Employee_MainTable.LastSignInUtc]] ...
  with one UPDATE statement". `check`:
  `schema-ref [api.1.1] [[Employee_MainTable.LastSignInUtc]]: Employee_MainTable has no property or navigation 'LastSignInUtc'`.
  As intended.
- Then the property (`[Column("last_sign_in_utc")] DateTime?` in the entity's support region), the migration
  (guarded `ALTER TABLE ... ADD [last_sign_in_utc] DATETIME2 NULL`, in this repo's SQL style), applied only to
  the trial container by `env/reset.sh --apply` (which also rebuilds the reset backup), then the schema
  re-exported.
- `check` again: **the reference resolves** (`LastSignInUtc column last_sign_in_utc, datetime2, optional`); no
  schema problems.
- **Steps wrongly marked `schema-changed`: 0.** Compared before vs after the migration across all 11 steps that
  refer to the schema: no recorded fact changed, and the only new fact is api.1.1's `LastSignInUtc`. Entity
  facts are "table and key" only, so adding a column cannot flag steps that just read the table.
- Regenerated (`regen --build=controller`: only [api.1.1] and the controller's contract region; the other three
  files byte-identical) → `ExecuteUpdateAsync(s => s.SetProperty(e => e.LastSignInUtc, signedInAt))`.
  Build 0 errors, tests 45 / 45. Replay, then the database: 9002, the last one to sign in, has
  `last_sign_in_utc` = 32 s before the query (the scenario waits 32 s after signing in); the others are NULL.

## 5. Friction, in the order I hit it

- **F1 (setup) Install.** The handoff said zip, then the GitHub repo appeared mid-run. I could not install
  plugins from inside the session (auto mode blocked it in round 2 too). The v2 skills stayed loaded, and I
  ran the v4 tool by path. Someone needs to run
  `claude plugin marketplace add ben-mad-jlp/ladder && claude plugin install ladder@ladder`.
- **F2 (schema) No EF snapshot to point at.** An API whose migrations are SQL scripts has no `ModelSnapshot.cs`.
  "kind: json" worked, but writing the exporter was mine to do. Ladder could ship one: a tiny .NET exporter
  that builds the model offline, about 70 lines (`schema-export/Program.cs` on the qbs branch).
- **F3 (config) `"steps": []` means every step.** This is the same bug as round 3's `"data": []`. A
  support-only build for the entity reported 29 missing steps, so I dropped the build. The entity file keeps
  its `@support` tag, but no build checks it now.
- **F4 (blind) My profile leaked the answer.** csharp.md's data-access example was [emp.3]'s exact query,
  copied in round 2. Blind mode hides old regions but not conventions. I replaced the example before
  regenerating. Suggestion: `regen --blind` warns when a hidden region's lines appear verbatim in the
  conventions.
- **F5 (blind) Parent regions are kept.** `[api.1]` and `[jwt.1]` (class declaration, constructor) are "kept:
  holds nested regions". So round 1's constructor-order failure was not re-tested blind. The original
  constructors stayed.
- **F6 (replay) What the built-in replay loses compared with round 3's replay.py:**
  - no SQL count per request;
  - masking is by key everywhere, so a masked `refreshToken` no longer tells null from text, and `expiresAt`
    can't be compared as "120 minutes from now";
  - `wait` must ride on a request (round 3 had a standalone sleep);
  - `save` paths need `body.`.

  It worked, and it was repeatable.
- **F7 (check) Only the first difference per run is shown.** s05 had 4 differences and `check` showed 1. I wrote
  `harness/diff_traces.py` to list every one.
- **F8 (seam) No cross-tree link**, as in round 3: an API `out:` change does not touch the React tree.
- **F9 (vocabulary) A capability's description can be wrong and nothing checks it.** The HTTP client entry was
  mine and wrong (401 message). Only running both sides together found it. This is the most important
  finding of the round: a seam check needs to run code, or at least read the binding's source.
- **F10 (environment) Migration location.** Auto mode refused writing the migration into
  `qb_api_models/Migrations` (shared migrations folder). It lives in `ladder/auth/api/migrations/` on the
  trial branch instead, applied only to the trial database. This is not a Ladder problem.
- **F11 (schema) `schema-changed` needs a stamp.** Facts are only recorded by `stamp`, and the rules forbid
  stamping, so `check` could not show `schema-changed` at all. I measured with the tool's own `check_refs`
  (`trial/schema_facts.py`), no lock written. Suggestion: `ladder check --schema-since <git ref>`.
- **F12 (seam test) My first harness test asserted the wrong vocabulary.** It expected `err.message`. After the
  vocabulary was corrected I changed that harness expectation (a trial harness file, not a qbs test), and said
  so here.

## 6. Schema references: helped, noise, reader

- **Helped:**
  - The entity is no longer generated, so round 3's camelCase-column failure cannot happen.
  - The prompts carried exact tables, columns and navigations. Every query in the blind code used the right
    `Include`/`ThenInclude` chain and `Terminated != true`.
  - `[[Employee_EmployeeRoles.Role]]` / `[[Employee_Role.RoleAuthorizations]]` replaced vague "with each
    role's grants".
  - The unknown-member check for change (b) worked exactly as described.
- **Noise:**
  - `[[...]]` in [jwt.1.1]'s claim list (names, id) adds nothing the profile didn't give.
  - `reads:` lines repeat the entities the `[[...]]` already name.
  - About a third of the 54 references could go without loss.
- **Reader:**
  - The json reader read everything right, including the skip navigation ("through EmployeeAuthorization")
    and `char(2)` / `datetime2` / `decimal(9,2)` types.
  - The snapshot reader was not used (no snapshot).
  - One limit: an entity-only reference (`reads: X`) records "table, key", so a removed or retyped column
    used without `[[...]]` would not flag the step.

## 7. Steps awaiting your approval (nothing stamped)

- **API tree (`ladder/auth/api/api.ladder`):** all 31 steps.
  - Behavior changed this round, and changed in the regenerated code only (in scratch and
    `trial/gen/r4-changes`; the working files are still the original code, so `check` shows these stale):
    [api.1.1] (missing-permission answer, last sign-in), [emp.2] and [emp.7] (ignore case).
  - Reworded only (schema references): [api.1.2], [jwt.1.1], [jwt.1.2], [jwt.1.4], [emp.1], [emp.3], [emp.4],
    [emp.6], [emp.8].
  - 11 QUESTION notes remain open (round 3's 13 minus the two now decided).
- **React tree (`ladder/auth/clients/auth.ladder`):** new [authsvc.1] and [login.1] (transcribed, then
  changed), plus everything from round 1.
- **Vocabulary:** new capability `HTTP client` (with the 401 correction).
- **Migration:** `ladder/auth/api/migrations/20261012_AddEmployeeLastSignInUtc.sql`, for you to review if this
  ever leaves the trial.

## 8. Files (qbs repo, branch `ladder-trial-r4`, local only)

- `ladder/auth/api/`:
  - `api.ladder`, `ladder.json` (schemas, `auth-check.slnx`, builds);
  - `schemas/*.json` and `schema-export/`;
  - `migrations/`, `env/reset.sh` (`--apply`);
  - `harness/record4.sh`, `mutants4.sh`, `diff_traces.py`;
  - `traces/{original,regen-r4,regen-r4-changes,m1..m4}`;
  - `trial/gen/r4` (blind output, prompts and replies), `trial/gen/r4-changes`;
  - `trial/schema_facts.py` and `facts-*.json`, `trial/r4_regen.sh`.
- `ladder/auth/clients/`: `auth.ladder`, `ladder.json`, `harness/seam_login.test.tsx`,
  `trial/tag_clients_r4.py`.
- Still running or on disk:
  - containers `qbs_mssql_ladder` (127.0.0.1:1436, now with the new column) and `qbs_redis_ladder` (6390);
  - scratch worktrees `~/code/qbs-ladder-api-scratch` (regenerated code), `~/code/qbs-ladder-mutant-scratch`
    and `~/code/qbs-ladder-scratch`.

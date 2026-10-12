# Ladder API trial report: qbs_api auth (sign-in, refresh, sign-out, validate, login picker)

2026-10-11 · for Ben · branch `ladder-trial-api` in `~/code/qbs-ladder-trial` (push disabled) · nothing stamped ·
plugin v2 (ladder-plugin-2.zip) · phase 6 (a change through the English) waits for your pick.

## 1. Slice

| File | Lines | In the slice |
| --- | --- | --- |
| `qb_api/Controllers/Auth/AuthController.cs` | 358 | all: 5 endpoints + 4 cookie helpers |
| `qb_api_services/Infrastructure/JwtService.cs` | 302 | all: access tokens, refresh-token families in Redis |
| `qb_api_services/Employees/EmployeeService.cs` | 1,705 | 8 members (about 230 lines); the rest is `@support` |
| `qb_api_dtos/AuthDtos.cs` | 156 | 8 of 12 classes |
| `qb_api_models/Models/Employee_MainTable.cs` | 131 | the entity (EF configuration is attributes here) |

Chosen because it produces exactly what the React store turns into permission checks (`authorizations`,
`authorizationInfo.authorizationsWithSource`), so the API tree and the client tree from the last trial meet.
Read, not transcribed: `IEmployeeService`, `IJwtService`, `IAuthorizationResolver` (its rules are a vocabulary
capability), `EmployeeDTO.cs`, the AutoMapper profile; `QbsDbContext.cs` (10,484 lines) is too big to be a build.

## 2. Numbers

| Measure | Result |
| --- | --- |
| Baseline build and tests | build 0 errors (21 s); filtered auth tests 45 / 45 (`qb_api_tests.Auth.*`, `JwtServiceTests`, `AuthorizationResolverTests`), base main b848164610 |
| Tree size (steps, data blocks, lines) | 31 steps (api 10, jwt 13, emp 8), 11 data blocks, 1 rule; api.ladder 333 lines; 8 C# capabilities; csharp.md profile |
| QUESTION / DIFFERS / DECISION notes | 13 / 0 / 0 |
| Scenarios and requests recorded; two recordings identical? | 6 files, 67 requests; yes, traces and SQL counts identical across two recordings |
| Trial regeneration: rounds until replay matches | did not converge in 3 rounds (see below) |
| Replayed requests identical to the original | round 1 (controller + JwtService only): 65 / 67; round 3 (all five files): 14 / 67 |
| SQL commands per request: any that changed | round 1: none; round 3: all, because every employee query failed |
| Mutants caught: by tests / by replay | brief's three: tests 0 / 3, replay 3 / 3; a fourth (grace window 30 s -> 31 s): tests caught it, replay did not |
| Seam mismatches between API and client English | 10 (S1–S10 in seam.md), 2 that agree (S11, S12) |
| The change | not started: needs your pick and your migration |
| Time per phase | setup + baseline 8 min · transcribe 7 · record 11 · regenerate 18 (3 rounds) · mutants 8 · seam 3 · report 5 |

Regeneration rounds:
- **Round 1** (`generate --out`): controller and JwtService usable; EmployeeService (302 of 1,705 lines) and
  AuthDtos (68 of 156) lost every out-of-slice member, the DTOs were renamed after their data blocks, the entity
  had the wrong namespace casing. With round-1 controller + JwtService and the original rest: build ok, tests
  do not compile (constructor parameter order, `ValidateToken` renamed), replay 65 / 67 (the body parameter
  `dto` became `request`, which shows in the framework's 400 text), SQL counts identical.
- **Round 2** (fixes: English says the body is called `dto`; profile gets namespaces, constructors, names; blind
  `regen` after blanking regions in a scratch copy so support code stays): entity guessed two navigation types;
  `repair` refused (it reads errors in `@contract` regions as support code).
- **Round 3** (profile gets every navigation, entity property names, DbSet names, helper names; entity, jwt and
  employees regenerated; 3 `repair` runs for compile errors): build 0 errors; tests do not compile
  (`ValidateToken` renamed again); replay 14 / 67: the regenerated entity maps every property to a camelCase
  column (`firstName` instead of `first_name`), so every employee query fails at run time.
- What a round 4 needs: column names in data block Employee (an English gap: the database names are behavior),
  and the profile actually reaching `regen` prompts (a tool bug, F2).

Mutants (one line each, built, tested, replayed):
- m1 credential check without the "not terminated" filter: tests 45 / 45 pass; replay: terminated 9004 signs in
  (s01) and validates (s04). Security-relevant and invisible to the tests.
- m2 missing required permission answers 403 instead of 401: tests pass; replay catches it (s01).
- m3 `authType` of only spaces is checked instead of ignored: tests pass; replay catches it (s04).
- m4 re-presentation window 31 s instead of 30 s: a test fails; replay cannot reach the limit (s06 waits 32 s).

## 3. Notes for you to decide (all QUESTION)

1. `api.1.1`: "passwords are compared ignoring case, so \"Secret\" and \"SECRET\" both sign in"
2. `api.1.9`: "a list that ends up with no names (\",\" alone) answers an empty list, while an empty value answers every employee"
3. `jwt.1.2`: "[jwt.1.4] computes the expiry it reports with the given clock, while the token's own expiry uses the system time; with a test clock the two differ"
4. `jwt.1.4`: "the presented token's own record is never deleted, so re-presenting it within 30 seconds returns the same successor and after that revokes the family"
5. `emp.1`: "two employees with the same last and first name come back in no defined order"
6. `emp.1`: "direct grants and roles are loaded for every employee, though the login picker ([api.1.9]) sends only four fields"
7. `emp.2`: "the names are matched with case, while the permission resolver and the React store ignore case, so \"dashboard.alerts\" finds nobody that \"Dashboard.Alerts\" finds"
8. `emp.2`: "resolves permissions one employee at a time (several queries per employee)" (28 SQL commands for one picker request with 4 employees, s05 #2)
9. `emp.4`: "a role grant stored in a different case from the catalog's spelling of a direct grant is \"already listed\" (ignoring case) but not found by the exact-name lookup, and fails with an error (sign-in answers 500)" (read from the code; the seed does not reproduce it)
10. `emp.4`: "the effective names keep the case the grant rows store ... while this list uses the catalog's spelling ..., so the two lists in the login answer disagree on case" (seen for 9005)
11. `emp.4`: "blacklisted entries stay in the list (marked), so a client reading sources without the flag shows a permission the employee does not have"
12. `emp.6`: "the effective names come in the resolver's order, which is database order on a cache miss and alphabetical on a cache hit, so two sign-ins in a row can list them differently" (seen: s01 #1 vs #2)
13. `emp.7`: "same case rule as [emp.2]; signing in with `authorizations: [\"dashboard.alerts\"]` is refused for someone who holds \"Dashboard.Alerts\"" (seen: s01 #15)

Outside Ladder: the API's startup authorization seeding fails on a clean schema
(`FK_RoleAuthorizations_Authorization`: a role grant names an authorization the catalog seeder did not create).

## 4. Seam findings

See `seam.md` (both sides quoted). The ones that matter: S1 case rules (the client's rule cites the API, but the
API's required-permission check and picker filter are case-sensitive); S2 the client turns "you lack the
required permission" into "invalid credentials"; S3 `refreshToken` typed as always present, absent for the
dashboard; S4/S5 sources are joined strings and include blacklisted grants, which the client's English and types
do not expect; S8 roles include expired memberships; S9 the library's validate response type is wrong in every
field (no callers), the scanner types `employeeId` as text.

## 5. Friction, most serious first

1. **No blind regeneration of a partly-transcribed file** (generate/regen). `generate` writes the whole file from
   the English and drops every `@support` member (EmployeeService 1,705 -> 302 lines); `regen` keeps support code
   but shows the generator the current region code. Worked around by blanking regions in a scratch copy and
   running `regen`. Wanted: `generate --keep-support` (or `regen --blind`).
2. **`regen` prompts for step regions leave out the build profile** (tool bug). Only `generate` and `@contract`
   prompts include `conventions`. Every name, constructor and DbSet rule added to csharp.md after round 1 never
   reached the step regions in rounds 2–3; `ValidateToken` was renamed in both rounds.
3. **Build checks miss what callers and tests see** (generate). The compile check passes back only errors inside
   the generated file (a DTO rename that broke every caller "generated" fine), and it builds the API project, not
   the tests (constructor order and method names only fail there). Wanted: build the whole solution including
   tests, and pass every error to the regions they implicate.
4. **The schema is behavior the format doesn't ask for** (format/profile). Data block Employee listed fields and
   lengths, not column names; the regenerated entity compiled, passed the SQLite-backed tests (their schema comes
   from the same model) and failed on SQL Server. Wanted: data blocks for entities say `stored as <table>.<column>`,
   and the transcribe skill asks for it.
5. **`ladder replay` can't drive an auth API** (verify). No chaining of response values into later requests, no
   cookies or response headers, passwords would sit in scenario files, masking hides tokens instead of comparing
   what they mean. Wrote `harness/replay.py` (same trace format) with `{{env:}}`, `save`/`{{var:}}`, a cookie jar,
   Set-Cookie recording, JWT claims, relative times, and SQL counts.
6. **`repair` can't fix `@contract` regions** (repair). Errors there are reported as "error in support code, not
   regenerated".
7. **Starting a real API safely is most of the setup** (verify skill). Hard-coded report database, device and
   e-commerce URLs, hosted services, a startup seeder that writes, and an authorization cache in Redis that
   survives a database restore. The skill says "fresh test database"; it should say "find every outbound
   connection and background writer first, and reset caches with the database".
8. **The brief's SQL-count method didn't work** (verify). This API's DbContexts are built without the app's
   logger, so EF never logs a command; counted with an Extended Events session on the trial server instead.
9. **Parallel `regen` runs share one log folder** when started in the same second, and v2's `generate --out`
   swaps files into the real path to compile, so parallel generations in one tree would compile each other's
   output. Ran generation one at a time (6.5 min for round 1).
10. **One step at a time loses cross-step names**: `regen` wrote `emp.8` down to `emp.1`, so `emp.6` was written
    before `emp.4` and guessed its helper's name.
11. `"data": []` on a build is treated as "all data blocks" (hashes show the controller covering every block).
12. Retagging before approval needs the untagged base commit (`git show <base>:`, `adopt-check --base <base>`);
    the skill's tip says HEAD, which is the tagged version once committed.
13. Mutants: `check` prints "caught" for a mutant but never the value that differed (fine for a pass/fail, but the
    report needed a separate diff to say what each mutant broke).

What v2 fixed from the React trial, confirmed here: `"traces"` per build (no symlinks), `"mutant": true`
(caught / NOT CAUGHT), `--builds`, unknown trace step names reported (it flagged the React harness's `input`
until listed in `extra_steps`), `init` naming the reference build, the hand-edit guard (it refused to overwrite a
region I had blanked until `--discard-hand-edits`).

ASP.NET / EF / SQL Server behavior the skills did not prepare for: the body parameter's name appears in the
framework's 400 text; a query value of only spaces becomes "not given" before the action runs; SQL Server lets a
foreign key match in a different case, so stored grants and catalog names differ in case; skip navigations
return the catalog's spelling while the resolver returns the stored one; the resolver's Redis cache changes the
order of lists between two identical requests.

## 6. Where the English was hard to write

- The sources algorithm (`emp.4`): five ordered sentences, and the first replay showed one of them wrong (direct
  grant names come from the catalog, not the grant row).
- Case: every comparison needed "ignoring case" or "exactly, with the same case" spelled out, and which spelling
  of a name ends up where.
- Order: "in collection order", "in the resolver's order", "ordered by name" each needed saying; the resolver's
  order depends on a cache, which is hard to say as a rule.
- Framework behavior that isn't in the code (the 400 text naming `dto`, whitespace query values) only surfaced by
  replaying.
- EF shape (includes, what is loaded with each employee) reads naturally as "with division, direct grants and
  role memberships with each role's grants"; the database names behind it were the gap.

## 7. Files

- Branch `ladder-trial-api` in `~/code/qbs-ladder-trial`; scratch worktree `~/code/qbs-ladder-api-scratch`.
- Ladder projects: `ladder/auth/api/` (this) and `ladder/auth/clients/` (moved React project); shared
  `ladder/auth/vocabulary.ladder` and `ladder/auth/conventions/`.
- Scenarios `ladder/auth/api/scenarios/`; traces `ladder/auth/api/traces/<build>/`; SQL counts `ladder/auth/api/sql/`.
- Harness `ladder/auth/api/harness/` (`replay.py`, `record.sh`, `mutants.sh`, `show.py`); round files
  `trial/gen/r1`, `r2` logs, `r3`; `trial/blank_regions.py`, `trial/tag_api.py`.
- Test environment `ladder/auth/api/env/` (`containers.sh`, `api.sh`, `reset.sh`, `seed.sql`, `lib.sh`); secrets in
  `~/.qbs-ladder.env` (outside git). Containers `qbs_mssql_ladder` (127.0.0.1:1436, with the `ladder_count` XE
  session) and `qbs_redis_ladder` (127.0.0.1:6390) are still running.
- Log `ladder/auth/api/trial/log.md`; seam `trial/seam.md`.

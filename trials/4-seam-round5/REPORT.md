# Ladder round 5 report: links between the API and React trees

2026-10-12 · for Ben · qbs branch `ladder-trial-r5` in `~/code/qbs-ladder-trial` (push disabled) · nothing
stamped. The plugin is v0.5.0 at ladder commit 0eb4520. I couldn't install plugins from inside the session,
so the tool ran by path from a clone of `ben-mad-jlp/ladder` and I read the skills there. The session still
has the old v2 skills loaded.

Short version: both round 4 gaps are closed.
- **The API change reached the React side before anyone touched the React English.** `[authsvc.1]` showed
  `linked-changed` with the contract's before and after, and the link test showed `test-stale`.
- **The wrong HTTP client claim was caught before any code was generated.** `ladder test` reported it as
  `test-failed`.
- **The new tests found a second imprecise claim.** "Alphabetical" turned out to mean culture-sensitive order.
- **The new SQL counts (`--observe`) found a generator error that round 4 missed.** Round 4's blind run
  called the wrong service method in `[api.1.8]`. Its answers were identical, so replay couldn't see it,
  and round 4's report was wrong to say no difference came from the generator. A one-line profile fix
  stopped it.

Gaps remaining:
- `has-callers` never appears before a stamp.
- `[login.1]`, which consumes the API's answer through `[authsvc.1]`, isn't flagged.
- A few warnings fire on the wrong project or on capabilities with nothing to test.

## 1. Slice

The same as round 4, unchanged:
- API: `AuthController.cs`, `JwtService.cs`, 8 members of `EmployeeService.cs`, 8 classes of `AuthDtos.cs`,
  and the `Employee_MainTable` entity as support code.
- React: round 1's five files, plus `AuthService.login` (`[authsvc.1]`) and the `LoginModal` submit
  (`[login.1]`).

The base for phases 4 and 5 is **`f1bdecdf94`**:
- `[api.1.1]`, `[authsvc.1]`, `[login.1]` and the `HTTP client` capability are back to before round 4's
  change (a), the HTTP client in its first, wrong form;
- change (b), the last sign-in time, is kept.

## 2. Numbers

| Measure | Round 4 | Round 5 |
| --- | --- | --- |
| API change flagged on the React side before the React English was touched | no | **yes**: `linked-changed` on `[authsvc.1]` (with `--since=f1bdecdf94`) and `test-stale` on the link test (with or without `--since`) |
| Calling steps flagged `linked-changed`, of those that call `[api.1.1]` | n/a | **1 of 1** (`[authsvc.1]`, the only step that sends the request). `[login.1]`, which handles the answer through `[authsvc.1]`, is not flagged (F9) |
| Wrong HTTP client claim caught by `ladder test` before generation | no (found by a hand-written end-to-end test) | **yes**: `test-failed` before any code was regenerated |
| Capabilities with a `test:` line, of those with `known:` lines | 0 | **5 of 7**: HTTP client, read employees, effective permissions, key-value store, signed access token. Skipped: console warning and session store (React only; section 6) |
| Link test passes after the change, both sides regenerated | 3 / 3 by hand | **3 / 3** through `ladder test`, from a clean shell |
| Replay: two recordings of the original API identical, with the new masks and `--observe` | yes (without them) | **yes**: 67 / 67, SQL counts included |
| Blind controller regeneration builds and replays (now including its constructor) | constructor not regenerated | **yes**: whole check build 0 errors, auth tests 45 / 45, replay 67 / 67 identical to the normal regeneration. After the profile fix (F12), the SQL counts match the original too |

Other numbers:
- **Replay of the round 5 API** (both changes regenerated, normal `regen`):
  - 67 / 67 identical to round 4's changed API.
  - 58 / 67 against the original: the same 7 case-decision and 2 missing-permission differences as round 4.
  - Every successful sign-in now runs 2 more SQL commands (change (b)'s UPDATE).
- **`check --all-differences`** listed 26 differing results, against 23 without the flag. In s05 each of the 4
  differences was shown with its request (`result 2 (request #2 GET /api/auth/employees?authorizations=...)`).
- **Time:** setup and test data 10 min · phases 1–3: 15 · phase 4: 25 · phase 5: 20 · phase 6: 35 · report 10.

## 3. Phase by phase (each ended with `ladder check`)

0. **Set up.** Branch `ladder-trial-r5` from `ladder-trial-r4`, push disabled.
   - The trial containers had been removed after round 4. `env/containers.sh` recreated them.
   - `reset.sh --build` rebuilt the seeded backup, and round 4's migration was applied again.
   - A recording of the original API matched round 4's: 67 / 67.
1. **Back to before change (a)** using git (`trial_r5_revert.py`: step text from `f7ab9f511e`, the capability from
   `581ccd9b78`), with change (b)'s two lines kept. Commit `f1bdecdf94`. `check`: `[api.1.1]` stale in the
   working files, as expected.
2. **Links.** Clients: `"links": {"api": ...}`. API: `"links": {"clients": ...}`. `calls: api [api.1.1]` on
   `[authsvc.1]`.
   - The React tree has no steps for refresh, validate or the login picker, so there was nothing else to mark.
   - `check`: no `link` problems, and `untested-link [api] authsvc.1 call api, but no test runs both sides
     together; add "test": "<command>" to links.api`.
   - Adding `calls:` made `[authsvc.1]` stale (F3). I retagged it from the base commit; adopt-check: comments
     only.
3. **Link test.** `harness/with_api.sh harness/seam_login.test.tsx` works from `env -i`. It starts the
   containers if needed, resets the data, builds and starts the API, copies the test into the library, runs it,
   then stops the API and removes the copy.
   - Three cases: a sign-in that succeeds, a wrong password, a missing permission. The missing-permission case
     expected the old behavior: nothing is answered and the form shows "Invalid credentials".
   - `ladder test`: 1 / 1.
4. **Vocabulary tests.**
   - `clients/vocab/http-client.test.ts` calls the real `HttpClient` against the API. With the wrong claim, it
     failed and `check` said `test-failed`.
   - I corrected the claim as in round 4, and `check` said `test-stale` until the rerun, which passed.
   - I edited the one case that asserted the claim. That file is a trial harness file.
   - The API capabilities run through a .NET probe (`api/vocab/probe`, `api/vocab/run.sh <case>`) against the
     trial database and Redis. All 4 pass after one claim was made precise (F7).
5. **Change (a), the main measurement:** section 4.
6. **The other v0.5 fixes:** section 5.

## 4. Phase 5: change (a) through the English

1. **API English only.** Round 4's final `[api.1.1]`: a 401 with `code`, `missingAuthorizations` and a message
   naming the permission.
   - `check --since=f1bdecdf94` on the clients project printed:
     ```
     linked-changed  [authsvc.1] calls api:api.1.1, whose contract changed since f1bdecdf94: was out: 200 with LoginResponse; 401 or 500 with `message`; now out: 200 with LoginResponse; 401 with `message` (and, for a missing permission, `code` and `missingAuthorizations`); 500 with `message`; re-read this step (and the code that handles the answer), then approve
     test-stale      [link api] what it tests changed since it last ran (2026-10-12); run `ladder test`
     ```
     Both told me what to do. `linked-changed` shows the old and new contract, so I knew exactly what to
     re-read. `[login.1]` was not flagged (F9).
   - `check` on the API project, with and without `--since`, printed **no `has-callers`** (F10).
2. **The API regenerated** (`regen --build=controller`, normal) in the scratch copy.
   - `ladder test`: the link test showed `test-stale`, then **passed**.
   - That is correct, not a miss. The old client still turns every 401 into "nothing", so the base cases still
     held. The change was caught by `linked-changed` and `test-stale`, not by a failure.
3. **React English** (`[authsvc.1]` rethrows the failure with the code; `[login.1]` shows
   `responseData.message`). I updated the link test's missing-permission case (a harness edit), then
   regenerated both React steps normally.
   - **The generated `LoginModal` read `responseData.message` on the first try.** The capability was already
     correct and tested before generation. Round 4 needed a second English edit and regeneration to get there.
   - `tsc` 0 errors; `ladder test` 6 / 6 (5 capabilities + the link); replay as in section 2.

Compared with round 4, Ladder caught on its own:
- the API change on the React side before its English was touched;
- the wrong library claim before generation.

Round 4 found both by running both sides by hand after generating.

## 5. The other v0.5 fixes, one line each

- **Support-only build: worked.** The entity build with `"steps": []` reports
  `support only ("steps": []): checks tags, hand edits and exports; implements no steps` and is ok.
- **Replay: worked.**
  - `--mask traceId,refreshToken:presence,expiresAt:time` recorded `"now+120m"` and `"<text>"`.
  - The standalone `{"wait": 32}` and the bare `save` paths worked.
  - `--observe env/sqlcount.sh` recorded each request's SQL count.
  - Two recordings of the original: 67 / 67 identical.
- **Differences: worked.** Every difference is listed with its request, and `--all-differences` lifts the cap.
  One snag: values are cut at about 200 characters, which hides the `observed` count at the end of a long body
  (F13).
- **Blind regeneration: worked.**
  - The controller's class declaration and constructor were regenerated ("written blind around its nested
    regions (381 lines)").
  - It builds, passes 45 / 45, and replays 67 / 67 against the normal regeneration.
  - One leak warning, on 3 constructor lines the profile fixes on purpose. The warning says this case is fine.
  - The blind controller made the same wrong call in `[api.1.8]` as round 4 (F12).
- **Schema: worked**, with one false alarm.
  - `check --since=581ccd9b78` (before round 4's migration) and `--since=f7ab9f511e` flag nothing for the new
    optional column.
  - A required `sign_in_count` (in a throwaway commit, applied to the live trial database, then reverted)
    flagged only the writing step:
    `schema-changed  [api.1.1] the schema it refers to changed since 2f58c53fb3 (qbs:Employee_MainTable.SignInCount added, column sign_in_count, int, required (writes must now set it)); re-read the step, then regenerate its code with --redo`.
  - The false alarm: `[api.1.1]` only updates an existing row, so "writes must now set it" doesn't apply
    (F14).
- **EF exporter: works, after a workaround** (F15).
  - For `QbsDbContext` and `ReportDbContext`, its JSON matches round 4's exporter on all 850 shared entities:
    tables, keys, columns, types, required, lengths and navigations.
  - It adds 15 entities mine skipped: the many-to-many join tables such as `EmployeeAuthorization`. That's
    better.
  - It also adds a `generated` flag.
  - It can't build `PoArchiveYearContext` or `UsageArchiveYearContext`, because their constructors take a year
    as well as the options.

## 6. Capabilities with `known:` lines

| Capability | Test | Result |
| --- | --- | --- |
| HTTP client (React) | `clients/vocab/http-client.test.ts` (real client against the API) | wrong claim → `test-failed`; corrected → ok |
| read employees | probe `read-employees` | ok: a query filter ignores case and C# `==` doesn't; expired direct grants are loaded |
| effective permissions | probe `effective-permissions` | failed on "alphabetical" (F7); claim made precise → ok |
| key-value store | probe `key-value-store` | ok: in 50 rounds of 8 concurrent `When.NotExists` writes, exactly one won each time |
| signed access token | probe `signed-access-token` | ok: "JWT Key not configured" |
| console warning, session store (React) | skipped | out of this round's scope (the handoff asks for the API's). Both are practical: a `console.warn` spy, and zustand's `subscribe` |

## 7. Friction, in the order I hit it

- **F1 (setup) Install.** I couldn't install from inside the session (round 4's limitation), so I used the
  clone and the tool by path.
- **F2 (setup) The test data had to be rebuilt.** I had removed the containers after round 4.
  `reset.sh --build` needs the passwords exported first (my script; the first run failed with
  `KeyError: 'LADDER_PW_FULL'`).
- **F3 (links) Adding `calls:` makes the code stale.** The step's hash covers `calls:`, so `[authsvc.1]`'s
  region went stale although its code needs no change. I retagged it with my tagging script. A false alarm:
  `calls:` doesn't change what the code must do.
- **F4 (tests) `untested-capability` fires on capabilities with no `known:` lines.** That's 5 of them
  (unauthorized page, employee blacklist, wire shape, random token, diagnostic log), but the message says
  "nothing checks that the binding behaves as its known: lines say". I'd turn it off when there are no
  `known:` lines.
- **F5 (tests) The shared vocabulary leaks between projects.**
  - The API project ran the TypeScript HTTP client test, which none of its steps use.
  - The clients project warns `test-not-run` for the 4 C# capability tests, because results are recorded per
    project.
  - Suggestion: only consider capabilities a project's steps `use:`, and share results for a shared
    vocabulary.
- **F6 (tests) `ladder test` runs commands in `check_cwd`** (the library folder for clients). I found that by
  reading the tool, and every path in a `test:` line is relative to it. Worth one line in the format reference.
- **F7 (claims) "Alphabetical" was imprecise.** The resolver sorts with `OrderBy(a => a)` (culture-sensitive),
  not ordinal. My test assumed ordinal and failed. The claim now says which, and the test checks it. That's a
  second claim corrected by a test this round.
- **F8 (tests) The `test-failed` message cuts off the useful part.** It shows the last 8 lines of output
  trimmed to 400 characters, the source lines around the failed `expect`, but not vitest's expected/received
  values. "Unauthorized" never appeared in `check`, so I had to rerun by hand to see what the client did.
- **F9 (links) Indirect callers aren't flagged.** `[login.1]` handles the API's answer through `[authsvc.1]`,
  in the same tree. After the API change it showed nothing. The link test covers it, but `check` alone
  doesn't. Suggestion: mark steps that use a `linked-changed` step as needing a re-read too.
- **F10 (links) `has-callers` needs a stamp.** It compares with the lock's hash and ignores `--since`, so before
  any approval it never appears. I couldn't paste one.
- **F11 (tests) Editing a test file doesn't make its test stale.** The hash covers the capability text and the
  command, not the test file. I edited two harness files without any `test-stale`.
- **F12 (generator) `--observe` found a round 4 error that replay couldn't see.**
  - Round 4's blind `[api.1.8]` called `IEmployeeService.HasAuthorizationAsync` (out of the slice), not
    `[emp.7]`'s `HasAnyAuthorizationAsync`. The answers were identical for every scenario, but each validate
    with an `authType` ran 4 fewer SQL commands.
  - Round 4's report ("none from the generator") was wrong here.
  - The blind run repeated it, because nothing told the generator which method `[emp.7]` is. I added the
    mapping to the profile, and the next blind run called the right method, with SQL counts matching the
    original.
  - Suggestion: put the called step's own signature in the prompt when the English says "[emp.7] says", as
    v0.5 already does for `calls:` across trees.
- **F13 (check) Long values are cut at about 200 characters**, which hides the `observed` count after a long
  body. I compared SQL counts with my own script (`harness/diff_traces.py` plus a few lines).
- **F14 (schema) The required-column warning doesn't tell an UPDATE from an INSERT.** "writes must now set it"
  is wrong for a step that only updates existing rows.
- **F15 (exporter) Three problems:**
  - the README's `-p:TargetFramework=net9.0` doesn't work: NuGet's restore drops that global property, so
    the project's net8.0 default wins (`NU1201`, with `dotnet run` and `dotnet build` alike). I ran a copy
    with `<TargetFramework>net9.0</TargetFramework>` instead;
  - the README says `--schema-since`, but the option is `--since`;
  - contexts with extra constructor parameters aren't supported.

No `REFUSED` or `REJECTED` messages. I wanted no hand edits to generated code.

## 8. False alarms

- `[authsvc.1]` going stale for a `calls:` line (F3).
- `untested-capability` on capabilities with nothing to test (F4).
- `test-not-run` and cross-language test runs from the shared vocabulary (F5).
- "writes must now set it" on an UPDATE-only step (F14).

The warnings I'd turn off: F4, and F5's cross-project ones. The constructor leak warning was correct and
says so, so I'd keep it.

## 9. Steps awaiting approval (nothing stamped)

- **API tree, all 31 steps.**
  - Changed this round: `[api.1.1]` (back to the base, then change (a) again).
  - Still stale in the working files (regenerated only in scratch, as the rules require): `[api.1.1]`,
    `[emp.2]`, `[emp.7]`.
- **React tree:** `[authsvc.1]` (change (a), plus `calls: api [api.1.1]`), `[login.1]` (change (a)),
  and everything from round 1.
- **Vocabulary:**
  - `HTTP client`: corrected claim plus a `test:` line.
  - `effective permissions`: the order claim made precise, plus a `test:` line.
  - `test:` lines added on read employees, key-value store and signed access token.
- **Profile (`conventions/csharp.md`):** the step-to-method mapping for `IEmployeeService` (F12).
- **Links:** both `ladder.json` files.

## 10. Files (qbs repo, branch `ladder-trial-r5`, local only)

- `ladder/auth/clients/`:
  - `harness/with_api.sh` (runs a vitest file against the API from a clean shell);
  - `harness/seam_login.test.tsx` (the link test);
  - `vocab/http-client.test.ts`.
- `ladder/auth/api/`:
  - `vocab/probe` and `vocab/run.sh` (C# capability tests);
  - `env/sqlcount.sh` (the `--observe` SQL count);
  - `harness/record5.sh`, scenarios in v0.5 form;
  - `traces/{original,regen-r5,regen-r5-blind}`;
  - `trial/gen/r5` (regenerated files and prompts).
- `ladder/auth/trial_r5_revert.py` (phase 1).
- Still running or on disk:
  - the trial containers `qbs_mssql_ladder` and `qbs_redis_ladder`;
  - the scratch worktree `~/code/qbs-ladder-r5-scratch` (the round 5 regenerated code).

# Ladder round 5 handoff: links between the API and React trees

2026-10-12 · from Ben

## Goal

Round 5 tests whether Ladder now catches a change that crosses from the API tree to the React
tree, and a wrong claim about a library, without someone running both sides by hand first.

Round 4 (`../3-api-auth-round4/REPORT.md`) found the two gaps this round is about:

- **F8:** changing the API's English left the React tree "ok, nothing stale".
- **F9:** a vocabulary entry said the HTTP client passes the API's error message through. `check`
  accepted it, generation followed it, it typechecked, and only an end-to-end test showed the
  client replaces every 401's message with "Unauthorized".

Plugin v0.5.0 adds two things for them:

- **Links:** `calls: api [api.1.1]` on a client step, plus `"links"` in each `ladder.json`. A change
  to the called step's contract shows the caller as `linked-changed`; the API side warns
  `has-callers`.
- **Tests for claims:** `test:` lines on vocabulary capabilities and a `"test"` command on a link.
  `ladder test` runs them and records the results; `check` fails on a failed test and warns about
  missing or out-of-date ones.

It also fixes the rest of round 4's friction; phase 6 exercises those fixes.

The code is throwaway, as in round 4: judge every result by what it says about Ladder.

## Ground rules

- **Test database and test users only.** Never point anything at production or a shared service.
- **Secrets come from the environment.** They never go into git, traces, logs or the report.
- **Approval is Ben's.** Do not run `ladder stamp`. Use `ladder check --since=<commit>` wherever
  a check would otherwise need a stamp (schema and link changes), and say which commit you used.
- **No hand edits to generated code.** Change the English and regenerate, or use `ladder repair`.
  If a fix can only be made by hand, stop and report it as friction.
- **Don't edit qbs tests** to make them pass. Trial harness files are yours; say when you change one.
- **Work on a branch with push disabled** in the qbs repo. Blind regeneration happens in a scratch
  copy, never over the working files.
- **Migrations:** allowed on the trial database only, as in round 4.

## Phases

Each phase ends with `ladder check` and a line in the report.

0. **Set up.**
    - Install or update the plugin: `claude plugin marketplace add ben-mad-jlp/ladder` (or
      `claude plugin marketplace update ladder`), then `claude plugin install ladder@ladder`. Note
      the commit (`0eb4520` or later).
    - If you can't install from inside your session (round 4 couldn't), clone `ben-mad-jlp/ladder`,
      run the tool by path, read the skills from the clone, and say so in the report.
    - Make branch `ladder-trial-r5` from round 4's `ladder-trial-r4`, push disabled.
1. **Go back to before change (a).** Round 4's change (a), the missing-permission error, is the
   change this round repeats.
    - Put the English of `[api.1.1]`, `[authsvc.1]` and `[login.1]` back to what it was before
      change (a), using git. Keep change (b), the last sign-in time, and everything else from round 4.
    - Also put the `HTTP client` capability back to its first, wrong form (an error's `message`
      is the body's `message`).
    - Commit this as the base for phases 4 and 5, and write its hash in the report.
2. **Link the trees.**
    - Add `"links"` to both projects: the clients project links `api`, and the API project
      links `clients`.
    - Add `calls: api [<step>]` to every client step that sends a request to the API (sign-in, and
      also refresh, validate and the login picker if the React tree has steps for them).
    - Run `check` on both projects: no `link` problems. Record any `untested-link` warning.
3. **Make the seam test a link test.**
    - Turn round 4's `harness/seam_login.test.tsx` into the clients project's
      `links.api.test` command. It runs the real `AuthService` and `LoginModal` against the running
      API on the trial database.
    - The command must work on its own, from a clean shell: start the API (and anything it needs),
      run the test, stop what it started.
    - Its cases: a sign-in that succeeds, a wrong password, and a missing permission.
    - Run `ladder test`. Against the base from phase 1 it should pass for the old behavior; if a
      case only makes sense after change (a), add that case in phase 5, not now.
4. **Test the vocabulary.**
    - Give the `HTTP client` capability a `test:` line: a small test that calls the real client
      against the API and asserts each `known:` line.
    - Run `ladder test` while the capability still has its wrong claim. Record whether `check`
      reports `test-failed`, and what it says.
    - Correct the capability as round 4 did (a 401 always says "Unauthorized"; the body is in
      `responseData`), then run `ladder test` again. Record that `test-stale` showed between the
      edit and the rerun.
    - Add `test:` lines to the API's capabilities that have `known:` lines, where a test is
      practical. List the ones you skipped and why.
5. **Repeat change (a) through the English.** This is the main measurement.
    - Edit only the API English for `[api.1.1]`: the 401 carries `code`, `missingAuthorizations`,
      and a message naming the permission, as in round 4.
    - **Before touching the React English**, run `check --since=<phase 1 commit>` on the clients
      project. Record whether every calling step shows `linked-changed`, and whether the message
      says what changed. Run `check` on the API project and record the `has-callers` warning.
    - Run `ladder test`. Record whether the link test shows as stale, then whether it passes or
      fails against the regenerated API.
    - Update the React English (the client rethrows the API's error, and the form shows the API's
      text), regenerate both sides normally (not blind), and run `ladder test` and the replay
      comparison. Record what each step caught that round 4 did not.
6. **Exercise the other v0.5 fixes, briefly.** One line each in the report: worked, or what went wrong.
    - **Support-only build:** give the entity file a build with `"steps": []`, and confirm `check`
      reports it as support only.
    - **Replay:**
        - re-record round 4's scenarios with `--mask traceId,refreshToken:presence,expiresAt:time`;
        - make s06's 32-second wait a standalone `{"wait": 32}`;
        - use `save` paths without `body.`;
        - add `--observe` running your SQL count from the Extended Events session.

      Do the two recordings of the original API still match?
    - **Differences:** `check --all-differences` on a comparison with several differences per run.
      Does it list every one, with its request?
    - **Blind regeneration:** `regen --blind` on the controller build in a scratch copy. The class
      declaration and constructor are now regenerated too. Record whether it still builds and
      replays, and any convention-leak warnings.
    - **Schema:** `check --since=<commit before the round 4 migration>`. Steps that write the
      employee table should not be flagged for the new optional column. Then add a required column
      in a throwaway commit on the trial database and confirm the writing steps are flagged. Revert
      it afterwards.
    - **EF exporter:** run the plugin's `tool/exporters/efcore-schema` on qbs_api's DbContexts and
      compare its JSON with your round 4 exporter's. List any differences.
7. **Report.** Leave everything awaiting Ben's approval; do not stamp.

## What to report

Write `REPORT.md` in this folder (`trials/4-seam-round5/`) on a branch
`trial/4-seam-round5`, and open a pull request.

| Measure | Round 4 | Round 5 |
| --- | --- | --- |
| API change flagged on the React side before the React English was touched | no | |
| Calling steps flagged `linked-changed`, of those that call `[api.1.1]` | n/a | |
| Wrong HTTP client claim caught by `ladder test` before generation | no (found by a hand-written end-to-end test) | |
| Capabilities with a `test:` line, of those with `known:` lines | 0 | |
| Link test passes after the change, both sides regenerated | 3 / 3 by hand | |
| Replay: two recordings of the original API identical, with the new masks and `--observe` | yes (without them) | |
| Blind controller regeneration builds and replays (now including its constructor) | constructor not regenerated | |

Also include:

- **Friction**, in the order you hit it. Note every workaround, every `REFUSED` message, and
  anything you wanted to edit by hand.
- **The messages themselves**: paste the `linked-changed`, `has-callers`, `test-failed` and
  `test-stale` lines exactly as `check` printed them, and say whether each told you what to do.
- **False alarms**: any step flagged that didn't need to be, and any warning you'd turn off.
- **Steps awaiting approval**, listed for Ben.

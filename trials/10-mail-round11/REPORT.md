# Ladder round 11 report: employee mail in two apps (v0.6.5, then v0.6.6)

2026-10-12 · trial branch `ladder-trial-r11` in `~/code/qbs-ladder-trial` (commits `f0a81448ea` to `354ee7661b`),
plugin v0.6.5 (PR #12), then v0.6.6 (this round's fixes, PR to follow).

## 1. Verdict

**The bar is not met in this round, but the loop is close to smooth.** The whole loop ran with no hand edits to
generated code:
1. transcribe;
2. link and test;
3. regenerate blind;
4. stamp;
5. change through the English in three trees;
6. regenerate;
7. accept;
8. move the reference;
9. stamp again.

Two serious problems showed up, both fixed in v0.6.6:
- **F1, a change that reaches nothing:**
  - **Rules weren't in the hash:** a named rule's text is not part of the hash of the steps that cite it, so
    editing the rule stales nothing but contract types.
  - **Both apps kept the rule's value in support code:** the 5000-character limit lived in a `@support` constant,
    which regeneration never rewrites.

  Changing the limit to 2000 would have changed no code, without a word.
- **F2, files several projects tag:** the scanner's `lib/api.ts` holds the timeclock project's regions and now
  mail's. Each project reported the other's regions as `unknown-step`, so a repository-wide transcription, where
  every app's API module is shared by many areas, could not pass `check`.

With the fixes:

| | Result |
| --- | --- |
| Blind regeneration | all 12 builds compile without repair (11 at the first try; the scanner dialog's dropped exports are fixed by F3); the blind API replay matches 28/28 |
| The change | plain `regen --repair=3`; all 5 builds clean without repair, including the new top-level step and both rule constants; 46 changed lines; every replay difference is the change |
| Tests after the change | API 1/1, library 3/3, clients 7/7 |

**English gaps (mine), all caught by tests or the OpenAPI snapshot before anything was stamped:**
- the response types the API documents;
- whitespace in initials;
- accessibility labels;
- which auth signal means "signed in" (twice).

Each was fixed in the English and regenerated. The transcribe skill now says how to avoid them.

The pattern since round 9: each round's serious findings are narrower, and each of them is something a whole-repo
transcription would hit at once:
- a shared file;
- shared rules;
- derived contracts.

**Round 12** should go on an unseen slice that has none of the specific fixes in mind.

## 2. The slice

| Tree | Steps | Builds | Files |
| --- | --- | --- | --- |
| `ladder/mail/api` | 9 (`mla.*`, `mls.1`–`mls.5`; `mls.5` added in the change) | controller, service, dtos | `MailController.cs`, `MailService.cs`, `MailDTO.cs`, `SendMailRequestDTO.cs` |
| `ladder/mail/library` | 6 (`ml.*`) | library-service, library-dtos | `mail-service.ts`, `dtos/mail.ts` |
| `ladder/mail/clients` | 21: dashboard `mcd.1`–`mcd.9`, scanner `mcs.*`, compose `mcc.1`–`mcc.6` shared by both apps | 3 dashboard and 4 scanner builds | `hooks.ts`, `MailScreen.tsx` and `SendMailModal.tsx` (dashboard); `types.ts`, `lib/api.ts` (shared with timeclock), `MailScreen.tsx` and `SendMailModal.tsx` (scanner) |

**The compose dialog** is one set of steps (`mcc.*`) that both apps implement, with seven `DIFFERS` notes:
- the search fields;
- "Select all" replacing the ticks versus adding to them;
- the failure text;
- error clearing;
- where the length check lives.

Blind regeneration produced each app's own behaviour from the shared English and the notes; the behaviour and link
tests confirmed both.

**One shared step had no region in one app:** the dashboard checks the length inline in JSX, where no region can go,
so `mcc.5` is the scanner's alone. The dashboard's render step states it instead.

**Vocabulary added:**
- *API JSON answer*: the API drops trailing spaces from every text it writes, which replay showed;
- *active employees*;
- *division list*;
- *console error*;
- *app alert*;
- *scanner screen kit*.

**Trial harness files** (mine, not qbs tests):
- `ladder/mail/api/env/`: seed, reset and the `rows.sh` observer;
- `api/harness/record.sh`;
- `api/scenarios/` (28 requests);
- the link tests: `library/harness/link.test.ts` (5), `clients/harness/dashboard-link.test.tsx` (3) and
  `scanner-link.test.tsx` (2);
- `clients/harness/scanner-behaviour.test.tsx` (9);
- a `regions.json` per project.

The committed OpenAPI contract was regenerated as part of the change (`maxLength` 5000 → 2000).

## 3. Results

| Measure | Round 10 | Round 11 |
| --- | --- | --- |
| Transcription, comments only | yes | yes (14 files, via `ladder tag`) |
| Blind regeneration clean without repair | 9 of 9 (v0.6.5) | 11 of 12 at first; 12 of 12 after F3 and the English fixes |
| Tests after blind regeneration | 3/3, 3/3, 7/7 | API 1/1 (OpenAPI snapshot), library 3/3, clients 6/6 |
| Blind API replay | 28/28 | 28/28 (after F7) |
| Change regenerated | 3 builds clean | 5 builds clean, new top-level step inserted by plain `regen`, 46 lines |
| Replay after the change | every difference the change | every difference the change: the 2000 limit, the recipient check (400 instead of 500, and 2 more SQL statements per send) |
| Stamped clean (`check` exit 0) | 2 of 3 | 3 of 3 |
| Hand edits to generated code | 0 | 0 |

## 4. Findings, by severity

### Serious (fixed in v0.6.6)

**F1. A rule change could reach no code.**
- **Rules weren't in the hash:** a step's hash covers its own text only. A named rule it cites ("(rule message
  limit)") could change and the step stayed current; `check` said only "steps that use it may need --redo".
- **The values lived in support code:** both apps kept the rule's value as a constant in `@support` code, which
  regeneration never rewrites.
- **Fix:**
  - `check` names the steps citing a changed rule (`rule-changed`), and `regen` rewrites them.
  - A `@contract rule <name>` region holds a rule's constant; its hash is the rule's text, so it goes stale and is
    regenerated.
  - `check` warns `rule-in-support` for a rule's value written in support code. It found the two mail constants and
    two in round 10's unpick dashboard, with no false alarms on the other 13 projects.
- **Result:** after moving the mail constants into rule regions, the change regenerated both to 2000.

**F2. Files several projects tag.**
- **What happened:** a region of another project in a shared file was an `unknown-step` problem, in both projects.
- **Fix:** a build's `"shared_with"` names the other projects. Their steps are foreign: not unknown, not recorded
  as this project's code, never regenerated by it.
- **Docs:** the format and the transcribe skill ("Files several areas share") describe it.

### Moderate (fixed in v0.6.6)

**F3. Blind regeneration dropped exports.**
- **What happened:** the scanner dialog's two props interfaces came back unexported. The folder's `index.ts`
  re-exports them, so the build failed in a file no build owns, and `repair` could not reach it. Before the first
  stamp, `check` had no export list to compare with.
- **Fix:**
  - blind prompts list the names each hidden region exports;
  - `exports-changed` compares an adopted file with its git baseline before the first stamp.

**F4. `note:` lines in a data block were fields.**
- **What happened:** two notes in one block failed as a repeated field, and in earlier rounds a single note became a
  field named "note".
- **Fix:** they are notes now. Their place in the block's text is kept, so no hash changed.
- **A regression I made and fixed:** I first changed how notes render in a linked step's recorded contract, which
  made round 10's dashboard show false `linked-changed`. It's back as it was.

**F5. Files derived from code weren't rebuilt.**
- **What happened:** the 2000 limit changed the API's published OpenAPI contract. Only qbs's snapshot test noticed.
- **Fix:** ladder.json `"after_generate"` commands run after code is generated (here: regenerate the contract and
  the client types).

**F6. `ladder tag` on an already-tagged commit doubled every marker.**
- **What happened:** I re-ran it with `--base HEAD` after committing the tags. The new `split-step` and
  `contract-misplaced` checks flagged it at once.
- **Fix:** `ladder tag` refuses a base that already has the project's markers, and defaults to the `baseline`.

**F7. Replay recorded the service's own address.**
- **What happened:** a `Location` header holds `http://127.0.0.1:<port>/...`, so two builds on two ports differed.
- **Fix:** recorded as `<base>`.

### Minor

- **F8.** `ladder reference --retire` could not retire the build just made the reference. Fixed: it retires after
  the copy.
- **F9.** A handler written inline in JSX cannot be a region, so a shared step may belong to one app only. The other
  app's render step states the rule. No tool change.

### English gaps, caught by the loop

| Gap | How it showed | Fix (in the English or profile) |
| --- | --- | --- |
| `[ProducesResponseType]` for every status, including the framework's 400/401 | the OpenAPI snapshot test | the profile lists them exactly |
| "split at spaces" (the code splits at any white space) | found by reading the diff; no test caught it | "every run of white space" |
| Accessibility labels | the scanner behaviour test | listed in the render step |
| "signed in" (`isAuthenticated` versus the employee id), in `[mcd.1]` and `[mcd.3]` | the dashboard link test and qbs's `SendMailModal` test | the field named |
| A mapping's source field | a compile error, fixed by repair | the source named |

The transcribe skill now asks to name the exact signal a condition reads, and to list accessibility labels.

### qbs, not Ladder (QUESTION / DECISION in the trees)

- **QUESTION:** any signed-in employee can read, mark and acknowledge another employee's mail, and send as them: the
  path id is used as given.
- **QUESTION:**
  - In the trial database, `Employee.Mail.id` is not generated. Every new mail is mail 0, so a second send fails
    with 500.
  - An unknown recipient saved the mail and then failed with 500. Changed in the trial branch (DECISION): it is now
    a 400 before anything is written.
- **QUESTION:**
  - New mail is stored in UTC while the other mail rows hold local times, and the API answers without a zone.
  - A mail that needs no acknowledgement can still be acknowledged.
  - The library types `hasAcknowledged` as yes/no, but the API sends null.
- **QUESTION (scanner):**
  - Its Send button is grayed while the form can't be sent, so its two validation messages never appear.
  - Its loading flag is never shown.
  - It cannot acknowledge mail.

## 5. What to fix next

All of F1–F8 are addressed in v0.6.6:
- 35 tool tests pass (`test_round10.py`, `test_round11.py`);
- `check` exit codes match v0.6.4 on every earlier project.
  - **Expected differences:** mail and timeclock clients differ, because v0.6.4 cannot read two notes in a data
    block or `shared_with`.
  - **Before this round:** the unpick API keeps its failing qbs test (round 10, left for the owner).

**Round 12:** an unseen slice with v0.6.6, chosen without these fixes in mind. If it finds no serious problem, the
bar is met.

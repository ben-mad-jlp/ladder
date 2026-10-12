# Ladder round 4 handoff: C# API with schema references

2026-10-12 · from Ben

## Goal

Round 4 re-runs the qbs_api auth trial on Ladder plugin v4, to see whether blind regeneration now
converges and whether schema references hold up through a real migration.

The code is throwaway: we are hardening Ladder, not shipping this auth code. Judge every result by
what it says about the tool.

Round 3 matched only 14 of 67 replay runs after regeneration (see `../2-api-auth/REPORT.md`). The
causes, all fixed in v4:

- Region prompts left out the profile, so generated C# ignored the project's conventions.
- `"data": []` meant every data block instead of none.
- Parallel generations wrote to the same log folder and compiled each other's output.
- Entities were described in English, so the generator guessed column names and types.

New in v4:

- **Schema references.** `"schemas"` in `ladder.json` points at each EF model snapshot; steps say
  `reads:` / `writes:` and mark exact members as `[[Entity.Member]]`. `ladder check` catches bad
  references, and `ladder stamp` records the schema facts each step relies on. A migration that
  changes one shows the step as `schema-changed`.
- **Built-in replay.** It supports `{{env:X}}`, `save` / `{{var:x}}`, cookies, `--jwt` claims with
  relative lifetimes, `wait`, `--before-each` and `--mask`. It replaces the agent's own `replay.py`
  from round 3.
- **Blind regeneration.** `regen --blind` hides the old region code from the generator, so a match
  proves the English is enough on its own.

## Ground rules

- **Test database and test users only.** Never point anything at production or a shared service.
- **Secrets come from the environment.** They never go into git, traces, logs or the report. Use
  `{{env:X}}` in replay scenarios.
- **Approval is Ben's.** Do not run `ladder stamp`. When a step is ready, list it in the report as
  awaiting approval.
- **No hand edits to generated code.** Change the English and regenerate, or use `ladder repair`. If a
  fix can only be made by hand, stop and report it as friction.
- **Don't edit tests** to make them pass.
- **Work on a branch with push disabled** in the qbs repo. Regeneration happens in a scratch copy
  (`generate --out`), never over the working files.
- **The migration is allowed.** Because the code is throwaway, you may create the phase 6 migration
  and apply it to the test database yourself. Do not apply it anywhere else.

## Phases

Start from the round 3 branch: its English, tags and replay recordings carry over. Each phase ends
with `ladder check` and a line in the report.

0. **Set up.** Install the plugin from GitHub, replacing v3:
   `claude plugin marketplace add ben-mad-jlp/ladder`, then `claude plugin install ladder@ladder`
   (or `claude plugin marketplace update ladder` if already added). Note the commit you installed.
   Make a new branch from round 3 with push disabled. Read the `ladder-transcribe`, `ladder-write`
   and `ladder-generate` skills again; the schema sections are new.
1. **Point Ladder at the schema.** Add a `"schemas"` entry to `ladder.json` for each DbContext, using
   `"kind": "efcore-snapshot"` and its `ModelSnapshot.cs`. A database without migrations gets
   `"kind": "json"` and an exported file. Run `ladder schema` and confirm every entity the auth code
   uses is listed, with the right tables and columns.
2. **Refer to the schema instead of describing it.**
    - Remove English that restates entities (their columns, types, lengths, keys).
    - Add `reads:` / `writes:` to every step that touches the database.
    - Mark exact members as `[[Entity.Member]]` where precision matters: filters, ordering, what is loaded.
    - Tag the entity classes as `@support`; they are never generated.
    - Run `ladder check` until there are no `schema-ref` problems. Read each `two-databases` warning
      and either split the step or leave a note on why it's safe.
3. **Settle the case-insensitive questions.** QUESTIONs 7 and 13 and seam S1 are intended: permission
   names match case-insensitively because the database is set up that way. Turn each into a DECISION
   saying so.
4. **Regenerate blind.** Set `check_command` to build the whole solution, tests included. Run
   `regen --blind` on all five auth files in a scratch copy (`generate --out`). Use `ladder repair` on
   build errors. Record how many repair rounds each file took, and stop a file after 3.
5. **Compare by replay.** Use the built-in `ladder replay` with the round 3 recordings: `{{env:X}}` for
   credentials, `save` / `{{var:x}}` for tokens, the cookie jar for refresh, `--jwt` to compare
   claims, and `--before-each` to reset test data. Replay against the original API and the
   regenerated one, then run `ladder check` to compare. Round 3 matched 14 of 67; record the new
   count and explain every difference. Run the mutants too.
6. **Make two changes in English only, then regenerate.**
    - **(a) A clear missing-permission error**, across both the API English and the React library
      English. The response names the missing permission, and the React side shows it. Check that the
      seam between the two trees still agrees, and record whether Ladder flagged the change on both sides.
    - **(b) Record each employee's last sign-in time.** First write the English, with `writes:` naming
      the new member. Run `ladder check` and confirm it reports the unknown member. Then add the
      property, create the migration and apply it to the test database. Run `ladder check` again.
      Record whether the reference now resolves, and whether any unrelated step was wrongly marked
      `schema-changed`. Regenerate, then replay a sign-in to show the column being written.
7. **Report.** Write it as described below. Leave everything awaiting Ben's approval; do not stamp.

## What to report

Write `REPORT.md` in this folder (`trials/3-api-auth-round4/`) of the `ben-mad-jlp/ladder` repo, on a
branch `trial/3-api-auth-round4`, and open a pull request. Use the same sections as round 3 so the two
can be compared.

| Measure | Round 3 | Round 4 |
| --- | --- | --- |
| Replay runs matching after blind regeneration | 14 of 67 | |
| Files clean after regeneration, without repair | | |
| Repair rounds, per file | | |
| Mutants caught | | |
| Schema references written; problems `check` found | n/a | |
| Steps wrongly marked `schema-changed` after the migration | n/a | |

Also include:

- **Every replay difference**, with its cause: the English, the generator, or the comparison.
- **Friction**, in the order you hit it. Note anything you had to work around, especially hand edits
  you wanted to make, and every `REFUSED` message.
- **Schema references**: where `[[...]]` helped, where it was noise, and any entity the snapshot
  reader got wrong.
- **The phase 6 results**: whether each change was flagged on both the API and React sides, and
  whether the migration went through `check` as described in phase 6.
- **Steps awaiting approval**, listed for Ben.

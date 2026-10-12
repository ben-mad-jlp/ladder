# Working on Ladder

**The goal is to harden Ladder, not to make any one codebase work.** The trials run Ladder on real
code (qbs_api, the React library and scanner) to find where Ladder breaks. Their code is throwaway.
Once Ladder is good enough, the whole qbs repository will be transcribed into Ladder, and from then
on bug fixes and new features there go through the English.

## Fixing what a trial finds

- Ask of every finding: would this happen on another codebase? Fix the general cause, in the tool,
  the format or the skills. Never add a rule, path, name or heuristic that only fits the trial repo
  (a folder name, a class naming habit, one team's folder layout). If a setting is needed, make it a
  documented ladder.json option with a neutral default.
- A finding that is about the trial's code, data or environment, not Ladder, is recorded in the report
  as "not Ladder" and left alone.
- Prefer making Ladder say something true and actionable over making a trial's numbers look better.
  A false alarm is fixed by making the check more precise, not by hiding it.
- Every fix gets a test on a small sample project and a line in `plugins/ladder/reference/ladder-format.md`
  (or the skill it changes). Re-run `ladder check` over the earlier projects for regressions.

## Before the full transcription ("good enough")

Ladder is ready to transcribe the whole repository when a trial on a slice it has not seen before:
- finds no serious Ladder problem (wrong code generated silently, a change that reaches nothing, a
  check that cannot be trusted);
- needs no workaround the skills don't describe;
- runs the whole loop (transcribe, link, test, change through the English, regenerate, review,
  stamp) without hand edits to generated code.

## Repository

- `plugins/ladder/`: the plugin (skills, reference, the `ladder` tool). Bump `.claude-plugin/plugin.json`
  on every change that ships.
- `trials/`: each round's HANDOFF.md and REPORT.md.
- `docs/review-app/`: the Ladder Review app spec and mockups.

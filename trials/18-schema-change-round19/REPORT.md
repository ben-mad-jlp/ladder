# Ladder round 19 report: a change that needs a new column (v0.6.12, then v0.6.13)

2026-10-13 · trial branch `ladder-trial-r16` in `~/code/qbs-ladder-trial` (commits after `680473de06`, to `a64570647f`).

## What was tried

The schema-change flow, which no round had walked end to end. qbs changes its database with SQL scripts, not EF
migrations, so Ladder's schema is an export of the EF model.

**The change:** a subscription to an alert can be muted, and a muted subscriber gets no pushes. It went on the
round 18 slice (the alert notifier).

**The flow, as the skills describe it:**
1. A person writes the migration (`db_migrations/20261013_add_employee_alert_muted.sql`, applied to the trial
   database only with the trial reset's `--apply`) and the entity property (`Employee_Alert.Muted`).
2. The person re-exports the schema with the plugin's exporter.
3. The English uses the column (`[[Employee_Alert.Muted]]`).
4. `check`, regenerate, review, accept, stamp.

## Verdict

**The flow works:**
- `check` resolved the new column and marked `[aln.1]` stale.
- It marked three steps of another project (`my-alerts/api`, which writes the same table) `schema-changed`, saying a
  required column was added. They were re-read and re-stamped; their tests pass.
- `regen` changed one condition (`&& !s.Muted`), with no repair.
- **Replay:**
  - the new code with employee 963 subscribed and muted matches the reference (963 gets nothing);
  - the old code with the same data pushes to 963, so the replay catches the behaviour.
- Accepted, reference re-recorded, stamped. No hand edits to generated code.

**Friction, fixed in v0.6.13:**
- **F1.** The exporter targeted net8.0 and failed with NU1201 against the net9.0 models project. The fix
  (`-p:LadderTargetFramework=net9.0`) was in the exporter's README but not in the transcribe skill's command. The
  exporter now takes the models project's `<TargetFramework>` by default.

**Noted, not changed:**
- The export says the new column has no default because the model has none, although the migration gives it one in
  SQL. `schema-changed` therefore says inserts must now set it. That's true for EF, which always sends the value; a
  person reading it should know the database has a default.
- Projects should declare database defaults in the model (`HasDefaultValue`) when they matter to the English.

## qbs, not Ladder

- **DECISION (trial branch only):** muted subscriptions (`Employee.Alert.muted`).

## Next

v0.6.13: 61 tool tests pass; the exporter, run without any flag on the qbs models, gives the same export as with the
flag. With rounds 16 to 19 behind it, I'd call the hardening satisfactory: see PR #23's recommendation, now with v0.6.13.

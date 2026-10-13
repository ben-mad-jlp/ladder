# Ladder round 18 report: alert push over SignalR (v0.6.11, then v0.6.12)

2026-10-13 · trial branch `ladder-trial-r16` in `~/code/qbs-ladder-trial` (commits after `da3ab4171a`, to `680473de06`),
plugin v0.6.11 with no tool change during the round, then v0.6.12.

## What was tried

A push channel, a shape no round had covered:
- **The slice:**
  - the SignalR alert hub (connect, disconnect and ping, with employee groups);
  - the service that pushes "AlertCreated" and "AlertAcknowledged" to them.
- **Verification:**
  - `ladder replay` drove the HTTP routes that trigger the pushes;
  - a listener connected as three employees and wrote what each received;
  - `--observe` put those events in each request's trace.

  The reference was recorded twice; both recordings are identical. The trace shows who got a push and who did not
  (employee 963, not subscribed, never does).

## Verdict

**The loop ran cleanly with no tool change:**
- blind regeneration: 2 of 2 builds clean without repair; the replay (pushes included) is 7/7 identical; the qbs
  alert tests pass;
- the change, a rule cited by four steps in two builds (the group name "employee:<id>" → "employee-<id>"): all four
  were stale at once and regenerated, a one-line diff each, with no repair; the replay is identical (the name is
  internal, and both sides changed);
- after accepting, v0.6.9's `reference-stale` asked for the reference to be recorded again from the changed code,
  as designed.

**One finding, fixed in v0.6.12:**
- **F1. `replay` wrote signed tokens into traces.**
  - The recorder I wrote for this round left out `--jwt`, and the login answers' access tokens went into the trace
    files as they were.
  - I caught it by reading a diff, before anything was committed (staged diffs are scanned for tokens).
  - Traces are committed, so a missing flag should not be able to put secrets in git.
  - **Fix:** `replay` writes any value that looks like a JWT (also inside a text) as `<token>` and says so; `--jwt`
    records the claims as before, and `--keep-tokens` is the explicit way to keep them.
- **Docs:** recording pushed events through a listener and `--observe` is now in `scenarios.md`. That includes
  using one events file name for every recording: my first recorder named it after the build, and
  `replay-settings` rightly reported the recordings as made differently.

## qbs, not Ladder

- **QUESTION:** a second notification for the same alert fails with 500. Each one inserts an `Alert.Notification`
  row keyed by the alert's name.
- **QUESTION:** a notification for an alert with no definition fails with 500. The service creates the definition
  without the required `description`.
- **DECISION (trial branch only):** the group name is "employee-<id>".

## Next

v0.6.12: 61 tool tests pass, including 3 new ones (2 fail on v0.6.11). Another unseen slice follows.

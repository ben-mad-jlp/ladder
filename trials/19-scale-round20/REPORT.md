# Ladder round 20 report: whole-repository scale (v0.6.13, then v0.7.0)

2026-10-13. Not a new slice. The question was what breaks when Ladder covers a whole repository rather than
1 to 9 files. Two inputs:
- **The trial repository:** the 28 trial projects on `ladder-trial-r16` in `~/code/qbs-ladder-trial`.
- **A synthetic repository:** 500 projects of 50 steps (20,000 leaf steps in all), a 1,000-term shared vocabulary,
  and 3 links per project with `calls:` lines. It was generated, tagged at the real hashes and stamped by
  [`gen.py`](gen.py) (`python3 gen.py <out> 500 50 1000 3`).

## Verdict

**Correctness holds at scale:**
- **An edited step:** `check` flagged its callers one, two and three links away, and nothing else.
- **A changed vocabulary binding:** `binding-changed` appeared in exactly the 19 projects that use the term, each
  with the right `--redo`.

**Speed is fine for one project and was poor for the whole repository:** one `check` takes 0.32 s, but no command
covered the repository.

**Three things would have hurt a whole-repository run,** all fixed generally in v0.7.0 (PR fix/v0.7.0-repo).

### F1. Every project repeats the same settings
Across the 28 trial projects:

| Setting | Projects repeating it |
|---|---|
| generator | 28 of 28, identical |
| vocabulary | 26 of 28 |
| schemas | 10 of 11 |
| `mode` and `adopted` | 89 of 89 builds, the same values |

At 500 projects, changing the generator or a conventions file means editing hundreds of files, and missing one goes
unnoticed.

**Fix:** a `ladder.repo.json`, found by walking up from each project.
- **What it holds:** `defaults` for project keys and `build_defaults` for build keys (`"*"`, then per language).
- **Paths:** written relative to it and rebased for each project.
- **Precedence:** the project always wins. Builds compared by behaviour only take no build defaults.
- **Refused:** keys that belong to one project (`title`, `tree`, `builds`, `baseline`, and a build's `name` and
  `files`) are an error there.
- **`init`:** leaves out what the repository supplies.

**Checked on the trial repository:** with 244 repeated settings moved into one `ladder.repo.json`, all 28 projects
give byte-identical `check` output.

### F2. No way to check the whole repository
- **Before:** 500 separate `check` runs took 2 min 42 s, and nothing summarised them.
- **Fix:** `ladder check --all` checks every project the repository file's `"projects"` globs list, prints one line per
  project that isn't ok and a count by kind, and exits as the worst project.
- **Times:** 29 s for the 500-project repository, 1.1 s for the trial repository.
- **What made it slow:**
  - each check re-read the same linked trees, configs and locks, and re-ran the pending-change walk up to three links
    deep, once per caller;
  - the rule-agreement check walks every project reachable through links, which was 250 projects for p250.

  These are now read once per run, keyed by file stamp, and one `check` still takes 0.32 to 0.35 s.

### F3. An edited step warned only the callers the project linked back to
- **Before:** `has-callers` needed the called project to list its callers in its own `"links"`. An API called by
  many screens lists none of them, so editing an API step said nothing on the API side. Each screen found out only when
  its own `check` ran.
- **Fix:** under a repository file with `"projects"`, a reverse-link index (built once per run) finds every project
  that links to this one. The warning is now one per step, naming every caller:
  `[p100.1.1] edited since approval, and it is called by ../p101 [p101.1.1], ../p102 [p102.1.2], ../p103 [p103.1.3]`.
- **Cost:** at first 5.2 s per check, because the scan ran at every level of the link walk. With the index it's
  0.38 s.

## Not Ladder

`check --all` on the trial repository surfaced three projects that were already failing, a state invisible before
because nobody re-checked old rounds:
- `auth/api` and `auth/clients` (rounds 3 and 4) were never stamped in the current format;
- `unpick/api` has a recorded test that failed.

All are trial leftovers.

## Still not measured

- **Generator time and cost** per thousand regions, and **review time** per thousand steps. Only a real area can
  measure these.
- **The pilot** (one whole feature area through the full loop on v0.7.0) is the next step.

## Tests

70 tool tests pass: 9 new in `test_round20.py`. Every trial project's `check` output is the same with v0.7.0 as with
v0.6.13, both with and without the repository file.

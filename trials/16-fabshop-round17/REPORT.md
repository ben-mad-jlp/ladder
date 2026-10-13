# Ladder round 17 report: fabshop cut-bundle permutations (v0.6.10, then v0.6.11)

2026-10-13 · trial branch `ladder-trial-r16` in `~/code/qbs-ladder-trial` (commits after `45274b9256`, to `da3ab4171a`),
plugin v0.6.10 with no tool change during the round, then v0.6.11 (this round's fix).

## What was tried

A shape no round had covered: a C# algorithm with no HTTP route, ported from a legacy procedure. The slice is
`FabshopPermutationGenerator.cs` (718 lines): it reads cut demand, builds every candidate bundle with a cross-join,
prunes them with a reason each, and rewrites a table plus debug rows.

**Verification:** a C# differential harness, new to the trials.
- An xunit class runs on the qbs tests' real-schema SQLite context, run on its own by `ladder/env/api-harness.sh`.
  The script copies the class in, runs it alone and removes it.
- 400 seeded demand scenarios. The reference was recorded twice; both recordings are identical.
- 6 of 8 mutants were caught:
  - one is equivalent (the insertion order of an unordered table);
  - one boundary (falloff between 24 and 25 inches) is too rare in the seeds; I stopped tuning there, since the port
    is throwaway.
- 40 qbs bundle-generation tests.

## Verdict

**The loop ran cleanly with no tool change:**
- blind regeneration: 1 of 1 build clean without repair; differential 400/400 identical; 40/40 qbs tests;
- the change (rule max falloff 24 → 30 inches): the rule's constant region and `[fpg.8]` regenerated with no repair;
  one seed differs, and it is explained;
- reference moved, stamped, no hand edits.

**One finding where a check could not be trusted, fixed in v0.6.11:**
- **F1. A schema reference resolved to the wrong entity.**
  - `[[Saw.Division]]` matched `Fabshop_BuilderDebugSaw`, whose bare table name is also "Saw", before the entity
    named `Saw`.
  - `check` reported three false `schema-ref` problems.
  - Had the wrong entity had those columns, it would have silently checked the wrong table.
  - **Fix:** an entity's class name is matched first, then a schema-qualified table name, then a bare table name; a
    bare table name several entities share is reported as ambiguous.
  - **Checks:** `check` output on every other trial project is unchanged; 2 new tests fail on v0.6.10.

## qbs, not Ladder

- **DECISION (trial branch only):** the falloff limit is 30 inches; the rejection keeps the legacy text "falloff
  greater than 2ft and no stock".
- **Note:** the qbs tests pin the reason literal "greater than 216 inches", so a change to the 216-inch rule would
  need its text changed too. That is a coupling the English now states for the falloff rule.

## Next

v0.6.11: 58 tool tests pass. Another unseen slice follows with v0.6.11.

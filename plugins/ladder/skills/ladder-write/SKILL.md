---
name: ladder-write
description: Write or edit Ladder English - the .ladder step trees (steps, in/out contracts, > how-lines, notes, data blocks, rules, uses:) that drive generated code. Use this whenever someone wants to add a feature, change behavior, fix a bug, add a validation rule, add or rename a field, or otherwise change what a laddered system does; when they say "update the English", "change the tree", "write this in our language" or describe new behavior for a laddered part of the system; or when a .ladder file needs reviewing for ambiguity. Behavior changes in laddered code start here, not in the generated code.
---

# Write Ladder English

In a laddered system the English is the source of truth. People change behavior by changing the
English; code is regenerated from it (ladder-generate) and checked by running it (ladder-verify).
So the English has to be precise enough that two different generators, in two different
languages, would build the same behavior from it, and still read as plain English to someone
who doesn't program.

Format: `${CLAUDE_PLUGIN_ROOT}/reference/ladder-format.md`. Style rules and the ambiguity checklist:
`references/style.md`; read it before writing more than a line or two. Run the tool as
`ladder <command>` (or `python3 ${CLAUDE_PLUGIN_ROOT}/tool/ladder.py <command>`).

## 1. Start from what exists

Find the project's `ladder.json`, its tree (any file name; `.ladder` is the convention, older
projects may use `.tree`), vocabulary and data blocks, if the project has them. Read the steps around the
change and anything that consumes them, including other trees that call this part of the system
(an API tree's output is a client tree's input). Run `ladder check` to see the current state, so
you don't mistake old problems for new ones.

If `check` lists a region as `hand-edited`, someone changed the code directly. When the request is
to make the English match such an edit, read it in git (`git diff`, `git log -p`), describe the
behavior it adds in the English like any other change, then run `ladder accept <ladder.json> <ids>`
so the region counts as described again.

## 2. Pin down the change with the person

Restate the change as behavior: inputs, outputs, rules, error cases. Where the request leaves a
real choice open (which status code, inclusive or exclusive, what to show when empty, the order
of checks), ask. Don't silently pick, because a guess written into the English becomes the spec.
Offer a sensible default with your question so it is quick to answer.

When nobody is available to answer (an unattended run), write the sensible default into the English
and mark it on the step with `note: DECISION: <what was chosen and why>`, then list every DECISION
in your hand-back so the person reviews them before approving. DECISION is only for choices *you*
made; what the person asked for is written as plain English (with a plain `note:` giving the reason
when it isn't obvious).

When a change answers a `QUESTION:` or `DIFFERS:` note, replace that note with a plain note recording
what was decided ("cleared tasks' promises reject; decided by <who>"), so the open question is gone.

## 3. Edit the tree

- **Ids are permanent.** Never renumber or reuse an id. A new step gets a new id, even if that
  leaves gaps or out-of-order numbers. Moving a step keeps its id.
- **Smallest edit that says it.** Each changed step's code will be regenerated; unrelated rewording
  regenerates code for nothing.
- **Contracts are exact.** Field names in backticks, exactly as on the wire. Adding, removing or
  renaming a field is a contract change: it regenerates `@contract` types and every consumer.
- **The database is referred to, not described.** Use `reads:` / `writes:` and `[[Entity.Property]]`
  (format section 3); `ladder schema` lists what exists. A change that needs a new column is two
  things: the migration (the schema), and the English that refers to the new column. Write the English
  against the schema after the migration, so `check` can verify the reference.
- **Data blocks for data, steps for behavior.** New fields and constraints go in `data` blocks;
  rules used in more than one place become a named `rule`. This includes new *state* a step needs
  (a class field, a hook's state): add it to the data block, not to the parent step's wording.
  `check` then reports `data-edited`; regeneration rewrites the `@contract` region that holds the
  state, and you `--redo` the steps that use it. Editing the parent step instead regenerates
  everything under it.
- **What counts as the same is English too.** When verification shows a difference no caller can
  depend on (generated ids, the order of a set, timing within one tick), say so on the step with a
  `compare:` line (`compare: ignore id`, `compare: any timing`; format section 9). It doesn't change
  code or the step's hash, but `check` reports it as `compare-edited` for approval. Only the person
  decides that a difference doesn't matter; unattended, add it with a `note: DECISION:`.
- **Watch the consumers' tests.** A behavior change makes tests that asserted the old behavior fail.
  Name those tests in your hand-back; changing them is the person's call (they are not generated).
- **Libraries through the vocabulary.** If the change needs a capability that doesn't exist, add it
  with the ladder-vocabulary skill and reference it with `uses:`.
- **Notes say why.** Use `note:` for the reason behind a rule or a decision the person made, so the
  next reader doesn't "fix" it.

## 4. Review for ambiguity

For new behavior, the best ambiguity check is an independent reading: have someone who has not seen
the code (another agent, given only the changed steps and data blocks) write acceptance tests from
the English. Every place they had to guess, quote the line back into the English as a fix. In the
cockatiel trial the reader found a note that contradicted a `>` line about what happens in the gap
between a slot freeing and the next call starting; nothing else would have found it before code
existed.

Named rules (`rule name: ...`) count toward a build's contract only when its steps or data blocks
mention the rule's name; a rule that belongs to one data block is better written as a `rule:` line
inside that block.

In the build profile, a shape line for code that doesn't exist yet is written as the intended line,
marked `(new)`: `` `public async execute<T>(fn, signal = neverAbortedSignal, priority = 0)` (new) ``.

Go through the checklist in `references/style.md` for every step you touched. For each gap, either
answer it in the English or ask the person. Then look outward: does the change interact with
another tree? (Example: an API that creates stories at 1 point, and a front page that hides stories
under 5 points, means new stories never show. Each tree is fine alone; together they surprise.)
Raise any interaction you find.

## 5. Check and hand over

```
ladder check <ladder.json>        # parses, vocabulary bound; lists edited steps and stale code
ladder hashes <ladder.json>       # optional: confirm which step hashes changed
```

Expect the changed steps to show as `edited` and their code as `stale` (so `check` exits 1, "problems
found": after an English edit that is the expected state, not a failure): that is what tells
ladder-generate what to regenerate. If a change was only rewording that changes no behavior (a typo,
a clearer sentence, a resolved DECISION note turned into a plain note), the person can run
`ladder retag <ladder.json> <ids>` instead of regenerating. Steps under a changed parent show `parent-changed`; re-read
them, and leave them unchanged if they still fit.

Show the person a short before/after of each changed step (or the diff), list any questions you
asked and the answers you wrote in, and name the steps whose code is now stale. Next step:
regenerate with the ladder-generate skill. Approval (`ladder stamp`) comes only after the person has
reviewed the regenerated code and its verification, and is theirs to give.

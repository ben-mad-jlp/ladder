---
name: ladder-generate
description: Generate, regenerate or repair code from Ladder English - turn .ladder steps into tagged code regions for any build (C#/ASP.NET/EF Core, TypeScript/React/React Native, Python, C++), regenerate only what an English change made stale (contract types first), insert code for new steps, and repair regions that fail to build. Use this after the English changes, when `ladder check` reports stale, missing or binding-changed regions, when someone says "regenerate", "update the code from the English", "port this to <language>", or "add a <language> build", or when a laddered build fails to compile.
---

# Generate code from Ladder English

Generated code comes from three inputs: the English tree, the build profile for the language, and
the vocabulary bindings. The LLM writes code; the `ladder` tool decides whether to accept it (markers,
tags, hashes, coverage). Then the build and the comparison decide whether it is right.

Format: `${CLAUDE_PLUGIN_ROOT}/reference/ladder-format.md` (sections 5 to 7). Run the tool as `ladder
<command>` (or `python3 ${CLAUDE_PLUGIN_ROOT}/tool/ladder.py <command>`).

## 0. Before generating

- `ladder check <ladder.json>` must parse cleanly with every capability bound for the target build.
  Fix the English (ladder-write) or vocabulary (ladder-vocabulary) first.
- The build must have a profile (`conventions` in ladder.json). Without one, generated code will not
  match the codebase; write it first with the ladder-profile skill.
- `generator.command` in ladder.json is the program that writes code (default: `claude -p` with tools
  off). Check it runs: `echo "Reply with: ok" | claude -p --output-format text --tools ""`.

## 1. Choose the operation

| Situation | Command |
|---|---|
| A new build or language (file does not exist yet) | `ladder generate <ladder.json> --build=<name>` |
| English edited: stale regions, new steps, changed contract | `ladder regen <ladder.json>` |
| Only one build | `ladder regen <ladder.json> --build=<name>` |
| A binding or profile changed but the English didn't | `ladder regen <ladder.json> --redo=<step ids>` |
| See the prompts without calling the generator | add `--dry-run` |
| The build or a run fails | `ladder repair <ladder.json> <errors.txt> --build=<name>` |

When a region holds nested regions (a class holding its members), regenerating it regenerates
the nested ones too: the prompt includes their English and the exact marker lines they must keep,
and a reply that drops or mis-tags one is rejected (with one retry, told why). Stale `@contract`
regions are regenerated first, all of them.

Set `"check_command"` to build what callers and tests see, not just the project: for .NET the whole
solution including test projects (`["dotnet", "build", "My.sln", "--nologo", "-v", "q"]`), because a
renamed method or a reordered constructor compiles alone and breaks every caller. Errors in other files
are passed back to the generator too, marked as possibly caused by the file it wrote.

If ladder.json sets `"check_command"` (`["npx", "tsc", "--noEmit"]`), `generate` builds after writing
and retries once with the compile errors; `"format_command"` runs the formatter over every file the
generator changed. `generate --out=<file>` writes somewhere else, to try a regeneration safely.
`repair` can open an `@support imports` region at the top of a file that has none when the fix is a
missing import, and it repairs `@contract` regions (entities, DTOs) as well as step regions.

**Blind regeneration** (`ladder regen --build=<name> --blind`, in a scratch copy): rewrites every
`@contract` region and every innermost step region of a build from the English and the profile, one
at a time from the top of the file, with the old code of regions not yet rewritten hidden from the
generator; `@support` code and regions that hold other regions are kept. Use it to test whether the
English and profile are enough, especially for files only partly in the slice, where `generate` would
drop everything outside it. Every region prompt now includes the build profile.

`regen` exits 1 if any region's reply was rejected (that region keeps its old code; the reason is
printed and the prompt and reply are logged), 0 otherwise. `generate` writes only the steps in the
build's `steps` scope, and gives the generator the build's `"reads"` files as read-only context.

**Hand-edited regions.** If someone changed generated code by hand since it was generated or
approved, `regen`, `repair` and `generate` print `REFUSED` for that region and leave it alone. Don't
reach for `--discard-hand-edits` on your own: look at the edit (`git diff`, `git log -p` on the
file), then tell the person what it does and offer the fitting route. If it changes behavior, move it
into the English (ladder-write), regenerate, and run `ladder accept`. If it changes no behavior,
`ladder accept`. If it was a mistake, discard it, with their agreement.

`regen` does, in order: regenerate stale `@contract` types; regenerate the reference build's stale
regions; regenerate the other builds, each told to match the reference build's new code; insert
regions for new steps after their previous sibling and update the parent to call them. Every prompt
and reply is saved under `.ladder/regen/<time>/`.

**Adopted builds.** When the reference build is existing code that was transcribed (`"adopted": true`),
regenerating its stale regions *replaces hand-written code with generated code*. That is the moment
the codebase starts being driven by the English for those steps. Confirm with the person before
doing it the first time for a slice, and make sure reference traces were recorded first (see
ladder-verify) so you can prove nothing else changed.

If no generator command can run (no `claude` CLI), you may write the regions yourself, following
exactly what the prompt would ask: one region per step, the marker line `@node <id>@<hash>` with
the hash from `ladder hashes`, the profile's style, the vocabulary's calls. Then rely on the same
checks below.

## 2. Build, then repair

Right after generating, build and run the fast tests for each changed build (`dotnet build`,
`npx tsc --noEmit`, the project's test command). Save the compiler or test output to a file and run
`ladder repair` with it. It maps each error to the region it points at and regenerates only that
region, with the error in the prompt. It may add imports or declarations to `@support` regions
through `@add-to-support` requests; these are listed in its output, so review them.

**Failing tests that assert the old behavior are not repair material.** When the English changed
on purpose, a test that checks the old behavior should fail. Don't feed it to `ladder repair` (that
would pull the code back to the old behavior) and don't edit the test; list it for the person with
the step that changed. Repair is for compile errors and for tests the English says should pass.
Formatting is not behavior: running the project's formatter (`prettier --write`, `xo --fix`,
`dotnet format`) over generated regions is fine.

Stop after two repair rounds on the same error and report it. A generator that keeps failing on one
error usually means the English or the profile is missing something (a type location, a helper that
should exist), and that is where the fix belongs.

## 3. Read what was generated

Once the English has been approved (`ladder stamp`), `check` also compares each file's exported names
with the approved ones (`exports-changed`), and with `"consumers"` on a build (say
`["../../src/index.ts"]`) reports a new export the re-exporting file doesn't mention
(`consumer-missing`). After an English change that adds a public name, `ladder accept --exports` once
it's right. Code that does nothing (`void createContext;`) passes every check; only reading finds it.

The tool checks shape, not intent. Read every changed region against its step's English and look for
the quiet failures:
- types widened or re-declared locally instead of using the contract types (`Card & { hot: boolean }`):
  regenerate the `@contract` region, then `--redo` the step;
- constants that are not in the English, and missing error cases;
- swallowed exceptions or empty `catch` blocks;
- a library call that differs from the vocabulary binding;
- edits outside the step's purpose.

When the code is wrong because the English was ambiguous, fix the English (ladder-write) and
regenerate. Don't hand-edit generated regions to change behavior: the next regeneration will undo it,
and the English will no longer describe the code.

## 4. Data changes (EF Core and other ORMs)

When the project has `"schemas"`, prompts carry the exact entities each step refers to (tables,
columns, navigations). The generator must use them as they are; entity classes are support code and
never regenerated. A step marked `schema-changed` (a migration changed a column it relies on) is
regenerated with `ladder regen --redo=<id>` after a person re-reads it.

When data blocks or contracts change, entity and DTO types regenerate in `@contract` regions. The
generator never writes migrations. After the entities build, tell the person to run
`dotnet ef migrations add <DescriptiveName>` and review the migration before applying it anywhere.

## 5. Hand back

`ladder check` must show no untagged, stale or missing regions for the builds you touched. Until a
person approves the English it ends with "RESULT: awaiting approval" (exit code 3); that is expected. Report what
was regenerated per build, repairs and support additions made, anything you noticed while reading the
code, and the next step: verify with the ladder-verify skill before anyone approves.

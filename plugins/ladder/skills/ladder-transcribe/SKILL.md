---
name: ladder-transcribe
description: Transcribe existing code into Ladder - write the plain-English step tree (.ladder) that describes exactly what a slice of an existing codebase does, then tag that code with Ladder region markers without changing a single line of it. Use this whenever someone wants to bring existing code (a C#/ASP.NET/EF Core API, React or React Native logic, Python, C++, anything) into Ladder, "describe this code in our English language", "laddering" or "adopting" a feature, reverse-engineering behavior into English, or documenting what code really does as a reviewable spec, even if they don't say "transcribe".
---

# Transcribe existing code into Ladder

The goal is an English tree that a person can read and say "yes, that is what our system does",
plus tags in the existing code that tie every line back to a step. The code must not change:
transcription only describes. Changing behavior is a separate, deliberate step done later
through the English (see the ladder-write and ladder-generate skills).

Read `${CLAUDE_PLUGIN_ROOT}/reference/ladder-format.md` first if you have not seen the format in
this session. Run the tool as `ladder <command>`; if that is not found, use
`python3 ${CLAUDE_PLUGIN_ROOT}/tool/ladder.py <command>`.

## 1. Agree the slice

Transcribe one vertical slice at a time: a feature end to end. For a web + mobile + API system
that is typically the endpoints of one feature, the entities and database configuration behind
them, and the client logic (API client, hooks, state) both apps use for it. Not UI layout.

If the person did not name a slice, look at the codebase, propose one or two candidates (prefer
something with real rules: validation, paging, permissions, retries, but not the most critical
path) and ask before starting. List the files you will read and the files you will tag.

## 2. Set up the projects

A project is one tree plus the builds that implement it. A feature that spans an API and client
apps is two trees, because the server and the clients do different jobs: an API tree (implemented
by the API build) and a client tree (implemented by the web and mobile builds). Give them a shared
vocabulary and shared conventions:

```
ladder/<area>/vocabulary.ladder          shared by both projects
ladder/<area>/conventions/               shared.md, csharp.md, typescript.md
ladder/<area>/api/ladder.json            tree api.ladder; build "api" (csharp)
ladder/<area>/clients/ladder.json        tree clients.ladder; builds "web" and "mobile" (typescript)
```

Set `"baseline"` in each ladder.json to the branch the work will merge into (`"origin/main"`), so
`check` shows what a change touched even when nothing has been approved with `ladder stamp`.

Link the two: in each ladder.json, `"links": {"api": {"project": "../api/ladder.json", "test":
"<command>"}}` (and `"clients"` the other way), and give every client step that calls the API a
`calls: api [api.1.1]` line. The `"test"` is a test that runs the real client code against the
running API on the test database (one sign-in that succeeds, one that fails, one missing
permission); it is the only thing that catches a wrong assumption about the code between the two
trees, like an HTTP client that rewrites error messages.

```
ladder init ladder/<area>/api --name "<Area> API" --build api:csharp --adopted
ladder init ladder/<area>/clients --name "<Area> clients" --build web:typescript --build mobile:typescript --adopted
```

Then, in each ladder.json, point `"vocabulary"` and the `"conventions"` entries at the shared
files (`"../vocabulary.ladder"`, `"../conventions/csharp.md"`), delete the per-project copies that
`init` created, and list each build's `files` (paths relative to that ladder.json). The API
project's `compare.reference` is the API build: the existing system is the reference every
future API build is compared against. For the clients project, use the web build as reference.

(One tree implemented partly by different builds is also possible: give each build
`"steps": ["client.*"]`, glob patterns of the step ids it implements, so `check` and `generate` only
expect those.)

**A library or a single module** (no API, no clients) is one project. Give each source file its own
build with a `steps` scope, and list files you are not transcribing but that the code relies on
(hand-written types, small helpers) in each build's `"reads"`, so the generator sees them:

```
ladder init ladder/<lib> --name "<lib> core" --build index:typescript --build heap:typescript --adopted
```
or in one go: `ladder init ladder/<lib> --name "<lib> core" --build index:typescript:../../source/index.ts
--build heap:typescript:../../source/heap.ts --steps index=q.* --steps heap=heap.* --adopted`. Then add
`"reads": ["../../source/types.ts"]` and each build's `"data": [...]`, the names of the data blocks its
`@contract` regions spell out, so editing one file's data doesn't make every file's types stale. Data
blocks no build lists describe types that live in the `reads` files. Delete the placeholder step
`init` wrote into the tree.
`compare.reference` names the build other builds are ported from and compared with; with one build
per file there is nothing to port, so it simply names the main build.

## 3. Read everything that decides behavior

Read the slice completely, including the places where rules hide: attributes and data
annotations, EF Core `OnModelCreating`, validators, middleware and filters, auth policies,
configuration defaults, client-side fetch wrappers and retry helpers, and the callers of each
function. `references/where-rules-hide.md` has a checklist per stack; skim the sections for the
stacks in this slice. For a library, the public surface is the contract: every exported name,
option, event, thrown error and message, and the *order* in which things happen (events relative
to each other, synchronous vs microtask vs timer). Callers and tests depend on that order even when
no document mentions it.

Read the app-wide failure handling too, even when it is outside the slice: a global exception
middleware or filter often turns an exception type into a status and body (an
`InvalidOperationException` answering 409, not 500). Write that mapping once as a vocabulary
capability ("API error answer") the steps use, rather than guessing a status per step; replay
then checks it.

While reading, collect facts, not impressions: exact routes and status codes, exact error
messages, limits and whether they are inclusive, defaults, ordering and tie-breaks, paging
math, what happens on empty, missing, duplicate and too-long input, time zones and units,
retries and delays, what is written to the database and when, and who may do what.

## 4. Write the tree

Write `<area>.ladder` so it describes what the code **does today**, in plain English:

- One step per job the code does. Use the code's own structure as a guide (a step often maps
  to an action method, a service method, a hook function or a well-defined block), but name
  steps by what they do for the user, not by class or method names.
- Contracts (`in:` / `out:`) name the exact fields as they appear on the wire (JSON names), in
  backticks. Statuses and error bodies go in `out:`. For a library, they name public methods,
  properties, options and events exactly as exported.
- State a step keeps (fields of a class, a hook's state) goes in a `data` block, not in the parent
  step's prose, so later changes to state are visible as data changes (see ladder-profile on giving
  state its own region).
- Every number, message, limit, order and default appears exactly as the code has it.
- Database entities are not described: the English refers to the schema (see "Entities and the
  database" below). Shapes the code owns (DTOs, request and response bodies, in-memory state) become
  `data` blocks: fields in words (whole number, text up to 120 characters), plus `rule:` lines.
  Repeated validation rules become named `rule`s.
- Libraries the steps rely on go in `uses:` lines and the vocabulary (use the
  ladder-vocabulary skill for that file). Do not name libraries or language types in the steps.
- No C#, TypeScript or SQL in the English. "Kept between 1 and 50", not `Math.Clamp(x, 1, 50)`.

**Describe, don't fix.** When code looks wrong, surprising or inconsistent (an off-by-one, a
missing check, a message that contradicts another), write what it does and add a
`note: QUESTION: ...` explaining what looks off. Never quietly write the "right" behavior: the
English must match the code, or every comparison later will be meaningless.

**Two clients doing the same thing.** When web and mobile implement the same logic (for example
their own `useNotes` hooks), write one shared step for the behavior and record every difference
as `note: DIFFERS: web ...; android ...`. Read both files line by line for this; page sizes,
retry delays, error messages and optimistic updates drift quietly. The person decides later which
behavior wins; transcription only reports.

## 5. Tag the code (comments only)

1. Print the hashes for the finished tree: `ladder hashes ladder/<area>/ladder.json`.
2. In every adopted file, wrap the code for each step in `@node <id>@<hash>` ... `@end` comment
   lines, using the file's line comment (`//` or `#`). Wrap everything that belongs to no step
   (usings, namespace and class braces, DI wiring, helpers shared by several steps) in
   `@support <short label>` ... `@end`, and always give support regions a label: the generator
   can only add imports to labeled ones. Wrap entities, their EF Core configuration
   (`OnModelCreating`) and DTOs in `@contract types@<contract hash>`, because the tree's data blocks
   describe them; `ladder hashes` prints the contract hash on its last line.
   For a class, put its fields in their own region (`@contract state@<contract hash>`) rather than
   in the parent step's region, so adding a field later doesn't regenerate the whole class. Put a
   member's doc comment (JSDoc, XML docs) inside that member's region.
   A parent step can own a whole unit, with its sub-steps nested inside: a controller class in
   `@node api.1`, each action in its own `@node api.1.x` inside it; a React hook in `@node client.1`,
   with `load`, `add`, `archive` each nested as their own step, leaving the state declarations and
   the `return {...}` in the parent's region.
3. Add only whole comment lines. Do not move, reformat, reorder or re-indent code, and do not
   touch blank lines inside code, so the diff is pure additions. Markers can sit between any two
   lines, including inside a method body, and regions may nest.
4. If one step's code is scattered (a helper used by two steps), tag the helper with the step it
   mainly serves, or as support, and mention it in the step's `note:`.

For more than a couple of files, list the regions in a `regions.json` next to ladder.json and let
`ladder tag` write the markers:

```json
{"../../src/notes/NotesController.cs": [[1, 8, "support usings and namespace"], [9, 80, "node api.1"],
                                         [20, 41, "node api.1.1"], [43, 79, "node api.1.2"]],
 "../../src/notes/NoteDto.cs": [[1, 2, "support namespace"], [3, 20, "contract NoteDto"]]}
```

`ladder tag <ladder.json> regions.json --base <base>` rebuilds each file from `<base>` (the commit before
any tags; record it when you start, since once the tags are committed HEAD is the tagged version) with the
marker lines added and the tree's current hashes, so re-running it after the tree changes is safe and the
diff stays comment lines only. `ladder adopt-check <ladder.json> --base <base>` proves it. Line numbers
are the untagged file's; regions may nest. Commit `regions.json` with the tree.

**Shapes another system reads.** An object the code hands to another system (a snapshot for an
assistant, an analytics event, a message on a queue, a log record a dashboard parses) is a contract
even when nothing in the code declares its type: write it as a data block with its exact keys and say
which step builds it ("the snapshot is a MyAlertsSnapshot"). In round 8 the English said "what is
selected (the alert being deleted, ...)"; blind regeneration chose its own keys and the assistant's
tests failed. The same goes for attributes another system finds on the page (`data-sofia-target`,
`data-testid` a test runner uses): name the attribute in the English or in the vocabulary. In round 10
the English said "the assistant's target"; regeneration wrote `data-assistant-target`. The props of a component other files render, and any exported type
other files import, are contracts too: data blocks in `@contract` regions (round 12: a view's props were described in
prose and blind regeneration renamed them; the container and the story fixtures stopped compiling). Accessibility labels and roles
are the same kind of contract (screen readers and tests find controls by them): list them in the step that renders.

**Cite a rule wherever its value is used.** A named rule reaches only the steps that say "(rule <name>)". In round 13
three parsers checked the same weight limit and only one cited the rule; a change to the rule regenerated that one and
left the other two with the old limit, while every check and test passed. `check` now warns `rule-uncited`, but write
the citation in the first place.

**Branches that never run.** Code often guards a case that cannot happen (a split that always yields a piece, a check
after an earlier one already returned). Say so in the English, with the reason ("there is always a piece, so ... never
fires"); written as a live branch, regeneration makes it reachable. In round 13 "no pieces: error ..." became
reachable for blank text, and the differential run caught it in 118 of 200 seeds.

**Name the exact signal.** When the code decides on one particular field and the English says something looser
("while signed in", "once loaded", "when valid"), name the field: "while the auth store holds an employee (its
`isAuthenticated` flag is not read)". In round 11 "signed in" was regenerated as `isAuthenticated` twice, where the
code read the employee id; only a test that set one and not the other told them apart. The same goes for a field
a mapping reads from: write `requiresAcknowledgement` its `requireAcknowledgement`, not just the target name.

**Files several areas share.** A file another project already tags (an app's API module, where each area added
its own functions) gets this area's regions too: tag them inside the other project's `@support` region with
`ladder tag ... --base HEAD` (line numbers of the tagged file, so the other project's markers stay), and name each
project in the other's build as `"shared_with": ["../../<area>/<project>/ladder.json"]`. Without it, each
project reports the other's regions as `unknown-step`.

**Large files.** When only part of a file belongs to the slice (8 members of a 1,700-line service),
tag the rest as `@support` with a label and transcribe only the slice's members. To try regenerating
such a file, don't use `generate` (it writes the whole file from the English and drops the support
code); in a scratch copy run `ladder regen <ladder.json> --build=<name> --blind`, which rewrites only
the slice's regions from the English, hides their old code from the generator, and keeps everything
else.

**Entities and the database.** Don't describe tables in the English. Add each EF model (one per
DbContext, usually one per database) to ladder.json `"schemas"` (format section 3), check
`ladder schema <ladder.json>` shows it, and refer to it: `reads:` / `writes:` on each step that touches
the database, and `[[Entity.Property]]` where a sentence depends on an exact column (filters,
ordering, what is loaded with each row). Tag entity classes and their configuration as `@support`:
they belong to the EF model and its migrations, and are never generated. To keep their tags and
hand edits checked, give them a support-only build (`"steps": []`). (In the API trial a
regenerated entity mapped every property to a camelCase column; every query failed on SQL Server
while the tests, built from the same model, passed.)

If the project has no `ModelSnapshot.cs` (its schema changes are SQL scripts), export the model with
`dotnet run --project ${CLAUDE_PLUGIN_ROOT}/tool/exporters/efcore-schema -p:ModelsProject=<the
project with the DbContexts> -- --context <Name> --out ladder/<area>/api/schemas/<name>.json` (one
`--context`/`--out` pair per DbContext) and point `"schemas"` at the JSON with `"kind": "json"`.
Re-export after each schema change and commit the JSON. Before anything is stamped,
`ladder check --since=<base commit>` shows which steps a schema change affects.

## 6. Verify

Run these and fix what they report before handing back:

```
ladder adopt-check ladder/<area>/ladder.json      # must say: only comment lines added
ladder check ladder/<area>/ladder.json            # no untagged code, no missing steps, vocabulary bound
```

`check` will list every step as "new, not yet approved" and finish with "RESULT: awaiting approval"
(exit code 3): that is the expected state until a person approves. Anything listed under a build, or
"problems found" (exit code 1), needs fixing.
If you can build the project here (`dotnet build`, `npx tsc --noEmit`), do it: comments must not
break a build, but a marker in the wrong place (inside a string or a multi-line expression) can.

**Trial regeneration** (the real test of the English and the profile): in a scratch copy,
`ladder regen <ladder.json> --build=<name> --blind --repair=3` rewrites the build's regions from the
English alone, then builds and repairs until it compiles (or says it still does not); then run the
tests. (`ladder generate <ladder.json> --build=<name> --out=<scratch file>` writes a whole file from the
English instead, without touching the real one; swap it in, build and run the tests.) Every compile error or failing test is a gap: a missing sentence in the
English, or a missing shape rule in the profile. Fix those, not the generated code. Set
`"check_command"` (e.g. `["npx", "tsc", "--noEmit"]`, with `"check_cwd"` relative to ladder.json) and
`"format_command"` (e.g. `["npx", "prettier", "--write"]`) in ladder.json so generation retries on
compile errors and output matches the formatter.

## 7. Record reference scenarios (when the API can run)

For a library (no API), write a differential harness instead
(`${CLAUDE_PLUGIN_ROOT}/skills/ladder-verify/references/differential.md`) and record the existing
code's runs as the reference; the HTTP steps below don't apply.

Write `ladder/<area>/scenarios/<name>.json` files that exercise the slice's endpoints:
happy paths, each validation error, not found, paging edges, permissions. Use the format in
`${CLAUDE_PLUGIN_ROOT}/skills/ladder-verify/references/scenarios.md`. If the existing API can run
against a test database (never production), record the reference traces:

```
ladder replay ladder/<area>/api/scenarios --base http://localhost:5000 --out ladder/<area>/api/traces/api \
  --mask id,createdUtc,updatedUtc --header "Authorization: Bearer <test token>" \
  --before-each "<command that resets and reseeds the test database>"
```

If it cannot run here, still write the scenarios and say exactly how to record them.

## 8. Hand back

Report, briefly:
- the tree's steps (ids and titles) and the data blocks, rules and capabilities it defines;
- every `QUESTION` and `DIFFERS` note, as a list the person can decide on;
- the files tagged and the result of `adopt-check` and `check` (and the build, if run);
- the scenarios written and whether reference traces were recorded;
- the next step: a person reads the English and runs `ladder stamp` to approve it. Stamping also
  records the tagged code (`ladder.code.json`); from then on, an edit to that code without an English
  change shows up in `ladder check` as `hand-edited`, so commit that file and run `check` in CI.

# The Ladder format (v1)

Ladder keeps a program's behavior in plain English and generates code in any language from it.
The English is what people write and review; code regions are tagged back to the English;
the `ladder` tool checks the tags mechanically and compares builds by running them.

Contents: 1 Project files · 2 Trees · 3 Data and rules · 4 Vocabulary · 5 Regions in code ·
6 Build profiles · 7 ladder.json · 8 Approval and the lock · 9 Traces and comparison · 10 Commands

---

## 1. Project files

```
ladder/                       (any folder; one project per area of the system)
  ladder.json                 the project: tree, vocabulary, builds, comparison
  <area>.ladder               the English tree (steps, data, rules)
  vocabulary.ladder           capabilities the English may use, bound per language
  conventions/shared.md       build profile parts every language shares
  conventions/<lang>.md       one build profile per language or build
  scenarios/*.json            recorded inputs for comparing builds
  traces/<build>/<run>.jsonl  what each build did on each scenario (generated)
  ladder.lock.json            the last approved English (written by `ladder stamp`)
  ladder.code.json            fingerprint of each region's code as last approved or generated
  .ladder/regen/...           every prompt and reply the generator saw (for review)
```

## 2. Trees

A tree is indented plain text. Two spaces per level. `#` starts a comment line.

```
[api.1] Answer a request to the notes API
  in: request with `method`, `path`, `body`
  out: response with `status` and `body`
  effects: reads and writes notes
  uses: current user
  > GET "/api/notes" is answered by [api.1.1]
  note: every route requires a signed-in user

  [api.1.1] List the user's notes
    in: page number, page size
    out: `items`, `page`, `pageSize`, `total`
    > page size is kept between 1 and 50
```

| Line | Meaning |
|---|---|
| `[id] Title` | A step. The id is stable forever (letters, digits, `.`, `-`, `_`); indentation makes it a child of the step above. |
| `in:` / `out:` | The step's contract. Names in `backticks` are exact field names every build must use. A build may reshape anything inside a step, never its contract. |
| `effects:` | What the step does to the outside world (database writes, messages, files). |
| `> ...` | How the step works, one plain sentence per line. Optional. |
| `note:` | Anything a reviewer or the generator should know. |
| `uses:` | Capabilities from the vocabulary this step relies on, separated by `;` or `,`. |
| `reads:` / `writes:` | Database entities the step reads or writes (section 3, schema references). |
| `calls:` | Steps in another tree this step calls: `api [api.1.1]` (section 4, links between trees). |
| `compare:` | Which differences between builds don't matter for this step (see 9). Verification only. |

A step's **hash** covers its title, contract, `>` lines, notes, `uses:`, `reads:` and `writes:` (not its children, and
not `compare:` lines, which change how builds are compared, never the code, nor `calls:` lines, which
say which other tree's step this one calls). Changing any of them makes code generated from the old
wording *stale*. Approval (`stamp`) covers the whole step, `calls:` included: adding or removing a
`calls:` line shows the step as edited, not its code as stale.

Refer to another step as `[id]` inside text ("answered by [api.1.1]").

## 3. Data and rules

Data blocks and named rules sit at the top level of a tree file (no indentation):

```
data Note
  id: whole number, assigned by the database
  owner: the signed-in user's id
  title: text, 1 to 120 characters after trimming
  tags: list of Tag names
  rule: tag names are unique within a note

rule tag name: 1 to 24 characters from a-z, 0-9 and dashes
```

- `data <Name>` (capitalized) then indented `field: description` lines, `rule:` lines and `note:` lines (notes, any
  number, not fields).
- `rule <name>: <text>` names a rule several steps refer to ("follows rule tag name"). When a rule changes,
  `check` lists the steps that cite it (`rule-changed`) and `regen` rewrites them. A value the rule states (a limit,
  a message) that the code keeps in a constant goes in a `@contract rule <name>@<hash>` region: its hash is the
  rule's text, so changing the rule makes it stale and `regen` rewrites it. `check` warns `rule-in-support` when such
  a value sits in `@support` code, which no change to the rule can reach.
- Data blocks and rules are part of the **contract hash**: changing them makes `@contract`
  regions stale (see 5), and builds regenerate their entity/DTO types first.
- Describe fields in words (whole number, text, Unix seconds, list of X), not language types.
  The build profile says how each language represents them (EF Core entity, TS type...).
- **Database tables are not data blocks.** When a database schema exists (an EF Core model, a
  database), the English refers to it instead of describing it; see "Schema references" below. Data
  blocks are for shapes the code owns: DTOs, request and response bodies, in-memory state.

### Schema references

The project names where its schema lives, one entry per EF model (a DbContext) or database:

```json
"schemas": {
  "qbs":     {"kind": "efcore-snapshot", "source": "../../../qb_api_models/Migrations/QbsDbContextModelSnapshot.cs"},
  "reports": {"kind": "json", "source": "schemas/reports.json"}
}
```

`efcore-snapshot` reads the model snapshot the migrations maintain (tables, columns, types, keys,
navigations, indexes). `json` reads an export for databases without migrations
(`{"entities": [{"name", "table", "keys", "properties": [{"name", "column", "type", "required", "maxLength", "generated"}],
"navigations": [{"name", "target", "many", "foreignKey"}]}]}`). `ladder schema <ladder.json> [Entity]`
prints what the English can refer to.

Steps refer to it two ways:

```
[emp.1] List employees for the login picker
  reads: Employee_MainTable, qbs:Division
  > employees whose [[Employee_MainTable.TerminatedOn]] is empty, each with their [[Employee_MainTable.Division]]
  > ordered by [[Employee_MainTable.LastName]], then [[Employee_MainTable.FirstName]]
```

- `reads:` / `writes:` list the entities a step touches (class name or table name).
- `[[Entity.Member]]` marks an exact property or navigation inside a sentence. Use it where precision
  matters (filters, ordering, what is loaded), not on every word.
- A `schema:` prefix is needed only when two schemas have an entity of that name.

`ladder check` reports references that don't exist (with a suggestion), ambiguous ones, and steps
writing to two schemas (no single transaction; a warning). `stamp` records the facts each step relies
on; a migration that changes one (a column's type, length, nullability or name) shows the step as
`schema-changed` until it is re-read and approved. A whole-entity reference (`reads: X`) also relies on
every member of X: removing or retyping one flags the step, and for `writes:` so does a new required
column the database doesn't fill in (inserts must now set it); new optional columns flag nothing.
A step that never inserts says `writes: X (updates only)`, and new required columns don't flag it;
neither does a required column with a default. When a new required column does flag an inserting
step, `check` also lists code elsewhere in the repository that creates rows of that entity
(`new Dbo_Timeclock {`, `INSERT INTO [dbo].[TIMECLOCK]`): tests, seeders and other services must set
it too, and no step covers them (`other-writers`: source files only, skipping `.ladder/` logs, files git
ignores and ladder.json's `"ignore"` globs (paths from the repository root, for copies or vendored code); past 10 places the full list goes to
`.ladder/other-writers-<Entity>.txt`). A change seen only through a whole-table reference
(`reads:` / `writes:`), in a column the step never names, is a warning (`schema-changed-table`), not an
approval item; name the column with `[[Entity.Member]]` if the step relies on it. An attribute the old facts never carried
(`generated by the database`, `default ...`, added by a newer exporter) is not compared, so switching
exporters doesn't flag steps.
Before the first stamp, `ladder check --since=<git ref>` compares with the schema files as they were
at that commit. Generator prompts include the referenced entities exactly, and entity classes are
never generated: tag them as support code (a support-only build has `"steps": []`).

No `ModelSnapshot.cs` (the database changes by SQL scripts, not EF migrations)? The plugin's
`tool/exporters/efcore-schema` builds each DbContext's model offline and writes the `json` kind;
see its README.

## 4. Vocabulary

`vocabulary.ladder` lists the capabilities the English may rely on, and binds each one to a
concrete library, version and call per language (or per build name).

```
capability save data
  in: entities that were added or changed
  out: nothing
  csharp: Microsoft.EntityFrameworkCore.SqlServer 8.0.10 | await db.SaveChangesAsync()
  python: SQLAlchemy 2.0.36 | session.commit()
  known: nothing is written until SaveChangesAsync; call it once per request
  check: scenarios/notes_create.json shows the note on a second GET

capability current user
  in: nothing
  out: the signed-in user's id
  csharp: Microsoft.AspNetCore.Authentication.JwtBearer 8.0.10 | User.FindFirstValue(ClaimTypes.NameIdentifier)
  typescript: (client) the bearer token from the sign-in context
```

- Any indented key other than `in`, `out`, `known`, `check`, `note` is a **binding**; the key
  is a language (`csharp`) or a build name (`web-ts`), the value is `package version | call`.
- `ladder check` reports a step that uses an undefined capability, and a build with no binding
  for a capability its steps use.
- A binding of code in the same repository starts with `(in repository)` and names its files
  (`typescript: (in repository) src/services/storage.ts | await storage.get<T>(key)`); paths are
  resolved from the project folder, its `check_cwd`, or any folder above. Generator prompts include
  each such file the region's steps use (a long one cut to the declarations its calls name), so the
  generator calls what exists; repair prompts forbid replacing a binding with another library.
  `check` warns `binding-not-called` when no file of a build, and no other build of the project with
  the same binding, calls any name the binding's call part calls (`get`, `set` above): the code may
  use another library or an API that does not exist. (A controller step that relies on the error
  answer its service throws into is not warned.)
- Changing a capability's in/out flags its users for re-review; changing one binding flags
  only that language's builds. When the code must change, regenerate with `--redo=<step ids>`; when
  the approved code still fits (another area added a call or a claim to a shared capability), read it
  against the new binding and `ladder stamp`. A vocabulary shared by many areas changes often: expect
  each edit to ask every project that uses the capability for that review.
- Framework plumbing (routing, DI, rendering) and small utilities are not capabilities; build
  profiles cover them. Keep the vocabulary to what the English actually needs to say.

### Tests for claims

A binding and its `known:` lines are claims about a library, and nothing in the English or the
types can check them: a wrong claim generates code that compiles and passes `check`. Give each
capability the steps rely on a `test:` line that exercises the real library:

```
capability HTTP client
  in: a request
  out: the response body, or an ApiException
  typescript: (in-repo) src/core/http/client.ts | http.post(path, body)
  known: a 401's message is always "Unauthorized"; the body is in responseData
  test: typescript | npx vitest run ladder/auth/clients/vocab/http-client.test.ts
```

`test: <binding key> | <command>` (or just a command, for every binding). `ladder test` runs them
(and link tests, below) from the project's `check_cwd`, so paths in a command are relative to it, and
records each result in `ladder.code.json` against what it tested: the capability's in/out, binding,
`known:` lines and command. A project runs and checks only the tests of capabilities its own steps
`use:`, for bindings its builds have (a build's name or language), so an API project and a client
project can share one vocabulary. `check` reports a failed test as a problem (with the assertion's
expected and received values when the output shows them), and as warnings: a capability with
`known:` lines that steps use and no test checks (`untested-capability`), a test never run, and a test
whose subject changed since it ran (`test-stale`). The files a command names (a script, a test
file) are part of that subject too, so editing a test makes its result stale; files it reaches
only indirectly are not. A capability whose test touches database tables names them with `reads:` /
`writes:` lines, like a step; a schema change to those tables then makes the test stale too.

The project's own behaviour tests (the slice's unit or integration tests) go in ladder.json:
`"tests": [{"name": "unit", "command": "npx vitest run src/x.test.ts", "builds": ["hooks"]}]`
(`builds` optional: all tagged builds by default). `ladder test` runs them with the others and records
each result against the command, the files it names and the code of the builds it tests, so any change
to that code makes the result `test-stale`; a failed one is a problem. A project with tagged builds and
no `"tests"` gets an `untested-project` warning: nothing records that its code passes the slice's
tests. `ladder test` runs each distinct command once, however many capabilities, links or tests name
it, and records the result for each.

### Links between trees

When one tree calls another (a React client calling the API), the calling step says so:

```
[authsvc.1] Sign in from the app
  calls: api [api.1.1]
```

and ladder.json names the other project, optionally with a test that runs both sides together:

```json
"links": {"api": {"project": "../api/ladder.json",
                  "test": "npx vitest run ladder/auth/clients/harness/seam_login.test.tsx"}}
```

(`"links": {"api": "../api/ladder.json"}` without a test.) `check` resolves every `calls:` item.
`stamp` records the called step's contract: its `in:`, `out:` and `effects:` lines and the data
blocks they name. When that contract changes, the calling step shows as `linked-changed` until it
is re-read and approved, so a change to the API's answer reaches the client's review. A caller also
relies on every step the called step's English names, transitively (`out: what [sa.4] answers`, then
`[sa.4]` uses `[as.2]`, which checks the name with `[as.11]`): `stamp` records those steps' hashes too,
and when one changes while the contract text does not (a new refusal three steps down), the caller
shows `linked-changed` naming the changed step and the path to it, and the called project warns
`has-callers` on the changed step. A called step that is itself waiting on a change in a further tree
flags its callers as well, so a change in the API reaches a screen that calls it through a library.
Steps in the calling tree that rely on that step are flagged too: any step whose English names it
(`> signs in through [authsvc.1]`), and so on outward. So name the step you use, in the English.
The message lists what changed line by line (`out: was ...; now ...`, `data ClockInRequest gained
field source: ...`). When a data block of the called step changed and a file the calling project
reads but never generates (its builds' `"reads"`) declares a type of that name (`ClockInRequestDTO`),
`check` warns `type-drift`: nothing will update that file. If
the called project lists the caller in its own `"links"`, its `check` warns that an edited step has
callers (`has-callers`); with `--since=<ref>` it compares the called step's contract with that commit
instead of the lock. Generator prompts for a calling step include the called step's contract. A link
with callers but no `"test"` is reported as `untested-link`: only running both sides catches a
wrong assumption about the code between them. A call into a step its own project has never approved,
or has changed since approving, is warned `linked-unapproved`: its English may still change, so stamp
the called project first (or re-read the caller once it is approved).

## 5. Regions in code

Every line of a laddered file sits in a region, marked with the language's line comment:

```csharp
// @support usings and helpers
using Microsoft.EntityFrameworkCore;
// @end

// @contract types@3fa9c1
public record NoteDto(int Id, string Title, ...);
// @end

// @node api.1.1@b70d22
public async Task<ActionResult<PagedNotes>> List(int page = 1, int pageSize = 20) { ... }
// @end

// Several steps merged in one region (optimized builds):
// @node api.1.2@1c2d3e api.1.3@4f5a6b
// @end
```

- `@node <id>@<hash> [...]`: code generated from (or tagged with) those steps at that hash.
- `@contract <label>@<hash>`: types that spell out the contract (DTOs, entities); the hash covers
  every step's in/out lines plus data blocks and rules. A label that names data blocks
  (`@contract UnpickShipment@...`) says which types the region holds: generation writes only those
  there (and is told where the build's other blocks live), and `check` reports `contract-misplaced` for
  a labelled region that declares no type, or declares a block another region's label names.
- `@support <label>`: hand-written code no step owns (imports, hosting, glue).
- `@end` closes the innermost region. Regions may nest, including a `@contract` region inside a `@node`
  region when a type sits between a member and its doc comment.
- Code outside every region is an error (`untagged`). A region whose hash differs from the tree
  is `stale`. A leaf step with no region is `missing`.

**Adopted code.** When existing code is transcribed into Ladder, tags are added as comment lines
only; `ladder adopt-check` proves the file differs from git HEAD only by added comments. Set
`"adopted": true` on that build in ladder.json. Use hash `000000` for tags placed before the
tree is final; `ladder hashes` prints the current hashes to write in.

**Generator replies** may ask for a line in a support region (an import, a declaration):
```
@add-to-support usings
using System.Text.RegularExpressions;
@end-add
```
The tool adds it, deduplicated, and lists the addition in its output.

## 6. Build profiles

A build profile (`conventions/*.md`) is what the generator needs beyond the English for one
language: file and class layout, how a step is written and traced, how data is stored and
queried, naming, error handling, which runtime helpers exist, versions to pin. Profiles are
written once per language and shared by every tree. The English never contains language-specific
instructions; when a step truly needs one, write `note: (csharp) reuse the buffer`.

## 7. ladder.json

```json
{
  "title": "Notes API",
  "tree": "notes-api.ladder",
  "vocabulary": "vocabulary.ladder",
  "generator": {"command": ["claude", "-p", "--output-format", "text", "--tools", ""]},
  "pins": {"efcore": "8.0.10"},
  "builds": [
    {"name": "existing", "lang": "csharp", "mode": "literal", "adopted": true,
     "files": ["../api/NotesApi/Controllers/NotesController.cs"],
     "conventions": ["conventions/shared.md", "conventions/csharp.md"],
     "uses": "ASP.NET Core 8, EF Core 8 on SQL Server"}
  ],
  "compare": {"reference": "existing", "runs": ["notes_create", "notes_list"], "number_tolerance": 0}
}
```

`mode` is `literal` (one function per step, easiest to review and trace) or `optimized` (steps may
be merged in one region; must still tag every step it implements). `adopted: true` marks existing
code that was transcribed (checked by `adopt-check`). `steps` (optional) lists glob patterns of the
step ids a build implements (`["client.*"]`) when one tree is shared by builds that each do part of it;
without it, every leaf step must be tagged in every build. `"steps": []` means none: a support-only
build (an entity class, a file of shared helpers) whose tags, hand edits and exports are still checked,
or a contract-only build (DTO files whose `@contract` regions spell out data blocks).
`"data": []` likewise means no data blocks. `links` names other Ladder projects this tree calls (section 4). `data` (optional) lists the data blocks (glob patterns) a build's `@contract` regions spell out; with
`steps` and `data`, a build's contract hash covers only its own steps' in/out lines, its data blocks,
and the named rules they mention, so editing one file's types doesn't make every file's types stale
(`ladder hashes` prints the hash per build). Finer still: after generation, a `@contract` region that
declares types named after data blocks (`class ClockInRequest`, `interface IClockInRequest`,
`ClockInRequestDto`), or whose label names a data block (`@contract ClockStatus@...` over
`class ClockStatusResponseDto`), is re-tagged with a hash of just those blocks, so adding a field to
one block marks only the regions that declare it. Label a region after its block when the class
name doesn't follow it. Data blocks no build lists describe types that live in
`reads` files. `check_command` (with optional `check_cwd`) builds the code after `generate` writes a
file, and the errors for that file go back to the generator once. `format_command` runs on every
file `generate`, `regen` or `repair` changed. `after_generate` (optional) lists commands that rebuild files
derived from the code (an API's committed OpenAPI contract, client types generated from it); they run from
`check_cwd` after `generate`, `regen` or `repair` changed code.
`traces` (optional) names the trace folder a build's runs are in, when one harness covers several
per-file builds. `mutant: true` (with `"tagged": false`) marks a deliberately broken copy: it must differ
from the reference somewhere, and its differences are not failures. `consumers` lists files that
re-export a build (a barrel `index.ts`), checked for names the build newly exports.
`shared_with` (optional) lists the other projects (their ladder.json) whose builds tag regions in the same files,
like an API module every area adds functions to. Their step ids are foreign here: not `unknown-step`, not
recorded as this project's code, never regenerated by it. Name each project in the other's build too.
`"tagged": false` marks a build that is compared by behavior only, with no tag or coverage checks
(an outside implementation, a build not under Ladder, a deliberately broken copy for a mutation check).
`reads` (optional) lists files the generator may read but never writes
(hand-written types, small helpers the build imports). `vocabulary` and `conventions` paths may
point outside the project folder (`"../vocabulary.ladder"`), so several projects can share them. `generator.command` is any
program that reads a prompt on stdin and prints code; the default is Claude Code, tools off.

## 8. Approval and the lock

**Note markers** used by the skills: `note: QUESTION: ...` (existing behavior that looks wrong),
`note: DIFFERS: web ...; mobile ...` (two builds behave differently today), `note: DECISION: ...`
(a choice made without the person; review before approving).

**Before anything is approved**, set `"baseline": "origin/main"` (any git ref) in ladder.json.
With no stamp, `check` compares the tree with the tree file at that commit instead (a tree that did
not exist there, as in a first transcription, shows every step as new and is no problem): steps changed
since then show as `edited`, schema and linked-step changes are measured from it (as with
`--since`), and regeneration prompts show the baseline's wording as "Before". A stamp, once made,
takes over; an explicit `--since=<ref>` reviews against that ref for one run, stamp or not.

**Local files.** `.ladder/` in a project holds only local files: prompt and reply logs, and
`.ladder/generated.json`, what the generator wrote in this checkout. It ignores itself in git. A region
is hand-edited when its code matches neither the approved record (`ladder.code.json`) nor what was
generated here, so syncing the English into a scratch copy (which brings the working tree's
`ladder.code.json` with it) does not make the scratch copy's own generated code look hand-edited, and
`accept --from=<scratch>` reads what the scratch copy generated.

`ladder stamp` records the current English (step hashes and text, data blocks and rules, vocabulary hashes) in
`ladder.lock.json`. `ladder check` then reports steps edited since approval, steps whose parent
changed, new and removed steps, data blocks or rules added, edited or removed, and steps whose
`compare:` lines changed (`compare-edited`: loosening a comparison needs approval like any edit). It also flags
tree lines that parse but are indented wrongly (`format`). Regeneration prompts show the generator the approved wording
next to the new wording. Only a person approves, after reading the English and the code.

**Hand edits.** `stamp` also records a fingerprint of every `@node` and `@contract` region's own code
in `ladder.code.json` (nested regions, comment lines, blank lines and spacing are left out, so
reformatting doesn't count). `generate`, `regen` and `repair` record the regions they write. A region
whose code no longer matches is reported by `check` as `hand-edited`: the English may no longer
describe it. `regen`, `repair` and `generate` refuse to overwrite a hand-edited region (`REFUSED`),
because that would silently undo the edit. Resolve it one of three ways:
- the edit changed behavior: describe it in the English (ladder-write), then `ladder accept`;
- the edit changed no behavior (a refactor): `ladder accept <ladder.json> [step ids]`;
- the edit was wrong: regenerate with `--discard-hand-edits`, or revert it with git;
- the code was regenerated in a scratch copy and copied here: `ladder accept <ladder.json>
  --from=<scratch>/ladder.json` accepts each region that is exactly what the scratch project recorded
  as generated, and leaves anything else hand-edited.
`git diff` shows what the edit was. `stamp` also records each file's exported names; `check` reports
names added or removed since (`exports-changed`) until a person runs `ladder accept --exports`. Before the first
stamp, an adopted file is compared with its version at the project's `baseline` (else HEAD). Blind regeneration
tells the generator the names each hidden region exports, so it keeps them. Commit `ladder.code.json` with the code, and run `ladder check`
in CI so a hand edit can't merge unnoticed.

## 9. Traces and comparison

A trace is one JSON object per line: `{"step", "ev": "enter"|"exit", "ms", "info", "data"}`.
`info` is a short summary for people; `data` is the step's full result as canonical JSON
(sorted keys) and is what comparison uses. A run of every build on the same scenario is
compared step by step against the reference build: `same`, `close` (only numbers differ, within
`number_tolerance`), or `different`. A step that exists in only one build is listed as
"not comparable".

**What counts as the same.** By default every result must be identical. A step's `compare:` lines
say which differences don't matter for it; each line holds one or more clauses separated by `;`:

| Clause | Meaning |
|---|---|
| `ignore id, createdUtc` | those keys (at any depth in the result) are not compared |
| `any order` | this step's results may come in any order (compared as a set) |
| `` `items` in any order `` | the list under that key may be in any order |
| `numbers within 0.01` | numbers may differ by up to that much (overrides `number_tolerance`) |
| `any timing` | the step may answer earlier or later relative to other steps (see strict order) |
| `final result only` | only the step's last result is compared (retries, progress updates) |

`check` lists every differing result of a step, with the request it answered (`#15 POST /login`) when
the traces come from `ladder replay`; the first 10 per step, or all with `--all-differences`. Long
values are shown around the place where they first differ.

`ladder check` rejects clauses it doesn't understand. Use them for differences that are truly
harmless and that nobody can rely on; anything a caller or user can depend on belongs in the English
as behavior instead.

**Order across steps.** Results are lined up per step (the n-th result of a step against the n-th of
the same step). With `"order": "strict"` in `compare`, the order of results *across* steps must match
too, except for steps marked `any timing`. Use strict order for libraries and event-driven code, where
callers see the sequence. `"runs": ["s*"]` takes every reference trace whose name matches.
Trace step names must be steps of the tree; names a harness uses for its own bookkeeping go in
`"extra_steps"` (`http` is always allowed).

Two ways to get traces:
- **Inside the code**: generated steps are wrapped with a runtime span (the build profile says how).
- **From a differential harness** (libraries): log every observable event of seeded random call
  sequences and write each run as a trace, naming each event after the step that produces it.
- **At the boundary**: `ladder replay` sends recorded HTTP requests to a running service and stores
  each response as a step result (use the request's `"step"` field to name it). This needs no
  change to the service, so it works for the existing system as the reference build.
  `--mask name[:kind]` (or a scenario's `"mask": [...]`) handles values that differ every run:
  `value` hides it, `presence` keeps whether it is null, empty or set, `time` keeps a date-time
  relative to when the request was sent (`now+120m`; `time:s` to the second; a time without a zone
  is read as local time, `time:utc` reads it as UTC). For a value inside text ("Already clocked in
  since 10:55"), `--mask-text 'PATTERN=REPLACEMENT'` (or `"mask_text": [...]`) replaces regex matches
  in every string: `'\d\d:\d\d=<hh:mm>'`. Patterns apply in the order given, so put the longer one
  first (an ISO date-time pattern before an `hh:mm` one, or the time inside the date is replaced
  first). Each trace folder gets a `.replay.json` recording the Ladder version and the replay settings;
  `check` warns (`replay-settings`) when a build's traces were recorded differently from the
  reference's, since the difference may then be the recording's. In requests, `{{now}}`, `{{now+90m}}` and `{{now-2d}}`
  give ISO times. Replay refuses to overwrite traces that are committed to git (usually the reference
  build's) unless given `--force`. `{"wait": 32}` alone
  pauses between requests. `--observe "<command>"` runs after each request and its output is compared
  too (a SQL command count, a queue length). `save` paths without a prefix read the body.
  A masked value of 4 or more characters is also replaced wherever it appears inside the response's
  other strings (`<incidentId>` inside a message); shorter ones need `--mask-text`. Text masks are
  applied again when comparing, to both sides, from either side's `.replay.json`: adding a pattern to
  a newer recording masks the older ones too, without re-recording them.

**What is compared.** Each run of the reference is set against the same run of every other build that
has its own traces. Builds that share the reference's traces (`"traces": "<reference>"`, one harness
for several tagged builds) are not compared; to compare another recording (a second run of the same
code, a regenerated build) add it as a build with `"tagged": false`, named after its folder under
`traces/`. When no build has its own traces, `check` says "nothing was compared" and does not call the
comparison fine; a folder under `traces/` that no build names is warned `traces-unused`.

**An approved change of behaviour.** After a change through the English, the reference still shows
the old behaviour, so the regenerated build differs where the change was meant to. Once the
difference is reviewed and the English stamped, record the approved code as a build and make it the
reference: `ladder reference <ladder.json> --from=<build>` copies its traces into the reference's
folder and moves the old reference to `traces/history/<name>-<time>/`. Re-record other builds that
came from the old code.

## 10. Commands

```
ladder init <folder> --name NAME --build NAME:LANG[:FILE]... [--steps NAME=GLOB...] [--adopted]
ladder check <ladder.json> [--since=REF] [--all-differences]
                                                      tags, coverage, staleness, vocabulary, links, tests,
                                                      comparison; exit 0 ok · 1 problems · 3 only awaiting approval
                                                      --since: review steps, schema and linked steps against a
                                                      git ref instead of the last approval
ladder test <ladder.json> [NAME...]                   run capability and link tests; record the results
ladder hashes <ladder.json>                           current hash of every step
ladder export <ladder.json> [out.json]                the parsed tree as JSON
ladder adopt-check <ladder.json> [--base REF]         transcription changed nothing but comments
ladder generate <ladder.json> --build=NAME [--out=F]  write a build's file from the English (--out: elsewhere)
ladder regen <ladder.json> [--build=NAME] [--redo=IDS] [--dry-run] [--repair=N]
                                                      regenerate stale/new regions (contract first);
                                                      exit 1 if any reply was rejected; --repair=N: then
                                                      run check_command and repair, at most N rounds
ladder tag <ladder.json> <regions.json> [--base REF]  write a transcription's markers from line ranges
ladder repair <ladder.json> <errors.txt> --build=NAME regenerate the regions errors point at
ladder accept <ladder.json> [--build=NAME] [IDS]      accept hand edits (the English still describes them);
                                                      --from=SCRATCH: regions copied from a scratch copy that
                                                      are exactly what it generated (copy the files first)
ladder retag <ladder.json> IDS [--build=NAME]         English reworded, behavior unchanged: update markers only
ladder reference <ladder.json> --from=BUILD          an approved change: BUILD's recording becomes the reference
              [--retire=A,B]                          (recordings of the old code that cannot be made again
                                                      move to traces/history/ and leave the builds)
ladder schema <ladder.json> [ENTITY]                  the database schema the English can refer to
              (generate, regen and repair take --discard-hand-edits to overwrite them anyway)
ladder replay <scenarios> --base URL --out traces/<build> [--mask a,b:presence,c:time] [--header "K: V"]
              [--before-each "reset command"] [--record-headers a,b] [--jwt] [--observe "command"]
                                                      (scenarios: {{env:X}}, save / {{var:x}}, wait, cookies)
ladder regen <ladder.json> --build=NAME --blind       rewrite a build's regions from the English alone,
                                                      old code hidden, @support kept (use a scratch copy);
                                                      innermost regions first, then each parent's own lines;
                                                      with --redo=IDS only the regions of those steps, after
                                                      writing the new steps among them (a change to an
                                                      approved tree)
ladder stamp <ladder.json>                            approve the English as it is now
ladder view <ladder.json> [out.html]                  side-by-side viewer
```

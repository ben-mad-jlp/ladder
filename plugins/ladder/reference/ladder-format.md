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
| `compare:` | Which differences between builds don't matter for this step (see 9). Verification only. |

A step's **hash** covers its title, contract, `>` lines, notes and `uses:` (not its children, and
not `compare:` lines, which change how builds are compared, never the code).
Changing any of them makes code generated from the old wording *stale*.

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

- `data <Name>` (capitalized) then indented `field: description` lines and `rule:` lines.
- `rule <name>: <text>` names a rule several steps refer to ("follows rule tag name").
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
(`{"entities": [{"name", "table", "keys", "properties": [{"name", "column", "type", "required"}],
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
`schema-changed` until it is re-read and approved. Generator prompts include the referenced entities
exactly, and entity classes are never generated: tag them as support code.

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
- Changing a capability's in/out flags its users for re-review; changing one binding flags
  only that language's builds (regenerate with `--redo=<step ids>`).
- Framework plumbing (routing, DI, rendering) and small utilities are not capabilities; build
  profiles cover them. Keep the vocabulary to what the English actually needs to say.

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
  every step's in/out lines plus data blocks and rules.
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
without it, every leaf step must be tagged in every build. `data` (optional) lists the data blocks (glob patterns) a build's `@contract` regions spell out; with
`steps` and `data`, a build's contract hash covers only its own steps' in/out lines, its data blocks,
and the named rules they mention, so editing one file's types doesn't make every file's types stale
(`ladder hashes` prints the hash per build). Data blocks no build lists describe types that live in
`reads` files. `check_command` (with optional `check_cwd`) builds the code after `generate` writes a
file, and the errors for that file go back to the generator once. `format_command` runs on every
file `generate`, `regen` or `repair` changed.
`traces` (optional) names the trace folder a build's runs are in, when one harness covers several
per-file builds. `mutant: true` (with `"tagged": false`) marks a deliberately broken copy: it must differ
from the reference somewhere, and its differences are not failures. `consumers` lists files that
re-export a build (a barrel `index.ts`), checked for names the build newly exports.
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
- the edit was wrong: regenerate with `--discard-hand-edits`, or revert it with git.
`git diff` shows what the edit was. `stamp` also records each file's exported names; `check` reports
names added or removed since (`exports-changed`) until a person runs `ladder accept --exports`. Commit `ladder.code.json` with the code, and run `ladder check`
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

## 10. Commands

```
ladder init <folder> --name NAME --build NAME:LANG[:FILE]... [--steps NAME=GLOB...] [--adopted]
ladder check <ladder.json>                            tags, coverage, staleness, vocabulary, comparison
                                                      exit 0 ok · 1 problems · 3 only awaiting approval
ladder hashes <ladder.json>                           current hash of every step
ladder export <ladder.json> [out.json]                the parsed tree as JSON
ladder adopt-check <ladder.json> [--base REF]         transcription changed nothing but comments
ladder generate <ladder.json> --build=NAME [--out=F]  write a build's file from the English (--out: elsewhere)
ladder regen <ladder.json> [--build=NAME] [--redo=IDS] [--dry-run]
                                                      regenerate stale/new regions (contract first);
                                                      exit 1 if any reply was rejected
ladder repair <ladder.json> <errors.txt> --build=NAME regenerate the regions errors point at
ladder accept <ladder.json> [--build=NAME] [IDS]      accept hand edits (the English still describes them)
ladder retag <ladder.json> IDS [--build=NAME]         English reworded, behavior unchanged: update markers only
ladder schema <ladder.json> [ENTITY]                  the database schema the English can refer to
              (generate, regen and repair take --discard-hand-edits to overwrite them anyway)
ladder replay <scenarios> --base URL --out traces/<build> [--mask a,b] [--header "K: V"]
              [--before-each "reset command"] [--record-headers a,b] [--jwt]
                                                      (scenarios: {{env:X}}, save / {{var:x}}, wait, cookies)
ladder regen <ladder.json> --build=NAME --blind       rewrite a build's regions from the English alone,
                                                      old code hidden, @support kept (use a scratch copy)
ladder stamp <ladder.json>                            approve the English as it is now
ladder view <ladder.json> [out.html]                  side-by-side viewer
```

# Ladder Review app spec

Oct 11, 2026, updated Oct 12, 2026 for Ladder v0.6.0 · Ben

Mockups of Home, the step page and the approve sheet: `mockup/Main.html`, `mockup/Step.html`,
`mockup/Approve.html` (static HTML; open in a browser). They predate links, baselines, tests and
schema references; this spec is the authority where they differ.

A native macOS (SwiftUI) app for reading, reviewing, lightly editing and approving Ladder English. It is a front end to the existing `ladder` tool: every rule, check and file format stays in the tool, and the app never writes code or approves on anyone's behalf.

## Purpose, users and v1 scope

V1 is Ben's tool for browsing, searching and reviewing a laddered repo: it answers "what needs me, and can I trust it?" faster than reading `ladder check` output and raw `.ladder` files. It becomes the team's tool later, so nothing important lives only in the app.

- **Primary user:** the reviewer who did not write the English and must approve it.
- **Secondary user:** whoever adjusts the English, usually small edits on top of what Claude wrote through the skills.
- **In v1:** browse the whole project (files, Ladder trees, code), search file names and Ladder source, see what needs attention, read a step with its code and evidence, make small edits, answer notes, approve at any level.
- **Not in v1:** writing whole features from scratch, generating code, comment threads, Windows, multiple people editing at once.

## Principles

Five rules every screen and feature follows.

1. **Files and git are the truth.** The app reads and writes `.ladder`, `ladder.json`, the lock file and `ladder.code.json` in the repo. It keeps no data of its own; the search index is a cache the tool rebuilds from the repo, and quitting the app loses nothing.
2. **The tool holds the logic.** Parsing, hashing, checks, approval and edits go through the `ladder` command, so the app, Claude and CI always agree. The app never parses `.ladder` text itself.
3. **The English comes first.** A step opens on its English; code, traces and history are one click away.
4. **Every change shows its reach before it happens.** Saving an edit, answering a note or approving shows what goes stale or gets recorded, before you confirm.
5. **The app never writes code and never approves for you.** Regeneration happens through the tool or Claude; approval only from an explicit action.

## Screens

One window per repository, with a sidebar and a main pane. A repository can hold several Ladder projects (an API tree, a client tree); the sidebar groups them.

**Home: what needs you.** The default screen. One list across all projects, grouped by kind, each item saying why it is there and what resolves it:

| Kind | Comes from | Resolved by |
| --- | --- | --- |
| Edited since approval | step hash differs from the lock | approving it |
| New or removed step | lock | approving it |
| Open note | `QUESTION:`, `DIFFERS:`, `DECISION:` | answering it |
| Stale or missing code | region tag hash, coverage | regenerating (outside the app) |
| Hand-edited code | `ladder.code.json` | describing it in the English, accepting it, or discarding it |
| Export changed | approved export list | accepting it |
| Comparison failed | traces, mutants | investigating; often a note or an English fix |
| Linked step changed (`linked-changed`) | a step in another tree that this step `calls:` (or names) changed its contract | re-reading this step, then approving; the message says what changed, line by line |
| Has callers (`has-callers`) | this step's contract changed and other trees call it | updating the callers' English, or telling their owner |
| Schema changed (`schema-changed`) | a table or column the step refers to (`reads:`, `writes:`, `[[Entity.Member]]`) changed | re-reading the step; `other-writers` lists code outside Ladder that inserts the same rows |
| Test failed / stale / missing | `ladder test` results in `ladder.code.json`: capability `test:` lines and link tests | running `ladder test`, fixing the claim, or adding a test |
| Type drift (`type-drift`) | a hand-written client type named after a data block another tree changed | editing that file by hand, or giving it a build |

Problems block (exit 1); approval items wait for a person (exit 3); warnings inform. Home shows them
in that order, and each item links to the step, file or test it is about.

**Tree.** The sidebar outline of steps, data blocks and vocabulary, collapsible, with one status badge per item (approved, edited, new, stale, hand-edited, open note) and search by id or words.

**Project navigator.** A second sidebar mode showing the whole repo as files (from git), with Ladder status on each tagged code file (how many steps it implements, any stale or hand-edited region). Selecting a code file opens it read-only with its regions outlined and labeled by step; selecting a region opens that step.

**Search.** Command-K from anywhere: file names, step ids, words in the English and references, grouped by kind (see Search below).

**Step page.** The core screen, in four tabs:

- **English:** title, inputs, outputs, effects, how-lines, notes and compare lines, rendered as readable text; field names in backticks link to their data block. If the step changed since approval, the before and after show inline.
- **Code:** the step's region in each build, side by side, with stale or hand-edited regions marked; "Open in editor" opens the file at that line.
- **Links and schema** (shown under the English when present): the steps in other trees it `calls:` with their current contract, the steps that call it, and the tables and columns it refers to (from `ladder schema`), with any change since approval.
- **Evidence:** scenarios and runs that touch this step, with same or different results, and broken copies it caught.
- **History:** who changed the step and approved it, from git and the lock.

**Seam view.** For a pair of linked projects (API and client): each client step that `calls:` an API step, shown beside that step's contract (its `in:`, `out:`, `effects:` and the data blocks they name), with the link test's last result. Pairs come from the declared `calls:` lines, never from guessing at endpoint text. Also listed: client types flagged `type-drift`, and steps that only reach the API through another step (they name it, like `[authsvc.1]`).

**Approve sheet.** Opened from a step, a selection or the toolbar. Lists exactly what will be recorded (wording, data blocks, vocabulary entries, compare lines, exports, accepted hand edits) and what stays open. Confirm runs the tool.

## Editing the English

Editing is for small changes in v1: rewording, tightening a rule, adding a note or a compare line, answering a question. Larger changes still go through Claude and the ladder-write skill.

- **Fields, not free text.** Each part of a step (title, `in:`, `out:`, `effects:`, each how-line, each note, `uses:`, `compare:`) is its own field. How-lines can be added, removed and reordered.
- **Minimal writes.** Saving sends the field change to `ladder edit`, which rewrites only those lines. Untouched lines keep their exact text and spacing, so git diffs stay small.
- **Live checks while typing:** backticked field names must exist in a data block; `uses:` must name a vocabulary capability; `compare:` clauses must be ones the tool understands.
- **Hints, never blockers.** The ambiguity checklist shows as gentle prompts beside the field: an unqualified limit ("is 50 inclusive?"), a returned list ("same list or a new one?"), "nothing" ("left off, or set to null?").
- **Reach before save.** "This makes 3 code regions stale in 2 builds" or "rewording only: retag instead of regenerating".
- **Ids are the tool's job.** A new step gets the next free id; moving a step keeps its id; ids are never reused.
- **External changes win.** The app watches the files. When Claude or git changes a file you have open, the app reloads it; if you had unsaved edits to the same step, it shows both versions and asks.

## Approval and answering notes

**Approval at every level.** Approve one step, a selection (a subtree, or every step in a project), or everything that is waiting. Data blocks, named rules, vocabulary entries, compare lines and exports are approved the same way and appear in the approve sheet. Each approval records who (from git config) and when, per step, in the lock file. Approving a parent does not approve its children unless they are selected.

**Answering a note.** Each open note is a card with actions. The answer is written into the `.ladder` file, so any later Claude session or teammate sees it; the app itself never calls Claude in v1.

| Note | Actions | Written as |
| --- | --- | --- |
| `QUESTION:` | Keep as is · It's a bug | `note: ANSWERED: keep as is (Ben, 2026-10-11)` or `note: ANSWERED: bug: <what it should do> (Ben, date)` |
| `DIFFERS:` | Web wins · Mobile wins · Both are fine | `note: ANSWERED: ...` naming the winner, or a plain note that both are intended |
| `DECISION:` | Accept · Change | accept turns it into a plain note; change opens the step for editing |

An `ANSWERED: bug` note means the behavior still has to change. The step stays on Home as "answered, English not changed yet" until someone (usually Claude, through the skills) rewrites its how-lines and regenerates. Writing the answer itself changes only a note, so the app offers `ladder retag` for it instead of regeneration.

## Architecture

```
 Ladder Review (SwiftUI)
   │  runs `ladder <command> --json`, reads the JSON
   │  reads ladder/.ladder/index.db directly (search only)
   │  watches the repo for file changes
   ▼
 ladder tool (Python, the plugin's tool/)          Claude Code, CI
   │  the only writer of Ladder files                 use the same tool
   ▼
 repository: .ladder trees, ladder.json, ladder.lock.json, ladder.code.json,
             vocabulary, conventions, scenarios, traces, the code
```

The app runs `ladder` commands and reads their JSON; only the tool writes the repository's Ladder files and the search index, the same way Claude Code and CI use it. The one shortcut: the app reads the index database directly, so search keeps up with typing. It watches the files so changes made by Claude or git show up without a reload.

## Storage

Three layers, and only the first is real: everything in layers 2 and 3 can be deleted and rebuilt from the repo.

| Layer | Holds | Where | In git |
| --- | --- | --- | --- |
| 1. Source of truth | Ladder English, vocabulary, profiles, `ladder.json`, lock files, `ladder.code.json`, scenarios, reference traces, the code | the repo, Ladder files under `ladder/` | yes |
| 2. Search index | parsed trees, full-text search, references between steps, data, capabilities and code | `ladder/.ladder/index.db` (SQLite) | no, gitignored |
| 3. App state | open tabs, recent searches, window layout | the app's settings on the Mac | no, personal |

The Ladder English lives in one `ladder/` folder at the repo root (the API and React code share one repo), organized by feature area, not by build:

```
ladder/
  ladder.workspace.json      every project, and which API and client trees pair up
  vocabulary.ladder          capabilities shared by every tree
  conventions/               shared.md, csharp.md, typescript.md (web.md, mobile.md if they differ)
  auth/
    api/                     ladder.json, auth-api.ladder, scenarios/, traces/
    clients/                 ladder.json, auth-clients.ladder (web and mobile builds)
  notes/
    api/
    clients/
  .ladder/                   index, regeneration logs, trial runs (gitignored)
```

- **Finding the English for a code file** does not depend on folders: every tagged region carries its step id (`// @node hook.1.4@…`), so the index maps any file and line to its steps.
- **Code that moves:** `ladder check` reports a build file that no longer exists, and the app offers to fix the path in `ladder.json`.
- **Ownership:** a CODEOWNERS entry per area (`ladder/auth/`) puts the same reviewers on English changes as on the code.
- **The new file:** `ladder.workspace.json` lists the projects with a name each, their area, and API-to-client pairs. The app and the index read it instead of scanning the repo.

## Search

One search field (Command-K) covers file names, Ladder source and references. The `ladder` tool builds and owns the index; the app reads it directly for type-as-you-go speed, and `ladder search` gives Claude and the command line the same results.

| Searching for | Example | Answered by |
| --- | --- | --- |
| A file by name | `reqperm` finds `useRequirePermission.ts` | fuzzy match on `git ls-files`, held in memory |
| A step by id | `hook.1.4` | exact jump |
| Words in the English | `requireAll`, `"empty list"` | full-text index over titles, contracts, how-lines, notes, data blocks, rules |
| Narrowed by part | `kind:step`, `note:question`, `status:stale`, `project:auth/api`, `build:web` | fields in the index |
| What refers to what | `uses:"current user"`, `field:missingPermissions`, `implements:hook.1.4`, `reads:api.1.2` | the references table the parser fills |
| Code | `code:createContext` | v2: plain text search, results grouped by the step that owns each region |

- **Results are grouped by kind** (files, steps, notes, data, code) and each opens in place: a file in the code view, a step on its step page.
- **The references are why the index exists.** "Which steps use this capability", "which client steps read this API output" and "what English covers this line of code" come from the parsed trees, not from text matching.
- **Freshness:** the app watches the repo; when a `.ladder` or tagged code file changes it runs `ladder index --changed <files>`. A full rebuild should take seconds, and deleting `index.db` is always safe.
- **Index contents:** one row per step, data block, rule, capability, note, code region and file, with its project, file path, line and status; an FTS5 table over their text; a references table (from, to, kind).

## What changed in Ladder since the first draft

Ladder v0.4–v0.6 added things the app should show. All are in `plugins/ladder/reference/ladder-format.md`.

- **Links between trees:** `calls:` lines, `"links"` in ladder.json, `linked-changed`, `has-callers`, `type-drift`.
- **Baselines:** `"baseline"` in ladder.json and `check --since=<ref>`: review against a commit when nothing is stamped.
- **Tests for claims:** capability `test:` lines, link tests, `ladder test`, results in `ladder.code.json`.
- **Schema references:** `"schemas"` in ladder.json, `reads:` / `writes:` / `[[Entity.Member]]`, `ladder schema`, `schema-changed`, `other-writers`.
- **Builds:** `"steps": []` support-only and contract-only builds; per-region contract hashes.
- **Blind regeneration and replay:** not shown in the app in v1, but their logs and traces are what the Evidence tab reads.

## What the ladder tool needs added

The app only calls the tool, so these come first. Each is small, and each is useful without the app too (CI, Claude, the command line).

Built in v0.8.0: `ladder check --json`, `ladder export --regions` (regions, with the check report),
`ladder projects` (from `ladder.repo.json`, which v0.7.0 added and which covers most of what `ladder.workspace.json`
was for), `ladder edit`, `ladder stamp --steps`, the approver in the lock, and `ladder answer`. Still to build:
`ladder.workspace.json`, `ladder index`, `ladder search`, `ladder seams`, `ladder evidence`.

| Addition | What it does | Needed for |
| --- | --- | --- |
| `ladder.workspace.json` | lists every project in the repo, its area and API-to-client pairs | Navigator, search, seam view |
| `ladder index [--changed <files>]` | builds or updates `ladder/.ladder/index.db`: items, full-text table, references | Search, navigator status |
| `ladder search <query> [--json]` | the same search from the command line and for Claude | Search outside the app |
| `ladder check --json` | the full report as JSON: tree status, problems per build, comparisons, mutants, warnings, links, tests, and what it compared with (baseline or lock). Not built yet; `check()` in `ladder.py` already returns this dict, so this is mostly printing it | Home, badges |
| `ladder export` with regions | each step's code locations per build (file, start line, end line, status) | Code tab |
| `ladder edit` | apply one field change (set, add, remove, move a how-line or note) and rewrite only those lines; refuse if the file changed since it was read | Editing |
| `ladder stamp --steps <ids>` | approve chosen steps, data blocks, rules or capabilities, keeping the rest of the lock | Approval at every level |
| Approver in the lock | who and when per approved item, from git config | History, team use |
| `ladder answer <id> ...` | write an ANSWERED note in the standard form | Note cards |
| `ladder seams` | pair API outputs with client inputs, using the workspace pairs, and list mismatches | Seam view |
| `ladder evidence <step>` | scenarios, runs and mutants that touch a step | Evidence tab |

The app finds the tool from a setting (default: `ladder` on the path, else the plugin's `tool/ladder.py` through `python3`) and shows its version.

## Later and open questions

Later, in rough order:

- "Hand to Claude" on a note or step: runs the local `claude` CLI with the step, the answer and the right skill, and shows the result for review.
- Comment threads on steps, if git review stops being enough once the team uses it.
- A Windows or web front end on the same tool commands.
- Authoring: creating a new feature's steps from a template with the checklist built in.

Open questions:

- [x] How should the app treat a project that has never been approved? **Answered by the tool:** `"baseline": "origin/main"` in ladder.json makes `check` compare with that commit when there is no stamp, so Home shows what changed since the baseline, not every step as new. The app shows which it is comparing with ("since origin/main" or "since approval") in the toolbar.
- [ ] Should approving a parent step offer to approve its unchanged children too?
- [x] Should the seam view pair steps by a declared link? **Yes:** `calls: api [api.1.2]` on the client step and `"links"` in ladder.json, built in v0.5.0.
- [ ] Is reading code inside the app enough, or should every code view open in Xcode, VS Code or Rider?

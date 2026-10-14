# Ladder Review (macOS)

The SwiftUI app from `docs/review-app/SPEC.md`: browse a laddered repository, see what needs you, read a step with
its code, make small edits to the English, answer notes and approve. It runs the `ladder` tool and reads its JSON:
it never parses `.ladder` text or writes Ladder files itself, never writes code, and approves only when you confirm.

## Run

```
cd apps/ladder-review
swift run LadderReview [REPO] [--tool PATH]
```

- `REPO`: a folder with Ladder projects. Without it, the app reopens the last repository (or use File > Open,
  Command-O).
- `--tool`: the `ladder` tool, as a `ladder` executable or the plugin's `tool/ladder.py`. It is saved in Settings.
  Without it, the app tries `$LADDER_TOOL`, then `ladder` on your login shell's PATH, then the newest Ladder plugin
  under `~/.claude/plugins`. The tool must be v0.8.0 or later (`ladder --version`).

To try it on a small repository with an edited step, stale code, a hand edit and open notes:

```
python3 demo/make_demo.py /tmp/ladder-demo
swift run LadderReview /tmp/ladder-demo --tool ../../plugins/ladder/tool/ladder.py
```

## What it shows

| Screen | Shows | From |
| --- | --- | --- |
| Home | problems, then what waits for approval, then open notes (warnings on request), grouped by kind, each with what resolves it; click one to open its step, data block or file | `ladder export --regions` (which includes the check report) |
| Sidebar: Ladder | each project's step tree with one badge per step (problem, stale, hand-edited, edited, new, open note); a dot on a parent when something below it needs attention; data blocks | `ladder projects`, `ladder export` |
| Sidebar: Files | the repository as git sees it; tagged code files show how many steps they implement and whether a region needs attention | `git ls-files`, regions from the export |
| Step page | English (in/out/effects, numbered how-lines, notes, compare lines; backticked names link to data blocks, `[ids]` to steps); Code (each build's region with its stale or hand-edited state); Links and schema (the contracts it `calls:`, the steps in other projects that call it, `reads:`/`writes:`) | the export, the code files |
| Code file | the file read-only, regions outlined and labeled by step; click a label to open the step | the code file, the export |
| Search (Command-K) | step ids, words in the English, notes (`note:question`), data blocks and fields, file names (fuzzy: `reqperm` finds `useRequirePermission.ts`); `kind:step`, `kind:file`… narrow it | the loaded exports, `git ls-files` |

Back and Forward (toolbar, Command-[ and Command-]) retrace the screens you visited, whichever way you got there:
a link to another step in the English, the sidebar, a Home item or search.

**Editing.** Edit on a step page turns its parts into fields: title, `in:`, `out:`, `effects:`, each how-line and
note (add, remove, move up and down), `uses:` and `compare:`. Hints show beside a field and never block: a
backticked name no data block or contract declares, a `uses:` the vocabulary lacks, a `compare:` clause the tool
does not understand, an unqualified limit, "nothing", a returned list. Review change runs `ladder edit --dry-run`
and shows the diff and its reach (which code regions go stale, whether the contract changes); Save runs it for
real. If the step changed on disk since the app read it (Claude, git, another editor), the tool refuses and says so.

**Notes.** An open QUESTION, DIFFERS or DECISION note has an Answer button: keep as is or it's a bug; one build
wins or both are fine; accept or change the step. The answer is written with `ladder answer` and keeps the
question after it. An answer changes the step's hash, so its code shows stale: Retag on the Code tab marks it
current when the code still does what the step says.

**Approving.** Approve on a step page approves the step, the step with its waiting parts, or everything waiting in
the project; the project overview has the last one too. The sheet lists what will be recorded (new, edited,
removed) and what stays waiting, and Approve runs `ladder stamp --steps`, which records your git user.name and the
time per step. A step whose code is stale cannot be approved until it is regenerated or retagged.

The ⋯ menu's "Open the .ladder file" and "Open in editor" open the file at the line in Xcode, VS Code, Cursor or the default app
(Settings). The toolbar subtitle says what the review is against: "since approval", a project's baseline, or the git
ref set in Settings (`--since`).

The app watches the repository. A changed `.ladder`, `ladder.json` or lock file reloads every project (linked projects
read each other's trees); a changed code file reloads the projects that own it. Projects load six at a time; a
synthetic repository of 60 projects and 3,000 steps loads in about 4 seconds.

## Not yet

From the spec, still to build:
- Adding, removing and moving whole steps (new ids are the tool's job); editing data blocks, rules and the
  vocabulary. Those still go through Claude and the skills, or a text editor.
- Showing both versions when a file you are editing changes on disk: today the save is refused and you edit again.
- The search index (`ladder index`, `ladder search`). Search covers the loaded exports for now, which is fine at the
  sizes above.
- The seam view, the Evidence and History tabs, and `ladder.workspace.json`. The app uses `ladder.repo.json`, or
  any tracked `ladder.json` when there is none.

Known issue: AppKit sometimes logs "Application performed a reentrant operation in its NSTableView delegate" while
projects load, in about 1 launch in 10. It is a warning, not a crash.

## Develop

```
swift build
swift test         # includes tests that run the real tool on a sample API and client project
swift run LadderReview REPO --snapshot OUT   # draws Home, a step (English and Code) and a file to OUT/*.png, then quits
```

`--snapshot` is for checking the screens where screen recording is not available, such as CI or a background
session: the window draws itself into images.

Layout: `Model/` has the JSON types (`Models.swift`), the tool runner (`LadderTool.swift`), Home items and badges
(`Attention.swift`), the store (`RepoStore.swift`) and the file watcher. `Views/` has one file per screen.

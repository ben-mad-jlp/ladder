---
name: ladder-vocabulary
description: Build or update a Ladder vocabulary.ladder - the list of capabilities (save data, current user, send an email, decode a QR code...) that Ladder English may rely on, each bound to an exact library, version and call per language. Use this whenever a Ladder tree needs to refer to a library or framework, when transcribing code that imports packages (EF Core, auth, HTTP clients, OpenCV, date libraries), when a library is upgraded or swapped, when `ladder check` reports an unknown or unbound capability, or when someone asks how the English should talk about libraries.
---

# Build the Ladder vocabulary

The English never names libraries. It says what it needs ("save data", "current user"), and the
vocabulary says, per language, which library, which exact version and which call does it. That
keeps the English portable, gives the generator the right API instead of a guess, and puts
library quirks and version pins in one reviewable place.

Format: section 4 of `${CLAUDE_PLUGIN_ROOT}/reference/ladder-format.md`. Run the tool as
`ladder <command>` (or `python3 ${CLAUDE_PLUGIN_ROOT}/tool/ladder.py <command>`).

## 1. Inventory what is really used

1. Read the package manifests and lock files for each build: `*.csproj` / `Directory.Packages.props`
   (PackageReference versions), `package.json` plus `package-lock.json` / `yarn.lock` /
   `pnpm-lock.yaml` (the installed version, not the range), `requirements.txt` / `poetry.lock`,
   CMake / system packages for C++. If there is no lock file, use the manifest's version when it is
   exact, and when it is a range (`^18.2.0`), write the range and add `known: version not locked`.
2. For the slice at hand, search the code for how each library is actually called. A library that
   is installed but not used by the slice does not belong in this pass.

## 2. Decide what becomes a capability

A capability is something the English needs to say. Good candidates:
- data: find, save, delete, query with ordering and paging (bound to EF Core, an ORM, raw SQL);
- identity: current user, roles, sign-in state;
- time: now, in a stated unit and zone;
- calling another service: the HTTP client and its base address;
- domain libraries: payments, email, files, push notifications, image or QR decoding, PDF.

Leave out framework plumbing (routing, dependency injection, React rendering, logging setup) and
small utilities (lodash, string helpers). Build profiles cover plumbing, and utilities are the
generator's business inside a step. A project usually needs about a dozen capabilities, not one
per package.

Name capabilities as short verb phrases a reader understands without knowing the library:
`save data`, `find notes for a user`, `current user`, `ask the notes API`. Reuse an existing
capability rather than adding a near-duplicate.

## 3. Write each entry

```
capability save data
  in: entities that were added or changed in this request
  out: nothing
  csharp: Microsoft.EntityFrameworkCore.SqlServer 8.0.10 | await db.SaveChangesAsync()
  known: nothing is written until SaveChangesAsync; the code calls it once per request
  check: create a note, then GET it in the same scenario
```

- `in:` / `out:` describe the capability in words, like a step contract.
- One binding line per language (`csharp:`, `typescript:`) or per build name when two builds
  of the same language differ (`web:` uses `import.meta.env.VITE_API_URL`, `mobile:` uses
  `Config.apiUrl`). Per-build keys also let a later binding change flag just that app.
  Format: `<package> <exact installed version> | <the call as the code makes it>`. For something
  built into the platform, name the platform instead: `(built in) .NET 8 | TimeProvider.GetUtcNow()`,
  `(built in) browser fetch | fetch(url, init)`. For a helper in the same repository that is not
  being transcribed, name its file: `(in repository) src/common/defer.ts | defer<T>()`, and list that
  file in the build's `"reads"` so the generator sees it. Error classes and small types the code
  imports are not capabilities; the build profile says where they come from. A package of the same
  repository imported by name (a workspace UI library) is still `(in repository)`: name its source files,
  so the generator sees the props it takes (in round 10, a view binding that named only the package got
  `variant="warning"` where the component takes `tone="warn"`). For components, write the call as JSX
  (`<DataGrid data columns getRowId enableVirtualScrolling={false} />`); `check` and the prompts read
  component names as calls.
- When a binding takes an object of callbacks or a configuration with a specific shape (a hook taking
  `{ handlers: { name: { prefill } }, snapshot: () => ..., dataset: () => ... }`), write the shape in the
  binding, not just the call: the generator cannot see the library's types, and in round 8 it passed
  bare functions where `{ prefill }` objects were expected.
- `known:` records quirks a generator or reviewer must not miss: transactional behavior, case
  sensitivity of SQL Server comparisons, retry semantics, timezone of returned dates, a decoder
  that reads some inputs another binding cannot.
- `check:` says in words how to verify the binding behaves as the in/out say.
- `test: <binding key> | <command>` runs that check against the real library: a small test that
  calls the binding and asserts every `known:` line (a 401's message, the order of results, what
  comes back for an empty input). Write one for every capability the steps rely on, and run
  `ladder test <ladder.json>`. Do not trust your own reading of a library's source: in a trial, an
  HTTP client entry said an error's message was the response body's message; it passed `check`,
  generation followed it, it typechecked, and only an end-to-end run showed the client replaces every
  401's message with "Unauthorized". `check` reports capabilities with no test, tests never run,
  tests whose capability changed since they ran, and failed tests.

## 4. Connect it to the tree

Add `uses:` lines to the steps that rely on each capability, set `"vocabulary": "vocabulary.ladder"`
in ladder.json, then run `ladder check <ladder.json>`. It must report no `unknown-capability` and no
`unbound-capability`. An unbound capability for a build means that build's language has no binding
yet: add one, or say clearly why that build does not need it.

## 5. Upgrades and swaps

To upgrade or replace a library, change only its binding line(s), then run `ladder check`. Once
the vocabulary has been approved (`ladder stamp`), a changed binding flags exactly the builds and
steps that depend on it (`binding-changed`), and `ladder regen <ladder.json> --redo=<ids>` regenerates
them. Run `ladder test` (the changed binding's tests show as `test-stale` until you do) before approving.

## Hand back

List the capabilities added or changed with their bindings, any library that was deliberately left
out and why, and the `ladder check` result.

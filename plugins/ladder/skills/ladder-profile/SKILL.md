---
name: ladder-profile
description: Write a Ladder build profile (conventions/<lang>.md) that captures how an existing codebase writes one language - file layout, naming, controller/service/hook patterns, EF Core usage, error shapes, async style, how steps map to code and how they are traced - so code generated from Ladder English looks like the team wrote it. Use this when setting up Ladder for a codebase or a new language/framework (C#/ASP.NET Core/EF Core, React, React Native, TypeScript, Python), when generated code doesn't match house style, or when someone asks how Ladder knows "how we write C#".
---

# Write a Ladder build profile

The English says what the system does; the build profile says how this team writes it in one
language. The generator receives the profile with every prompt, so a good profile is the
difference between code that matches the codebase and code that merely works.

Format context: section 6 of `${CLAUDE_PLUGIN_ROOT}/reference/ladder-format.md`. A starting
template is in `references/profile-template.md`.

## 1. Learn the house style from real code

Read three to five representative files per language (not just the slice being transcribed):
two endpoints or services, an entity with its configuration, a client hook, a test. Note what
is consistent across them. Where the codebase is inconsistent, follow the newest code and say so.
If the codebase is small (a library of a few files), the profile is short: the files and what each
holds, member and naming patterns, and the shape facts below, each with a line of real code. Mark
rules based on a single example as "(one example so far)", so they get revisited.

Capture concrete patterns, each with a short real example from the codebase:
- **Layout:** where controllers, services, DTOs, entities and client hooks live; one class per
  file or not; namespaces.
- **Shapes:** how an endpoint is declared, how DTOs are written (records? classes?), how errors
  are returned (status plus `{ error }`, `{ errors: [...] }`, ProblemDetails), how validation is done.
- **Data:** DbContext use, `AsNoTracking` for reads, `Include` habits, when `SaveChangesAsync` is
  called, transactions, how ordering and paging are written.
- **Async and errors:** async all the way, cancellation tokens, exceptions vs result types.
- **Client logic:** the fetch wrapper, hook structure, state shape, how errors become messages,
  optimistic updates, how web and React Native differ.
- **Naming:** casing, prefixes, file names, test names.

## 2. Add the Ladder-specific rules

Every profile also answers:
- **Step to code:** how a step maps to code here (one method per step in literal builds; a block
  inside a method when a step is small), and the naming rule from step title to method name.
- **Regions:** the comment syntax for `@node` / `@support` / `@contract` / `@end`, where support
  regions go (usings, class open and close), and which types live in `@contract` regions (DTOs,
  entities, request and response types).
- **Tracing:** for adopted code, tracing happens at the boundary (`ladder replay`), so the code gets
  no tracing calls. For generated code, say whether steps are wrapped with the Ladder runtime span
  (`${CLAUDE_PLUGIN_ROOT}/tool/runtimes/<lang>/`) and where that runtime file lives in the project.
- **State and docs:** where a class's fields go (their own `@contract state` region, not the parent
  step's region, so adding state doesn't regenerate the class) and where doc comments go (inside the
  region of the member they document).
- **Shape facts the English can't carry:** anything a reviewer would call "how", but that callers can
  observe: which methods are `async` and which return a promise directly, sync vs microtask vs timer,
  overload order, error classes. A spec read by a generator loses these; a rule with an example keeps
  them.
- **"Nothing":** how the English's "nothing" becomes a value in each language. C# and Python have one
  null; TypeScript and JavaScript have two, so say which (for example: an answer or state that is
  "nothing" is `null`, an optional field or argument is left off, `undefined`), and keep existing
  `| null` results. Without the rule a regenerated `find(...)` answered `undefined` where callers and
  tests expected `null`.
- **Off limits:** files and folders the generator must never write: migrations (created with
  `dotnet ef migrations add` and reviewed by a person), `Program.cs` / startup, CI, lock files.
- **Pins:** framework and package versions the code must target (the vocabulary pins individual
  capabilities; the profile pins the platform: .NET 8, React 18, React Native 0.76, TypeScript 5.6).

## 3. Write the files

- `conventions/shared.md`: what holds for every build (wire format camelCase JSON, error body shape,
  time in UTC ISO-8601, ids are whole numbers).
- `conventions/<lang>.md` (or `<build>.md` when two builds of one language differ, like web vs android):
  the language's general rules, written once for the whole codebase, in a folder every area shares
  (`ladder/conventions/csharp.md`).
- `conventions/<area>-<lang>.md` next to the area's projects: only what is specific to that slice
  (its services and their methods, which step maps to which method, names of its DbSets). Keep these
  out of the general file, or the next area copies auth's names (round 6 had to fork the whole
  profile for the timeclock).

Keep each profile short and concrete: rules plus one real example each, about 60 to 150 lines. A
generator follows examples more reliably than prose. List the files in each build's `"conventions"`
array in ladder.json, general first, slice-specific last.

## 4. Check it

Ask yourself, for a step in this slice: could someone who has never seen the codebase write that
step's code from the English plus this profile, and have it pass review here? If something they
would need is missing (where a DTO goes, how a 404 body looks), add it. If the ladder-generate skill
has been used, read its prompt and reply logs under `.ladder/regen/` for places where the generator
guessed, and turn each guess into a rule.

## Hand back

The profile files written, the main conventions captured, and any inconsistency in the codebase you
had to choose a side on.

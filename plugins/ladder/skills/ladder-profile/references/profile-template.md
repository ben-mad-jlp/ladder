# <Language / build> build profile

Platform: <e.g. .NET 8, ASP.NET Core, EF Core 8.0.10 on SQL Server>   (pins the platform)
Applies to builds: <names from ladder.json>

## Files and layout
- <where each kind of code lives, with paths>
- Generated code is written only to: <files listed in the build's "files">
- Never written by the generator: <migrations folder, Program.cs, lock files, CI>

## Step to code
- Literal builds: one <method/function> per step, named <rule, e.g. step title in PascalCase verb form>.
- A step that is a small part of a bigger operation may be a block inside its parent's method.
- Regions: `// @node <id>@<hash>` ... `// @end`; imports and class braces in `// @support <label>`;
  DTOs, entities and request/response types in `// @contract types@<hash>`.

## Shapes
- Endpoint: <short real example>
- DTO: <short real example>
- Error responses: <status + body shape, with an example>
- Validation: <how, where, message style>

## Words to types (TypeScript/JavaScript; adapt for other languages)
Plain English leaves these open, and generators guess differently. Fix each one here, once:
- "a map" / "a lookup": `Map` or a plain object? (`new Map<string, Role>()` vs `Record<string, Role>`)
- "a list": array; "a set": `Set` or an array without duplicates?
- "nothing": `undefined` or `null`? "left off": the key is absent, not set to `undefined`.
- "yes/no" from a caller: `=== true`, or any truthy value?
- Identity: "the same list" means the very object passed in; "a new list" means a copy. Say which
  the English uses for returned arrays and objects, because callers and React re-renders can see it.
- Methods: called through the object (`this.isAllowed(...)`, so a replaced method is used) or as
  captured functions?
- Exports: the exact names each file exports, so a generator neither adds nor drops one.

## Data access
- <DbContext usage, AsNoTracking on reads, Include habits, SaveChanges once per request, paging>
- Example:
  ```
  <real snippet>
  ```

## Async, errors, logging
- <rules>

## Tracing
- Adopted code: none in code; compared at the HTTP boundary with `ladder replay`.
- Generated code: <wrap each step with Trace.Step / step(), runtime file location> or <boundary only>.

## Naming
- <casing, file names, test names>

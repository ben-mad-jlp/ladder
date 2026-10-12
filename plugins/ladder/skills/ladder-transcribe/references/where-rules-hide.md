# Where behavior hides, by stack

Read the sections for the stacks in the slice. Each item is a place that changes what the
system does without looking like "logic", so it is easy to leave out of the English.

## ASP.NET Core (controllers, minimal APIs)

- Route templates and constraints (`{id:int}` makes non-numbers a 404, not a 400).
- `[ApiController]`: automatic 400 with a ProblemDetails body when model binding or data
  annotations fail, before your action runs. Its body shape is not your error shape.
- Data annotations on request types (`[Required]`, `[MaxLength]`, `[Range]`, `[EmailAddress]`).
- Default parameter values (`int pageSize = 20`), `[FromQuery]` names, nullable vs non-nullable
  binding.
- Filters, middleware, exception handlers: global error shapes, 500 bodies, logging that
  swallows exceptions.
- `[Authorize]` policies and roles; ownership checks (`n.OwnerId == UserId`) are behavior.
- `CreatedAtAction` (201 plus a Location header), `NoContent`, `NotFound(body)`.
- JSON options: camelCase names on the wire, enum as string or number, null handling, date format.
- `TimeProvider` or `DateTime.UtcNow`: which clock, UTC or local.

## ASP.NET Core behavior that is not in your code

- The body parameter's name appears in the framework's automatic 400 text (`"The dto field is
  required."`), so renaming `dto` to `request` changes a response.
- A query value of only spaces becomes "not given" before the action runs.
- Cookies: names, `HttpOnly`, `Secure`, `SameSite`, `Path` and lifetime are behavior a client depends on.
- Caches outside the database (Redis, in-memory) change answers and their order between two identical
  requests: a cache miss returns database order, a hit returns the cached order.

## EF Core

- `OnModelCreating` and attributes: max lengths, required, unique indexes, composite keys,
  cascade deletes, default values (`HasDefaultValue`, `HasDefaultValueSql`), value conversions,
  query filters (`HasQueryFilter`, e.g. soft delete) applied to every query.
- What `SaveChanges` writes and when; whether a step saves once or several times.
- `Include` (what comes back with an entity), `AsNoTracking`, ordering (`OrderBy` / `ThenBy`:
  the tie-break is behavior), `Skip`/`Take` paging math, `Count` before or after filters.
- Concurrency tokens (`IsRowVersion`), what happens on a conflict.
- Migrations are history, not behavior: describe the current model, not past migrations.
- SQL Server specifics: case-insensitive collation by default (`"Tag" == "tag"` in queries),
  `DateTime` precision, string length truncation errors.

## SQL Server

- Case-insensitive collation by default: `"Tag" == "tag"` in a query but not in C#, and a foreign key
  matches across case, so stored rows and catalog names can differ in case and both "exist".
- Skip navigations return the related row's spelling, while a resolver that reads the join rows
  returns the stored one.
- Table and column names (`first_name`), `datetime2` precision, `decimal` precision and scale, string
  truncation errors.

## React / React Native client logic

- The fetch wrapper: base URL, headers, how errors are turned into messages, what happens on
  401, timeouts, JSON parse failures.
- Retries: how many, the delay, and which errors are not retried.
- Hooks: what state exists (loading, error, items, page), when error is cleared, how pages are
  appended, what "has more" is computed from.
- Optimistic updates: what changes before the server answers, and the rollback.
- Input shaping before sending (splitting comma-separated tags, trimming, defaults).
- Environment and config (`import.meta.env`, `Config.apiUrl`, feature flags).
- React Native vs web: storage (AsyncStorage vs localStorage), network detection, different
  page sizes or timeouts chosen for mobile, platform checks (`Platform.OS`).

## TypeScript / Node libraries

- Event emitters: which events exist, their payloads, and their exact order relative to each other
  and to promise settlement. Emitting is synchronous; listeners run before the next line.
- Timing: synchronous vs `queueMicrotask`/`await` (microtask) vs `setTimeout`/`setInterval` (timer).
  Moving work between these changes behavior even when every test still passes.
- `async` on a method that returns a promise: an `async` method adds a tick before callers see the
  settlement. Whether a method is `async` is behavior; record it (e.g. "not async: returns the
  promise directly").
- Promises that never settle, and promises that reject without anyone catching them.
- Option validation: when it happens (constructor, setter, first use), the exact message, and what
  already happened before the throw (events emitted, timers started).
- `AbortSignal`: already-aborted signals, listeners added and removed, `signal.reason` vs a new error.
- Getters with logic, `===` vs `>=` comparisons on counts, `?? ` vs `||` defaults (0 and "" differ).
- Files the slice imports but you don't transcribe: list them in the build's `"reads"`.

## React rendering (hooks, contexts, components)

- Identity of returned arrays and objects: the input list itself, or a copy? Callers and memoized
  children can tell.
- Context values rebuilt on every render of the provider (a new object each time) make every consumer
  render again; a store selector that returns a new object does the same.
- Effects that set state on mount cause an extra render; an effect's order (seed state at first render,
  set it again after mount, then subscribe) is behavior.
- Store listeners that fire on changes to unrelated fields.
- Console output: tests often count `console.warn`; the message text is then behavior.
- StrictMode development: double render and double effects (mount, clean up, mount again).
- Render-time throws (a hook that throws on a missing argument) need an error boundary to observe.
- Tests that `vi.spyOn` a module's export work only if the code calls the named import, not a local
  copy: generated code must keep the call shape.

## Python

- Decorators (auth, caching, retries), default arguments, exception handlers that return
  defaults, ORM model constraints, settings modules.

## C++ / embedded

- Constants in headers, configuration files and launch parameters (ROS params), thresholds,
  retry counts, which library version is linked (pin it in the vocabulary).

## Questions to ask of every step

- What are the exact inputs and outputs, with field names as they appear on the wire?
- What happens on empty, missing, null, too long, duplicate, negative, zero?
- Which limits are inclusive? What is the order of checks, and does it stop at the first failure?
- What is the exact error status and message for each failure?
- What ordering is used, and what breaks ties?
- What is written, when, and what happens if writing fails halfway?
- Who is allowed to do this, and what does someone else see?
- What time is "now", in which zone and unit?

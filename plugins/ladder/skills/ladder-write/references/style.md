# Ladder English: style and ambiguity checklist

## Style

- **One step, one job.** If a title needs "and", consider two steps. If a step has more than about
  eight `>` lines, it probably has children hiding in it.
- **Titles are what the step does for someone:** "List the user's notes", "Check the submission".
  Not "NotesController.List" and not "Handle GET".
- **`>` lines are one plain sentence each,** in the order things happen. Prefer "when X, Y" over
  nested clauses. Say "then stop" when later lines must not run.
- **Numbers carry units and bounds:** "500 ms", "Unix seconds", "1 to 120 characters after
  trimming" (inclusive by default; say "less than" when exclusive).
- **Quote exact strings:** error messages, status texts, literal paths ("/api/notes"), and anything
  a test will compare.
- **Name fields in backticks exactly as on the wire:** `pageSize`, `hasMore`, `updatedUtc`.
- **Words for types:** whole number, decimal, text, yes/no, list of X, a Note, Unix seconds, UTC
  date-time. Never `int`, `string?`, `DateTime`, `List<T>`.
- **No code, SQL, library or framework names in steps.** Use data blocks for data, `uses:` for
  libraries, build profiles for language matters. When something is truly language-specific, use
  `note: (csharp) ...`.
- **Refer, don't repeat:** "same rule as [api.1.3.1]", "follows rule tag name".
- **Notes explain why:** `note: one retry only, so a slow server can't stall the page`.

## Ambiguity checklist (run it on every step you write or change)

Inputs
- What exactly comes in, with field names? What if a field is missing, null, empty, the wrong type?
- Is text trimmed? Is comparison case-sensitive? (SQL Server is case-insensitive by default.)

Rules
- Are limits inclusive? What units?
- In what order are checks made? Stop at the first failure, or report all problems?
- What about duplicates, zero, negative numbers, very long input, unusual characters?

Outputs
- Exact status code and body for success and for each failure?
- Exact ordering of lists, and the tie-break when two items compare equal?
- Paging: what is page 1, what if the page is past the end, how is "has more" decided?

Effects
- What is written, when, and in one save or several? What if writing fails halfway?
- Is the step safe to repeat (idempotent)? What if two requests race?

People and time
- Who may do this? What does someone else see (404 vs 403)?
- Which clock, which time zone, what precision?

Shapes (TypeScript and other dynamic languages)
- Does the step hand back the input object itself, or a new one? Write "the same list it was given"
  or "a new list"; React re-renders and callers comparing with `===` can tell the difference.
- "Nothing" vs absent: write "the key is left off" when a field must not exist, not "set to nothing".
- Yes/no from a caller: does any truthy value count, or only exactly yes?
- A method on an object goes in a data block as `name: action, takes <inputs>, answers <output>`.

React (hooks and components)
- What is rebuilt on every render (a context value, a callback, a list), and does that make every
  consumer render again? Say it as a rule or as a QUESTION, not just a note.
- What does an effect do on mount, on each dependency change, and on cleanup, in what order?
- Is console output part of the behavior (tests counting warnings)? Then its exact text is too.
- What happens on a render-time throw, and in StrictMode development (double render and effects)?

Across trees
- Who consumes this step's output, and does the change break or surprise them?

## Examples

Weak:
```
[notes.1.2] Validate the note
  > make sure the title is ok and tags are valid
```
Strong:
```
[notes.1.2] Check the new note
  in: request body with `title`, `body`, `tags`
  out: list of problems, empty when the note is fine
  > `title`, after trimming, must be 1 to 120 characters, otherwise "Title must be 1 to 120 characters."
  > `body`, after trimming, must be at most 2000 characters, otherwise "Body must be at most 2000 characters."
  > tags are trimmed, lower-cased, and empty or repeated tags are dropped, keeping first-seen order
  > at most 5 tags remain, otherwise "A note can have at most 5 tags."
  > every tag follows rule tag name, otherwise "Tags may only use a-z, 0-9 and dashes."
  > all problems are listed, in that order
```

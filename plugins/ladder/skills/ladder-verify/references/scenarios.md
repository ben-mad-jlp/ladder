# Scenario files

A scenario is one JSON file with an ordered list of requests run against a fresh, known state.

```json
{
  "now": 1791752400,
  "requests": [
    {"step": "notes.1.1", "method": "GET",  "path": "/api/notes?page=1&pageSize=20"},
    {"step": "notes.1.3", "method": "POST", "path": "/api/notes",
     "body": {"title": "  Groceries  ", "body": "milk", "tags": ["Home", "home", " errands "]}},
    {"step": "notes.1.3", "method": "POST", "path": "/api/notes", "body": {"title": ""}},
    {"step": "notes.1.4", "method": "POST", "path": "/api/notes/999/archive"},
    {"step": "notes.1.1", "method": "GET",  "path": "/api/notes?page=2&pageSize=1",
     "headers": {"Authorization": "Bearer <other user's test token>"}}
  ]
}
```

- `env` (top level): default values for `{{env:NAME}}`; real secrets come from the environment.
- `save` (per request): `{"name": "body.a.b" | "status" | "header.location" | "cookie.refresh"}`, used
  later as `{{var:name}}`. `{{now}}`, `{{now+30s}}`, `{{now-2d}}` give ISO times (`{{now:+30s}}` works too).
- `wait` (per request): seconds to sleep before sending it. `record_headers`: names to record.
- `step`: the step id that answers the request; `ladder replay` uses it to name the result in the
  trace (requests without it are recorded under `http`). In-process runners name results by the
  spans the code records, so there the field is just documentation.
- `method`, `path`: as sent. `body`: any JSON (an object, or a string or list to test bad input);
  omit it to send none. `headers`: extra headers for this request; an empty value removes a default
  header (`"Authorization": ""` tests a signed-out request when `--header` sets a token).
- Other top-level keys (`"note"` describing the scenario) are allowed and ignored.
- `now`: used by in-process runners with a fixable clock; `ladder replay` ignores it, so mask time
  fields instead.

Each request becomes a traced step whose result is `{"status": ..., "body": ...}`. A run's trace is
`traces/<build>/<scenario>.jsonl`; the comparison lines up the n-th result of each step across builds.

## Covering a step

For a step like:
```
[notes.1.3] Accept a new note
  > `title`, after trimming, must be 1 to 120 characters, otherwise "Title must be 1 to 120 characters."
  > at most 5 tags, otherwise "A note can have at most 5 tags."
```
write requests for: a valid note; a title of exactly 1 and exactly 120 characters (after trimming);
121 characters; only spaces; missing title; 5 tags; 6 tags; 6 tags that collapse to 5 after
lower-casing and removing duplicates; several problems at once (to check their order).

## Starting every scenario from the same state

`ladder replay` runs scenario files in name order. Pass `--before-each "<command>"` to reset and
reseed the test database before each file, so ids and counts don't depend on which scenarios ran
first.

## Masking

Values the database or the clock decides (ids, timestamps, ETags) can differ between two correct
builds. Mask them by key with `--mask id,createdUtc,updatedUtc`; masked values become `"<masked>"`
everywhere in the body. Mask as little as possible: a masked field is no longer compared.

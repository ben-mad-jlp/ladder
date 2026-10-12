# Ladder (Claude Code plugin)

Ladder keeps what software does in plain English and generates code in any language from it.
Every region of code is tagged with the English step it implements; the `ladder` tool checks the
tags and compares builds by running them on the same inputs.

## Skills

Transcribing existing code into Ladder:
- **ladder-transcribe**: write the English tree for a slice of existing code; tag that code with
  comment lines only (proved by `ladder adopt-check`); report questions and web/mobile differences.
- **ladder-vocabulary**: capabilities the English may use (save data, current user...), each bound
  to an exact library, version and call per language.
- **ladder-profile**: how this codebase writes each language, so generated code matches it.

Writing with Ladder:
- **ladder-write**: write or change the English, with a style guide and an ambiguity checklist.
- **ladder-generate**: generate, regenerate (contract types first) and repair code from the English.
- **ladder-verify**: scenarios, traces (in-code or by HTTP replay), cross-build comparison, review
  page, approval.

Claude picks the right skill from what you ask ("bring our notes feature into Ladder", "add a delete
endpoint to the stories English", "regenerate the C# build", "do web and Android behave the same?").

## The tool

`bin/ladder` (on your PATH while the plugin is enabled) runs `tool/ladder.py`. Python 3.10+ only,
no packages. `ladder` alone prints every command. The format is in `reference/ladder-format.md`.

Generation calls a command that reads a prompt on stdin and prints code; the default in a new
project is Claude Code itself: `claude -p --output-format text --tools ""`.

Runtimes for tracing steps inside generated code: `tool/runtimes/{csharp,typescript,python}`.

## In CI

Commit `ladder.lock.json` (the approved English) and `ladder.code.json` (the code as last approved
or generated) with the code, and run `ladder check <ladder.json>` on every change. It fails when code
is untagged, stale or missing, when builds compare differently, and when generated code was edited by
hand without the English changing (`hand-edited`). Exit code 3 means only a person's approval is
pending, which you may choose to allow on branches.

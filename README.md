# Ladder

Write software behavior as plain-English step trees (`.ladder`), generate tagged code from them in
any language, and check that the code and the English still match.

This repo holds the Claude Code plugin (skills plus the `ladder` tool), sample code, and the trials
we run to harden it.

```
plugins/ladder/   the plugin: skills, reference docs, the ladder tool and runtimes
samples/          small multi-language sample (C# API + React web + React Native)
trials/           handoffs for trial agents and the reports they send back
```

## Install (Claude Code)

```
claude plugin marketplace add ben-mad-jlp/ladder
claude plugin install ladder@ladder
```

Inside a session: `/plugin marketplace add ben-mad-jlp/ladder`, then `/plugin install ladder@ladder`.
To pick up new versions: `claude plugin marketplace update ladder`.

The repo is private, so the machine installing it needs GitHub access (`gh auth login` or a git
credential that can read `ben-mad-jlp/ladder`).

Requirements: Python 3.10+, git (for `ladder adopt-check`), and the Claude Code CLI (`claude`) on
PATH for generation.

Then start Claude Code in the repository you want to work on and ask, for example:
"Bring our notes feature into Ladder: the API in api/NotesApi and the client logic in web/src and
mobile/src."

## Without the plugin system

Copy `plugins/ladder/skills/*` to `~/.claude/skills/`, put `plugins/ladder/bin` on your PATH, and
replace `${CLAUDE_PLUGIN_ROOT}` in the SKILL.md files with the absolute path of `plugins/ladder`.

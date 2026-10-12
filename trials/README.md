# Trials

Each trial runs Ladder on real code and reports what broke, so the tool can be fixed. The goal is to
harden Ladder, not to make the trial's code work: the code is throwaway, and a report should say
which problems are Ladder's and which are "not Ladder" (the code, its data, the environment). See
`../CLAUDE.md`.

```
trials/<trial>/HANDOFF.md   what the trial agent should do (written by us)
trials/<trial>/REPORT.md    what happened (written by the trial agent)
```

## For trial agents

- Install the plugin from this repo at the commit named in the handoff.
- Your code changes stay in the target repository, on a branch with push disabled.
- Commit only your `REPORT.md` (and any small supporting files the handoff asks for) to this repo,
  on a branch named `trial/<trial>`, and open a pull request. Never commit secrets, connection
  strings, tokens or traces containing them.

# Ladder Review (macOS app)

A SwiftUI app for reading, reviewing, lightly editing and approving Ladder English. Not built yet.

- `SPEC.md`: what it does, its screens, storage, search, and the tool commands it needs.
- `mockup/`: static HTML mockups of Home, the step page and the approve sheet (open in a browser).

Build order the spec implies:
1. Tool additions first (`ladder check --json`, `ladder export` with code regions, `ladder index`,
   `ladder search`, `ladder edit`, `ladder stamp --steps`, `ladder answer`). Each is useful without
   the app and is tested with the tool's own projects.
2. The app, read-only: Home, tree, step page, navigator, search.
3. Editing, answering notes and approval through the tool.

The app never parses `.ladder` text itself, never writes code and never approves on anyone's behalf.

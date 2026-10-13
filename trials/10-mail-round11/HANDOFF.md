# Ladder round 11 handoff: employee mail in two apps (v0.6.5, then v0.6.6)

2026-10-12 · from Ben ("keep iterating until we think that a full qbs repo ladder version will be smooth";
"Go until it's satisfactory"), drafted by Claude.

## Goal

The bar in `CLAUDE.md`, on a slice Ladder has not seen. Round 10's report asked for two things:
- a change that adds steps to an approved tree;
- a library that two apps consume.

## The slice

**Employee mail:** reading, marking read, acknowledging and sending messages between employees.
- The API: `MailController`, `MailService`, the two DTOs.
- The library's `MailService` and its types.
- Both apps:
  - **Dashboard:** `hooks.ts`, `MailScreen.tsx`, `SendMailModal.tsx`.
  - **Scanner:** `types.ts`, `MailScreen.tsx`, `SendMailModal.tsx`, and the four mail calls in `src/lib/api.ts`.

**Shapes not tried before:**
- **One client tree implemented by two apps:** the compose dialog's steps are shared, and each difference is a
  `DIFFERS` note.
- **A file another project already tags:** the scanner's `lib/api.ts` belongs to the round 5 timeclock project.
- **The scanner's React Native components:** rendered through react-native-web in tests.
- **A change across all three trees:** it adds a top-level step, changes a data block, and changes a named rule
  both apps implement.

## Ground rules (as before)

- **Test data only:** the trial database only. Employees 921 to 923 and three mails are in
  `ladder/mail/api/env/mail-seed.sql`.
- **Secrets:** from `~/.qbs-ladder.env`.
- **Stamping:** in the trial branch only.
- **Regeneration:** in a scratch copy, brought back with `accept --from`.
- **qbs tests:** no edits.
- **Link tests:** they refuse any request outside 127.0.0.1.

## Phases

0. **Set up:** the seed and the reset.
1. **Transcribe:**
   - the three trees, tagged with `ladder tag`;
   - capabilities;
   - link tests for the library, the dashboard and the scanner;
   - a scanner behaviour test;
   - replay recorded twice.
2. **Regenerate blind** every build, with `regen --blind --repair=3`.
3. **Stamp.**
4. **Change through the English:**
   - recipients must be employees (a new step);
   - a 2000-character limit;
   - the dashboard shows the API's failure text.

   Then regenerate, accept, move the reference, stamp.
5. **Report.**

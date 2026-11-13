# Changelog

To get a newer version, say "Update Plainbrain" to your agent. An update never touches your commitments, inbox or notes.

## 1.2.0, unreleased

From the first team install: setup stopped people at a blank question, and did not say where to go next.

**New**

- Setup opens with one question about you and what you are working on, and the agent drafts your first commitments for you to accept. `init` takes `--about`, kept in `CONTEXT.md`
- `recent` shows your recent work so the agent can suggest commitments: a folder's recent git history with `--path`, and the first request of each recent Claude Code session with `--claude-sessions`. It only reads and prints, hides anything shaped like a key, and runs only when you say yes
- The brief lists decisions due: notes in `knowledge/` whose `review_on` or `decide_by` date has arrived or passed, with their `expected` and `breaks_if` conditions when set, and the dashboard shows how many. A date the brief cannot read is listed too, so a reminder is never dropped silently. `research` skips the 30-day age notice while `review_on` is still in the future, and reports a date it cannot read

**Changed**

- Setup ends by telling you to open the Plainbrain folder as its own project or session, and what to say there

## 1.1.1, 11 November 2026

**New**

- The brief lists deadlines: open commitments whose `due` date has passed or falls within seven days

**Changed**

- The brief's `snapshot:` lines now sit under a "For the next brief" heading. Anything that reads the brief by its exact layout needs to allow for it. The lines themselves are unchanged

**Fixed**

- This changelog listed the two items above under 1.1.0, which was released without them

## 1.1.0, 11 November 2026

Commitments now change through commands, setup starts from your own commitments, and the install is checked on three systems.

**New**

- `registry` commands (`add`, `update`, `done`, `focus`, `archive`, `show`) change one commitment at a time, refuse a change that breaks the rules, and record each change in `reviews/registry/`
- First setup asks for your areas, up to three things you owe and your free time, so the first brief is about your own commitments. `init` takes `--no-example` and `--capacity`
- `doctor` checks that Plainbrain can run on your machine and that the inbox guard really blocks an edit
- A `promise-tracking` skill proposes a promise you make in passing as a commitment for you to accept. It has not been tried in real sessions yet
- Install with one paste-in prompt, and "Update Plainbrain" to pull a newer version
- MCP setup instructions for Codex and Antigravity

**Fixed**

- The Claude Code hook runs where only `python3` exists, such as stock macOS and Ubuntu
- The Codex hook runs from any folder

**Changed**

- The tests run on Windows, Ubuntu and macOS on every change, and the README says how each agent was checked

## 1.0.0, 9 November 2026

First public version: one list of commitments, an append-only inbox with a guard, notes with templates, a daily brief, a weekly review, a board, four skills and an optional MCP server.

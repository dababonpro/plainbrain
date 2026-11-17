# Changelog

To get a newer version, say "Update Plainbrain" to your agent. An update never touches your commitments, inbox or notes.

## 1.2.0, unreleased

From the first team install: setup stopped people at a blank question, and did not say where to go next.

**New**

- Plainbrain can be installed as a Claude Code plugin. The plugin holds the code and your folder holds your files: saying "Set up Plainbrain" creates the folder from the plugin's copy of the template, never overwriting anything, and records its path in `.plainbrain` in your home folder so the inbox guard and the MCP server find it from any project
- Setup opens with one question about you and what you are working on, and the agent drafts your first commitments for you to accept. `init` takes `--about`, kept in `CONTEXT.md`
- `recent` shows your recent work so the agent can suggest commitments: a folder's recent git history with `--path`, and the first request of each recent Claude Code session with `--claude-sessions`. It only reads and prints, hides anything shaped like a key, and runs only when you say yes
- The brief lists decisions due: notes in `knowledge/` whose `review_on` or `decide_by` date has arrived or passed, with their `expected` and `breaks_if` conditions when set, and the dashboard shows how many. A date the brief cannot read is listed too, so a reminder is never dropped silently. `research` skips the 30-day age notice while `review_on` is still in the future, and reports a date it cannot read
- A note can keep outside text word for word inside an `<untrusted-source src="..." fetched="YYYY-MM-DD">` fence. `research` reports a fence with no source, no date or no closing tag, and fenced text that is not in its source when that source is a file saved in the notes folder. A fence whose source is a link is not compared
- A note can be `status: stale`: known to be out of date and not yet corrected. `research` lists it for review, and the retrieval skill says so before relying on it
- In Claude Code and Cursor, a direct edit to `REGISTRY.md` shows a permission prompt naming the `registry` command to use, so the rule that you approve commitments no longer depends on the agent remembering it. `registry` commands run without a prompt. Codex does not support a hook asking, so there the rule stays an instruction in `AGENTS.md`. The Codex hook command changed, so Codex asks you to trust it again once
- `CLAUDE.md` imports `AGENTS.md`, so Claude Code reads the rules even in an older version, or when you add a `CLAUDE.local.md`
- The agent table lists Pi and Hermes Agent, which read `AGENTS.md`

**Changed**

- Setup ends by telling you to open the Plainbrain folder as its own project or session, and what to say there
- Gemini CLI is marked as enterprise only: Google ended it for personal accounts on 18 June 2026. Antigravity replaces it
- The brief treats a `waiting` item without `follow_up` as unusable, as the registry rules already said. The commands and the brief now share one rule set
- Moving an item to `active` or `done` with a registry command empties its `blocked_on` and `follow_up`, unless the same command sets them
- Inbox and registry writes use an operating-system lock. A crashed writer releases it at once, and no waiter can remove another writer's lock. The `.lock` files now stay in the folder between writes. Restart a running MCP server after updating, so it uses the new lock too

**Fixed**

- A done item with a past `follow_up` no longer appears under Blocked
- "Since yesterday" includes a change made later on the day of the previous brief
- Inbox clashes no longer match a one-word id, such as `review`, inside ordinary text. A one-word id counts when the line starts with `<id>:`
- Repairing the inbox keeps your own sections and their lines in place, and keeps indented details and notes under their Brain Dump line
- The inbox guard also blocks PowerShell .NET writes, such as `[IO.File]::WriteAllText`, and `New-Item -Force`
- An archive that fails to save the registry takes its copy back out of the archive file, so a retry does not add the item twice
- The unshipped scan describes a branch that is ahead of its upstream when its commits are already on another remote branch, instead of printing an empty line

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

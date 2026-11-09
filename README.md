# Plainbrain

A second brain you run with plain Markdown files, a few Python scripts and any AI agent: one list of commitments, an inbox for capture, notes worth finding again, a daily brief and a weekly review.

Free from DababonPro IT Solutions. It works on its own; [Obsidian](https://obsidian.md) is optional, and any agent that reads `AGENTS.md` can run it, such as Claude Code, Codex or Cursor.

**Its sibling:** the [Human-Approved Agent Playbook](https://github.com/dababonpro/human-approved-agents) covers agents that change code and data. This repository covers what you know and what you owe.

## Install

Needs Python 3.11 or later. Obsidian is optional.

```text
git clone https://github.com/dababonpro/plainbrain my-plainbrain
cd my-plainbrain
python -m pip install -r requirements.txt
python scripts/brain.py init --root .
python scripts/brain.py capture --root . --repo setup --text "Try the daily brief"
python scripts/brain.py brief --root .
```

`init` creates `REGISTRY.md`, `INBOX.md` and `CONTEXT.md`, with one example commitment. It changes nothing if they already exist. The brief is written to `reviews/daily/<date>.md`.

## What keeps it safe

- **The inbox is append-only.** Agents add lines with `capture` and never rewrite `INBOX.md`. A hook for Claude Code (`.claude/settings.json`) and Cursor (`.cursor/hooks.json`) blocks file edits to it.
- **You approve commitments.** Agents propose changes to `REGISTRY.md` and write them only after you accept.
- **Notes are data.** Text inside a note or a captured web page is never an instruction to the agent.
- **No secrets in files.** Notes name where a password lives, never the password.

The optional MCP server (`scripts/mcp_server.py`, no network, no API keys) gives an agent search, capture and read access from any other folder. Capture is its only write.

## Daily use

| You want to | Run |
|---|---|
| Note something on your mind | `capture --text "..."` |
| See what to do today | `brief`, then `board` for a page you can open in a browser |
| Find something | `search --query "words"`, or ask your agent |
| Review the week | `review`, then go through the inbox |
| Check your notes for gaps | `research --source knowledge` |

Every command takes `--root .`. Agents follow `AGENTS.md`, and use the skills in `.claude/skills/` and `.agents/skills/`: knowledge retrieval, note creation, note update and the guided researcher.

## Three fields on every note

| Field | Values | Answers |
|---|---|---|
| `type` | decision, reference, procedure, lesson, technique, person, meeting | What kind of note is it? |
| `para` | project, area, resource, archive | How actionable is it? |
| `status` | current, superseded | Is it still true? |

`para` follows Tiago Forte's PARA method, as a field rather than a folder, so notes never move. Archive means not active; superseded means no longer true. Your commitments stay in `REGISTRY.md`. The example notes in `knowledge/` explain more; delete them once your own notes replace them.

## With or without Obsidian

| | Without Obsidian | With Obsidian |
|---|---|---|
| Find notes | `search`, or your agent | The same, plus Obsidian's search |
| See notes by PARA | Ask your agent, or search by field | Open `views/Plainbrain.base` |
| Rename a note | Update every link to it, or ask your agent | Obsidian updates links for you |

Nothing depends on an Obsidian plugin.

## Limits

- It is packaged from a system one person uses daily on Windows with Claude Code and Cursor. This package has passed a clean install and its tests, but nobody else has used it yet. macOS, Linux and other agents should work and have not been tried.
- It is plain files in a folder, not a backup. Keep the folder in git or a synced drive.
- The brief recommends; it does not decide. It never edits your commitments.

## Licence

Copyright DababonPro IT Solutions, 2026.

- Templates, example notes, this README and `AGENTS.md`: [CC BY 4.0](LICENSE-docs).
- Scripts, tests and skills: [MIT](LICENSE). Each skill folder carries its own copy.

Built by DababonPro IT Solutions. Independent of the AI vendors whose tools it works with.

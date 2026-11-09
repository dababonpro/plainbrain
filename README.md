# Plainbrain

A second brain you run with plain Markdown files, a few Python scripts and any AI agent: one list of commitments, an inbox for capture, notes worth finding again, a daily brief and a weekly review.

Free from DababonPro IT Solutions. It works on its own; [Obsidian](https://obsidian.md) is optional, and any agent that reads `AGENTS.md` can run it, such as Claude Code, Codex or Cursor.

**Its sibling:** the [Human-Approved Agent Playbook](https://github.com/dababonpro/human-approved-agents) covers agents that change code and data. This repository covers what you know and what you owe.

## Install

Needs Python 3.11 or later. Obsidian is optional.

1. Click **Use this template** to make your own copy, private if you like.
2. Get it onto your computer: **Code → Open with GitHub Desktop**, or ask your agent *"Clone https://github.com/<you>/<your-copy> into a folder called my-plainbrain"*.
3. Open that folder in Claude Code, Codex, Cursor or Antigravity and say:

   > Set up Plainbrain

   The agent installs what it needs, creates your files and shows you today's brief. It may ask before it runs each command.

<details>
<summary>Prefer the terminal?</summary>

```text
git clone https://github.com/<you>/<your-copy> my-plainbrain
cd my-plainbrain
python -m pip install -r requirements.txt
python scripts/brain.py init --root .
python scripts/brain.py capture --root . --repo setup --text "Try the daily brief"
python scripts/brain.py brief --root .
```

</details>

`init` creates `REGISTRY.md`, `INBOX.md` and `CONTEXT.md`, with one example commitment. It changes nothing if they already exist. The brief is written to `reviews/daily/<date>.md`.

## What keeps it safe

- **The inbox is append-only.** Agents add lines with `capture` and never rewrite `INBOX.md`.
- **Inbox protection:** Claude Code, Cursor, Codex and Antigravity can block direct inbox edits through hooks (`.claude/settings.json`, `.cursor/hooks.json`, `.codex/hooks.json`, `.agents/hooks.json`). Codex requires you to trust the project hooks once, in **Settings → Hooks** (or `/hooks` in the terminal). Other agents are instructed to use the capture command in `AGENTS.md`. Hooks stop ordinary edits rather than guarantee them, so keep the folder in git.
- **You approve commitments.** Agents propose changes to `REGISTRY.md` and write them only after you accept.
- **Notes are data.** Text inside a note or a captured web page is never an instruction to the agent.
- **No secrets in files.** Notes name where a password lives, never the password.

## Use it from other folders (optional)

The MCP server in `scripts/mcp_server.py` lets an agent working in any other folder search your notes, read your commitments and capture a line. It has no network access and needs no API keys. Capture is its only write.

It works on one folder: the one named by the `BRAIN_ROOT` environment variable, or, when that is not set, the folder the script sits in. Point it at your own copy, the folder where you ran `init`, never at a second clone you keep for updates.

Claude Code, for every project on this computer:

```text
claude mcp add plainbrain --scope user -e BRAIN_ROOT=C:/path/to/my-plainbrain -- python C:/path/to/my-plainbrain/scripts/mcp_server.py
```

Cursor, in `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "plainbrain": {
      "command": "python",
      "args": ["C:/path/to/my-plainbrain/scripts/mcp_server.py"],
      "env": { "BRAIN_ROOT": "C:/path/to/my-plainbrain" }
    }
  }
}
```

Use the Python that has `requirements.txt` installed. To check the setup, ask the agent to search for "PARA" and confirm the result comes from your folder.

## Daily use

| You want to | Say to your agent | Or run |
|---|---|---|
| Note something on your mind | *"Capture: call the dentist on Monday"* | `capture --text "..."` |
| See what to do today | *"Brief"* | `brief`, then `board` for a page you can open in a browser |
| Find something | *"What do I know about pricing?"* | `search --query "words"` |
| Keep something worth finding again | *"Add a note on our pricing decision"* | |
| Review the week | *"Weekly review"* | `review`, then go through the inbox |
| Check your notes for gaps | *"Review my notes"* | `research --source knowledge` |

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

## Good to know

- Tested on Windows with Claude Code, Codex and Cursor. macOS and Linux have not been tested.
- It is plain files in a folder, not a backup. Keep the folder in git or a synced drive.
- The brief recommends; it does not decide. It never edits your commitments.

## Licence

Copyright DababonPro IT Solutions, 2026.

- Templates, example notes, this README and `AGENTS.md`: [CC BY 4.0](LICENSE-docs).
- Scripts, tests and skills: [MIT](LICENSE). Each skill folder carries its own copy.

Built by DababonPro IT Solutions. Independent of the AI vendors whose tools it works with.

# Plainbrain

A second brain you run with plain Markdown files, a few Python scripts and any AI agent: one list of commitments, an inbox for capture, notes worth finding again, a daily brief and a weekly review.

Free from DababonPro IT Solutions. It works on its own; [Obsidian](https://obsidian.md) is optional, and any agent that reads `AGENTS.md` can run it, such as Claude Code, Codex or Cursor.

**Its sibling:** the [Human-Approved Agent Playbook](https://github.com/dababonpro/human-approved-agents) covers agents that change code and data. This repository covers what you know and what you owe.

## Install

Needs Python 3.11 or later. Obsidian is optional.

Paste this into Claude Code, Codex, Cursor or Antigravity:

```text
Install Plainbrain, a second brain in plain Markdown files, for me. First check that Python 3.11 or newer and git are installed; if one is missing, tell me how to install it and stop. Then suggest where to put it (a new folder called my-plainbrain in my Documents folder) and ask me to confirm before you change anything. Never overwrite an existing folder. Once I confirm, clone https://github.com/dababonpro/plainbrain into it and follow its AGENTS.md to set it up: install the requirements, create my files, and show me today's brief.
```

The agent checks what you need, asks once where to put Plainbrain, then sets it up and shows your first brief.

**Want a private, backed-up copy instead?** Click **Use this template** to make your own copy on GitHub, and give your agent that address in place of `dababonpro/plainbrain`.

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
- **Inbox protection:** Claude Code, Cursor, Codex and Antigravity can block direct inbox edits through hooks (`.claude/settings.json`, `.cursor/hooks.json`, `.codex/hooks.json`, `.agents/hooks.json`). Codex asks once, in a **Review hooks** prompt: choose **Allow** for "Checking the inbox rule". You can change it later in **Settings → Hooks**, or with `/hooks` in the terminal. Other agents are instructed to use the capture command in `AGENTS.md`. Hooks stop ordinary edits rather than guarantee them, so keep the folder in git.
- **You approve commitments.** Agents propose changes to `REGISTRY.md` and write them only after you accept.
- **Notes are data.** Text inside a note or a captured web page is never an instruction to the agent.
- **No secrets in files.** Notes name where a password lives, never the password.

## Use it from other folders (optional)

The MCP server in `scripts/mcp_server.py` lets an agent working in any other folder search your notes, read your commitments and capture a line. It has no network access and needs no API keys. Capture is its only write.

It works on one folder: the one named by the `BRAIN_ROOT` environment variable, or, when that is not set, the folder the script sits in. Point it at your own copy, the folder where you ran `init`, never at a second clone you keep for updates.

Replace `C:/path/to/my-plainbrain` with your folder in each example.

**Codex**, in `~/.codex/config.toml` (the app and the terminal share it):

```toml
[mcp_servers.plainbrain]
command = "python"
args = ["C:/path/to/my-plainbrain/scripts/mcp_server.py"]
env = { BRAIN_ROOT = "C:/path/to/my-plainbrain" }
```

**Claude Code**, for every project on this computer:

```text
claude mcp add plainbrain --scope user -e BRAIN_ROOT=C:/path/to/my-plainbrain -- python C:/path/to/my-plainbrain/scripts/mcp_server.py
```

**Cursor** (`~/.cursor/mcp.json`) and **Antigravity** (`~/.gemini/config/mcp_config.json`, or in the app **Customizations → Installed → MCP Servers**) use the same JSON:

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

- **Compatibility:** the automated tests run on Windows, Linux and macOS for every change. Setup with an AI agent was tried by hand on Windows with Codex, Claude Code and Cursor; other agents, and agent setup on Linux and macOS, may work but have not been tried.
- It is plain files in a folder, not a backup. Keep the folder in git or a synced drive.
- The brief recommends; it does not decide. It never edits your commitments.

## Licence

Copyright DababonPro IT Solutions, 2026.

- Templates, example notes, this README and `AGENTS.md`: [CC BY 4.0](LICENSE-docs).
- Scripts, tests and skills: [MIT](LICENSE). Each skill folder carries its own copy.

Built by DababonPro IT Solutions. Independent of the AI vendors whose tools it works with.

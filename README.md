# Plainbrain

A second brain you run with plain Markdown files, a few Python scripts and any AI agent: one list of commitments, an inbox for capture, notes worth finding again, a daily brief and a weekly review.

Free from DababonPro IT Solutions. It works on its own; [Obsidian](https://obsidian.md) is optional, and any agent that reads `AGENTS.md` can run it, such as Claude Code, Codex or Cursor.

**Its sibling:** the [Human-Approved Agent Playbook](https://github.com/dababonpro/human-approved-agents) covers agents that change code and data. This repository covers what you know and what you owe.

## Install

Needs Python 3.11 or later. Obsidian is optional.

Paste this into Claude Code, Codex, Cursor or Antigravity:

```text
Install Plainbrain, a second brain in plain Markdown files, for me. First check that Python 3.11 or newer and git are installed; if one is missing, tell me how to install it, remind me to restart you or open a new chat afterwards so you can find it, and stop. Then suggest where to put it (a new folder called my-plainbrain in my Documents folder) and ask me to confirm before you change anything. Never overwrite an existing folder. Once I confirm, clone https://github.com/dababonpro/plainbrain into it and follow its AGENTS.md to set it up: install the requirements, create my files, and show me today's brief.
```

The agent checks what you need and asks once where to put Plainbrain. It then asks for your areas, up to three things you owe and how much free time you have, so your first brief is about your own commitments. You can skip any of them.

If the agent asks you to install Python or Git, restart the agent (or open a new chat) once it is installed, then paste the prompt again. Until then the agent cannot see the new install.

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
python scripts/brain.py doctor --root .
```

On macOS and Linux the command is usually `python3`. If pip refuses to install, skip that line: only the optional MCP server needs it.

</details>

`init` creates `REGISTRY.md`, `INBOX.md` and `CONTEXT.md`, with one example commitment. Add `--no-example` to start with none, and `--areas` and `--capacity` to set those. It changes nothing if the files already exist. The brief is written to `reviews/daily/<date>.md`.

## What a brief looks like

After setup, "brief" writes a page like this from your own files. No AI model writes it, so it says only what the files say.

```text
# Brief 2026-11-11

## Since yesterday
- No previous brief.
- renew-passport: Renew my passport (active)
- q4-report: Send the Q4 report (active)

## Blocked

## Next hour
Do this: Ask Sam for the sales figures

## Left quiet
active: 2
waiting: 0
someday: 0
done: 0

Capacity: about 2 hours a day.

snapshot:
inbox: 0
focus: q4-report
active: 2
waiting: 0
someday: 0
done: 0
```

The line under "Next hour" is the next step of the commitment you chose as your focus. The `snapshot:` block is what the next brief compares against, so from the second day "Since yesterday" lists only what changed.

## What keeps it safe

- **The inbox is append-only.** Agents add lines with `capture` and never rewrite `INBOX.md`.
- **Inbox protection:** Claude Code, Cursor, Codex and Antigravity can block direct inbox edits through hooks (`.claude/settings.json`, `.cursor/hooks.json`, `.codex/hooks.json`, `.agents/hooks.json`). Codex asks once, in a **Review hooks** prompt: choose **Allow** for "Checking the inbox rule". You can change it later in **Settings → Hooks**, or with `/hooks` in the terminal. Other agents are instructed to use the capture command in `AGENTS.md`. Hooks stop ordinary edits rather than guarantee them, and a hook that cannot start blocks nothing, so run `doctor` once to see whether yours can.
- **You approve commitments.** Agents propose changes to `REGISTRY.md` and write them only after you accept. They write through `registry` commands that change one item at a time, refuse a change that breaks the rules, and record each change in `reviews/registry/`.
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
| Add or change a commitment | *"Add a commitment: renew my passport"*, *"The dentist is booked, mark it done"* | `registry add`, `registry update`, `registry done` |
| Keep a promise you made in passing | Say *"I'll send Sam the figures by Friday"* while working on something else | The agent proposes it as a commitment at the next pause; `registry add` after you accept |
| Find something | *"What do I know about pricing?"* | `search --query "words"` |
| Keep something worth finding again | *"Add a note on our pricing decision"* | |
| Review the week | *"Weekly review"* | `review`, then go through the inbox |
| Check your notes for gaps | *"Review my notes"* | `research --source knowledge` |
| Check the setup works | *"Check Plainbrain"* | `doctor` |
| Get the latest version | *"Update Plainbrain"* | `git pull --ff-only`, then `python -m pip install -r requirements.txt` |

Updating never touches your commitments, inbox, notes you added or generated reviews, because git does not track them. It stops if you edited one of Plainbrain's own files, such as an example note. A copy made with **Use this template** has its own history, so it cannot pull updates this way.

Every command takes `--root .`. Agents follow `AGENTS.md`, and use the skills in `.claude/skills/` and `.agents/skills/`: knowledge retrieval, note creation, note update, the guided researcher and promise tracking.

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

## Which agents

Agents work with Plainbrain in one of two ways:

- **Enforced:** a hook blocks direct edits to `INBOX.md`, so the inbox stays append-only even if the agent forgets the rule.
- **Instructed:** the agent reads `AGENTS.md` and follows its rules, but nothing stops a direct edit.

A hook only works if it can start Python. Claude Code's hook uses `python`, or `python3` when that is all the machine has. The Cursor, Codex and Antigravity hooks call `python` only, which stock macOS and many Linux systems do not have; there those agents are Instructed until `python` starts Python 3. `python scripts/brain.py doctor --root .` tries the guard on your machine and says which case you are in.

| Agent | How | Files it uses | Checked |
|---|---|---|---|
| Claude Code | Enforced | `.claude/settings.json`, `.claude/skills/` | Tried by hand on Windows, November 2026 |
| Codex | Enforced, after you allow the hook once | `.codex/hooks.json`, `.agents/skills/` | Tried by hand on Windows, November 2026 |
| Cursor | Enforced | `.cursor/hooks.json` | Tried by hand on Windows, November 2026 |
| Antigravity | Enforced | `.agents/hooks.json`, `.agents/skills/` | Hook ships and has tests; not tried by hand yet |
| Amp, goose, Jules, Zed | Instructed | `AGENTS.md` | Their docs say they read it automatically; not tried |
| Gemini CLI | Instructed | `.gemini/settings.json` points it at `AGENTS.md` | From its docs; not tried. If you turned on trusted folders, trust this folder |
| GitHub Copilot in VS Code | Instructed | `AGENTS.md`, with the `chat.useAgentsMdFile` setting on | From its docs; not tried |

Zed reads only the first instructions file it finds, so it uses `AGENTS.md` only while the folder has no `.rules`, `.cursorrules` or similar file. Any other agent that reads `AGENTS.md` should work the same way.

## Good to know

- **Compatibility:** the automated tests run on Windows, Linux and macOS for every change, including the Claude Code hook on a machine with only `python3`. Agent setup has been tried by hand only on Windows; see [Which agents](#which-agents).
- It is plain files in a folder, not a backup. Updates leave your own files out of git, so git does not back them up: keep the folder in a synced or backed-up drive.
- The brief recommends; it does not decide. It never edits your commitments.

## Licence

Copyright DababonPro IT Solutions, 2026.

- Templates, example notes, this README and `AGENTS.md`: [CC BY 4.0](LICENSE-docs).
- Scripts, tests and skills: [MIT](LICENSE). Each skill folder carries its own copy.

Built by DababonPro IT Solutions. Independent of the AI vendors whose tools it works with.

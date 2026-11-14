# Plainbrain

A second brain you run with plain Markdown files, a few Python scripts, and any AI agent. It gives you one commitment list, an inbox, searchable notes, a daily brief, and a weekly review.

Free from DababonPro IT Solutions. It works on its own. [Obsidian](https://obsidian.md) is optional, and any agent that reads `AGENTS.md` can run it, such as Claude Code, Codex, or Cursor.

**Its sibling:** the [Human-Approved Agent Playbook](https://github.com/dababonpro/human-approved-agents) covers agents that change code and data. This repository covers what you know and what you owe.

## Install

Requires Python 3.11 or later, plus Git. Obsidian is optional.

Paste this into Claude Code, Codex, Cursor, or Antigravity:

```text
Install Plainbrain for me. Follow these steps in order:
1. Check that Python 3.11+ and git are installed. If either is missing, tell me how to install it, remind me to open a new chat afterwards, and stop.
2. Suggest a new folder path (for example, Documents/my-plainbrain) and wait for my confirmation. Never overwrite an existing folder.
3. After I confirm, clone https://github.com/dababonpro/plainbrain into that folder.
4. Read AGENTS.md in the new folder and follow "First setup": install requirements.txt, create my files, and show me today's brief.
```

The agent checks your tools first and asks once where to put Plainbrain. Next, it asks one open question about your work and drafts your first commitments for you to review. It can also offer a read-only scan of your recent local work. That scan runs only if you say yes, stays on your machine, and writes nothing without your approval.

**After setup, open your Plainbrain folder as its own project or session in your agent.** In the Claude desktop app, start a new session and choose the folder. In a terminal, `cd` into the folder and start the agent. Then say "Brief".

If you had to install Python or Git first, restart your agent or open a new chat so it can find the new binary.

**Want a private, backed-up copy instead?** Click **Use this template** on GitHub, choose **Private**, and give your agent your repository URL instead of `dababonpro/plainbrain`. Keep your copy private so your commitments and notes are never public.

<details>
<summary>Prefer the terminal?</summary>

```text
git clone https://github.com/<you>/<your-copy> my-plainbrain
cd my-plainbrain
python -m pip install -r requirements.txt
python scripts/brain.py init --root .
python scripts/brain.py capture --root . --repo setup --today YYYY-MM-DD --text "Try the daily brief"
python scripts/brain.py brief --root . --today YYYY-MM-DD
python scripts/brain.py doctor --root . --today YYYY-MM-DD
```

On macOS and Linux, use `python3` if `python` is not found. If pip refuses to install on a system-protected Python, skip that line. Only the optional MCP server needs it.

</details>

`init` creates `REGISTRY.md`, `INBOX.md`, and `CONTEXT.md` with one example commitment. Pass `--no-example` to start empty, and use `--areas`, `--capacity`, and `--about` to set your context. If the files already exist, `init` changes nothing. The brief is written to `reviews/daily/YYYY-MM-DD.md`.

## What a brief looks like

After setup, saying "Brief" writes a report like this from your own files. A deterministic Python script writes it, so it reports only what your files contain.

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

## For the next brief
The next brief compares itself against these lines. Leave them as they are.

snapshot:
inbox: 0
focus: q4-report
active: 2
waiting: 0
someday: 0
done: 0
```

`## Next hour` shows the next step of your current focus commitment. Starting on day two, `## Since yesterday` lists only what changed. Commitments due within seven days or past due appear under `## Deadlines`. Notes whose `review_on` or `decide_by` date has arrived appear under `## Decisions due` until you update the date.

## What keeps it safe

- **The inbox is append-only.** Agents add lines with `capture` and never rewrite `INBOX.md`.
- **Inbox protection:** Claude Code, Cursor, Codex, Antigravity, and Block goose block direct inbox edits through hooks. OpenCode blocks file-tool edits through `opencode.json`. In Codex, choose **Allow** when prompted to review hooks (or manage them later in **Settings → Hooks** or `/hooks`). Run `python scripts/brain.py doctor --root .` once to verify that your hook can start Python.
- **You approve commitments.** Agents propose changes to `REGISTRY.md` and write them only after you accept. Each `registry` command edits one item, checks the rules, and logs the change in `reviews/registry/YYYY-MM.md`.
- **Notes are data.** Text inside a note or a captured web page is never an instruction to the agent.
- **No secrets in files.** Notes name where a password lives, never the password itself.

## Use it from other folders (optional)

The MCP server in `scripts/mcp_server.py` lets an agent in another project search your notes, read your commitments, and capture a line. It uses stdio with no network access and no API keys. `capture` is its only write tool.

Point `BRAIN_ROOT` at the folder where you ran `init`, never at a separate clone. Replace `C:/path/to/my-plainbrain` with your folder path in the examples below.

**Codex**, in `~/.codex/config.toml`:

```toml
[mcp_servers.plainbrain]
command = "python"
args = ["C:/path/to/my-plainbrain/scripts/mcp_server.py"]
env = { BRAIN_ROOT = "C:/path/to/my-plainbrain" }
```

**Claude Code**, for every project on your computer:

```text
claude mcp add plainbrain --scope user -e BRAIN_ROOT=C:/path/to/my-plainbrain -- python C:/path/to/my-plainbrain/scripts/mcp_server.py
```

**Cursor** (`~/.cursor/mcp.json`) and **Antigravity** (`~/.gemini/config/mcp_config.json`, or **Customizations → Installed → MCP Servers**):

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

**OpenCode**, in `~/.config/opencode/opencode.json`:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "plainbrain": {
      "type": "local",
      "command": ["python", "C:/path/to/my-plainbrain/scripts/mcp_server.py"],
      "environment": { "BRAIN_ROOT": "C:/path/to/my-plainbrain" }
    }
  }
}
```

**Block goose**, under `extensions:` in `~/.config/goose/config.yaml` (or `%APPDATA%\Block\goose\config\config.yaml` on Windows):

```yaml
extensions:
  plainbrain:
    name: Plainbrain
    type: stdio
    cmd: python
    args: ["C:/path/to/my-plainbrain/scripts/mcp_server.py"]
    envs: { BRAIN_ROOT: "C:/path/to/my-plainbrain" }
    enabled: true
```

Use the Python environment where you installed `requirements.txt`. To verify the setup, ask your agent to search for `PARA`.

## Daily use

| You want to | Say to your agent | Or run |
|---|---|---|
| Note something on your mind | *"Capture: call the dentist on Monday"* | `capture --root . --repo <folder> --text "..."` |
| See what to do today | *"Brief"* | `brief --root .`, then `board --root .` |
| Add or change a commitment | *"Add a commitment: renew my passport"* | `registry add`, `registry update`, `registry done` |
| Keep a promise you made in passing | *"I'll send Sam the figures by Friday"* | The agent proposes a commitment at the next pause and runs `registry add` after you accept |
| Find something | *"What do I know about pricing?"* | `search --root . --query "words"` |
| Keep something worth finding again | *"Add a note on our pricing decision"* | Skill: `note-creation` |
| Review the week | *"Weekly review"* | `review --root .`, then triage the inbox |
| Check your notes for gaps | *"Review my notes"* | `research --root . --source knowledge` |
| See what you worked on recently | *"Look at my recent work and suggest what to track"* | `recent --path <folder>`, `recent --claude-sessions` |
| Check the setup | *"Check Plainbrain"* | `doctor --root .` |
| Get the latest version | *"Update Plainbrain"* | Follow `## Updating Plainbrain` in `AGENTS.md` |

Updating never touches your commitments, inbox, notes, or generated reviews because git does not track them. If you modified a tracked file such as an example note, the update stops first. A repository created with **Use this template** has separate git history and cannot pull directly.

Every command takes `--root .`. Agents follow `AGENTS.md` and use the skills in `.claude/skills/` and `.agents/skills/`.

## Three fields on every note

| Field | Values | Answers |
|---|---|---|
| `type` | decision, reference, procedure, lesson, technique, person, meeting | What kind of note is it? |
| `para` | project, area, resource, archive | How actionable is it? |
| `status` | current, superseded | Is it still true? |

`para` uses Tiago Forte's PARA method as a frontmatter field rather than a folder, so notes never need to move. `archive` means inactive, and `superseded` means no longer true. Delete the example notes in `knowledge/` once your own notes replace them.

## With or without Obsidian

| Task | Without Obsidian | With Obsidian |
|---|---|---|
| Find notes | `search`, or ask your agent | Same, plus Obsidian search |
| Browse notes by PARA | Ask your agent, or search by field | Open `views/Plainbrain.base` |
| Rename a note | Update links with your agent | Obsidian updates links automatically |

Nothing requires an Obsidian plugin.

## Which agents

Agents work with Plainbrain in one of two modes:

- **Enforced:** a hook blocks direct edits to `INBOX.md`, so the inbox stays append-only even if the agent forgets.
- **Instructed:** the agent reads `AGENTS.md` and follows its rules, without a hook blocking direct edits.

Hooks require a working Python command. Claude Code's hook tries `python` and falls back to `python3`. Cursor, Codex, and Antigravity hooks call `python` directly. Run `python scripts/brain.py doctor --root .` to see whether hooks are active on your machine.

| Agent | Mode | Files used | Status |
|---|---|---|---|
| Claude Code | Enforced | `.claude/settings.json`, `.claude/skills/` | Tested on Windows, November 2026 |
| Codex | Enforced after allowing the hook | `.codex/hooks.json`, `.agents/skills/` | Tested on Windows, November 2026 |
| Cursor | Enforced | `.cursor/hooks.json` | Tested on Windows, November 2026 |
| Antigravity | Enforced | `.agents/hooks.json`, `.agents/skills/` | Automated tests pass, manual test pending |
| Block goose | Enforced | `.agents/plugins/plainbrain/hooks/hooks.json`, `.agents/skills/`, `AGENTS.md` | Automated tests pass, manual test pending |
| OpenCode | Enforced for file tools, instructed for shell | `opencode.json`, `.agents/skills/`, `.claude/skills/`, `AGENTS.md` | Configured from docs, manual test pending |
| Amp, Jules, Zed | Instructed | `AGENTS.md` | Reads `AGENTS.md` automatically per vendor docs |
| Gemini CLI | Instructed | `.gemini/settings.json` points to `AGENTS.md` | Configured from docs, trust the folder if prompted |
| GitHub Copilot in VS Code | Instructed | `AGENTS.md` with `chat.useAgentsMdFile` enabled | Configured from docs |

Zed reads only the first instruction file it finds, so keep `AGENTS.md` as the only rules file in the root folder.

## Good to know

- **Compatibility:** automated tests run on Windows, Linux, and macOS for every change.
- **Backups:** git ignores your personal files so updates never overwrite them. Keep your Plainbrain folder in a backed-up or synced drive.
- **You decide:** the daily brief recommends a next step and never edits your commitments.

## Licence

Copyright DababonPro IT Solutions, 2026.

- Templates, example notes, this README, and `AGENTS.md`: [CC BY 4.0](LICENSE-docs).
- Scripts, tests, and skills: [MIT](LICENSE). Each skill folder includes its own copy.

Built by DababonPro IT Solutions. Independent of the AI vendors whose tools it works with.

# Plainbrain

Plainbrain is a local commitment and work-loop system in plain Markdown for people running AI agents across projects. It gives you one commitment list (`REGISTRY.md`) your agent proposes to and you approve, an append-only inbox guarded by hooks, deterministic daily briefs, searchable notes, and a local MCP server—a second brain that tracks what you owe, not just what you read.

Free from DababonPro IT Solutions. It works on its own. [Obsidian](https://obsidian.md) is optional, and any agent that reads `AGENTS.md` can run it, such as Claude Code, Codex, Cursor, or Antigravity.

**Its sibling:** the [Human-Approved Agent Playbook](https://github.com/dababonpro/human-approved-agents) covers agents that change code and data. Plainbrain covers what you know and what you owe.

## Install

Requires Python 3.11 or later. Obsidian is optional.

### Option 1: Install as a package (every agent)

Install the package once so Plainbrain holds the code and your folder holds only your data. You can put your data folder in its own private git repo without blocking future Plainbrain updates.

```text
pipx install "plainbrain[mcp] @ git+https://github.com/dababonpro/plainbrain.git@v1.3.0"
```

*(With `uv`: `uv tool install "plainbrain[mcp] @ git+https://github.com/dababonpro/plainbrain.git@v1.3.0"`. Omit `[mcp]` if you do not need the cross-project MCP server.)*

Next, create your data folder and run first setup:

```text
plainbrain setup --to ~/Documents/my-plainbrain
```

Or paste this into Claude Code, Codex, Cursor, or Antigravity:

```text
Set up Plainbrain for me. Follow these steps in order:
1. Check that Python 3.11+ and `plainbrain` are installed (if `plainbrain` is missing, tell me to install it with pipx or uv tool install and stop).
2. Suggest a new folder path (for example, Documents/my-plainbrain) and wait for my confirmation. Never overwrite an existing folder.
3. After I confirm, run `plainbrain setup --to "<folder>"`.
4. Read AGENTS.md in the new folder and follow "First setup": ask me about my work, create my files, offer global hooks, and show me today's brief.
```

**After setup, open your Plainbrain folder as its own project or session in your agent.** In the Claude desktop app, start a new session and choose the folder. In a terminal, `cd` into the folder and start the agent. Then say "Brief".

### Option 2: Install as a Claude Code plugin

In Claude Code (2.1.275 or later), install the self-contained plugin in one step:

```text
/plugin install plainbrain --marketplace dababonpro/plainbrain
```

Then say `"Set up Plainbrain"`. The agent asks where to put your data folder, creates it from the plugin's own template without copying scripts into your folder, and runs the same first setup as above.

What the plugin adds, and everything it runs:

- **Skills:** `setup` and `plainbrain`, plus the note, retrieval, and review skills this template ships.
- **Hooks:** before a file edit or a shell command, it runs `scripts/inbox_guard.py` to keep your inbox append-only; when a session ends with uncaptured commits, PRs, or Jira work, `scripts/capture_nudge.py` reminds you once to capture it.
- **A local MCP server:** `scripts/mcp_server.py`, over stdio, so an agent in any project can search your notes, read your commitments, and add one line to your inbox. Adding that line is its only write.
- **One pointer file:** setup writes your folder's path to `~/.plainbrain`, so the hook and the server find it from any project. Delete that file to disconnect the plugin; your folder is untouched.

The plugin uses no network, sends nothing anywhere, and stores no keys. Tested on Windows in Claude Code. The MCP server starts with `python`; on macOS and Linux, where the command is often `python3`, the skills and hooks work and the server may not start unless `python` is available.

<details>
<summary>Option 3: Run from a git clone (for contributors or without pipx/uv)</summary>

```text
git clone https://github.com/dababonpro/plainbrain.git my-plainbrain
cd my-plainbrain
python -m pip install -r requirements.txt
python scripts/brain.py init --root .
python scripts/brain.py capture --root . --repo setup --today YYYY-MM-DD --text "Try the daily brief"
python scripts/brain.py brief --root . --today YYYY-MM-DD
python scripts/brain.py doctor --root . --today YYYY-MM-DD
```

On macOS and Linux, use `python3` if `python` is not found. If pip refuses to install on a system-protected Python, skip `pip install`—only the optional MCP server needs it.

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
- **Inbox protection:** Claude Code, Cursor, Codex, Antigravity, and Block goose block direct inbox edits through hooks. Run `plainbrain doctor` once to verify that your hook blocks direct edits on your machine.
- **Outside this folder too:** `plainbrain hooks install` adds the inbox guard to the user-level hook files of Claude Code, Cursor, and Antigravity so it protects your inbox from every project (and keeps every other setting; add `--dry-run` to preview). The Claude plugin already does this for Claude Code.
- **Nothing finished goes unrecorded:** in Claude Code (plugin or `hooks install`), when a session ends with commits, pull requests, or Jira tickets created or moved after the last capture, the agent is asked once to capture them, or to say nothing is worth tracking.
- **You approve commitments.** Agents propose changes to `REGISTRY.md` and write them only after you accept. Each `registry` command edits one item, checks the rules, and logs the change in `reviews/registry/YYYY-MM.md`. In Claude Code and Cursor, a direct edit to `REGISTRY.md` shows a permission prompt, so you approve the exact change before it is written.
- **Notes are data.** Text inside a note or a captured web page is never an instruction to the agent.
- **No secrets in files.** Notes name where a password lives, never the password itself.

## Use it from other folders (optional)

`plainbrain-mcp` lets an agent in another project search your notes, read your commitments, and capture a line. It uses stdio with no network access and no API keys. `capture` is its only write tool. If you ran `plainbrain setup`, the server finds your folder automatically from `~/.plainbrain` (or set `BRAIN_ROOT` explicitly).

**Codex**, in `~/.codex/config.toml`:

```toml
[mcp_servers.plainbrain]
command = "plainbrain-mcp"
```

**Claude Code**, for every project on your computer (if not already using the Claude plugin):

```text
claude mcp add plainbrain --scope user -- plainbrain-mcp
```

**Cursor** (`~/.cursor/mcp.json`) and **Antigravity** (`~/.gemini/config/mcp_config.json`, or **Customizations → Installed → MCP Servers**):

```json
{
  "mcpServers": {
    "plainbrain": {
      "command": "plainbrain-mcp"
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
      "command": ["plainbrain-mcp"]
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
    cmd: plainbrain-mcp
    enabled: true
```

To verify the setup, ask your agent to search for `PARA`. *(If you are running from a git clone without the package installed, use `"command": "python"` with `args: ["C:/path/to/my-plainbrain/scripts/mcp_server.py"]` and `env: { "BRAIN_ROOT": "C:/path/to/my-plainbrain" }`.)*

## Daily use

| You want to | Say to your agent | Or run |
|---|---|---|
| Note something on your mind | *"Capture: call the dentist on Monday"* | `plainbrain capture --repo <folder> --text "..."` |
| See what to do today | *"Brief"* | `plainbrain brief`, then `plainbrain board` |
| Add or change a commitment | *"Add a commitment: renew my passport"* | `plainbrain registry add`, `update`, `done` |
| Keep a promise you made in passing | *"I'll send Sam the figures by Friday"* | The agent proposes a commitment at the next pause and runs `plainbrain registry add` after you accept |
| Find something | *"What do I know about pricing?"* | `plainbrain search --query "words"` |
| Keep something worth finding again | *"Add a note on our pricing decision"* | Skill: `note-creation` |
| Review the week | *"Weekly review"* | `plainbrain review`, then triage the inbox |
| Check your notes for gaps | *"Review my notes"* | `plainbrain research --source knowledge` |
| See what you worked on recently | *"Look at my recent work and suggest what to track"* | `plainbrain recent --path <folder>`, `--claude-sessions` |
| Check the setup | *"Check Plainbrain"* | `plainbrain doctor` |
| Get the latest version | *"Update Plainbrain"* | Follow `## Updating Plainbrain` in `AGENTS.md` |

Upgrading the `plainbrain` package or plugin never touches your commitments, inbox, notes, or generated reviews. Agents follow `AGENTS.md` and use the skills in `.claude/skills/` and `.agents/skills/`.

## Three fields on every note

| Field | Values | Answers |
|---|---|---|
| `type` | decision, reference, procedure, lesson, technique, person, meeting | What kind of note is it? |
| `para` | project, area, resource, archive | How actionable is it? |
| `status` | current, stale, superseded | Is it still true? |

`para` uses Tiago Forte's PARA method as a frontmatter field rather than a folder, so notes never need to move. `archive` means inactive, `stale` means known to be out of date and not yet corrected, and `superseded` means no longer true. Delete the example notes in `knowledge/` once your own notes replace them.

## With or without Obsidian

| Task | Without Obsidian | With Obsidian |
|---|---|---|
| Find notes | `plainbrain search`, or ask your agent | Same, plus Obsidian search |
| Browse notes by PARA | Ask your agent, or search by field | Open `views/Plainbrain.base` |
| Rename a note | Update links with your agent | Obsidian updates links automatically |

Nothing requires an Obsidian plugin.

## Which agents

Agents work with Plainbrain in one of two modes:

- **Enforced:** a hook blocks direct edits to `INBOX.md`, so the inbox stays append-only even if the agent forgets.
- **Instructed:** the agent reads `AGENTS.md` and follows its rules, without a hook blocking direct edits.

Run `plainbrain doctor` to see whether hooks are active on your machine.

| Agent | Mode | Files used | Status |
|---|---|---|---|
| Claude Code | Enforced | `.claude/settings.json` (or plugin), `.claude/skills/`, `CLAUDE.md` (imports `AGENTS.md`) | Tested on Windows, November 2026 |
| Codex | Enforced after allowing the hook | `.codex/hooks.json`, `.agents/skills/` | Tested on Windows, November 2026 |
| Cursor | Enforced | `.cursor/hooks.json` | Tested on Windows, November 2026 |
| Antigravity | Enforced | `.agents/hooks.json`, `.agents/skills/` | Automated tests pass, manual test pending |
| Block goose | Enforced | `.agents/plugins/plainbrain/hooks/hooks.json`, `.agents/skills/`, `AGENTS.md` | Automated tests pass, manual test pending |
| OpenCode | Instructed (or enforced via `opencode.json`) | `.agents/skills/`, `.claude/skills/`, `AGENTS.md` | Configured from docs, manual test pending |
| Pi | Instructed | `AGENTS.md`, `.agents/skills/` | Configured from docs, manual test pending |
| Hermes Agent | Instructed | `AGENTS.md` | Configured from docs, manual test pending |
| Amp, Jules, Zed | Instructed | `AGENTS.md` | Reads `AGENTS.md` automatically per vendor docs |
| Gemini CLI | Instructed | `.gemini/settings.json` points to `AGENTS.md` | Enterprise accounts only: Google ended Gemini CLI for personal accounts on 18 June 2026. Use Antigravity instead |
| GitHub Copilot in VS Code | Instructed | `AGENTS.md` with `chat.useAgentsMdFile` enabled | Configured from docs |

Zed reads only the first instruction file it finds. `AGENTS.md` comes before `CLAUDE.md` in its order, so Zed reads `AGENTS.md`. Do not add `.rules`, `.cursorrules`, `.windsurfrules`, `.clinerules`, or `AGENT.md` to the root folder, because Zed would read that file instead.

## Good to know

- **Compatibility:** automated tests run on Windows, Linux, and macOS for every change.
- **Backups:** put your Plainbrain **data folder** in a private git repository or synced drive (`REGISTRY.md`, `INBOX.md`, `CONTEXT.md`, `knowledge/`, and `reviews/` are all trackable; `.gitignore` ignores `board/`, `.obsidian/`, `.env`, and `*.lock`). Do not use GitHub's **Use this template** on this code repository for a private copy, because a template copy disconnects you from package/git updates.
- **You decide:** the daily brief recommends a next step and never edits your commitments.

## Licence

Copyright DababonPro IT Solutions, 2026.

- Templates, example notes, this README, and `AGENTS.md`: [CC BY 4.0](LICENSE-docs).
- Scripts, tests, and skills: [MIT](LICENSE). Each skill folder includes its own copy.

Built by DababonPro IT Solutions. Independent of the AI vendors whose tools it works with.

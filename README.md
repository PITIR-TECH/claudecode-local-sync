# Claude Sync — Cross-Platform Session Sync for Claude Code

Created by **Coskun Eren** at **[PITIR TECH](https://github.com/PITIR-TECH)**

Sync your Claude Code sessions, memory, plugins, agents, skills, rules, hooks, commands, MCP configs, and project settings across Mac and Windows. Switch PCs and pick up exactly where you left off.

---

## Why This Exists

Claude Code's real power is **local** — MCP servers, local file access, terminal commands, build tools, test runners, browser automation, database connections. None of this works in Claude Remote, Claude Team, or cloud-based setups.

But working locally creates a problem: **your sessions, memory, plugins, and configs are trapped on one machine.**

| Approach | Local tools (MCP, terminal, builds) | Session sync | Project sync |
|---|---|---|---|
| **Claude Remote / Team** | No — cloud only, no local MCP or CLI | Built-in | Built-in |
| **Standard Git + VS Code** | Yes | No — sessions stay on one PC | Yes |
| **Claude Sync (this repo)** | **Yes — full local power** | **Yes — sessions, memory, plugins, everything** | **Yes** |

### The Problem

You're a developer. You have a desktop at work, a laptop at home, maybe a Windows machine for testing. You use Claude Code locally because you need:
- MCP servers (database, browser, API integrations)
- Local terminal access for builds, tests, deployments
- File system access for reading/writing project files
- Plugin ecosystems (claude-mem, LSP servers)
- Custom agents, skills, rules, hooks

But when you switch machines, your **sessions are gone**. Your **memory files don't follow you**. Your **MCP configs vanish**. Your **plugin settings disappear**. You start over on every machine.

### The Solution

Claude Sync gives you the best of both worlds:
- **Full local power** — MCP servers, terminal, builds, everything works
- **Full sync** — sessions, memory, plugins, agents, skills, hooks, MCP configs, project settings all follow you across machines
- **Per-project isolation** — push/pull only the project you're working on
- **Cross-platform** — Mac and Windows, automatic path fixing

Work like a true developer with your full arsenal available. Push when you leave. Pull when you arrive. Everything is exactly where you left it.

---

## How It Works

### The Workspace

Create a main folder anywhere on your machine — call it whatever you want. This is your workspace root. All your projects live as subfolders inside it:

```
my-workspace/                   <- can be anywhere, named anything
├── scripts/                    <- root scripts from this repo
├── my-web-app/                 <- a project (its own git repo)
│   └── scripts/                <- generated push/pull/rollback for this project
├── my-api/                     <- another project
│   └── scripts/                <- generated push/pull/rollback for this project
└── my-mobile-app/              <- another project
    └── scripts/                <- generated push/pull/rollback for this project
```

Every script detects its location dynamically — no hardcoded paths. The `scripts/` folder figures out its parent directory automatically. Put the workspace on your Desktop, in Documents, on a second drive, wherever you want.

### Two Repos Per Project

Claude Code stores everything in `~/.claude/` — sessions, memory, plugins, settings. This system uses a private GitHub repo to sync that directory across machines, with automatic path fixing, session merging, and platform-specific config correction.

Two types of data are synced:
- **Project code** (v-tags) — each project has its own GitHub repo
- **Sessions + config** (s-tags) — everything in `~/.claude/` syncs via a single dotfiles repo

### Per-Project Sync

Projects are identified by **git remote**, not path. Push and pull behave differently:

**Push** is scoped — only that project's sessions are committed and pushed. Other projects' sessions are untouched.

**Pull** fetches everything (git can't pull selectively from a single repo), then runs the **full 12-step migration pipeline on ALL projects** — path fixing, timestamp correction, session merging, etc. This is necessary because pulling from a shared repo updates files across all projects, and they all need their paths and timestamps corrected for the current machine.

**Conflict resolution** during per-project pull is scoped:
- Files **inside** the pulled project's scope — you're asked whether to accept remote or keep local
- Files **outside** the project's scope (other projects, settings) — local is kept automatically, no prompt

### What Syncs

Everything by default. The only exclusions are machine-local ephemeral files:

| Excluded | Why |
|---|---|
| `.credentials.json` | OAuth tokens — security |
| `settings.local.json` | Machine-specific permissions |
| `cache/`, `debug/`, `telemetry/` | Temp data, regenerated |
| `sessions/` | IDE process state, not session history |
| `stats-cache.json`, `*.untrimmed` | Ephemeral |
| `*.jsonl.backup-*`, `*.jsonl.pre-*`, etc. | Session repair artifacts |
| `projects/*/tool-results/` | Machine-local tool output blobs |
| `projects/*/*.meta.json` | Subagent metadata |

Everything else syncs automatically — plugins you install, agents you create, skills, rules, hooks, MCP servers, observer sessions, tool-results, subagent sessions, memory files. No config changes needed. Any new plugin or tool you install on one machine is available on all machines after the next sync.

---

## Understanding the Two Sync Systems

This tool syncs two separate things through two separate mechanisms:

| What | Where it lives | Synced via | Identified by |
|---|---|---|---|
| **Project code** | `workspace/<project>/` | Each project's own GitHub repo | Git remote URL |
| **Sessions + config** | `~/.claude/` (Claude's native folder) | A single private dotfiles repo | Encoded absolute path |

**Sessions are NOT stored in your project folder.** They live in Claude's native `~/.claude/` directory. When you push/pull a project, the session sync runs automatically alongside the code sync — but they go to different repos.

This means:
- Deleting a project folder does NOT delete your sessions
- Recreating a project with `new-project` restores the code; sessions were never lost
- You can sync sessions without touching project code (and vice versa)

---

## Quick Start

### Step 1: Prerequisites

Install these on every machine:
- Git (https://git-scm.com)
- Python 3.8+ (https://python.org)
- Node.js (https://nodejs.org)
- Claude Code: `npm install -g @anthropic-ai/claude-code`

### Step 2: Set Up Your Workspace

```bash
# Create a workspace folder anywhere
mkdir ~/Desktop/my-workspace
cd ~/Desktop/my-workspace

# Copy the scripts/ folder from this repo into it
# (download this repo as ZIP, or git clone, then copy scripts/)
```

### Step 3: Configure Ownership (first PC only)

```bash
./scripts/setup-owner.sh        # Mac
scripts\setup-owner.bat          # Windows
```

The setup wizard:
1. **Auto-detects your Claude CLI directory** (`~/.claude/`) — shows what it found and asks you to confirm. If it's in a non-standard location, you can enter a custom path.
2. Asks for your **dotfiles repo URL** — create a PRIVATE repo on GitHub first (e.g., `your-name/claude-dotfiles`)
3. Asks for your **GitHub org/username** — used for project repo examples

This updates all scripts with your configuration. **You only run this once** — the settings travel with your project code (see "Setting Up a Second PC" below).

### Step 4: Add Your Projects

For each project, create a GitHub repo first, then:

```bash
./scripts/new-project.sh         # Mac
scripts\new-project.bat          # Windows
```

Enter the repo URL (e.g., `https://github.com/your-name/my-app`). The script clones the code and generates push/pull/rollback scripts with that project's remote baked in.

### Step 5: Pull Sessions (if you have them from another machine)

Run `pull.sh` from each project to pull that project's sessions:

```bash
cd my-app && ./scripts/pull.sh        # Mac
cd my-app && scripts\pull.bat          # Windows
```

### Step 6: Authenticate

The first time you push/pull, GitHub will ask for authentication. Use a personal access token or SSH key. After that, it's cached.

---

## Setting Up a Second PC

You do **NOT** need to run `setup-owner` again. Your configuration (org, dotfiles URL) is already baked into the scripts that live inside your project repos.

### If Claude CLI is in the default location (`~/.claude/`):

```bash
# 1. Create workspace folder
mkdir ~/Desktop/my-workspace
cd ~/Desktop/my-workspace

# 2. Copy YOUR scripts/ folder from your first PC (not the original repo download —
#    these were configured by setup-owner with your org, repos, and settings)

# 3. Pull all sessions
./scripts/pull-all-sessions.sh

# 4. Clone each project
./scripts/new-project.sh
# Enter the repo URL — it clones the code WITH the already-configured scripts
```

That's it. The configured push/pull/rollback scripts come with the project code.

### If Claude CLI is in a custom location:

Run `setup-owner` on the second PC **only to set the Claude directory path**:
```bash
./scripts/setup-owner.sh
# It will detect the directory and ask you to confirm
# The org/repo settings are already in the scripts — just press Enter through those
```

### Multiple machines with different Claude paths:

Each machine can have its own `.claude-dir` config file (gitignored, machine-specific). The sync engine reads it automatically. Run `setup-owner` on each machine that has a non-default Claude path.

### What `new-project` Does

When you run `new-project`, it:
1. Asks for your project's GitHub repo URL
2. Clones the project into your workspace as a subfolder
3. Generates 6 scripts inside the project's `scripts/` folder:
   - `push.sh` + `push.bat` — push code + sync this project's sessions
   - `pull.sh` + `pull.bat` — pull code + sync this project's sessions
   - `rollback.sh` + `rollback.bat` — rollback to a previous version
4. Copies the launcher and documentation into the project

These generated scripts have the project's git remote (e.g., `--project your-org/my-app`) baked in, so each project's session sync is scoped automatically.

### Starting Fresh

If something goes wrong or you're setting up a new machine, you can delete all project folders and recreate them with `new-project`. Sessions are stored in `~/.claude/` (synced via the dotfiles repo), not in the project folders. Running `new-project` again reclones the code and regenerates all scripts — your sessions are untouched.

### Daily Workflow

```
Arrive at a machine  →  ./scripts/pull.sh (from each project)
Work                 →  work
Done for the day     →  ./scripts/push.sh (from each project)
```

---

## Scripts

### Root Scripts (workspace/scripts/)

| Script | Purpose |
|---|---|
| `push-all-sessions.sh/.bat` | Push ALL sessions (force push, squash history) |
| `pull-all-sessions.sh/.bat` | Pull ALL sessions + full migration pipeline |
| `rollback-all-sessions.sh/.bat` | Rollback ALL sessions to a previous sync tag |
| `new-project.sh/.bat` | Create a new project (clone + generate scripts) |
| `setup-owner.sh/.bat` | Configure for your GitHub account (run once) |
| `claude-launch.sh/.bat` | Interactive Claude Code launcher TUI |

### Per-Project Scripts (generated by new-project)

| Script | Purpose |
|---|---|
| `push.sh/.bat` | Push project code + sync this project's sessions |
| `pull.sh/.bat` | Pull project code + sync this project's sessions |
| `rollback.sh/.bat` | Rollback project code to a previous version |

Every push and pull script starts by asking what you want to sync:

```
What would you like to push?

  1) Both project code + sessions  (default)
  2) Project code only
  3) Sessions only

Choice [1]:
```

Press Enter for both (most common). Pick 2 or 3 when you want to sync only one.

Then shows a **full status dashboard** before doing anything:

```
  ┌─────────────────────────────────────────────────┐
  │  SESSION SYNC STATUS                            │
  │  Local:  abc1234  2026-03-26 15:00  [s44] ...   │
  │  Remote: def5678  2026-03-26 10:00  [s43] ...   │
  │  Local ahead: 2 commit(s)  Behind: 0 commit(s) │
  └─────────────────────────────────────────────────┘

  + 3 uncommitted change(s) on disk (active sessions, recent edits)
     M projects/.../234428a7.jsonl
     M history.jsonl
     M plugins/known_marketplaces.json

  What will be pushed (committed):
    projects/.../session1.jsonl    | 45 +
    settings.json                  |  2 +-
    3 files changed, 47 insertions(+)

  The 3 uncommitted change(s) above will also be included in this push.
```

Every file is listed — nothing is truncated. You can scroll up to review the full list before confirming.

### Root pull: sessions vs config separation

When pulling all sessions (`pull-all-sessions`), if the remote has both session changes and config changes, you're asked how to handle them separately:

```
  Sessions to pull: 142 file(s)
    projects/.../session1.jsonl
    projects/.../session2.jsonl
    ...

  Config/settings to pull: 5 file(s)
    settings.json
    plugins/known_marketplaces.json
    plugins/installed_plugins.json
    project-settings.json
    keybindings.json

  What would you like to pull?
    1) Both sessions + config  (default)
    2) Sessions only (keep local config)
    3) Config only (keep local sessions)
    N) Cancel
```

This is useful when you want different configurations on different machines (different MCP servers, different plugins) but still want your sessions synced everywhere.

---

## Customizing the Generated Scripts

The per-project `push.sh`, `pull.sh`, and `rollback.sh` (plus their `.bat` counterparts) are generated from templates inside `new-project-gen.py`. If you want to change how these scripts behave:

1. Edit the templates in `scripts/new-project-gen.py`
2. Re-run `new-project` for each existing project to regenerate its scripts
3. Or manually edit the specific project's scripts — but know they'll be overwritten next time `new-project` runs for that project

The root scripts (`push-all-sessions`, `pull-all-sessions`, etc.) are standalone — edit them directly.

---

## Pull Pipeline (11 Steps)

Both `pull-all-sessions` and per-project `pull` run the same pipeline on **all** projects. The only difference is how conflicts are resolved (see "How Conflicts Are Resolved" below).

When you pull, the engine automatically:

```
 1. Fix .gitignore           Enforce security rules on all machines
 2. Backup large files       Append >90MB sessions to session-originals/ archive
 3. Git pull                 Fetch latest from GitHub (replaces local with remote)
 4. Materialize symlinks     Convert old symlinks to real directories
 5. Merge sessions           Copy new + replace outdated files from other machine
 6. Detect renamed projects  Match by git remote URL
 7. Fix cwd paths            Rewrite paths in ALL .jsonl (including subagents)
 8. Fix platform configs     Fix plugin installLocation/installPath for current OS
 9. Clean up other-PC dirs   Delete merged dirs, free disk space
10. Fix timestamps           Set correct dates so claude --resume shows real times
11. Import project settings  Apply MCP servers, allowedTools from other machine
```

After pull, local sessions are the remote's 90MB trimmed version. Full history lives in `session-originals/` (local-only, gitignored, grows on every push and pull).

## Push Pipeline (6 Steps)

```
 1. Fix .gitignore           Enforce security rules
 2. Export project settings   Save MCP/tools keyed by git remote
 3. Trim oversized files      Sessions >90MB trimmed to last 90MB
 4. Stage + commit            Per-project: incremental. Root: soft-reset + force push
                              Repair artifacts (*.jsonl.backup-*, tool-results/) auto-excluded
 5. Push                      Per-project: regular push. Root: force push with tag
                              On failure: auto-rollback commit + delete tag (prevents orphaned tags)
 6. Archive + restore         Append full originals to session-originals/ archive,
                              then restore full files back to project folder
```

---

## Ownership Setup

If you're setting this up for yourself or your team:

1. Create a **private** GitHub repo for your dotfiles (e.g., `your-org/claude-dotfiles`)
2. Run `setup-owner.sh` (Mac) or `setup-owner.bat` (Windows)
3. Enter your dotfiles repo URL and GitHub org/username
4. The script updates all references in sync-sessions.py, new-project.sh/bat, and documentation

That's it. All future projects generated by `new-project` will use your repos.

---

## Cross-Platform Details

### Dynamic Root Directory

All scripts detect their location dynamically — nothing is hardcoded. The workspace folder can be:
- Anywhere on disk (`~/Desktop`, `D:\projects`, `/home/dev/work`)
- Named anything (doesn't have to be "CLAUDECODE")
- Different paths on each machine (the path encoding handles this)

The only structural requirement: `scripts/` folder at the root, project folders as siblings.

### Path Encoding

Claude Code stores sessions keyed by absolute path. This system encodes paths by replacing `\ / : .` with `-`:
- Mac: `/Users/alice/projects/workspace/my-app` -> `-Users-alice-projects-workspace-my-app`
- Windows: `C:\Users\alice\projects\workspace\my-app` -> `C--Users-alice-projects-workspace-my-app`

On pull, the engine merges sessions from the other platform's encoded dirs into yours, fixes all paths inside session files, then cleans up the other platform's dirs.

### Plugin Path Fixing

Plugin configs like `known_marketplaces.json` and `installed_plugins.json` contain absolute paths (e.g., `C:\Users\alice\.claude\plugins\...`). These are automatically rewritten to the current OS's home directory on every pull.

### Project Settings Sync

MCP servers and allowedTools configured per-project in `.claude.json` are synced via git remote matching:
1. Push exports settings keyed by `org/repo` (e.g., `my-org/my-app`)
2. Pull imports by matching git remotes to local project paths
3. Only fills in empty settings — never overwrites existing configs

### Large File Handling

Sessions over 90MB are trimmed to the last 90MB for push (GitHub can't handle huge files). `session-originals/` is a local-only, gitignored, growing archive that preserves full session history.

**On push**, sessions >90MB are:
1. Copied to `.untrimmed` backup, then trimmed to 90MB for GitHub
2. After push succeeds, the full `.untrimmed` file is **appended** to `session-originals/` (growing archive, no duplication)
3. The full file is restored back to the project folder (you keep working with it)

**On pull**, sessions >90MB are:
1. **Appended** to `session-originals/` before the pull replaces them
2. Replaced with the remote's 90MB version (trimmed by the other machine)

**The archive grows on both push and pull.** Each append operation finds the last line of the existing archive in the new content, and only appends lines after that point. No duplicates. If no overlap is found, all content is appended.

**Example flow:**
```
Windows: 300MB session → push → archived to session-originals, 90MB on remote, 300MB stays local
Mac: pull 90MB → work → grows to 130MB → push → 130MB archived, 90MB on remote, 130MB stays local
Windows: pull → 300MB appended to session-originals, replaced with 90MB
Windows: work → grows to 150MB → push → 150MB archived, 90MB on remote, 150MB stays local
Mac: pull → 130MB appended to session-originals, replaced with 90MB
```

Each machine's `~/.claude/session-originals/` accumulates the complete session history from that machine's perspective.

---

## Folder Structure

```
workspace/                                <- your root (anywhere, any name)
├── scripts/                              <- root scripts (from this repo)
│   ├── push-all-sessions.sh / .bat       <- push ALL sessions
│   ├── pull-all-sessions.sh / .bat       <- pull ALL sessions
│   ├── rollback-all-sessions.sh / .bat   <- rollback ALL sessions
│   ├── new-project.sh / .bat             <- create new project
│   ├── new-project-gen.py                <- script template generator (edit this to customize)
│   ├── sync-sessions.py                  <- core engine
│   ├── setup-owner.sh / .bat             <- configure GitHub account
│   ├── claude-launch.sh / .bat / .py     <- interactive launcher
│   └── platform-fix.py                   <- plugin path fixer
├── README.md
├── my-web-app/                           <- a project
│   ├── scripts/
│   │   ├── push.sh / push.bat            <- push code + this project's sessions
│   │   ├── pull.sh / pull.bat            <- pull code + this project's sessions
│   │   ├── rollback.sh / rollback.bat    <- rollback code
│   │   └── claude-launch.sh / .bat       <- launcher (finds root .py)
│   └── (project files...)
├── my-api/                               <- another project
│   └── scripts/ ...
└── ...
```

---

## Scenarios

### Brand New PC
```
1. Install git, Python, Node.js, Claude Code
2. Create a workspace folder, copy scripts/ into it
3. Run setup-owner.sh (first time only)
4. Run new-project.sh for each project — clones code + generates scripts
5. Run pull.sh from each project — pulls that project's sessions from remote
```

### Existing PC (returning from another machine)
```
1. Run pull.sh from each project you'll work on
```

### End of Workday
```
1. Run push.sh from each project you worked on
```

**Always use per-project push/pull.** Each project's push only touches that project's sessions — it's incremental (no force push), safe even when working on different projects across multiple machines simultaneously, and safe even if you forget to pull first. `push-all-sessions` / `pull-all-sessions` are power tools for initial setup only — they force-push the entire remote state, which can overwrite another machine's newer sessions.

### Starting Over
```
1. Delete any project folder
2. Run new-project.sh to recreate it — reclones code, regenerates scripts
3. Sessions are safe in ~/.claude/ — they were never in the project folder
```

---

## Technical Architecture

### sync-sessions.py

The core engine (~1500 lines of Python) handles everything:
- Two modes: `push/pull` with optional `--project org/repo` for per-project scope
- Path encoding/resolution matching projects by git remote
- Recursive session merging (copies ALL data types: .jsonl, subagents, tool-results, memory)
- Platform config fixing (plugin paths, install locations)
- Large file trim/restore with overlap detection
- `.gitignore` enforcement across all machines
- Project settings export/import via git remote matching
- Session timestamp correction
- Stale-data detection with user prompts

### new-project-gen.py

Generates per-project push/pull/rollback scripts from templates. This is the **single source of truth** for per-project scripts. Each generated script:
- **Validates project folder** at startup — compares folder name vs expected, checks git remote if mismatch, stops if wrong project
- Shows PROJECT CODE STATUS (local vs remote, ahead/behind)
- Shows SESSION SYNC STATUS (via sync-sessions.py)
- Warns before destructive operations
- Handles "no code changes" gracefully (still syncs sessions)
- Stashes/restores local changes during pull
- Has `--project org/repo` baked in for scoped session sync
- Pauses before closing on all platforms

**If you want to change per-project script behavior**, edit the templates in `new-project-gen.py`, then re-run `new-project` for each existing project to regenerate its scripts.

### claude-launch.py

Interactive TUI launcher with:
- Resume session / Continue last session (mutually exclusive)
- Auto-accept mode (skip permissions)
- Model selection (Default, Opus, Sonnet, Haiku)
- Live command preview
- Cross-platform key handling (Windows msvcrt / Unix termios)

---

## How Conflicts Are Resolved

When you pull and both machines have modified the same file, git can't automatically merge them. The system handles this differently depending on whether you're pulling all sessions or a single project.

### Pull-All Sessions (root pull)

Uses `git reset --hard` — no conflicts possible. Remote always wins entirely.

### Per-Project Pull

Uses `git pull --no-rebase` (merge) to preserve other projects' local state. When conflicts occur:

**Out-of-scope files** (other projects, settings, plugins) are automatically resolved by **keeping local** — no prompt, no user action needed. This protects your other projects and machine-specific configs.

**In-scope files** (the project you're pulling) are shown to you for a decision:

```
  [CONFLICTS DETECTED]

  Keeping local for 3 file(s) outside my-app scope.

  2 file(s) have conflicts:

    Local  (2026-03-26 20:15):
    Remote (2026-03-26 19:58):

    - projects/..../session1.jsonl
    - projects/..../session2.jsonl

  [WARNING] Your local data is NEWER than the remote.
  Accepting remote will replace these files with older versions.
  If you have unsaved work, cancel and push first.

  Accept remote? (Y/N):
```

- **Y**: Remote wins for in-scope files. Out-of-scope files stay local.
- **N**: Nothing changes. You can resolve manually and push your version.

**The principle:** Per-project pull only asks you about your project. Everything else stays untouched. After conflicts are resolved, the full 12-step migration pipeline runs on ALL projects to fix paths, timestamps, and configs across the board.

---

## Customizing Per-Machine Settings

By default, everything syncs to all machines. But you may want certain settings to stay machine-specific — for example, different MCP servers on Mac vs Windows, or different plugin configs.

### Using .gitignore

Edit `~/.claude/.gitignore` on each machine to exclude files you want to keep local:

```gitignore
# Already excluded by default:
.credentials.json
settings.local.json
cache/
debug/
telemetry/

# Add your own exclusions, for example:
# Keep my MCP config local (different servers per machine)
# mcp-configs/my-local-server.json
```

Each machine's `.gitignore` is independent. Changes you make to `.gitignore` on one machine don't affect the other — the `ensure_gitignore_entries` function only **adds** required security rules, it never removes your custom entries.

### What to exclude vs what to sync

| Want this | Do this |
|---|---|
| Same plugins everywhere | Don't exclude anything (default) |
| Different MCP servers per machine | Add the specific config file to `.gitignore` on each machine |
| Different settings per machine | Keep `settings.local.json` for machine-specific permissions (already excluded). For other settings, add to `.gitignore`. |
| Skip syncing a specific plugin's data | Add `plugins/data/<plugin-name>/` to `.gitignore` |
| Different keybindings per machine | Add `keybindings.json` to `.gitignore` on each machine |

### Important

- The `.gitignore` inside `~/.claude/` controls what gets synced via the dotfiles repo
- Editing it only affects the machine you edit it on
- The security rules (`.credentials.json`, `settings.local.json`) are always enforced — you can't accidentally remove them
- After adding to `.gitignore`, run `git rm --cached <file>` in `~/.claude/` to stop tracking an already-tracked file

---

## Safety Features

- **Full status dashboard**: Shows local vs remote comparison, timestamps, ahead/behind count, and lists every file that will change — nothing truncated.
- **Uncommitted change detection**: Detects active sessions and unsaved edits on disk. Shows them before push/pull so you know what's included.
- **Push warning**: Warns if remote has unmerged data from another machine. Asks before overwriting.
- **Pull warning**: Warns if local is newer than remote (stale pull detection). Asks before proceeding.
- **Sessions vs config separation**: Root pull shows session changes and config changes separately. You can choose to sync both, sessions only, or config only.
- **Conflict resolution**: Lists all conflicting files, shows timestamps, asks once — remote wins or local wins entirely. No partial merging.
- **Progress indicators**: Every slow operation shows file-by-file progress so you know the system isn't frozen.
- **Rollback plan**: Shows exactly what commits will be undone and what files will change.
- **Stash protection**: Auto-stashes local changes during pull, restores them after.
- **Credentials excluded**: `.credentials.json` never leaves your machine.
- **Large file backup**: Files >90MB are appended to a growing backup in `session-originals/` before being replaced. The backup accumulates complete session history across all pulls — no duplicates.
- **Push failure rollback**: If a push fails (e.g., GitHub rejects a large file), the commit and tag are automatically rolled back so they don't block future pushes. Previously, orphaned tags pointing to bad commits would cause every subsequent push to fail.
- **Repair artifact exclusion**: Session repair files (`*.jsonl.backup-*`, `*.jsonl.pre-*`, `*.jsonl.minimal`, `*.jsonl.repaired*`, `*.jsonl.branch-repair`) and machine-local blobs (`tool-results/`, `*.meta.json`) are never staged or pushed, even if they exist on disk.
- **Force push confirmation**: Root push asks "Overwrite remote?" when remote has newer data.
- **Per-project isolation**: Push only commits that project's sessions. Pull fetches everything but auto-resolves conflicts outside the project scope by keeping local — other projects, settings, and plugins are never overwritten. The full migration pipeline still runs on all projects to fix paths and timestamps.
- **Claude directory detection**: Auto-finds `~/.claude/`, prompts if not found, lets you enter a custom path.
- **Project folder validation**: Every per-project script verifies the parent folder name matches the expected project name. If the folder was renamed, it checks the git remote as source of truth — if the remote matches, it warns but proceeds; if the remote doesn't match, it stops with clear fix instructions (rename the folder or re-run `new-project`).
- **Workspace structure check**: Warns if project isn't inside the workspace.
- **Branch safety**: Detects `master` branch and informs instead of force-renaming.

---

## Requirements

- Git
- Python 3.8+
- Node.js (for Claude Code CLI and plugin dependencies)
- Claude Code (`npm install -g @anthropic-ai/claude-code`)

---

## License

MIT License - Copyright (c) 2026 Coskun Eren / PITIR TECH

This software is free to use, modify, and distribute under the MIT License. The copyright notice and permission notice must be included in all copies or substantial portions of the software. See [LICENSE](LICENSE) for full terms.

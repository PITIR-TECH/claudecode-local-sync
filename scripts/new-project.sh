#!/bin/bash
# New Project Setup — Self-contained generator for Mac

GREEN='\033[0;32m'
CYAN='\033[0;36m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo ""
echo "══════════════════════════════════════════════════"
echo "  NEW PROJECT SETUP"
echo "══════════════════════════════════════════════════"
echo ""
echo "  This will create a new project folder with all"
echo "  standardized scripts (push, pull, rollback,"
echo "  session push/pull, migration scripts)."
echo ""
echo "  Fully self-contained — works on a fresh Mac."
echo ""
echo "══════════════════════════════════════════════════"
echo ""

# Save original directory for later (before any cd)
ORIG_DIR="$(pwd)"
SCRIPT_DIR_ABS="$(cd "$(dirname "$0")" && pwd)"

# Check git
if ! command -v git &>/dev/null; then
    echo -e "${RED}  [ERROR] git is not installed.${NC}"
    echo "  Install from: https://git-scm.com/download/mac"
    exit 1
fi

# ── Auto-setup CLI session repo (pull from GitHub) ──
CLAUDE_DIR="$HOME/.claude"
if [ -d "$CLAUDE_DIR/.git" ]; then
    echo -e "  ${GREEN}[OK]${NC} CLI session repo already configured."
    echo ""
else
    echo "──────────────────────────────────────────────────"
    echo "  CLI SESSION REPO SETUP"
    echo "──────────────────────────────────────────────────"
    echo ""
    echo "  Pull your CLI sessions from GitHub:"
    echo "  https://github.com/YOUR-ORG/claude-dotfiles"
    echo ""
    read -p "  Pull CLI sessions now? (Y/N): " SETUP_CLI
    if [[ "$SETUP_CLI" =~ ^[Yy]$ ]]; then
        if [ -d "$CLAUDE_DIR" ]; then
            echo "  [INFO] Claude folder exists. Initializing..."
            cd "$CLAUDE_DIR"
            git init >/dev/null 2>&1
            git remote add origin https://github.com/YOUR-ORG/claude-dotfiles.git 2>/dev/null
            git branch -M main >/dev/null 2>&1
            git pull origin main --no-rebase --allow-unrelated-histories --no-edit >/dev/null 2>&1
            if [ $? -ne 0 ]; then
                echo -e "${YELLOW}  [WARNING] Could not pull. Check GitHub auth.${NC}"
            else
                echo -e "${GREEN}  [OK] CLI sessions pulled.${NC}"
                # Run full session sync to fix cross-platform paths
                CLAUDECODE_ROOT="$(cd "$SCRIPT_DIR_ABS/.." && pwd)"
                PY=""
                if command -v python3 &>/dev/null; then PY="python3"
                elif command -v python &>/dev/null; then PY="python"
                fi
                if [ -n "$PY" ] && [ -f "$SCRIPT_DIR_ABS/sync-sessions.py" ]; then
                    echo "  Running session sync..."
                    "$PY" "$SCRIPT_DIR_ABS/sync-sessions.py" pull "$CLAUDECODE_ROOT"
                fi
            fi
            cd "$ORIG_DIR"
        else
            echo "  [INFO] Pulling CLI sessions from GitHub..."
            git clone https://github.com/YOUR-ORG/claude-dotfiles.git "$CLAUDE_DIR" 2>&1
            if [ $? -ne 0 ]; then
                echo -e "${YELLOW}  [WARNING] Clone failed. Check GitHub auth.${NC}"
            else
                echo -e "${GREEN}  [OK] CLI sessions pulled.${NC}"
                # Run full session sync to fix cross-platform paths
                CLAUDECODE_ROOT="$(cd "$SCRIPT_DIR_ABS/.." && pwd)"
                PY=""
                if command -v python3 &>/dev/null; then PY="python3"
                elif command -v python &>/dev/null; then PY="python"
                fi
                if [ -n "$PY" ] && [ -f "$SCRIPT_DIR_ABS/sync-sessions.py" ]; then
                    echo "  Running session sync..."
                    "$PY" "$SCRIPT_DIR_ABS/sync-sessions.py" pull "$CLAUDECODE_ROOT"
                fi
            fi
        fi
    else
        echo "  [SKIP] CLI sessions skipped."
    fi
    echo ""
fi

# ── Ask for GitHub repo URL ──
echo "  Enter the GitHub repository URL:"
echo "  Example: https://github.com/YOUR-ORG/my-project"
echo ""
read -p "  >> " REPO_URL

if [ -z "$REPO_URL" ]; then
    echo -e "${RED}  [ERROR] No URL provided.${NC}"
    exit 1
fi

# Clean URL
REPO_URL="${REPO_URL%.git}"
REPO_URL="${REPO_URL%/}"

# Extract project name
PROJECT_NAME=$(basename "$REPO_URL")

if [ -z "$PROJECT_NAME" ]; then
    echo -e "${RED}  [ERROR] Could not extract project name.${NC}"
    exit 1
fi

# Build display name (title case)
DISPLAY_NAME=$(echo "$PROJECT_NAME" | sed 's/-/ /g' | awk '{for(i=1;i<=NF;i++) $i=toupper(substr($i,1,1)) tolower(substr($i,2))}1')

# Default parent: one folder above the scripts folder (CLAUDECODE root)
DEFAULT_PARENT="$(cd "$(dirname "$0")/.." && pwd)"
PARENT_DIR="$DEFAULT_PARENT"

echo ""
echo "──────────────────────────────────────────────────"
echo "  Repo URL:      $REPO_URL"
echo "  Project name:  $PROJECT_NAME"
echo "  Display name:  $DISPLAY_NAME"
echo "──────────────────────────────────────────────────"
echo ""
echo "  Project will be created at:"
echo "    $PARENT_DIR/$PROJECT_NAME"
echo ""
read -p "  Press Enter to proceed, or type CHANGE to pick a different folder: " DIR_CHOICE

if [[ "$DIR_CHOICE" =~ ^[Cc][Hh][Aa][Nn][Gg][Ee]$ ]]; then
    echo ""
    read -rp "  Enter the parent folder path: " CUSTOM_DIR

    if [ -z "$CUSTOM_DIR" ]; then
        echo -e "${RED}  [ERROR] No path entered. Cancelled.${NC}"
        exit 1
    fi

    # Remove trailing slash
    CUSTOM_DIR="${CUSTOM_DIR%/}"

    # Check if the path exists and is a directory
    if [ ! -d "$CUSTOM_DIR" ]; then
        echo ""
        echo -e "${RED}  [ERROR] Folder does not exist: $CUSTOM_DIR${NC}"
        echo "  Please create it first or check the path."
        exit 1
    fi

    PARENT_DIR="$CUSTOM_DIR"
    echo ""
    echo "  Using: $PARENT_DIR/$PROJECT_NAME"
    echo ""
fi

PROJECT_DIR="$PARENT_DIR/$PROJECT_NAME"

# Confirm creation
echo "──────────────────────────────────────────────────"
echo "  Full path:  $PROJECT_DIR"
echo "──────────────────────────────────────────────────"
echo ""
read -p "  Create this project? (Y/N): " CONFIRM
if [[ ! "$CONFIRM" =~ ^[Yy]$ ]]; then
    echo "  Cancelled."
    exit 0
fi

# Create folder
if [ -d "$PROJECT_DIR" ]; then
    echo -e "${YELLOW}  [WARNING] Folder already exists. Continuing anyway.${NC}"
else
    mkdir -p "$PROJECT_DIR"
    echo "  [OK] Created folder: $PROJECT_NAME"
fi

cd "$PROJECT_DIR"

# Clone or init
if [ ! -d ".git" ]; then
    echo "  [INFO] Checking if remote repo has content..."
    if git ls-remote "$REPO_URL.git" >/dev/null 2>&1; then
        git clone "$REPO_URL.git" "$PROJECT_DIR" 2>&1 || {
            git init
            git remote add origin "$REPO_URL.git"
            git branch -M main
        }
    else
        git init
        git remote add origin "$REPO_URL.git"
        git branch -M main
    fi
    echo ""
fi

# Ensure main branch
CURRENT_BRANCH=$(git branch --show-current 2>/dev/null)
if [ "$CURRENT_BRANCH" != "main" ]; then
    git branch -M main >/dev/null 2>&1
fi

echo "  Generating project files..."

# ── Use Python generator for all scripts (single source of truth) ──
SCRIPT_DIR_SH="$(cd "$(dirname "$0")" && pwd)"
PYTHON_CMD=""
if command -v python3 &>/dev/null; then PYTHON_CMD="python3"
elif command -v python &>/dev/null; then PYTHON_CMD="python"
elif command -v py &>/dev/null; then PYTHON_CMD="py"
fi

if [ -n "$PYTHON_CMD" ] && [ -f "$SCRIPT_DIR_SH/new-project-gen.py" ]; then
    "$PYTHON_CMD" "$SCRIPT_DIR_SH/new-project-gen.py" "$DISPLAY_NAME" "$REPO_URL" "$PROJECT_DIR"
    # Make .sh files executable
    chmod +x "$PROJECT_DIR/scripts/"*.sh 2>/dev/null
else
    echo "  [ERROR] Python or new-project-gen.py not found. Cannot generate scripts."
    echo "  Install Python: https://www.python.org/downloads/"
fi


echo ""
echo -e "${GREEN}══════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  SUCCESS! Project \"$PROJECT_NAME\" created${NC}"
echo -e "${GREEN}══════════════════════════════════════════════════${NC}"
echo ""
echo "  Folder:    $PROJECT_DIR"
echo "  Repo:      $REPO_URL"
echo "  Branch:    main"
echo ""
echo "  Files created (in scripts/):"
echo "    push.sh               - Push code + CLI sessions"
echo "    pull.sh               - Pull code + CLI sessions"
echo "    rollback.sh           - Rollback to previous version"
echo "    claude-launch.bat     - Interactive launcher TUI"
echo ""
echo "  Global scripts (in CLAUDECODE/scripts/):"
# Check if sessions need pulling
CLAUDE_DIR_NP="${HOME}/.claude"
if [ -f "$SCRIPT_DIR_SH/.claude-dir" ]; then
    CLAUDE_DIR_NP="$(cat "$SCRIPT_DIR_SH/.claude-dir" | tr -d '\r\n')"
fi

if [ -d "$CLAUDE_DIR_NP/.git" ]; then
    # Repo exists — check if behind remote
    SESS_BEHIND=$(cd "$CLAUDE_DIR_NP" && git fetch origin main >/dev/null 2>&1 && git rev-list --count HEAD..origin/main 2>/dev/null || echo 0)
    if [ "$SESS_BEHIND" = "0" ]; then
        echo ""
        echo -e "  ${GREEN}[OK]${NC} Sessions already up to date."
    else
        echo ""
        echo "  [INFO] $SESS_BEHIND new session sync(s) available from another machine."
        read -p "  Pull latest sessions? (Y/N): " PULL_SESSIONS
        if [[ "$PULL_SESSIONS" =~ ^[Yy]$ ]]; then
            echo ""
            REMOTE_SLUG=$(echo "$REPO_URL" | sed 's|https://github.com/||' | tr '[:upper:]' '[:lower:]')
            if [ -n "$PYTHON_CMD" ] && [ -f "$SCRIPT_DIR_SH/sync-sessions.py" ]; then
                PARENT_DIR_SH="$(cd "$SCRIPT_DIR_SH/.." && pwd)"
                "$PYTHON_CMD" "$SCRIPT_DIR_SH/sync-sessions.py" pull "$PARENT_DIR_SH" --project "$REMOTE_SLUG"
            else
                echo "  [SKIP] sync-sessions.py or Python not found."
            fi
        fi
    fi
else
    # No repo — first time setup
    echo ""
    read -p "  Pull sessions for this project from another machine? (Y/N): " PULL_SESSIONS
    if [[ "$PULL_SESSIONS" =~ ^[Yy]$ ]]; then
        echo ""
        REMOTE_SLUG=$(echo "$REPO_URL" | sed 's|https://github.com/||' | tr '[:upper:]' '[:lower:]')
        if [ -n "$PYTHON_CMD" ] && [ -f "$SCRIPT_DIR_SH/sync-sessions.py" ]; then
            PARENT_DIR_SH="$(cd "$SCRIPT_DIR_SH/.." && pwd)"
            "$PYTHON_CMD" "$SCRIPT_DIR_SH/sync-sessions.py" pull "$PARENT_DIR_SH" --project "$REMOTE_SLUG"
        else
            echo "  [SKIP] sync-sessions.py or Python not found."
        fi
    fi
fi

echo ""
echo "  Next steps:"
echo "    1. Open the folder in Claude Code"
echo "    2. Start working"
echo "    3. When done, run ./scripts/push.sh"
echo ""
read -p "  Press Enter to close..." _

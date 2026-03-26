"""Generate per-project push/pull/rollback scripts (.bat and .sh)."""
import sys, os

if len(sys.argv) < 4:
    print("Usage: new-project-gen.py <display_name> <repo_url> <project_dir>")
    sys.exit(1)

display_name = sys.argv[1]
repo_url = sys.argv[2]
project_dir = sys.argv[3]
scripts_dir = os.path.join(project_dir, 'scripts')
os.makedirs(scripts_dir, exist_ok=True)

# Extract org/repo slug for per-project session sync
_clean_url = repo_url.rstrip('/').removesuffix('.git')
remote_slug = _clean_url.replace("https://github.com/", "").lower()
project_name = os.path.basename(_clean_url)

# ══════════════════════════════════════════════════════════
#  push.bat
# ══════════════════════════════════════════════════════════
push_bat = r"""@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion
title {display} — Push to GitHub
color 0A

echo ══════════════════════════════════════════════════
echo   {display} — Push to GitHub
echo ══════════════════════════════════════════════════
echo.

:: ── Sync mode selection ──
echo  What would you like to push?
echo.
echo    1) Both project code + sessions  (default)
echo    2) Project code only
echo    3) Sessions only
echo.
set /p SYNC_MODE="  Choice [1]: "
if "!SYNC_MODE!"=="" set "SYNC_MODE=1"

set "PUSH_CODE=1"
set "PUSH_SESSIONS=1"
if "!SYNC_MODE!"=="2" set "PUSH_SESSIONS=0"
if "!SYNC_MODE!"=="3" set "PUSH_CODE=0"
echo.

where git >nul 2>&1
if errorlevel 1 (
    color 0C
    echo  [ERROR] git is not installed or not in PATH.
    pause
    exit /b 1
)

:: ── Verify project directory exists ──
if not exist "%~dp0.." (
    color 0C
    echo  [ERROR] Project directory not found.
    echo  The project folder may have been moved or deleted.
    echo  To fix: run new-project.bat to recreate the project.
    pause
    exit /b 1
)
cd /d "%~dp0.."

:: ── Verify project folder ──
set "EXPECTED_FOLDER={project_name}"
for %%I in ("!CD!") do set "ACTUAL_FOLDER=%%~nxI"
if /i not "!ACTUAL_FOLDER!"=="!EXPECTED_FOLDER!" (
    color 0E
    echo  [WARNING] Folder name mismatch
    echo    Expected: !EXPECTED_FOLDER!
    echo    Actual:   !ACTUAL_FOLDER!
    echo.
    set "REMOTE_MATCH=0"
    if exist ".git" (
        for /f "tokens=*" %%r in ('git remote get-url origin 2^>nul') do (
            set "CHECK_REMOTE=%%r"
            if /i "!CHECK_REMOTE!"=="{repo}.git" set "REMOTE_MATCH=1"
            if /i "!CHECK_REMOTE!"=="{repo}" set "REMOTE_MATCH=1"
        )
    )
    if "!REMOTE_MATCH!"=="1" (
        echo  Git remote matches — correct project, folder was renamed.
        echo  Continuing...
        echo.
    ) else (
        color 0C
        echo  [ERROR] This script was generated for: {repo}
        echo  But this folder does not appear to be that project.
        echo.
        echo  To fix:
        echo    - Rename this folder to "!EXPECTED_FOLDER!"
        echo    - Or re-run new-project to generate correct scripts
        echo.
        pause
        exit /b 1
    )
)

set "REPO_URL={repo}"

if not exist ".git" (
    echo  [SETUP] No git repo found. Initializing...
    git init
    git remote add origin "!REPO_URL!.git"
    echo  Git initialized with remote: !REPO_URL!
    echo.
)

for /f "tokens=*" %%b in ('git branch --show-current 2^>nul') do set "CURRENT_BRANCH=%%b"
if not "!CURRENT_BRANCH!"=="main" (
    if not "!CURRENT_BRANCH!"=="master" (
        git branch -M main >nul 2>&1
        echo  [SETUP] Switched to main branch.
        echo.
    ) else (
        echo  [INFO] Using master branch (rename to main with: git branch -M main^)
        echo.
    )
)

if "!PUSH_CODE!"=="0" goto :sync_sessions

:: ── Project code status ──
git fetch origin main --tags >nul 2>&1
set "AHEAD=0"
set "BEHIND=0"
for /f %%n in ('git rev-list --count origin/main..HEAD 2^>nul') do set "AHEAD=%%n"
for /f %%n in ('git rev-list --count HEAD..origin/main 2^>nul') do set "BEHIND=%%n"
for /f "tokens=*" %%c in ('git log -1 --format^="%%h  %%ad  %%s" --date^=short 2^>nul') do set "LOCAL_COMMIT=%%c"
for /f "tokens=*" %%c in ('git log -1 --format^="%%h  %%ad  %%s" --date^=short origin/main 2^>nul') do set "REMOTE_COMMIT=%%c"

echo  PROJECT CODE STATUS
echo  ──────────────────────────────────────────────────
echo    Local:  !LOCAL_COMMIT!
echo    Remote: !REMOTE_COMMIT!
echo    Ahead: !AHEAD! commit(s)  Behind: !BEHIND! commit(s)
echo  ──────────────────────────────────────────────────
echo.

if !BEHIND! GTR 0 (
    color 0E
    echo  [WARNING] Remote has !BEHIND! commit(s^) you haven't pulled.
    echo  Consider running pull.bat first to merge.
    echo.
    set /p PUSH_CONFIRM="  Continue with push anyway? (Y/N): "
    if /i not "!PUSH_CONFIRM!"=="Y" ( echo  Cancelled. & endlocal & pause & exit /b 0 )
    echo.
)

echo  Changed files:
echo ──────────────────────────────────────────────────
git status --short
echo.
echo ──────────────────────────────────────────────────
echo.

:: Check if there are any code changes
for /f "tokens=*" %%x in ('git status --porcelain') do goto :has_changes
echo  [INFO] No project code changes to push.
echo  Session sync will still run.
echo.
goto :sync_sessions

:has_changes
echo  What did you change? (short description)
set /p MSG="  >> "
if "!MSG!"=="" set "MSG=Update"

:: Get next version tag
set LAST_NUM=0
for /f "tokens=*" %%t in ('git tag -l "v*" --sort^=-version:refname 2^>nul') do (
    if !LAST_NUM!==0 (
        set "TVAL=%%t"
        set "TVAL=!TVAL:v=!"
        set /a "TCHECK=!TVAL!" 2>nul
        if !TCHECK! GTR 0 (
            set LAST_NUM=!TCHECK!
        )
    )
)
set /a NEXT_NUM=!LAST_NUM!+1
set "NEW_TAG=v!NEXT_NUM!"

echo.
echo ──────────────────────────────────────────────────
echo   Version:  !NEW_TAG!  (previous: v!LAST_NUM!)
echo   Message:  !MSG!
echo   Date:     %date% %time:~0,5%
echo ──────────────────────────────────────────────────
echo.
set /p CONFIRM="  Push to GitHub? (Y/N): "
if /i not "!CONFIRM!"=="Y" ( echo  Cancelled. & endlocal & pause & exit /b 0 )

echo.
echo  Pushing project code...
git add -A
git commit -m "[!NEW_TAG!] !MSG!"
if errorlevel 1 ( color 0C & echo  [ERROR] Commit failed. & pause & exit /b 1 )
git tag -a "!NEW_TAG!" -m "!MSG!"
git push origin main --tags --force 2>&1
if errorlevel 1 (
    git push -u origin main --tags --force 2>&1
    if errorlevel 1 ( color 0C & echo  [ERROR] Push failed. & pause & exit /b 1 )
)

echo.
color 0A
echo  SUCCESS^^! Project pushed as !NEW_TAG!
echo  Repo: !REPO_URL!
echo.

:sync_sessions
if "!PUSH_SESSIONS!"=="0" goto :done
:: ── Push CLI Sessions (via sync-sessions.py) ──
echo  Syncing CLI sessions to GitHub...
echo ──────────────────────────────────────────────────
set "SYNC_SCRIPT=%~dp0..\..\scripts\sync-sessions.py"
if not exist "!SYNC_SCRIPT!" set "SYNC_SCRIPT=%~dp0..\scripts\sync-sessions.py"
if exist "!SYNC_SCRIPT!" (
    set "PY_EXE="
    for /f "tokens=*" %%P in ('where py 2^>nul') do if not defined PY_EXE set "PY_EXE=%%P"
    if not defined PY_EXE for /f "tokens=*" %%P in ('where python 2^>nul') do if not defined PY_EXE set "PY_EXE=%%P"
    if defined PY_EXE (
        pushd "%~dp0..\..\" >nul
        set "PROJ_PARENT=!CD!"
        popd >nul
        "!PY_EXE!" "!SYNC_SCRIPT!" push "!PROJ_PARENT!" --project "{remote_slug}"
    ) else (
        echo  [SKIP] Python not found. Install Python to sync sessions.
    )
) else (
    echo  [WARNING] sync-sessions.py not found.
    echo  This project may not be inside the workspace folder.
    echo  Session sync requires: workspace\scripts\sync-sessions.py
)
echo ──────────────────────────────────────────────────

:done
cd /d "%~dp0.."
echo.

endlocal
pause
""".strip()

# ══════════════════════════════════════════════════════════
#  pull.bat
# ══════════════════════════════════════════════════════════
pull_bat = r"""@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion
title {display} — Pull from GitHub
color 0B

echo ══════════════════════════════════════════════════
echo   {display} — Pull Latest from GitHub
echo ══════════════════════════════════════════════════
echo.

:: ── Sync mode selection ──
echo  What would you like to pull?
echo.
echo    1) Both project code + sessions  (default)
echo    2) Project code only
echo    3) Sessions only
echo.
set /p SYNC_MODE="  Choice [1]: "
if "!SYNC_MODE!"=="" set "SYNC_MODE=1"

set "PULL_CODE=1"
set "PULL_SESSIONS=1"
if "!SYNC_MODE!"=="2" set "PULL_SESSIONS=0"
if "!SYNC_MODE!"=="3" set "PULL_CODE=0"
echo.

where git >nul 2>&1
if errorlevel 1 (
    color 0C
    echo  [ERROR] git is not installed or not in PATH.
    pause
    exit /b 1
)

:: ── Verify project directory exists ──
if not exist "%~dp0.." (
    color 0C
    echo  [ERROR] Project directory not found.
    echo  The project folder may have been moved or deleted.
    echo  To fix: run new-project.bat to recreate the project.
    pause
    exit /b 1
)
cd /d "%~dp0.."

:: ── Verify project folder ──
set "EXPECTED_FOLDER={project_name}"
for %%I in ("!CD!") do set "ACTUAL_FOLDER=%%~nxI"
if /i not "!ACTUAL_FOLDER!"=="!EXPECTED_FOLDER!" (
    color 0E
    echo  [WARNING] Folder name mismatch
    echo    Expected: !EXPECTED_FOLDER!
    echo    Actual:   !ACTUAL_FOLDER!
    echo.
    set "REMOTE_MATCH=0"
    if exist ".git" (
        for /f "tokens=*" %%r in ('git remote get-url origin 2^>nul') do (
            set "CHECK_REMOTE=%%r"
            if /i "!CHECK_REMOTE!"=="{repo}.git" set "REMOTE_MATCH=1"
            if /i "!CHECK_REMOTE!"=="{repo}" set "REMOTE_MATCH=1"
        )
    )
    if "!REMOTE_MATCH!"=="1" (
        echo  Git remote matches — correct project, folder was renamed.
        echo  Continuing...
        echo.
    ) else (
        color 0C
        echo  [ERROR] This script was generated for: {repo}
        echo  But this folder does not appear to be that project.
        echo.
        echo  To fix:
        echo    - Rename this folder to "!EXPECTED_FOLDER!"
        echo    - Or re-run new-project to generate correct scripts
        echo.
        pause
        exit /b 1
    )
)

if not exist ".git" (
    color 0C
    echo  [ERROR] No git repo found. Run push.bat first.
    pause
    exit /b 1
)

if "!PULL_CODE!"=="0" goto :pull_sessions

:: ── Project code status ──
git fetch origin main --tags >nul 2>&1
set "AHEAD=0"
set "BEHIND=0"
for /f %%n in ('git rev-list --count origin/main..HEAD 2^>nul') do set "AHEAD=%%n"
for /f %%n in ('git rev-list --count HEAD..origin/main 2^>nul') do set "BEHIND=%%n"
for /f "tokens=*" %%c in ('git log -1 --format^="%%h  %%ad  %%s" --date^=short 2^>nul') do set "LOCAL_COMMIT=%%c"
for /f "tokens=*" %%c in ('git log -1 --format^="%%h  %%ad  %%s" --date^=short origin/main 2^>nul') do set "REMOTE_COMMIT=%%c"

echo  PROJECT CODE STATUS
echo  ──────────────────────────────────────────────────
echo    Local:  !LOCAL_COMMIT!
echo    Remote: !REMOTE_COMMIT!
echo    Ahead: !AHEAD! commit(s)  Behind: !BEHIND! commit(s)
echo  ──────────────────────────────────────────────────
echo.

if !BEHIND!==0 if !AHEAD!==0 (
    echo  [INFO] Already up to date. Pulling anyway to ensure consistency.
    echo.
)
if !AHEAD! GTR 0 (
    echo  [INFO] You have !AHEAD! local commit(s^) not yet pushed.
    echo  Pulling will merge remote changes with your local commits.
    echo.
)

:: Check for unsaved changes
set "STASHED=0"
for /f "tokens=*" %%x in ('git status --porcelain') do goto :has_changes
goto :do_pull

:has_changes
color 0E
echo  [WARNING] Unsaved local changes:
git status --short
echo.
set /p CONFIRM="  Continue? (Y/N): "
if /i not "!CONFIRM!"=="Y" ( echo  Cancelled. & endlocal & pause & exit /b 0 )
git stash >nul 2>&1
set "STASHED=1"
echo.

:do_pull
echo  Pulling...
git pull origin main --tags 2>&1
if errorlevel 1 (
    color 0C
    echo  [ERROR] Pull failed.
    pause
    exit /b 1
)
if "!STASHED!"=="1" (
    echo  Restoring local changes...
    git stash pop >nul 2>&1
    if errorlevel 1 echo  [WARNING] Could not restore stash. Run 'git stash pop' manually.
)

echo.
git log --oneline --decorate -10
echo.
color 0A
echo  DONE^^! You have the latest version.
echo.

:pull_sessions
if "!PULL_SESSIONS!"=="0" goto :done
:: ── Pull CLI Sessions (via sync-sessions.py) ──
echo  Syncing CLI sessions from GitHub...
echo ──────────────────────────────────────────────────
set "SYNC_SCRIPT=%~dp0..\..\scripts\sync-sessions.py"
if not exist "!SYNC_SCRIPT!" set "SYNC_SCRIPT=%~dp0..\scripts\sync-sessions.py"
if exist "!SYNC_SCRIPT!" (
    set "PY_EXE="
    for /f "tokens=*" %%P in ('where py 2^>nul') do if not defined PY_EXE set "PY_EXE=%%P"
    if not defined PY_EXE for /f "tokens=*" %%P in ('where python 2^>nul') do if not defined PY_EXE set "PY_EXE=%%P"
    if defined PY_EXE (
        pushd "%~dp0..\..\" >nul
        set "PROJ_PARENT=!CD!"
        popd >nul
        "!PY_EXE!" "!SYNC_SCRIPT!" pull "!PROJ_PARENT!" --project "{remote_slug}"
    ) else (
        echo  [SKIP] Python not found. Install Python to sync sessions.
    )
) else (
    echo  [WARNING] sync-sessions.py not found.
    echo  This project may not be inside the workspace folder.
    echo  Session sync requires: workspace\scripts\sync-sessions.py
)
echo ──────────────────────────────────────────────────

:done
cd /d "%~dp0.."
echo.

endlocal
pause
""".strip()

# ══════════════════════════════════════════════════════════
#  rollback.bat
# ══════════════════════════════════════════════════════════
rollback_bat = r"""@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion
title {display} — Rollback
color 0E

echo ══════════════════════════════════════════════════════════════════════════════
echo   {display} — Rollback to Previous Version
echo ══════════════════════════════════════════════════════════════════════════════
echo.

where git >nul 2>&1
if errorlevel 1 (
    color 0C
    echo  [ERROR] git is not installed or not in PATH.
    pause
    exit /b 1
)

cd /d "%~dp0.."

:: ── Verify project folder ──
set "EXPECTED_FOLDER={project_name}"
for %%I in ("!CD!") do set "ACTUAL_FOLDER=%%~nxI"
if /i not "!ACTUAL_FOLDER!"=="!EXPECTED_FOLDER!" (
    color 0E
    echo  [WARNING] Folder name mismatch
    echo    Expected: !EXPECTED_FOLDER!
    echo    Actual:   !ACTUAL_FOLDER!
    echo.
    set "REMOTE_MATCH=0"
    if exist ".git" (
        for /f "tokens=*" %%r in ('git remote get-url origin 2^>nul') do (
            set "CHECK_REMOTE=%%r"
            if /i "!CHECK_REMOTE!"=="{repo}.git" set "REMOTE_MATCH=1"
            if /i "!CHECK_REMOTE!"=="{repo}" set "REMOTE_MATCH=1"
        )
    )
    if "!REMOTE_MATCH!"=="1" (
        echo  Git remote matches — correct project, folder was renamed.
        echo  Continuing...
        echo.
    ) else (
        color 0C
        echo  [ERROR] This script was generated for: {repo}
        echo  But this folder does not appear to be that project.
        echo.
        echo  To fix:
        echo    - Rename this folder to "!EXPECTED_FOLDER!"
        echo    - Or re-run new-project to generate correct scripts
        echo.
        pause
        exit /b 1
    )
)

:: ── Check remote status ──
git fetch origin main --tags >nul 2>&1
set "BEHIND=0"
for /f %%n in ('git rev-list --count HEAD..origin/main 2^>nul') do set "BEHIND=%%n"
if !BEHIND! GTR 0 (
    echo  [WARNING] Remote has !BEHIND! commit(s^) you haven't pulled.
    echo  Rolling back without pulling first means you'll lose those remote changes.
    echo  Consider running pull.bat first.
    echo.
)

echo  YOU ARE HERE:
echo ──────────────────────────────────────────────────────────────────────────────
for /f "tokens=*" %%c in ('git log -1 --format^="  %%h  %%ad  %%s" --date^=short') do echo %%c
echo ──────────────────────────────────────────────────────────────────────────────
echo.

echo  VERSION HISTORY (most recent first):
echo ══════════════════════════════════════════════════════════════════════════════
echo.
echo  TAG        DATE         FILES   MESSAGE
echo  ───────    ──────────   ─────   ─────────────────────────────────────────
echo.

for /f "tokens=*" %%t in ('git tag --sort^=-version:refname -l "v*"') do (
    set "TAG=%%t"
    for /f "tokens=*" %%d in ('git log -1 --format^="%%ad" --date^=short "%%t" 2^>nul') do set "TDATE=%%d"
    for /f "tokens=*" %%m in ('git tag -l --format^="%%(contents:subject)" "%%t" 2^>nul') do set "TMSG=%%m"
    if "!TMSG!"=="" for /f "tokens=*" %%m in ('git log -1 --format^="%%s" "%%t" 2^>nul') do set "TMSG=%%m"
    set "FCOUNT=?"
    for /f %%n in ('git diff --name-only "%%t~1" "%%t" 2^>nul ^| find /c /v ""') do set "FCOUNT=%%n"
    set "PADTAG=!TAG!          "
    set "PADTAG=!PADTAG:~0,10!"
    set "PADFCOUNT=  !FCOUNT!  "
    set "PADFCOUNT=!PADFCOUNT:~0,7!"
    echo   !PADTAG! !TDATE!   !PADFCOUNT! !TMSG!
)

echo.
echo ══════════════════════════════════════════════════════════════════════════════
echo.
echo  FULL COMMIT LOG (last 15):
echo ──────────────────────────────────────────────────────────────────────────────
git log --format="  %%h  %%ad  [%%D]  %%s" --date=short -15
echo ──────────────────────────────────────────────────────────────────────────────
echo.

echo  Enter a version tag (e.g. v3) or a commit hash (e.g. 5d8c50a)
echo  Type "quit" to cancel.
echo.
set /p TARGET="  Rollback to: "
if /i "!TARGET!"=="quit" ( echo  Cancelled. & pause & exit /b 0 )
if "!TARGET!"=="" ( echo  Cancelled. & pause & exit /b 0 )

git rev-parse "!TARGET!" >nul 2>&1
if errorlevel 1 (
    color 0C
    echo  [ERROR] Version "!TARGET!" not found.
    pause
    exit /b 1
)

echo.
echo ══════════════════════════════════════════════════════════════════════════════
echo  TARGET VERSION: !TARGET!
echo ══════════════════════════════════════════════════════════════════════════════
echo.
git log -1 --format="    Hash:    %%H%%n    Date:    %%ad%%n    Author:  %%an%%n    Message: %%s" --date=format:"%%Y-%%m-%%d %%H:%%M" "!TARGET!"
echo.

echo  COMMITS THAT WILL BE UNDONE:
echo ──────────────────────────────────────────────────────────────────────────────
set UNDO_COUNT=0
for /f %%n in ('git rev-list "!TARGET!..HEAD" --count 2^>nul') do set UNDO_COUNT=%%n
if !UNDO_COUNT!==0 (
    echo    (none — you are already at this version)
    pause
    exit /b 0
)
git log --format="    %%h  %%ad  %%s" --date=short "!TARGET!..HEAD"
echo ──────────────────────────────────────────────────────────────────────────────
echo   Total: !UNDO_COUNT! commit(s) will be reverted
echo.

echo  FILES THAT WILL CHANGE:
echo ──────────────────────────────────────────────────────────────────────────────
git diff --stat "!TARGET!" HEAD
echo ──────────────────────────────────────────────────────────────────────────────
echo.
echo  A NEW commit will be created — your history is NEVER deleted.
echo.
set /p CONFIRM="  Proceed with rollback to !TARGET!? (Y/N): "
if /i not "!CONFIRM!"=="Y" ( echo  Cancelled. & pause & exit /b 0 )

echo.
echo  Rolling back...
git checkout "!TARGET!" -- .
if errorlevel 1 ( color 0C & echo  [ERROR] Rollback failed. & pause & exit /b 1 )

git add -A
git commit -m "[ROLLBACK] Reverted to !TARGET!"
if errorlevel 1 ( color 0C & echo  [ERROR] Commit failed. & pause & exit /b 1 )

echo.
set /p PUSHIT="  Push rollback to GitHub? (Y/N): "
if /i "!PUSHIT!"=="Y" (
    git push origin main --force
    if errorlevel 1 ( color 0C & echo  [ERROR] Push failed. Rollback saved locally. & pause & exit /b 1 )
)

echo.
color 0A
echo ══════════════════════════════════════════════════════════════════════════════
echo  SUCCESS^^! Rolled back to !TARGET!
echo ══════════════════════════════════════════════════════════════════════════════
echo.
echo  Your code is now at version !TARGET!. History preserved.
echo.

endlocal
pause
""".strip()

# ══════════════════════════════════════════════════════════
#  push.sh
# ══════════════════════════════════════════════════════════
push_sh = r"""#!/bin/bash
# {display} — Push to GitHub

GREEN='\033[0;32m'
CYAN='\033[0;36m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

DISPLAY_NAME="{display}"
REPO_URL="{repo}"

echo ""
echo "══════════════════════════════════════════════════"
echo "  $DISPLAY_NAME — Push to GitHub"
echo "══════════════════════════════════════════════════"
echo ""

# ── Sync mode selection ──
echo "  What would you like to push?"
echo ""
echo "    1) Both project code + sessions  (default)"
echo "    2) Project code only"
echo "    3) Sessions only"
echo ""
read -p "  Choice [1]: " SYNC_MODE
[ -z "$SYNC_MODE" ] && SYNC_MODE="1"

PUSH_CODE=1
PUSH_SESSIONS=1
case "$SYNC_MODE" in
    2) PUSH_SESSIONS=0 ;;
    3) PUSH_CODE=0 ;;
esac

if ! command -v git &>/dev/null; then
    echo -e "${{RED}}  [ERROR] git is not installed.${{NC}}"
    read -p "  Press Enter to close..." _
    exit 1
fi

# ── Verify project directory exists ──
PROJ_DIR="$(cd "$(dirname "$0")/.." 2>/dev/null && pwd)"
if [ -z "$PROJ_DIR" ] || [ ! -d "$PROJ_DIR" ]; then
    echo -e "${{RED}}  [ERROR] Project directory not found.${{NC}}"
    echo "  The project folder may have been moved or deleted."
    echo "  Expected: $(dirname "$0")/.."
    echo ""
    echo "  To fix: run new-project.sh to recreate the project."
    read -p "  Press Enter to close..." _
    exit 1
fi
cd "$PROJ_DIR"

# ── Verify project folder ──
EXPECTED_FOLDER="{project_name}"
ACTUAL_FOLDER="$(basename "$PROJ_DIR")"
if [ "$ACTUAL_FOLDER" != "$EXPECTED_FOLDER" ]; then
    echo -e "${{YELLOW}}  [WARNING] Folder name mismatch${{NC}}"
    echo "    Expected: $EXPECTED_FOLDER"
    echo "    Actual:   $ACTUAL_FOLDER"
    echo ""
    ACTUAL_REMOTE=$(git remote get-url origin 2>/dev/null)
    if [ "$ACTUAL_REMOTE" = "{repo}.git" ] || [ "$ACTUAL_REMOTE" = "{repo}" ]; then
        echo "  Git remote matches — correct project, folder was renamed."
        echo "  Continuing..."
        echo ""
    else
        echo -e "${{RED}}  [ERROR] This script was generated for: {repo}${{NC}}"
        echo "  But this folder does not appear to be that project."
        echo ""
        echo "  To fix:"
        echo "    - Rename this folder to \"$EXPECTED_FOLDER\""
        echo "    - Or re-run new-project to generate correct scripts"
        read -p "  Press Enter to close..." _
        exit 1
    fi
fi

if [ ! -d ".git" ]; then
    echo -e "${{YELLOW}}  [SETUP] No git repo found. Initializing...${{NC}}"
    git init
    git remote add origin "${{REPO_URL}}.git"
    echo "  Git initialized with remote: $REPO_URL"
    echo ""
fi

CURRENT_BRANCH=$(git branch --show-current 2>/dev/null)
if [ "$CURRENT_BRANCH" != "main" ]; then
    if [ "$CURRENT_BRANCH" = "master" ]; then
        echo "  [INFO] Using master branch (rename to main with: git branch -M main)"
    else
        git branch -M main >/dev/null 2>&1
        echo "  [SETUP] Switched to main branch."
    fi
fi

# ── Push project code ──
if [ $PUSH_CODE -eq 1 ]; then
    # ── Project code status ──
    git fetch origin main --tags >/dev/null 2>&1
    AHEAD=$(git rev-list --count origin/main..HEAD 2>/dev/null || echo 0)
    BEHIND=$(git rev-list --count HEAD..origin/main 2>/dev/null || echo 0)
    LOCAL_COMMIT=$(git log -1 --format="%h  %ad  %s" --date=format:"%Y-%m-%d %H:%M" 2>/dev/null)
    REMOTE_COMMIT=$(git log -1 --format="%h  %ad  %s" --date=format:"%Y-%m-%d %H:%M" origin/main 2>/dev/null)

    echo "  ┌─────────────────────────────────────────────────┐"
    echo "  │  PROJECT CODE STATUS                            │"
    echo "  ├─────────────────────────────────────────────────┤"
    echo "  │  Local:  $LOCAL_COMMIT"
    echo "  │  Remote: $REMOTE_COMMIT"
    echo "  │  Ahead: $AHEAD commit(s)  Behind: $BEHIND commit(s)"
    echo "  └─────────────────────────────────────────────────┘"
    echo ""

    if [ "$BEHIND" -gt 0 ] 2>/dev/null; then
        echo -e "${{YELLOW}}  [WARNING] Remote has $BEHIND commit(s) you haven't pulled.${{NC}}"
        echo "  Pushing will not include those changes."
        echo "  Consider running pull.sh first to merge."
        echo ""
        read -p "  Continue with push anyway? (Y/N): " PUSH_CONFIRM
        if [[ ! "$PUSH_CONFIRM" =~ ^[Yy]$ ]]; then
            echo "  Cancelled."
            read -p "  Press Enter to close..." _
            exit 0
        fi
        echo ""
    fi

    echo "  Changed files:"
    echo "──────────────────────────────────────────────────"
    git status --short
    echo "──────────────────────────────────────────────────"
    echo ""

    if [ -z "$(git status --porcelain)" ]; then
        echo -e "${{YELLOW}}  [INFO] No project code changes to push.${{NC}}"
        echo ""
    else
        read -p "  What did you change? >> " MSG
        if [ -z "$MSG" ]; then MSG="Update"; fi

        LAST_NUM=0
        for t in $(git tag -l "v*" --sort=-version:refname 2>/dev/null); do
            NUM="${{t#v}}"
            if [[ "$NUM" =~ ^[0-9]+$ ]] && [ "$NUM" -gt 0 ] 2>/dev/null; then
                LAST_NUM=$NUM; break
            fi
        done
        NEXT_NUM=$((LAST_NUM + 1))
        NEW_TAG="v${{NEXT_NUM}}"

        echo ""
        echo "──────────────────────────────────────────────────"
        echo "  Version:  $NEW_TAG  (previous: v$LAST_NUM)"
        echo "  Message:  $MSG"
        echo "  Date:     $(date '+%Y-%m-%d %H:%M')"
        echo "──────────────────────────────────────────────────"
        echo ""
        read -p "  Push to GitHub? (Y/N): " CONFIRM
        if [[ ! "$CONFIRM" =~ ^[Yy]$ ]]; then echo "  Cancelled."; read -p "  Press Enter to close..." _; exit 0; fi

        echo "  Pushing project code..."
        git add -A
        git commit -m "[$NEW_TAG] $MSG" || {{ echo -e "${{RED}}  [ERROR] Commit failed.${{NC}}"; read -p "  Press Enter to close..." _; exit 1; }}
        git tag -a "$NEW_TAG" -m "$MSG"
        git push origin main --tags --force 2>&1 || git push -u origin main --tags --force 2>&1 || {{ echo -e "${{RED}}  [ERROR] Push failed.${{NC}}"; read -p "  Press Enter to close..." _; exit 1; }}

        echo ""
        echo -e "${{GREEN}}  SUCCESS! Project pushed as $NEW_TAG${{NC}}"
        echo "  Repo: $REPO_URL"
        echo ""
    fi
fi

# ── Push CLI Sessions (via sync-sessions.py) ──
if [ $PUSH_SESSIONS -eq 1 ]; then
    echo "  Syncing CLI sessions to GitHub..."
    echo "──────────────────────────────────────────────────"
    _SDIR="$(cd "$(dirname "$0")" && pwd)"
    SYNC_SCRIPT="$_SDIR/../../scripts/sync-sessions.py"
    [ ! -f "$SYNC_SCRIPT" ] && SYNC_SCRIPT="$_SDIR/../scripts/sync-sessions.py"
    if [ -f "$SYNC_SCRIPT" ]; then
        PROJ_PARENT="$(cd "$_SDIR/.." && cd .. && pwd)"
        if command -v python3 &>/dev/null; then python3 "$SYNC_SCRIPT" push "$PROJ_PARENT" --project "{remote_slug}"
        elif command -v python &>/dev/null; then python "$SYNC_SCRIPT" push "$PROJ_PARENT" --project "{remote_slug}"
        elif command -v py &>/dev/null; then py "$SYNC_SCRIPT" push "$PROJ_PARENT" --project "{remote_slug}"
        else echo -e "${{YELLOW}}  [SKIP] Python not found. Install Python to sync sessions.${{NC}}"; fi
    else
        echo -e "${{YELLOW}}  [WARNING] sync-sessions.py not found.${{NC}}"
        echo "  This project may not be inside the workspace folder."
        echo "  Session sync requires: workspace/scripts/sync-sessions.py"
    fi
    echo "──────────────────────────────────────────────────"
fi

cd "$(dirname "$0")/.."
echo ""
read -p "  Press Enter to close..." _
""".strip()

# ══════════════════════════════════════════════════════════
#  pull.sh
# ══════════════════════════════════════════════════════════
pull_sh = r"""#!/bin/bash
# {display} — Pull from GitHub

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

DISPLAY_NAME="{display}"

echo ""
echo "══════════════════════════════════════════════════"
echo "  $DISPLAY_NAME — Pull Latest from GitHub"
echo "══════════════════════════════════════════════════"
echo ""

# ── Sync mode selection ──
echo "  What would you like to pull?"
echo ""
echo "    1) Both project code + sessions  (default)"
echo "    2) Project code only"
echo "    3) Sessions only"
echo ""
read -p "  Choice [1]: " SYNC_MODE
[ -z "$SYNC_MODE" ] && SYNC_MODE="1"

PULL_CODE=1
PULL_SESSIONS=1
case "$SYNC_MODE" in
    2) PULL_SESSIONS=0 ;;
    3) PULL_CODE=0 ;;
esac

if ! command -v git &>/dev/null; then echo -e "${{RED}}  [ERROR] git not installed.${{NC}}"; read -p "  Press Enter to close..." _; exit 1; fi

# ── Verify project directory exists ──
PROJ_DIR="$(cd "$(dirname "$0")/.." 2>/dev/null && pwd)"
if [ -z "$PROJ_DIR" ] || [ ! -d "$PROJ_DIR" ]; then
    echo -e "${{RED}}  [ERROR] Project directory not found.${{NC}}"
    echo "  The project folder may have been moved or deleted."
    echo "  To fix: run new-project.sh to recreate the project."
    read -p "  Press Enter to close..." _
    exit 1
fi
cd "$PROJ_DIR"

# ── Verify project folder ──
EXPECTED_FOLDER="{project_name}"
ACTUAL_FOLDER="$(basename "$PROJ_DIR")"
if [ "$ACTUAL_FOLDER" != "$EXPECTED_FOLDER" ]; then
    echo -e "${{YELLOW}}  [WARNING] Folder name mismatch${{NC}}"
    echo "    Expected: $EXPECTED_FOLDER"
    echo "    Actual:   $ACTUAL_FOLDER"
    echo ""
    ACTUAL_REMOTE=$(git remote get-url origin 2>/dev/null)
    if [ "$ACTUAL_REMOTE" = "{repo}.git" ] || [ "$ACTUAL_REMOTE" = "{repo}" ]; then
        echo "  Git remote matches — correct project, folder was renamed."
        echo "  Continuing..."
        echo ""
    else
        echo -e "${{RED}}  [ERROR] This script was generated for: {repo}${{NC}}"
        echo "  But this folder does not appear to be that project."
        echo ""
        echo "  To fix:"
        echo "    - Rename this folder to \"$EXPECTED_FOLDER\""
        echo "    - Or re-run new-project to generate correct scripts"
        read -p "  Press Enter to close..." _
        exit 1
    fi
fi

if [ ! -d ".git" ]; then echo -e "${{RED}}  [ERROR] No git repo found. Run push.sh first.${{NC}}"; read -p "  Press Enter to close..." _; exit 1; fi

# ── Pull project code ──
if [ $PULL_CODE -eq 1 ]; then
    # ── Project code status ──
    git fetch origin main --tags >/dev/null 2>&1
    AHEAD=$(git rev-list --count origin/main..HEAD 2>/dev/null || echo 0)
    BEHIND=$(git rev-list --count HEAD..origin/main 2>/dev/null || echo 0)
    LOCAL_COMMIT=$(git log -1 --format="%h  %ad  %s" --date=format:"%Y-%m-%d %H:%M" 2>/dev/null)
    REMOTE_COMMIT=$(git log -1 --format="%h  %ad  %s" --date=format:"%Y-%m-%d %H:%M" origin/main 2>/dev/null)

    echo "  ┌─────────────────────────────────────────────────┐"
    echo "  │  PROJECT CODE STATUS                            │"
    echo "  ├─────────────────────────────────────────────────┤"
    echo "  │  Local:  $LOCAL_COMMIT"
    echo "  │  Remote: $REMOTE_COMMIT"
    echo "  │  Ahead: $AHEAD commit(s)  Behind: $BEHIND commit(s)"
    echo "  └─────────────────────────────────────────────────┘"
    echo ""

    if [ "$BEHIND" -eq 0 ] 2>/dev/null; then
        echo -e "${{YELLOW}}  [INFO] Already up to date with remote.${{NC}}"
        echo "  Pulling anyway to ensure consistency."
        echo ""
    fi

    if [ "$AHEAD" -gt 0 ] 2>/dev/null; then
        echo -e "${{YELLOW}}  [INFO] You have $AHEAD local commit(s) not yet pushed.${{NC}}"
        echo "  Pulling will merge remote changes with your local commits."
        echo ""
    fi

    STASHED=0
    if [ -n "$(git status --porcelain)" ]; then
        echo -e "${{YELLOW}}  [WARNING] Unsaved local changes:${{NC}}"
        git status --short
        read -p "  Continue? (Y/N): " CONFIRM
        [[ ! "$CONFIRM" =~ ^[Yy]$ ]] && exit 0
        git stash >/dev/null 2>&1
        STASHED=1
    fi

    echo "  Pulling project code..."
    git pull origin main --tags 2>&1 || {{ echo -e "${{RED}}  [ERROR] Pull failed.${{NC}}"; read -p "  Press Enter to close..." _; exit 1; }}

    if [ $STASHED -eq 1 ]; then
        echo "  Restoring local changes..."
        git stash pop >/dev/null 2>&1 || echo -e "${{YELLOW}}  [WARNING] Could not restore stash. Run 'git stash pop' manually.${{NC}}"
    fi

    echo ""
    git log --oneline --decorate -5
    echo ""
    echo -e "${{GREEN}}  [OK] Project code updated.${{NC}}"
    echo ""
fi

# ── Pull CLI Sessions (via sync-sessions.py) ──
if [ $PULL_SESSIONS -eq 1 ]; then
    echo "  Syncing CLI sessions from GitHub..."
    echo "──────────────────────────────────────────────────"
    _SDIR="$(cd "$(dirname "$0")" && pwd)"
    SYNC_SCRIPT="$_SDIR/../../scripts/sync-sessions.py"
    [ ! -f "$SYNC_SCRIPT" ] && SYNC_SCRIPT="$_SDIR/../scripts/sync-sessions.py"
    if [ -f "$SYNC_SCRIPT" ]; then
        PROJ_PARENT="$(cd "$_SDIR/.." && cd .. && pwd)"
        if command -v python3 &>/dev/null; then python3 "$SYNC_SCRIPT" pull "$PROJ_PARENT" --project "{remote_slug}"
        elif command -v python &>/dev/null; then python "$SYNC_SCRIPT" pull "$PROJ_PARENT" --project "{remote_slug}"
        elif command -v py &>/dev/null; then py "$SYNC_SCRIPT" pull "$PROJ_PARENT" --project "{remote_slug}"
        else echo -e "${{YELLOW}}  [SKIP] Python not found. Install Python to sync sessions.${{NC}}"; fi
    else
        echo -e "${{YELLOW}}  [WARNING] sync-sessions.py not found.${{NC}}"
        echo "  This project may not be inside the workspace folder."
        echo "  Session sync requires: workspace/scripts/sync-sessions.py"
    fi
    echo "──────────────────────────────────────────────────"
fi

cd "$(dirname "$0")/.."
echo ""
read -p "  Press Enter to close..." _
""".strip()

# ══════════════════════════════════════════════════════════
#  rollback.sh
# ══════════════════════════════════════════════════════════
rollback_sh = r"""#!/bin/bash
# {display} — Rollback

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo ""
echo "══════════════════════════════════════════════════════════════════════════════"
echo "  {display} — Rollback to Previous Version"
echo "══════════════════════════════════════════════════════════════════════════════"
echo ""

if ! command -v git &>/dev/null; then echo -e "${{RED}}  [ERROR] git not installed.${{NC}}"; read -p "  Press Enter to close..." _; exit 1; fi
cd "$(dirname "$0")/.."

# ── Verify project folder ──
EXPECTED_FOLDER="{project_name}"
ACTUAL_FOLDER="$(basename "$(pwd)")"
if [ "$ACTUAL_FOLDER" != "$EXPECTED_FOLDER" ]; then
    echo -e "${{YELLOW}}  [WARNING] Folder name mismatch${{NC}}"
    echo "    Expected: $EXPECTED_FOLDER"
    echo "    Actual:   $ACTUAL_FOLDER"
    echo ""
    ACTUAL_REMOTE=$(git remote get-url origin 2>/dev/null)
    if [ "$ACTUAL_REMOTE" = "{repo}.git" ] || [ "$ACTUAL_REMOTE" = "{repo}" ]; then
        echo "  Git remote matches — correct project, folder was renamed."
        echo "  Continuing..."
        echo ""
    else
        echo -e "${{RED}}  [ERROR] This script was generated for: {repo}${{NC}}"
        echo "  But this folder does not appear to be that project."
        echo ""
        echo "  To fix:"
        echo "    - Rename this folder to \"$EXPECTED_FOLDER\""
        echo "    - Or re-run new-project to generate correct scripts"
        read -p "  Press Enter to close..." _
        exit 1
    fi
fi

# ── Project code status ──
git fetch origin main --tags >/dev/null 2>&1
AHEAD=$(git rev-list --count origin/main..HEAD 2>/dev/null || echo 0)
BEHIND=$(git rev-list --count HEAD..origin/main 2>/dev/null || echo 0)
LOCAL_COMMIT=$(git log -1 --format="%h  %ad  %s" --date=format:"%Y-%m-%d %H:%M" 2>/dev/null)
REMOTE_COMMIT=$(git log -1 --format="%h  %ad  %s" --date=format:"%Y-%m-%d %H:%M" origin/main 2>/dev/null)

echo "  ┌─────────────────────────────────────────────────┐"
echo "  │  CURRENT STATE                                  │"
echo "  ├─────────────────────────────────────────────────┤"
echo "  │  Local:  $LOCAL_COMMIT"
echo "  │  Remote: $REMOTE_COMMIT"
echo "  │  Ahead: $AHEAD commit(s)  Behind: $BEHIND commit(s)"
echo "  └─────────────────────────────────────────────────┘"
echo ""

if [ "$BEHIND" -gt 0 ] 2>/dev/null; then
    echo -e "${{YELLOW}}  [WARNING] Remote has $BEHIND commit(s) you haven't pulled.${{NC}}"
    echo "  Rolling back without pulling first means you'll lose those remote changes."
    echo ""
fi

echo "  VERSION HISTORY:"
echo "  ──────────────────────────────────────────────────"
git log --oneline --decorate -15
echo "  ──────────────────────────────────────────────────"
echo ""

read -p "  Rollback to (tag/hash, or 'quit'): " TARGET
[ -z "$TARGET" ] || [ "$TARGET" = "quit" ] && {{ read -p "  Press Enter to close..." _; exit 0; }}
git rev-parse "$TARGET" >/dev/null 2>&1 || {{ echo -e "${{RED}}  [ERROR] Not found.${{NC}}"; read -p "  Press Enter to close..." _; exit 1; }}

UNDO_COUNT=$(git rev-list "$TARGET..HEAD" --count 2>/dev/null)
[ "$UNDO_COUNT" = "0" ] && echo "  Already at this version." && read -p "  Press Enter to close..." _ && exit 0

TARGET_INFO=$(git log -1 --format="%h  %ad  %s" --date=format:"%Y-%m-%d %H:%M" "$TARGET" 2>/dev/null)

echo ""
echo "  ┌─────────────────────────────────────────────────┐"
echo "  │  ROLLBACK PLAN                                  │"
echo "  ├─────────────────────────────────────────────────┤"
echo "  │  From: $LOCAL_COMMIT"
echo "  │  To:   $TARGET_INFO"
echo "  │  Commits to undo: $UNDO_COUNT"
echo "  └─────────────────────────────────────────────────┘"
echo ""
echo "  Files that will change:"
echo "  ──────────────────────────────────────────────────"
git diff --stat "$TARGET" HEAD
echo "  ──────────────────────────────────────────────────"
echo ""

read -p "  Proceed with rollback? (Y/N): " CONFIRM
[[ ! "$CONFIRM" =~ ^[Yy]$ ]] && {{ echo "  Cancelled."; read -p "  Press Enter to close..." _; exit 0; }}

git checkout "$TARGET" -- . && git add -A && git commit -m "[ROLLBACK] Reverted to $TARGET"

echo ""
read -p "  Push rollback to remote? (Y/N): " PUSHIT
[[ "$PUSHIT" =~ ^[Yy]$ ]] && git push origin main --force

echo ""
echo -e "${{GREEN}}  SUCCESS! Rolled back to $TARGET${{NC}}"
echo "  A new commit was created — history is preserved."
echo ""
read -p "  Press Enter to close..." _
""".strip()

# ══════════════════════════════════════════════════════════
#  Write all files
# ══════════════════════════════════════════════════════════
files = {
    'push.bat': push_bat.format(display=display_name, repo=repo_url, remote_slug=remote_slug, project_name=project_name),
    'pull.bat': pull_bat.format(display=display_name, repo=repo_url, remote_slug=remote_slug, project_name=project_name),
    'rollback.bat': rollback_bat.format(display=display_name, repo=repo_url, project_name=project_name),
    'push.sh': push_sh.format(display=display_name, repo=repo_url, remote_slug=remote_slug, project_name=project_name),
    'pull.sh': pull_sh.format(display=display_name, repo=repo_url, remote_slug=remote_slug, project_name=project_name),
    'rollback.sh': rollback_sh.format(display=display_name, repo=repo_url, project_name=project_name),
}

for filename, content in files.items():
    filepath = os.path.join(scripts_dir, filename)
    action = "UPDATE" if os.path.isfile(filepath) else "OK"
    # .bat files need CRLF for Windows cmd.exe, .sh files need LF for bash
    line_ending = '\r\n' if filename.endswith('.bat') else '\n'
    with open(filepath, 'w', encoding='utf-8', newline='') as f:
        f.write(content.replace('\n', line_ending) + line_ending)
    print(f"  [{action}] scripts/{filename}")

# ── Copy claude-launch.bat and claude-launch.sh from root scripts/ ──
# The wrappers find the .py in the root CLAUDECODE/scripts/ folder
gen_script_dir = os.path.dirname(os.path.abspath(__file__))
import shutil
for launcher in ('claude-launch.bat', 'claude-launch.sh'):
    src = os.path.join(gen_script_dir, launcher)
    dst = os.path.join(scripts_dir, launcher)
    if os.path.isfile(src):
        shutil.copy2(src, dst)
        print(f"  [OK] scripts/{launcher}")
    else:
        print(f"  [SKIP] {launcher} not found in root scripts/")

# ── Copy SESSION-SYNC-GUIDE.md if available ──
parent_dir = os.path.dirname(project_dir)
guide_src = os.path.join(parent_dir, 'SESSION-SYNC-GUIDE.md')
if os.path.isfile(guide_src):
    import shutil
    shutil.copy2(guide_src, os.path.join(project_dir, 'SESSION-SYNC-GUIDE.md'))
    print(f"  [OK] SESSION-SYNC-GUIDE.md")

print()
print("  [OK] All scripts generated.")

@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion
title New Project Setup
color 0B

echo ══════════════════════════════════════════════════
echo   NEW PROJECT SETUP
echo ══════════════════════════════════════════════════
echo.
echo  This will create a new project folder with all
echo  standardized scripts (push, pull, rollback,
echo  session push/pull, migration scripts).
echo.
echo  Fully self-contained — works on a fresh PC.
echo.
echo ══════════════════════════════════════════════════
echo.

:: ── Check git ──
where git >nul 2>&1
if errorlevel 1 (
    color 0C
    echo  [ERROR] git is not installed or not in PATH.
    echo  Install from: https://git-scm.com/download/win
    pause
    exit /b 1
)

:: ── Auto-setup CLI session repo ──
set "CLAUDE_DIR=%USERPROFILE%\.claude"
if exist "!CLAUDE_DIR!\.git" (
    echo  [OK] CLI session repo already configured.
    echo.
) else (
    echo ──────────────────────────────────────────────────
    echo   CLI SESSION REPO SETUP
    echo ──────────────────────────────────────────────────
    echo.
    echo  Pull your CLI sessions from GitHub:
    echo  https://github.com/YOUR-ORG/claude-dotfiles
    echo.
    set /p SETUP_CLI="  Pull CLI sessions now? (Y/N): "
    if /i "!SETUP_CLI!"=="Y" (
        if exist "!CLAUDE_DIR!" (
            echo  [INFO] Claude folder exists. Initializing...
            pushd "!CLAUDE_DIR!"
            git init >nul 2>&1
            git remote add origin https://github.com/YOUR-ORG/claude-dotfiles.git 2>nul
            git branch -M main >nul 2>&1
            git add -A >nul 2>&1
            git commit -m "local files before first pull" >nul 2>&1
            git pull origin main --no-rebase --allow-unrelated-histories --no-edit >nul 2>&1
            if errorlevel 1 (
                echo  [WARNING] Could not pull. Check GitHub auth.
            ) else (
                echo  [OK] CLI sessions pulled.
                :: Run full session sync to fix cross-platform paths
                set "SYNC_PY=%~dp0sync-sessions.py"
                if exist "!SYNC_PY!" (
                    set "PY_S="
                    for /f "tokens=*" %%P in ('where py 2^>nul') do if not defined PY_S set "PY_S=%%P"
                    if not defined PY_S for /f "tokens=*" %%P in ('where python 2^>nul') do if not defined PY_S set "PY_S=%%P"
                    if defined PY_S (
                        set "CC_ROOT=%~dp0.."
                        "!PY_S!" "!SYNC_PY!" pull "!CC_ROOT!"
                    )
                )
            )
            popd
        ) else (
            echo  [INFO] Pulling CLI sessions from GitHub...
            git clone https://github.com/YOUR-ORG/claude-dotfiles.git "!CLAUDE_DIR!" 2>&1
            if errorlevel 1 (
                echo  [WARNING] Clone failed. Check GitHub auth.
            ) else (
                echo  [OK] CLI sessions pulled.
                :: Run full session sync to fix cross-platform paths
                set "SYNC_PY=%~dp0sync-sessions.py"
                if exist "!SYNC_PY!" (
                    set "PY_S="
                    for /f "tokens=*" %%P in ('where py 2^>nul') do if not defined PY_S set "PY_S=%%P"
                    if not defined PY_S for /f "tokens=*" %%P in ('where python 2^>nul') do if not defined PY_S set "PY_S=%%P"
                    if defined PY_S (
                        set "CC_ROOT=%~dp0.."
                        "!PY_S!" "!SYNC_PY!" pull "!CC_ROOT!"
                    )
                )
            )
        )
    ) else (
        echo  [SKIP] CLI sessions skipped.
    )
    echo.
)

:: ── Ask for GitHub repo URL ──
echo  Enter the GitHub repository URL:
echo  Example: https://github.com/YOUR-ORG/my-project
echo.
set /p REPO_URL="  >> "

if "!REPO_URL!"=="" (
    color 0C
    echo  [ERROR] No URL provided.
    pause
    exit /b 1
)

:: Clean URL (remove trailing .git and /)
if "!REPO_URL:~-1!"=="/" set "REPO_URL=!REPO_URL:~0,-1!"
if "!REPO_URL:~-4!"==".git" set "REPO_URL=!REPO_URL:~0,-4!"

:: Extract project name (last segment of URL)
for %%I in ("!REPO_URL!") do set "PROJECT_NAME=%%~nxI"

if "!PROJECT_NAME!"=="" (
    color 0C
    echo  [ERROR] Could not extract project name.
    pause
    exit /b 1
)

:: ── Build display name (title case via PowerShell) ──
for /f "tokens=*" %%n in ('powershell -NoProfile -Command "('!PROJECT_NAME!' -replace '-',' ' -split ' ' | ForEach-Object { $_.Substring(0,1).ToUpper() + $_.Substring(1).ToLower() }) -join ' '"') do set "DISPLAY_NAME=%%n"

:: Default parent: CLAUDECODE root (one folder above scripts/)
set "SCRIPT_DIR=%~dp0"
set "SCRIPT_DIR=!SCRIPT_DIR:~0,-1!"
for %%I in ("!SCRIPT_DIR!") do set "PARENT_DIR=%%~dpI"
set "PARENT_DIR=!PARENT_DIR:~0,-1!"

echo.
echo ──────────────────────────────────────────────────
echo   Repo URL:      !REPO_URL!
echo   Project name:  !PROJECT_NAME!
echo   Display name:  !DISPLAY_NAME!
echo ──────────────────────────────────────────────────
echo.
echo  Project will be created at:
echo    !PARENT_DIR!\!PROJECT_NAME!
echo.
set /p DIR_CHOICE="  Press Enter to proceed, or type CHANGE to pick a different folder: "

if /i "!DIR_CHOICE!"=="CHANGE" (
    echo.
    set /p CUSTOM_DIR="  Enter the parent folder path: "
    if "!CUSTOM_DIR!"=="" (
        color 0C
        echo  [ERROR] No path entered. Cancelled.
        pause
        exit /b 1
    )
    if not exist "!CUSTOM_DIR!" (
        color 0C
        echo  [ERROR] Folder does not exist: !CUSTOM_DIR!
        echo  Please create it first or check the path.
        pause
        exit /b 1
    )
    set "PARENT_DIR=!CUSTOM_DIR!"
    echo.
    echo  Using: !PARENT_DIR!\!PROJECT_NAME!
    echo.
)

set "PROJECT_DIR=!PARENT_DIR!\!PROJECT_NAME!"

echo ──────────────────────────────────────────────────
echo   Full path:  !PROJECT_DIR!
echo ──────────────────────────────────────────────────
echo.
set /p CONFIRM="  Create this project? (Y/N): "
if /i not "!CONFIRM!"=="Y" ( echo  Cancelled. & pause & exit /b 0 )

:: ── Create folder ──
if exist "!PROJECT_DIR!" (
    echo  [WARNING] Folder already exists. Continuing anyway.
) else (
    mkdir "!PROJECT_DIR!"
    echo  [OK] Created folder: !PROJECT_NAME!
)

cd /d "!PROJECT_DIR!"

:: ── Clone or init ──
if not exist ".git" (
    echo  [INFO] Checking if remote repo has content...
    git ls-remote "!REPO_URL!.git" >nul 2>&1
    if not errorlevel 1 (
        git clone "!REPO_URL!.git" "!PROJECT_DIR!" 2>&1
        if errorlevel 1 (
            git init
            git remote add origin "!REPO_URL!.git"
            git branch -M main
        )
    ) else (
        git init
        git remote add origin "!REPO_URL!.git"
        git branch -M main
    )
    echo.
)

:: Ensure main branch
for /f "tokens=*" %%b in ('git branch --show-current 2^>nul') do set "CURRENT_BRANCH=%%b"
if not "!CURRENT_BRANCH!"=="main" (
    git branch -M main >nul 2>&1
)

:: ── Generate scripts ──
echo  Generating project scripts...
mkdir "!PROJECT_DIR!\scripts" 2>nul

:: Check for Python (try py launcher first — most reliable on Windows)
set "PYTHON_CMD="
where py >nul 2>&1
if not errorlevel 1 set "PYTHON_CMD=py"
if "!PYTHON_CMD!"=="" (
    where python >nul 2>&1
    if not errorlevel 1 set "PYTHON_CMD=python"
)
if "!PYTHON_CMD!"=="" (
    where python3 >nul 2>&1
    if not errorlevel 1 set "PYTHON_CMD=python3"
)

if "!PYTHON_CMD!"=="" (
    color 0C
    echo  [ERROR] Python is required to generate project scripts.
    echo  Install from: https://www.python.org/downloads/
    pause
    exit /b 1
)

:: Generate scripts using Python
!PYTHON_CMD! "!SCRIPT_DIR!\new-project-gen.py" "!DISPLAY_NAME!" "!REPO_URL!" "!PROJECT_DIR!"
if errorlevel 1 (
    color 0C
    echo  [ERROR] Script generation failed.
    pause
    exit /b 1
)

echo.
color 0A
echo ══════════════════════════════════════════════════
echo   SUCCESS^^! Project "!PROJECT_NAME!" created
echo ══════════════════════════════════════════════════
echo.
echo  Folder:    !PROJECT_DIR!
echo  Repo:      !REPO_URL!
echo  Branch:    main
echo.
echo  Files created (in scripts/):
echo    push.bat / push.sh         - Push code + CLI sessions
echo    pull.bat / pull.sh         - Pull code + CLI sessions
echo    rollback.bat / rollback.sh - Rollback to previous version
echo    claude-launch.bat          - Interactive launcher TUI
echo.
:: Check if sessions need pulling
set "CLAUDE_DIR_NP=!CLAUDE_DIR!"
if not defined CLAUDE_DIR_NP set "CLAUDE_DIR_NP=%USERPROFILE%\.claude"
set "CDIR_FILE=%~dp0.claude-dir"
if exist "!CDIR_FILE!" (
    set /p CLAUDE_DIR_NP=<"!CDIR_FILE!"
)

if exist "!CLAUDE_DIR_NP!\.git" (
    :: Repo exists — check if behind remote
    pushd "!CLAUDE_DIR_NP!" >nul
    git fetch origin main >nul 2>&1
    set "SESS_BEHIND=0"
    for /f %%n in ('git rev-list --count HEAD..origin/main 2^>nul') do set "SESS_BEHIND=%%n"
    popd >nul
    if "!SESS_BEHIND!"=="0" (
        echo.
        echo  [OK] Sessions already up to date.
    ) else (
        echo.
        echo  [INFO] !SESS_BEHIND! new session sync(s^) available from another machine.
        set /p PULL_SESS="  Pull latest sessions? (Y/N): "
        if /i "!PULL_SESS!"=="Y" (
            echo.
            set "SYNC_PY=%~dp0sync-sessions.py"
            if exist "!SYNC_PY!" (
                set "PY_S="
                for /f "tokens=*" %%P in ('where py 2^>nul') do if not defined PY_S set "PY_S=%%P"
                if not defined PY_S for /f "tokens=*" %%P in ('where python 2^>nul') do if not defined PY_S set "PY_S=%%P"
                if defined PY_S (
                    set "CC_ROOT=%~dp0.."
                    set "RSLUG=!REPO_URL!"
                    set "RSLUG=!RSLUG:https://github.com/=!"
                    "!PY_S!" "!SYNC_PY!" pull "!CC_ROOT!" --project "!RSLUG!"
                ) else (
                    echo  [SKIP] Python not found.
                )
            ) else (
                echo  [SKIP] sync-sessions.py not found.
            )
        )
    )
) else (
    :: No repo — first time setup
    echo.
    set /p PULL_SESS="  Pull sessions for this project from another machine? (Y/N): "
    if /i "!PULL_SESS!"=="Y" (
        echo.
        set "SYNC_PY=%~dp0sync-sessions.py"
        if exist "!SYNC_PY!" (
            set "PY_S="
            for /f "tokens=*" %%P in ('where py 2^>nul') do if not defined PY_S set "PY_S=%%P"
            if not defined PY_S for /f "tokens=*" %%P in ('where python 2^>nul') do if not defined PY_S set "PY_S=%%P"
            if defined PY_S (
                set "CC_ROOT=%~dp0.."
                set "RSLUG=!REPO_URL!"
                set "RSLUG=!RSLUG:https://github.com/=!"
                "!PY_S!" "!SYNC_PY!" pull "!CC_ROOT!" --project "!RSLUG!"
            ) else (
                echo  [SKIP] Python not found.
            )
        ) else (
            echo  [SKIP] sync-sessions.py not found.
        )
    )
)

echo.
echo  Next steps:
echo    1. Open the folder in Claude Code or terminal
echo    2. Start working
echo    3. When done, run scripts\push.bat
echo.

endlocal
pause

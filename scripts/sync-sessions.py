"""Unified CLI session sync — push or pull sessions between PCs via GitHub.

Supports per-project or all-project sync:

  sync-sessions.py push <claudecode_dir>                          # push ALL sessions (force push)
  sync-sessions.py pull <claudecode_dir>                          # pull ALL sessions
  sync-sessions.py push <claudecode_dir> --project org/repo       # push ONE project (incremental)
  sync-sessions.py pull <claudecode_dir> --project org/repo       # pull + process ONE project
"""
import os, sys, glob, shutil, re, subprocess, json, argparse
from datetime import datetime, timezone
from pathlib import Path

# ═══════════════════════════════════════════════════════
#  Configuration
# ═══════════════════════════════════════════════════════
THRESHOLD_MB = 90
THRESHOLD_BYTES = THRESHOLD_MB * 1024 * 1024
CLI_REPO = "https://github.com/YOUR-ORG/claude-dotfiles.git"

# ANSI colors for terminal output
C_GREEN = "\033[32m"
C_YELLOW = "\033[33m"
C_RED = "\033[31m"
C_CYAN = "\033[36m"
C_DIM = "\033[2m"
C_BOLD = "\033[1m"
C_RESET = "\033[0m"


def encode_path(p):
    return p.replace("\\", "-").replace("/", "-").replace(":", "-").replace(".", "-")


def get_claude_dir():
    """Get the Claude CLI config directory. Checks (in order):
    1. CLAUDE_DIR environment variable (set by setup-owner or manually)
    2. .claude-dir file in the workspace scripts/ directory
    3. Default: ~/.claude/
    If the resolved directory doesn't exist and isn't the default, prompts the user.
    """
    # Check env var first
    env_dir = os.environ.get("CLAUDE_DIR")
    if env_dir and os.path.isdir(env_dir):
        return os.path.normpath(env_dir)

    # Check .claude-dir config file next to sync-sessions.py
    config_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".claude-dir")
    if os.path.isfile(config_file):
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                custom_dir = f.read().strip()
            if custom_dir and os.path.isdir(custom_dir):
                return os.path.normpath(custom_dir)
        except Exception:
            pass

    # Default
    default = os.path.join(os.path.expanduser("~"), ".claude")
    if os.path.isdir(default):
        return default

    # Default doesn't exist — try to find it
    return _find_or_ask_claude_dir(default, config_file)


def _find_or_ask_claude_dir(default, config_file):
    """When the Claude directory can't be found, search common locations or ask the user."""
    # Search common alternative locations
    candidates = [
        default,
        os.path.join(os.path.expanduser("~"), ".config", "claude"),
    ]
    if sys.platform == "win32":
        userprofile = os.environ.get("USERPROFILE", "")
        if userprofile:
            candidates.append(os.path.join(userprofile, ".claude"))

    for c in candidates:
        if os.path.isdir(c) and (os.path.isdir(os.path.join(c, "projects")) or
                                  os.path.isfile(os.path.join(c, "settings.json"))):
            print(f"  [INFO] Found Claude directory at: {c}")
            return c

    # Not found anywhere — ask the user
    print()
    print("  ┌─────────────────────────────────────────────────┐")
    print("  │  Claude CLI directory not found                  │")
    print("  └─────────────────────────────────────────────────┘")
    print()
    print(f"  Expected at: {default}")
    print()
    print("  This could mean:")
    print("    - Claude Code CLI hasn't been run yet on this machine")
    print("    - Your Claude config is in a non-standard location")
    print()
    print("  Options:")
    print("    1) Use default location (will be created on first sync)")
    print("    2) Enter a custom path")
    print("    3) Run setup-owner to configure (recommended for first time)")
    print()

    try:
        choice = input("  Choice [1]: ").strip()
    except (EOFError, KeyboardInterrupt):
        choice = "1"

    if choice == "2":
        while True:
            try:
                custom = input("  Enter Claude directory path: ").strip()
            except (EOFError, KeyboardInterrupt):
                custom = ""
            if not custom:
                print("  Using default.")
                return default
            if os.path.isdir(custom):
                # Save it for next time
                try:
                    with open(config_file, "w", encoding="utf-8") as f:
                        f.write(custom + "\n")
                    print(f"  [OK] Saved to .claude-dir for future use.")
                except Exception:
                    pass
                return os.path.normpath(custom)
            else:
                print(f"  [ERROR] Directory does not exist: {custom}")
                print("  Please check the path and try again.")
                print()
    elif choice == "3":
        print()
        print("  Run setup-owner first:")
        print("    Mac:     ./scripts/setup-owner.sh")
        print("    Windows: scripts\\setup-owner.bat")
        print()
        sys.exit(1)

    # Default: use standard location (will be created by ensure_repo)
    return default


def get_projects_dir():
    return os.path.join(get_claude_dir(), "projects")


def is_junction_or_symlink(path):
    if os.path.islink(path):
        return True
    if sys.platform == "win32":
        try:
            import ctypes
            attrs = ctypes.windll.kernel32.GetFileAttributesW(path)
            return attrs != -1 and (attrs & 0x400) != 0
        except Exception:
            pass
    return False


def resolve_project_folder(claudecode_dir, project_remote):
    """Given a git remote slug (e.g., 'pitir-tech/n8n'), find the local folder name."""
    if not os.path.isdir(claudecode_dir):
        return None
    target = project_remote.lower()
    for entry in os.listdir(claudecode_dir):
        full = os.path.join(claudecode_dir, entry)
        if not os.path.isdir(full) or not os.path.isdir(os.path.join(full, ".git")):
            continue
        remote = _get_git_remote(full)
        if remote and remote == target:
            return entry
    # Fallback: use the repo name portion of the remote
    repo_name = project_remote.split("/")[-1] if "/" in project_remote else project_remote
    folder = os.path.join(claudecode_dir, repo_name)
    if os.path.isdir(folder):
        return repo_name
    return None


def _dir_matches_project(dir_name, project_filter):
    """Check if a session dir name belongs to a specific project folder."""
    if project_filter is None:
        return True
    return dir_name.lower().endswith(f"-{project_filter.lower()}")


def _walk_matches_project(root_path, projects_dir, project_filter):
    """Check if a path within projects/ belongs to the filtered project."""
    if project_filter is None:
        return True
    rel = os.path.relpath(root_path, projects_dir)
    top_dir = rel.split(os.sep)[0]
    return top_dir.lower().endswith(f"-{project_filter.lower()}")


# ═══════════════════════════════════════════════════════
#  TRIM: Backup originals, write trimmed versions
# ═══════════════════════════════════════════════════════
def trim_oversized(claude_dir, project_filter=None):
    """Trim .jsonl files >90MB to last 90MB. Originals saved as .untrimmed."""
    projects_dir = os.path.join(claude_dir, "projects")
    if not os.path.isdir(projects_dir):
        return 0
    trimmed = 0
    for root, dirs, files in os.walk(projects_dir):
        if not _walk_matches_project(root, projects_dir, project_filter):
            continue
        for fname in files:
            if not fname.endswith(".jsonl"):
                continue
            fpath = os.path.join(root, fname)
            try:
                fsize = os.path.getsize(fpath)
            except OSError:
                continue
            if fsize <= THRESHOLD_BYTES:
                continue
            backup = fpath + ".untrimmed"
            if os.path.exists(backup):
                continue
            rel = os.path.relpath(fpath, projects_dir)
            mb = fsize / (1024 * 1024)
            print(f"  [TRIM] {rel} ({mb:.0f} MB -> {THRESHOLD_MB} MB)")
            try:
                shutil.copy2(fpath, backup)
                with open(fpath, "rb") as f:
                    f.seek(fsize - THRESHOLD_BYTES)
                    f.readline()
                    data = f.read()
                if not data or len(data) < 100:
                    # Safety: don't overwrite with empty/tiny content
                    print(f"  [ERROR] {rel}: trimmed data too small ({len(data)} bytes), skipping")
                    os.remove(backup)
                    continue
                with open(fpath, "wb") as f:
                    f.write(data)
                trimmed += 1
            except Exception as e:
                print(f"  [ERROR] {rel}: {e}")
                if os.path.exists(backup):
                    shutil.move(backup, fpath)
    if trimmed:
        print(f"  [OK] Trimmed {trimmed} file(s). Originals saved as .untrimmed.")
    else:
        print("  All files within size limits.")
    return trimmed


def archive_to_session_originals(claude_dir, project_filter=None):
    """Append .untrimmed files (full originals) to session-originals/ archive.

    Called after a successful push. The .untrimmed file is the full session
    before trimming. Its content is appended to session-originals/ (growing
    archive, no duplication). The .untrimmed file is NOT deleted here —
    restore_untrimmed() handles moving it back to the project folder.
    """
    projects_dir = os.path.join(claude_dir, "projects")
    backup_dir = os.path.join(claude_dir, "session-originals")
    if not os.path.isdir(projects_dir):
        return
    archived = 0
    for root, dirs, files in os.walk(projects_dir):
        if project_filter and not _walk_matches_project(root, projects_dir, project_filter):
            continue
        for fname in files:
            if not fname.endswith(".untrimmed"):
                continue
            untrimmed_path = os.path.join(root, fname)
            # Map to session-originals path (strip .untrimmed suffix for the archive name)
            original_name = fname.replace(".untrimmed", "")
            rel = os.path.relpath(os.path.join(root, original_name), projects_dir)
            archive_path = os.path.join(backup_dir, rel)
            os.makedirs(os.path.dirname(archive_path), exist_ok=True)
            try:
                _append_to_backup(untrimmed_path, archive_path)
                archived += 1
                asize = os.path.getsize(archive_path) if os.path.exists(archive_path) else 0
                usize = os.path.getsize(untrimmed_path)
                print(f"  [ARCHIVE] {rel} ({usize // (1024*1024)} MB -> {asize // (1024*1024)} MB archive)")
            except Exception as e:
                print(f"  [ERROR] Could not archive {rel}: {e}")
    if archived:
        print(f"  [OK] Archived {archived} file(s) to session-originals/.")


def restore_untrimmed(claude_dir, project_filter=None):
    """Restore .untrimmed backups to their original names in project folder."""
    projects_dir = os.path.join(claude_dir, "projects")
    if not os.path.isdir(projects_dir):
        return
    restored = 0
    for root, dirs, files in os.walk(projects_dir):
        if project_filter and not _walk_matches_project(root, projects_dir, project_filter):
            continue
        for fname in files:
            if not fname.endswith(".untrimmed"):
                continue
            backup = os.path.join(root, fname)
            original = backup.replace(".untrimmed", "")
            try:
                shutil.move(backup, original)
                restored += 1
            except Exception as e:
                print(f"  [ERROR] Could not restore {fname}: {e}")
    if restored:
        print(f"  [OK] Restored {restored} original file(s).")


# ═══════════════════════════════════════════════════════
#  BACKUP: Save large originals before pull overwrites
# ═══════════════════════════════════════════════════════
def _append_to_backup(src_path, backup_path):
    """Append only NEW lines from src onto the existing backup.

    The backup is a growing history file. This function:
    1. Reads the last few lines of the backup to find an overlap anchor
    2. Searches the source for that anchor
    3. Appends only lines AFTER the anchor (new content)
    4. If the entire source is already in the backup, appends nothing
    5. If no overlap found, the source has entirely new content — append all

    If no backup exists yet, copies the source as the initial backup.
    """
    if not os.path.exists(backup_path):
        shutil.copy2(src_path, backup_path)
        return

    try:
        # Read last few non-empty lines of backup as anchor candidates
        bsize = os.path.getsize(backup_path)
        with open(backup_path, "rb") as f:
            f.seek(max(0, bsize - 50000))
            tail = f.read().decode("utf-8", errors="replace")

        backup_tail_lines = [l.strip() for l in tail.strip().split("\n") if l.strip()]
        if not backup_tail_lines:
            shutil.copy2(src_path, backup_path)
            return

        # Try matching with the last line, then second-to-last, etc.
        # This handles cases where the last line was truncated during trim
        src_lines = []
        with open(src_path, "r", encoding="utf-8", errors="replace") as f:
            src_lines = f.readlines()

        if not src_lines:
            return

        # Search for overlap — try last 5 backup lines as anchors
        new_start = -1
        for anchor in reversed(backup_tail_lines[-5:]):
            candidate = -1
            for i, line in enumerate(src_lines):
                if line.strip() == anchor:
                    candidate = i  # Keep searching for the LAST occurrence
            if candidate >= 0:
                new_start = candidate + 1
                break

        if new_start > 0 and new_start < len(src_lines):
            # Append only lines after the overlap
            new_content = src_lines[new_start:]
            if new_content:
                with open(backup_path, "a", encoding="utf-8") as f:
                    f.writelines(new_content)
        elif new_start == -1:
            # No overlap found — source is entirely new content, append all
            with open(backup_path, "a", encoding="utf-8") as f:
                f.writelines(src_lines)
        # else: new_start >= len(src_lines) means all source lines are in backup already

    except Exception:
        # Fallback: just replace
        shutil.copy2(src_path, backup_path)


def backup_originals(claude_dir, project_filter=None):
    """Backup files >90MB to session-originals/ before pull."""
    projects_dir = os.path.join(claude_dir, "projects")
    backup_dir = os.path.join(claude_dir, "session-originals")
    if not os.path.isdir(projects_dir):
        return
    os.makedirs(backup_dir, exist_ok=True)
    backed = 0
    for root, dirs, files in os.walk(projects_dir):
        if not _walk_matches_project(root, projects_dir, project_filter):
            continue
        for fname in files:
            if not fname.endswith(".jsonl"):
                continue
            fpath = os.path.join(root, fname)
            try:
                fsize = os.path.getsize(fpath)
            except OSError:
                continue
            if fsize <= THRESHOLD_BYTES:
                continue
            rel = os.path.relpath(fpath, projects_dir)
            bpath = os.path.join(backup_dir, rel)
            # Append new content to backup (growing history)
            os.makedirs(os.path.dirname(bpath), exist_ok=True)
            try:
                _append_to_backup(fpath, bpath)
                backed += 1
                bsize = os.path.getsize(bpath) if os.path.exists(bpath) else 0
                print(f"  [BACKUP] {rel} ({fsize // (1024*1024)} MB local, {bsize // (1024*1024)} MB backup)")
            except Exception as e:
                print(f"  [ERROR] {rel}: {e}")
    if backed:
        print(f"  [OK] Backed up {backed} large file(s).")
    elif backed == 0:
        print("  No files need backup.")


# ═══════════════════════════════════════════════════════
#  MERGE: Copy sessions from other-PC folders into ours
# ═══════════════════════════════════════════════════════
def merge_sessions(claude_dir, new_encoded, root_folder, project_filter=None):
    """Find session folders from other PCs and merge into this PC's folders."""
    projects_dir = os.path.join(claude_dir, "projects")
    if not os.path.isdir(projects_dir):
        return

    # Find old prefixes
    old_prefixes = set()
    for entry in os.listdir(projects_dir):
        full = os.path.join(projects_dir, entry)
        if not os.path.isdir(full) or is_junction_or_symlink(full):
            continue
        if entry.startswith(new_encoded):
            continue
        idx = entry.upper().find(root_folder.upper())
        if idx < 0:
            continue
        prefix = entry[:idx + len(root_folder)]
        old_prefixes.add(prefix)

    if not old_prefixes:
        print("  No session folders from other machines found.")
        return

    total_merged = 0
    files_scanned = 0
    for old_prefix in sorted(old_prefixes):
        print(f"  Merging: {old_prefix} -> {new_encoded}")
        for entry in sorted(os.listdir(projects_dir)):
            if not entry.startswith(old_prefix):
                continue
            rest = entry[len(old_prefix):]
            if rest and not rest.startswith("-"):
                continue
            if project_filter and not _dir_matches_project(entry, project_filter):
                continue
            old_dir = os.path.join(projects_dir, entry)
            if not os.path.isdir(old_dir) or is_junction_or_symlink(old_dir):
                continue
            new_name = new_encoded + rest
            new_dir = os.path.join(projects_dir, new_name)
            os.makedirs(new_dir, exist_ok=True)
            # Recursive merge: copy ALL files and subdirs that don't exist in target
            for dirpath, dirnames, filenames in os.walk(old_dir):
                rel = os.path.relpath(dirpath, old_dir)
                tgt_dir = os.path.join(new_dir, rel) if rel != "." else new_dir
                os.makedirs(tgt_dir, exist_ok=True)
                for fname in filenames:
                    files_scanned += 1
                    if files_scanned % 100 == 0:
                        sys.stdout.write(f"    {C_DIM}Processing {files_scanned} files ({total_merged} merged)...{C_RESET}\r")
                        sys.stdout.flush()
                    src = os.path.join(dirpath, fname)
                    dst = os.path.join(tgt_dir, fname)
                    if not os.path.exists(dst):
                        # File doesn't exist in target — copy it
                        shutil.copy2(src, dst)
                        total_merged += 1
                    else:
                        # File exists — skip if identical, replace if source is newer or larger
                        try:
                            src_size = os.path.getsize(src)
                            dst_size = os.path.getsize(dst)
                            if src_size == dst_size:
                                continue  # Same size = same content, skip
                            src_mtime = os.path.getmtime(src)
                            dst_mtime = os.path.getmtime(dst)
                            if src_size > dst_size or src_mtime > dst_mtime:
                                # Back up local file before replacing
                                if dst_size > THRESHOLD_BYTES:
                                    backup_dir = os.path.join(claude_dir, "session-originals")
                                    rel = os.path.relpath(dst, projects_dir)
                                    bpath = os.path.join(backup_dir, rel)
                                    os.makedirs(os.path.dirname(bpath), exist_ok=True)
                                    _append_to_backup(dst, bpath)
                                    print(f"    {C_DIM}Backed up {os.path.basename(dst)} ({dst_size // (1024*1024)} MB){C_RESET}")
                                shutil.copy2(src, dst)
                                total_merged += 1
                        except OSError:
                            pass

    if total_merged:
        print(f"  [OK] Merged {total_merged} file(s) (sessions + memory) from other PC(s).")
    else:
        print("  All sessions and memory already merged.")


# ═══════════════════════════════════════════════════════
#  MATERIALIZE: Convert symlinks/junctions to real dirs
# ═══════════════════════════════════════════════════════
def materialize_symlinks(claude_dir, new_encoded, project_filter=None):
    """Convert symlinks/junctions pointing to old-PC dirs into real directories.

    The older session-migrate-core.py creates symlinks from the current
    machine's dir name to the old-PC dir. Before we can delete old dirs,
    we must copy the content into real dirs so nothing is lost.
    """
    projects_dir = os.path.join(claude_dir, "projects")
    if not os.path.isdir(projects_dir):
        return

    materialized = 0
    for entry in sorted(os.listdir(projects_dir)):
        full = os.path.join(projects_dir, entry)
        # Only process current machine's dirs that are symlinks/junctions
        if not entry.startswith(new_encoded):
            continue
        if project_filter and not _dir_matches_project(entry, project_filter):
            continue
        if not is_junction_or_symlink(full):
            continue

        # Resolve the symlink target and copy its contents
        try:
            target = os.path.realpath(full)
            if not os.path.isdir(target):
                continue

            # Remove the symlink/junction
            if os.path.islink(full):
                os.remove(full)
            elif sys.platform == "win32":
                # Windows junction
                import subprocess
                subprocess.run(["cmd", "/c", "rmdir", full],
                               capture_output=True, text=True)
            else:
                os.remove(full)

            # Copy the real content
            shutil.copytree(target, full)
            materialized += 1
        except Exception as e:
            print(f"  [WARNING] Could not materialize {entry}: {e}")

    if materialized:
        print(f"  [OK] Converted {materialized} symlink(s) to real dirs.")


# ═══════════════════════════════════════════════════════
#  CLEANUP: Remove other-PC dirs after merge
# ═══════════════════════════════════════════════════════
def cleanup_old_dirs(claude_dir, new_encoded, root_folder, project_filter=None):
    """Remove other-PC project dirs after their sessions have been merged."""
    projects_dir = os.path.join(claude_dir, "projects")
    if not os.path.isdir(projects_dir):
        return

    removed = 0
    for entry in sorted(os.listdir(projects_dir)):
        full = os.path.join(projects_dir, entry)
        if not os.path.isdir(full):
            continue
        # Skip current machine's dirs (real or symlink)
        if entry.startswith(new_encoded):
            continue
        # Only remove dirs that contain our root folder name (e.g., CLAUDECODE)
        if root_folder.upper() not in entry.upper():
            continue
        if project_filter and not _dir_matches_project(entry, project_filter):
            continue
        # Remove symlinks/junctions
        if is_junction_or_symlink(full):
            try:
                if os.path.islink(full):
                    os.remove(full)
                elif sys.platform == "win32":
                    subprocess.run(["cmd", "/c", "rmdir", full],
                                   capture_output=True, text=True)
                removed += 1
            except Exception as e:
                print(f"  [WARNING] Could not remove link {entry}: {e}")
            continue
        # Remove real dirs
        try:
            shutil.rmtree(full)
            removed += 1
        except Exception as e:
            print(f"  [WARNING] Could not remove {entry}: {e}")

    if removed:
        print(f"  [OK] Cleaned up {removed} other-PC project dir(s).")
    else:
        print("  No other-PC dirs to clean up.")


# ═══════════════════════════════════════════════════════
#  RESTORE: Merge large originals back after pull
# ═══════════════════════════════════════════════════════
def restore_large_originals(claude_dir, project_filter=None):
    """If session-originals/ has a larger version of a file, merge the history back.

    After pull, git may replace a 300MB file with a trimmed 90MB version.
    The original was saved to session-originals/ by backup_originals().
    This function restores the full history by appending new lines from
    the pulled version onto the original.
    """
    backup_dir = os.path.join(claude_dir, "session-originals")
    projects_dir = os.path.join(claude_dir, "projects")
    if not os.path.isdir(backup_dir):
        return

    restored = 0
    failed = 0
    for root, dirs, files in os.walk(backup_dir):
        for fname in files:
            # Filter by project if specified
            if project_filter and fname.endswith(".jsonl"):
                rel = os.path.relpath(os.path.join(root, fname), backup_dir)
                top_dir = rel.split(os.sep)[0]
                if not top_dir.lower().endswith(f"-{project_filter.lower()}"):
                    continue
            # (original filter below)
            if not fname.endswith(".jsonl"):
                continue
            backup_path = os.path.join(root, fname)
            rel = os.path.relpath(backup_path, backup_dir)
            current_path = os.path.join(projects_dir, rel)
            sys.stdout.write(f"    {C_DIM}Checking: {fname[:50]}...{C_RESET}\r")
            sys.stdout.flush()

            if not os.path.isfile(current_path):
                continue

            try:
                backup_size = os.path.getsize(backup_path)
                current_size = os.path.getsize(current_path)
            except OSError:
                continue

            if backup_size <= current_size:
                # Current is already bigger or same — no restore needed
                continue

            try:
                # Read the last line of the backup to find the overlap point
                with open(backup_path, "rb") as f:
                    f.seek(max(0, backup_size - 20000))
                    tail = f.read().decode("utf-8", errors="replace")
                last_backup_line = tail.strip().split("\n")[-1].strip()

                if not last_backup_line:
                    continue

                # Read all lines from the pulled version, find the LAST
                # occurrence of the overlap line to avoid duplicates
                with open(current_path, "r", encoding="utf-8", errors="replace") as f:
                    current_lines = f.readlines()

                last_overlap_idx = -1
                for i, line in enumerate(current_lines):
                    if line.strip() == last_backup_line:
                        last_overlap_idx = i

                if last_overlap_idx >= 0 and last_overlap_idx + 1 < len(current_lines):
                    # Append only lines AFTER the last overlap point
                    new_lines = current_lines[last_overlap_idx + 1:]
                    with open(backup_path, "a", encoding="utf-8") as f:
                        f.writelines(new_lines)
                    shutil.move(backup_path, current_path)
                    restored += 1
                elif backup_size > current_size:
                    # No overlap found but backup has more data — use backup as-is
                    shutil.move(backup_path, current_path)
                    restored += 1

            except Exception as e:
                print(f"  [WARNING] Could not restore {fname}: {e}")
                failed += 1
                continue

    # Only clean up session-originals/ if ALL files were processed successfully
    if os.path.isdir(backup_dir) and failed == 0:
        shutil.rmtree(backup_dir, ignore_errors=True)
    elif failed > 0:
        print(f"  [WARNING] Kept session-originals/ — {failed} file(s) failed to restore.")

    if restored:
        print(f"  [OK] Restored {restored} large session(s) with full history.")
    else:
        print("  No large sessions needed restoring.")


# ═══════════════════════════════════════════════════════
#  RENAME DETECT: Match renamed projects by git remote
# ═══════════════════════════════════════════════════════
def detect_renames(claudecode_dir, new_encoded, project_filter=None):
    """Copy sessions from renamed projects (matched by git remote or cwd)."""
    projects_dir = os.path.join(get_claude_dir(), "projects")
    root_folder = os.path.basename(claudecode_dir)

    # Build local projects -> remote URL map
    local_projects = {}
    for entry in os.listdir(claudecode_dir):
        full = os.path.join(claudecode_dir, entry)
        if os.path.isdir(full) and os.path.exists(os.path.join(full, ".git")):
            try:
                r = subprocess.run(["git", "-C", full, "remote", "get-url", "origin"],
                                   capture_output=True, text=True, timeout=5)
                if r.returncode == 0:
                    url = r.stdout.strip().rstrip("/")
                    if url.endswith(".git"):
                        url = url[:-4]
                    local_projects[entry] = url.lower()
            except Exception:
                pass

    # Find other-PC session folders
    other_folders = {}
    for entry in os.listdir(projects_dir):
        full = os.path.join(projects_dir, entry)
        if not os.path.isdir(full) or is_junction_or_symlink(full):
            continue
        if entry.startswith(new_encoded):
            continue
        if root_folder.upper() not in entry.upper():
            continue
        idx = entry.upper().find(root_folder.upper())
        suffix = entry[idx + len(root_folder):]
        if suffix.startswith("-"):
            other_folders[suffix[1:]] = full

    renamed = 0
    for old_name, old_folder in other_folders.items():
        if project_filter and old_name.lower() != project_filter.lower():
            continue
        # Skip if project exists with same name on this PC
        if os.path.isdir(os.path.join(claudecode_dir, old_name)):
            continue
        # Try matching by cwd in session files
        for local_name, local_remote in local_projects.items():
            if local_name.lower() == old_name.lower():
                continue
            target_dir = os.path.join(projects_dir, f"{new_encoded}-{local_name}")
            if not os.path.isdir(target_dir):
                continue
            # Check if session cwd points to local_name
            matched = False
            try:
                for jsonl in glob.glob(os.path.join(old_folder, "*.jsonl"))[:3]:
                    with open(jsonl, "r", encoding="utf-8", errors="replace") as f:
                        for line in f:
                            if not line.strip():
                                continue
                            try:
                                obj = json.loads(line)
                                cwd = obj.get("cwd", "")
                                if cwd and os.path.basename(os.path.normpath(cwd)).lower() == local_name.lower():
                                    matched = True
                                    break
                            except (json.JSONDecodeError, KeyError):
                                continue
                    if matched:
                        break
            except Exception:
                pass
            if not matched:
                continue
            # Copy sessions (recursive — includes subagents, tool-results, memory)
            copied = 0
            for dirpath, dirnames, filenames in os.walk(old_folder):
                rel = os.path.relpath(dirpath, old_folder)
                tgt_d = os.path.join(target_dir, rel) if rel != "." else target_dir
                os.makedirs(tgt_d, exist_ok=True)
                for fname in filenames:
                    src = os.path.join(dirpath, fname)
                    dst = os.path.join(tgt_d, fname)
                    if not os.path.exists(dst):
                        shutil.copy2(src, dst)
                        copied += 1
            if copied:
                print(f"  [RENAME] {old_name} -> {local_name}: copied {copied} file(s)")
                renamed += copied
            break

    if renamed:
        print(f"  [OK] Copied {renamed} session(s) from renamed projects.")


# ═══════════════════════════════════════════════════════
#  FIX CWD: Correct paths inside session files
# ═══════════════════════════════════════════════════════
def fix_cwd_paths(claudecode_dir, new_encoded, project_filter=None, changed_files=None):
    """Fix cwd fields in session files to match this PC's paths.
    If changed_files is provided, only scans those files (much faster).
    """
    projects_dir = os.path.join(get_claude_dir(), "projects")
    root_folder = os.path.basename(claudecode_dir)
    fixed = 0
    scanned = 0
    cwd_pattern = re.compile(r'"cwd"\s*:\s*"([^"]*)"')
    origin_pattern = re.compile(r'"originCwd"\s*:\s*"([^"]*)"')

    for entry in os.listdir(projects_dir):
        if not entry.startswith(new_encoded):
            continue
        if project_filter and not _dir_matches_project(entry, project_filter):
            continue
        folder = os.path.join(projects_dir, entry)
        if not os.path.isdir(folder):
            continue
        # Determine correct cwd
        suffix = entry[len(new_encoded):]
        if suffix.startswith("-"):
            correct_cwd = os.path.join(claudecode_dir, suffix[1:])
        elif suffix == "":
            correct_cwd = claudecode_dir
        else:
            continue
        correct_cwd = os.path.normpath(correct_cwd)
        # Case-insensitive folder match
        if not os.path.isdir(correct_cwd):
            parent = os.path.dirname(correct_cwd)
            target = os.path.basename(correct_cwd)
            if os.path.isdir(parent):
                for real in os.listdir(parent):
                    if real.lower() == target.lower():
                        correct_cwd = os.path.join(parent, real)
                        break
            if not os.path.isdir(correct_cwd):
                continue

        # Walk all .jsonl files recursively (includes subagents)
        for dirpath, dirnames, filenames in os.walk(folder):
            for jsonl in filenames:
                if not jsonl.endswith(".jsonl"):
                    continue
                scanned += 1
                if scanned % 50 == 0:
                    sys.stdout.write(f"    {C_DIM}Scanned {scanned} files...{C_RESET}\r")
                    sys.stdout.flush()
                fpath = os.path.join(dirpath, jsonl)
                # Skip files that weren't changed by the pull (if we know which changed)
                if changed_files is not None:
                    rel = os.path.relpath(fpath, os.path.dirname(projects_dir))
                    if rel.replace("\\", "/") not in changed_files and rel not in changed_files:
                        continue
                try:
                    # Quick check: read first 10KB to find what cwd is in the file
                    with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                        sample = f.read(10000)
                    sample_cwds = cwd_pattern.findall(sample)
                    if not sample_cwds:
                        continue
                    old_cwd = sample_cwds[0]
                    if os.path.normpath(old_cwd).lower() == correct_cwd.lower():
                        continue  # Already correct — skip

                    # Needs fixing — read full file, do string replace
                    with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read()

                    # Replace all variations of the old cwd with the correct one
                    escaped_correct = correct_cwd.replace("\\", "\\\\")
                    # Replace the escaped version (JSON has double backslashes)
                    old_escaped = old_cwd.replace("\\", "\\\\")
                    new_content = content.replace(old_cwd, escaped_correct)
                    if old_escaped != old_cwd:
                        new_content = new_content.replace(old_escaped, escaped_correct)

                except Exception:
                    continue

                if new_content != content:
                    try:
                        with open(fpath, "w", encoding="utf-8", newline="\n") as f:
                            f.write(new_content)
                        fixed += 1
                    except Exception:
                        pass

    if fixed:
        print(f"  [OK] Fixed cwd in {fixed} of {scanned} session file(s).          ")
    else:
        print(f"  All {scanned} cwd paths already correct.                           ")


# ═══════════════════════════════════════════════════════
#  FIX TIMESTAMPS: Set file mtime from session content
# ═══════════════════════════════════════════════════════
def fix_timestamps(claude_dir, project_filter=None, changed_files=None):
    """Set file mtime to the latest timestamp found in session content.
    If changed_files is provided, only scans those files.
    """
    projects_dir = os.path.join(claude_dir, "projects")
    if not os.path.isdir(projects_dir):
        return
    fixed = 0
    scanned = 0
    ts_re = re.compile(r'"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?)"')

    for root, dirs, files in os.walk(projects_dir):
        if "subagents" in root:
            continue
        if not _walk_matches_project(root, projects_dir, project_filter):
            continue
        for fname in files:
            if not fname.endswith(".jsonl"):
                continue
            scanned += 1
            if scanned % 50 == 0:
                sys.stdout.write(f"    {C_DIM}Checking {scanned} files...{C_RESET}\r")
                sys.stdout.flush()
            fpath = os.path.join(root, fname)
            # Skip files that weren't changed by the pull
            if changed_files is not None:
                rel = os.path.relpath(fpath, os.path.dirname(projects_dir))
                if rel.replace("\\", "/") not in changed_files and rel not in changed_files:
                    continue
            try:
                fsize = os.path.getsize(fpath)
                start = max(0, fsize - 50000)
                with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                    if start > 0:
                        f.seek(start)
                        f.readline()
                    chunk = f.read()
                stamps = ts_re.findall(chunk)
                if not stamps:
                    with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                        stamps = ts_re.findall(f.read(10000))
                if not stamps:
                    continue
                latest = None
                for ts in stamps:
                    try:
                        clean = ts.rstrip("Z")
                        fmt = "%Y-%m-%dT%H:%M:%S.%f" if "." in clean else "%Y-%m-%dT%H:%M:%S"
                        dt = datetime.strptime(clean, fmt).replace(tzinfo=timezone.utc)
                        if latest is None or dt > latest:
                            latest = dt
                    except ValueError:
                        continue
                if latest and abs(os.path.getmtime(fpath) - latest.timestamp()) > 60:
                    os.utime(fpath, (latest.timestamp(), latest.timestamp()))
                    fixed += 1
            except Exception:
                continue

    if fixed:
        print(f"  [OK] Fixed timestamps on {fixed} of {scanned} session file(s).      ")
    else:
        print(f"  All {scanned} timestamps already correct.                            ")


# ═══════════════════════════════════════════════════════
#  FIX PLATFORM CONFIGS: Update OS-specific paths
# ═══════════════════════════════════════════════════════
def fix_platform_configs(claude_dir):
    """Fix platform-specific paths in config files after pull from another OS.

    Handles:
    - known_marketplaces.json  → installLocation
    - installed_plugins.json   → installPath
    """
    fixed = []

    # ── known_marketplaces.json ──
    km_path = os.path.join(claude_dir, "plugins", "known_marketplaces.json")
    if os.path.isfile(km_path):
        try:
            with open(km_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            changed = False
            for name, info in data.items():
                if "installLocation" in info:
                    expected = os.path.join(claude_dir, "plugins", "marketplaces", name)
                    if os.path.normpath(info["installLocation"]) != os.path.normpath(expected):
                        info["installLocation"] = expected
                        changed = True
            if changed:
                with open(km_path, "w", encoding="utf-8", newline="\n") as f:
                    json.dump(data, f, indent=2)
                    f.write("\n")
                fixed.append("known_marketplaces.json")
        except Exception as e:
            print(f"  [WARNING] Could not fix known_marketplaces.json: {e}")

    # ── installed_plugins.json ──
    ip_path = os.path.join(claude_dir, "plugins", "installed_plugins.json")
    if os.path.isfile(ip_path):
        try:
            with open(ip_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            changed = False
            plugins = data.get("plugins", {})
            home_prefix = os.path.expanduser("~").replace("\\", "/") + "/.claude/"
            for plugin_name, installs in plugins.items():
                if not isinstance(installs, list):
                    continue
                for install in installs:
                    if not isinstance(install, dict) or "installPath" not in install:
                        continue
                    old_path = install["installPath"]
                    # Extract relative part using known home prefix
                    normalized = old_path.replace("\\", "/")
                    if normalized.startswith(home_prefix):
                        continue  # Already correct for this platform
                    # Find .claude/ anchored after a path separator
                    anchor = "/.claude/"
                    idx = normalized.find(anchor)
                    if idx >= 0:
                        relative = normalized[idx + len(anchor):]
                        relative_native = relative.replace("/", os.sep)
                        expected = os.path.join(claude_dir, relative_native)
                        install["installPath"] = expected
                        changed = True
            if changed:
                with open(ip_path, "w", encoding="utf-8", newline="\n") as f:
                    json.dump(data, f, indent=2)
                    f.write("\n")
                fixed.append("installed_plugins.json")
        except Exception as e:
            print(f"  [WARNING] Could not fix installed_plugins.json: {e}")

    if fixed:
        print(f"  [OK] Fixed platform paths in: {', '.join(fixed)}")
    else:
        print("  All config paths already correct for this platform.")


# ═══════════════════════════════════════════════════════
#  FIX GITIGNORE: Remove entries that block session sync
# ═══════════════════════════════════════════════════════
def fix_gitignore(claude_dir):
    """Remove project folder entries from .gitignore that block session sync."""
    gitignore = os.path.join(claude_dir, ".gitignore")
    if not os.path.isfile(gitignore):
        return
    with open(gitignore, "r", encoding="utf-8") as f:
        lines = f.readlines()

    new_lines = []
    removed = 0
    skip_header = False
    for line in lines:
        stripped = line.strip()
        # Remove lines that gitignore project session folders (any platform)
        if stripped.startswith("projects/") or stripped.startswith("projects\\"):
            removed += 1
            continue
        # Remove the "Junctions" or "Symlinks" header comment if it's now empty
        if stripped in ("# Junctions (path migration - machine-specific)",
                        "# Symlinks (path migration - machine-specific)"):
            skip_header = True
            continue
        if skip_header and stripped == "":
            skip_header = False
            continue
        skip_header = False
        new_lines.append(line)

    if removed:
        with open(gitignore, "w", encoding="utf-8", newline="\n") as f:
            f.writelines(new_lines)
        print(f"  [OK] Removed {removed} blocking entries from .gitignore.")


# Required .gitignore entries — enforced on every push and pull so all machines
# have the same security and cleanup rules regardless of conflict resolution.
REQUIRED_GITIGNORE = {
    "# Security — never push credentials": [
        ".credentials.json",
    ],
    "# Machine-local state": [
        "stats-cache.json",
        "mcp-needs-auth-cache.json",
        "sessions/",
        "session-originals/",
        "plugins/install-counts-cache.json",
    ],
    "# Platform-specific — keep local version only": [
        "settings.local.json",
    ],
    "# Cache and temp files": [
        "cache/",
        "debug/",
        "telemetry/",
        "shell-snapshots/",
        "session-env/",
        "backups/",
        "paste-cache/",
        "file-history/",
        "metrics/",
        "*.untrimmed",
    ],
    "# Session repair/backup artifacts — never push": [
        "*.jsonl.backup-*",
        "*.jsonl.pre-*",
        "*.jsonl.minimal",
        "*.jsonl.repaired*",
        "*.jsonl.branch-repair",
    ],
    "# Tool result blobs and subagent metadata — machine-local": [
        "projects/*/tool-results/",
        "projects/*/*/tool-results/",
        "projects/*/*.meta.json",
        "projects/*/*/*.meta.json",
    ],
}


def ensure_gitignore_entries(claude_dir):
    """Ensure critical .gitignore entries exist on every machine.

    Runs on both push and pull so the rules propagate even if
    .gitignore conflict resolution kept an older version.
    """
    gitignore = os.path.join(claude_dir, ".gitignore")

    # Read existing content
    existing = set()
    lines = []
    if os.path.isfile(gitignore):
        with open(gitignore, "r", encoding="utf-8") as f:
            lines = f.readlines()
        for line in lines:
            existing.add(line.strip())

    added = 0
    for header, entries in REQUIRED_GITIGNORE.items():
        missing = [e for e in entries if e not in existing]
        if not missing:
            continue
        # Add header if not present
        if header not in existing:
            if lines and lines[-1].strip():
                lines.append("\n")
            lines.append(header + "\n")
        for entry in missing:
            lines.append(entry + "\n")
            added += 1

    if added:
        with open(gitignore, "w", encoding="utf-8", newline="\n") as f:
            f.writelines(lines)
        print(f"  [OK] Added {added} required entries to .gitignore.")
    else:
        print("  .gitignore already has all required entries.")

    # Untrack any files that are now gitignored but still tracked
    for entries in REQUIRED_GITIGNORE.values():
        for entry in entries:
            clean = entry.rstrip("/")
            # Check if actually tracked before running git rm
            r = git_run(claude_dir, "ls-files", "--error-unmatch", clean)
            if r.returncode == 0:  # file is tracked
                if entry.endswith("/"):
                    git_run(claude_dir, "rm", "-r", "--cached", clean)
                else:
                    git_run(claude_dir, "rm", "--cached", clean)


# ═══════════════════════════════════════════════════════
#  PROJECT SETTINGS: Sync .claude.json settings via git remote matching
# ═══════════════════════════════════════════════════════
SYNC_KEYS = ["mcpServers", "allowedTools", "enabledMcpjsonServers", "disabledMcpjsonServers"]


def _get_git_remote(project_path):
    """Get the normalized git remote URL for a project directory."""
    try:
        r = subprocess.run(
            ["git", "-C", project_path, "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=5
        )
        if r.returncode == 0:
            url = r.stdout.strip().rstrip("/")
            if url.endswith(".git"):
                url = url[:-4]
            # Normalize to lowercase org/repo
            for prefix in ["https://github.com/", "git@github.com:"]:
                if url.lower().startswith(prefix.lower()):
                    return url[len(prefix):].lower()
            return url.lower()
    except Exception:
        pass
    return None


def _read_claude_json():
    """Read ~/.claude.json (the root config outside the .claude/ dir)."""
    path = os.path.join(os.path.expanduser("~"), ".claude.json")
    if not os.path.isfile(path):
        return None, path
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f), path
    except Exception:
        return None, path


def export_project_settings(claude_dir, claudecode_dir, project_filter=None):
    """Export project-level settings from .claude.json to a portable file.

    Keyed by git remote (e.g., 'pitir-tech/n8n') so the other machine
    can import them regardless of local path.
    """
    data, _ = _read_claude_json()
    if not data:
        return

    projects = data.get("projects", {})
    exported = {}

    for proj_path, config in projects.items():
        # Only export projects under our CLAUDECODE dir
        norm_path = os.path.normpath(proj_path)
        norm_root = os.path.normpath(claudecode_dir)
        if not norm_path.lower().startswith(norm_root.lower()):
            continue

        # Check if any sync-worthy settings exist
        settings = {}
        for key in SYNC_KEYS:
            val = config.get(key)
            if val is not None and val != [] and val != {}:
                settings[key] = val

        if not settings:
            continue

        # Get git remote for this project
        if os.path.isdir(proj_path):
            remote = _get_git_remote(proj_path)
        else:
            # Project path doesn't exist locally (other platform) — try folder name
            folder = os.path.basename(norm_path)
            local_path = os.path.join(claudecode_dir, folder)
            remote = _get_git_remote(local_path) if os.path.isdir(local_path) else None

        if remote:
            if project_filter and remote != project_filter.lower():
                continue
            exported[remote] = settings

    # Write to .claude/project-settings.json (inside git repo)
    out_path = os.path.join(claude_dir, "project-settings.json")
    if exported:
        with open(out_path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(exported, f, indent=2)
            f.write("\n")
        print(f"  [OK] Exported settings for {len(exported)} project(s).")
    elif os.path.isfile(out_path):
        print("  No project settings to export.")


def import_project_settings(claude_dir, claudecode_dir, project_filter=None):
    """Import project settings from the portable file into .claude.json.

    Matches projects by git remote URL, then copies mcpServers, allowedTools, etc.
    Only fills in settings that are EMPTY locally (never overwrites existing config).
    """
    settings_path = os.path.join(claude_dir, "project-settings.json")
    if not os.path.isfile(settings_path):
        print("  No project settings to import.")
        return

    try:
        with open(settings_path, "r", encoding="utf-8") as f:
            remote_settings = json.load(f)
    except Exception:
        return

    if not remote_settings:
        return

    data, config_path = _read_claude_json()
    if not data:
        return

    projects = data.get("projects", {})

    # Build local remote -> path map
    local_map = {}  # remote -> local project path
    if os.path.isdir(claudecode_dir):
        for entry in os.listdir(claudecode_dir):
            full = os.path.join(claudecode_dir, entry)
            if os.path.isdir(full) and os.path.isdir(os.path.join(full, ".git")):
                remote = _get_git_remote(full)
                if remote:
                    local_map[remote] = full

    applied = 0
    for remote, settings in remote_settings.items():
        if project_filter and remote != project_filter.lower():
            continue
        local_path = local_map.get(remote)
        if not local_path:
            continue

        # Find or create the project entry in .claude.json
        if local_path not in projects:
            # Claude Code may not have created this entry yet — skip
            continue

        config = projects[local_path]
        changed = False
        for key, value in settings.items():
            local_val = config.get(key)
            # Only import if local is empty/missing
            if not local_val and value:
                config[key] = value
                changed = True

        if changed:
            applied += 1

    if applied:
        try:
            with open(config_path, "w", encoding="utf-8", newline="\n") as f:
                json.dump(data, f, indent=2)
                f.write("\n")
            print(f"  [OK] Imported settings for {applied} project(s).")
        except Exception as e:
            print(f"  [WARNING] Could not write .claude.json: {e}")
    else:
        print("  All project settings already up to date.")


# ═══════════════════════════════════════════════════════
#  GIT HELPERS
# ═══════════════════════════════════════════════════════
def git_run(claude_dir, *args, check=False):
    """Run a git command in claude_dir."""
    r = subprocess.run(["git", "-C", claude_dir] + list(args),
                       capture_output=True, text=True)
    return r




def _get_commit_timestamp(claude_dir, ref):
    """Get the commit timestamp for a ref as epoch seconds."""
    r = git_run(claude_dir, "log", "-1", "--format=%ct", ref)
    try:
        return int(r.stdout.strip())
    except (ValueError, AttributeError):
        return 0




def _resolve_pull_conflicts(claude_dir, project_folder=None):
    """Resolve merge conflicts: remote wins entirely after user confirmation.

    For per-project pulls, auto-accepts remote for files outside the project scope
    and only asks about files within the project. Shows a clear summary.
    """
    print(f"  {C_YELLOW}{C_BOLD}[CONFLICTS DETECTED]{C_RESET}")
    print()

    # Get all conflicting files
    cr = git_run(claude_dir, "diff", "--name-only", "--diff-filter=U")
    conflicts = [f.strip() for f in cr.stdout.strip().split("\n") if f.strip()]

    if not conflicts:
        print("  No conflicts to resolve.")
        return

    resolved = []

    # For per-project pulls: keep LOCAL for everything outside the project scope
    # Only the project's own session files get replaced with remote
    if project_folder:
        pf_lower = project_folder.lower()
        in_scope = [f for f in conflicts if pf_lower in f.lower()]
        out_scope = [f for f in conflicts if pf_lower not in f.lower()]

        # Keep local for out-of-scope conflicts (don't touch settings, other projects)
        if out_scope:
            print(f"  {C_DIM}Keeping local for {len(out_scope)} file(s) outside {project_folder} scope.{C_RESET}")
            for f in out_scope:
                git_run(claude_dir, "checkout", "--ours", f)
                git_run(claude_dir, "add", f)
                resolved.append((f, "local", "Kept local (outside project scope)"))

        # If no in-scope conflicts remain, commit and return
        if not in_scope:
            if resolved:
                print(f"  Committing resolution (this may take a moment)...")
                sys.stdout.flush()
                git_run(claude_dir, "commit", "-m", "auto-resolve merge conflicts")
                print(f"  {C_GREEN}[OK] All conflicts resolved (none were for {project_folder}).{C_RESET}")
            return

        # Only show in-scope conflicts to the user
        conflicts = in_scope

    # Get timestamps
    local_ts = _get_commit_timestamp(claude_dir, "HEAD")
    remote_ts = _get_commit_timestamp(claude_dir, "MERGE_HEAD")
    local_date = datetime.fromtimestamp(local_ts).strftime("%Y-%m-%d %H:%M") if local_ts else "unknown"
    remote_date = datetime.fromtimestamp(remote_ts).strftime("%Y-%m-%d %H:%M") if remote_ts else "unknown"

    local_newer = local_ts > remote_ts and local_ts > 0 and remote_ts > 0

    # Show conflict summary
    print(f"  {C_BOLD}{len(conflicts)} file(s) have conflicts:{C_RESET}")
    print()

    for f in conflicts:
        print(f"    {C_DIM}-{C_RESET} {f}")
    print()

    if local_newer:
        print(f"  {C_YELLOW}[WARNING] Your local data is NEWER than the remote.{C_RESET}")
        print(f"  Accepting remote will replace these files with older versions.")
        print(f"  If you have unsaved work, cancel and push first.")
    else:
        print(f"  Remote is newer. Accepting will update these files to the latest version.")
    print()
    print(f"  {C_BOLD}Accept remote version for all conflicts?{C_RESET}")
    print(f"    Y = Replace local with remote")
    print(f"    N = Cancel — resolve manually, then push your version")
    print()

    try:
        answer = input("  Accept remote? (Y/N): ").strip()
    except (EOFError, KeyboardInterrupt):
        answer = ""

    if answer.upper().startswith("Y"):
        # Remote wins for everything
        print()
        print(f"  Resolving {len(conflicts)} conflict(s)...")
        for i, f in enumerate(conflicts, 1):
            print(f"    {C_CYAN}[{i}/{len(conflicts)}]{C_RESET} {f} {C_DIM}-> remote{C_RESET}")
            git_run(claude_dir, "checkout", "--theirs", f)
            git_run(claude_dir, "add", f)
            resolved.append((f, "remote", "Replaced with remote version"))
    else:
        # Local wins for everything
        print()
        print(f"  Keeping local for {len(conflicts)} conflict(s)...")
        for i, f in enumerate(conflicts, 1):
            print(f"    {C_GREEN}[{i}/{len(conflicts)}]{C_RESET} {f} {C_DIM}-> local{C_RESET}")
            git_run(claude_dir, "checkout", "--ours", f)
            git_run(claude_dir, "add", f)
            resolved.append((f, "local", "Kept local version"))

    # Show resolution summary
    if resolved:
        print(f"  ┌─────────────────────────────────────────────────┐")
        print(f"  │  {C_BOLD}CONFLICT RESOLUTION SUMMARY{C_RESET}                     │")
        print(f"  ├─────────────────────────────────────────────────┤")
        for filename, kept, reason in resolved:
            if kept == "merged":
                color = C_YELLOW
                arrow = "MERGED"
            elif kept == "local":
                color = C_GREEN
                arrow = "LOCAL "
            else:
                color = C_CYAN
                arrow = "REMOTE"
            print(f"  │  {color}{arrow}{C_RESET}  {filename}")
            print(f"  │  {C_DIM}         {reason}{C_RESET}")
        print(f"  └─────────────────────────────────────────────────┘")
        print()

    print(f"  Committing resolution (this may take a moment)...")
    sys.stdout.flush()
    git_run(claude_dir, "commit", "-m", "auto-resolve merge conflicts")
    print(f"  {C_GREEN}[OK] All {len(resolved)} conflict(s) resolved.{C_RESET}")
    sys.stdout.flush()


def ensure_git_identity():
    """Ensure git user.name and user.email are set (required for commits on fresh machines)."""
    r = subprocess.run(["git", "config", "--global", "user.name"],
                       capture_output=True, text=True)
    if not r.stdout.strip():
        import getpass
        user = getpass.getuser()
        subprocess.run(["git", "config", "--global", "user.name", user],
                       capture_output=True, text=True)
        subprocess.run(["git", "config", "--global", "user.email",
                        f"{user}@users.noreply.github.com"],
                       capture_output=True, text=True)
        print(f"  [INFO] Git identity set to: {user}")


def ensure_repo(claude_dir):
    """Ensure .claude has a git repo with the correct remote."""
    ensure_git_identity()
    git_dir = os.path.join(claude_dir, ".git")
    if os.path.isdir(git_dir):
        return True
    if os.path.isdir(claude_dir):
        git_run(claude_dir, "init")
        git_run(claude_dir, "remote", "add", "origin", CLI_REPO)
        git_run(claude_dir, "branch", "-M", "main")
        # Commit existing files so pull can merge
        git_run(claude_dir, "add", "-A")
        git_run(claude_dir, "commit", "-m", "local files before first pull")
        return True
    else:
        r = subprocess.run(["git", "clone", CLI_REPO, claude_dir],
                           capture_output=True, text=True)
        return r.returncode == 0


# ═══════════════════════════════════════════════════════
#  STATUS: Show local vs remote context before push/pull
# ═══════════════════════════════════════════════════════
def _show_session_status(claude_dir, mode, project_folder=None):
    """Show detailed local vs remote session status. Returns (ahead, behind) counts."""
    git_run(claude_dir, "fetch", "origin", "main", "--tags")

    # Local info
    local_log = git_run(claude_dir, "log", "-1", "--format=%h  %ad  %s", "--date=format:%Y-%m-%d %H:%M")

    # Remote info
    remote_log = git_run(claude_dir, "log", "-1", "--format=%h  %ad  %s", "--date=format:%Y-%m-%d %H:%M", "origin/main")

    # Ahead/behind
    ahead_r = git_run(claude_dir, "rev-list", "--count", "origin/main..HEAD")
    behind_r = git_run(claude_dir, "rev-list", "--count", "HEAD..origin/main")
    ahead = int(ahead_r.stdout.strip()) if ahead_r.stdout.strip().isdigit() else 0
    behind = int(behind_r.stdout.strip()) if behind_r.stdout.strip().isdigit() else 0

    # Latest session tag
    tags_r = git_run(claude_dir, "tag", "-l", "s*", "--sort=-version:refname")
    latest_tag = ""
    if tags_r.stdout.strip():
        latest_tag = tags_r.stdout.strip().split("\n")[0].strip()
        tag_info = git_run(claude_dir, "log", "-1", "--format=%ad", "--date=format:%Y-%m-%d %H:%M", latest_tag)
        latest_tag_date = tag_info.stdout.strip()
    else:
        latest_tag_date = ""

    print("  ┌─────────────────────────────────────────────────┐")
    print("  │  SESSION SYNC STATUS                            │")
    print("  ├─────────────────────────────────────────────────┤")
    print(f"  │  Local:  {local_log.stdout.strip()[:46]:<46} │" if local_log.stdout.strip() else "  │  Local:  (no commits)                          │")
    print(f"  │  Remote: {remote_log.stdout.strip()[:46]:<46} │" if remote_log.stdout.strip() else "  │  Remote: (no commits)                          │")
    if latest_tag:
        print(f"  │  Latest tag: {latest_tag} ({latest_tag_date}){' ' * max(0, 30 - len(latest_tag) - len(latest_tag_date))}│")
    print(f"  │  Local ahead: {ahead} commit(s)  Behind: {behind} commit(s){' ' * max(0, 15 - len(str(ahead)) - len(str(behind)))}│")
    print("  └─────────────────────────────────────────────────┘")
    print()

    # Check for uncommitted changes (files modified on disk but not yet committed)
    dirty = git_run(claude_dir, "status", "--porcelain")
    dirty_files = [l.strip() for l in dirty.stdout.strip().split("\n") if l.strip()]

    # Filter by project if scoped
    if project_folder:
        pf_lower = project_folder.lower()
        dirty_files = [f for f in dirty_files if pf_lower in f.lower()]

    if dirty_files:
        modified = [f for f in dirty_files if not f.startswith("D ") and not f.startswith(" D")]
        deleted = [f for f in dirty_files if f.startswith("D ") or f.startswith(" D")]
        if modified:
            print(f"  {C_YELLOW}+ {len(modified)} changed file(s) on disk{C_RESET}")
            for df in modified:
                print(f"    {C_DIM}{df}{C_RESET}")
            print()
        if deleted:
            print(f"  {C_DIM}- {len(deleted)} file(s) removed from tracking (gitignore cleanup){C_RESET}")
            print()

    # Show what will be affected — summary only, conflicts shown later
    if mode == "push":
        real_changes = [f for f in dirty_files if not f.startswith("D ") and not f.startswith(" D")] if dirty_files else []
        if real_changes:
            print(f"  {C_BOLD}{len(real_changes)} file(s) will be pushed.{C_RESET}")
            print()
    elif mode == "pull":
        if behind > 0:
            diff = git_run(claude_dir, "diff", "--name-only", "HEAD", "origin/main")
            changed = [f.strip() for f in diff.stdout.strip().split("\n") if f.strip()]

            # Filter by project if scoped
            if project_folder:
                changed = [f for f in changed if pf_lower in f.lower()]

            if changed:
                print(f"  {C_BOLD}Pulling {latest_tag}: {len(changed)} file(s) for this project to update.{C_RESET}")
                print(f"  {C_DIM}Conflicts (if any) will be shown after pull.{C_RESET}")
                print()
            else:
                print(f"  {C_BOLD}No changes for this project in {latest_tag}.{C_RESET}")
                print()
        if dirty_files:
            if project_folder:
                # Per-project pull: commits all local changes, merges remote.
                # On conflict: remote wins for THIS project, local wins for everything else.
                print(f"  {C_DIM}[INFO] {len(dirty_files)} uncommitted local change(s) will be committed before merge.{C_RESET}")
                print(f"  {C_DIM}On conflict: remote wins for {project_folder}, local wins for all other projects.{C_RESET}")
            else:
                # All-project pull: reset --hard replaces everything
                print(f"  {C_YELLOW}[WARNING] Your {len(dirty_files)} uncommitted local change(s) will be replaced by the remote version.{C_RESET}")
                print(f"  {C_DIM}If you have unsaved work, cancel and push first.{C_RESET}")
                print(f"  {C_DIM}Large files (>90MB) are backed up in Step 2.{C_RESET}")
            print()

    return ahead, behind, bool(dirty_files)


def _categorize_changes(claude_dir, diff_range):
    """Split changed files into sessions vs config."""
    diff = git_run(claude_dir, "diff", "--name-only", diff_range)
    sessions = []
    config = []
    for f in diff.stdout.strip().split("\n"):
        f = f.strip()
        if not f:
            continue
        if f.startswith("projects/"):
            sessions.append(f)
        else:
            config.append(f)
    return sessions, config


def _show_change_categories(sessions, config, verb):
    """Show categorized changes and return what to include."""
    if not sessions and not config:
        return True, True

    if sessions or config:
        parts = []
        if sessions:
            parts.append(f"{len(sessions)} session file(s)")
        if config:
            parts.append(f"{len(config)} config file(s)")
        print(f"  {C_BOLD}To {verb}: {', '.join(parts)}{C_RESET}")
        print()

    # If both have changes, ask separately
    include_sessions = True
    include_config = True

    if sessions and config:
        print(f"  What would you like to {verb}?")
        print(f"    1) Both sessions + config  (default)")
        print(f"    2) Sessions only (keep local config)")
        print(f"    3) Config only (keep local sessions)")
        print(f"    N) Cancel")
        print()
        try:
            choice = input("  Choice [1]: ").strip()
        except (EOFError, KeyboardInterrupt):
            choice = "1"
        if choice.upper() == "N":
            print("  Cancelled.")
            return None, None
        if choice == "2":
            include_config = False
        elif choice == "3":
            include_sessions = False
    else:
        try:
            answer = input(f"  Continue with {verb}? (Y/N): ").strip()
        except (EOFError, KeyboardInterrupt):
            answer = "Y"
        if not answer.upper().startswith("Y"):
            print("  Cancelled.")
            return None, None

    print()
    return include_sessions, include_config


def _confirm_session_push(claude_dir):
    """Check session status before push. Returns True if safe to proceed."""
    ahead, behind, has_dirty = _show_session_status(claude_dir, "push")

    if behind > 0:
        print(f"  {C_YELLOW}[WARNING] Remote has {behind} commit(s) you haven't pulled.{C_RESET}")
        print("  These were pushed from another machine.")
        print("  Pushing now will OVERWRITE them (force push).")
        print("  To merge instead, run pull-all-sessions first.")
        print()
        try:
            answer = input("  Overwrite remote? (Y to overwrite / N to cancel): ").strip()
        except (EOFError, KeyboardInterrupt):
            answer = ""
        if not answer.upper().startswith("Y"):
            print("  Cancelled.")
            return False
        print()
    elif ahead == 0 and behind == 0:
        if has_dirty:
            print("  [INFO] Commits match remote. Uncommitted local changes will be pushed.")
        else:
            print("  [INFO] Already up to date. Nothing to push.")
            return False
        print()
        try:
            answer = input("  Continue with push? (Y/N): ").strip()
        except (EOFError, KeyboardInterrupt):
            answer = "Y"
        if not answer.upper().startswith("Y"):
            print("  Cancelled.")
            return False
        print()
    else:
        print(f"  [OK] You have {ahead} local commit(s) to push.")
        print()
        try:
            answer = input("  Continue with push? (Y/N): ").strip()
        except (EOFError, KeyboardInterrupt):
            answer = "Y"
        if not answer.upper().startswith("Y"):
            print("  Cancelled.")
            return False
        print()
    return True


def _confirm_session_pull(claude_dir, per_project=False, project_folder=None):
    """Check session status before pull. Returns True if safe to proceed.

    For all-session pulls, also asks whether to include config changes
    or sessions only, when both types of changes are detected.
    Per-project pulls skip the category question.
    """
    ahead, behind, _ = _show_session_status(claude_dir, "pull", project_folder=project_folder)

    if behind == 0 and ahead == 0:
        print("  [INFO] Already up to date with remote.")
        print()
        try:
            answer = input("  Pull anyway to ensure consistency? (Y/N): ").strip()
        except (EOFError, KeyboardInterrupt):
            answer = "Y"
        if not answer.upper().startswith("Y"):
            print("  Cancelled.")
            return False
        print()
    elif behind == 0 and ahead > 0:
        print(f"  {C_YELLOW}[WARNING] Your local sessions are NEWER than remote ({ahead} unpushed commit(s)).{C_RESET}")
        print("  The remote may have stale/older sessions from another machine.")
        print("  Pulling is safe (merge only adds missing files, never overwrites),")
        print("  but consider pushing first to update the remote.")
        print()
        try:
            answer = input("  Continue with pull? (Y/N): ").strip()
        except (EOFError, KeyboardInterrupt):
            answer = "Y"
        if not answer.upper().startswith("Y"):
            print("  Cancelled.")
            return False
        print()
    elif behind > 0:
        if per_project:
            # Per-project: just confirm, no category question
            try:
                answer = input("  Continue with pull? (Y/N): ").strip()
            except (EOFError, KeyboardInterrupt):
                answer = "Y"
            if not answer.upper().startswith("Y"):
                print("  Cancelled.")
                return False
            print()
        else:
            # Root pull: show categorized changes and let user choose
            sessions, config = _categorize_changes(claude_dir, "HEAD..origin/main")
            inc_s, inc_c = _show_change_categories(sessions, config, "pull")
            if inc_s is None:
                return False
        # Store choices for later use by the pull pipeline
        # (currently not used — git pull is atomic, can't partial pull)
        # But the user at least sees the breakdown and confirms
    return True


# ═══════════════════════════════════════════════════════
#  PUSH MODE
# ═══════════════════════════════════════════════════════
def push_sessions(claudecode_dir):
    claude_dir = get_claude_dir()
    if not ensure_repo(claude_dir):
        print("  [ERROR] Could not set up session repo.")
        return False

    # ── Safety check with full context ──
    if not _confirm_session_push(claude_dir):
        return False

    print("  Step 1: Fix .gitignore...")
    fix_gitignore(claude_dir)
    ensure_gitignore_entries(claude_dir)

    print("\n  Step 2: Export project settings...")
    export_project_settings(claude_dir, claudecode_dir)

    print("\n  Step 3: Trim oversized files...")
    trim_oversized(claude_dir)

    print("\n  Step 4: Prepare commit...")
    # Fetch and soft-reset to avoid large files in history
    git_run(claude_dir, "fetch", "origin", "main", "--tags")
    git_run(claude_dir, "reset", "--soft", "origin/main")
    # Stage everything except backup/repair artifacts
    git_run(claude_dir, "add", "-A")
    git_run(claude_dir, "reset", "--", "**/*.untrimmed")
    git_run(claude_dir, "reset", "--", "**/*.jsonl.backup-*")
    git_run(claude_dir, "reset", "--", "**/*.jsonl.pre-*")
    git_run(claude_dir, "reset", "--", "**/*.jsonl.minimal")
    git_run(claude_dir, "reset", "--", "**/*.jsonl.repaired*")
    git_run(claude_dir, "reset", "--", "**/*.jsonl.branch-repair")

    # Check if anything to push
    r = git_run(claude_dir, "diff", "--cached", "--quiet")
    if r.returncode == 0:
        print("  No session changes to push.")
        archive_to_session_originals(claude_dir)
        restore_untrimmed(claude_dir)
        return True

    # Get next s-tag
    r = git_run(claude_dir, "tag", "-l", "s*", "--sort=-version:refname")
    last_num = 0
    for tag in r.stdout.strip().split("\n"):
        tag = tag.strip()
        if tag.startswith("s"):
            try:
                num = int(tag[1:])
                if num > last_num:
                    last_num = num
                    break
            except ValueError:
                continue
    next_tag = f"s{last_num + 1}"

    print(f"\n  Step 5: Commit and push as {next_tag}...")
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    git_run(claude_dir, "commit", "-m", f"[{next_tag}] sessions push {now}")
    git_run(claude_dir, "tag", "-a", next_tag, "-m", "sessions push")
    r = git_run(claude_dir, "push", "origin", "main", "--tags", "--force")
    if r.returncode != 0:
        print(f"  [ERROR] Push failed:\n{r.stderr[-500:]}")
        # Clean up the local tag so it doesn't block future pushes
        git_run(claude_dir, "tag", "-d", next_tag)
        git_run(claude_dir, "reset", "--soft", "HEAD~1")
        print(f"  [OK] Rolled back commit and deleted tag {next_tag}.")
        restore_untrimmed(claude_dir)
        return False

    print(f"  [OK] Sessions pushed as {next_tag}")

    print("\n  Step 6: Archive + restore originals...")
    archive_to_session_originals(claude_dir)
    restore_untrimmed(claude_dir)
    return True


# ═══════════════════════════════════════════════════════
#  PULL MODE
# ═══════════════════════════════════════════════════════
def pull_sessions(claudecode_dir):
    claude_dir = get_claude_dir()
    new_encoded = encode_path(claudecode_dir)
    root_folder = os.path.basename(claudecode_dir)

    print(f"  This PC: {claudecode_dir}")
    print(f"  Encoded: {new_encoded}\n")

    if not ensure_repo(claude_dir):
        print("  [ERROR] Could not set up session repo.")
        return False

    if not _confirm_session_pull(claude_dir):
        return False

    print("  Step 1: Fix .gitignore...")
    fix_gitignore(claude_dir)
    ensure_gitignore_entries(claude_dir)

    print("\n  Step 2: Backup large originals...")
    backup_originals(claude_dir)

    print("\n  Step 3: Pull from GitHub...")
    sys.stdout.write("    Fetching remote...")
    sys.stdout.flush()
    git_run(claude_dir, "fetch", "--tags", "--force")
    print(" done.")
    # Track which files will change (for targeted fix_cwd and fix_timestamps)
    changed_r = git_run(claude_dir, "diff", "--name-only", "HEAD", "origin/main")
    changed_files = set(f.strip() for f in changed_r.stdout.strip().split("\n") if f.strip())
    sys.stdout.write(f"    Updating to latest ({len(changed_files)} files)...")
    sys.stdout.flush()
    git_run(claude_dir, "reset", "--hard", "origin/main")
    print(" done.")
    print(f"  {C_GREEN}[OK] Pulled successfully.{C_RESET}")

    print("\n  Step 4: Materialize symlinks...")
    materialize_symlinks(claude_dir, new_encoded)

    print("\n  Step 5: Merge sessions from other PC(s)...")
    merge_sessions(claude_dir, new_encoded, root_folder)

    print("\n  Step 6: Detect renamed projects...")
    detect_renames(claudecode_dir, new_encoded)

    print("\n  Step 7: Fix cwd paths...")
    fix_cwd_paths(claudecode_dir, new_encoded)

    print("\n  Step 8: Fix platform configs...")
    fix_platform_configs(claude_dir)

    print("\n  Step 9: Clean up other-PC dirs...")
    cleanup_old_dirs(claude_dir, new_encoded, root_folder)

    print("\n  Step 10: Fix timestamps (all files — reset replaces all)...")
    fix_timestamps(claude_dir)

    print("\n  Step 11: Sync project settings...")
    import_project_settings(claude_dir, claudecode_dir)

    print("\n  [OK] Session sync complete.")
    return True


# ═══════════════════════════════════════════════════════
#  PER-PROJECT PUSH
# ═══════════════════════════════════════════════════════
def push_project(claudecode_dir, project_remote):
    """Push only one project's sessions (incremental commit, regular push)."""
    claude_dir = get_claude_dir()
    if not ensure_repo(claude_dir):
        print("  [ERROR] Could not set up session repo.")
        return False

    # Resolve project folder
    project_folder = resolve_project_folder(claudecode_dir, project_remote)
    if not project_folder:
        print(f"  [WARNING] Could not find local folder for {project_remote}. Skipping session sync.")
        return True  # Not a fatal error — project code was already pushed

    print(f"  Project: {project_remote} -> folder: {project_folder}\n")

    # Show session status scoped to this project
    _show_session_status(claude_dir, "push", project_folder=project_folder)

    print("  Step 1: Fix .gitignore...")
    fix_gitignore(claude_dir)
    ensure_gitignore_entries(claude_dir)

    print("\n  Step 2: Export project settings...")
    export_project_settings(claude_dir, claudecode_dir, project_filter=project_remote)

    print("\n  Step 3: Trim oversized files...")
    trim_oversized(claude_dir, project_filter=project_folder)

    print("\n  Step 4: Stage project files...")
    new_encoded = encode_path(claudecode_dir)
    # Stage only this project's session dirs + shared configs
    project_dir_pattern = f"projects/*-{project_folder}"
    # Also stage the exact match for this PC's encoding
    this_pc_dir = f"projects/{new_encoded}-{project_folder}"

    # Commit any pending changes first
    git_run(claude_dir, "add", this_pc_dir)
    git_run(claude_dir, "add", project_dir_pattern)
    git_run(claude_dir, "add", "settings.json")
    git_run(claude_dir, "add", "plugins/")
    git_run(claude_dir, "add", "project-settings.json")
    git_run(claude_dir, "add", ".gitignore")
    git_run(claude_dir, "add", "history.jsonl")
    # Don't stage backup/repair artifacts
    git_run(claude_dir, "reset", "--", "**/*.untrimmed")
    git_run(claude_dir, "reset", "--", "**/*.jsonl.backup-*")
    git_run(claude_dir, "reset", "--", "**/*.jsonl.pre-*")
    git_run(claude_dir, "reset", "--", "**/*.jsonl.minimal")
    git_run(claude_dir, "reset", "--", "**/*.jsonl.repaired*")
    git_run(claude_dir, "reset", "--", "**/*.jsonl.branch-repair")

    # Check if anything to push
    r = git_run(claude_dir, "diff", "--cached", "--quiet")
    if r.returncode == 0:
        print("  No session changes to push.")
        restore_untrimmed(claude_dir, project_filter=project_folder)
        return True

    print("\n  Step 5: Commit and push...")
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    git_run(claude_dir, "commit", "-m", f"[{project_folder}] sessions {now}")

    r = git_run(claude_dir, "push", "origin", "main", "--tags")
    if r.returncode != 0:
        # Rebase and retry
        print("  Push failed, rebasing...")
        r2 = git_run(claude_dir, "pull", "--rebase", "origin", "main")
        if r2.returncode != 0:
            print("  [WARNING] Rebase failed. Try running root pull first.")
            restore_untrimmed(claude_dir, project_filter=project_folder)
            return False
        r = git_run(claude_dir, "push", "origin", "main", "--tags")
        if r.returncode != 0:
            print(f"  [ERROR] Push failed:\n{r.stderr[-500:]}")
            restore_untrimmed(claude_dir, project_filter=project_folder)
            return False

    print(f"  [OK] Sessions for {project_folder} pushed.")

    print("\n  Step 6: Archive + restore originals...")
    archive_to_session_originals(claude_dir, project_filter=project_folder)
    restore_untrimmed(claude_dir, project_filter=project_folder)
    return True


# ═══════════════════════════════════════════════════════
#  PER-PROJECT PULL
# ═══════════════════════════════════════════════════════
def pull_project(claudecode_dir, project_remote):
    """Pull sessions and process only one project's dirs."""
    claude_dir = get_claude_dir()
    new_encoded = encode_path(claudecode_dir)
    root_folder = os.path.basename(claudecode_dir)

    # Resolve project folder
    project_folder = resolve_project_folder(claudecode_dir, project_remote)
    if not project_folder:
        print(f"  [WARNING] Could not find local folder for {project_remote}. Skipping session sync.")
        return True

    print(f"  Project: {project_remote} -> folder: {project_folder}")
    print(f"  Encoded: {new_encoded}\n")

    if not ensure_repo(claude_dir):
        print("  [ERROR] Could not set up session repo.")
        return False

    # Show session status (per-project: skip category question)
    if not _confirm_session_pull(claude_dir, per_project=True, project_folder=project_folder):
        return False

    print("  Step 1: Fix .gitignore...")
    fix_gitignore(claude_dir)
    ensure_gitignore_entries(claude_dir)

    print("\n  Step 2: Backup large originals...")
    backup_originals(claude_dir, project_filter=project_folder)

    print("\n  Step 3: Pull from GitHub...")
    # Per-project: use git pull (not reset --hard) to preserve other projects' data
    sys.stdout.write("    Committing local changes...")
    sys.stdout.flush()
    git_run(claude_dir, "add", "-A")
    r = git_run(claude_dir, "diff", "--cached", "--quiet")
    if r.returncode != 0:
        git_run(claude_dir, "commit", "-m", f"local changes before {project_folder} pull")
        print(" done.")
    else:
        print(" nothing to commit.")
    sys.stdout.write("    Fetching remote...")
    sys.stdout.flush()
    git_run(claude_dir, "fetch", "--tags", "--force")
    print(" done.")
    # Track which files will change
    changed_r = git_run(claude_dir, "diff", "--name-only", "HEAD", "origin/main")
    changed_files = set(f.strip() for f in changed_r.stdout.strip().split("\n") if f.strip())
    sys.stdout.write(f"    Merging ({len(changed_files)} files)...")
    sys.stdout.flush()
    r = git_run(claude_dir, "pull", "origin", "main",
                "--no-rebase", "--allow-unrelated-histories", "--no-edit")
    if r.returncode != 0:
        print(" conflicts detected.")
        _resolve_pull_conflicts(claude_dir, project_folder=project_folder)
    else:
        print(" done.")
        print(f"  {C_GREEN}[OK] Pulled successfully.{C_RESET}")

    # Full migration — fix ALL projects (git pulled everything anyway)

    print("\n  Step 4: Materialize symlinks...")
    materialize_symlinks(claude_dir, new_encoded)

    print("\n  Step 5: Merge sessions from other PC(s)...")
    merge_sessions(claude_dir, new_encoded, root_folder)

    print("\n  Step 6: Detect renamed projects...")
    detect_renames(claudecode_dir, new_encoded)

    print("\n  Step 7: Fix cwd paths...")
    fix_cwd_paths(claudecode_dir, new_encoded, changed_files=changed_files)

    print("\n  Step 8: Fix platform configs...")
    fix_platform_configs(claude_dir)

    print("\n  Step 9: Clean up other-PC dirs...")
    cleanup_old_dirs(claude_dir, new_encoded, root_folder)

    print("\n  Step 10: Fix timestamps...")
    fix_timestamps(claude_dir, changed_files=changed_files)

    print("\n  Step 11: Import project settings...")
    import_project_settings(claude_dir, claudecode_dir)

    print(f"\n  [OK] Session sync for {project_folder} complete.")
    return True


# ═══════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CLI session sync")
    parser.add_argument("mode", choices=["push", "pull"])
    parser.add_argument("claudecode_dir")
    parser.add_argument("--project", default=None,
                        help="Git remote slug (e.g., pitir-tech/n8n) for per-project sync")
    args = parser.parse_args()

    claudecode_dir = os.path.normpath(args.claudecode_dir)
    print()

    if args.project:
        # Per-project mode
        label = args.project.split("/")[-1] if "/" in args.project else args.project
        if args.mode == "push":
            print("=" * 54)
            print(f"  PUSH {label.upper()} SESSIONS TO GITHUB")
            print("=" * 54)
            print()
            ok = push_project(claudecode_dir, args.project)
        else:
            print("=" * 54)
            print(f"  PULL {label.upper()} SESSIONS FROM GITHUB")
            print("=" * 54)
            print()
            ok = pull_project(claudecode_dir, args.project)
    else:
        # All-project mode
        if args.mode == "push":
            print("=" * 54)
            print("  PUSH ALL SESSIONS TO GITHUB")
            print("=" * 54)
            print()
            ok = push_sessions(claudecode_dir)
        else:
            print("=" * 54)
            print("  PULL ALL SESSIONS FROM GITHUB")
            print("=" * 54)
            print()
            ok = pull_sessions(claudecode_dir)

    print()
    sys.exit(0 if ok else 1)

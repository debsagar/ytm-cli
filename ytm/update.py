"""ytm update: move this copy of the code to the latest release.

A pinned copy (detached, like the ytm-stable worktree) jumps to origin/main; a
normal clone on a branch is fast-forwarded. Library, history and settings live
outside the code, so they are never touched. Local edits make git refuse."""

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def git(*args):
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True)


def main():
    r = git("fetch", "-q", "origin")
    if r.returncode == 0:
        pinned = git("symbolic-ref", "-q", "HEAD").returncode != 0
        r = git("checkout", "-q", "--detach", "origin/main") if pinned else git("pull", "-q", "--ff-only")
    if r.returncode:
        print("update failed, nothing was changed:", r.stderr.strip() or r.stdout.strip())
        return 1
    # Safe while this python runs: sync only touches site-packages, and nothing from there is imported here.
    try:
        r = subprocess.run(["uv", "sync", "-q", "--frozen", "--no-dev"], cwd=ROOT, capture_output=True, text=True)
    except FileNotFoundError:
        r = subprocess.CompletedProcess([], 1, "", "uv not found")
    if r.returncode:
        print("code updated, but installing packages failed (fix that, then run ytm update again):",
              r.stderr.strip() or r.stdout.strip())
        return 1
    version = re.search(r'__version__ = "(.+?)"', (ROOT / "ytm" / "__init__.py").read_text(encoding="utf-8"))
    print("ytm is now", version.group(1) if version else "updated", f"({git('rev-parse', '--short', 'HEAD').stdout.strip()})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

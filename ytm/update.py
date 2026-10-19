"""ytm update: move this copy of the code to the latest release.

`ytm update` follows the branch this copy is on: a normal clone is fast-forwarded, a
pinned copy (a detached HEAD) jumps to origin/main. `ytm update stable` and `ytm update
dev` switch the copy to the main or dev branch first. Packages are synced to the
code's uv.lock either way, so going back to stable is a full rollback. Library and
history (git-ignored, or in the ytm.home folder) and settings (~/.config/ytm) are never
touched. Local edits make git refuse."""

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHANNELS = {"stable": "main", "dev": "dev"}


def git(*args):
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True)


def current_branch():
    r = git("symbolic-ref", "-q", "--short", "HEAD")
    return r.stdout.strip() if r.returncode == 0 else None


def switch(branch):
    """Fast-forward the local branch from origin, then check it out. Git refuses a
    non-fast-forward or a checkout over local edits, and each step changes all or nothing."""
    if current_branch() == branch:
        return git("pull", "-q", "--ff-only", "origin", branch)
    # Creates the branch if this clone only has main, fast-forwards it otherwise.
    r = git("fetch", "-q", "origin", f"{branch}:{branch}")
    if r.returncode == 0:
        r = git("checkout", "-q", branch, "--")  # "--": the repo also has a dev/ folder
    if r.returncode == 0:
        git("branch", "-q", f"--set-upstream-to=origin/{branch}", branch)
    return r


def main(args=None):
    args = [a for a in (sys.argv[1:] if args is None else args) if a]  # ytm.cmd passes "" for no word
    if len(args) > 1 or (args and args[0].lower() not in CHANNELS):
        print("usage: ytm update [stable|dev]")
        return 2
    r = git("fetch", "-q", "origin")
    if r.returncode == 0:
        if args:
            r = switch(CHANNELS[args[0].lower()])
        elif current_branch() is None:
            r = git("checkout", "-q", "--detach", "origin/main")
        else:
            r = git("pull", "-q", "--ff-only")
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
    branch = current_branch()
    channel = {"main": "stable", "dev": "dev", None: "stable (pinned)"}.get(branch, branch)
    print("ytm is now", version.group(1) if version else "updated",
          f"({git('rev-parse', '--short', 'HEAD').stdout.strip()}) · {channel}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

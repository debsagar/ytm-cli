"""Local data: play history. Reads the history.tsv written by mpv/scripts/history.lua.

(Step 4 of the plan moves this to SQLite and adds playlists; the UI won't change.)
"""

from .player import MPV_CONFIG
from .search import Track

HISTORY = MPV_CONFIG / "history.tsv"


def history(limit=50):
    """Most recent plays first, one entry per song."""
    if not HISTORY.exists():
        return []
    out, seen = [], set()
    for line in reversed(HISTORY.read_text(encoding="utf-8", errors="replace").splitlines()):
        parts = line.split("\t", 2)
        if len(parts) != 3 or "v=" not in parts[1]:
            continue
        vid = parts[1].split("v=", 1)[1][:11]
        if vid in seen:
            continue
        seen.add(vid)
        out.append(Track(vid, parts[2]))
        if len(out) >= limit:
            break
    return out

"""Local data: play history (history.tsv, written by mpv/scripts/history.lua),
plus liked songs and playlists in a small SQLite database (data/ytm.db)."""

import sqlite3
import threading
import time

from .player import MPV_CONFIG, ROOT
from .search import Track

HISTORY = MPV_CONFIG / "history.tsv"
DB = ROOT / "data" / "ytm.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS tracks (id TEXT PRIMARY KEY, title TEXT, artist TEXT, duration TEXT);
CREATE TABLE IF NOT EXISTS likes (id TEXT PRIMARY KEY, at REAL);
CREATE TABLE IF NOT EXISTS playlists (name TEXT PRIMARY KEY, created REAL);
CREATE TABLE IF NOT EXISTS playlist_items (
    playlist TEXT, id TEXT, pos INTEGER,
    PRIMARY KEY (playlist, id)
);
"""


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


class Library:
    def __init__(self, path=DB):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.executescript(SCHEMA)
        self.lock = threading.Lock()

    def _q(self, sql, args=()):
        with self.lock, self.db:
            return self.db.execute(sql, args).fetchall()

    def _save(self, t: Track):
        self._q("INSERT OR REPLACE INTO tracks VALUES (?,?,?,?)", (t.video_id, t.title, t.artist, t.duration))

    def _tracks(self, sql, args=()):
        return [Track(*row) for row in self._q(sql, args)]

    # ---- likes ----
    def liked_ids(self):
        return {r[0] for r in self._q("SELECT id FROM likes")}

    def toggle_like(self, t: Track):
        """Returns True if the song is now liked."""
        if self._q("SELECT 1 FROM likes WHERE id=?", (t.video_id,)):
            self._q("DELETE FROM likes WHERE id=?", (t.video_id,))
            return False
        self._save(t)
        self._q("INSERT INTO likes VALUES (?,?)", (t.video_id, time.time()))
        return True

    def liked(self):
        return self._tracks(
            "SELECT t.id, t.title, t.artist, t.duration FROM likes l JOIN tracks t ON t.id=l.id ORDER BY l.at DESC")

    # ---- playlists ----
    def playlists(self):
        """[(name, song count)] newest first."""
        return self._q(
            "SELECT p.name, COUNT(i.id) FROM playlists p LEFT JOIN playlist_items i ON i.playlist=p.name "
            "GROUP BY p.name ORDER BY p.created DESC")

    def add_to_playlist(self, name, tracks):
        """Adds songs (skipping ones already in it); creates the playlist if needed. Returns how many were added."""
        self._q("INSERT OR IGNORE INTO playlists VALUES (?,?)", (name, time.time()))
        start = self._q("SELECT COALESCE(MAX(pos), 0) FROM playlist_items WHERE playlist=?", (name,))[0][0]
        added = 0
        for t in tracks:
            self._save(t)
            if not self._q("SELECT 1 FROM playlist_items WHERE playlist=? AND id=?", (name, t.video_id)):
                added += 1
                self._q("INSERT INTO playlist_items VALUES (?,?,?)", (name, t.video_id, start + added))
        return added

    def playlist(self, name):
        return self._tracks(
            "SELECT t.id, t.title, t.artist, t.duration FROM playlist_items i JOIN tracks t ON t.id=i.id "
            "WHERE i.playlist=? ORDER BY i.pos", (name,))

    def remove_from_playlist(self, name, video_id):
        self._q("DELETE FROM playlist_items WHERE playlist=? AND id=?", (name, video_id))

    def delete_playlist(self, name):
        self._q("DELETE FROM playlist_items WHERE playlist=?", (name,))
        self._q("DELETE FROM playlists WHERE name=?", (name,))

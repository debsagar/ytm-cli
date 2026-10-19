"""Local data: play history (history.tsv, written by mpv/scripts/history.lua),
plus liked songs and playlists in a small SQLite database (data/ytm.db)."""

import json
import sqlite3
import threading
import time

from .player import HOME
from .search import Track

HISTORY = HOME / "mpv" / "history.tsv"
DB = HOME / "data" / "ytm.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS tracks (id TEXT PRIMARY KEY, title TEXT, artist TEXT, duration TEXT, album TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS likes (id TEXT PRIMARY KEY, at REAL);
CREATE TABLE IF NOT EXISTS playlists (name TEXT PRIMARY KEY, created REAL);
CREATE TABLE IF NOT EXISTS playlist_items (
    playlist TEXT, id TEXT, pos INTEGER,
    PRIMARY KEY (playlist, id)
);
CREATE TABLE IF NOT EXISTS features (id TEXT PRIMARY KEY, data TEXT);  -- Jev judgment per song
CREATE TABLE IF NOT EXISTS themes (name TEXT PRIMARY KEY, spec TEXT, created REAL);  -- LLM-written themes
CREATE TABLE IF NOT EXISTS centres (name TEXT PRIMARY KEY, vec TEXT);  -- learned cluster centres
CREATE TABLE IF NOT EXISTS events (at REAL, type TEXT, id TEXT, data TEXT);  -- play/skip/tweak signals
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
        if "album" not in [r[1] for r in self.db.execute("PRAGMA table_info(tracks)")]:  # older databases
            self.db.execute("ALTER TABLE tracks ADD COLUMN album TEXT DEFAULT ''")
            self.db.commit()
        self.lock = threading.Lock()

    def _q(self, sql, args=()):
        with self.lock, self.db:
            return self.db.execute(sql, args).fetchall()

    def _save(self, t: Track):
        # a track from history has no album or duration: keep the ones already stored
        self._q("INSERT INTO tracks VALUES (?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET title=excluded.title, "
                "artist=excluded.artist, duration=COALESCE(NULLIF(excluded.duration, ''), duration), "
                "album=COALESCE(NULLIF(excluded.album, ''), album)",
                (t.video_id, t.title, t.artist, t.duration, t.album))

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
            "SELECT t.id, t.title, t.artist, t.duration, t.album FROM likes l JOIN tracks t ON t.id=l.id ORDER BY l.at DESC")

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
            "SELECT t.id, t.title, t.artist, t.duration, t.album FROM playlist_items i JOIN tracks t ON t.id=i.id "
            "WHERE i.playlist=? ORDER BY i.pos", (name,))

    def remove_from_playlist(self, name, video_id):
        self._q("DELETE FROM playlist_items WHERE playlist=? AND id=?", (name, video_id))

    # ---- song features, themes, events (the memory the brain reads) ----
    def features(self, video_id):
        row = self._q("SELECT data FROM features WHERE id=?", (video_id,))
        return json.loads(row[0][0]) if row else None

    def save_features(self, video_id, data):
        self._q("INSERT OR REPLACE INTO features VALUES (?,?)", (video_id, json.dumps(data)))

    def centres(self):
        return {n: json.loads(v) for n, v in self._q("SELECT name, vec FROM centres")}

    def set_centre(self, name, vec):
        self._q("INSERT OR REPLACE INTO centres VALUES (?,?)", (name, json.dumps(vec)))

    def remember(self, video_id, title, artist, album=""):
        self._q("INSERT OR IGNORE INTO tracks VALUES (?,?,?,?,?)", (video_id, title, artist, "", album))

    def all_features(self):
        return {vid: json.loads(d) for vid, d in self._q("SELECT id, data FROM features")}

    def song(self, video_id):
        row = self._q("SELECT title, artist, album FROM tracks WHERE id=?", (video_id,))
        return {"title": row[0][0], "artist": row[0][1], "album": row[0][2] or ""} if row else None

    def themes(self):
        return [json.loads(r[0]) for r in self._q("SELECT spec FROM themes ORDER BY created")]

    def themes_since(self, at):
        """How many themes were written since a unix time."""
        return self._q("SELECT COUNT(*) FROM themes WHERE created>=?", (at,))[0][0]

    def save_theme(self, spec):
        self._q("INSERT OR REPLACE INTO themes VALUES (?,?,?)", (spec["name"], json.dumps(spec), time.time()))

    def log(self, type_, video_id="", **data):
        self._q("INSERT INTO events VALUES (?,?,?,?)", (time.time(), type_, video_id, json.dumps(data)))

    def spend(self, since=0.0):
        """{api: (calls, usd)} for paid calls logged since a unix time."""
        rows = self._q("SELECT json_extract(data, '$.api'), COUNT(*), SUM(json_extract(data, '$.usd')) "
                       "FROM events WHERE type='cost' AND at>=? GROUP BY 1", (since,))
        return {api: (n, usd or 0.0) for api, n, usd in rows}

    def delete_playlist(self, name):
        self._q("DELETE FROM playlist_items WHERE playlist=?", (name,))
        self._q("DELETE FROM playlists WHERE name=?", (name,))

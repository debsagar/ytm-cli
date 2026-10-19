"""YouTube Music lookups via ytmusicapi (public data only, no login)."""

import re
from dataclasses import dataclass

from ytmusicapi import YTMusic

_yt = None
# The song id in a link: watch?v=ID or youtu.be/ID (history.lua logs whichever mpv was given)
VID_RE = re.compile(r"(?:v=|youtu\.be/)([\w-]{11})", re.I)  # links may be typed in capitals


def _api():
    global _yt
    if _yt is None:
        _yt = YTMusic()
    return _yt


@dataclass
class Track:
    video_id: str
    title: str
    artist: str = ""
    duration: str = ""
    album: str = ""

    @property
    def url(self):
        return f"https://music.youtube.com/watch?v={self.video_id}"

    @property
    def label(self):
        return f"{self.artist} - {self.title}" if self.artist else self.title


def _track(item):
    artists = ", ".join(a["name"] for a in item.get("artists") or [] if a.get("name"))
    album = (item.get("album") or {}).get("name") or ""
    return Track(item["videoId"], item.get("title", "?"), artists, item.get("duration") or item.get("length") or "", album)


def search(query, limit=10):
    """Top song results for a query."""
    items = _api().search(query, filter="songs", limit=limit)
    return [_track(i) for i in items if i.get("videoId")][:limit]


def radio(video_id, limit=50):
    """A YT Music mix seeded from one track (the seed comes first)."""
    data = _api().get_watch_playlist(videoId=video_id, radio=True, limit=limit)
    return [_track(i) for i in data.get("tracks", []) if i.get("videoId")]

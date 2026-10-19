"""Import public/unlisted YouTube Music playlists into the library.

    python -m ytm.importer <playlist url> [<playlist url> ...] [--judge]

--judge also asks Jev about every new song now (about $0.00002 each), so themes
and taste data are ready before you press play."""

import re
import sys

from . import brain, library, settings
from .search import _api, _track

LIST_RE = re.compile(r"[?&]list=([\w-]+)")


def import_playlist(lib, url):
    m = LIST_RE.search(url)
    if not m:
        raise ValueError(f"no playlist id in {url}")
    p = _api().get_playlist(m.group(1), limit=None)
    tracks = [_track(t) for t in p["tracks"] if t.get("videoId")]
    added = lib.add_to_playlist(p["title"], tracks)
    return p["title"], tracks, added


def main(args):
    judge = "--judge" in args
    lib = library.Library()
    for url in [a for a in args if not a.startswith("--") and a != "import"]:  # ytm.cmd passes "import" too
        title, tracks, added = import_playlist(lib, url)
        print(f"{title}: {len(tracks)} songs ({added} new)")
        for i, t in enumerate(tracks, 1):
            if judge and not lib.features(t.video_id):
                jev, llm, why = brain.budget(lib, settings.Settings())  # re-checked per song
                if not jev:
                    print(f"  stopped judging: {why}")
                    break
                f = brain.think({"id": t.video_id, "title": t.title, "artist": t.artist}, lib, llm)
                print(f"  {i:>3}/{len(tracks)} {t.title[:40]:40} {f['theme']} · {f['mood']} · {f['tags']}")


if __name__ == "__main__":
    main(sys.argv[1:])

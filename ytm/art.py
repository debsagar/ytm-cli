"""Album art for the terminal: the song's thumbnail drawn with half-block
characters. Each cell shows two pixels: '▀' coloured with the top pixel as
foreground and the bottom pixel as background. Costs only a tiny image in memory."""

import io
import urllib.request

from rich.style import Style
from rich.text import Text

_cache = {}  # (video id, w, h) -> Text; a handful of entries at most


def fetch(video_id, width, height):
    """Returns a Rich Text of width x height cells, or None if there is no thumbnail."""
    key = (video_id, width, height)
    if key in _cache:
        return _cache[key]
    from PIL import Image  # imported lazily: only costs memory once art is shown

    url = f"https://i.ytimg.com/vi/{video_id}/mqdefault.jpg"  # 320x180
    try:
        data = urllib.request.urlopen(url, timeout=8).read()
    except OSError:
        return None
    img = Image.open(io.BytesIO(data)).convert("RGB")
    w, h = img.size
    side = min(w, h)  # centre square: album covers sit in the middle of the 16:9 frame
    img = img.crop(((w - side) // 2, (h - side) // 2, (w + side) // 2, (h + side) // 2))
    img = img.resize((width, height * 2), Image.LANCZOS)
    px = img.load()

    text = Text()
    for y in range(0, height * 2, 2):
        for x in range(width):
            top, bottom = px[x, y], px[x, y + 1]
            text.append("▀", Style(color="rgb(%d,%d,%d)" % top, bgcolor="rgb(%d,%d,%d)" % bottom))
        if y < height * 2 - 2:
            text.append("\n")
    if len(_cache) > 8:
        _cache.clear()
    _cache[key] = text
    return text

"""Theme specs: the small JSON "language" that describes how the player looks.

Both the LLM and the instant controls produce the same spec; the app only ever
draws from the primitives below, so any spec (even a broken one) renders safely.

  {
    "name": "pit lane",
    "palette": {"bg": "#0b0b0b", "panel": "#161616", "accent": "#e10600", "accent2": "#ffffff",
                "text": "#f2f2f2", "dim": "#7a7a7a"},
    "motif": "checkered",               # one of MOTIFS
    "progress": {"style": "track", "cursor": "🏎", "label": "LAP {lap}/{laps}"},
    "headline": "Lights out and away we go",
    "blurb": "From F1: The Movie (2025)"
  }
"""

import math
import re
import unicodedata

HEX = re.compile(r"^#[0-9a-fA-F]{6}$")

# A short pattern repeated across the top of the now-playing panel.
MOTIFS = {
    "none": "",
    "checkered": "▚▞",
    "waves": "∿~",
    "stars": "✦ · ✧ · ",
    "rain": "╎ ¦ ",
    "dots": "· ",
    "grid": "┼─",
    "hearts": "♥ ♡ ",
    "flames": "▲▴^▵",
    "vinyl": "◉ ○ ",
    "zigzag": "╱╲",
    "blocks": "▁▂▃▅▇▅▃▂",
    "notes": "♪ ♫ ♬ ",
    "leaves": "❦ ❧ ",
    "circuit": "─┬─┴",
    "sun": "☼ ",
}

# Progress bar styles: (filled char, empty char, default cursor)
PROGRESS = {
    "line": ("━", "━", ""),
    "track": ("═", "─", "●"),
    "dots": ("●", "·", ""),
    "blocks": ("█", "░", ""),
    "wave": ("≋", "∼", ""),
    "thin": ("─", "─", "◆"),
}

VIBES = ["calm", "normal", "loud"]

# How the screen is arranged. A theme picks one; the vibe control can override it.
LAYOUTS = {
    "classic": "album art left, song list below",
    "hero": "big album art and a spaced-out title, short list",
    "stage": "animated equaliser instead of art, list below",
    "focus": "just the song, centred; no list",
    "dashboard": "four panels: player, ask, library, visualizer (needs 100x30)",
}

DEFAULT = {
    "name": "default", "for": "neutral fallback: songs with no strong mood or setting",
    "palette": {"bg": "#1e1e2e", "panel": "#181825", "accent": "#cba6f7", "accent2": "#f5c2e7",
                "text": "#cdd6f4", "dim": "#6c7086"},
    "motif": "none",
    "progress": {"style": "line", "cursor": "", "label": "{pos} / {dur}"},
    "headline": "",
    "blurb": "",
}

# The 13 seed themes. Each is a cluster centre: "centre" describes the typical song
# (energy 0..1, mood weights, context tags) in the same terms Jev measures songs.
def _t(name, for_, centre, bg, panel, accent, accent2, text, dim, motif, style, cursor="", label="{pos} / {dur}",
       layout="classic"):
    return {"name": name, "for": for_, "centre": centre, "motif": motif, "layout": layout,
            "palette": {"bg": bg, "panel": panel, "accent": accent, "accent2": accent2, "text": text, "dim": dim},
            "progress": {"style": style, "cursor": cursor, "label": label}}


PRESETS = [
    _t("neon rave", "euphoric club and dance music", {"energy": .9, "mood": {"euphoric": 1}, "tags": ["club"]},
       "#0b0716", "#130b24", "#ff3cac", "#2bd2ff", "#f3eaff", "#7a6a99", "blocks", "blocks", layout="stage"),
    _t("pit wall", "motorsport, racing and speed", {"energy": .8, "mood": {"aggressive": 1}, "tags": ["motorsport", "soundtrack"]},
       "#0d0d10", "#1a1a20", "#ff2d2d", "#ffd400", "#f2f2f2", "#6b6b78", "checkered", "track", "🏎", "LAP {lap}/{laps}  {pos}", layout="hero"),
    _t("dream haze", "dreamy, hazy, psychedelic indie", {"energy": .3, "mood": {"dreamy": 1}, "tags": []},
       "#1d1730", "#161126", "#c8a2ff", "#ffb3d9", "#efe6ff", "#7f72a3", "stars", "wave"),
    _t("desi street", "high-energy South Asian rap and hip-hop", {"energy": .75, "mood": {"aggressive": 1}, "tags": ["south_asian"]},
       "#1a1208", "#120c05", "#ff9933", "#19c37d", "#fff3e0", "#8a7458", "zigzag", "dots", layout="hero"),
    _t("desi soul", "soft, emotional South Asian songs", {"energy": .35, "mood": {"melancholic": .5, "romantic": .5}, "tags": ["south_asian"]},
       "#220f14", "#180a0e", "#e8b04b", "#d9466f", "#fbe9dc", "#8d6a6f", "notes", "thin", "◆"),
    _t("dark techno", "dark, heavy, peak-time club music", {"energy": .9, "mood": {"dark": 1}, "tags": ["club"]},
       "#0a0a0a", "#050505", "#e0e0e0", "#ff1f3d", "#d8d8d8", "#5c5c5c", "grid", "blocks", "", "{pct}%", layout="stage"),
    _t("velvet", "romantic, sensual, slow-burning songs", {"energy": .4, "mood": {"romantic": 1}, "tags": []},
       "#1f0d16", "#16090f", "#ff6f91", "#ffc2d1", "#ffe8ee", "#8f6574", "hearts", "thin", "♥", layout="focus"),
    _t("retro tape", "nostalgic, retro, throwback songs", {"energy": .55, "mood": {"nostalgic": 1}, "tags": []},
       "#1c1712", "#14100c", "#f4a259", "#5bc0be", "#f6efe6", "#857565", "vinyl", "line"),
    _t("gold rush", "hype rap, swagger and bangers", {"energy": .85, "mood": {"aggressive": 1}, "tags": []},
       "#0f0c06", "#0a0804", "#ffd166", "#ef476f", "#fff6dc", "#857a5c", "flames", "track", "●", layout="hero"),
    _t("campfire", "acoustic, folk and soft singer-songwriter", {"energy": .2, "mood": {"melancholic": .5, "happy": .5}, "tags": []},
       "#1b2420", "#141b18", "#a6e3a1", "#f9e2af", "#e2efe6", "#6f8577", "leaves", "dots", layout="focus"),
    _t("cinema", "film and game soundtracks, epic and dramatic", {"energy": .6, "mood": {"dark": .5, "euphoric": .5}, "tags": ["soundtrack"]},
       "#0b1020", "#070b17", "#4ea8de", "#ffd166", "#e8eefc", "#5f6b8a", "dots", "thin", "◆", layout="hero"),
    _t("sunny day", "happy, upbeat, feel-good pop", {"energy": .65, "mood": {"happy": 1}, "tags": []},
       "#1c1a10", "#15130b", "#ffd23f", "#3bceac", "#fffbea", "#8c8660", "sun", "wave"),
    _t("rainy window", "sad, melancholic, late-night songs", {"energy": .25, "mood": {"melancholic": 1}, "tags": []},
       "#10151c", "#0b0f14", "#7aa2c7", "#b8c7d9", "#e3ebf3", "#5d6b7a", "rain", "thin", layout="focus"),
]


def _hex(c, fallback):
    return c if isinstance(c, str) and HEX.match(c) else fallback


def _mix(a, b, t):
    """Blend two #rrggbb colours: t=0 gives a, t=1 gives b."""
    ca = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    cb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(ca, cb))


def normalize(spec):
    """Return a complete, safe theme: unknown or missing fields fall back to the default."""
    spec = spec if isinstance(spec, dict) else {}
    pal_in = spec.get("palette") if isinstance(spec.get("palette"), dict) else {}
    palette = {k: _hex(pal_in.get(k), v) for k, v in DEFAULT["palette"].items()}
    prog_in = spec.get("progress") if isinstance(spec.get("progress"), dict) else {}
    style = prog_in.get("style") if prog_in.get("style") in PROGRESS else "line"
    return {
        "name": str(spec.get("name") or "untitled")[:30],
        "for": str(spec.get("for") or "")[:200],
        "palette": palette,
        "motif": spec.get("motif") if spec.get("motif") in MOTIFS else "none",
        "layout": spec.get("layout") if spec.get("layout") in LAYOUTS else "classic",
        "progress": {
            "style": style,
            "cursor": str(prog_in.get("cursor") or PROGRESS[style][2])[:2],
            "label": str(prog_in.get("label") or "{pos} / {dur}")[:30],
        },
        "headline": str(spec.get("headline") or "")[:80],
        "blurb": str(spec.get("blurb") or "")[:160],
        **{k: spec[k] for k in ("centre", "vec") if k in spec},  # cluster position, kept as-is
    }


def colors(theme):
    """The full colour set the UI uses, derived from the theme's six colours."""
    p = theme["palette"]
    return {
        "base": p["bg"], "mantle": p["panel"], "crust": _mix(p["panel"], "#000000", 0.35),
        "s0": _mix(p["bg"], p["text"], 0.10), "s1": _mix(p["bg"], p["text"], 0.22),
        "dim": p["dim"], "sub": _mix(p["text"], p["dim"], 0.45), "text": p["text"],
        "mauve": p["accent"], "pink": p["accent2"], "blue": p["accent"], "green": p["accent2"],
        "peach": p["accent2"], "red": "#f38ba8",
    }


def apply_vibe(theme, vibe):
    """Instant control: calm strips decoration, loud adds it."""
    t = {**theme, "progress": dict(theme["progress"])}
    if vibe == "calm":
        t["layout"] = "focus"
        t["motif"] = "none"
        t["blurb"] = ""
        t["progress"]["cursor"] = ""
    elif vibe == "loud":
        t["layout"] = "stage"
        if t["motif"] == "none":
            t["motif"] = "notes"
    return t


def motif_line(theme, width, offset=0):
    """The motif repeated across `width`, shifted by `offset` so it scrolls over time."""
    pat = MOTIFS.get(theme["motif"], "")
    if not pat or width <= 0:
        return ""
    k = offset % len(pat)
    return (pat * (width // len(pat) + 2))[k:k + width]


BARS = " ▁▂▃▄▅▆▇█"
EIGHTHS = " ▏▎▍▌▋▊▉"  # a cell filled from the left, in eighths


def equaliser(width, rows, t, energy, levels=None, dt=0.0):
    """A decorative equaliser: one-cell bars with a gap between, swaying with time `t` and song
    energy (0..1). Not real audio analysis: that would mean decoding the stream ourselves.
    `levels` (a list kept by the caller) makes each bar ease toward its target over `dt` seconds:
    quick to rise, slow to fall, so frames never jump."""
    full = rows * 8
    n = (width + 1) // 2
    targets = []
    for x in range(n):
        wave = (math.sin(x * 0.55 + t * 2.3) + math.sin(x * 0.23 - t * 1.3) + 0.5 * math.sin(x * 1.3 + t * 3.7)) / 2.5
        targets.append((0.2 + 0.7 * energy) * (0.55 + 0.45 * wave) * full)
    if levels is None:
        levels = []
    if len(levels) != n:  # first frame, or a new width: start on target
        levels[:] = targets
    for i, goal in enumerate(targets):
        rate = 14 if goal > levels[i] else 5  # per second
        levels[i] += (goal - levels[i]) * (1 - math.exp(-rate * dt))
    cells = [max(1, min(full, round(lv))) for lv in levels]
    lines = []
    for r in range(rows - 1, -1, -1):  # top row first
        lines.append(" ".join(BARS[max(0, min(8, lv - r * 8))] for lv in cells)[:width])
    return "\n".join(lines)


def spaced(title):
    """HERO TITLE STYLE: uppercase with letter spacing. Accents stay attached to their letter."""
    chars = []
    for ch in unicodedata.normalize("NFC", title.upper()):
        if chars and unicodedata.combining(ch):
            chars[-1] += ch
        else:
            chars.append(ch)
    return " ".join(chars)


def fmt(s):
    if s is None:
        return "-:--"
    s = max(0, int(s))
    return f"{s // 60}:{s % 60:02d}"


def _clamp(pos, dur):
    """Position within [0, duration]: mpv can briefly report past the end, or negative."""
    pos = max(0, pos or 0)
    return min(pos, dur) if dur else pos


def progress_label(theme, pos, dur):
    """Fill the theme's label template. Only the five known {names} are replaced (no str.format:
    LLM-written templates could otherwise pad to any width or reach Python internals)."""
    pos = _clamp(pos, dur)
    laps = 4
    vals = {"pos": fmt(pos), "dur": fmt(dur), "pct": int(100 * pos / dur) if dur else 0,
            "lap": min(laps, int(laps * pos / dur) + 1) if dur else 1, "laps": laps}
    out = re.sub(r"\{(\w+)\}", lambda m: str(vals.get(m.group(1), m.group(0))), theme["progress"]["label"])
    if "{" in out or "}" in out:
        return f"{fmt(pos)} / {fmt(dur)}"
    return out[:30]


def progress_bar(theme, width, pos, dur):
    """(filled, cursor, empty) strings for a bar `width` cells wide. The solid "blocks" style
    ends in an eighth-block cell, so the head creeps instead of jumping a whole cell."""
    full, empty, _ = PROGRESS[theme["progress"]["style"]]
    cursor = theme["progress"]["cursor"]
    width = max(4, width - len(cursor))
    eighths = int(8 * width * _clamp(pos, dur) / dur) if dur else 0
    filled, part = divmod(eighths, 8)
    if full != "█" or cursor or not part or filled >= width:
        return full * filled, cursor, empty * (width - filled)
    return full * filled + EIGHTHS[part], cursor, empty * (width - filled - 1)

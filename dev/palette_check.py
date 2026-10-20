"""Self-check for theme.readable (the palette rules normalize enforces) and brain.motion.

    uv run python dev/palette_check.py

Pure code: no app, no network. Exits non-zero on the first broken rule."""

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ytm import brain, theme  # noqa: E402

BAD = [  # what a careless theme writer could return
    {"bg": "#3b0a45", "panel": "#0a4b35", "accent": "#5a2a6a", "accent2": "#00ff00", "text": "#8a6a90", "dim": "#7a5a80"},
    {"bg": "#2b3a10", "panel": "#5a2a10", "accent": "#4a5a20", "accent2": "#ff0000", "text": "#7a8a50", "dim": "#7a8a50"},
    {"bg": "#c8d8e8", "panel": "#ffffff", "accent": "#e0f0ff", "accent2": "#ffcc00", "text": "#ffffff", "dim": "#dddddd"},
    {"bg": "#ffffff", "panel": "#000000", "accent": "#000000", "accent2": "#000000", "text": "#000000", "dim": "#000000"},
]

for t in theme.PRESETS + [theme.DEFAULT]:
    assert theme.readable(t["palette"]) == t["palette"], f"preset {t['name']} changed"

rnd = random.Random(1)
FUZZ = [{k: f"#{rnd.randrange(1 << 24):06x}" for k in BAD[0]} for _ in range(300)]

for p in BAD + FUZZ + [t["palette"] for t in theme.PRESETS]:
    q = theme.readable(p)
    c = {k: theme.contrast(q[k], q["bg"]) for k in q}
    assert theme._lum(q["bg"]) <= 0.02, q
    assert c["text"] >= 7 and c["accent"] >= 3 and c["accent2"] >= 3 and c["dim"] >= 3, (p, q, c)
    assert c["dim"] < c["text"], (p, q)
    gap = abs((theme._hls(q["accent2"])[0] - theme._hls(q["accent"])[0] + 0.5) % 1 - 0.5) * 360
    assert not 62 < gap < 118 or min(theme._hls(q[k])[2] for k in ("accent", "accent2")) < 0.15, (q, gap)
    assert theme.readable(q) == q, f"not stable: {q}"

old = {"energy": 0.8, "mood_p": {"dark": 1}, "tag_p": {"club": 1}}  # cached before pace/bright/texture
assert brain.motion(old) == {"energy": 0.8, "pace": 0.8, "bright": 0.0, "texture": 0.9}, brain.motion(old)
assert brain.motion({}) == {"energy": 0.5, "pace": 0.5, "bright": 0.5, "texture": 0.3}
assert brain.motion({**old, "pace": 0.2, "bright": 0.9, "texture": 0.1})["pace"] == 0.2
print("palette and motion: OK")

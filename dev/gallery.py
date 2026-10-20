"""Mock widget arrangements drawn with the real renderers and themes, saved as SVGs. Dev only:
it never starts the app's player, and the app's behaviour is untouched.

    uv run python dev/gallery.py [--out DIR] [--only NAME ...]    the gallery boards
    uv run python dev/gallery.py --measure [--only app|NAME ...]   shrink every widget, print min sizes
    uv run python dev/gallery.py --count                          how many widgets fit per terminal size

A board is a character map: each letter is one widget, its bounding box becomes a grid cell with
column-span/row-span (Textual has no grid-template-areas), "." is an empty cell. Widgets marked
"mock" don't exist in ytm yet (stats, clock, lyrics, queue, gauge)."""

import argparse
import asyncio
import colorsys
import importlib.util
import os
import sys
from pathlib import Path

os.environ.pop("NO_COLOR", None)
REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from textual.app import App  # noqa: E402
from textual.containers import Container, Horizontal, Vertical  # noqa: E402
from textual.widget import Widget  # noqa: E402
from textual.widgets import Input, Label, ListItem, ListView, Static  # noqa: E402

from ytm import pixel, theme  # noqa: E402
from ytm.app import TABS, Btn, keys  # noqa: E402

_spec = importlib.util.spec_from_file_location("ytm_try", REPO / "dev" / "try.py")
TRY = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(TRY)  # screen_text, and run() for measuring the real app's panels

OUT = Path(r"C:\Users\User\.claude\jobs\c3b1c854\tmp\s3\sizes")
SONGS = [("Midnight City", "M83", "4:03"), ("Blinding Lights", "The Weeknd", "3:20"),
         ("Kesariya", "Arijit Singh", "4:28"), ("Smooth Operator", "Sade", "4:58"),
         ("Lose Yourself", "Eminem", "5:20"), ("Tum Hi Ho", "Arijit Singh", "4:22"),
         ("Get Lucky", "Daft Punk", "6:09"), ("Dreams", "Fleetwood Mac", "4:14"),
         ("Strobe", "deadmau5", "10:37"), ("Clocks", "Coldplay", "5:07")]
POS, DUR = 83, 243
DIGITS = {"0": "█▀█ █ █ █▄█", "1": "▀█   █  ▄█▄", "2": "▀▀█ █▀▀ █▄▄", "3": "▀▀█  ▀█ ▄▄█", "4": "█ █ ▀▀█   █",
          "5": "█▀▀ ▀▀█ ▄▄█", "6": "█▀▀ █▀█ █▄█", "7": "▀▀█   █   █", "8": "█▀█ █▀█ █▄█", "9": "█▀█ ▀▀█ ▄▄█",
          ":": " ▪▪"}  # the colon: one cell per row


def big(s):
    """Three-row block digits; 4 cells per digit, 2 per colon."""
    rows = ["", "", ""]
    for ch in s:
        d = DIGITS[ch]
        for r in range(3):
            rows[r] += d[r * 4:r * 4 + 3] + " " if ch != ":" else d[r] + " "
    return [r.rstrip() for r in rows]


class Draw(Widget):
    """Redraws from a function of its content size, like the app's motif/eq/bar do on tick."""
    DEFAULT_CSS = "Draw { height: 1fr; text-wrap: nowrap; text-overflow: ellipsis; }"

    def __init__(self, fn, **kw):
        super().__init__(**kw)
        self.fn = fn

    def render(self):
        return self.fn(self.content_size.width, self.content_size.height)


def _hue(hex_, turn):
    r, g, b = (int(hex_[i:i + 2], 16) / 255 for i in (1, 3, 5))
    h, lum, s = colorsys.rgb_to_hls(r, g, b)
    return "#" + "".join(f"{round(v * 255):02x}" for v in colorsys.hls_to_rgb((h + turn) % 1, lum, s))


def accents(c):
    """Six accents from the theme's two, so each widget gets its own border colour."""
    a, z = c["mauve"], c["pink"]
    return [a, z, _hue(a, 1 / 3), _hue(z, 1 / 3), _hue(a, -1 / 6), _hue(z, -1 / 6)]


# ---- widgets: name -> (title, mock?, builder(board) -> list of children) ----
# A builder reads b.c once; box() swaps in the widget's own accent as "mauve" while it builds.
def _bar(b, c, w, label=True):
    right = f"  {theme.progress_label(b.t, POS, DUR)}" if label else ""
    full, cur, empty = theme.progress_bar(b.t, max(4, w - len(right)), POS, DUR)
    return f"[{c['mauve']}]{full}[/][b {c['pink']}]{cur}[/][{c['s1']}]{empty}[/][{c['sub']}]{right}[/]"


def w_now(b):
    c = b.c
    return [Draw(lambda w, h: f"[{c['mauve']}]{theme.motif_line(b.t, w)}[/]\n[b {c['pink']}]{SONGS[0][0]}[/]\n"
                 f"[{c['sub']}]{SONGS[0][1]}[/]\n{_bar(b, c, w)}", classes="fit"), controls(b)]


def w_mini(b):
    c = b.c
    return [Draw(lambda w, h: f"[b {c['pink']}]{SONGS[0][0]}[/] [{c['sub']}]· {SONGS[0][1]}[/]\n{_bar(b, c, w)}")]


def w_clock(b):
    c = b.c

    def f(w, h):
        rows = big(theme.fmt(POS))
        pad = " " * max(0, (w - len(rows[0])) // 2)
        return ("\n".join(f"{pad}[b {c['mauve']}]{r}[/]" for r in rows)
                + f"\n{_bar(b, c, w, label=False)}\n[{c['sub']}]{SONGS[0][0]}[/]")
    return [Draw(f)]


def controls(b, rows=1):
    a = [Btn("⏮"), Btn("⏸", classes="big"), Btn("⏭"), Btn("♥"), Btn("−"), Btn("+")]
    z = [Btn("∞"), Btn("◐"), Btn("▦")]
    if rows == 1:
        return Horizontal(*a, *z, classes="ctl")
    return Vertical(Horizontal(*a, classes="ctl"), Horizontal(*z, classes="ctl"), classes="ctl2")


def song_list(n=len(SONGS)):
    return ListView(*[ListItem(Label(f"{i + 1:>2}  {t} · {a}  {d}")) for i, (t, a, d) in enumerate(SONGS[:n])],
                    classes="list")


def w_library(b):
    return [Horizontal(*[Btn(v, classes="tab" + (" current" if v == "history" else "")) for v in TABS[:4]],
                       classes="ctl"),
            Horizontal(*[Btn(x, classes="act") for x in ("▶ play", "+ queue", "♥ like", "≡ playlist")], classes="ctl"),
            song_list()]


def w_prompt(b):
    c = b.c
    return [Static(f"[{c['peach']}]theme: {b.t['name']}[/]", classes="msg"),
            Input(placeholder="search a song, or ? for help", classes="prompt")]


def w_viz(b):
    c = b.c
    return [Draw(lambda w, h: pixel.Bars().frame(w, max(1, h), 1.3, {"energy": 0.8, "pace": 0.8}, pixel.palette(b.t), 0)),
            Static(f"[{c['dim']}]{b.t['name']} · euphoric · energy 80%[/]", classes="cap")]


def w_art(b):
    a, z = b.c["mauve"], b.c["pink"]

    def f(w, h):
        lines = []
        for y in range(h):
            row = ""
            for x in range(w):
                t1, t2 = (x / max(1, w) + 2 * y / max(1, 2 * h)) / 2, (x / max(1, w) + (2 * y + 1) / max(1, 2 * h)) / 2
                row += f"[{theme._mix(a, z, t1)} on {theme._mix(a, z, t2)}]▀[/]"
            lines.append(row)
        return "\n".join(lines)
    return [Draw(f)]


def w_stats(b):
    c = b.c
    hours = [0, 0, 1, 0, 0, 0, 0, 2, 4, 3, 1, 0, 2, 5, 6, 4, 3, 2, 1, 4, 7, 8, 5, 2]

    def f(w, h):
        spark = "".join(theme.BARS[min(8, v)] for v in hours)[-max(1, w):]
        lines = [f"[b {c['pink']}]23[/] [{c['sub']}]plays today[/]", f"[b {c['pink']}]1h 12m[/] [{c['sub']}]listened[/]",
                 f"[{c['mauve']}]{spark}[/]", f"[{c['dim']}]top: Arijit Singh ×6[/]"]
        return "\n".join(lines[:max(1, h)])
    return [Draw(f)]


def w_queue(b):
    c = b.c
    return [Draw(lambda w, h: "\n".join(f"[{c['dim']}]{i + 1}[/] {t} [{c['dim']}]· {a}[/]"
                                        for i, (t, a, _) in enumerate(SONGS[1:1 + max(1, h)])))]


def w_lyrics(b):
    c = b.c
    lines = ["The city is my church", "It wraps me in the sparkling twilight", "Waiting in a car",
             "Waiting for a ride in the dark", "Drinking in the lounge", "Following the neon signs"]

    def f(w, h):
        mid = min(len(lines) - 1, max(0, h // 2 - 1))
        out = [f"[{c['dim']}]{x}[/]" for x in lines[:mid]] + [f"[b {c['pink']}]{lines[mid]}[/]"]
        return "\n".join(out + [f"[{c['sub']}]{x}[/]" for x in lines[mid + 1:h]])
    return [Draw(f)]


def w_gauge(b):
    c = b.c
    t = {**b.t, "progress": {"style": "blocks", "cursor": "", "label": ""}}

    def f(w, h):
        bw = max(4, w - 8)
        e = theme.progress_bar(t, bw, 80, 100)
        v = theme.progress_bar(t, bw, 35, 100)
        return (f"[{c['sub']}]energy[/]  [{c['pink']}]{e[0]}[/][{c['s1']}]{e[2]}[/]\n"
                f"[{c['sub']}]valence[/] [{c['mauve']}]{v[0]}[/][{c['s1']}]{v[2]}[/]\n[{c['dim']}]mood: euphoric[/]")
    return [Draw(f)]


def w_motif(b):
    c = b.c
    return [Draw(lambda w, h: "\n".join(f"[{c['mauve'] if r % 2 else c['pink']}]{theme.motif_line(b.t, w, r * 3)}[/]"
                                        for r in range(h)))]


WIDGETS = {  # name: (border title, mock, builder)
    "now": ("now playing", False, w_now), "mini": ("mini player", False, w_mini),
    "clock": ("clock", True, w_clock), "controls": ("controls", False, lambda b: [controls(b)]),
    "controls2": ("controls", False, lambda b: [controls(b, 2)]), "library": ("library", False, w_library),
    "list": ("list", False, lambda b: [song_list()]), "prompt": ("ask", False, w_prompt),
    "viz": ("visualizer", False, w_viz), "art": ("art", False, w_art), "stats": ("stats", True, w_stats),
    "queue": ("up next", True, w_queue), "lyrics": ("lyrics", True, w_lyrics), "gauge": ("mood", True, w_gauge),
    "motif": ("motif", False, w_motif),
}


def areas(rows):
    """Character map -> [(key, col, row, col_span, row_span)] in row-major order of top-left corners,
    which is the order Textual's grid auto-places children in. Each letter must be one rectangle."""
    boxes, seen = [], set()
    for y, line in enumerate(rows):
        for x, ch in enumerate(line):
            if ch == "." or ch in seen:
                if ch == ".":
                    boxes.append((".", x, y, 1, 1))
                continue
            seen.add(ch)
            cells = [(i, j) for j, ln in enumerate(rows) for i, k in enumerate(ln) if k == ch]
            x1, y1 = max(i for i, _ in cells), max(j for _, j in cells)
            assert len(cells) == (x1 - x + 1) * (y1 - y + 1), f"{ch!r} is not a rectangle"
            boxes.append((ch, x, y, x1 - x + 1, y1 - y + 1))
    return boxes


assert areas(["AAB", "CCB"]) == [("A", 0, 0, 2, 1), ("B", 2, 0, 1, 2), ("C", 0, 1, 2, 1)]
assert big("1:23") == ["▀█    ▀▀█ ▀▀█", " █  ▪ █▀▀  ▀█", "▄█▄ ▪ █▄▄ ▄▄█"]


def box(b, name, title=None, hot=False):
    """One widget in its own rounded box, titled, in its own accent colour (heavy border when hot)."""
    label, mock, build = WIDGETS[name]
    acc = accents(b.c)[list(WIDGETS).index(name) % 6]
    base, b.c = b.c, {**b.c, "mauve": acc}
    try:
        w = Vertical(*build(b), classes="w")
    finally:
        b.c = base
    w.border_title, w.border_subtitle = title or label, "mock" if mock else ""
    w.styles.border = ("heavy", acc) if hot else ("round", theme._mix(base["base"], acc, 0.6))
    w.styles.border_title_color = acc
    return w


def grid(b, rows, names, cols=None, heights=None, hot=None, frame=None):
    """One grid from a character map; a name can be a dict, which nests another grid."""
    kids = []
    for key, _, _, cs, rs in areas(rows):
        if key == ".":
            w = Static(classes="blank")
        elif isinstance(names[key], dict):
            w = grid(b, **names[key])
        else:
            w = box(b, names[key], hot=key == hot)
        w.styles.column_span, w.styles.row_span = cs, rs
        kids.append(w)
    g = Container(*kids, classes="grid")
    g.styles.grid_size_columns, g.styles.grid_size_rows = len(rows[0]), len(rows)
    if cols:
        g.styles.grid_columns = cols
    if heights:
        g.styles.grid_rows = heights
    return framed(g, frame)


def framed(g, label):
    if label:  # a dashed outline standing for a smaller terminal window
        g = Container(g, classes="frame")
        g.border_title = label
    return g


def placed(b, x, y, w, h, what, label=None):
    """Pin something at x,y with an exact outer size: a widget name, a grid spec (dict), or a list of
    placements (a canvas of its own). Textual's position: absolute does the rest."""
    if isinstance(what, str):
        g = box(b, what, label)
    elif isinstance(what, dict):
        g = grid(b, **what, frame=label)
    else:
        g = framed(Container(*[placed(b, *p) for p in what], classes="canvas"), label)
    g.styles.position, g.styles.offset = "absolute", (x, y)
    g.styles.width, g.styles.height = w, h
    return g


def pack(items, W, H):
    """Skyline packing of (key, w, h): each item goes where it sits highest, leftmost on ties, and is
    skipped if it fits nowhere. Greedy, so the counts it gives are lower bounds."""
    sky, out = [0] * W, []
    for key, w, h in items:
        if w > W:
            continue
        y, x = min((max(sky[x:x + w]), x) for x in range(W - w + 1))
        if y + h <= H:
            out.append((key, x, y, w, h))
            sky[x:x + w] = [y + h] * w
    return out


assert pack([("a", 3, 2), ("b", 3, 1), ("c", 2, 1), ("d", 4, 4)], 6, 3) == [
    ("a", 0, 0, 3, 2), ("b", 3, 0, 3, 1), ("c", 3, 1, 2, 1)]


class Board(App):
    CSS = """
    Screen { background: $ytm-base; color: $ytm-text; }
    .grid { layout: grid; height: 1fr; }
    .canvas { height: 1fr; hatch: right $ytm-s0; }
    .frame { height: 1fr; border: dashed $ytm-sub; border-title-color: $ytm-text; border-title-style: bold;
             background: $ytm-base; }
    .w { height: 1fr; padding: 0 1; background: $ytm-base; border: round $ytm-s1;
         border-title-style: bold; border-subtitle-color: $ytm-dim; }
    .fit { height: 4; }
    .ctl { height: 1; width: auto; }
    .ctl2 { height: 2; }
    Btn { height: 1; min-width: 3; width: auto; border: none; padding: 0; margin-right: 1;
          background: $ytm-s0; color: $ytm-text; text-style: none; }
    Btn.big { background: $ytm-mauve; color: $ytm-crust; text-style: bold; }
    Btn.tab, Btn.act { padding: 0 1; margin-right: 0; background: $ytm-base; color: $ytm-dim; }
    Btn.act { color: $ytm-blue; }
    Btn.current { background: $ytm-mauve; color: $ytm-crust; text-style: bold; }
    .list { height: 1fr; background: $ytm-base; scrollbar-size-vertical: 1; scrollbar-color: $ytm-s1; }
    .list > ListItem { background: $ytm-base; }
    .list > ListItem.-highlight { background: $ytm-s0; }
    .list Label { text-wrap: nowrap; text-overflow: ellipsis; }
    .msg, .cap { height: 1; text-wrap: nowrap; text-overflow: ellipsis; }
    .prompt { height: 1; background: $ytm-base; color: $ytm-text; border: none; padding: 0; }
    .prompt > .input--placeholder { color: $ytm-dim; }
    .blank { height: 1fr; }
    #footer { height: 1; padding: 0 2; background: $ytm-crust; }
    """

    def __init__(self, theme_name="neon rave", footer=True, place=None, **grid_kw):
        spec = next((p for p in theme.PRESETS if p["name"] == theme_name), theme.DEFAULT)
        self.t = theme.normalize(spec)
        self.c = theme.colors(self.t)  # before super(): App.__init__ reads get_css_variables()
        super().__init__()
        self.footer, self.place, self.grid_kw = footer, place, grid_kw

    def get_css_variables(self):
        return {**super().get_css_variables(), **{f"ytm-{k}": v for k, v in self.c.items()}}

    def compose(self):
        if self.place:
            yield Container(*[placed(self, *p) for p in self.place], classes="canvas")
        else:
            yield grid(self, **self.grid_kw)
        if self.footer:
            note = self.footer if isinstance(self.footer, str) else f"{self.t['name']} · jev"
            yield Static(keys(("enter", "search"), ("tab", "list"), ("^space", "pause"), ("?", "help"))
                         + f"   [{self.c['dim']}]{note}[/]", id="footer")


async def shoot(name, size, out, **kw):
    app = Board(**kw)
    async with app.run_test(size=size) as pilot:
        await pilot.pause(0.2)
        text = TRY.screen_text(app)
        if out:
            app.save_screenshot(f"{name}.svg", str(out))
    return text


# ---- counting: how many widgets fit ----
MIX = ["mini", "controls2", "list", "prompt", "clock", "queue", "stats", "viz", "art", "lyrics", "gauge", "motif"]
SIZES = [(60, 18), (74, 24), (100, 30), (140, 40), (200, 55), (190, 50)]


def fill(sizes, W, H, rounds=30):
    """The MIX widgets in priority order, round after round, packed into W x H (one row less for the
    footer). Returns the placements and how many of the first round (all different) made it."""
    first = pack([(n, *sizes[n]) for n in MIX], W, H - 1)
    return pack([(n, *sizes[n]) for n in MIX] * rounds, W, H - 1), len(first)


def count():
    print(f"{'terminal':<10}{'min: all':>10}{'distinct':>10}{'comfy: all':>12}{'distinct':>10}")
    for W, H in SIZES:
        (m, md), (c, cd) = fill(MIN, W, H), fill(COMFY, W, H)
        print(f"{f'{W}x{H}':<10}{len(m):>10}{f'{md}/{len(MIX)}':>10}{len(c):>12}{f'{cd}/{len(MIX)}':>10}")


# ---- the gallery: every board is a full 190x50 screen, the user's 1920x1080 terminal ----
FULL = (190, 50)
COCKPIT = dict(rows=["CCCQQQSSSGGG",
                     "CCCQQQSSSGGG",
                     "AANNNNNKKLLL",
                     "AANNNNNKKLLL",
                     "IIIIIIIVVLLL",
                     "IIIIIIIVVLLL",
                     "IIIIIIIVVLLL",
                     "PPPPPPPPPMMM"],
               names=dict(C="clock", Q="queue", S="stats", G="gauge", A="art", N="mini", K="controls2",
                          L="lyrics", I="library", V="viz", P="prompt", M="motif"),
               heights="4 4 3 3 1fr 1fr 1fr 4", hot="N")


def window(x, y, w, h, what, label):
    """A smaller terminal drawn inside the full screen: the dashed frame sits outside the w x h cells."""
    return (x, y, w + 2, h + 2, what, f"your window at {w}×{h} · {label}")


def side_by_side(names):
    """Each widget at its minimum size, then at its comfortable size, pairs packed across the screen."""
    pairs = pack(sorted(((n, MIN[n][0] + COMFY[n][0] + 1, COMFY[n][1] + 1) for n in names),
                        key=lambda p: -p[2]), FULL[0], FULL[1] - 1)  # tallest first packs tighter
    assert len(pairs) == len(names), f"only {len(pairs)} of {len(names)} pairs fit"
    out = []
    for n, x, y, _, _ in pairs:
        (mw, mh), (cw, ch) = MIN[n], COMFY[n]
        out += [(x, y, mw, mh, n, f"min {mw}×{mh}"), (x + mw, y, cw, ch, n, f"{WIDGETS[n][0]} {cw}×{ch}")]
    return out


def boards():
    retro_74 = dict(rows=["WWWWWS", "IIIIIS", "IIIIIG", "PPPPPP"],
                    names=dict(W="now", I="library", S="stats", G="gauge", P="prompt"),
                    cols="1fr 1fr 1fr 1fr 1fr 22", heights="8 1fr 7 4")
    strip = dict(rows=["C", "K", "A", "Q", "G", "V", "P"], hot="C", heights="7 4 10 1fr 5 6 4",
                 names=dict(C="clock", K="controls2", A="art", Q="queue", G="gauge", V="viz", P="prompt"))
    tiny = [window(1, 1, 60, 18, dict(rows=["NNNNSS", "IIIISS", "IIIIVV", "PPPPPP"],
                                      names=dict(N="mini", I="list", S="stats", V="viz", P="prompt"),
                                      heights="4 1fr 1fr 4"), "list + stats"),
            window(1, 24, 60, 18, dict(rows=["AN", "AK", "LL", "PP"],
                                       names=dict(A="art", N="mini", K="controls", L="list", P="prompt"),
                                       cols="14 1fr", heights="4 3 1fr 4"), "art + list"),
            window(66, 1, 40, 12, dict(rows=["N", "K", "P"], names=dict(N="mini", K="controls", P="prompt"),
                                       heights="4 3 1fr", hot="N"), "tiny"),
            window(66, 17, 40, 12, dict(rows=["C", "K"], names=dict(C="clock", K="controls"), heights="1fr 3",
                                        hot="C"), "clock"),
            window(66, 33, 40, 12, dict(rows=["NQ", "PP"], names=dict(N="mini", Q="queue", P="prompt"),
                                        heights="1fr 4"), "queue"),
            window(111, 1, 30, 46, strip, "strip")]

    def packed_window(x, y, w, h):
        at, _ = fill(MIN, w, h)  # like --count: the bottom row stays free for the footer
        return window(x, y, w, h, [(px, py, pw, ph, n) for n, px, py, pw, ph in at], f"{len(at)} fit at min size")
    windows = [window(1, 1, 74, 24, retro_74, "your real one, today's widgets"), packed_window(80, 1, 74, 24),
               packed_window(1, 28, 60, 18), packed_window(66, 28, 40, 12), packed_window(111, 28, 30, 18)]
    at_min, d_min = fill(MIN, *FULL)
    at_comfy, d_comfy = fill(COMFY, *FULL)
    return {
        "01-cockpit": (FULL, dict(COCKPIT, footer="cockpit · 12 widgets · neon rave")),
        "02-cockpit-dream-haze": (FULL, dict(COCKPIT, theme_name="dream haze")),
        "03-cockpit-pit-wall": (FULL, dict(COCKPIT, theme_name="pit wall")),
        "04-calm-two-panel": (FULL, dict(rows=["XL"], cols="1fr 1fr", theme_name="rainy window", names=dict(
            X=dict(rows=["A", "N"], names=dict(A="art", N="now"), heights="1fr 10", hot="N"), L="library"))),
        "05-strip-column": (FULL, dict(rows=["MS"], cols="1fr 30", theme_name="campfire", names=dict(
            M=dict(rows=["IL", "PP"], names=dict(I="library", L="lyrics", P="prompt"), heights="1fr 4"),
            S=dict(rows=["C", "K", "A", "Q", "G", "V"], hot="C", heights="7 4 12 1fr 5 7",
                   names=dict(C="clock", K="controls2", A="art", Q="queue", G="gauge", V="viz"))))),
        "06-split-halves": (FULL, dict(rows=["XY"], cols="1fr 1fr", theme_name="desi street", names=dict(
            X=dict(rows=["N", "I"], names=dict(N="now", I="list"), heights="10 1fr", hot="N"),
            Y=dict(rows=["LV", "QG", "PP"], names=dict(L="lyrics", V="viz", Q="queue", G="gauge", P="prompt"),
                   heights="1fr 1fr 4")))),
        "07-split-thirds": (FULL, dict(rows=["XYZ"], cols="2fr 3fr 2fr", theme_name="cinema", names=dict(
            X=dict(rows=["C", "A", "K"], names=dict(C="clock", A="art", K="controls2"), heights="7 1fr 4"),
            Y=dict(rows=["N", "I"], names=dict(N="now", I="library"), heights="10 1fr", hot="N"),
            Z=dict(rows=["S", "L", "G", "P"], names=dict(S="stats", L="lyrics", G="gauge", P="prompt"),
                   heights="7 1fr 5 4")))),
        "08-small-windows": (FULL, dict(place=tiny, theme_name="retro tape", footer=False)),
        "09-windows-packed": (FULL, dict(place=windows, theme_name="neon rave", footer=False)),
        "10-min-vs-comfy": (FULL, dict(place=side_by_side(list(COMFY)), theme_name="velvet",
                                       footer="each widget at its minimum size (left) and comfortable size")),
        "11-packed-min": (FULL, dict(place=[(x, y, w, h, n) for n, x, y, w, h in at_min], theme_name="gold rush",
                                     footer=f"{len(at_min)} widgets at minimum size ({d_min} different)")),
        "12-packed-comfy": (FULL, dict(place=[(x, y, w, h, n) for n, x, y, w, h in at_comfy],
                                       theme_name="sunny day",
                                       footer=f"{len(at_comfy)} widgets at comfortable size ({d_comfy} different)")),
    }


async def gallery(out, only):
    for name, (size, kw) in boards().items():
        if not only or name in only:
            await shoot(name, size, out, **kw)
            print(out / f"{name}.svg")


# ---- measuring: shrink until the widget stops working ----
def has(*parts):
    return lambda text: all(p in text for p in parts)


TITLE = SONGS[0][0]
CHECKS = {  # what must be on screen for the widget to "work" (buttons fully drawn = clickable)
    "mini": has(TITLE[:8], "1:23 / 4:03"),  # elapsed and total, so the bar has room
    "clock": has("▄▄█", "Midnight"),  # the last digit's bottom row, and the title
    "controls": has("⏮", "⏸", "⏭", "♥", "−", "+", "∞", "◐", "▦"),
    "controls2": has("⏮", "⏸", "⏭", "♥", "−", "+", "∞", "◐", "▦"),
    "now": has(TITLE[:8], "1:23", "⏮", "⏸", "⏭", "♥", "−", "+", "∞", "◐", "▦"),
    "list": has(" 1  Midnight", " 3  Kesar"),  # 3 rows, readable start of each title
    "library": has("queue", "history", "liked", "playlists", "▶ play", "♥ like", " 3  Kesar"),
    "prompt": has("theme", "search a song"),
    "viz": lambda text: sum(ch in text for ch in "▂▃▄▅▆▇█") >= 3 and "euphoric" in text,  # bars + the mood
    "art": lambda text: sum(ln.count("▀") >= 6 for ln in text.splitlines()) >= 3,  # 6x3 cells: a thumbnail
    "stats": has("plays today", "listened"),
    "queue": has("Blinding", "Kesariya", "Smooth"),
    "lyrics": has("my church", "in a car"),  # 3 lines, readable
    "gauge": has("energy", "valence", "euphoric", "███"),  # 3 lines, bars at least 3 cells
    "motif": lambda text: "▇" in text,
}
COMFY = {"mini": (40, 4), "clock": (24, 7), "controls": (40, 3), "controls2": (28, 4), "now": (50, 8),
         "list": (50, 12), "library": (56, 14), "prompt": (50, 4), "viz": (30, 8), "art": (22, 12),
         "stats": (26, 6), "queue": (30, 7), "lyrics": (40, 8), "gauge": (26, 5), "motif": (20, 3)}
MIN = {"mini": (21, 4), "clock": (17, 7), "controls": (38, 3), "controls2": (26, 4), "now": (38, 7),  # from --measure
       "list": (17, 5), "library": (44, 7), "prompt": (17, 4), "viz": (25, 4), "art": (10, 5),
       "stats": (19, 4), "queue": (15, 5), "lyrics": (25, 5), "gauge": (18, 5), "motif": (9, 3)}


async def works(name, w, h):
    text = await shoot(None, (w, h), None, rows=["A"], names={"A": name}, footer=False)
    return CHECKS[name](text)


async def shrink(check, w, h):
    """Smallest height at width w, then smallest width at that height."""
    assert await check(w, h), f"fails at its comfortable size {w}x{h}"
    while h > 1 and await check(w, h - 1):
        h -= 1
    while w > 1 and await check(w - 1, h):
        w -= 1
    return w, h


# The real app's panels: run the real app (dev/try.py's fake player), hide everything but one panel.
PANELS = {"player": ["Midnight", "1:23", "⏮", "⏭", "♥", "∞", "◐", "▦"],
          "library": ["history", "queue", "liked", "▶ play", "✕ remove", "Midnight", "Kesariya"],
          "ask": ["search a song"]}  # #viz only draws in the dashboard layout; the "viz" mock uses its renderer


def solo_app(panel):
    class Solo(TRY.A.YtmApp):
        def on_mount(self):
            super().on_mount()
            for w in self.query(".panel, #footer"):
                w.display = w.id == panel
            self.query_one(f"#{panel}").styles.height = "1fr"
            self.query_one(f"#{panel}").styles.margin = 0
            self.query_one("#right").styles.height = "1fr" if panel == "ask" else "auto"
            self.query_one("#right").styles.margin = 0
            self.query_one("#left").display = panel != "ask"
            self.query_one("#body").styles.padding = 0

        def play_tracks(self, *a, **kw):  # the library panel opens on history, which try.py leaves empty
            super().play_tracks(*a, **kw)
            self.show("queue")
    return Solo


async def real_panel(panel, w, h, out=None):
    real = TRY.A.YtmApp
    TRY.A.YtmApp = solo_app(panel)
    try:
        songs = [{"id": f"vid{i:08d}", "title": t, "artist": a, "duration": d} for i, (t, a, d) in enumerate(SONGS)]
        sc = {"name": f"real-{panel}-{w}x{h}", "size": [w, h], "songs": songs, "pos": POS, "expect": PANELS[panel],
              "theme": "retro tape"}  # a classic-layout theme
        return not await TRY.run(sc, out or Path(os.environ.get("TEMP", ".")), bool(out))
    finally:
        TRY.A.YtmApp = real


async def measure(out, only):
    print(f"{'widget':<16}{'min':>8}{'comfy':>8}")
    for panel, comfy in {"player": (74, 12), "library": (74, 12), "ask": (74, 4)}.items():
        if only and "app" not in only:
            continue
        mw, mh = await shrink(lambda w, h, p=panel: real_panel(p, w, h), *comfy)
        print(f"{'app #' + panel:<16}{f'{mw}x{mh}':>8}{f'{comfy[0]}x{comfy[1]}':>8}")
    for name, comfy in COMFY.items():
        if only and name not in only:
            continue
        mw, mh = await shrink(lambda w, h, n=name: works(n, w, h), *comfy)
        print(f"{name:<16}{f'{mw}x{mh}':>8}{f'{comfy[0]}x{comfy[1]}':>8}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--measure", action="store_true")
    ap.add_argument("--count", action="store_true")
    a = ap.parse_args()
    Path(a.out).mkdir(parents=True, exist_ok=True)
    if a.count:
        count()
    else:
        asyncio.run(measure(Path(a.out), a.only) if a.measure else gallery(Path(a.out), a.only))

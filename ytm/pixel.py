"""Pixel art in half blocks: each cell is two pixels, '▀' with the top pixel as foreground and
the bottom one as background. Three pieces, all coloured from the theme's six colours:
the equaliser, the mood scene shown when a song has no cover, and the mini player's cassette.

A picture is a list of pixel rows (an even number), each a list of (r, g, b) or None (the
widget's own background). to_text turns it into one Rich Text, merging runs of equal cells."""

import math
import random
from functools import lru_cache

from rich.color import Color
from rich.style import Style
from rich.text import Span, Text


def rgb(h):
    return int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)


def mix(a, b, t):
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def ramp(stops, n):
    """n colours evenly along a list of colours (worked out once, then looked up per pixel)."""
    out = []
    for i in range(n):
        x = i / max(1, n - 1) * (len(stops) - 1)
        k = min(int(x), len(stops) - 2)
        out.append(mix(stops[k], stops[k + 1], x - k))
    return out


def palette(theme):
    return {k: rgb(v) for k, v in theme["palette"].items()}


@lru_cache(maxsize=4096)
def _style(fg, bg):
    return Style(color=Color.from_rgb(*fg), bgcolor=bg and Color.from_rgb(*bg))


@lru_cache(maxsize=4096)
def _cell(top, bot):
    """(character, style, has a background) for one cell; None pixels let the widget's background
    show. Foreground-only styles where possible: blank cells can then sit inside one span."""
    if top is None:
        return ("▄", _style(bot, None), False) if bot else (" ", None, False)
    if top == bot or bot is None:
        return "█" if bot else "▀", _style(top, None), False
    return "▀", _style(top, bot), True


def to_text(rows):
    """One Text, one span per run of equal styles (the costly part to draw is the span count)."""
    chars, spans, pos = [], [], 0
    for y in range(0, len(rows) - 1, 2):
        start, cur, cur_bg = pos, None, False
        for top, bot in zip(rows[y], rows[y + 1]):
            ch, style, bg = _cell(top, bot)
            chars.append(ch)
            if style is not cur and (style is not None or cur is None or cur_bg):  # styles are cached: same colours, same object
                if cur is not None:
                    spans.append(Span(start, pos, cur))
                start, cur, cur_bg = pos, style, bg
            pos += 1
        if cur is not None:
            spans.append(Span(start, pos, cur))
        chars.append("\n")
        pos += 1
    return Text("".join(chars[:-1]), spans=spans, no_wrap=True)


class Bars:
    """The equaliser: thin bars with gaps, an accent2 -> accent gradient, quick eased rise, a
    gravity fall, and a cap on each that holds at the peak a moment, then drifts down.
    Not real audio: the song's energy sets the height, its pace the sway and a soft kick."""

    def __init__(self):
        self.lv = []

    def frame(self, w, h, t, f, pal, dt):
        n, ph, e, pace = (w + 1) // 2, 2 * h, f["energy"], f["pace"]
        sway = t * (0.5 + pace)
        beat = max(0.0, math.sin(t * math.pi * (1 + 2 * pace))) ** 8
        goals = []
        for i in range(n):
            x = i / max(1, n - 1)
            wave = (math.sin(i * 0.55 + sway * 2.3) + math.sin(i * 0.23 - sway * 1.3) + 0.5 * math.sin(i * 1.3 + sway * 3.7)) / 2.5
            goals.append(min(1.0, (0.2 + 0.7 * e) * (0.55 + 0.45 * wave) * (1 - 0.35 * x) + 0.3 * e * beat * (1 - x)))
        if len(self.lv) != n:  # first frame, or a new width: start on target
            self.lv, self.vel, self.peak, self.hold = goals[:], [0.0] * n, goals[:], [0.0] * n
        for i, goal in enumerate(goals):
            if goal > self.lv[i]:
                self.lv[i] += (goal - self.lv[i]) * (1 - math.exp(-14 * dt))
                self.vel[i] = 0.0
            else:
                self.vel[i] += 2.5 * dt  # heights per second, per second
                self.lv[i] = max(goal, self.lv[i] - self.vel[i] * dt)
            if self.lv[i] >= self.peak[i]:
                self.peak[i], self.hold[i] = self.lv[i], 0.25
            elif self.hold[i] > 0:
                self.hold[i] -= dt
            else:
                self.peak[i] = max(self.lv[i], self.peak[i] - 1.2 * dt)  # stays within a few rows of its bar
        grad, cap = _grad(pal["bg"], pal["accent2"], pal["accent"], ph), pal["dim"]
        rows = [[None] * w for _ in range(ph)]
        for i in range(n):
            top = max(1, round(self.lv[i] * (ph - 1)))
            for r in range(top):
                rows[ph - 1 - r][2 * i] = grad[r & ~1]  # one colour per cell row: whole rows share a span
            c = round(self.peak[i] * (ph - 1))
            if c > top:
                rows[ph - 1 - c][2 * i] = cap
        return to_text(rows)


@lru_cache(maxsize=8)
def _grad(bg, low, high, n):
    return ramp([mix(bg, low, 0.4), low, high], n)  # the faint low end keeps it decoration, not the main thing


def scene_for(f):
    """Which scene suits the song: euphoric/club/high energy -> synthwave sun; acoustic -> campfire;
    the rest (dreamy, melancholic, calm, unknown) -> moon over water."""
    if f["energy"] >= 0.65 or f.get("mood") == "euphoric" or "club" in f.get("tags", ()):
        return "sun"
    if f["texture"] < 0.3 or (f.get("mood") in ("happy", "nostalgic") and f["energy"] < 0.5):
        return "fire"
    return "moon"


class Scene:
    """A generated cover: built once per song, size and palette, seeded by the video id so each
    song gets its own hills and stars; frame(t) adds the slow motion (twinkle, grid, ripples, flicker)."""

    def __init__(self, kind, vid, w, h, pal):
        self.kind, self.w, self.ph, self.p = kind, w, 2 * h, pal
        W, H, P = w, 2 * h, pal
        self.s = s = W / 40  # drawn for 40x40 px, scaled
        rnd = random.Random(vid or "ytm")
        self.hz = hz = int(H * 0.58)
        waves = [(rnd.uniform(.08, .3) / s, rnd.uniform(0, 6), rnd.uniform(1, 3) * s) for _ in range(3)]
        ridge = [int(hz - 2 * s - sum(a * 1.1 * (1 + math.sin(x * fq + ph)) for fq, ph, a in waves)) for x in range(W)]
        ridge2 = [r + int(3 * s + 2 * s * math.sin(x * .4 / s)) for x, r in enumerate(ridge)]
        self.stars = [(rnd.randrange(W), rnd.randrange(max(1, int(hz - 4 * s))), rnd.random() * 6.28) for _ in range(W * H // 40)]
        top = mix(P["bg"], (0, 0, 0), .3)
        sky = ramp([top, mix(P["bg"], P["accent"], .25), mix(P["accent"], P["accent2"], .35)] if kind == "sun"
                   else [top, mix(P["bg"], P["accent"], .3)], hz)
        rows = self.rows = [[sky[min(y, hz - 1)]] * W for y in range(H)]
        if kind == "moon":
            mx, my, r = W * .68, hz * .38, 5.2 * s
            for y in range(hz):
                for x in range(W):
                    d = math.hypot(x - mx, y - my)
                    if d <= r:
                        rows[y][x] = mix(P["text"], P["accent2"], .25 if (x - mx) * .5 + (y - my) > 2 * s else 0)
                    elif d <= r + 4 * s:
                        rows[y][x] = mix(rows[y][x], P["accent"], .35 * (1 - (d - r) / (4 * s)))  # halo
            for band in range(3):  # cloud bands
                by, off = int((4 + band * 6) * s), rnd.uniform(0, 40)
                for x in range(W):
                    if math.sin((x / s + off) * .25 + band) + math.sin((x / s + off) * .09) > .9:
                        for y in (by, by + 1):
                            rows[y][x] = mix(rows[y][x], P["accent2"], .3)
        hills = {"sun": (mix(P["bg"], P["accent"], .18), mix(P["bg"], P["dim"], .25)),
                 "moon": (mix(P["bg"], P["dim"], .35), mix(P["bg"], P["accent"], .2)),
                 "fire": (mix(P["bg"], P["dim"], .3), mix(P["bg"], P["accent"], .18))}[kind]
        for x in range(W):
            for y in range(max(0, ridge[x]), hz):
                rows[y][x] = hills[0]
            for y in range(max(0, ridge2[x]), hz):
                rows[y][x] = hills[1]
        if kind == "sun":
            cx, cy, r = W / 2 - .5, hz - 6 * s, W * .25
            sun = ramp([P["accent2"], P["accent"]], int(2 * r) + 2)
            for y in range(max(0, int(cy - r)), hz):
                dy = y - cy
                if dy > -r * .3 and int(dy + r) % max(2, 5 - int((dy + r * .3) / (3 * s))) == 0:
                    continue  # cut-out stripes, wider apart lower down
                for x in range(W):
                    if (x - cx) ** 2 + dy ** 2 <= r * r:
                        rows[y][x] = sun[int(y - cy + r)]
        if kind == "fire":
            ground, tree = mix(P["bg"], P["accent"], .1), mix(P["bg"], (0, 0, 0), .35)
            for y in range(hz, H):
                rows[y] = [ground] * W
            for tx in sorted(rnd.sample(range(2, W - 2), 5)):  # pines
                th = int((7 + tx % 4) * s)
                for k in range(th):
                    for x in range(tx - int(k / 3), tx + int(k / 3) + 1):
                        if 0 <= x < W and 0 <= hz - th + k:
                            rows[hz - th + k][x] = tree
            self.fx, self.fy = fx, fy = W // 2, H - max(2, int(4 * s))
            glow = mix(ground, P["accent2"], .2)
            for y in range(fy - 1, H):
                for x in range(W):
                    if abs(x - fx) + abs(y - fy) * 2 < 11 * s:
                        rows[y][x] = glow
            for x in range(fx - int(4 * s), fx + int(4 * s) + 1):
                rows[min(H - 1, fy + 1)][x] = mix(P["dim"], (90, 60, 40), .5)  # logs
            self.flame = ramp([P["accent2"], mix(P["accent2"], (255, 120, 40), .5), (200, 60, 30)], 5)
        self.stars = [(x, y, ph) for x, y, ph in self.stars if rows[y][x] == sky[y]]  # only in open sky
        if kind == "moon":  # the sky mirrored in the water, in two strengths for the ripple bands
            water = mix(P["bg"], (0, 0, 0), .25)
            self.water = [[[mix(water, c, k) for c in rows[max(0, min(H - 1, 2 * hz - y - 1))]] for y in range(H)] for k in (.45, .25)]

    def frame(self, t):
        W, H, P, hz, s = self.w, self.ph, self.p, self.hz, self.s
        rows = [r[:] for r in self.rows]
        for x, y, ph in self.stars:
            k = math.sin(t * 1.2 + ph)
            if k > -.3:
                rows[y][x] = mix(rows[y][x], P["text"], .5 + .5 * k)
        if self.kind == "sun":  # the floor's grid drifts slowly toward you
            floor, line, cx = mix(P["bg"], (0, 0, 0), .3), P["accent"], W / 2 - .5
            for y in range(hz, H):
                d = (y - hz + 1) / s
                rows[y] = [floor] * W
                if d > 2 and int(16 / d + t * .5) != int(16 / (d + 1 / s) + t * .5):
                    rows[y] = [mix(floor, line, .55 + .45 * (y - hz) / (H - hz))] * W
                for k in range(-8, 9):
                    x = round(cx + k * d * 1.4 * s)
                    if 0 <= x < W:
                        rows[y][x] = mix(floor, line, .7)
            rows[hz] = [P["accent2"]] * W
        elif self.kind == "moon":  # the sky mirrored in rippling water
            for y in range(hz, H):
                row, sh = self.water[(y + int(t * 2)) % 4 == 0][y], int(1.5 * s * math.sin(y * .9 / s + t * 1.5))
                rows[y] = row[sh:] + row[-1:] * sh if sh >= 0 else row[:1] * -sh + row[:sh]
        else:  # flickering flames, smoke puffs rising
            fx, fy, rnd = self.fx, self.fy, random.Random(int(t * 8))
            half = max(1, int(3 * s))
            for x in range(fx - half, fx + half + 1):
                hgt = min(fy, int((half + 1 - abs(x - fx)) * (1.2 + 0.6 * rnd.random())))
                for k in range(hgt):
                    rows[fy - k][x] = self.flame[min(4, k * 5 // max(1, hgt))]
            for i in range(3):
                age = (t * .4 + i / 3) % 1
                x, y = int(fx + 1.5 * s * math.sin(age * 6 + i)), int(fy - 5 * s - age * 14 * s)
                if 0 <= y < H and 0 <= x < W:
                    rows[y][x] = mix(rows[y][x], P["dim"], .6 * (1 - age))
        return to_text(rows)


# The mini player's cassette, 16x8 px: s shell, a label, . window, t tape, o screw holes, r reels
CASSETTE = [" ssssssssssssss ",
            "saaaaaaaaaaaaaas",
            "sa.rrr....rrr.as",
            "sa.r.r....r.r.as",
            "sa.rrr.tt.rrr.as",
            "saaaaaaaaaaaaaas",
            "sssosssssssssoss",
            " ssssssssssssss "]
RING = [(0, 0), (1, 0), (2, 0), (2, 1), (2, 2), (1, 2), (0, 2), (0, 1)]  # a reel's pixels, clockwise


@lru_cache(maxsize=16)
def sprite(step, colours, vinyl=False):
    """The cassette (or a vinyl, 8x8 px) at one of 4 steps of its turn; colours: the theme
    palette's items (hashable, so each frame is drawn once and then reused)."""
    P = {k: rgb(v) for k, v in colours}
    if vinyl:
        ang = step * math.pi / 4
        rows = [[None] * 8 for _ in range(8)]
        for y in range(8):
            for x in range(8):
                d = math.hypot(x - 3.5, y - 3.5)
                if d > 4:
                    continue
                if d < 1.2:
                    rows[y][x] = P["accent"]
                else:
                    sheen = abs(math.cos(math.atan2(y - 3.5, x - 3.5) - ang)) ** 6
                    rows[y][x] = mix(mix(P["bg"], P["dim"], .35 if (x + y) % 2 else .2), P["text"], .45 * sheen)
        return to_text(rows)
    look = {"s": mix(P["bg"], P["dim"], .55), "a": P["accent"], ".": mix(P["bg"], (0, 0, 0), .5),
            "t": mix(P["accent2"], P["bg"], .45), "o": P["bg"], "r": mix(P["text"], P["bg"], .6), " ": None}
    rows = [[look[c] for c in line] for line in CASSETTE]
    for x0 in (3, 10):
        for j in (step, step + 4):
            rows[2 + RING[j][1]][x0 + RING[j][0]] = P["text"]
    return to_text(rows)

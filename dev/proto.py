"""Throwaway prototype of the widget dashboard. Run: ytmdev proto

What it tries out, before the real refactor:
  - widgets: small self-contained classes; each one says which state keys it watches
    and draws itself from the shared state. Widgets never talk to each other.
  - a layout as data: LAYOUT below is a split tree; nothing about placement is in the widgets.
  - an LLM-designed widget: the sprite is JSON the LLM wrote (frames, motion, colours);
    code animates it. In yolo mode it's designed per song, otherwise cached/default.
  - borderless colour blocks, a braille equaliser, thin progress line, dimming of the
    pane you're not using.
Plays real music on whatever data this checkout uses (ytmdev: the copy in ~/.ytmdev)."""

import json
import math
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("COLORTERM", "truecolor")

from textual import on, work  # noqa: E402
from textual.app import App  # noqa: E402
from textual.binding import Binding  # noqa: E402
from textual.containers import Horizontal, Vertical  # noqa: E402
from textual.markup import escape  # noqa: E402
from textual.widgets import Input, Label, ListItem, ListView, RichLog, Static  # noqa: E402

from ytm import art, brain, library, search, settings, theme  # noqa: E402
from ytm.app import VID_RE, fmt_time, split_label, track_parts  # noqa: E402
from ytm.player import HOME, Player  # noqa: E402

# ---- the layout, as data: [name, size, children]. rows stack, cols sit side by side ----
LAYOUT = ["rows", "1fr", [
    ["cols", 9, [["player", "3fr"], ["chat", "2fr"]]],
    ["cols", "1fr", [["library", "3fr"], ["rows", "2fr", [["sprite", "1fr"], ["eq", 3]]]]],
]]

C = theme.colors(theme.normalize(theme.DEFAULT))
SPRITES = HOME / "data" / "proto_sprites.json"  # LLM-written sprites, cached per song


# ---- widgets ----
class Pane(Static):
    """A widget: watches some state keys, draws itself from the shared state."""
    WATCHES: set = set()
    ANIMATED = False

    def on_mount(self):
        self.redraw()

    def redraw(self):
        self.update(self.draw(self.app.st))

    def draw(self, st):
        return ""


class PlayerPane(Horizontal):
    """Compact player: small art, title, thin progress line, clickable controls."""
    WATCHES = {"vid", "time-pos", "duration", "pause", "volume", "media-title", "liked"}

    def compose(self):
        yield Static(id="art")
        yield Static(id="np")

    def redraw(self):
        st = self.app.st
        title, artist = st.get("title") or "Nothing playing", st.get("artist") or "type a song in the chat →"
        pos, dur = st.get("time-pos") or 0, st.get("duration") or 0
        w = max(10, self.query_one("#np").content_size.width - 16)
        done = int(w * pos / dur) if dur else 0
        bar = f"[{C['mauve']}]{'━' * done}●[/][{C['s1']}]{'─' * max(0, w - done)}[/]"
        play = "⏸" if not st.get("pause") else "▶"
        heart = f"[{C['pink']}]♥[/]" if st.get("liked") else "♡"
        ctl = (f"[@click=app.prev]⏮[/]   [@click=app.toggle][b]{play}[/b][/]   [@click=app.next]⏭[/]   "
               f"[@click=app.like]{heart}[/]   [{C['dim']}]vol {int(st.get('volume') or 0)}%[/]")
        self.query_one("#np").update(
            f"[b {C['mauve']}]{escape(title)}[/]\n[{C['sub']}]{escape(artist)}[/]\n\n"
            f"{bar} [{C['sub']}]{fmt_time(pos)} / {fmt_time(dur)}[/]\n\n{ctl}")


class Chat(Vertical):
    """Command log + input. Plain words search; a few verbs do the rest. No LLM unless asked."""
    WATCHES = set()

    def compose(self):
        yield RichLog(id="log", markup=True, wrap=True)
        yield Input(placeholder="play / queue / radio <song> · next · like · dream · help", id="ask")

    def redraw(self):
        pass

    def say(self, text):
        self.query_one("#log", RichLog).write(text)


class LibraryPane(Vertical):
    """Your space: queue · history · liked · playlists. ←/→ switch, Enter plays."""
    WATCHES = {"queue", "liked"}
    TABS = ["queue", "history", "liked", "playlists"]
    BINDINGS = [Binding("left", "tab(-1)"), Binding("right", "tab(1)")]

    def compose(self):
        self.tab = "history"
        yield Static(id="tabs")
        yield ListView(id="songs")

    def action_tab(self, step):
        self.tab = self.TABS[(self.TABS.index(self.tab) + step) % len(self.TABS)]
        self.redraw()

    def redraw(self):
        tabs = "  ·  ".join(f"[b {C['mauve']}]{t}[/]" if t == self.tab else f"[@click=app.tab('{t}')][{C['dim']}]{t}[/][/]"
                            for t in self.TABS)
        self.query_one("#tabs").update(tabs)
        lv = self.query_one("#songs", ListView)
        lv.clear()
        app = self.app
        if self.tab == "queue":
            rows = [(t, i == app.st.get("pos")) for i, t in enumerate(app.queue_tracks())]
        elif self.tab == "history":
            rows = [(t, False) for t in library.history(40)]
        elif self.tab == "liked":
            rows = [(t, False) for t in app.lib.liked()]
        else:
            rows = [(f"{n}  ({c})", False) for n, c in app.lib.playlists()]
        for t, now in rows:
            if isinstance(t, str):
                item = ListItem(Label(escape(t)))
                item.playlist = t.rsplit("  (", 1)[0]
            else:
                title, artist = track_parts(t)
                mark = f"[{C['green']}]▶ [/]" if now else "  "
                item = ListItem(Label(f"{mark}{escape(title)}  [{C['dim']}]{escape(artist)}[/]"))
                item.track = t
            lv.append(item)


class Eq(Pane):
    """Braille equaliser: each cell is a 2x4 dot grid, so 8x the resolution of block bars."""
    WATCHES = {"energy"}
    ANIMATED = True
    BITS = [[0x01, 0x02, 0x04, 0x40], [0x08, 0x10, 0x20, 0x80]]

    def draw(self, st):
        w, h = max(1, self.content_size.width), max(1, self.content_size.height)
        t, energy = self.app.clock, st.get("energy", 0.5)
        cells = [[0] * w for _ in range(h)]
        rows = h * 4
        for x in range(w * 2):
            wave = 0.5 + 0.5 * math.sin(t * 2.7 + x * 0.42) * math.sin(t * 1.1 + x * 0.13)
            level = 0.1 + 0.9 * wave * (0.45 + 0.55 * energy)  # quiet songs still move
            for y in range(rows - int(level * rows), rows):
                cells[y // 4][x // 2] |= self.BITS[x % 2][y % 4]
        return f"[{C['mauve']}]" + "\n".join("".join(chr(0x2800 + c) for c in r) for r in cells) + "[/]"


DEFAULT_SPRITE = {"name": "little note", "frames": [" ♪\n/|\n", " ♫\n|\\\n"], "motion": "bounce", "speed": 2}


class Sprite(Pane):
    """Draws an LLM-written sprite: frames + motion. The LLM only writes data; this code animates it."""
    WATCHES = {"sprite"}
    ANIMATED = True

    def draw(self, st):
        sp = st.get("sprite") or DEFAULT_SPRITE
        w, h = max(1, self.content_size.width), max(2, self.content_size.height)
        t, speed = self.app.clock, sp.get("speed", 2)
        frame = sp["frames"][int(t * speed) % len(sp["frames"])].split("\n")
        fw = max(len(line) for line in frame)
        span = max(1, w - fw)
        x = {"left": span - int(t * speed * 3) % (span + 1), "right": int(t * speed * 3) % (span + 1),
             "bounce": int(abs((t * speed * 2) % (2 * span) - span)), "still": span // 2}[sp.get("motion", "still")]
        grid = [[" "] * w for _ in range(h - 1)]
        top = max(0, (h - 1 - len(frame)) // 2)
        for dy, line in enumerate(frame):
            for dx, ch in enumerate(line):
                if ch != " " and 0 <= top + dy < h - 1 and 0 <= x + dx < w:
                    grid[top + dy][x + dx] = ch
        body = escape("\n".join("".join(r) for r in grid))
        return f"[{C['dim']}]✦ {escape(sp['name'])}[/]\n[{sp.get('color', C['pink'])}]{body}[/]"


WIDGETS = {"player": PlayerPane, "chat": Chat, "library": LibraryPane, "eq": Eq, "sprite": Sprite}


def build(node, parent="rows"):
    """Turn the LAYOUT data into containers and widgets."""
    name, size, *kids = node
    if name in ("rows", "cols"):
        box = (Vertical if name == "rows" else Horizontal)(*[build(k, name) for k in kids[0]])
    else:
        box = WIDGETS[name](classes="pane", id=f"w_{name}")
    if parent == "rows":
        box.styles.height = size
    else:
        box.styles.width = size
    return box


# ---- the LLM writes the sprite (data only) ----
SPRITE_PROMPT = """Design a tiny ASCII animation for a terminal music player, for this song:
{song}
Return ONLY JSON: {{"name": "2-4 words", "frames": ["frame 1", "frame 2"], "motion": "left|right|bounce|still",
"color": "#rrggbb", "speed": 1-4}}
Rules: 2-4 frames, each at most 5 lines and 22 characters wide, lines joined with \\n; plain text
characters only (no emoji, no tabs); depict something from the song's world (a race car for an F1
song, rain for a sad one, a crowd for a club track); the colour must be bright on a dark background."""


def clean_sprite(d):
    """Never trust model output: clip sizes, check fields, fall back to defaults."""
    frames = [f for f in d.get("frames", []) if isinstance(f, str) and f.strip()][:4]
    frames = ["\n".join(line.replace("\t", " ")[:22] for line in f.split("\n")[:5]) for f in frames]
    if not frames:
        return None
    return {"name": str(d.get("name") or "sprite")[:24], "frames": frames,
            "motion": d.get("motion") if d.get("motion") in ("left", "right", "bounce", "still") else "still",
            "color": theme._hex(d.get("color"), C["pink"]),
            "speed": max(1, min(4, int(d["speed"]))) if isinstance(d.get("speed"), (int, float)) else 2}


def design_sprite(song, lib):
    r = brain._post(brain.LLM_URL, brain._key("OPENROUTER_API_KEY"), {
        "model": brain.LLM_MODEL, "max_tokens": 1500, "response_format": {"type": "json_object"},
        "usage": {"include": True}, "messages": [{"role": "user", "content": SPRITE_PROMPT.format(song=json.dumps(song))}]},
        timeout=40)
    u = r.get("usage", {})
    brain._spend(lib, "llm", u.get("prompt_tokens", 0), u.get("completion_tokens", 0),
                 u.get("cost", 0), song.get("id", ""))
    text = r["choices"][0]["message"].get("content") or ""
    return clean_sprite(json.loads(text[text.find("{"):text.rfind("}") + 1])) if "{" in text else None


# ---- the app: owns state, routes changes to the widgets that watch them ----
class Proto(App):
    CSS = """
    Screen { background: $p-base; }
    .pane { background: $p-mantle; padding: 1 2; }
    #w_player, #w_chat { background: $p-crust; }
    #w_library { background: $p-base; }
    #w_eq { padding: 0 2; background: $p-mantle; }
    #art { width: 14; height: 7; margin-right: 2; }
    #np { width: 1fr; }
    #log { background: transparent; height: 1fr; scrollbar-size-vertical: 1; }
    #ask { border: none; height: 1; padding: 0 1; background: $p-s0; color: $p-text; }
    #songs { background: transparent; height: 1fr; margin-top: 1; }
    #songs > ListItem { background: transparent; }
    #songs > ListItem.-highlight { background: $p-s0; }
    .dim > * { tint: $p-base 60%; }
    * { scrollbar-size-vertical: 1; scrollbar-size-horizontal: 0; scrollbar-color: $p-s1;
        scrollbar-color-hover: $p-mauve; scrollbar-color-active: $p-mauve; scrollbar-background: $p-mantle;
        scrollbar-background-hover: $p-mantle; scrollbar-background-active: $p-mantle; link-style: none; }
    #log { overflow-x: hidden; }
    """
    BINDINGS = [Binding("ctrl+c,ctrl+q", "quit", priority=True), Binding("ctrl+n", "next", priority=True), Binding("ctrl+b", "prev", priority=True)]

    def __init__(self):
        super().__init__()
        self.lib, self.settings = library.Library(), settings.Settings()
        self.st = {"pause": False, "volume": 70, "pos": -1}
        self.known, self.clock, self.vid = {}, 0.0, None
        try:
            self.sprites = json.loads(SPRITES.read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError):
            self.sprites = {}

    def get_css_variables(self):
        return {**super().get_css_variables(), **{f"p-{k}": v for k, v in C.items()}}

    def compose(self):
        yield build(LAYOUT)

    def on_mount(self):
        self.player = Player(on_change=self._from_mpv)
        self.set_interval(1 / 8, self.tick)
        self.query_one("#ask").focus()
        self.chat("[b]ytm dashboard prototype[/b] · layout, widgets and sprite are all data")
        self.chat(f"mode [b]{self.settings['mode']}[/b]: " + ("the LLM designs a sprite per song" if self.settings["mode"] == "yolo"
                                                             else "sprites are cached/default · `dream` designs one now"))

    def on_unmount(self):
        if hasattr(self, "player"):
            self.player.close()

    def chat(self, text):
        self.query_one(Chat).say(text)

    # one place where state changes; only widgets watching a changed key redraw
    def set_state(self, **changes):
        changes = {k.replace("_", "-"): v for k, v in changes.items()}
        self.st.update(changes)
        for w in self.query(".pane"):
            if w.WATCHES & changes.keys():
                w.redraw()

    def tick(self):
        if self.st.get("time-pos") is not None and not self.st.get("pause") and self.settings["motion"] != "off":
            self.clock += 1 / 8
        for w in self.query(".pane"):
            if getattr(w, "ANIMATED", False):
                w.redraw()

    # ---- mpv ----
    def _from_mpv(self, name, value):
        try:
            self.call_from_thread(self._apply, name, value)
        except RuntimeError:
            pass

    def _apply(self, name, value):
        if name == "time-pos" and value is not None and abs(value - (self.st.get("time-pos") or 0)) < 0.25:
            return
        self.set_state(**{name: value})
        if name in ("playlist-pos", "media-title", "playlist-count"):
            vid = self.current_id()
            self.set_state(pos=self.st.get("playlist-pos"), queue=time.time())
            if vid and vid != self.vid:
                self.song_changed(vid)

    def current_id(self):
        pos, entries = self.st.get("playlist-pos"), self.player.playlist()
        if pos is None or not 0 <= pos < len(entries):
            return None
        m = VID_RE.search(entries[pos].get("filename", ""))
        return m.group(1) if m else None

    def queue_tracks(self):
        out = []
        for e in self.player.playlist():
            m = VID_RE.search(e.get("filename", ""))
            if m:
                out.append(self.known.get(m.group(1)) or search.Track(m.group(1), e.get("title") or m.group(1)))
        return out

    def song_changed(self, vid):
        self.vid = vid
        t = self.known.get(vid)
        title, artist = track_parts(t) if t else split_label(self.st.get("media-title") or "")
        self.set_state(vid=vid, title=title, artist=artist, liked=vid in self.lib.liked_ids(),
                       sprite=self.sprites.get(vid))
        self.query_one("#art").update("")
        self.load_art(vid)
        self.think({"id": vid, "title": title, "artist": artist})

    @work(thread=True, exclusive=True, group="art")
    def load_art(self, vid):
        img = art.fetch(vid, 14, 7)
        if img is not None and vid == self.vid:
            self.call_from_thread(self.query_one("#art").update, img)

    @work(thread=True, exclusive=True, group="brain")
    def think(self, song):
        try:
            jev, llm, _ = brain.budget(self.lib, self.settings)
            if jev or self.lib.features(song["id"]):
                f = brain.think(song, self.lib, llm)
                self.call_from_thread(self.restyle, f)
            if self.settings["mode"] == "yolo" and llm and song["id"] not in self.sprites:
                self.call_from_thread(self.chat, f"[{C['dim']}]✦ designing a sprite for {escape(song['title'])} …[/]")
                self.make_sprite(song)
        except Exception as e:
            self.call_from_thread(self.chat, f"[{C['red']}]brain: {escape(str(e))[:80]}[/]")

    def make_sprite(self, song):
        sp = design_sprite(song, self.lib)
        if sp:
            self.sprites[song["id"]] = sp
            SPRITES.parent.mkdir(parents=True, exist_ok=True)
            SPRITES.write_text(json.dumps(self.sprites, indent=1), encoding="utf-8")
            if song["id"] == self.vid:
                self.call_from_thread(self.set_state, sprite=sp)
            self.call_from_thread(self.chat, f"✦ sprite: [b]{escape(sp['name'])}[/] ({len(sp['frames'])} frames, {sp['motion']})")

    def restyle(self, f):
        spec = next((t for t in theme.PRESETS + self.lib.themes() if t["name"] == f.get("theme")), theme.DEFAULT)
        C.update(theme.colors(theme.normalize(spec)))
        self.refresh_css()
        self.st["energy"] = f.get("energy", 0.5)
        for w in self.query(".pane"):  # new colours: everything redraws
            w.redraw()
        self.chat(f"[{C['dim']}]{escape(f.get('theme', ''))} · {escape(str(f.get('mood', '')))} · energy {int(f.get('energy', 0.5) * 100)}%[/]")

    # ---- focus dimming: the pane you're not using fades ----
    def on_descendant_focus(self, event):
        for name in ("chat", "library"):
            pane = self.query_one(f"#w_{name}")
            pane.set_class(pane not in event.widget.ancestors_with_self, "dim")

    # ---- actions (buttons, keys, chat) ----
    def action_next(self):
        self.player.next()

    def action_prev(self):
        self.player.prev()

    def action_toggle(self):
        self.player.toggle_pause()

    def action_like(self):
        t = self.known.get(self.vid) or (self.vid and search.Track(self.vid, self.st.get("title", ""), self.st.get("artist", "")))
        if t:
            self.set_state(liked=self.lib.toggle_like(t))

    def action_tab(self, name):
        lib = self.query_one(LibraryPane)
        lib.tab = name
        lib.redraw()

    @on(ListView.Selected, "#songs")
    def picked(self, event):
        item = event.item
        if hasattr(item, "track"):
            self.play([item.track], replace=True)
        elif hasattr(item, "playlist"):
            tracks = self.lib.playlist(item.playlist)
            self.play(tracks, replace=True)
            self.chat(f"▶ playlist {escape(item.playlist)} ({len(tracks)} songs)")

    def play(self, tracks, replace):
        for i, t in enumerate(tracks):
            self.known[t.video_id] = t
            (self.player.play if replace and i == 0 else self.player.queue)(t.url)
        self.set_state(queue=time.time())

    @on(Input.Submitted, "#ask")
    def ask(self, event):
        line = event.value.strip()
        event.input.value = ""
        if not line:
            return
        self.chat(f"[{C['sub']}]› {escape(line)}[/]")
        cmd, _, arg = line.partition(" ")
        cmd = cmd.lower()
        if cmd in ("next", "skip", "n"):
            self.action_next()
        elif cmd in ("prev", "back"):
            self.action_prev()
        elif cmd in ("pause", "p"):
            self.action_toggle()
        elif cmd == "like":
            self.action_like()
        elif cmd in ("vol", "volume") and arg.isdigit():
            self.player.set_volume(int(arg))
        elif cmd == "dream":
            if self.vid:
                self.chat(f"[{C['dim']}]✦ designing a sprite …[/]")
                self.dream()
        elif cmd == "help":
            self.chat("play/queue/radio <song> · plain text plays the top result · next · prev · pause · like · "
                      "vol 50 · dream (LLM designs a sprite for this song) · tab moves between panes")
        else:
            action = cmd if cmd in ("play", "queue", "radio") and arg else "play"
            self.find(arg if action != "play" or cmd == "play" else line, action)

    @work(thread=True, group="dream")
    def dream(self):
        try:
            self.make_sprite({"id": self.vid, "title": self.st.get("title", ""), "artist": self.st.get("artist", "")})
        except Exception as e:
            self.call_from_thread(self.chat, f"[{C['red']}]dream failed: {escape(str(e))[:80]}[/]")

    @work(thread=True, group="search")
    def find(self, query, action):
        results = search.search(query, limit=5)
        if not results:
            self.call_from_thread(self.chat, "nothing found")
            return
        top = results[0]
        tracks = (search.radio(top.video_id, limit=30) or [top]) if action == "radio" else [top]
        self.call_from_thread(self.play, tracks, action != "queue")
        title, artist = track_parts(top)
        verb = {"queue": "+ queued", "radio": "∞ radio from"}.get(action, "▶")
        self.call_from_thread(self.chat, f"{verb} [b]{escape(title)}[/] [{C['dim']}]{escape(artist)}[/]")


if __name__ == "__main__":
    Proto().run()

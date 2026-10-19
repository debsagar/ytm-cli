"""The terminal UI (Textual): a compact mini-player. Run with:  python -m ytm"""

import math
import os
import re
import time

# Windows Terminal supports 24-bit colour but doesn't always advertise it,
# which makes Textual fall back to grey. Say so before Textual starts.
os.environ.setdefault("COLORTERM", "truecolor")

from textual import on, work  # noqa: E402
from textual.app import App, ComposeResult  # noqa: E402
from textual.binding import Binding  # noqa: E402
from textual.containers import Horizontal, Vertical, VerticalScroll  # noqa: E402
from textual.markup import escape as _escape  # noqa: E402
from textual.screen import ModalScreen  # noqa: E402
from textual.widgets import Button, Input, Label, ListItem, ListView, Static  # noqa: E402

from . import art, brain, library, search, settings, theme  # noqa: E402
from .player import Player  # noqa: E402
from .search import Track  # noqa: E402

# Catppuccin Mocha palette, used directly so colours never depend on the terminal theme.
C = dict(
    crust="#11111b", mantle="#181825", base="#1e1e2e", s0="#313244", s1="#45475a",
    dim="#6c7086", sub="#a6adc8", text="#cdd6f4",
    mauve="#cba6f7", pink="#f5c2e7", blue="#89b4fa", green="#a6e3a1", peach="#fab387", red="#f38ba8",
)

URL_RE = re.compile(r"^(https?://)?((www|music|m)\.)?youtu(be\.com|\.be)/", re.I)
VID_RE = re.compile(r"(?:v=|youtu\.be/)([\w-]{11})")
# Noise YouTube adds to titles: "(Official Music Video)", "[Lyrics]", "| Lyrics" ...
NOISE_RE = re.compile(
    r"\s*([(\[][^)\]]*\b(official|video|lyrics?|letra|audio|visuali[sz]er|oficial|4k|hd)\b[^)\]]*[)\]]|\|\s*lyrics.*)",
    re.I,
)
TABS = ["queue", "history", "liked", "playlists", "results"]
ART_W, ART_H = 20, 10  # cells; the image is 20x20 pixels

HELP_ROWS = [
    ("Type anything", "search YouTube Music"),
    ("play <song>", "play the top result now"),
    ("queue <song>", "add the top result to the queue"),
    ("radio <song>", "start a 50-song mix"),
    ("like", "like / unlike the song that's playing"),
    ("save <name>", "save the whole queue as a playlist"),
    ("skip · prev · pause · vol 40", "playback"),
    ("remove 3 · clear", "edit the queue"),
    ("auto", "autoplay: keep adding similar songs"),
    ("cost", "what the brain has spent (Jev + LLM)"),
    ("set · set <key> <value>", "see or change settings"),
    ("mode off · jev · yolo", "how much the brain may do"),
    ("quit", "exit (Ctrl+Q also works)"),
    ("", ""),
    ("Mouse", "every button and tab is clickable"),
    ("Tab / Esc", "move between list and prompt"),
    ("Enter", "play selected song / open playlist"),
    ("a · l · s · d", "queue · like · playlist · remove"),
    ("← →", "switch list tabs"),
    ("Ctrl+Space · Ctrl+N · Ctrl+B", "pause · next · previous"),
]


def fmt_time(s):
    if s is None:
        return "-:--"
    s = int(s)
    return f"{s // 60}:{s % 60:02d}"


def clean(title):
    return NOISE_RE.sub("", title or "").strip() or (title or "")


def split_label(label):
    """'Uploader - Artist - Title' -> ('Title', 'Artist')."""
    parts = [p.strip() for p in (label or "").split(" - ") if p.strip()]
    if len(parts) >= 2:
        return clean(parts[-1]), parts[-2]
    return clean(label), ""


def track_parts(t: Track):
    if t.artist:
        return clean(t.title), t.artist
    return split_label(t.title)


def tidy(t: Track):
    """A Track with clean title/artist fields, for saving to likes and playlists."""
    title, artist = track_parts(t)
    return Track(t.video_id, title, artist, t.duration)


def fmt_usd(usd):
    """Jev costs fractions of a cent per song, so small amounts are shown in cents."""
    if usd >= 0.01:
        return f"${usd:.2f}"
    return f"{usd * 100:.3f}¢" if usd else "$0"


def escape(text):
    """Make text safe inside markup. A trailing backslash would escape the next tag (and the
    style would leak), so it is kept out of escape() and fenced with a zero-width space."""
    core = text.rstrip("\\")
    tail = text[len(core):]
    return _escape(core) + (tail + "\u200b" if tail else "")


def songs(n):
    return f"{n} song" + ("" if n == 1 else "s")


# commands that need an argument; bare, they show this instead of searching YouTube for the word
USAGE = {"play": "play <song>", "radio": "radio <song>", "save": "save <playlist name>",
         "vol": "vol <0-130>", "volume": "vol <0-130>", "remove": "remove <number in the queue>",
         "rm": "remove <number in the queue>", "search": "search <song>", "s": "search <song>"}


def keys(*pairs):
    """Footer hint: coloured key, grey description."""
    return "   ".join(f"[b {C['blue']}]{k}[/] [{C['dim']}]{d}[/]" for k, d in pairs)


class Btn(Button, can_focus=False):
    """A one-line button that doesn't steal focus from the list or prompt."""


class Row(ListItem):
    def __init__(self, track: Track, num: int, current=False, liked=False):
        title, artist = (escape(x) for x in track_parts(track))
        if current:
            text = f"[b {C['green']}]▶  {title}[/]"
        else:
            text = f"[{C['dim']}]{num:>2}[/] {title}"
        if liked:
            text += f" [{C['pink']}]♥[/]"
        if artist:
            text += f"  [{C['dim']}]{artist}[/]"
        super().__init__(Label(text))
        self.track = track


class PlaylistRow(ListItem):
    def __init__(self, name, count):
        super().__init__(Label(f"[{C['mauve']}]≡[/]  [b]{escape(name)}[/]  [{C['dim']}]{songs(count)}[/]"))
        self.name_ = name


class HelpScreen(ModalScreen):
    """A popup of text lines: the help, or the settings list."""
    BINDINGS = [Binding("escape,question_mark,q,enter", "dismiss")]
    CSS = f"""
    HelpScreen {{ align: center middle; background: $ytm-crust 70%; }}
    #help {{ width: 72; max-width: 100%; height: auto; max-height: 100%; background: $ytm-mantle;
             border: round $ytm-mauve; padding: 1 1; border-title-color: $ytm-mauve;
             scrollbar-size-vertical: 1; scrollbar-color: $ytm-mauve; scrollbar-background: $ytm-mantle; }}
    """

    def __init__(self, lines=None, title="how to use ytm"):
        super().__init__()
        self.lines = lines or [f"[b {C['blue']}]{escape(k):<30}[/][{C['sub']}]{d}[/]" if k else ""
                               for k, d in HELP_ROWS]
        self.title_ = title

    def compose(self):
        text = Static("\n".join(self.lines) + f"\n\n[{C['dim']}]↑↓ scroll · Esc closes[/]")
        box = VerticalScroll(text, id="help")  # scrolls when the window is shorter than the text
        box.border_title = self.title_
        yield box


class PlaylistPicker(ModalScreen):
    """Pick an existing playlist or type a new name. Dismisses with the name, or None."""
    BINDINGS = [Binding("escape", "dismiss(None)")]
    CSS = f"""
    PlaylistPicker {{ align: center middle; background: $ytm-crust 70%; }}
    #box {{ width: 50; height: auto; max-height: 20; background: $ytm-mantle;
            border: round $ytm-mauve; padding: 1 2; border-title-color: $ytm-mauve; }}
    #pl {{ height: auto; max-height: 10; background: $ytm-mantle; }}
    #pl > ListItem.-highlight {{ background: $ytm-s0; }}
    #name {{ margin-top: 1; border: round $ytm-s1; background: $ytm-base; }}
    #name:focus {{ border: round $ytm-mauve; }}
    """

    def __init__(self, playlists, what):
        super().__init__()
        self.playlists, self.what = playlists, what

    def compose(self):
        with Vertical(id="box") as box:
            box.border_title = f"add {self.what} to…"
            yield ListView(*[PlaylistRow(n, c) for n, c in self.playlists], id="pl")
            yield Input(placeholder="or type a new playlist name + enter", id="name")

    def on_mount(self):
        (self.query_one("#pl") if self.playlists else self.query_one("#name")).focus()

    @on(ListView.Selected)
    def chose(self, event):
        self.dismiss(event.item.name_)

    @on(Input.Submitted)
    def typed(self, event):
        self.dismiss(event.value.strip() or None)


class YtmApp(App):
    TITLE = "ytm"
    ENABLE_COMMAND_PALETTE = False
    CSS = f"""
    Screen {{ background: $ytm-base; color: $ytm-text; }}

    #now {{ height: auto; background: $ytm-mantle; padding: 1 2; }}
    #art {{ width: {ART_W}; height: {ART_H}; margin-right: 2; color: $ytm-s1; }}
    #info {{ height: auto; }}
    #title {{ color: $ytm-pink; text-style: bold; }}
    #motif {{ color: $ytm-mauve; height: 1; }}
    #eq {{ color: $ytm-mauve; height: 3; display: none; }}
    Screen.layout-stage #eq {{ display: block; }}
    Screen.layout-hero.tall #art {{ width: {ART_W * 2}; height: {ART_H * 2}; margin-right: 3; }}
    Screen.layout-hero #title {{ margin-top: 1; }}
    Screen.layout-hero #list {{ max-height: 12; }}
    Screen.layout-focus #art, Screen.layout-focus #tabs, Screen.layout-focus #actions,
    Screen.layout-focus #list {{ display: none; }}
    Screen.layout-focus #now {{ height: 1fr; align: center middle; }}
    Screen.layout-focus #info {{ width: 80%; }}
    Screen.layout-focus #title {{ text-align: center; }}
    Screen.layout-focus #artist, Screen.layout-focus #headline, Screen.layout-focus #motif {{ text-align: center; }}
    #headline {{ color: $ytm-mauve; text-style: italic; height: auto; text-wrap: nowrap; text-overflow: ellipsis; }}
    Screen.layout-focus #headline {{ text-wrap: wrap; }}  /* focus has rows to spare */
    #artist {{ color: $ytm-sub; }}
    #bar {{ margin-top: 1; }}
    #title, #artist, #list Label {{ text-wrap: nowrap; text-overflow: ellipsis; }}

    Btn {{ height: 1; min-width: 3; width: auto; border: none; padding: 0 1; margin-right: 1;
           background: $ytm-s0; color: $ytm-text; text-style: none; }}
    Btn:hover {{ background: $ytm-s1; }}
    Btn.-active {{ background: $ytm-s0; }}
    #controls {{ height: 1; margin-top: 1; }}
    #controls Btn {{ padding: 0; }}  /* Button's line-pad already pads the icon */
    #controls .big {{ background: $ytm-mauve; color: $ytm-crust; text-style: bold; }}
    #controls .big:hover {{ background: $ytm-pink; }}
    #like_now.on, #r_like.on {{ color: $ytm-pink; }}
    #auto {{ color: $ytm-dim; }}
    #auto.on {{ color: $ytm-green; }}

    #tabs {{ height: 1; padding: 0 1; margin-top: 1; }}
    #tabs Btn {{ background: $ytm-base; color: $ytm-dim; margin-right: 0; }}
    #tabs Btn:hover {{ color: $ytm-text; }}
    #tabs Btn.current {{ background: $ytm-mauve; color: $ytm-crust; text-style: bold; }}

    #actions {{ height: 1; padding: 0 1; margin-top: 1; }}
    #actions Btn {{ background: $ytm-base; color: $ytm-blue; border: none; }}
    #actions Btn:hover {{ background: $ytm-s0; }}
    #actions #r_rm {{ color: $ytm-red; }}

    #list {{ height: 1fr; background: $ytm-base; padding: 0 1;
             scrollbar-size-vertical: 1; scrollbar-color: $ytm-s1; scrollbar-background: $ytm-base; }}
    #list > ListItem {{ background: $ytm-base; }}
    #list > ListItem.-highlight {{ background: $ytm-mantle; }}
    #list:focus > ListItem.-highlight {{ background: $ytm-s0; }}

    #msg {{ height: 1; padding: 0 2; color: $ytm-peach; }}
    #prompt {{ height: 3; margin: 0 1; background: $ytm-mantle; color: $ytm-text;
               border: round $ytm-s1; padding: 0 1; }}
    #prompt:focus {{ border: round $ytm-mauve; }}
    #prompt > .input--placeholder {{ color: $ytm-dim; }}
    #prompt > .input--cursor {{ background: $ytm-mauve; color: $ytm-crust; }}
    #footer {{ height: 1; padding: 0 2; background: $ytm-crust; }}
    """
    BINDINGS = [
        Binding("ctrl+space", "pause", priority=True),
        Binding("ctrl+n", "next", priority=True),
        Binding("ctrl+b", "prev", priority=True),
        Binding("ctrl+right", "seek(10)", priority=True),
        Binding("ctrl+left", "seek(-10)", priority=True),
        Binding("escape", "focus_prompt"),
        Binding("left", "tab(-1)"),
        Binding("right", "tab(1)"),
        Binding("a", "row('queue')"),
        Binding("l", "row('like')"),
        Binding("s", "row('playlist')"),
        Binding("delete,d", "row('remove')"),
        Binding("question_mark", "help"),
        Binding("ctrl+c,ctrl+q", "quit", priority=True),
    ]

    def __init__(self):
        super().__init__()
        self.state = {"media-title": None, "time-pos": None, "duration": None,
                      "pause": False, "volume": 70, "playlist-pos": -1, "playlist-count": 0}
        self.known = {}  # video id -> Track, so the queue can show proper titles
        self.results = []
        self.view = "history"
        self.open_playlist = None  # name, when view == "playlist"
        self._last_sec = None
        self.auto = True  # autoplay: top up the queue with similar songs
        self._filling = False
        self._art_id = None
        self.lib = library.Library()
        self.settings = settings.Settings()
        self._ticks = 0
        self._songs_since = 10 ** 6  # songs since the look last changed (huge: first song restyles)
        self._restyled_at = 0.0
        self.vibe = "normal"
        self.theme_spec = theme.normalize(theme.DEFAULT)
        self.song_feats = {}       # features of the song playing (headline, blurb...)
        self._played = None        # (video id, last position, duration) for skip logging
        self.layout = "classic"
        self._phase = 0.0           # animation clock, advances only while playing
        self._bar_width = None      # #info width the bar was last drawn for

    def compose(self) -> ComposeResult:
        with Horizontal(id="now"):
            yield Static("", id="art")
            with Vertical(id="info"):
                yield Static(id="motif")
                yield Static(id="eq")
                yield Static(id="title")
                yield Static(id="artist")
                yield Static(id="headline")
                yield Static(id="bar")
                with Horizontal(id="controls"):
                    yield Btn("⏮", id="prev", tooltip="previous")
                    yield Btn("⏯", id="pause", classes="big", tooltip="pause / play")
                    yield Btn("⏭", id="next", tooltip="next")
                    yield Btn("♥", id="like_now", tooltip="like")
                    yield Btn("−", id="voldown", tooltip="volume down")
                    yield Btn("+", id="volup", tooltip="volume up")
                    yield Btn("∞", id="auto", tooltip="autoplay")
                    yield Btn("◐", id="theme", tooltip="next theme")
                    yield Btn("normal", id="vibe", tooltip="vibe: calm · normal · loud")
        with Horizontal(id="tabs"):
            for v in TABS + ["playlist"]:
                yield Btn(v, id=f"t_{v}")
        with Horizontal(id="actions"):
            yield Btn("▶ play", id="r_play")
            yield Btn("+ queue", id="r_queue")
            yield Btn("♥ like", id="r_like")
            yield Btn("≡ playlist", id="r_pl")
            yield Btn("✕ remove", id="r_rm")
        yield ListView(id="list")
        yield Static(id="msg")
        yield Input(placeholder="search a song, or type ? for help", id="prompt")
        yield Static(id="footer")

    def on_mount(self):
        self.player = Player(on_change=self._from_mpv)
        self.show("history")
        self.render_now()
        self.render_controls()
        self.query_one("#art").update(self.empty_art())
        self.set_interval(0.25, self.tick)
        self.query_one("#prompt").focus()

    def on_unmount(self):
        try:  # position at quit, for resume; must never block quitting
            vid, pos, dur = self._played
            self.lib.log("quit", vid, at=int(pos), dur=int(dur))
        except Exception:
            pass
        if hasattr(self, "player"):
            self.player.close()

    def on_resize(self, event):
        self.fit_art()
        self.call_after_refresh(self.render_now)  # widths are only known after layout

    def fit_art(self):
        """Show art only when there's room (big hero art only when tall). Runs on resize,
        theme change and every tick, so the bar's width never waits for the next second."""
        roomy = self.size.width >= 70 and self.size.height >= 26
        tall = self.size.width >= 100 and self.size.height >= 36  # room for 40x20 hero art
        if self.main.has_class("tall") != tall:
            self.main.set_class(tall, "tall")
            if self.layout == "hero":
                self._art_id = None
                self.update_art()
        show = "block" if roomy and self.layout != "focus" else "none"
        if self.query_one("#art").styles.display != show:
            self.query_one("#art").styles.display = show
            self.call_after_refresh(self.render_now)  # the bar's width depends on the art

    @property
    def main(self):
        """The player screen. (self.screen is the popup while help or a picker is open.)"""
        return self.screen_stack[0]

    def on_descendant_focus(self):
        self.render_footer()

    # ---- mpv events (arrive on a background thread) ----
    def _from_mpv(self, name, value):
        if name == "time-pos":  # fires many times a second; redraw once per second
            sec = None if value is None else int(value)
            if sec == self._last_sec:
                return
            self._last_sec = sec
        try:
            self.call_from_thread(self._apply, name, value)
        except RuntimeError:
            pass  # app is shutting down

    def _apply(self, name, value):
        self.state[name] = value
        if name in ("playlist-pos", "playlist-count"):
            if self.view == "queue":
                self.fill_list()
            self.maybe_autofill()
        if name == "time-pos" and self.current_id():
            self._played = (self.current_id(), value, self.state["duration"])
        if name in ("playlist-pos", "media-title"):
            if self.current_id() != self._art_id:
                self.song_changed()
            self.update_art()
            self.render_controls()
        if name == "pause":
            self.render_controls()
        self.render_now()

    # ---- themes: the brain proposes, instant controls adjust ----
    def get_css_variables(self):
        return {**super().get_css_variables(), **{f"ytm-{k}": v for k, v in C.items()}}

    def apply_theme(self, spec=None):
        if spec is not None:
            self.theme_spec = theme.normalize(spec)
        t = theme.apply_vibe(self.theme_spec, self.vibe)
        C.update(theme.colors(t))
        if t["layout"] != self.layout:
            self.layout = t["layout"]
            self._art_id = None  # art size depends on layout: fetch again
            self.update_art()
        for name in theme.LAYOUTS:
            self.main.set_class(name == self.layout, f"layout-{name}")
        self.fit_art()
        self.refresh_css()
        self.fill_list()
        self.render_footer()
        self.render_now()

    def library_themes(self):
        return theme.PRESETS + self.lib.themes()

    def theme_named(self, name):
        return next((t for t in self.library_themes() if t["name"] == name), theme.DEFAULT)

    def song_dict(self, vid):
        t = self.known.get(vid)
        if t:
            title, artist = track_parts(t)
        else:
            title, artist = split_label(self.state["media-title"] or "")
        return {"id": vid, "title": title, "artist": artist}

    @work(thread=True, exclusive=True, group="brain")
    def think(self, vid, next_vid=None):
        """Judge the current song (and prefetch the next one) on a worker thread.
        Songs measured before cost nothing, so they keep their theme even with paid calls off."""
        try:
            jev, llm, _ = brain.budget(self.lib, self.settings)
            if not jev and not self.lib.features(vid):
                return
            if not self.lib.features(vid):
                self.call_from_thread(self.say, "✦ reading the song …")
            feats = brain.think(self.song_dict(vid), self.lib, llm)
            if vid == self.current_id():
                self.call_from_thread(self.show_song_theme, feats)
            if jev and next_vid and not self.lib.features(next_vid):
                brain.think(self.song_dict(next_vid), self.lib, llm)  # ready before the song starts
        except Exception as e:  # network/API trouble: keep the current look
            self.call_from_thread(self.say, f"brain offline: {escape(str(e))[:60]}")
        finally:
            self.call_from_thread(self.render_footer)  # new spend shows up right away

    def show_song_theme(self, feats):
        self.song_feats = feats
        tags = " · ".join(feats.get("tags", []))
        note = f"{feats['theme']} · {feats['mood']} · energy {int(feats['energy'] * 100)}%" + (f" · {tags}" if tags else "")
        kept = self.keep_look(feats)
        if kept:
            note += f" · kept {self.theme_spec['name']} ({kept})"
        else:
            self.restyle(self.theme_named(feats["theme"]))
        self.say((f"✦ new theme grown from {brain.MIN_CLUSTER}+ similar songs · " if feats.get("new_theme") else "") + escape(note))

    def keep_look(self, feats):
        """Why the current look stays (the restyle schedule, or stickiness), or None to switch."""
        s = self.settings
        if feats["theme"] == self.theme_spec["name"]:
            return None
        if not settings.restyle_due(s["restyle"], self._songs_since, time.time() - self._restyled_at):
            return s["restyle"]
        cur = next((t for t in brain.all_themes(self.lib) if t["name"] == self.theme_spec["name"]), None)
        if cur:  # hysteresis: the new theme must fit clearly better, not just slightly
            gain = math.dist(brain.song_vec(feats), brain.theme_vec(cur)) - feats["dist"]
            if gain < s["stickiness"] * brain.STICKY:
                return "sticky"
        return None

    def restyle(self, spec):
        """Switch to a theme, changing only the parts the can_change setting allows."""
        new, cur, allowed = theme.normalize(spec), self.theme_spec, self.settings["can_change"]
        if "colours" not in allowed:
            new["palette"] = cur["palette"]
        if "motif" not in allowed:
            new["motif"], new["progress"] = cur["motif"], cur["progress"]
        if "layout" not in allowed:
            new["layout"] = cur["layout"]
        self._songs_since, self._restyled_at = 0, time.time()
        self.apply_theme(new)

    def song_changed(self):
        """Log the play/skip of the previous song, then theme the new one."""
        if self._played:
            vid, pos, dur = self._played
            if pos is not None and dur:
                self.lib.log("skip" if pos < dur - 15 else "finish", vid, at=int(pos), dur=int(dur))
        vid = self.current_id()
        self._played = None
        self.song_feats = {}
        if not vid:
            return
        self.lib.log("play", vid)
        self._songs_since += 1
        entries = self.player.playlist()
        pos = self.state["playlist-pos"] or 0
        nxt = VID_RE.search(entries[pos + 1].get("filename", "")) if pos + 1 < len(entries) else None
        self.think(vid, nxt.group(1) if nxt else None)

    def tick(self):
        """4x a second: scroll the motif, move the equaliser, keep art visibility right."""
        if not self.is_running:
            return  # shutting down: the widgets are already being removed
        self._ticks += 1
        if self._ticks % 8 == 0 and self.settings.reload():  # every 2 s: pick up hand edits
            self.say(escape(self.settings.error) if self.settings.error else "⚙ settings reloaded")
            self.render_footer()
        self.fit_art()
        if self.query_one("#info").content_size.width != self._bar_width:
            self.render_now()  # layout moved (resize, art shown/hidden, new theme): redraw the bar
        motion = self.settings["motion"]
        if not self.state["pause"] and self.state["time-pos"] is not None and motion != "off":
            self._phase += 0.25
        if motion == "low" and self._ticks % 4:
            return  # 1 frame a second
        t = theme.apply_vibe(self.theme_spec, self.vibe)
        width = self.query_one("#info").content_size.width
        self.query_one("#motif").update(escape(theme.motif_line(t, width, int(self._phase * 2))))
        if self.layout == "stage":
            energy = self.song_feats.get("energy", 0.5)
            self.query_one("#eq").update(theme.equaliser(width, 3, self._phase, energy))

    # ---- the song that's playing ----
    def current_id(self):
        pos = self.state["playlist-pos"]
        if pos is None or pos < 0:
            return None
        entries = self.player.playlist()
        if pos < len(entries):
            m = VID_RE.search(entries[pos].get("filename", ""))
            return m.group(1) if m else None
        return None

    def current_track(self):
        vid = self.current_id()
        if not vid:
            return None
        return self.known.get(vid) or Track(vid, self.state["media-title"] or "")

    # ---- drawing ----
    def empty_art(self):
        return "\n".join(["░" * ART_W] * ART_H)

    def update_art(self):
        vid = self.current_id()
        if vid and vid != self._art_id:
            self._art_id = vid
            self.load_art(vid)

    @work(thread=True, exclusive=True, group="art")
    def load_art(self, vid):
        big = self.layout == "hero" and self.main.has_class("tall")
        img = art.fetch(vid, ART_W * (2 if big else 1), ART_H * (2 if big else 1))
        if img is not None and vid == self._art_id:
            self.call_from_thread(self.query_one("#art").update, img)

    def render_now(self):
        s = self.state
        t = self.current_track() if hasattr(self, "player") else None
        if t:
            title, artist = track_parts(t)
        elif s["media-title"]:
            title, artist = split_label(s["media-title"])
        else:
            title, artist = "Nothing playing", "search for a song below to start"
        t = theme.apply_vibe(self.theme_spec, self.vibe)
        self.query_one("#title").update(escape(theme.spaced(title) if t["layout"] == "hero" else title))
        self.query_one("#artist").update(escape(artist))
        width = self._bar_width = self.query_one("#info").content_size.width
        f = self.song_feats
        line = " — ".join(x for x in (f.get("headline"), f.get("blurb") if self.vibe != "calm" else "") if x)
        self.query_one("#headline").update(escape(line))
        self.query_one("#headline").display = bool(line)

        pos, dur = s["time-pos"], s["duration"]
        right = f"  {theme.progress_label(t, pos, dur)}   vol {int(s['volume'] or 0)}%"
        full, cursor, empty = theme.progress_bar(t, max(10, width - len(right)), pos, dur)
        self.query_one("#bar").update(
            f"[{C['mauve']}]{escape(full)}[/][b {C['pink']}]{escape(cursor)}[/][{C['s1']}]{escape(empty)}[/]"
            f"[{C['sub']}]{escape(right)}[/]"
        )

    def render_controls(self):
        self.query_one("#pause").label = "▶" if self.state["pause"] else "⏸"
        vid = self.current_id() if hasattr(self, "player") else None
        self.query_one("#like_now").set_class(bool(vid and vid in self.lib.liked_ids()), "on")
        auto = self.query_one("#auto")
        auto.set_class(self.auto, "on")  # green when on, dim when off (CSS)

    def render_tabs(self):
        for b in self.query("#tabs Btn"):
            v = b.id[2:]
            b.display = (v != "results" or bool(self.results)) and (v != "playlist" or self.view == "playlist")
            b.set_class(v == self.view, "current")
            if v == "playlist" and self.open_playlist:
                b.label = f"≡ {self.open_playlist}"

    def render_actions(self):
        """Show only the row buttons that make sense for the current tab."""
        v = self.view
        shown = {
            "queue": {"r_play", "r_like", "r_pl", "r_rm"},
            "playlists": {"r_play", "r_queue", "r_rm"},
            "playlist": {"r_play", "r_queue", "r_like", "r_rm"},
        }.get(v, {"r_play", "r_queue", "r_like", "r_pl"})
        for b in self.query("#actions Btn"):
            b.display = b.id in shown
        self.query_one("#r_play").label = "▶ play all" if v == "playlists" else "▶ play"
        self.query_one("#r_queue").label = "+ queue all" if v == "playlists" else "+ queue"
        row = self.query_one("#list", ListView).highlighted_child
        liked = isinstance(row, Row) and row.track.video_id in self.lib.liked_ids()
        self.query_one("#r_like").set_class(liked, "on")
        self.query_one("#r_like").label = "♥ liked" if liked else "♡ like"

    def render_footer(self):
        if self.focused is self.query_one("#list"):
            pairs = [("enter", "play"), ("a", "queue"), ("l", "like"), ("s", "playlist"),
                     ("d", "remove"), ("←→", "tabs"), ("esc", "back")]
        else:
            pairs = [("enter", "search"), ("tab", "list"), ("^space", "pause"), ("^n", "next"), ("?", "help")]
        _, _, why = brain.budget(self.lib, self.settings)
        today = sum(usd for _, usd in self.lib.spend(settings.start_of("today")).values())
        why = None if why == "mode off" else why
        status = " · ".join(x for x in (self.settings["mode"], why, today and f"{fmt_usd(today)} today") if x)
        room = self.size.width - 4 - len(status) - 3
        while pairs and len("   ".join(f"{k} {d}" for k, d in pairs)) > room:
            pairs.pop()
        self.query_one("#footer").update(keys(*pairs) + f"   [{C['dim']}]{escape(status)}[/]")

    def change_setting(self, cmd, arg):
        """`set` lists settings, `set key value` changes one, `mode x` = `set mode x`."""
        key, _, value = (f"mode {arg}" if cmd == "mode" else arg).partition(" ")
        if not key or not value:
            lines = []
            for k, (_, _, why) in settings.SPEC.items():
                v = settings._toml(self.settings[k])
                lines += [f"[b {C['blue']}]{k}[/] = [{C['text']}]{escape(v)}[/]", f"  [{C['dim']}]{escape(why)}[/]"]
            self.push_screen(HelpScreen(lines + ["", f"[{C['sub']}]change one: set <key> <value>[/]"], "settings"))
            return
        try:
            v = self.settings.set(key, value)
        except ValueError as e:
            self.say(escape(str(e)))
            return
        self.lib.log("setting", "", key=key, to=v)
        self.say(f"⚙ {escape(key)} = {escape(settings._toml(v))}")
        self.render_footer()

    def cost_report(self):
        def line(period, s):
            calls = " · ".join(f"{n} {api}" for api, (n, _) in sorted(s.items())) or "no calls"
            return f"{period} {fmt_usd(sum(u for _, u in s.values()))} ({calls})"
        self.say(escape(" · ".join(line(p, self.lib.spend(t)) for p, t in
                                   (("today", settings.start_of("today")), ("month", settings.start_of("month")), ("all", 0)))))

    def fill_list(self):
        lv = self.query_one("#list", ListView)
        old = lv.index
        liked = self.lib.liked_ids()
        items = []  # built first: lv.clear() only finishes after this frame, so lv.children is stale
        if self.view == "queue":
            for i, e in enumerate(self.player.playlist()):
                url = e.get("filename", "")
                m = VID_RE.search(url)
                vid = m.group(1) if m else url
                t = self.known.get(vid) or Track(vid, self.state["media-title"] if e.get("current") else url)
                items.append(Row(t, i + 1, current=bool(e.get("current")), liked=vid in liked))
        elif self.view == "playlists":
            items = [PlaylistRow(name, count) for name, count in self.lib.playlists()]
        else:
            tracks = {
                "results": lambda: self.results,
                "liked": self.lib.liked,
                "playlist": lambda: self.lib.playlist(self.open_playlist),
            }.get(self.view, lambda: library.history(100))()
            items = [Row(t, i, liked=t.video_id in liked) for i, t in enumerate(tracks, 1)]
        if not items:
            empty = {"liked": "no liked songs yet · press ♥ on a song",
                     "playlists": "no playlists yet · use ≡ playlist on any song, or type save <name>",
                     "queue": "queue is empty · search for a song"}.get(self.view, "nothing here")
            items = [ListItem(Label(f"[{C['dim']}]{empty}[/]"))]
        lv.clear()
        lv.extend(items)
        index = min(old or 0, len(items) - 1)
        self.call_after_refresh(setattr, lv, "index", index)  # once the new rows are mounted
        self.render_tabs()
        self.render_actions()

    def show(self, view):
        if view != self.view:
            self.query_one("#list", ListView).index = 0
        self.view = view
        self.fill_list()

    def say(self, text):
        self.query_one("#msg").update(text)

    # ---- adding music ----
    def play_tracks(self, tracks, replace):
        for t in tracks:
            self.known[t.video_id] = t
        for i, t in enumerate(tracks):
            if replace and i == 0:
                self.player.play(t.url)
            else:
                self.player.queue(t.url)
        if self.view == "queue":
            self.fill_list()

    # ---- autoplay ----
    def queue_ids(self):
        ids = []
        for e in self.player.playlist():
            m = VID_RE.search(e.get("filename", ""))
            if m:
                ids.append(m.group(1))
        return ids

    def maybe_autofill(self):
        """When playing one of the last two songs, append a mix seeded from the last one."""
        if not self.auto or self._filling:
            return
        pos, count = self.state.get("playlist-pos"), self.state.get("playlist-count")
        if pos is None or pos < 0 or not count or pos < count - 2:
            return
        ids = self.queue_ids()
        if ids:
            self._filling = True
            self.autofill(ids[-1], set(ids))

    @work(thread=True, group="autoplay")
    def autofill(self, seed, existing):
        try:
            new = [t for t in search.radio(seed, limit=30) if t.video_id not in existing][:10]
            if new:
                self.call_from_thread(self.play_tracks, new, False)
                self.call_from_thread(self.say, f"autoplay · added {len(new)} similar {'song' if len(new) == 1 else 'songs'}")
        except Exception as e:
            self.call_from_thread(self.say, f"autoplay failed: {escape(str(e))}")
        finally:
            self.call_from_thread(setattr, self, "_filling", False)

    def toggle_auto(self, value=None):
        self.auto = (not self.auto) if value is None else value
        self.render_controls()
        self.say(f"autoplay {'on' if self.auto else 'off'}")
        self.maybe_autofill()

    @work(thread=True, exclusive=True)
    def do_search(self, query, action):
        """Network lookups run on a worker thread so the UI never freezes."""
        self.call_from_thread(self.say, f"searching {escape(query)} …")
        try:
            results = search.search(query)
            if not results:
                self.call_from_thread(self.say, f"no results for {escape(query)}")
                return
            top = results[0]
            if action == "search":
                self.results = results
                self.call_from_thread(self.show, "results")
                self.call_from_thread(self.say, "")
                self.call_from_thread(self.query_one("#list").focus)
            elif action == "radio":
                tracks = search.radio(top.video_id) or [top]
                self.call_from_thread(self.play_tracks, tracks, True)
                self.call_from_thread(self.show, "queue")
                self.call_from_thread(self.say, f"radio · {songs(len(tracks))} queued")
            else:
                self.call_from_thread(self.play_tracks, [top], action == "play")
                verb = "playing" if action == "play" else "queued"
                self.call_from_thread(self.say, f"{verb} · {escape(top.label)}")
        except Exception as e:  # network errors etc. should not kill the app
            self.call_from_thread(self.say, f"[{C['red']}]error: {escape(str(e))}[/]")

    # ---- likes & playlists ----
    def like(self, t: Track):
        on_ = self.lib.toggle_like(tidy(t))
        self.say(f"{'♥ liked' if on_ else 'unliked'} · {escape(track_parts(t)[0])}")
        self.render_controls()
        self.fill_list()

    def add_to_playlist(self, tracks, what):
        def done(name):
            if name:
                n = self.lib.add_to_playlist(name, [tidy(t) for t in tracks])
                self.say(f"≡ added {n} song{'s' * (n != 1)} to {escape(name)}")
                if self.view in ("playlists", "playlist"):
                    self.fill_list()
        self.push_screen(PlaylistPicker(self.lib.playlists(), what), done)

    def queue_tracks(self):
        """Tracks currently in the mpv queue, with the best titles we know."""
        cur, out = self.current_id(), []
        for v in self.queue_ids():
            t = self.known.get(v)
            if not t:  # e.g. a pasted URL: use what mpv reports for the song playing
                title, artist = split_label(self.state["media-title"] or "") if v == cur else ("", "")
                t = Track(v, title or v, artist)
            out.append(t)
        return out

    # ---- the prompt ----
    @on(Input.Submitted, "#prompt")
    def run_command(self, event):
        line = event.value.strip()
        event.input.value = ""
        self.say("")
        if not line:
            return
        cmd, _, arg = line.partition(" ")
        cmd, arg = cmd.lower(), arg.strip()
        p = self.player
        try:
            if cmd in ("play", "queue", "q+", "radio", "search", "s") and arg:
                action = {"q+": "queue", "s": "search"}.get(cmd, cmd)
                if URL_RE.match(arg) and action in ("play", "queue"):
                    url = arg if arg.startswith("http") else "https://" + arg
                    (p.play if action == "play" else p.queue)(url)
                else:
                    self.do_search(arg, action)
            elif cmd in ("queue", "history", "results", "liked", "playlists") and not arg:
                self.show(cmd)
            elif cmd in USAGE and not arg:
                self.say(f"usage: {USAGE[cmd]}")
            elif cmd in ("auto", "autoplay"):
                self.toggle_auto(None if not arg else arg.lower() in ("on", "1", "yes"))
            elif cmd == "like":
                t = self.current_track()
                self.like(t) if t else self.say("nothing playing")
            elif cmd == "save" and arg:
                n = self.lib.add_to_playlist(arg, [tidy(t) for t in self.queue_tracks()])
                self.say(f"≡ saved {songs(n)} to {escape(arg)}")
            elif cmd in ("skip", "next", "n"):
                p.next()
            elif cmd in ("prev", "back"):
                p.prev()
            elif cmd in ("pause", "p"):
                p.toggle_pause()
            elif cmd in ("vol", "volume"):
                p.set_volume(int(arg))
            elif cmd in ("remove", "rm"):
                n = int(arg)
                if n < 1:
                    raise ValueError(n)
                p.remove(n - 1)
                self.show("queue")
            elif cmd == "clear":
                p.clear()
                self.show("queue")
            elif cmd in ("quit", "exit"):
                self.exit()
            elif cmd in ("set", "mode"):
                self.change_setting(cmd, arg)
            elif cmd == "cost":
                self.cost_report()
            elif cmd in ("help", "?"):
                self.action_help()
            elif URL_RE.match(line):
                p.play(line if line.startswith("http") else "https://" + line)
            else:
                self.do_search(line, "search")  # plain text = search
        except (ValueError, IndexError):
            self.say(f"didn't understand '{escape(line)}' · type ? for help")
        except RuntimeError as e:
            self.say(escape(str(e)))

    # ---- buttons ----
    @on(Button.Pressed)
    def pressed(self, event):
        bid = event.button.id or ""
        p = self.player
        if bid.startswith("t_"):
            self.show(bid[2:])
        elif bid.startswith("r_"):
            self.action_row({"r_play": "play", "r_queue": "queue", "r_like": "like",
                             "r_pl": "playlist", "r_rm": "remove"}[bid])
        elif bid == "prev":
            p.prev()
        elif bid == "pause":
            p.toggle_pause()
        elif bid == "next":
            p.next()
        elif bid == "voldown":
            p.set_volume((self.state["volume"] or 0) - 10)
        elif bid == "volup":
            p.set_volume((self.state["volume"] or 0) + 10)
        elif bid == "auto":
            self.toggle_auto()
        elif bid == "theme":  # instant: cycle through every theme in the library
            names = [t["name"] for t in self.library_themes()]
            cur = self.theme_spec["name"]
            nxt = names[(names.index(cur) + 1) % len(names)] if cur in names else names[0]
            self.restyle(self.theme_named(nxt))
            self.lib.log("theme_cycle", self.current_id() or "", to=nxt)
            self.say(f"◐ {escape(nxt)}")
        elif bid == "vibe":  # instant: calm strips decoration, loud adds it
            self.vibe = theme.VIBES[(theme.VIBES.index(self.vibe) + 1) % len(theme.VIBES)]
            event.button.label = self.vibe
            self.apply_theme()
            self.lib.log("vibe", self.current_id() or "", to=self.vibe)
        elif bid == "like_now":
            t = self.current_track()
            self.like(t) if t else self.say("nothing playing")

    # ---- list interaction ----
    @on(ListView.Highlighted, "#list")
    def moved(self):
        self.render_actions()

    @on(ListView.Selected, "#list")
    def picked(self, event):
        self.action_row("open")

    def action_row(self, what):
        """Do something with the highlighted row: play, queue, like, playlist, remove."""
        lv = self.query_one("#list", ListView)
        row, idx = lv.highlighted_child, lv.index
        if isinstance(row, PlaylistRow):
            tracks = self.lib.playlist(row.name_)
            if what == "open":
                self.open_playlist = row.name_
                self.show("playlist")
            elif what == "play" and tracks:
                self.play_tracks(tracks, True)
                self.say(f"▶ playing {escape(row.name_)}")
            elif what == "queue" and tracks:
                self.play_tracks(tracks, False)
                self.say(f"+ queued {songs(len(tracks))} from {escape(row.name_)}")
            elif what == "remove":
                self.lib.delete_playlist(row.name_)
                self.say(f"deleted playlist {escape(row.name_)}")
                self.fill_list()
            return
        if not isinstance(row, Row):
            return
        t = row.track
        if what in ("play", "open"):
            if self.view == "queue":
                self.player.jump(idx)
            else:
                self.play_tracks([t], True)
        elif what == "queue" and self.view != "queue":
            self.play_tracks([t], False)
            self.say(f"+ queued · {escape(track_parts(t)[0])}")
        elif what == "like":
            self.like(t)
        elif what == "playlist":
            self.add_to_playlist([t], f"“{track_parts(t)[0]}”")
        elif what == "remove":
            if self.view == "queue":
                self.player.remove(idx)
                self.fill_list()
            elif self.view == "playlist":
                self.lib.remove_from_playlist(self.open_playlist, t.video_id)
                self.fill_list()

    def action_tab(self, step):
        if self.focused is not self.query_one("#list"):
            return
        names = [t for t in TABS if t != "results" or self.results]
        cur = self.view if self.view in names else "playlists"
        self.show(names[(names.index(cur) + step) % len(names)])

    def action_help(self):
        if not isinstance(self.screen, (HelpScreen, PlaylistPicker)):
            self.push_screen(HelpScreen())

    # ---- hotkeys ----
    def action_pause(self):
        self.player.toggle_pause()

    def action_next(self):
        self.player.next()

    def action_prev(self):
        self.player.prev()

    def action_seek(self, seconds):
        self.player.seek(seconds)

    def action_focus_prompt(self):
        self.query_one("#prompt").focus()


def main():
    YtmApp().run()


if __name__ == "__main__":
    main()

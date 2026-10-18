"""The terminal UI (Textual): a compact mini-player card. Run with:  python -m ytm"""

import re

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.markup import escape
from textual.widgets import Input, Label, ListItem, ListView, Static

from . import library, search
from .player import Player
from .search import Track

HELP = (
    "[b]play[/] <song|url>   [b]queue[/] <song>   [b]radio[/] <song>   or just type to search\n"
    "[b]skip  prev  pause  vol[/] <n>   [b]remove[/] <n>   [b]clear[/]   [b]quit[/]\n"
    "[dim]tab → list (enter play · a add · d remove · ←/→ switch view)   esc → prompt\n"
    "ctrl+space pause · ctrl+n next · ctrl+b prev · ctrl+←/→ seek[/]"
)
URL_RE = re.compile(r"^(https?://)?((www|music|m)\.)?youtu(be\.com|\.be)/", re.I)
VID_RE = re.compile(r"(?:v=|youtu\.be/)([\w-]{11})")
# Noise YouTube adds to titles: "(Official Music Video)", "[Lyrics]", "| Lyrics" ...
NOISE_RE = re.compile(
    r"\s*([(\[][^)\]]*\b(official|video|lyrics?|letra|audio|visuali[sz]er|oficial|4k|hd)\b[^)\]]*[)\]]|\|\s*lyrics.*)",
    re.I,
)
VIEWS = ["queue", "history", "results"]


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


class Row(ListItem):
    def __init__(self, track: Track, num: int, current=False, duration=""):
        title, artist = (escape(x) for x in track_parts(track))
        lead = "[b $accent]▶ [/]" if current else f"[dim]{num:>2}[/] "
        name = f"[b]{title}[/]" if current else title
        super().__init__(Label(lead + name + (f"  [dim]{artist}[/]" if artist else "")))
        self.track = track
        self.duration = duration


class YtmApp(App):
    TITLE = "ytm"
    ENABLE_COMMAND_PALETTE = False
    CSS = """
    Screen { align: center middle; background: $background; }
    #card {
        width: 100%; max-width: 84; height: 100%; max-height: 26;
        border: round $primary 50%; padding: 0 1;
    }
    #title { text-style: bold; height: 1; color: $accent; }
    #title, #artist, #list Label { text-wrap: nowrap; text-overflow: ellipsis; }
    #artist { color: $text-muted; height: 1; }
    #bar { height: 1; margin-top: 1; }
    #tabs { height: 1; margin-top: 1; color: $text-muted; }
    #list { height: 1fr; background: transparent; scrollbar-size-vertical: 1; }
    #list > ListItem { background: transparent; }
    #list > ListItem.-highlight { background: $primary 20%; }
    #list:focus > ListItem.-highlight { background: $primary 35%; }
    #msg { height: auto; max-height: 4; color: $text-muted; }
    #prompt { border: none; background: transparent; padding: 0; height: 1; margin-top: 1; }
    #prompt:focus { border: none; }
    """
    BINDINGS = [
        Binding("ctrl+space", "pause", priority=True),
        Binding("ctrl+n", "next", priority=True),
        Binding("ctrl+b", "prev", priority=True),
        Binding("ctrl+right", "seek(10)", priority=True),
        Binding("ctrl+left", "seek(-10)", priority=True),
        Binding("escape", "focus_prompt"),
        Binding("left", "view(-1)"),
        Binding("right", "view(1)"),
        Binding("a", "add_selected"),
        Binding("delete,d", "remove_selected"),
        Binding("ctrl+c,ctrl+q", "quit", priority=True),
    ]

    def __init__(self):
        super().__init__()
        self.theme = "catppuccin-mocha"
        self.state = {"media-title": None, "time-pos": None, "duration": None,
                      "pause": False, "volume": 70, "playlist-pos": -1}
        self.known = {}  # video id -> Track, so the queue can show proper titles
        self.results = []
        self.view = "history"
        self._last_sec = None

    def compose(self) -> ComposeResult:
        with Vertical(id="card"):
            yield Static(id="title")
            yield Static(id="artist")
            yield Static(id="bar")
            yield Static(id="tabs")
            yield ListView(id="list")
            yield Static(id="msg")
            yield Input(placeholder="search or command · ? for help", id="prompt")

    def on_mount(self):
        self.player = Player(on_change=self._from_mpv)
        self.show("history")
        self.render_now()
        self.query_one("#prompt").focus()

    def on_unmount(self):
        if hasattr(self, "player"):
            self.player.close()

    def on_resize(self):
        self.render_now()

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
        if name in ("playlist-pos", "playlist-count") and self.view == "queue":
            self.fill_list()
        self.render_now()

    # ---- drawing ----
    def current_track(self):
        pos = self.state["playlist-pos"]
        entries = self.player.playlist() if pos is not None and pos >= 0 else []
        if 0 <= (pos or 0) < len(entries):
            m = VID_RE.search(entries[pos].get("filename", ""))
            if m and m.group(1) in self.known:
                return self.known[m.group(1)]
        return None

    def render_now(self):
        s = self.state
        t = self.current_track() if hasattr(self, "player") else None
        if t:
            title, artist = track_parts(t)
        elif s["media-title"]:
            title, artist = split_label(s["media-title"])
        else:
            title, artist = "Nothing playing", "type a song below to start"
        icon = "⏸ " if s["pause"] else ""
        self.query_one("#title").update(icon + escape(title))
        self.query_one("#artist").update(escape(artist))

        pos, dur = s["time-pos"], s["duration"]
        right = f"  {fmt_time(pos)} / {fmt_time(dur)}  vol {int(s['volume'] or 0)}"
        width = max(10, self.query_one("#card").content_size.width - len(right))
        filled = int(width * pos / dur) if pos and dur else 0
        self.query_one("#bar").update(
            f"[$accent]{'━' * filled}[/][$panel-lighten-2]{'━' * (width - filled)}[/][dim]{right}[/]"
        )

    def render_tabs(self):
        parts = []
        for v in VIEWS:
            if v == "results" and not self.results:
                continue
            parts.append(f"[b $background on $accent] {v} [/]" if v == self.view else f"[dim] {v} [/]")
        self.query_one("#tabs").update(" ".join(parts))

    def fill_list(self):
        lv = self.query_one("#list", ListView)
        old = lv.index
        lv.clear()
        if self.view == "queue":
            for i, e in enumerate(self.player.playlist()):
                url = e.get("filename", "")
                m = VID_RE.search(url)
                vid = m.group(1) if m else url
                t = self.known.get(vid) or Track(vid, self.state["media-title"] if e.get("current") else url)
                lv.append(Row(t, i + 1, current=bool(e.get("current"))))
        else:
            tracks = self.results if self.view == "results" else library.history(100)
            for i, t in enumerate(tracks, 1):
                lv.append(Row(t, i))
        if old is not None and lv.children:
            lv.index = min(old, len(lv.children) - 1)
        self.render_tabs()

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

    @work(thread=True, exclusive=True)
    def do_search(self, query, action):
        """Network lookups run on a worker thread so the UI never freezes."""
        self.call_from_thread(self.say, f"[dim]searching {query} …[/]")
        try:
            results = search.search(query)
            if not results:
                self.call_from_thread(self.say, f"no results for {query}")
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
                self.call_from_thread(self.say, f"[dim]radio · {len(tracks)} tracks[/]")
            else:
                self.call_from_thread(self.play_tracks, [top], action == "play")
                self.call_from_thread(self.say, f"[dim]{'playing' if action == 'play' else 'queued'} {top.label}[/]")
        except Exception as e:  # network errors etc. should not kill the app
            self.call_from_thread(self.say, f"[red]{e}[/]")

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
            elif cmd in ("queue", "history", "results") and not arg:
                self.show(cmd)
            elif cmd in ("skip", "next", "n"):
                p.next()
            elif cmd in ("prev", "back"):
                p.prev()
            elif cmd in ("pause", "p"):
                p.toggle_pause()
            elif cmd in ("vol", "volume"):
                p.set_volume(int(arg))
            elif cmd in ("remove", "rm"):
                p.remove(int(arg) - 1)
                self.show("queue")
            elif cmd == "clear":
                p.clear()
                self.show("queue")
            elif cmd in ("quit", "exit"):
                self.exit()
            elif cmd in ("help", "?"):
                self.say(HELP)
            elif URL_RE.match(line):
                p.play(line if line.startswith("http") else "https://" + line)
            else:
                self.do_search(line, "search")  # plain text = search
        except (ValueError, IndexError):
            self.say(f"bad argument for {cmd}")
        except RuntimeError as e:
            self.say(f"[red]{e}[/]")

    # ---- list interaction ----
    @on(ListView.Selected)
    def picked(self, event):
        if not isinstance(event.item, Row):
            return
        if self.view == "queue":
            self.player.jump(event.list_view.index)
        else:
            self.play_tracks([event.item.track], True)

    def _selected(self):
        lv = self.query_one("#list", ListView)
        return lv.highlighted_child if self.focused is lv and isinstance(lv.highlighted_child, Row) else None

    def action_add_selected(self):
        row = self._selected()
        if row and self.view != "queue":
            self.play_tracks([row.track], False)
            self.say(f"[dim]queued {row.track.label}[/]")

    def action_remove_selected(self):
        row = self._selected()
        if row and self.view == "queue":
            self.player.remove(self.query_one("#list", ListView).index)
            self.fill_list()

    def action_view(self, step):
        if self.focused is not self.query_one("#list"):
            return
        views = [v for v in VIEWS if v != "results" or self.results]
        self.show(views[(views.index(self.view) + step) % len(views)])

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

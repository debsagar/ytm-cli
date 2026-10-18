"""The full-screen terminal UI (Textual). Run with:  python -m ytm"""

import re

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.widgets import Input, Label, ListItem, ListView, Static

from . import library, search
from .player import Player
from .search import Track

HELP = (
    "play <song|url>  queue <song>  radio <song>  search <song> (or just type)  history\n"
    "skip  prev  pause  vol <0-100>  remove <n>  clear  quit      "
    "keys: ctrl+space pause · ctrl+n next · ctrl+b prev · ctrl+←/→ seek · esc prompt"
)
URL_RE = re.compile(r"^(https?://)?((www|music|m)\.)?youtu(be\.com|\.be)/", re.I)
VID_RE = re.compile(r"(?:v=|youtu\.be/)([\w-]{11})")


def fmt_time(s):
    if s is None:
        return "--:--"
    s = int(s)
    return f"{s // 60}:{s % 60:02d}"


class TrackItem(ListItem):
    def __init__(self, track: Track, text: str):
        super().__init__(Label(text))
        self.track = track


class YtmApp(App):
    TITLE = "ytm"
    ENABLE_COMMAND_PALETTE = False
    CSS = """
    Screen { background: $background; }
    #panels { height: 1fr; }
    .panel { width: 1fr; border: round $primary; border-title-color: $accent; }
    #queue { border: round $success; }
    ListView { background: transparent; }
    ListItem.--highlight { background: $primary 40%; }
    #now { height: 3; padding: 0 1; border: round $accent; }
    #msg { height: auto; color: $text-muted; padding: 0 1; }
    #prompt { border: round $primary; }
    """
    BINDINGS = [
        Binding("ctrl+space", "pause", "pause", priority=True),
        Binding("ctrl+n", "next", "next", priority=True),
        Binding("ctrl+b", "prev", "prev", priority=True),
        Binding("ctrl+right", "seek(10)", show=False, priority=True),
        Binding("ctrl+left", "seek(-10)", show=False, priority=True),
        Binding("escape", "focus_prompt", show=False),
        Binding("a", "add_selected", "add to queue", show=False),
        Binding("delete,d", "remove_selected", "remove", show=False),
        Binding("ctrl+c,ctrl+q", "quit", "quit", priority=True),
    ]

    def __init__(self):
        super().__init__()
        self.state = {"media-title": None, "time-pos": None, "duration": None,
                      "pause": False, "volume": 70, "playlist-pos": -1}
        self.labels = {}  # video id -> "Artist - Title", for queue display
        self._last_sec = None

    def compose(self) -> ComposeResult:
        with Horizontal(id="panels"):
            yield ListView(id="queue", classes="panel")
            yield ListView(id="side", classes="panel")
        yield Static(id="now")
        yield Static(HELP, id="msg")
        yield Input(placeholder="type a song to search, or a command (help)", id="prompt")

    def on_mount(self):
        self.query_one("#queue").border_title = "Queue"
        self.query_one("#side").border_title = "History"
        self.player = Player(on_change=self._from_mpv)
        self.show_history()
        self.render_now()
        self.query_one("#prompt").focus()

    def on_unmount(self):
        if hasattr(self, "player"):
            self.player.close()

    # ---- mpv events (arrive on a background thread) ----
    def _from_mpv(self, name, value):
        if name == "time-pos":  # fires many times a second; only redraw once per second
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
        if name in ("playlist-pos", "playlist-count", "media-title"):
            self.refresh_queue()
        self.render_now()

    # ---- drawing ----
    def render_now(self):
        s = self.state
        title = s["media-title"] or "nothing playing"
        pos, dur = s["time-pos"], s["duration"]
        width = 40
        filled = int(width * pos / dur) if pos and dur else 0
        bar = "━" * filled + "●" + "─" * (width - filled)
        icon = "⏸" if s["pause"] else "▶"
        vol = int(s["volume"] or 0)
        self.query_one("#now").update(
            f"[b]{icon} {title}[/b]\n[$accent]{bar}[/]  {fmt_time(pos)} / {fmt_time(dur)}   vol {vol}%"
        )

    def refresh_queue(self):
        lv = self.query_one("#queue", ListView)
        entries = self.player.playlist()
        old = lv.index
        lv.clear()
        for i, e in enumerate(entries):
            url = e.get("filename", "")
            m = VID_RE.search(url)
            vid = m.group(1) if m else url
            label = self.labels.get(vid) or (self.state["media-title"] if e.get("current") else None) or url
            mark = "▶" if e.get("current") else " "
            lv.append(TrackItem(Track(vid, label), f"{mark} {i + 1:>2}. {label}"))
        if old is not None and entries:
            lv.index = min(old, len(entries) - 1)

    def set_side(self, title, tracks):
        lv = self.query_one("#side", ListView)
        lv.border_title = title
        lv.clear()
        for i, t in enumerate(tracks, 1):
            extra = f"  [dim]{t.duration}[/]" if t.duration else ""
            lv.append(TrackItem(t, f"{i:>2}. {t.label}{extra}"))

    def say(self, text):
        self.query_one("#msg").update(text)

    def show_history(self):
        self.set_side("History", library.history(50))

    # ---- adding music ----
    def _remember(self, tracks):
        for t in tracks:
            self.labels[t.video_id] = t.label

    def play_tracks(self, tracks, replace):
        self._remember(tracks)
        for i, t in enumerate(tracks):
            if replace and i == 0:
                self.player.play(t.url)
            else:
                self.player.queue(t.url)
        self.refresh_queue()

    @work(thread=True, exclusive=True)
    def do_search(self, query, action):
        """Network lookups run on a worker thread so the UI never freezes."""
        self.call_from_thread(self.say, f"searching '{query}' ...")
        try:
            results = search.search(query)
            if not results:
                self.call_from_thread(self.say, f"no results for '{query}'")
                return
            top = results[0]
            if action == "search":
                self.call_from_thread(self.set_side, f"Results: {query}", results)
                self.call_from_thread(self.say, "enter = play · a = add to queue · esc = back to prompt")
                self.call_from_thread(self.query_one("#side").focus)
            elif action == "radio":
                tracks = search.radio(top.video_id) or [top]
                self.call_from_thread(self.play_tracks, tracks, True)
                self.call_from_thread(self.say, f"radio from {top.label} ({len(tracks)} tracks)")
            else:
                self.call_from_thread(self.play_tracks, [top], action == "play")
                verb = "playing" if action == "play" else "queued"
                self.call_from_thread(self.say, f"{verb} {top.label}")
        except Exception as e:  # network errors etc. should not kill the app
            self.call_from_thread(self.say, f"[red]error:[/] {e}")

    # ---- the prompt ----
    @on(Input.Submitted, "#prompt")
    def run_command(self, event):
        line = event.value.strip()
        event.input.value = ""
        if not line:
            return
        cmd, _, arg = line.partition(" ")
        cmd, arg = cmd.lower(), arg.strip()
        p = self.player
        try:
            if cmd in ("play", "queue", "q+", "radio", "search", "s"):
                if not arg:
                    return self.say(f"usage: {cmd} <song>")
                action = {"q+": "queue", "s": "search"}.get(cmd, cmd)
                if URL_RE.match(arg) and action in ("play", "queue"):
                    url = arg if arg.startswith("http") else "https://" + arg
                    (p.play if action == "play" else p.queue)(url)
                    self.say(f"{action}: {url}")
                else:
                    self.do_search(arg, action)
            elif cmd in ("skip", "next", "n"):
                p.next()
            elif cmd in ("prev", "back"):
                p.prev()
            elif cmd in ("pause", "p"):
                p.toggle_pause()
            elif cmd in ("vol", "volume"):
                p.set_volume(int(arg))
            elif cmd in ("history", "h"):
                self.show_history()
                self.query_one("#side").focus()
            elif cmd in ("remove", "rm"):
                p.remove(int(arg) - 1)
                self.refresh_queue()
            elif cmd == "clear":
                p.clear()
                self.refresh_queue()
            elif cmd in ("quit", "exit"):
                self.exit()
            elif cmd in ("help", "?"):
                self.say(HELP)
            elif URL_RE.match(line):
                p.play(line if line.startswith("http") else "https://" + line)
            else:
                self.do_search(line, "search")  # plain text = search
        except (ValueError, IndexError):
            self.say(f"bad argument for '{cmd}'")
        except RuntimeError as e:
            self.say(f"[red]{e}[/]")

    # ---- list interaction ----
    @on(ListView.Selected)
    def picked(self, event):
        item = event.item
        if not isinstance(item, TrackItem):
            return
        if event.list_view.id == "queue":
            self.player.jump(event.list_view.index)
        else:
            self.play_tracks([item.track], True)
            self.say(f"playing {item.track.label}")

    def action_add_selected(self):
        lv = self.focused
        if isinstance(lv, ListView) and lv.id == "side" and isinstance(lv.highlighted_child, TrackItem):
            t = lv.highlighted_child.track
            self.play_tracks([t], False)
            self.say(f"queued {t.label}")

    def action_remove_selected(self):
        lv = self.focused
        if isinstance(lv, ListView) and lv.id == "queue" and lv.index is not None:
            self.player.remove(lv.index)
            self.refresh_queue()

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

"""Control a hidden mpv process over its JSON IPC pipe.

This is the only module that knows mpv exists. It uses two pipe connections:
  - a command connection: send a request, wait for the reply with the same id
  - an event connection: a background thread reads property changes forever
Two connections are needed because Windows blocks a pipe while one thread is
reading it, so a single connection can't wait for events and send commands at once.
"""

import itertools
import json
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MPV_CONFIG = ROOT / "mpv"

# Properties the UI cares about; mpv pushes a message whenever one changes.
WATCHED = ["media-title", "time-pos", "duration", "pause", "volume", "playlist-pos", "playlist-count"]


def find_exe(names, dirs):
    for n in names:
        p = shutil.which(n)
        if p:
            return p
    for d in dirs:
        for n in names:
            p = Path(d) / n
            if p.exists():
                return str(p)
    return None


def find_tools():
    local = os.environ.get("LOCALAPPDATA", "")
    links = Path(local) / "Microsoft" / "WinGet" / "Links"
    mpv = find_exe(["mpv.exe", "mpv"], [ROOT / "bin", Path(os.environ.get("ProgramFiles", "")) / "MPV Player", links])
    ytdl = find_exe(["yt-dlp.exe", "yt-dlp"], [ROOT / "bin", links])
    return mpv, ytdl


def _open_pipe(path, timeout=5.0):
    # The pipe only exists once mpv has started, so retry for a few seconds.
    end = time.time() + timeout
    while True:
        try:
            return open(path, "r+b", buffering=0)
        except OSError:
            if time.time() > end:
                raise
            time.sleep(0.1)


class Player:
    def __init__(self, on_change=None, extra_args=()):
        """on_change(name, value) is called from a background thread on every property change."""
        self.on_change = on_change or (lambda name, value: None)
        mpv, ytdl = find_tools()
        if not mpv:
            raise RuntimeError("mpv not found (winget install shinchiro.mpv)")
        self.pipe = r"\\.\pipe\ytm-%d" % os.getpid()
        args = [
            mpv, "--idle=yes", "--no-terminal",
            f"--config-dir={MPV_CONFIG}",
            f"--input-ipc-server={self.pipe}",
            *extra_args,
        ]
        if ytdl:
            args.append(f"--script-opts=ytdl_hook-ytdl_path={ytdl}")
        self.proc = subprocess.Popen(args, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self._ids = itertools.count(1)
        self._lock = threading.Lock()
        self._cmd = _open_pipe(self.pipe)
        self._cmd_reader = self._lines(self._cmd)
        self._evt = _open_pipe(self.pipe)
        for i, name in enumerate(WATCHED, 1):
            self._evt.write((json.dumps({"command": ["observe_property", i, name]}) + "\n").encode())
        threading.Thread(target=self._event_loop, daemon=True).start()

    @staticmethod
    def _lines(f):
        buf = b""
        while True:
            chunk = f.read(4096)
            if not chunk:
                return
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                if line.strip():
                    yield json.loads(line)

    def _event_loop(self):
        try:
            for msg in self._lines(self._evt):
                if msg.get("event") == "property-change":
                    self.on_change(msg["name"], msg.get("data"))
        except Exception:
            pass  # mpv or the UI shut down

    def command(self, *args):
        """Send one mpv command and return its result (raises on error)."""
        with self._lock:
            rid = next(self._ids)
            self._cmd.write((json.dumps({"command": list(args), "request_id": rid}) + "\n").encode())
            for msg in self._cmd_reader:
                if msg.get("request_id") == rid:
                    if msg.get("error") != "success":
                        raise RuntimeError(f"mpv: {msg.get('error')} for {args}")
                    return msg.get("data")
            raise RuntimeError("mpv closed the pipe")

    def get(self, prop):
        try:
            return self.command("get_property", prop)
        except RuntimeError:
            return None

    # ---- playback ----
    def play(self, url):
        self.command("loadfile", url, "replace")

    def queue(self, url):
        self.command("loadfile", url, "append-play")

    def next(self):
        self.command("playlist-next", "force")

    def prev(self):
        self.command("playlist-prev", "force")

    def toggle_pause(self):
        self.command("cycle", "pause")

    def set_volume(self, v):
        self.command("set_property", "volume", max(0, min(100, int(v))))

    def seek(self, seconds):
        self.command("seek", seconds, "relative")

    def jump(self, index):
        self.command("set_property", "playlist-pos", index)

    def remove(self, index):
        self.command("playlist-remove", index)

    def clear(self):
        self.command("playlist-clear")  # keeps the current track

    def playlist(self):
        """List of {'filename', 'current'?} entries in queue order."""
        return self.get("playlist") or []

    def close(self):
        try:
            self.command("quit")
        except (OSError, RuntimeError):
            pass
        try:
            self.proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.proc.kill()

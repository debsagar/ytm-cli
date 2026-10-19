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


def _home():
    """Where your data lives (data/ytm.db, mpv/history.tsv): $YTM_HOME, else the folder named
    in a ytm.home file next to the code (how ytm and ytmdev get different data), else the repo."""
    if os.environ.get("YTM_HOME"):
        return Path(os.environ["YTM_HOME"])
    f = ROOT / "ytm.home"
    return Path(f.read_text(encoding="utf-8").strip()) if f.exists() else ROOT


HOME = _home()

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


def _kill_with_parent(proc):
    """Windows: put mpv in a job object that is killed when this process ends,
    however it ends (quit, closed window, crash). Returns the job handle to keep alive."""
    if os.name != "nt":
        return None
    import ctypes
    from ctypes import wintypes

    class Basic(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                    ("SchedulingClass", wintypes.DWORD)]

    class Extended(ctypes.Structure):
        _fields_ = [("Basic", Basic), ("Io", ctypes.c_uint64 * 6), ("ProcessMemoryLimit", ctypes.c_size_t),
                    ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                    ("PeakJobMemoryUsed", ctypes.c_size_t)]

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateJobObjectW.restype = wintypes.HANDLE
    k32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    job = k32.CreateJobObjectW(None, None)
    info = Extended()
    info.Basic.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    k32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info))  # 9 = ExtendedLimitInformation
    k32.AssignProcessToJobObject(job, int(proc._handle))
    return job


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
            args.append(f"--script-opts-append=ytdl_hook-ytdl_path={ytdl}")
        if HOME != ROOT:  # otherwise history.lua writes next to mpv.conf, as before
            args.append(f"--script-opts-append=ytm-history={HOME / 'mpv' / 'history.tsv'}")
        self.proc = subprocess.Popen(args, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self._job = _kill_with_parent(self.proc)
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
        """Returns False on the last song: mpv would stop and go idle with nothing to play."""
        pos, count = self.get("playlist-pos"), self.get("playlist-count") or 0
        if pos is not None and pos + 1 >= count:
            return False
        self.command("playlist-next", "force")
        return True

    def prev(self):
        pos = self.get("playlist-pos")
        if pos == 0:  # the first song restarts (playlist-prev would leave mpv idle)
            self.command("seek", 0, "absolute")
        elif pos is not None and pos > 0:  # idle (-1): nothing playing to go back from
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
        # Send quit without waiting for a reply (mpv may exit before answering).
        try:
            self._cmd.write(b'{"command": ["quit"]}\n')
        except OSError:
            pass
        try:
            self.proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.proc.kill()

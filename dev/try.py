"""Render ytm scenarios headlessly and report what broke. No mpv, no network, no API spend.

    python dev/try.py dev/breaks/*.json [--out DIR] [--svg | --png [--open]] [--jobs N]

Several files run in parallel child processes (--jobs, default 6); --png renders the
screens to PNG with headless Chrome or Edge, --open opens them.

A scenario is a JSON object (or a list of them). Every field is optional:
  name      label for the output files
  size      [w, h] terminal size (default [74, 24], the real window)
  songs     [{id, title, artist, duration, art: true, theme}] playlist; the first one plays
  pos       seconds into the song; paused: true/false
  theme     a theme name, or a whole theme spec (e.g. a malformed LLM-written one)
  themes    N made-up grown themes added to the library ("grown 01" ...)
  grown     list of whole theme specs added to the library, as the theme writer would
  feats     what the brain "measured" for the song (energy, mood, tags, ...)
  results   songs that search/radio return
  library   "copy" uses a copy of ~/.ytmdev data; default is an empty library
  settings  {key: "value"} applied with `set`, or raw text for settings.toml
  steps     list of: "text typed + Enter" | {"key": "tab"} | {"resize": [w, h]}
            | {"mpv": {"time-pos": 99}} | {"click": "#id", "times": 2} | {"wait": 0.5}
            | {"shot": "label"} (with --svg: saves <name>-<label>.svg mid-run, e.g. animation frames)
  expect    strings that must appear on screen at the end
  absent    strings that must NOT appear (e.g. "Traceback", "None")
  palette   {key: "#rrggbb"} the theme on screen must end up with (after normalize)

Writes OUT/<name>.txt (plain screen text) for each scenario, prints PASS/FAIL,
exits 1 if anything failed."""

import argparse
import asyncio
import glob
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

os.environ.pop("NO_COLOR", None)
REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from rich.console import Console  # noqa: E402
from rich.text import Text  # noqa: E402

import ytm.app as A  # noqa: E402
from ytm import art, brain, library, search, settings, theme  # noqa: E402
from ytm.search import Track  # noqa: E402

DEV_HOME = Path.home() / ".ytmdev"


def track(s):
    return Track(s["id"], s.get("title", ""), s.get("artist", ""), s.get("duration", ""))


class FakePlayer:
    """Same methods as ytm.player.Player; plays nothing and reports state straight to the app."""

    def __init__(self, on_change, catalogue):
        self.app, self.cat, self.items, self.pos = on_change.__self__, catalogue, [], -1

    def _emit(self, **props):
        for k, v in props.items():
            self.app._apply(k.replace("_", "-"), v)

    def _go(self, pos):
        self.pos = pos
        s = self.cat.get(self.items[pos].split("v=")[-1], {}) if 0 <= pos < len(self.items) else {}
        self._emit(playlist_count=len(self.items), playlist_pos=pos, duration=s.get("seconds", 200),
                   media_title=s.get("title"), time_pos=0)

    def playlist(self):
        return [{"filename": u, "current": i == self.pos} for i, u in enumerate(self.items)]

    def play(self, url):
        self.items = [url]
        self._go(0)

    def queue(self, url):
        self.items.append(url)
        self._emit(playlist_count=len(self.items))

    def next(self):
        if self.pos + 1 >= len(self.items):
            return False
        self._go(self.pos + 1)
        return True

    def prev(self):
        if self.pos > 0:
            self._go(self.pos - 1)

    def jump(self, i):
        if 0 <= i < len(self.items):
            self._go(i)

    def remove(self, i):
        del self.items[i]
        self._emit(playlist_count=len(self.items))

    def clear(self):
        self.items = self.items[self.pos:self.pos + 1]
        self.pos = 0 if self.items else -1
        self._emit(playlist_count=len(self.items), playlist_pos=self.pos)

    def toggle_pause(self):
        self._emit(pause=not self.app.state["pause"])

    def set_volume(self, v):
        self._emit(volume=max(0, min(100, v)))

    def seek(self, s):
        self._emit(time_pos=(self.app.state["time-pos"] or 0) + s)

    def command(self, *a):
        return None

    def close(self):
        pass


def fake_art(vid, w, h):
    """Deterministic coloured block instead of downloading a thumbnail."""
    n = sum(map(ord, vid)) % 200
    return Text("\n".join(["▀" * w] * h), style=f"rgb({n},{255 - n},120) on rgb(40,{n // 2},90)")


def screen_text(app):
    c = Console(width=app.size.width, height=app.size.height, file=io.StringIO(),
                record=True, legacy_windows=False, color_system=None)
    c.print(app.screen._compositor.render_update(full=True, screen_stack=app._background_screens))
    return c.export_text().replace("\u200b", "")  # zero-width: invisible in a terminal


async def run(sc, out, svg):
    name = sc.get("name", "scenario")
    songs = sc.get("songs", [])
    for s in songs:  # "3:20" -> 200 seconds, for the fake duration
        d = str(s.get("duration", "3:20"))
        s["seconds"] = sum(int(x) * 60 ** i for i, x in enumerate(reversed(d.split(":")))) if d.replace(":", "").isdigit() else 200
    cat = {s["id"]: s for s in songs}

    home = Path(tempfile.mkdtemp(prefix="ytmtry-"))
    (home / "data").mkdir()
    if sc.get("library") == "copy":
        shutil.copy(DEV_HOME / "data" / "ytm.db", home / "data" / "ytm.db")
    library.Library.__init__.__defaults__ = (home / "data" / "ytm.db",)
    library.HISTORY = home / "history.tsv"
    settings.Settings.__init__.__defaults__ = (home / "settings.toml",)
    if isinstance(sc.get("settings"), str):
        (home / "settings.toml").write_text(sc["settings"], encoding="utf-8")

    theme_in = sc.get("theme")
    feats = {"energy": 0.5, "mood": "happy", "mood_p": {"happy": 1}, "tag_p": {}, "tags": [], "dist": 0.0,
             **sc.get("feats", {})}

    def fake_think(song, lib, llm=True):
        f = dict(feats)
        if cat.get(song["id"], {}).get("theme"):  # a song can carry its own theme
            f["theme"] = cat[song["id"]]["theme"]
        if isinstance(theme_in, dict):
            f.setdefault("theme", str(theme_in.get("name") or "untitled"))
        elif theme_in:
            f.setdefault("theme", theme_in)
        f.setdefault("theme", "neon rave")
        return f

    A.Player = lambda on_change, extra_args=(): FakePlayer(on_change, cat)
    art.fetch = fake_art
    search.search = lambda q, limit=10: [track(s) for s in sc.get("results", [])]
    search.radio = lambda vid, limit=50: [track(s) for s in sc.get("results", [])]
    brain.think, brain.enabled = fake_think, lambda: True
    brain._post = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("dev/try.py: no network"))

    errors, text = [], ""
    try:
        app = A.YtmApp()  # inside the try: a bad settings.toml can crash the constructor
        async with app.run_test(size=tuple(sc.get("size", [74, 24]))) as pilot:
            await pilot.pause(0.2)
            if isinstance(theme_in, dict):
                app.lib.save_theme(theme_in)
            for t in sc.get("grown", []):
                app.lib.save_theme(t)
            for i in range(sc.get("themes", 0)):
                h = f"{(i * 37) % 256:02x}{(i * 91) % 256:02x}{(255 - i * 53) % 256:02x}"
                app.lib.save_theme({"name": f"grown {i + 1:02}", "for": f"made-up theme {i + 1}", "motif": list(theme.MOTIFS)[i % 16],
                                    "palette": {"bg": "#101018", "panel": "#0b0b12", "accent": f"#{h}", "accent2": f"#{h[4:]}{h[:4]}",
                                                "text": "#eeeeee", "dim": "#666677"}})
            if isinstance(sc.get("settings"), dict):
                for k, v in sc["settings"].items():
                    app.settings.set(k, str(v))
            if songs:
                app.play_tracks([track(s) for s in songs], True)
                app._apply("time-pos", sc.get("pos", 30))
                app._apply("pause", bool(sc.get("paused")))
            await pilot.pause(0.5)
            for step in sc.get("steps", []):
                if isinstance(step, str):
                    app.query_one("#prompt").focus()
                    await pilot.press(*step, "enter")
                elif "key" in step:
                    await pilot.press(step["key"])
                elif "resize" in step:
                    await pilot.resize_terminal(*step["resize"])
                elif "mpv" in step:
                    for k, v in step["mpv"].items():
                        app._apply(k, v)
                elif "click" in step:
                    await pilot.click(step["click"], times=step.get("times", 1))
                elif "shot" in step and svg:
                    app.save_screenshot(f"{name}-{step['shot']}.svg", str(out))
                await pilot.pause(step.get("wait", 0.3) if isinstance(step, dict) else 0.3)
            await pilot.pause(0.3)
            text = screen_text(app)
            for k, v in sc.get("palette", {}).items():
                if app.theme_spec["palette"].get(k) != v:
                    errors.append(f"palette {k}: {app.theme_spec['palette'].get(k)} != {v}")
            if svg:
                app.save_screenshot(f"{name}.svg", str(out))
    except Exception:
        errors.append(traceback.format_exc(limit=6))
    finally:
        shutil.rmtree(home, ignore_errors=True)

    for s in sc.get("expect", []):
        if s not in text:
            errors.append(f"expected on screen: {s!r}")
    for s in sc.get("absent", []):
        if s in text:
            errors.append(f"should not be on screen: {s!r}")
    (out / f"{name}.txt").write_text(text + ("\n\n--- errors ---\n" + "\n".join(errors) if errors else ""),
                                     encoding="utf-8")
    return errors


CHROMES = [shutil.which("chrome"), shutil.which("google-chrome"), shutil.which("msedge"),
           r"C:\Program Files\Google\Chrome\Application\chrome.exe",
           r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"]


def to_png(svgs):
    """SVG -> PNG with headless Chrome (or Edge), sized from the SVG's viewBox. Returns the PNGs."""
    chrome = os.environ.get("CHROME") or next((c for c in CHROMES if c and Path(c).exists()), None)
    if not chrome:
        sys.exit("--png needs Chrome or Edge: install one, or set CHROME to its path")

    def one(svg):
        m = re.search(r'viewBox="[\d.]+ [\d.]+ ([\d.]+) ([\d.]+)"', svg.read_text(encoding="utf-8"))
        w, h = (int(float(m.group(1))) + 1, int(float(m.group(2))) + 1) if m else (1200, 800)
        png = svg.with_suffix(".png")
        png.unlink(missing_ok=True)
        subprocess.run([chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--window-size={w},{h}",
                        f"--screenshot={png}", svg.resolve().as_uri()], capture_output=True, timeout=60)
        return png if png.exists() else print(f"PNG FAILED {svg}")
    with ThreadPoolExecutor(4) as pool:
        return [p for p in pool.map(one, svgs) if p]


def split(files, jobs):
    """Run the scenario files in `jobs` child processes (each scenario patches module globals,
    so they can't share one). Returns how many scenarios failed."""
    chunks, load = [[] for _ in range(jobs)], [0] * jobs
    for n, f in sorted(((len(d) if isinstance(d := json.loads(Path(f).read_text(encoding="utf-8")), list) else 1, f)
                        for f in files), reverse=True):  # biggest files first, each to the least loaded child
        i = load.index(min(load))
        chunks[i].append(f)
        load[i] += n
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    procs = [subprocess.Popen([sys.executable, __file__, *c, "--jobs", "1", "--out", str(OUT), *SVG],
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env) for c in chunks if c]
    failed = 0
    for pr in procs:
        text = pr.communicate()[0].decode("utf-8", "replace").replace("\r\n", "\n")
        lines = text.split("\n\n")[0]  # each child's own summary line is dropped
        print(lines.rstrip())
        fails = sum(line.startswith("FAIL ") for line in lines.splitlines())
        if pr.returncode and not fails:  # the child itself crashed
            print(f"FAIL child process\n{text}")
            fails = 1
        failed += fails
    return failed


async def main():
    global OUT, SVG
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--out", default=str(Path(tempfile.gettempdir()) / "ytm-try"))
    ap.add_argument("--svg", action="store_true")
    ap.add_argument("--png", action="store_true", help="also turn the SVGs into PNGs (needs Chrome or Edge)")
    ap.add_argument("--open", action="store_true", help="open the PNGs when done")
    ap.add_argument("--jobs", type=int, default=min(6, os.cpu_count() or 1), help="child processes (default 6)")
    a = ap.parse_args()
    sys.stdout.reconfigure(errors="replace")  # a cp1252 console can't print every screen character
    OUT, SVG = Path(a.out), ["--svg"] if a.svg or a.png or a.open else []
    OUT.mkdir(parents=True, exist_ok=True)
    started = time.time()
    files = [g for f in a.files for g in sorted(glob.glob(f)) or [f]]  # PowerShell passes *.json unexpanded
    failed = 0
    if a.jobs > 1 and len(files) > 1:
        failed = split(files, min(a.jobs, len(files)))
    else:
        for f in files:
            data = json.loads(Path(f).read_text(encoding="utf-8"))
            for i, sc in enumerate(data if isinstance(data, list) else [data]):
                sc.setdefault("name", f"{Path(f).stem}-{i}" if isinstance(data, list) else Path(f).stem)
                errs = await run(sc, OUT, bool(SVG))
                failed += bool(errs)
                print(("FAIL " if errs else "PASS ") + sc["name"] + ("".join(f"\n     {e.strip().splitlines()[-1]}" for e in errs)))
    pngs = []
    if a.png or a.open:
        pngs = to_png([f for f in OUT.glob("*.svg") if f.stat().st_mtime >= started])
    print(f"\n{failed} failed · {time.time() - started:.0f} s · screens in {OUT}" + (f" · {len(pngs)} PNGs" if pngs else ""))
    if a.open:
        for png in pngs:
            os.startfile(png)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    asyncio.run(main())

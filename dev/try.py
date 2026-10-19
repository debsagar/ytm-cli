"""Render ytm scenarios headlessly and report what broke. No mpv, no network, no API spend.

    python dev/try.py dev/breaks/*.json [--out DIR] [--svg]

A scenario is a JSON object (or a list of them). Every field is optional:
  name      label for the output files
  size      [w, h] terminal size (default [74, 24], the real window)
  songs     [{id, title, artist, duration, art: true}] playlist; the first one plays
  pos       seconds into the song; paused: true/false
  theme     a theme name, or a whole theme spec (e.g. a malformed LLM-written one)
  feats     what the brain "measured" for the song (energy, mood, tags, ...)
  results   songs that search/radio return
  library   "copy" uses a copy of ~/.ytmdev data; default is an empty library
  settings  {key: "value"} applied with `set`, or raw text for settings.toml
  steps     list of: "text typed + Enter" | {"key": "tab"} | {"resize": [w, h]}
            | {"mpv": {"time-pos": 99}} | {"click": "#id"} | {"wait": 0.5}
  expect    strings that must appear on screen at the end
  absent    strings that must NOT appear (e.g. "Traceback", "None")

Writes OUT/<name>.txt (plain screen text) for each scenario, prints PASS/FAIL,
exits 1 if anything failed."""

import argparse
import asyncio
import io
import json
import os
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

os.environ.pop("NO_COLOR", None)
REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from rich.console import Console  # noqa: E402
from rich.text import Text  # noqa: E402

import ytm.app as A  # noqa: E402
from ytm import art, brain, library, search, settings  # noqa: E402
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
        if self.pos + 1 < len(self.items):
            self._go(self.pos + 1)

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
        self._emit(volume=max(0, min(130, v)))

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
    return c.export_text()


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

    app, errors, text = A.YtmApp(), [], ""
    try:
        async with app.run_test(size=tuple(sc.get("size", [74, 24]))) as pilot:
            await pilot.pause(0.2)
            if isinstance(theme_in, dict):
                app.lib.save_theme(theme_in)
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
                    await pilot.click(step["click"])
                await pilot.pause(step.get("wait", 0.3) if isinstance(step, dict) else 0.3)
            await pilot.pause(0.3)
            text = screen_text(app)
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


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--out", default=str(Path(tempfile.gettempdir()) / "ytm-try"))
    ap.add_argument("--svg", action="store_true")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    failed = 0
    for f in a.files:
        data = json.loads(Path(f).read_text(encoding="utf-8"))
        for i, sc in enumerate(data if isinstance(data, list) else [data]):
            sc.setdefault("name", f"{Path(f).stem}-{i}" if isinstance(data, list) else Path(f).stem)
            errs = await run(sc, out, a.svg)
            failed += bool(errs)
            print(("FAIL " if errs else "PASS ") + sc["name"] + ("".join(f"\n     {e.strip().splitlines()[-1]}" for e in errs)))
    print(f"\n{failed} failed · screens in {out}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    asyncio.run(main())

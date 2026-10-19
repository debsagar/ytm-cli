"""User settings: how much the brain may spend and how fast the look may change.

Stored in ~/.config/ytm/settings.toml (outside the repo). Edit it by hand or with
`set <key> <value>` in the app; the file is re-read when it changes, so edits
apply without a restart. Bad or missing values fall back to the defaults."""

import math
import re
import time
import tomllib
from pathlib import Path

PATH = Path.home() / ".config" / "ytm" / "settings.toml"
MODEL_ID = re.compile(r"[\w.-]+/[\w.:-]+")
RESTYLE = re.compile(r"^(song|pinned|every \d+|\d+min)$")

# key: (default, allowed values or a type, explanation)
SPEC = {
    "mode": ("jev", ["off", "jev", "yolo"],
             "off: no paid calls · jev: + rare LLM themes · yolo: + widgets"),
    "budget_day": (0.05, float, "$ per day. LLM work stops at 80%, Jev at 100%"),
    "budget_month": (1.0, float, "$ per month, same rule"),
    "restyle": ("song", RESTYLE, "when the look may change: song · every 3 · 10min · pinned"),
    "stickiness": (0.5, float, "0: always jump to the best theme · 1: only for big changes"),
    "can_change": (["colours", "motif", "layout"], ["colours", "motif", "layout"], "what a restyle may touch"),
    "motion": ("full", ["full", "low", "off"], "animation: full · low (1 frame a second) · off"),
    "grow_themes": ("auto", ["auto", "never"], "let the LLM write new themes for new kinds of songs"),
    "llm_model": ("anthropic/claude-haiku-5.5", MODEL_ID, "OpenRouter model that writes themes, e.g. google/gemini-2.5-flash-lite"),
    "max_new_themes_week": (3, int, "cap on LLM-written themes per 7 days"),
}


def _valid(key, v):
    """v if it's an acceptable value for key, else raise ValueError."""
    default, rule, _ = SPEC[key]
    if rule is float or rule is int:
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0:
            raise ValueError(f"{key} must be a number ≥ 0")
        if key == "stickiness" and v > 1:
            raise ValueError("stickiness goes from 0 to 1")
        return rule(v)
    if isinstance(rule, re.Pattern):
        if not isinstance(v, str) or not rule.fullmatch(v):
            raise ValueError(f"{key}: {SPEC[key][2]}")
        return v
    if isinstance(default, list):  # a subset of the allowed values
        if not isinstance(v, list) or not all(isinstance(x, str) and x in rule for x in v):
            raise ValueError(f"{key}: pick from {', '.join(rule)}")
        return v
    if v not in rule:
        raise ValueError(f"{key}: one of {', '.join(rule)}")
    return v


def _parse(key, text):
    """Turn what the user typed after `set key` into a value of the right type."""
    default = SPEC[key][0]
    if isinstance(default, list):
        return [x.strip() for x in text.replace(",", " ").split() if x.strip()]
    if isinstance(default, (int, float)):
        try:
            return float(text.lstrip("$")) if isinstance(default, float) else int(text)
        except ValueError:
            raise ValueError(f"{key} must be a number") from None
    return text


def _toml(v):
    if isinstance(v, str):
        return '"' + v.replace("\\", "\\\\").replace('"', '\\"') + '"'
    if isinstance(v, list):
        return "[" + ", ".join(_toml(x) for x in v) + "]"
    return repr(v)


class Settings:
    def __init__(self, path=PATH):
        self.path = path
        self.values = {k: s[0] for k, s in SPEC.items()}
        self.error = None
        self._mtime = None
        self.reload()

    def __getitem__(self, key):
        return self.values[key]

    def reload(self):
        """Re-read the file if it changed. Returns True if it did (check .error)."""
        try:
            mtime = self.path.stat().st_mtime
        except FileNotFoundError:
            mtime = None
        if mtime == self._mtime:
            return False
        self._mtime = mtime
        data = {}
        if mtime is not None:
            try:
                data = tomllib.loads(self.path.read_text(encoding="utf-8-sig"))  # Notepad adds a BOM
                self.error = None
            except (tomllib.TOMLDecodeError, UnicodeDecodeError) as e:
                self.error = f"settings.toml: {e}"  # keep the last good values
                return True
        for key, (default, _, _) in SPEC.items():
            try:
                self.values[key] = _valid(key, data[key]) if key in data else default
            except ValueError:
                self.values[key] = default
        return True

    def set(self, key, text):
        """Change one setting from text typed in the app. Raises ValueError with a readable reason."""
        if key not in SPEC:
            raise ValueError(f"unknown setting {key}; type `set` to see them all")
        self.values[key] = _valid(key, _parse(key, text.strip()))
        self.save()
        return self.values[key]

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lines = ["# ytm settings. Edit freely; the app picks up changes while running.", ""]
        for key, (_, _, why) in SPEC.items():
            lines += [f"# {why}", f"{key} = {_toml(self.values[key])}", ""]
        self.path.write_text("\n".join(lines), encoding="utf-8")
        self._mtime = self.path.stat().st_mtime


def allowance(s, day, month):
    """What the brain may do right now: (jev allowed, llm allowed, reason when not).
    The LLM stops first (at 80% of a budget), so cheap per-song measuring lasts longest."""
    if s["mode"] == "off":
        return False, False, "mode off"
    used = max(day / s["budget_day"] if s["budget_day"] else 1,
               month / s["budget_month"] if s["budget_month"] else 1)
    if used >= 1:
        return False, False, "budget reached"
    llm = used < 0.8 and s["grow_themes"] == "auto"
    return True, llm, None if llm else ("LLM paused near budget" if used >= 0.8 else None)


def restyle_due(rule, songs_since, seconds_since):
    """Does the cadence setting allow a new look now? (Stickiness is checked separately.)"""
    if rule == "song":
        return True
    if rule == "pinned":
        return False
    if rule.startswith("every "):
        return songs_since >= int(rule.split()[1])
    return seconds_since >= 60 * int(rule[:-3])  # "10min"


def start_of(period):
    """Unix time at the start of today or this month."""
    t = time.localtime()
    day = 1 if period == "month" else t.tm_mday
    return time.mktime((t.tm_year, t.tm_mon, day, 0, 0, 0, 0, 0, -1))

"""The brain.

Jev measures every song once (energy, mood probabilities, context tags): a small
vector that never depends on which themes exist. Themes are cluster centres in
that space; code assigns each song to the nearest one. When at least MIN_CLUSTER
songs sit far from every centre but close to each other, Haiku names and styles
that new cluster. So the library starts at 13 themes and grows only with evidence.

Keys come from ~/.config/ytm/secrets.env (outside the repo) or the environment."""

import json
import math
import os
import time
import urllib.request
from pathlib import Path

from . import context, settings, theme

SECRETS = Path.home() / ".config" / "ytm" / "secrets.env"
JEV_URL = "https://api.typesafe.ai/v1/systemone"
LLM_URL = "https://openrouter.ai/api/v1/chat/completions"
LLM_MODEL = "anthropic/claude-haiku-5.5"  # default of the llm_model setting

# Tuned on 84 real songs after refine(): distance median 0.51, p90 0.70.
OUTLIER = 0.6       # distance beyond which a song doesn't belong to any theme
GROUP = 0.5         # how close outliers must be to each other to form a new cluster
MIN_CLUSTER = 3     # outliers needed before a new theme is written
MAX_THEMES = 24
STICKY = 1.0        # margin at stickiness 1. On 84 songs: 0 -> look changes every 1.2 songs, 0.5 -> 2.7, 1 -> 12

# $ per token. Jev bills input only. OpenRouter usually reports the exact cost itself;
# the Haiku price is the fallback when it doesn't.
JEV_IN = 0.042 / 1e6
LLM_IN, LLM_OUT = 0.10 / 1e6, 0.50 / 1e6


def _key(name):
    if os.environ.get(name):
        return os.environ[name]
    if SECRETS.exists():
        for line in SECRETS.read_text(encoding="utf-8").splitlines():
            k, _, v = line.partition("=")
            if k.strip() == name:
                return v.strip()
    return None


def enabled():
    return bool(_key("TYPESAFE_API_KEY"))


def _post(url, key, body, timeout=20):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={
        "Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def _spend(lib, api, tokens_in, tokens_out, usd, video_id="", estimated=False):
    """Every paid call becomes a 'cost' event, so the UI and the budget cap can add them up."""
    if lib:
        extra = {"estimated": True} if estimated else {}
        lib.log("cost", video_id, api=api, tokens_in=tokens_in, tokens_out=tokens_out, usd=usd, **extra)


def budget(lib, s):
    """(jev allowed, llm allowed, reason when something is off) given the settings
    and what has been spent so far today, this month and on themes this week."""
    total = lambda since: sum(usd for _, usd in lib.spend(since).values())
    jev, llm, why = settings.allowance(s, total(settings.start_of("today")), total(settings.start_of("month")))
    if not enabled():
        return False, False, "no TypeSafe key"
    if llm and lib.themes_since(time.time() - 7 * 86400) >= s["max_new_themes_week"]:
        llm, why = False, "weekly theme cap reached"
    return jev, llm, why


# ---- Jev: measure the song (one request, all questions in parallel) ----
ENERGY = ["slow, quiet, ambient or acoustic", "mid-tempo, relaxed groove",
          "upbeat and danceable", "intense, loud, peak-time banger"]
MOODS = {
    "happy": None, "melancholic": None, "romantic": None, "dark": "brooding, menacing or tense",
    "dreamy": "hazy, floaty, psychedelic", "aggressive": "hard, confrontational, hype",
    "nostalgic": "retro, throwback, wistful", "euphoric": "uplifting, rave, hands-in-the-air",
}
TAGS = {
    "soundtrack": "Is `song` from a film, TV show or video game soundtrack?",
    "motorsport": "Is `song` connected to racing or motorsport (F1, cars, speed)?",
    "south_asian": "Is `song` South Asian (Indian, Bangla, Pakistani) music or sung in a South Asian language?",
    "club": "Is `song` made for clubs or DJ sets (house, techno, garage, bass, EDM)?",
}


def judge(song, lib=None, video_id=""):
    questions = {
        "energy": {"type": "score", "criteria": ENERGY, "instructions": "How energetic is `song`?"},
        "mood": {"type": "choice", "criteria": MOODS, "instructions": "What is the dominant mood of `song`?"},
        **{k: {"type": "noul", "instructions": q} for k, q in TAGS.items()},
    }
    r = _post(JEV_URL, _key("TYPESAFE_API_KEY"), {"model": "jev-latest", "state": {"song": song},
                                                  "questions": questions})
    u = r.get("usage", {})
    _spend(lib, "jev", u.get("input_tokens", 0), u.get("output_tokens", 0),
           u.get("input_tokens", 0) * JEV_IN, video_id)
    a = r["answers"]
    return {
        "energy": round(a["energy"]["score"] / (len(ENERGY) - 1), 2),  # 0..1
        "mood": a["mood"]["choice"], "mood_p": a["mood"]["probabilities"],
        "tag_p": {k: a[k]["noul"] for k in TAGS},
        "tags": [k for k in TAGS if a[k]["noul"] >= 0.6],
        "model": r["model"],
    }


# ---- clustering, all in code ----
def vec(energy, mood, tags):
    """energy 0..1, mood {name: weight}, tags {name: 0..1} -> point in theme space.
    Energy counts double: it's the strongest visual cue."""
    return [2 * energy] + [mood.get(m, 0) for m in MOODS] + [tags.get(t, 0) for t in TAGS]


def song_vec(f):
    return vec(f["energy"], f["mood_p"], f["tag_p"])


def theme_vec(t):
    if "vec" in t:
        return t["vec"]
    c = t["centre"]
    return vec(c["energy"], c["mood"], {k: 1 for k in c["tags"]})


def nearest(v, themes):
    """(theme name, distance) of the closest cluster centre."""
    return min(((t["name"], math.dist(v, theme_vec(t))) for t in themes), key=lambda x: x[1])


def assign(f, themes):
    f["theme"], d = nearest(song_vec(f), themes)
    f["dist"] = round(d, 3)
    return f


# ---- Haiku: style a new cluster from its member songs ----
WRITER_PROMPT = """You design visual themes for a terminal music player.
A group of songs doesn't fit any existing theme. Design ONE theme for songs like these.
"measured" is how energetic/what mood they actually are; let it drive the look:
{songs}
Listener's taste: {profile}
Existing themes (make something clearly different): {existing}

Return ONLY a JSON object:
{{"name": "2-3 word theme name, lowercase",
  "for": "one line: which kinds of songs this theme suits",
  "palette": {{"bg": "#rrggbb", "panel": "#rrggbb", "accent": "#rrggbb", "accent2": "#rrggbb",
              "text": "#rrggbb", "dim": "#rrggbb"}},
  "motif": one of {motifs},
  "progress": {{"style": one of {styles}, "cursor": "one character or emoji, or empty",
               "label": "template using {{pos}} {{dur}} {{pct}} {{lap}} {{laps}}"}}}}
Keep text readable: bg/panel dark, text light, accent vivid."""


def write_theme(songs, profile, existing, lib=None, model=None):
    if not _key("OPENROUTER_API_KEY"):
        return None
    prompt = WRITER_PROMPT.format(songs=json.dumps(songs), profile=json.dumps(profile),
                                  existing=", ".join(existing), motifs=list(theme.MOTIFS),
                                  styles=list(theme.PROGRESS))
    r = _post(LLM_URL, _key("OPENROUTER_API_KEY"), {
        "model": model or settings.Settings()["llm_model"], "max_tokens": 600,  # the JSON is ~250 tokens
        "reasoning": {"effort": "none"},  # hidden reasoning is billed as output and tripled the cost
        "response_format": {"type": "json_object"},
        "usage": {"include": True},  # ask OpenRouter to report the cost
        "messages": [{"role": "user", "content": prompt}]}, timeout=40)
    u = r.get("usage", {})
    tin, tout = u.get("prompt_tokens", 0), u.get("completion_tokens", 0)
    cost = u.get("cost")  # missing: estimate from Haiku prices, which are wrong for other models
    _spend(lib, "llm", tin, tout, cost if cost is not None else tin * LLM_IN + tout * LLM_OUT,
           estimated=cost is None)
    text = r["choices"][0]["message"].get("content") or ""  # empty if the model ran out of max_tokens
    if "{" not in text:
        return None
    return theme.normalize(json.loads(text[text.find("{"):text.rfind("}") + 1]))


def grow(lib, themes):
    """If MIN_CLUSTER outliers lie within OUTLIER of each other, write a theme for them.
    Returns the new theme or None."""
    if len(themes) >= MAX_THEMES:
        return None
    feats = lib.all_features()
    outliers = [(vid, f) for vid, f in feats.items() if f.get("dist", 0) > OUTLIER]
    for vid, f in outliers:
        v = song_vec(f)
        group = [(o, g) for o, g in outliers if math.dist(v, song_vec(g)) <= GROUP]
        if len(group) >= MIN_CLUSTER:
            songs = [s for s in (lib.song(o) for o, _ in group) if s]
            measured = describe([song_vec(g) for _, g in group])
            spec = write_theme({"songs": songs, "measured": measured}, context.slice_for("theme", lib, ids=[o for o, _ in group]),
                                 [t["name"] for t in themes], lib)
            if not spec or spec["name"] in {t["name"] for t in themes}:
                return None
            vs = [song_vec(g) for _, g in group]
            spec["vec"] = [round(sum(c) / len(vs), 3) for c in zip(*vs)]  # centre = mean of members
            lib.save_theme(spec)
            return spec
    return None


def all_themes(lib):
    """Seed + grown themes, each carrying its learned centre when there is one."""
    learned = lib.centres()
    return [{**t, "vec": learned[t["name"]]} if t["name"] in learned else t
            for t in theme.PRESETS + lib.themes()]


def refine(lib, rounds=3):
    """k-means step: move each centre to the mean of its songs, so idealised seed centres
    become realistic and compete fairly with grown ones (which start as a mean)."""
    for _ in range(rounds):
        recluster(lib)
        members = {}
        for f in lib.all_features().values():
            members.setdefault(f["theme"], []).append(song_vec(f))
        for name, vs in members.items():
            lib.set_centre(name, [round(sum(c) / len(vs), 3) for c in zip(*vs)])
    recluster(lib)


def describe(vs):
    """Readable profile of a group of song vectors, for the theme writer."""
    mean = [sum(c) / len(vs) for c in zip(*vs)]
    moods = sorted(zip(MOODS, mean[1:1 + len(MOODS)]), key=lambda x: -x[1])[:3]
    tags = [t for t, p in zip(TAGS, mean[1 + len(MOODS):]) if p >= 0.5]
    return {"energy_0_to_1": round(mean[0] / 2, 2), "top_moods": {m: round(p, 2) for m, p in moods}, "tags": tags}


def think(song, lib, llm=True):
    """Measure a song (cached), assign it to a theme, and (if llm) grow the library
    when a new cluster has formed. Returns the song's features, including 'theme'."""
    lib.remember(song["id"], song["title"], song["artist"], song.get("album", ""))
    f = lib.features(song["id"])
    if not f or "mood_p" not in f:
        # Album only when known: features are cached per song, so this affects new judgments only.
        album = song.get("album") or (lib.song(song["id"]) or {}).get("album")
        f = judge({"title": song["title"], "artist": song["artist"], **({"album": album} if album else {})}, lib, song["id"])
    themes = all_themes(lib)
    assign(f, themes)
    lib.save_features(song["id"], f)
    new = grow(lib, themes) if llm and f["dist"] > OUTLIER else None
    if new:
        recluster(lib)
        f = lib.features(song["id"])
        f["new_theme"] = new["name"] if f["theme"] == new["name"] else None
    return f


def recluster(lib):
    """Re-assign every song after the theme set changed: pure code, no API calls."""
    themes = all_themes(lib)
    for vid, f in lib.all_features().items():
        if "mood_p" in f:
            lib.save_features(vid, assign(f, themes))


def with_look(lib, vid, f):
    """f with the look you settled on for this song (or a very close one) in place of its
    nearest theme. It counts as a perfect fit, so restyle cadence, stickiness and can_change
    still decide whether the look switches. Never saved: clustering keeps the nearest theme."""
    name = context.look_for(lib, vid, f)
    if not name or name == f.get("theme") or name not in {t["name"] for t in all_themes(lib)}:
        return f
    return {**f, "theme": name, "dist": 0.0, "chosen": True}


def measure_next(lib, s):
    """Measure one song known only from history, most played first. True when one was measured,
    False when none are left, None when Jev isn't allowed right now or the call failed."""
    if not budget(lib, s)[0]:
        return None
    st = context.state(lib)
    todo = [v for v in st["_plays"] if v not in st["_feats"]]
    if not todo:
        return False
    vid = max(todo, key=st["_plays"].get)
    artist, sep, title = st["_names"].get(vid, vid).partition(" - ")
    song = lib.song(vid) or ({"title": title, "artist": artist} if sep else {"title": artist, "artist": ""})
    try:
        think({"id": vid, **song}, lib, llm=False)
    except Exception:  # shortcut: offline or API trouble is retried on the next tick, forever
        return None
    return True

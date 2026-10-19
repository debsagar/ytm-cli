"""What ytm knows about the listener, and the small slice of it each model gets.

state(lib) folds the library, Jev's song features, history.tsv and the logged events
into one compact summary: pure code, a few SQL queries and one pass over the history,
remembered until the data changes. Plays fade with a half-life, so taste follows you.
slice_for(consumer, lib, ...) cuts a purpose-specific piece of it under a size cap.

    python -m ytm.context [state|jev|theme|widget|profile]   # see what a model would get

See docs/context.md."""

import json
import math
import sys
import time
from collections import deque

from . import brain, library

HALF_LIFE = 45 * 86400   # a play counts half as much after 45 days
SESSION_GAP = 30 * 60    # a pause this long starts a new session
EARLY = 1 / 3            # a skip before a third of the song is a clear "no"
MIN_N = 3                # behaviour needs this many observations before it's reported
CAPS = {"jev": 200, "theme": 900, "widget": 1000, "profile": 3200}  # JSON chars, ~4 per token
DAYPARTS = [("night", 0), ("morning", 6), ("afternoon", 12), ("evening", 18)]
ENERGY = ["calm", "mid", "upbeat", "intense"]  # quarters of Jev's 0..1 energy
SETTLE = 30              # a look or vibe kept this long (or until the song changes) is a choice
NEAR = 0.25              # songs this close in Jev space share a chosen look (median distance to a theme is 0.51)
TYPICAL = 0.5            # distance that neither pulls a song up nor pushes it down
SHIFT = 10               # how many places a strong reason may move a radio song

_memo = (None, None)


def _r(x):
    return round(x, 2)


def _top(counts, n, total=None):
    """{key: share} of the n biggest, biggest first."""
    total = total or sum(counts.values()) or 1
    return {k: _r(v / total) for k, v in sorted(counts.items(), key=lambda kv: -kv[1])[:n] if v > 0}


def _count(items, key=lambda x: [x]):
    c = {}
    for x in items:
        for k in key(x):
            c[k] = c.get(k, 0) + 1
    return c


def _daypart(hour):
    return [name for name, start in DAYPARTS if hour >= start][-1]


def _plays():
    """(unix time, hour, video id, label) per line of history.tsv ("2026-10-02 18:51"
    <TAB> url <TAB> label, local time), oldest first, streamed."""
    if not library.HISTORY.exists():
        return
    days = {}  # parsing each date once keeps a year of history well under a second
    with open(library.HISTORY, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            parts = line.rstrip("\n").split("\t", 2)
            if len(parts) != 3 or "v=" not in parts[1]:
                continue
            stamp = parts[0]
            try:
                if stamp[:10] not in days:
                    days[stamp[:10]] = time.mktime(time.strptime(stamp[:10], "%Y-%m-%d"))
                hour, minute = int(stamp[11:13]), int(stamp[14:16])
            except ValueError:
                continue
            yield days[stamp[:10]] + 3600 * hour + 60 * minute, hour, parts[1].split("v=", 1)[1][:11], parts[2]


def _settled(rows, per_song=False):
    """The (at, id, to) picks you stayed on: no further pick within SETTLE seconds
    (per_song: or the next pick is on another song, i.e. the song changed)."""
    return [r for r, nxt in zip(rows, rows[1:] + [None])
            if not nxt or nxt[0] - r[0] >= SETTLE or (per_song and nxt[1] != r[1])]


def _signature(lib):
    h = library.HISTORY
    st = h.stat() if h.exists() else None
    counts = lib._q("SELECT (SELECT COUNT(*) FROM events), (SELECT COUNT(*) FROM features), "
                    "(SELECT COUNT(*) FROM likes), (SELECT COUNT(*) FROM playlist_items)")[0]
    return id(lib), str(h), st and (st.st_size, st.st_mtime), counts


def _songs(vids, feats):
    """Energy, moods and tags of a group of songs (a list, or {id: plays}), from their Jev features."""
    n = vids if isinstance(vids, dict) else dict.fromkeys(vids, 1)
    fs = [(feats[v], k) for v, k in n.items() if v in feats]
    total = sum(k for _, k in fs)
    if not total:
        return {}
    moods, tags = {}, {}
    for f, k in fs:
        moods[f["mood"]] = moods.get(f["mood"], 0) + k
        for t in f.get("tags", []):
            tags[t] = tags.get(t, 0) + k
    d = {"energy": _r(sum(f["energy"] * k for f, k in fs) / total), "moods": list(_top(moods, 2))}
    tags = [t for t, k in tags.items() if k / total >= 0.3]
    return {**d, "tags": tags} if tags else d


def state(lib):
    """The whole summary. Cheap to call: rebuilt only when history, events, features,
    likes or playlists changed since the last call."""
    global _memo
    sig = _signature(lib)
    if _memo[0] != sig:
        _memo = (sig, _build(lib))
    return _memo[1]


def _build(lib):
    now = time.time()
    tracks = {i: (t, a) for i, t, a in lib._q("SELECT id, title, artist FROM tracks")}
    feats = {v: f for v, f in lib.all_features().items() if "mood_p" in f}
    liked = lib.liked_ids()
    lists = {}
    for name, vid in lib._q("SELECT playlist, id FROM playlist_items ORDER BY playlist, pos"):
        lists.setdefault(name, []).append(vid)
    in_list = {v for vs in lists.values() for v in vs}

    # history.tsv: plays (faded by age), labels, dayparts, sessions
    weight = {v: 1.0 for v in in_list}
    for v in liked:
        weight[v] = weight.get(v, 0) + 2
    plays, labels, parts = {}, {}, {p: {} for p, _ in DAYPARTS}  # parts: daypart -> {id: plays}
    first = last = start = None
    sessions, recent, in_session = 0, deque(maxlen=50), 0  # only the end of the latest session is kept
    for ts, hour, vid, label in _plays():
        weight[vid] = weight.get(vid, 0) + 0.5 ** ((now - ts) / HALF_LIFE)
        plays[vid] = plays.get(vid, 0) + 1
        labels[vid] = label
        part = parts[_daypart(hour)]
        part[vid] = part.get(vid, 0) + 1
        if last is None or ts - last > SESSION_GAP:
            sessions, in_session, start = sessions + 1, 0, ts
            recent.clear()
        recent.append((ts, vid))
        in_session += 1
        first, last = first or ts, ts

    spelling = {}  # one spelling per artist, whatever the case YouTube used

    def artists(vid):
        if vid in tracks and tracks[vid][1]:
            names = tracks[vid][1].split(", ")
        else:
            label = labels.get(vid, "")
            names = label.split(" - ", 1)[0].split(", ") if " - " in label else []
        return [spelling.setdefault(a.casefold(), a) for a in names]

    def name(vid):
        t, a = tracks.get(vid, (None, None))
        return f"{a} - {t}" if t and a else t or labels.get(vid, vid)

    # events: skips and finishes, look and vibe choices
    outcome = {}  # vid -> [early skips, late skips, finishes]
    for vid, typ, at, dur in lib._q(
            "SELECT id, type, json_extract(data,'$.at'), json_extract(data,'$.dur') "
            "FROM events WHERE type IN ('skip','finish')"):
        o = outcome.setdefault(vid, [0, 0, 0])
        o[2 if typ == "finish" else 0 if (at or 0) < EARLY * (dur or 1) else 1] += 1
    for vid, (early, _, _) in outcome.items():
        weight[vid] = max(0.0, weight.get(vid, 0) - early)
    picks = {"theme_cycle": [], "vibe": []}
    for typ, at, vid, to in lib._q("SELECT type, at, id, json_extract(data,'$.to') FROM events "
                                   "WHERE type IN ('theme_cycle','vibe') ORDER BY at"):
        picks[typ].append((at, vid, to))
    # cycling logs every look passed through; only the one you stay on is a choice
    chosen_look = {vid: to for _, vid, to in _settled(picks["theme_cycle"], per_song=True) if vid}
    vibes = [(_daypart(time.localtime(at).tm_hour), to) for at, _, to in _settled(picks["vibe"])]
    vibe = dict(enumerate(to for _, to in vibes))

    def rates(key):
        """{group: early-skip rate} for groups with enough skip/finish observations."""
        g = {}
        for vid, (early, late, fin) in outcome.items():
            for k in key(vid):
                c = g.setdefault(k, [0, 0])
                c[0], c[1] = c[0] + early, c[1] + early + late + fin
        return {k: _r(e / n) for k, (e, n) in sorted(g.items(), key=lambda kv: -kv[1][0] / kv[1][1])
                if n >= MIN_N}

    # taste: weighted by how much each song matters to you
    art, moods, energy, tags, themes = {}, {}, dict.fromkeys(ENERGY, 0.0), {}, {}
    for vid, w in weight.items():
        for a in artists(vid):
            art[a] = art.get(a, 0) + w
        f = feats.get(vid)
        if not f or not w:
            continue
        moods[f["mood"]] = moods.get(f["mood"], 0) + w
        energy[ENERGY[min(3, int(f["energy"] * 4))]] += w
        for t in f.get("tags", []):
            tags[t] = tags.get(t, 0) + w
        if f.get("theme"):
            themes[f["theme"]] = themes.get(f["theme"], 0) + w
    measured_w = sum(w for v, w in weight.items() if v in feats) or 1

    early = sum(o[0] for o in outcome.values())
    judged = sum(sum(o) for o in outcome.values())
    total = sum(plays.values())
    day = lambda ts, fmt="%Y-%m-%d": time.strftime(fmt, time.localtime(ts))
    return {
        "library": {"songs": len(in_list | liked | set(plays)), "liked": len(liked), "playlists": len(lists),
                    "measured": len(feats), "plays": total, "sessions": sessions,
                    "since": day(first) if first else None},
        "taste": {
            "artists": list(_top(art, 12)),
            "moods": _top(moods, 5),
            "energy": {k: _r(v / measured_w) for k, v in energy.items()},
            "tags": _top(tags, 4, measured_w),
            "themes": _top(themes, 5),
        },
        "contexts": {n: {"songs": len(vs), **_songs(vs, feats), "artists": list(_top(_count(vs, artists), 3)),
            "plays": sum(plays.get(v, 0) for v in vs)}
            for n, vs in [*sorted(lists.items(), key=lambda kv: -len(kv[1])), ("liked", list(liked))] if vs},
        "behaviour": {
            "skips": {"early": _r(early / judged) if judged else None, "n": judged},
            "skip_by_artist": rates(artists),
            "skip_by_mood": rates(lambda v: [feats[v]["mood"]] if v in feats else []),
            "skip_by_theme": rates(lambda v: [feats[v]["theme"]] if v in feats and "theme" in feats[v] else []),
            "dayparts": {p: {"share": _r(sum(vs.values()) / total), **_songs(vs, feats)}
                         for p, vs in parts.items() if vs},
            "looks_left": _top(_count(chosen_look, lambda v: [feats[v]["theme"]] if "theme" in feats.get(v, {})
                                      else []), 4),
            "looks_chosen": _top(_count(chosen_look.values()), 4),
            "vibe": _top(_count(vibe.values()), 3),
        },
        "recent": {"at": day(start, "%Y-%m-%d %H:%M"), "plays": in_session,
                   **_songs([v for _, v in recent], feats),
                   "songs": list(dict.fromkeys(name(v) for _, v in reversed(recent)))[:6],
                   "last_id": recent[-1][1]}
        if recent else {},
        "_names": {v: name(v) for v in set(plays) | in_list},  # for slices; never sent as is
        "_plays": plays, "_lists": lists, "_parts": parts, "_outcome": outcome,
        "_feats": feats, "_recent": list(recent), "_looks": chosen_look, "_vibes": vibes,
    }


# ---- slices: one per consumer, each under its cap ----
def _dump(d):
    return json.dumps(d)  # same as the prompt builders use


def _fit(d, cap):
    """Drop the last (least important) item of the biggest list or dict inside d until it fits."""
    def boxes(x):
        for v in (x.values() if isinstance(x, dict) else x):
            if isinstance(v, (list, dict)):
                if v:
                    yield v
                yield from boxes(v)
    while len(_dump(d)) > cap:
        bs = list(boxes(d))
        if not bs:
            break
        b = max(bs, key=lambda b: len(_dump(b)))
        b.pop() if isinstance(b, list) else b.pop(next(reversed(b)))
    return d


def _public(s, *keys):
    return json.loads(json.dumps({k: s[k] for k in keys}))  # a copy _fit may trim


def _about(s, vids):
    """How you treat a group of songs: where they live, when you play them, whether you skip."""
    vids = set(vids)
    plays = sum(s["_plays"].get(v, 0) for v in vids)
    when = {p: sum(vs.get(v, 0) for v in vids) for p, vs in s["_parts"].items()}
    o = [s["_outcome"][v] for v in vids if v in s["_outcome"]]
    n = sum(sum(x) for x in o)
    return {k: v for k, v in {
        "in": [name for name, vs in s["_lists"].items() if vids & set(vs)],
        "plays": plays, "when": list(_top(when, 2)) if plays else [],
        "early_skips": _r(sum(x[0] for x in o) / n) if n >= MIN_N else None}.items() if v not in (None, [])}


def slice_for(consumer, lib, ids=(), video_id=None):
    """A compact, JSON-able dict for one consumer, within CAPS[consumer] characters.

    jev      the song only. Measurement stays user-independent (see docs/context.md).
    theme    theme writer: taste, playlists as contexts, looks you reject, and how you
             treat the songs in `ids` (the new cluster).
    widget   yolo/widget writers: short taste, the current session, the song playing now.
    profile  a future daily profile rewrite: the whole state, trimmed to fit."""
    s = state(lib)
    if consumer == "jev":  # exactly what brain.think sends today: no listener in it
        vid = video_id or s["recent"].get("last_id")
        return _fit({"song": (lib.song(vid) if vid else None) or {}}, CAPS["jev"])
    if consumer == "theme":
        d = _public(s, "taste", "contexts")
        d["taste"].pop("themes")
        d["contexts"] = {n: {k: c[k] for k in ("energy", "moods", "tags") if k in c} for n, c in d["contexts"].items()}
        b = s["behaviour"]
        d.update({k: v for k, v in {"looks_left": list(b["looks_left"]), "looks_chosen": list(b["looks_chosen"]),
                                    "vibe": list(b["vibe"])[:1]}.items() if v})
        if ids:
            d["these_songs"] = _about(s, ids)
        return _fit(d, CAPS["theme"])
    if consumer == "widget":
        d = _public(s, "taste", "recent")
        d["taste"].pop("themes")
        d["recent"].pop("last_id", None)
        d["now"] = {"daypart": _daypart(time.localtime().tm_hour)}
        typical = s["behaviour"]["dayparts"].get(d["now"]["daypart"])
        if typical:
            d["now"]["usually"] = {k: typical[k] for k in ("energy", "moods") if k in typical}
        vid = video_id or s["recent"].get("last_id")
        if vid:
            f = lib.features(vid) or {}
            d["playing"] = {"song": s["_names"].get(vid, vid), **{k: f[k] for k in ("energy", "mood", "tags", "theme")
                                                                 if k in f}, **_about(s, [vid])}
        return _fit(d, CAPS["widget"])
    if consumer == "profile":
        return _fit(_public(s, "library", "taste", "contexts", "behaviour", "recent"), CAPS["profile"])
    raise ValueError(f"unknown consumer {consumer}; one of state, {', '.join(CAPS)}")


# ---- learning: code that acts on the state, no model involved ----
def _vec(s, vid):
    f = s["_feats"].get(vid)
    return brain.song_vec(f) if f else None


def _mean(vs):
    vs = [v for v in vs if v]
    return [sum(c) / len(vs) for c in zip(*vs)] if vs else None


def scores(lib, tracks, seed=None):
    """{video id: (places to move down, reasons)} for radio candidates. Songs are pulled towards
    the seed (the song a radio started from), else your current session, else this daypart,
    and pushed away from songs you skip early and from artists you skip early."""
    s = state(lib)
    skip_rate = {a.casefold(): r for a, r in s["behaviour"]["skip_by_artist"].items()}
    good, near = (_vec(s, seed), "the seed") if seed else (None, "")
    recent = s["_recent"]
    if not good and recent and time.time() - recent[-1][0] < SESSION_GAP:
        good, near = _mean(_vec(s, v) for _, v in recent), "your session"
    if not good:
        part = _daypart(time.localtime().tm_hour)
        good, near = _mean(_vec(s, v) for v, n in s["_parts"][part].items() for _ in range(n)), f"your {part}s"
    bad = _mean(_vec(s, v) for v, o in s["_outcome"].items() if o[0])
    clip = lambda x: SHIFT * max(-1.0, min(1.0, x))
    out = {}
    for t in tracks:
        shift, why = 0.0, []
        rate, artist = max(((skip_rate.get(a.casefold(), 0), a) for a in (t.artist or "").split(", ")))
        if rate:
            shift += SHIFT * rate
            why.append(f"you skip {artist} early {rate:.0%}")
        v = _vec(s, t.video_id)
        if v and good:
            d = math.dist(v, good)
            shift += clip(d - TYPICAL)
            why.append(f"{'near' if d < TYPICAL else 'far from'} {near} ({d:.2f})")
        if v and bad:
            d = math.dist(v, bad)
            shift += clip(TYPICAL - d)
            why.append(f"{'near' if d < TYPICAL else 'far from'} songs you skip ({d:.2f})")
        out[t.video_id] = (round(shift, 1), why)
    return out


def rerank(lib, tracks, seed=None):
    """Radio candidates reordered for you. Nothing is dropped, songs nothing is known about keep
    their radio order, and the seed, when it comes first, stays first."""
    head = tracks[:1] if seed and tracks and tracks[0].video_id == seed else []
    rest = tracks[len(head):]
    sc = scores(lib, rest, seed)
    return head + [t for _, t in sorted(enumerate(rest), key=lambda it: it[0] + sc[it[1].video_id][0])]


def look_for(lib, vid, feats):
    """The look you settled on for this song, or for the closest song within NEAR, else None."""
    s = state(lib)
    if vid in s["_looks"]:
        return s["_looks"][vid]
    if "mood_p" not in feats:
        return None
    v = brain.song_vec(feats)
    near = [(math.dist(v, _vec(s, o)), to) for o, to in s["_looks"].items() if o in s["_feats"]]
    d, to = min(near, default=(NEAR + 1, None))
    return to if d <= NEAR else None


def resume(lib):
    """{id, at} when the last session ended mid-song: from the quit event, or from a skip
    if that was the last thing that happened. None otherwise."""
    row = lib._q("SELECT type, id, json_extract(data,'$.at'), json_extract(data,'$.dur') FROM events "
                 "WHERE type IN ('play','skip','finish','quit') ORDER BY at DESC LIMIT 1")
    typ, vid, at, dur = row[0] if row else (None,) * 4
    if typ in ("quit", "skip") and vid and at and dur and at < dur - 15:
        return {"id": vid, "at": int(at)}
    return None


def usual_vibe(lib, hour=None):
    """The vibe you settle on at this time of day, if it's a clear habit (≥60% of ≥5 picks)."""
    part = _daypart(time.localtime().tm_hour if hour is None else hour)
    c = _count(to for p, to in state(lib)["_vibes"] if p == part)
    n = sum(c.values())
    top = max(c, key=c.get, default=None)
    return top if n >= 5 and c[top] >= 0.6 * n else None


def main(args):
    lib = library.Library()
    wanted = [a for a in args if a in CAPS or a == "state"] or ["state", *CAPS]
    vid = next((a for a in args if a not in wanted), None)
    for c in wanted:
        if c == "state":
            d = {k: v for k, v in state(lib).items() if not k.startswith("_")}
        else:
            d = slice_for(c, lib, video_id=vid, ids=[vid] if vid and c == "theme" else ())
        n = len(_dump(d))
        cap = f" of {CAPS[c]}" if c in CAPS else ""
        print(f"── {c}: {n}{cap} chars ≈ {n // 4} tokens")
        print(json.dumps(d, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main(sys.argv[1:])

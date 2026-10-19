"""Self-check for what ytm learns without a model (ytm/context.py, brain.with_look, brain.measure_next).

    python dev/learn_check.py [DIR]

Runs on a COPY of real data: DIR (default %TEMP%/ytm-learn) must hold ytm.db and history.tsv,
copied from ~/.ytmdev. Writes only to that copy. No network: brain._post is stubbed."""

import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from ytm import brain, context, library, settings  # noqa: E402
from ytm.search import Track  # noqa: E402

src = Path(sys.argv[1] if len(sys.argv) > 1 else Path(tempfile.gettempdir()) / "ytm-learn")
work = Path(tempfile.mkdtemp(prefix="ytm-learn-"))  # a copy of the copy, so reruns start the same
shutil.copy(src / "ytm.db", work / "ytm.db")
shutil.copy(src / "history.tsv", work / "history.tsv")
library.HISTORY = work / "history.tsv"
lib = library.Library(work / "ytm.db")
os.environ["TYPESAFE_API_KEY"] = "test"  # budget() needs a key; _post below never sends it
brain._post = lambda url, key, body, timeout=20: {
    "model": "stub", "usage": {"input_tokens": 100},
    "answers": {"energy": {"score": 2}, "mood": {"choice": "happy", "probabilities": {"happy": 1.0}},
                **{k: {"noul": 0.1} for k in brain.TAGS}}}
s = context.state(lib)
print(f"copy in {work}: {s['library']}")


def show(title, tracks, seed=None):
    sc = context.scores(lib, tracks, seed)
    after = context.rerank(lib, tracks, seed)
    print(f"\n{title}")
    for i, t in enumerate(after):
        shift, why = sc.get(t.video_id, (0, []))
        print(f"  {i + 1:2}. (was {tracks.index(t) + 1:2}, {shift:+5.1f})  {t.label[:40]:40}  {'; '.join(why)}")
    assert sorted(t.video_id for t in after) == sorted(t.video_id for t in tracks), "rerank dropped or added songs"
    return after, sc


# 1. skip-aware autoplay, on real songs: measured ones mixed with unknown ones
feats = s["_feats"]
known = [Track(v, *(lib.song(v) or {"title": v, "artist": ""}).values()) for v in list(feats)[:6]]
unknown = [Track(f"unknown{i:04}", f"radio song {i}", "Nobody Known") for i in range(4)]
cands = [x for pair in zip(known, unknown) for x in pair] + known[len(unknown):]
after, sc = show("autoplay, real data (session/daypart pull, skipped-song push):", cands)
order = [t for t in after if t in unknown]
assert order == unknown, "unknown songs must keep their radio order"

# an artist you skip early: three early skips on the copy, then the same candidates
victim = known[1]
for _ in range(3):
    lib.log("skip", victim.video_id, at=5, dur=200)
artist = victim.artist.split(", ")[0]
assert context.state(lib)["behaviour"]["skip_by_artist"].get(artist) == 1.0
after, sc = show(f"autoplay after 3 early skips of {artist}:", cands)
assert after.index(victim) > cands.index(victim), "a skipped artist must move down"
assert any("skip" in w for w in sc[victim.video_id][1])

# 2. more like this: radio from a measured song; the seed stays first
seed = known[3]
radio = [seed] + [t for t in cands if t != seed]
after, sc = show(f"radio from {seed.label[:40]} (pulled towards the seed):", radio, seed=seed.video_id)
assert after[0] == seed
assert context.rerank(lib, [], seed="x") == [] and len(context.rerank(lib, unknown)) == 4

# 3. the look you settle on: cycling logs every look passed; only the last of a burst counts
print("\nlooks you settled on (real data):", dict(list(s["_looks"].items())[:5]), f"… {len(s['_looks'])} songs")
target = next(v for v in feats if v not in s["_looks"])
f = dict(feats[target])
auto = f["theme"]
other = next(t["name"] for t in brain.all_themes(lib) if t["name"] != auto)
third = next(t["name"] for t in brain.all_themes(lib) if t["name"] not in (auto, other))
assert brain.with_look(lib, target, f)["theme"] in (auto, *s["_looks"].values())
t0 = time.time() - 100
for i, name in enumerate([third, other]):  # passes `third` 2 s before landing on `other`
    lib._q("INSERT INTO events VALUES (?,?,?,?)", (t0 + 2 * i, "theme_cycle", target, f'{{"to": "{name}"}}'))
lib.log("play", "somethingelse")
st = context.state(lib)
assert st["_looks"][target] == other, st["_looks"].get(target)
g = brain.with_look(lib, target, f)
print(f"  {lib.song(target)['title'][:30]}: auto {auto!r} → cycled past {third!r} → settled {other!r}; next time: {g['theme']!r}")
assert g["theme"] == other and g["dist"] == 0.0
nb = min((v for v in feats if v != target), key=lambda v: context.math.dist(brain.song_vec(feats[v]), brain.song_vec(f)))
d = context.math.dist(brain.song_vec(feats[nb]), brain.song_vec(f))
gn = brain.with_look(lib, nb, dict(feats[nb]))
print(f"  nearest song {lib.song(nb)['title'][:30]} at {d:.2f} (NEAR {context.NEAR}): gets {gn['theme']!r}")
if nb not in st["_looks"]:
    assert (gn["theme"] == other) == (d <= context.NEAR) or gn["theme"] == feats[nb]["theme"] == other
far = max(feats, key=lambda v: context.math.dist(brain.song_vec(feats[v]), brain.song_vec(f)))
if far not in st["_looks"]:
    assert brain.with_look(lib, far, dict(feats[far]))["theme"] == feats[far]["theme"], "no global drift"
assert context._settled([(0, "a", "x"), (5, "a", "y"), (6, "b", "z"), (100, "b", "w")], per_song=True) == \
    [(5, "a", "y"), (6, "b", "z"), (100, "b", "w")]

# 4. resume
print("\nresume, real data:", context.resume(lib))
song = known[0]
lib.log("play", song.video_id)
assert context.resume(lib) is None, "a play as the last thing means nothing to resume"
lib.log("skip", song.video_id, at=83, dur=200)
assert context.resume(lib) == {"id": song.video_id, "at": 83}
lib.log("quit", song.video_id, at=95, dur=200)
r = context.resume(lib)
print(f"  after quit at 1:35: {r} → resume · {lib.song(r['id'])['title']} at 1:35 · press ⏯")
assert r == {"id": song.video_id, "at": 95}
lib.log("quit", song.video_id, at=190, dur=200)
assert context.resume(lib) is None, "quit near the end: nothing to resume"

# 5. the usual vibe by time of day
vibes = context.state(lib)["_vibes"]
print(f"\nvibe picks you settled on (real data, {len(vibes)} of "
      f"{lib._q('SELECT COUNT(*) FROM events WHERE type=?', ('vibe',))[0][0]} presses):",
      {p: context._count(to for q, to in vibes if q == p) for p, _ in context.DAYPARTS})
print("  launch vibe now:", context.usual_vibe(lib) or "normal (no clear habit)")
for i, v in enumerate(["loud", "loud", "loud", "calm", "loud"]):
    lib._q("INSERT INTO events VALUES (?,?,?,?)", (t0 - 3600 * 24 * (i + 1), "vibe", "", f'{{"to": "{v}"}}'))
hour = time.localtime(t0).tm_hour
assert context.usual_vibe(lib, hour) == "loud" or len([1 for q, _ in context.state(lib)["_vibes"]
                                                         if q == context._daypart(hour)]) > 5
print(f"  after 4 loud + 1 calm at {context._daypart(hour)}: {context.usual_vibe(lib, hour)}")

# 6. measure history-only songs, one at a time, with paid calls allowed
st = context.state(lib)
todo = [v for v in st["_plays"] if v not in st["_feats"]]
print(f"\nhistory-only songs to measure: {len(todo)}")
cfg = settings.Settings(work / "settings.toml")
if todo:
    assert brain.measure_next(lib, cfg) is True
    assert len([v for v in context.state(lib)["_plays"] if v not in context.state(lib)["_feats"]]) == len(todo) - 1
cfg.values["mode"] = "off"
assert brain.measure_next(lib, cfg) is None, "mode off: no Jev"
cfg.values["mode"] = "jev"
n = 0
while brain.measure_next(lib, cfg) and n < 500:
    n += 1
assert brain.measure_next(lib, cfg) is False, "done: stop"
print(f"  measured {n + bool(todo)} with the stub, then measure_next → False (stops)")

lib.db.close()
shutil.rmtree(work, ignore_errors=True)
print("\nall checks passed")

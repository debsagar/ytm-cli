# Context: what ytm knows about you

One builder, `ytm/context.py`, turns raw data into small slices, one per consumer. No model ever sees raw history.
`python -m ytm.context [state|jev|theme|widget|profile] [video id]` prints exactly what each one would get, with its size.

```
 sources (raw, append-only)           state (code, ~2-40 KB)           slices (capped)         consumers
 ─────────────────────────            ─────────────────────            ───────────────         ─────────
 tracks · playlists · likes ─┐        library   counts, since           jev      ≤ 200 ch ──▶ Jev, per song
 features (Jev, per song) ───┤        taste     artists, moods,         theme    ≤ 900 ch ──▶ Haiku theme writer
 mpv/history.tsv (plays) ────┼─ state(lib) ─▶ energy, tags, themes ─▶   widget   ≤ 1000 ch ─▶ yolo/widget writers (later)
 events: skip/finish, ───────┘        contexts  playlists + liked,      profile  ≤ 3200 ch ─▶ daily profile rewrite (later)
   theme_cycle, vibe                            each with energy/moods
                                      behaviour skip rates, dayparts,          ▲
                                                looks left/chosen, vibe        └── LLM output (a profile note) would be stored
                                      recent    the latest session                 as data and quoted by the other slices
```

## Timescales

| when | what | cost |
|---|---|---|
| per frame | nothing here; the UI reads state already built | 0 |
| per song | Jev measures a new song once (cached in `features`); events are logged | ~$0.00003, 0.4 s, background |
| on demand | `state(lib)`: SQL aggregates + one streamed pass over history.tsv, memoised until history, events, features, likes or playlists change | 4 ms today, ~1 s and <0.5 MB peak for a year (58k plays); state ~40 KB |
| rare | theme writer gets the `theme` slice (only when 3+ songs fit no theme) | ~$0.0005, ~6 s, background |
| per session (later) | widget writer gets `widget` (yolo mode only) | ~$0.0005 |
| per day (later) | profile rewrite gets `profile`, returns a short note stored as data | ~$0.001 |

## Cold start

First run after `ytm import <urls> --judge`: everything is derived, nothing extra is stored.
Playlists become **contexts** ("Entropy: energy 0.33, dreamy/dark"; "BANGERS ONLY: 0.6, aggressive/euphoric, club"),
likes become a context of their own, and history.tsv gives artists, dayparts and the last session straight away.
The only cost is Jev on the imported songs: $0.003 per 100 songs, once. Songs known only from history.tsv count for artists and
timing; they get moods once Jev measures them.

## The state

- **taste**: top artists, dominant-mood shares, energy quarters (calm/mid/upbeat/intense), tag shares (club, south_asian, …), themes. Each song is weighted by how much it matters: 1 if in a playlist, +2 if liked, +1 per play fading with a **45-day half-life**, −1 per early skip (before a third of the song).
- **contexts**: each playlist and "liked", with size, mean energy, top moods, tags, top artists and plays.
- **behaviour**: early-skip rate overall and by artist, mood and theme (reported once there are 3 or more observations), what you play at night, morning, afternoon and evening, the looks you cycle away from and the ones you land on, and your usual vibe.
- **recent**: the latest session (30-minute gap): start, length, mood and energy, last songs, last id.

## Slices

- **jev**: the song only, `{title, artist}`, exactly what is sent today. **Measurement stays user-independent.** Features feed clustering, and the theme centres are learned from every song. If taste leaked in, the same song would measure differently as you change, cached vectors would go stale, and Jev, which can only score the options it is given, would drift towards moods you already like, so the clusters would collapse into your average. The user comes in *after* measurement, in code (nearest theme, ranking). Weak results on small artists are better fixed with song-side facts such as the album (see open questions).
- **theme**: taste without themes, contexts reduced to energy, moods and tags, looks left or chosen, vibe, and `these_songs` (which playlists the new cluster's songs are in, how often and when you play them, early skips). It replaces `lib.profile()` in `brain.grow`.
- **widget**: short taste, the latest session, `now` (daypart and what you usually play then), and the song playing with how you treat it.
- **profile**: the whole state, trimmed. A daily Haiku rewrite would turn it into a short note of a few lines, stored as data and quoted by the other slices.

Caps are enforced by `_fit`, which drops the last, least important item of the biggest list until the JSON fits (about 4 characters per token).

## Learning over time, without the LLM

The state is a pure function of append-only data, so it can always be rebuilt and never drifts. New plays, likes, skips and look changes appear the next time a slice is built. The half-life lets old favourites fade without deleting anything. Only the optional profile note costs an LLM call.

## Settings

No new setting. Building the state is free code. Paid consumers stay under the existing rules: `mode` (off: no slices sent; jev: theme writer; yolo: + widgets), `budget_day` and `budget_month` (the LLM stops at 80%), `grow_themes` and `max_new_themes_week` for the theme writer. The daily rewrite would be once a day at most, behind the same LLM allowance.

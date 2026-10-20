# How ytm runs

A map of what runs when, for a new contributor or before splitting `ytm/app.py` into widgets. References are `file:function`. There are no line numbers, since they go stale.

## 1. Entry points

### `ytm.cmd`

```
ytm.cmd [args]
├─ .venv\Scripts\python.exe missing → :setup        (first run: needs uv, then `uv sync -q --frozen --no-dev`)
├─ here                 → :app → python -m ytm      (in this terminal)
├─ import <urls>        → python -m ytm.importer import <urls>   (the "import" word is passed too and skipped)
├─ update [stable|dev]  → python -m ytm.update "%~2"   (kept on one line: the update may rewrite ytm.cmd while cmd reads it)
├─ any other args       → :classic
│    powershell ytm.ps1 %*   resolves the request, writes 3 lines to %YTM_OUT%: mpv path, URL, extra mpv options
│    then cmd starts mpv --config-dir=<repo>\mpv <extra> -- <url>   (no PowerShell left in memory)
└─ no args              → wt -w new --size 74,24 … python -m ytm   (falls back to :app without Windows Terminal)
```

`ytm.ps1` (the classic path) splits `--options` (passed to mpv) from the words, then picks a mode: `play`, `radio`, `search`, `history`, `stop` or `help`. `Find-Exe` finds mpv and yt-dlp, and `Search-Songs` runs yt-dlp on the YouTube Music song search, falling back to `ytsearch`. Radio is `watch?v=ID&list=RDAMVMID`, capped at 100 entries. Run directly without `%YTM_OUT%`, the script starts mpv itself. While mpv plays, the keys come from mpv's defaults plus `mpv/input.conf`.

`install.ps1` (`irm … | iex`) installs any missing mpv, yt-dlp, uv, git and Deno with winget. It then clones the repo into `%LOCALAPPDATA%\ytm` and runs `uv sync`, or runs `ytm.cmd update` if a clone is already there. Last, it writes the forwarder `%LOCALAPPDATA%\Microsoft\WindowsApps\ytm.cmd`.

### `python -m ytm`

`ytm/__main__.py` → `ytm/app.py:main` → `YtmApp().run()`. Importing `ytm.app` sets `COLORTERM=truecolor` before Textual loads.

### The other modules

- `python -m ytm.update [stable|dev]` → `ytm/update.py:main`: `git fetch`, then picks a branch: `main` for `stable`, `dev` for `dev`, or with no word the current one. On `main` or `dev` it runs `switch`: `pull --ff-only origin <b>` if already on it, else `fetch origin <b>:<b>` (creates or fast-forwards the local branch), `checkout <b> --` and sets it to track `origin/<b>`. A detached HEAD gets `checkout --detach origin/main`, any other branch `pull --ff-only`. Then `uv sync --frozen --no-dev`. Prints the new version and channel. Any other word prints usage and changes nothing.
- `python -m ytm.importer <urls> [--judge]` → `ytm/importer.py:main` → `import_playlist` (`search._api().get_playlist` → `Library.add_to_playlist`). `--judge` calls `brain.budget` and then `brain.think` once per new song, on the main thread. No UI is running.
- `python -m ytm.context [state|jev|theme|widget|profile] [video id]` → `ytm/context.py:main` prints `state(lib)` or `slice_for(...)` and their sizes. It reads the library and makes no network calls.

## 2. App startup

`YtmApp.__init__` sets up the state dicts, then opens `library.Library()` (creating the tables) and `settings.Settings()` (reading settings.toml). Textual then runs `compose` (section 8), then `YtmApp.on_mount`:

```
on_mount
├─ self.player = Player(on_change=self._from_mpv)   spawns hidden mpv, opens 2 pipes, starts the event thread
├─ show("history") → fill_list                      the default tab
├─ render_now, render_controls, apply_layout
├─ #art ← empty_art()
├─ set_interval(0.25, tick)                         the main loop (section 3)
├─ #prompt.focus()
├─ context.usual_vibe(lib) → vibe, apply_theme()    the vibe you usually settle on at this daypart
├─ context.resume(lib) → loadfile paused at the saved position (never plays sound)
│    set_timer(2, say "resume · … press ⏯")
└─ set_interval(30, backlog)                        measures history-only songs (section 6)
```

`usual_vibe` and `resume` build `context.state` on the UI thread. That's one pass over history.tsv: about 4 ms today, and about 1 s for a year of plays (docs/context.md).

`YtmApp.on_unmount` logs a `quit` event with the last position (which `resume` reads) and then calls `Player.close` (sends `quit`, kills mpv after 2 s). `player._kill_with_parent` also puts mpv in a Windows job object, so mpv dies with Python however Python ends.

## 3. The main loops

| what | where | how often | does |
|---|---|---|---|
| tick | `YtmApp.tick` | 0.25 s | every 8th tick (2 s): `Settings.reload` and a footer redraw if settings.toml changed. Every tick: `apply_layout`, `render_now` if `#info` changed width, advance `_phase` while playing, `#motif` scroll, `#eq` (stage), `#viz_eq`/`#viz_cap` (dashboard). `motion=low` draws 1 frame a second, `off` freezes `_phase` |
| backlog | the inner `backlog()` in `on_mount` | 30 s | when a song is playing, not paused, and no worker is running: a `backlog` thread worker runs `brain.measure_next`. The timer stops when it returns `False` (nothing left) |
| mpv events | `Player._event_loop` (daemon thread) | per property change | `on_change(name, value)` = `YtmApp._from_mpv` |

The mpv events, from the pipe to the screen:

```
mpv ──pipe──▶ Player._event_loop (thread) ──▶ YtmApp._from_mpv
                  time-pos is dropped unless the whole second changed
              ──call_from_thread──▶ YtmApp._apply(name, value)   (UI thread)
                  state[name] = value
                  playlist-pos / playlist-count → fill_list (queue tab) + maybe_autofill
                  time-pos → _played = (id, pos, duration)       for skip logging
                  playlist-pos / media-title → song_changed() if current_id() != _art_id,
                                               update_art(), render_controls()
                  pause → render_controls()
                  always → render_now()
```

`WATCHED` in `ytm/player.py` lists the properties observed: media-title, time-pos, duration, pause, volume, playlist-pos and playlist-count.

A song change does this:

```
song_changed
├─ log "skip" (ended > 15 s before the end) or "finish" for the previous _played
├─ log "play", _songs_since += 1
└─ think(vid, next_vid)                  brain worker (section 4)
update_art → load_art(vid)               art worker: art.fetch → #art
maybe_autofill → autofill(seed, ids)     when on one of the last 2 songs: autoplay worker
```

## 4. A song from start to finish

```
typed "radio daft punk"                  run_command (UI thread)
└─ do_search(query, "radio")             thread worker: never blocks the UI
   ├─ search.search(query)               ytmusicapi
   ├─ search.radio(top.video_id)         ytmusicapi watch playlist
   ├─ context.rerank(lib, tracks, seed)  code only, no model
   └─ call_from_thread(play_tracks)      known[id] = Track; Player.play / Player.queue → mpv loadfile
mpv loads it  ──▶ history.lua on "file-loaded" appends  time <TAB> url <TAB> artist - title  to history.tsv
              ──▶ playlist-pos / media-title events → _apply → song_changed (section 3)
think(vid, next_vid)                     @work(thread=True, exclusive=True, group="brain")
├─ brain.budget(lib, settings)           (jev, llm, why), section 6
├─ brain.think(song_dict(vid), lib, llm)
│   ├─ lib.remember(...)                 tracks row
│   ├─ lib.features(id) cached? else brain.judge → Jev (paid), brain._spend logs "cost"
│   ├─ brain.all_themes → brain.assign   nearest centre: f["theme"], f["dist"]
│   ├─ lib.save_features
│   └─ llm and dist > OUTLIER → brain.grow → write_theme (LLM, paid) → save_theme → recluster
├─ brain.with_look                       the look you settled on for this song or a close one (context.look_for)
├─ vid still current? → call_from_thread(show_song_theme, feats)
└─ prefetch: brain.think(next song) if Jev is allowed and the next song isn't cached
show_song_theme(feats)                   UI thread
├─ keep_look(feats)                      None = switch
│   ├─ settings.restyle_due(restyle, _songs_since, seconds)   cadence: song / every N / Nmin / pinned
│   └─ hysteresis: the gain over the current theme must be ≥ stickiness × brain.STICKY
└─ restyle(theme_named(feats["theme"]))  only the parts in can_change; resets _songs_since
   └─ apply_theme(spec)                  normalize → apply_vibe → C.update(theme.colors) → apply_layout
                                         → refresh_css → fill_list → render_footer → render_now
```

Learning happens later and in code, with no model involved:
- `skip`/`finish`/`play` events, `theme_cycle` and `vibe` picks, and history.tsv feed `context.state`.
- `context.rerank` uses `context.scores` (artists you skip early, distance to the session/daypart/seed, distance to songs you skip) to reorder `radio` and autoplay candidates.
- `brain.with_look` reuses looks you settled on.
- `context.resume` and `context.usual_vibe` set up the next launch.

`exclusive=True` on `think` and `load_art` cancels the previous worker of that group. A thread already inside an HTTP call still finishes, so `think` re-checks `vid == self.current_id()` and `load_art` re-checks `vid == self._art_id` before touching the screen.

## 5. Commands, buttons and keys

Typed input: `YtmApp.run_command` (`@on(Input.Submitted, "#prompt")`) splits the line into `cmd` and `arg`, then goes through one `if/elif` chain:

| typed | goes to |
|---|---|
| `play/queue/q+/radio/search/s <x>` | URL → `Player.play`/`queue`, else the `do_search(arg, action)` worker |
| `queue/history/results/liked/playlists` (no arg) | `show(view)` |
| a command in `USAGE` with no arg | `say("usage: …")` instead of searching for the word |
| `auto [on/off]` | `toggle_auto` |
| `like` | `like(current_track())` |
| `save <name>` | `Library.add_to_playlist(name, queue_tracks())` |
| `skip/next/n`, `prev/back`, `pause/p`, `vol N`, `remove N`/`rm N`, `clear` | `Player` methods directly |
| `set …`, `mode …` | `change_setting` → `Settings.set` (or the settings popup, a `HelpScreen`) |
| `cost` | `cost_report` |
| `layout` | `choose_layout` → `open_picker` → a `Picker` popup that previews each layout; Enter → `pick_layout(name)` |
| `theme`, `themes` | `theme_command` → `choose_theme` → `open_picker`; Enter → `pick_theme(name)`. While a picker is open `_held` keeps the look Esc goes back to, and `restyle` updates it instead of the screen |
| `theme <name>` | `theme_command`: exact (any case) → `pick_theme`; close → did-you-mean; otherwise a search |
| `layout <name>`, `vibe [name]` | `pick_layout`, `set_vibe` |
| `help`, `?` | `action_help` |
| a bare URL | `Player.play` |
| anything else | `do_search(line, "search")` |

`ValueError`/`IndexError` (e.g. `vol abc`) show "didn't understand", and `RuntimeError` (mpv errors) shows its message. The help text is `HELP_ROWS`.

Buttons: `YtmApp.pressed` (`@on(Button.Pressed)`) dispatches on the button id:
- `t_<view>` → `show`
- `r_*` → `action_row` (the same function keys use)
- `prev/pause/next/voldown/volup` → `Player`
- `auto` → `toggle_auto`
- `theme` → cycles `brain.all_themes` through `restyle` and logs `theme_cycle`
- `layout` → `pick_layout()`
- `like_now` → `like`

Keys: `YtmApp.BINDINGS` → `action_*`:
- `ctrl+space/n/b` and `ctrl+←/→` → `action_pause/next/prev/seek`, which call `Player` directly.
- `a/l/s/d` → `action_row('queue'|'like'|'playlist'|'remove')`
- `←/→` → `action_tab`, list only.
- `esc` → `action_focus_prompt`
- `?` → `action_help`
- Enter on the list (`ListView.Selected`) → `picked` → `action_row("open")`.

So one action can have up to three entry points that each call `Player` themselves. Pause, for example, is the `pause` command, the `pause` button and `ctrl+space`. `action_row` is the only shared handler.

Popups: `HelpScreen` (help and settings), `Picker` (layouts and themes) and `PlaylistPicker`. The picker comes from `add_to_playlist` and dismisses with a playlist name or `None`, which goes to its `done` callback.

## 6. The brain and the LLM path

Only two functions make paid calls, both through `brain._post`:
- `brain.judge` sends one POST to Jev (`JEV_URL`), with every question in it. The cost is logged as `api="jev"`.
- `brain.write_theme` sends one POST to OpenRouter (`LLM_URL`) with the `llm_model` setting. The cost comes from `usage.cost`, or is estimated at Haiku prices and marked `estimated`.

Each logs a `cost` event through `brain._spend` → `Library.log`. `Library.spend(since)` adds them up for the footer, `cost` and the budget.

They're reached from these callers:

| caller | thread | gate |
|---|---|---|
| `YtmApp.think` → `brain.think` | `brain` worker | `brain.budget`: no Jev and not cached → return; `llm` is passed through to `grow` |
| `brain.measure_next` (backlog) | `backlog` worker | `budget()[0]`; `think(..., llm=False)`, so it never calls the LLM |
| `importer.main --judge` | CLI main thread | `budget` checked again before each song |

`brain.budget(lib, s)`:
1. `settings.allowance(s, spent today, spent this month)`: mode `off` → nothing. The LLM stops at 80% of either budget (and needs `grow_themes=auto`), and Jev stops at 100%.
2. No `TYPESAFE_API_KEY` (`brain.enabled`) → nothing.
3. The LLM also stops once `max_new_themes_week` themes were written in 7 days (`Library.themes_since`).

Keys come from the environment or `~/.config/ytm/secrets.env` through `brain._key`. Without `OPENROUTER_API_KEY`, `write_theme` returns `None`.

`context.slice_for(consumer, lib, ...)` decides what each consumer is sent:
- `theme`: built in `brain.grow` for `write_theme`.
- `jev`: mirrors what `brain.think` sends, `{title, artist, album?}`. It's built there directly, not through `slice_for`.
- `widget`, `profile`: future consumers, printed only by `python -m ytm.context`.

The UI never waits on a model. Every network call (Jev, LLM, ytmusicapi, thumbnails) runs in a `@work(thread=True)` worker (`think`, `do_search`, `autofill`, `load_art`) or in the `backlog` worker. Workers hand results back only through `call_from_thread`. The UI thread still does quick local work, though:
- Player IPC round-trips (`current_id` calls `Player.playlist` each time).
- SQLite queries: `render_footer` calls `brain.budget` and `Library.spend` on every redraw.
- `brain._key`, which reads secrets.env from `render_footer`.
- `context.state` builds at startup.

## 7. Data

Where it lives: `ytm/player.py:_home` sets `HOME` to `$YTM_HOME`, else the folder named in a `ytm.home` file next to the code, else the repo folder. `library.DB = HOME/data/ytm.db` and `library.HISTORY = HOME/mpv/history.tsv` are fixed at import time.
- `Player.__init__` passes `--script-opts-append=ytm-history=<HOME>/mpv/history.tsv` when `HOME` isn't the repo. Otherwise history.lua writes next to mpv.conf.
- The classic path (`ytm.ps1`, mpv started by `ytm.cmd`) always uses `<repo>\mpv\history.tsv`. It ignores `ytm.home` and `YTM_HOME`.
- Settings (`settings.PATH`) and keys (`brain.SECRETS`) are always in `~/.config/ytm/`, whatever `HOME` is.

`ytm.db` (`library.SCHEMA`):

| table | written by | read by |
|---|---|---|
| `tracks` | `Library._save` (from `toggle_like`, `add_to_playlist`), `Library.remember` (`brain.think`) | `Library.song/liked/playlist`, `context._build` |
| `likes` | `Library.toggle_like` | `Library.liked_ids/liked`, `context._build`, `context._signature` |
| `playlists`, `playlist_items` | `Library.add_to_playlist`, `remove_from_playlist`, `delete_playlist` | `Library.playlists/playlist`, `context._build` |
| `features` | `Library.save_features` (`brain.think`, `brain.recluster`) | `Library.features/all_features`, `brain.grow`, `context._build` |
| `themes` | `Library.save_theme` (`brain.grow`) | `Library.themes/themes_since`, `brain.all_themes` |
| `centres` | `Library.set_centre`, only from `brain.refine` (a manual tuning step nothing calls) | `Library.centres` → `brain.all_themes` |
| `events` | `Library.log`: `play`, `skip`, `finish`, `quit`, `theme_cycle`, `layout`, `vibe`, `setting`, `cost` | `Library.spend`, `context._build`, `context.resume`, `context._signature` |

The schema also adds `tracks.album` to older databases when it opens them, in `Library.__init__`.

`history.tsv` holds one line per play: `YYYY-MM-DD HH:MM <TAB> url <TAB> artist - title`. `mpv/scripts/history.lua` writes it, and it's read by:
- `library.history()` (the history tab, newest first, one per song)
- `context._plays()` (streams every play for `context.state`)
- `ytm.ps1` (`ytm history`)

`settings.toml` is read by `Settings.reload`: at start, and from `tick` every 2 s when its mtime changes. A bad value falls back to its default, and a parse error keeps the last good values. `Settings.set` → `Settings.save` (the `set` command) rewrites the whole file with comments. `settings.SPEC` holds the keys, defaults and rules.

## 8. UI structure

The widget tree from `YtmApp.compose`:

```
Screen                           classes: layout-<name>, tight, tall
├─ Container#body
│  ├─ Vertical#left
│  │  ├─ Vertical#player.panel           "now playing"
│  │  │  └─ Horizontal#now
│  │  │     ├─ Static#art
│  │  │     └─ Vertical#info
│  │  │        ├─ Static#motif  #eq  #title  #artist  #headline  #bar
│  │  │        └─ Horizontal#controls
│  │  │           ├─ Horizontal: Btn#prev #pause #next #like_now #voldown #volup
│  │  │           └─ Horizontal: Btn#auto #theme #layout
│  │  └─ Vertical#library.panel          "library"
│  │     ├─ Horizontal#tabs     Btn#t_queue #t_history #t_liked #t_playlists #t_results #t_playlist
│  │     ├─ Horizontal#actions  Btn#r_play #r_queue #r_like #r_pl #r_rm
│  │     └─ ListView#list       Row | PlaylistRow | a placeholder ListItem
│  └─ Vertical#right
│     ├─ Vertical#ask.panel              "ask":  Static#log (dashboard only), Static#msg, Input#prompt
│     └─ Vertical#viz.panel              "visualizer" (dashboard only): Static#viz_eq, Static#viz_cap
└─ Static#footer
```

How layouts are applied today: all styling is one `YtmApp.CSS` string keyed on classes of the main screen (`YtmApp.main` = `screen_stack[0]`, so popups don't hide it).
- `apply_layout` picks `apply_vibe(theme_spec, vibe)["layout"]`, or `classic` if `fits()` fails (the dashboard needs `DASH_MIN` = 100x30). It sets one `layout-<name>` class and `tight` (height < 28), updates the `#layout` tooltip, then calls `fit_art`.
- `fit_art` sets `tall` (≥ 100x40: hero art doubles to 40x20) and writes `#art.styles.display` inline. Art shows only at ≥ 70x26 and never in focus. When `tall` flips in hero, `fit_art` resets `_art_id` so the art is fetched again at the new size, and `apply_layout` does the same on a layout change.
- Both run on resize, on theme change and on every tick. The size can arrive a moment after the resize event.
- Colours: `C` is a module-level dict. `get_css_variables` exposes it as `$ytm-*`, and `apply_theme` overwrites it from `theme.colors` before `refresh_css`.

Coupling points the widget refactor has to handle:
1. **Shared ids, one owner.** Every `render_*` method, `tick` and `say` reach panels with `query_one("#…")` from `YtmApp`. `#list` alone is queried in 7 places. `say` writes `#msg` and `#log`, and the workers call it.
2. **`tick` crosses panels.** It drives the player panel (`#motif`, `#eq`, the `#info` width), the dashboard visualizer (`#viz_eq`, `#viz_cap`), layout (`apply_layout`) and the settings reload/footer.
3. **Global colours baked into markup.** `C` is mutated in place, and `Row`, `PlaylistRow`, `HelpScreen`, `keys()` and `render_now` put `C[...]` hex values into markup when they build it. So `apply_theme` has to rebuild the list (`fill_list`) and redraw the footer and player after every theme change.
4. **`_art_id` has two jobs.** It's the art cache key and the "song changed" test in `_apply` (`current_id() != _art_id`). `apply_layout` and `fit_art` reset it to force a refetch.
5. **The effective theme is recomputed everywhere.** `theme.apply_vibe(theme_spec, vibe)` runs in `apply_theme`, `apply_layout`, `tick` and `render_now`.
6. **Bar width depends on art.** `render_now` sizes `#bar` from `#info`'s width, which depends on `#art` being shown. `tick` compares `_bar_width`, and `on_resize`/`fit_art` use `call_after_refresh`.
7. **One state bag.** mpv `state`, `known`, `results`, `view`, `open_playlist`, `theme_spec`, `vibe`, `song_feats`, `layout`, `_played`, `_log` and `_phase` all live on `YtmApp`, and panels read each other's state.
8. **Threads touch app state.** `do_search` assigns `self.results` on its worker thread, and `think` calls `current_id()` (a Player IPC round-trip) from its thread.
9. **Three input paths.** Commands, buttons and keys each call `Player` and the helpers (section 5).
10. **Test contract.** `dev/try.py` replaces `ytm.app.Player`, calls `app._apply`, `app.play_tracks`, `app.lib` and `app.settings`, and clicks `#theme`, `#layout` and `#prompt`. The break scenarios match on-screen text. Keep these names, or update try.py in the same change.

## 9. Test harness

`dev/try.py` renders the real `YtmApp` headlessly with `App.run_test(size=…)`. The scenario format is described at the top of the file. For each scenario, `try.py:run`:

- points `Library.__init__`'s default path, `library.HISTORY` and `Settings.__init__`'s default path at a fresh temp folder, which it deletes afterwards. `"library": "copy"` copies `~/.ytmdev/data/ytm.db` in first.
- replaces `ytm.app.Player` with `FakePlayer`, which has the same methods but plays nothing. It calls `app._apply` synchronously on the UI thread (there's no event thread), and `playlist()` returns fake `watch?v=` URLs.
- replaces `art.fetch` with `fake_art` (a coloured block) and `search.search`/`search.radio` with the scenario's `results`.
- replaces `brain.think` with `fake_think`, which returns the scenario's `feats` plus its theme name. It also sets `brain.enabled = True` and makes `brain._post` raise, so any real Jev or LLM call fails loudly. `brain.budget`, `with_look` and `context` run for real against the temp library.
- runs the `steps`: typed lines, keys, resizes, `mpv` property events, clicks and waits. It then checks `expect`/`absent` against the screen text from `screen_text` (the compositor) and writes `OUT/<name>.txt`, plus `.svg` with `--svg`.

`dev/learn_check.py` checks the learning code (`context.rerank/scores/resume/usual_vibe`, `brain.with_look/measure_next`). It runs on a copy of a data copy in `%TEMP%\ytm-learn`, with `brain._post` stubbed and a fake key.

CI (`.github/workflows/ci.yml`) runs `uv sync --locked`, `compileall`, `ruff check` and every `dev/breaks/*.json`.

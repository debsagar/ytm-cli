# Changelog

All notable changes to this project are documented here. Versions follow [Semantic Versioning](https://semver.org).

## [Unreleased]

### Added
- `layout` opens a layout picker: each layout with its description, the current one marked, ones too big for the window dimmed; moving the highlight previews it, Enter keeps it, Esc puts yours back. ▦ still cycles.
- A small window hides panels instead of squashing them: the visualizer first, then the library, then the player; the prompt never hides. `pin viz` / `unpin viz` (or `set pinned viz library`) keep a panel on a small window and show it in any layout, even classic. Panels come back when the window grows.
- `theme` (or `themes`) opens a theme picker: every theme with a colour swatch, its motif and layout; moving the highlight previews it, Enter keeps it like ◐, Esc puts yours back. `theme <name>` picks one directly and suggests the closest name for a typo.
- Mini mode: F2 (or Ctrl+P) collapses ytm to one line (▶ title · artist, time) over a thin progress bar, plus the prompt, for a small corner window; F2 again brings back the layout, pinned panels and focus as they were. It also shows on its own when the window is too small for the player panel.
- Keys for every control, all usable while typing: Ctrl+↑/↓ volume, Ctrl+L like, Ctrl+R autoplay, Ctrl+T theme picker, Ctrl+G layout picker, F1 help. The help popup and footer list them.

### Changed
- Panels share one quiet border and title colour; only the focused panel takes the theme's accent. The footer keys use the same quiet tone.
- The song info sits centred beside the album art. The dashboard's controls sit right under the progress bar, the focus layout centres them, and the visualizer is drawn at reduced weight.
- Empty list tabs say what fills them, centred (e.g. "no history yet · songs you play show up here").

- Jev also measures each new song's pace, brightness and texture (acoustic ↔ electronic); `brain.motion(f)` hands them to the look and the animation, with guesses for songs measured before.

### Changed
- Grown themes look like they belong with the presets: the theme writer gets a short design system and the song group's pace, brightness and texture, and every theme's colours are nudged to a readable, calm palette (dark bg, text 7:1, accents 3:1, no clashing or neon accent2). Preset colours stay as they were.

### Changed
- Smoother, calmer motion: the equaliser draws thin bars with gaps that ease toward their height (quick up, slow down) at 12 frames a second, swaying slower for slower songs; the motif scrolls by the clock; the blocks progress bar ends in an eighth-block cell and creeps between seconds.
- Less work when nothing moves: the animation timer runs only while a song plays and something animated is on screen, at 1 frame a second with `motion low` or when the terminal is in the background, never with `motion off`. Housekeeping (mpv check, settings reload, layout fit) runs once a second instead of four times. Unchanged text is not redrawn, and the song id is no longer asked of mpv on every update.
- History reads only the end of `history.tsv`; the events table has an index on (type, at).
- Dev: `dev/check.py` runs ruff, a history self-check and every scenario in one line; `try.py` runs scenarios in parallel (5 min → 1 min) and can render PNGs (`--png`, `--open`) and mid-scenario frames (`{"shot": ...}`).

### Fixed
- A search that starts with a command word ("quit playing games", "save your tears", "p diddy") searches instead of running the command.
- `set`: suggests the right key for a wrong one, accepts `key = value`, quotes, lists and any case, and never overwrites a `settings.toml` that has a syntax error. Bad values in the file are reported per key instead of silently ignored.
- Replies stay visible for at least 5 s before an automatic note replaces them.
- ⏮ on the first song restarts it and ⏭ on the last says "end of queue", instead of stopping playback for good.
- Player errors (seeking with nothing loaded, mpv dying) show a message and restart mpv once, instead of crashing the app.
- Resume keeps its point when you quit before pressing play; a paused resume load no longer counts as a play.
- Likes and playlists keep the album; `youtu.be` plays show up in History; replaying the song that just ended counts as a new play.
- One click highlights a list row, a double click plays it. Ctrl+Space pauses in Windows Terminal.
- A layout or colours picked by hand stick for the session. Search in the focus layout switches to classic to show results.
- Song titles and playlist names with `[...]` show correctly (some crashed the app). The footer only offers list keys that work on the current tab; `d` unlikes on the liked tab.
- `vol +10` / `vol -10` are relative; `save` with an empty queue creates nothing; `radio <link>` works; links typed in capitals play.

## [0.5.2] - 2026-10-19

### Added
- One-command install: `irm https://raw.githubusercontent.com/debsagar/ytm-cli/main/install.ps1 | iex` installs missing dependencies with winget, clones ytm into `%LOCALAPPDATA%\ytm`, sets up its packages and adds the `ytm` command. Running it again updates.
- Update channels: `stable` (the `main` branch) and `dev` (latest features). `ytm update dev` switches your copy to dev and `ytm update stable` takes it back, packages included; `ytm update` follows the channel you're on. Data and settings are never touched.

### Fixed
- Resume could pick the wrong song when two events landed in the same millisecond.
- The `vol` hint said 0-130; volume is capped at 100.
- Removed dead and duplicated code; added `docs/flow.md` (how ytm runs) and `docs/decisions.md` (why it is the way it is).

## [0.5.1] - 2026-10-19

### Changed
- Packages are managed with [uv](https://docs.astral.sh/uv/) and pinned in `uv.lock`. Each copy of the code gets its own `.venv`, created on the first `ytm` run and synced by `ytm update`, so updating the installed copy no longer changes a dev checkout. Install uv first; the old `%USERPROFILE%\.venvs\ytm` can be deleted.

## [0.5.0] - 2026-10-19

### Added
- `ytm update`: move your copy to the latest release; data and settings are untouched.
- Songs remember their album (new `album` column, added to existing databases on open); Jev sees it for songs judged from now on. The play position is logged as a `quit` event when the app closes.
- GitHub Actions CI (compile, ruff, break scenarios), CONTRIBUTING.md and issue/PR templates.
- Settings in `%USERPROFILE%\.config\ytm\settings.toml`, picked up live when the file changes; `set` lists them, `set <key> <value>` changes one.
  - `mode` off · jev · yolo; `budget_day` and `budget_month`: LLM work pauses at 80% of a budget, Jev stops at 100%. Songs measured before keep their theme for free.
  - How fast the look changes: `restyle` (every song, every N songs, every N minutes, or pinned), `stickiness` (a new theme must fit clearly better before the look switches) and `can_change` (colours, motif, layout).
  - `motion` (full, low, off), `grow_themes` and `max_new_themes_week` for the LLM.
  - Every change is logged as an event.
  - `llm_model` picks the OpenRouter model that writes themes. Theme calls now turn reasoning off and cap output at 600 tokens, about a third cheaper per theme.
- The help popup scrolls when the window is short.
- `ytm/context.py` builds what the app knows about you (taste, playlists as contexts, skips, time of day, the latest session) from the library, history and events, with no LLM calls, and gives each model a small capped slice of it. New themes are now written with this slice instead of a plain list of artists. `python -m ytm.context` prints the slices. See `docs/context.md`.
- ytm learns you, in code with no LLM (see `docs/context.md`):
  - autoplay and `radio` re-rank YouTube's mix: artists and kinds of songs you skip early move down, songs like your current session (or, for `radio`, like the seed song) move up;
  - the look you settle on after cycling themes is used again for that song and very similar ones;
  - launch resumes a song you left mid-way, paused at its position (press ⏯), and starts in the vibe you usually pick at that time of day;
  - songs known only from history are measured by Jev in the background, one every 30 s while playing, within the budget.
- **dashboard** layout: player and ask (with a short log of recent messages) on top, library and an animated visualizer below. It needs a 100x30 window; smaller windows show classic until there is room.
- ▦ button and `layout` command: `layout` cycles to the next layout (skipping the dashboard when the window is too small), `layout <name>` jumps to one. Logged as an event; a chosen layout stays across songs unless `can_change` includes `layout`.
- Cost tracking: every Jev and LLM call is logged with its tokens and price. The footer shows today's spend, and `cost` breaks it down by today, this month and all time.

### Changed
- The UI is split into bordered panels (now playing, library, ask), each with its own accent from the song's theme; the focused panel's border lights up. Panels lose their gaps when the window is under 28 rows, so everything still fits 74x24.
- The vibe button is gone (▦ took its place); `vibe` cycles calm, normal, loud and `vibe <name>` sets one.
- Hero shows its big 40x20 art from 40 rows up (was 36) so the list keeps a few rows.
- README screenshots now show per-song themes, the four layouts and the settings popup.

## [0.4.0] - 2026-10-19

### Added
- Album art drawn in the terminal with half-block characters.
- Clickable buttons: playback controls, like, volume, autoplay, and actions for the selected song.
- Liked songs (`like`, ♥ button, **liked** tab).
- Playlists: add any song (≡ button or `s`), `save <name>` saves the queue, **playlists** tab to open, play, queue or delete them.
- Add to queue from history, liked songs and playlists.
- Per-song themes: 13 seed themes (colours, scrolling motif, progress-bar style) that restyle the player for each song.
- Four layouts chosen by the theme: classic, hero (big art, spaced title), stage (animated equaliser next to the art) and focus (just the song, centred).
- **◐ theme** button cycles through themes; **vibe** button switches calm (focus layout, no decoration) / normal / loud (stage layout).
- Optional brain: TypeSafe Jev measures each song's energy, mood and context once (cached); code picks the nearest theme. When 3+ songs fit no theme, Claude Haiku (via OpenRouter) writes a new one, up to 24. Disabled when no API keys are set.
- `ytm import <playlist urls> [--judge]` imports public YouTube Music playlists; `--judge` measures every new song up front.
- Play, skip, theme and vibe events are logged locally.

### Changed
- Likes, playlists, song features and themes are stored in SQLite (`data/ytm.db`).
- Pillow is now required (album art).

### Fixed
- mpv no longer keeps running after the app exits, however it exits (a Windows job object kills it with the app).
- Album art stayed hidden after the window was resized bigger.
- A malformed progress-label template in a theme no longer crashes the player.

## [0.3.0] - 2026-10-18

### Added
- Autoplay (on by default): when the queue is almost done, 10 similar songs are added automatically. Toggle with `auto`.

## [0.2.0] - 2026-10-18

### Added
- Mini-player app (`ytm` with no arguments): a compact Textual UI in its own small window.
- Queue: add, remove, clear and jump to songs while music keeps playing.
- Search results, queue and history in one tabbed list.
- Radio mixes via ytmusicapi (50 songs, titles shown immediately).
- Cleaned-up song titles (drops "Official Video", duplicate artist names, etc.).
- Help popup (`?`) and context-sensitive key hints.
- `ytm here` to run the mini-player in the current terminal.

## [0.1.0] - 2026-10-18

### Added
- `ytm <song>`, `ytm radio`, `ytm search`, `ytm <url>`, `ytm stop`.
- Play history (`ytm history`), logged by an mpv Lua script.
- Minimal-RAM setup: audio-only mpv with a small cache; PowerShell exits before playback.

[0.5.2]: https://github.com/debsagar/ytm-cli/compare/v0.5.1...v0.5.2
[0.5.1]: https://github.com/debsagar/ytm-cli/compare/v0.5.0...v0.5.1
[0.5.0]: https://github.com/debsagar/ytm-cli/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/debsagar/ytm-cli/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/debsagar/ytm-cli/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/debsagar/ytm-cli/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/debsagar/ytm-cli/releases/tag/v0.1.0

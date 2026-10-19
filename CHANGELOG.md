# Changelog

All notable changes to this project are documented here. Versions follow [Semantic Versioning](https://semver.org).

## [Unreleased]

### Added
- GitHub Actions CI (compile, ruff, break scenarios), CONTRIBUTING.md and issue/PR templates.
- Settings in `%USERPROFILE%\.config\ytm\settings.toml`, picked up live when the file changes; `set` lists them, `set <key> <value>` changes one.
  - `mode` off · jev · yolo; `budget_day` and `budget_month`: LLM work pauses at 80% of a budget, Jev stops at 100%. Songs measured before keep their theme for free.
  - How fast the look changes: `restyle` (every song, every N songs, every N minutes, or pinned), `stickiness` (a new theme must fit clearly better before the look switches) and `can_change` (colours, motif, layout).
  - `motion` (full, low, off), `grow_themes` and `max_new_themes_week` for the LLM.
  - Every change is logged as an event.
  - `llm_model` picks the OpenRouter model that writes themes. Theme calls now turn reasoning off and cap output at 600 tokens, about a third cheaper per theme.
- The help popup scrolls when the window is short.
- `ytm/context.py` builds what the app knows about you (taste, playlists as contexts, skips, time of day, the latest session) from the library, history and events, with no LLM calls, and gives each model a small capped slice of it. New themes are now written with this slice instead of a plain list of artists. `python -m ytm.context` prints the slices. See `docs/context.md`.
- Cost tracking: every Jev and LLM call is logged with its tokens and price. The footer shows today's spend, and `cost` breaks it down by today, this month and all time.

### Changed
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

[0.4.0]: https://github.com/debsagar/ytm-cli/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/debsagar/ytm-cli/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/debsagar/ytm-cli/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/debsagar/ytm-cli/releases/tag/v0.1.0

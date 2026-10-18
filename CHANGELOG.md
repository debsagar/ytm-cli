# Changelog

All notable changes to this project are documented here. Versions follow [Semantic Versioning](https://semver.org).

## [Unreleased]

### Added
- Album art drawn in the terminal with half-block characters.
- Clickable buttons: playback controls, like, volume, autoplay, and actions for the selected song.
- Liked songs (`like`, ♥ button, **liked** tab).
- Playlists: add any song (≡ button or `s`), `save <name>` saves the queue, **playlists** tab to open, play, queue or delete them.
- Add to queue from history, liked songs and playlists.

### Fixed
- mpv no longer keeps running after the app exits (including when the window is closed).

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

[0.3.0]: https://github.com/debsagar/ytm-cli/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/debsagar/ytm-cli/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/debsagar/ytm-cli/releases/tag/v0.1.0

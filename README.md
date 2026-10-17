# ytm

A minimal-RAM YouTube Music player for the Windows terminal. Search and play songs, start radio mixes, play albums and playlists, and replay from your history: no browser, no login.

Under the hood it is a single audio-only [mpv](https://mpv.io) process fed by [yt-dlp](https://github.com/yt-dlp/yt-dlp). While music plays, mpv uses about 50–60 MB of RAM; yt-dlp runs for a few seconds at each track change and exits.

## Requirements

- Windows 10 or 11
- mpv and yt-dlp (yt-dlp pulls in FFmpeg automatically)
- A JavaScript runtime for yt-dlp: [Deno](https://deno.com) (yt-dlp's default) or Node.js

## Install

1. Install the dependencies:

   ```powershell
   winget install shinchiro.mpv
   winget install yt-dlp.yt-dlp
   winget install DenoLand.Deno   # skip if you already have Node.js
   ```

2. Clone this repo somewhere permanent:

   ```powershell
   git clone https://github.com/debsagar/ytm-cli.git C:\Tools\ytm
   ```

3. Make `ytm` available from any terminal. Either add the clone folder to your `PATH`, or create a one-line forwarder in a folder that is already on it:

   ```powershell
   Set-Content "$env:LOCALAPPDATA\Microsoft\WindowsApps\ytm.cmd" '@"C:\Tools\ytm\ytm.cmd" %*'
   ```

   Use the forwarder if the clone path contains a `;`, since such a folder can't be put on `PATH` reliably.

4. Open a new terminal and run `ytm help`.

ytm finds mpv in `C:\Program Files\MPV Player`, a `bin` folder inside the repo, or on `PATH`, and yt-dlp in the winget links folder, `bin`, or on `PATH`.

## Usage

| Command | What it does |
|---|---|
| `ytm <search terms>` | Play the top YouTube Music song result |
| `ytm radio <search terms>` | Play a mix (up to 100 tracks) seeded from the top result |
| `ytm search <search terms>` | List 10 songs; type a number to play it, or `r<number>` for radio from it |
| `ytm <url>` | Play a YouTube / YT Music track, album or playlist URL |
| `ytm history [count]` | List recently played tracks (default 20); pick one to replay, or `r<number>` for radio |
| `ytm stop` | Stop the player |
| `ytm help` | Show usage |

Any argument starting with `--` is passed straight to mpv:

```powershell
ytm --volume=40 radio daft punk
ytm --shuffle https://music.youtube.com/playlist?list=...
```

Include the artist in searches ("daft punk around the world"); search results only show song titles.

### Keys while playing

| Key | Action |
|---|---|
| `space` | Pause / resume |
| `q` | Quit (prefer this over Ctrl+C, which triggers cmd's "Terminate batch job?" prompt) |
| `n` / `>` | Next track |
| `p` / `<` | Previous track |
| `+` / `0` | Volume up |
| `-` / `9` | Volume down |
| `m` | Mute |
| `→` / `←` | Seek 5 s |
| `↑` / `↓` | Seek 1 min |
| `s` | Toggle shuffle |

## History

Every track that starts playing, including each song in a radio mix, is logged to `mpv\history.tsv` as time, URL and "Artist - Title". `ytm history` reads it back. Delete the file to clear your history; it is excluded from git.

## How it works

- `ytm.cmd` runs `ytm.ps1`, which resolves your search or URL (via yt-dlp's YouTube Music search) and exits. `ytm.cmd` then starts mpv, so no PowerShell process stays in memory while music plays.
- `mpv\mpv.conf` holds the player settings: audio only, a 24 MiB cache, no window. It is loaded with `--config-dir`, so your own mpv config is not read or changed.
- `mpv\input.conf` adds the extra key bindings, and `mpv\scripts\history.lua` writes the history log.

## Limitations

- No account access: liked songs, private playlists and age-restricted tracks won't play.
- Radio is capped at 100 tracks; uncapped mixes are ~700 entries and take about 20 s to start.
- A pasted `watch?v=...&list=...` link plays only that one track; pure playlist and album URLs play in full.
- Expect a few seconds' delay before the first track starts while yt-dlp resolves the stream.

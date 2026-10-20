# Decisions

This is a log of the design decisions behind ytm: what was decided, by whom, and why. Read it before proposing a change, so you don't undo something on purpose or repeat an idea that was already tried and dropped.

## How to add an entry

- Add one row to the table for its area. Use the next free ID and never reuse one.
- **Date**: the day it was decided (YYYY-MM-DD).
- **Who**:
  - **human**: the user asked for it or chose it.
  - **model**: an agent decided it, and the user didn't object or later accepted it.
  - When the user asked for an outcome and the agent picked the mechanism, log the mechanism as `model` and cite the human row it serves (for example "serves D12").
- **Decision** and **Why**: one line each. Quote the user's own words when they were decisive.
- **Status**:
  - `active`;
  - `proposed` (awaiting the user's yes);
  - `REVERSED → Dxx` (the decision was undone; Dxx says what replaced it);
  - `superseded → Dxx` (still roughly true, but Dxx refined or replaced it).
- Never delete a row. To reverse a decision, edit its status and add a new row that says what replaced it. Reversed rows are the most useful ones.
- Keep secrets out: no keys, tokens or personal data, only the decision.

Sources: git history, CHANGELOG, README, `dev/README.md`, `docs/context.md`, the agents' memory notes and the session transcripts (user messages only), up to 2026-10-19.

---

## Vision and principles

| ID | Date | Who | Decision | Why | Status |
|---|---|---|---|---|---|
| D01 | 2026-10-02 | human | Build a minimal-RAM YouTube Music player for the terminal | The machine was short on RAM ("i need yt music … with minimal ram usage") | active |
| D02 | 2026-10-17 | human | No login required | Keep it lightweight and frictionless ("make a lightweight app for ytm, no login required") | active |
| D03 | 2026-10-18 | human | Make it a serious open-source repo (playlists, queue, cool CLI graphics) | "turn this project into a serious opensource repo where we can add features" | active |
| D04 | 2026-10-18 | human | "Semi automatic": Claude writes the code and explains every step and decision | The user wants to learn, not just receive code ("I will only understand the steps not do it myself") | active |
| D05 | 2026-10-19 | human | RAM budget of 400 MB in total; personalisation is fine within it | "as long as it stays within 400 mb" | active |
| D06 | 2026-10-19 | model | Stay in Python + Textual; reject a Rust port | Measured about 118 MB (64 MB app + 54 MB mpv). Rust would save only 40–50 MB and lose ytmusicapi/yt-dlp and dynamism | active |
| D07 | 2026-10-19 | human | Spaces → widgets → customisation: the terminal splits into spaces, each space holds a widget, each widget is customisable | "the terminal is split into spaces, these spaces can be occupied by widgets, each widget itself can be customised" | active |
| D08 | 2026-10-19 | human | Timescales: code handles every instant thing, Jev runs once per song (cached), the LLM runs rarely, and the UI never waits on an LLM | "for heavy duty tasks we rely on llms but the dynamic ui part should be very frequent"; "not everything should pass through the llm, that wont feel dynamic and instant" | active |
| D09 | 2026-10-19 | human | Context engineering is a first-class concern | "Context engineering is also an important thing here" | active (see D33) |
| D10 | 2026-10-19 | human | Each user keeps 2–3 very personal layouts, rather than many generic ones | "a user would probably stick to 2 3 and make those very custom and personal" | active |
| D11 | 2026-10-19 | model | A layout is a split tree that survives resizes; widgets come from a closed registry and are customised by data | Inspired by kew, zellij and btop (awesome-tuis research); resize-safe | superseded → D66 (text maps, proposed) |
| D12 | 2026-10-19 | human | Stay minimal everywhere: as a proof of concept, but with real capabilities | "keep it simple and minimal like a poc but should still have some seriously cool capabilities"; "all while being minimal" | active |

## Brain, LLM and cost

| ID | Date | Who | Decision | Why | Status |
|---|---|---|---|---|---|
| D13 | 2026-10-19 | human | Per-song UI themes (for example, an F1 song gets a motorsport look) | The user's idea for a UI that is "on demand … sort of emergent" | active |
| D14 | 2026-10-19 | human | Use TypeSafe Jev as the cheap judging layer instead of an LLM for every change | "LLM for every patch is expensive. But typesafes jev is very cheap" | active |
| D15 | 2026-10-19 | model | Jev measures each song once (energy, mood, tags) and caches it; code picks the nearest theme centre; k-means refines the centres | Jev can only choose and can't invent, so the choosing goes to Jev and the inventing to the LLM | active |
| D16 | 2026-10-19 | model | The LLM (Claude Haiku via OpenRouter) writes a new theme only when 3 or more songs fit no theme; at most 24 themes | The LLM is used rarely and only for invention (D08) | active |
| D17 | 2026-10-19 | human | Three modes, off · jev · yolo, so that tokens aren't burned "for no reason" | "there should be a jev mode no jev mode so that we dont burn tokens for no reason"; yolo is where "the llm generates new widgets on layouts" | active |
| D18 | 2026-10-19 | model | Yolo produces data only (sprites, effect params, layouts, widget specs), never code | Safe, cheap to render, and reviewable | active |
| D19 | 2026-10-19 | human | Show a cost counter in the CLI | "we need to add a cost count to the cli" | active |
| D20 | 2026-10-19 | model | Log every Jev and LLM call with tokens and price; show today's spend in the footer; `cost` gives the breakdown | Serves D19 | active |
| D21 | 2026-10-19 | human | The user sets how often the UI changes and how often the LLM rewrites rules | "a user doesnt want the ui to change after every song, he wants to set how often llm rewrites rules" | active |
| D22 | 2026-10-19 | model | Budget settings `budget_day` / `budget_month`: LLM work pauses at 80% of a budget, Jev stops at 100%, and cached songs keep their themes for free | Spend degrades gracefully and the cheap layer keeps working longest. Serves D17, D21 | active |
| D23 | 2026-10-19 | model | `restyle` (song / every N / N min / pinned), `stickiness` (hysteresis, default 0.5 ≈ a change every ~3 songs), `can_change`, `motion` | Serves D21. STICKY was recalibrated to 1.0 from measured gains | active |
| D24 | 2026-10-19 | model | Settings live in `~/.config/ytm/settings.toml`, reload live on file change, and every change is logged as an event | Editable by hand or with `set`; the logged events double as taste data | active |
| D25 | 2026-10-19 | human | Look for a cheaper in-app LLM | "do you think we can get away with a cheaper model? … our haiku agent in the tui" | active |
| D26 | 2026-10-19 | model | Keep Haiku, but turn reasoning off and cap output at 600 tokens; make the model configurable with `llm_model` | Output fell from 599 to 185 tokens (about 55% cheaper) with no quality loss seen. Serves D25 | active |
| D27 | 2026-10-19 | model | Jev stays user-independent: it measures the song, not the listener | Song features are cacheable and shareable; the personal layer is the context builder | active |
| D28 | 2026-10-19 | model | Learn the listener in code, with no LLM: skip-aware radio re-ranking, remembered looks, resume, the usual vibe for the time of day | Follows D08; personalisation costs nothing at runtime | active |
| D29 | 2026-10-19 | human | Seed the user's history from their YouTube Music playlists (`ytm import`) | "so that the statemachine already has some history to get a profile summary" | active |
| D86 | 2026-10-20 | model | Jev also scores pace, bright and texture (three 0..1 scores, criteria a few words each) in the same request. They feed the look and the motion only (`brain.motion(f)`), never `vec()`, so cached centres and grown themes keep their dimensions; songs cached before them get guesses from energy, moods and the club tag and are never re-judged. Vocals and era were left out: nothing would read them yet, and era overlaps the nostalgic mood | "Create deeper but concise schemas for jev." Pace drives animation speed, bright the palette's warmth, texture earthy vs neon. Estimated ~620 → ~900 input tokens, $0.000026 → ~$0.000038 per song (offline estimate from 84 real calls, no paid call) | active |
| D87 | 2026-10-20 | model | A short design system in the theme-writer prompt (near-black bg and panel tinted by the accent, ONE vivid accent, a calmer analogous or split-complementary accent2, measured bright/texture/pace steer the palette), and `theme.readable()` in `normalize()` enforces it by nudging, never rejecting: bg luminance <= 0.02, panel within 28 RGB of bg, text >= 7:1, accents and dim >= 3:1, dim clearly darker than text, accent lightness >= 0.55, an accent2 hue 62–118° from accent snaps to 60/120°, accent2 chroma <= accent's + 0.2. Presets are fixed points (two accent2 values moved a few degrees to be) | "The designs are creative but don't merge together. We have to work on the prompt." Rules apply to every theme, including grown ones already saved | active |

## Data and privacy

| ID | Date | Who | Decision | Why | Status |
|---|---|---|---|---|---|
| D30 | 2026-10-18 | human | Keep a play history (an mpv Lua script writes `history.tsv`) | "just add history maybe? how much ram will that consume?" | active |
| D31 | 2026-10-19 | model | Store likes, playlists, song features, themes and events in SQLite (`data/ytm.db`) | One small local store with no server | active |
| D32 | 2026-10-19 | human | Never push tokens; API keys live only in `%USERPROFILE%\.config\ytm\secrets.env`, outside the repo | "dont push tokens" | active |
| D33 | 2026-10-19 | model | One context builder (`ytm/context.py`) builds the state of what ytm knows from the library, history and events, with no LLM, and hands each consumer a small capped slice (jev 200, theme 900, widget 1000, profile 3200 chars) | Serves D09: never dump raw history into a model | active |
| D34 | 2026-10-19 | model | Back up `history.tsv` / `ytm.db` and dry-run any filter before touching user data; tests use scratch copies | A cleanup with an empty pattern deleted a day of real plays, which could not be recovered | active |
| D35 | 2026-10-19 | model | The data location is movable (`YTM_HOME` or a git-ignored `ytm.home` file) | Lets ytm and ytmdev point at different data (D41) | active |
| D36 | 2026-10-19 | model | Store the album on tracks (an additive migration) and log the play position on quit | Better Jev input; resume needs the position | active |
| D37 | 2026-10-19 | model | Moving the real data to `%LOCALAPPDATA%\ytm` is deferred | Needs a backup and a verified copy first (D34); the real data still lives in the dev repo folder, so never run `git clean -x` there | active (deferred) |

## Install and updates

| ID | Date | Who | Decision | Why | Status |
|---|---|---|---|---|---|
| D38 | 2026-10-02 | model | Audio-only mpv with a small cache, yt-dlp, and PowerShell exiting before playback | The lowest-RAM way to play | active |
| D39 | 2026-10-18 | model | The Python venv lives outside the repo (`%USERPROFILE%\.venvs\ytm`) | `venv` refuses paths containing `;` (`G:\Projects\ho;jf`) | REVERSED → D45 |
| D40 | 2026-10-18 | human | Kill mpv when the app exits, however it exits | "after quitting the mpv process is still running fix it"; fixed with a Windows job object | active |
| D41 | 2026-10-19 | human | Split `ytm` (the stable copy on the real data) from `ytmdev` (the dev checkout on a copy of the data) | "we will make a separate freeze called ytmdev then?" | active |
| D42 | 2026-10-19 | model | `ytm` runs from a pinned worktree, `G:\Projects\ytm-stable`, which is updated with `git fetch` + `checkout --detach origin/main` | Freezes the stable copy without a second clone | REVERSED → D44 |
| D43 | 2026-10-19 | human | Add a `ytm update` command | "can we add a ytm update command? will it fuck without my development?" | active |
| D44 | 2026-10-19 | human | `ytm` is a normal clean install (a clone of `main`, e.g. `C:\Tools\ytm`) updated with `ytm update`; the ytm-stable worktree is dropped and must not be recreated | "too complicated i would rather do clean install man" | active |
| D45 | 2026-10-19 | human | Manage packages with uv | "we should probably use uv for this" | active |
| D46 | 2026-10-19 | model | One `.venv` per copy of the code, created on the first run; `ytm update` runs `uv sync --frozen --no-dev`; packages are pinned in `uv.lock` | Updating the install no longer changes the dev checkout. Serves D45 | active |
| D47 | 2026-10-19 | model | `ytm.cmd` hands `update` off to Python on a single line | cmd re-reads a `.cmd` file as it runs it; after the bug where `ytm update` searched for and played a song called "UPDAT" | active |
| D48 | 2026-10-19 | human | Make installing easy: no manual PowerShell setup commands | "currently it requires the user to do set commands in powershell which is too much" | active |
| D49 | 2026-10-19 | model | A one-command `install.ps1` (`irm … \| iex`): winget for the missing dependencies, a clone into `%LOCALAPPDATA%\ytm`, the `ytm` command added; rerunning it updates | Serves D48 | active |

## UI, layout and widgets

| ID | Date | Who | Decision | Why | Status |
|---|---|---|---|---|---|
| D50 | 2026-10-18 | model | A Textual TUI driving mpv over JSON IPC | Gives a real interactive app (queue, history) in the terminal; the user wanted it "like a claude code cli … without the llm" | active |
| D51 | 2026-10-18 | human | A small mini-player in its own small window, not full screen | "too overstimulating the screen is too big cant it just be smaller window?" | active |
| D52 | 2026-10-18 | human | A fixed colour palette with distinct sections and clear, uncluttered key hints | "colorless, no distinction between the different sections, the instructions are too unclear and cluttered" | active |
| D53 | 2026-10-18 | human | Autoplay: top up the queue with similar songs | "add a mode for it to auto add songs even if i dont add it" | active |
| D54 | 2026-10-18 | human | Graphics that use the least RAM, plus clickable buttons in the terminal | "can we add graphics … whatever takes the least ram … Can it not have more buttons in the terminal itself?"; album art is drawn with half-blocks | active |
| D55 | 2026-10-19 | model | Themes change the layout (classic, hero, stage, focus), not just the colours | More visible per-song change for no runtime cost | active |
| D56 | 2026-10-19 | model | Dashboard prototype (`dev/proto.py`, `ytmdev proto`): a from-scratch rewrite of the UI | A quick look at the dashboard idea | REVERSED → D57 |
| D57 | 2026-10-19 | human | Delete the prototype; never prototype by rewriting, always build on the real app | "just delete it and remember that it was a pretty bad prototype": it lost autoplay, auto themes, playlist contents and the queue view, and looked blocky | active |
| D58 | 2026-10-19 | human | Panels with visible or implied borders, each with its own accent colour, like github.com/Cvaniak/PixelArtTUI; the "borderless colour-block" advice was rejected | "i want boundaries around them either visible or implied"; "look at how this art is and how bifurcated it feels" | active |
| D59 | 2026-10-19 | human | Keep the layout controls minimal | "i want the controls to change the layout still minimal, do not put too many args and buttons please" | active |
| D60 | 2026-10-19 | model | One ▦ button plus `layout [name]`; the vibe button is removed and `vibe` becomes a command | Serves D59: one button does it | active |
| D61 | 2026-10-19 | model | A dashboard layout that needs 100×30; smaller windows show classic until there is room | Never garble a small window | active |
| D62 | 2026-10-19 | model | Everything must fit 74×24; panels lose their gaps under 28 rows | The smallest target window | active |
| D63 | 2026-10-19 | human | A playground: a large board that simulates the terminal, where widgets are placed, combined and previewed | "a separate interface to show all widgets separately, like a large blackboard … like a playground, this is for later" | active (later) |
| D64 | 2026-10-19 | model | Playground shape v1: a separate `ytm playground` app, tmux-style splits with draggable dividers, a window-size slider, saving to a layout file | First proposal for D63 | superseded → D66 |
| D65 | 2026-10-19 | model | Build order: widgets as pieces → layouts as text maps → playground → extra widgets and a braille visualizer → yolo widgets | Each step builds on the one before | proposed |
| D66 | 2026-10-19 | model | Layouts as text maps (`map = """…"""`, `.` = empty) converted into a Textual grid (`grid-size` + spans); user layouts in `~/.config/ytm/layouts/`; the playground built inside the app as `layout edit`, keyboard first, previewing at 74×24 and full size | Simpler than a split tree; text is diffable and easy for an LLM to write. Note: an earlier claim that Textual has `grid-template-areas` was false (it has none); see Priors | proposed |
| D67 | 2026-10-19 | model | Visualizer: braille instead of block bars | The user dislikes blockiness (D58) | proposed |
| D84 | 2026-10-20 | model | A small window hides whole panels in a fixed order (viz, then library, then player; the prompt never), and `pin <panel>` / the `pinned` setting keeps chosen ones, in any layout. Display only, never a remount; the dashboard still falls back to classic below 100x30 | The user asked to "pin the widgets that are important, or that the user sets" when resizing; hiding beats squashing every panel to a sliver (D61, D62), and pinning a panel into a layout that omits it was one CSS display toggle, so it's in | active |

## Testing

| ID | Date | Who | Decision | Why | Status |
|---|---|---|---|---|---|
| D68 | 2026-10-19 | human | No hard-coded test lists and no rerunning the same tasks; testing is an agentic loop | "please dont hardcode anything, needs to be like a pipeline or agentic system, dont test on same tasks again and again" | active |
| D69 | 2026-10-19 | human | Keep it simple: think only in counterexamples | "dont go overkill … think only in terms of counterexamples to gain the most information of where the edge cases and where we can break" | active |
| D70 | 2026-10-19 | model | `dev/try.py` renders the real UI with a fake player (no mpv, no network, no spend); only the scenarios that broke something are kept, in `dev/breaks/`, and replayed in CI | Serves D68 and D69 | active |
| D71 | 2026-10-19 | model | Before showing the user anything, exercise the real flows (autoplay, themes, playlists, queue), not just the happy path | A lesson from D56 | active |

## Dev process and repo

| ID | Date | Who | Decision | Why | Status |
|---|---|---|---|---|---|
| D72 | 2026-10-18 | human | Version and release on GitHub (semver, CHANGELOG, MIT) | "push to github versioning and all please" | active |
| D73 | 2026-10-19 | human | Follow proper open-source practice | "please follow proper development principles for maintaining this as a opensource repo" | active |
| D74 | 2026-10-19 | model | CI on GitHub Actions (compile, ruff, breaks), CONTRIBUTING, issue and PR templates; feature branches → `dev` → `main` with `--no-ff`, tagged releases | Serves D73 | active |
| D75 | 2026-10-19 | human | The user merges to `main` themselves | "make sure all checks are done and i will merge it myself" | superseded → D76 |
| D76 | 2026-10-19 | human | Claude may do the release itself (bump, CHANGELOG, merge, tag, push) | "do whatevers required" | active |
| D77 | 2026-10-19 | human | Ponytail mode: the smallest complete change | The user installed it and asked to use it ("install the ponytail skill and use that to code it up") | active |
| D78 | 2026-10-19 | human | One Opus implementer agent writes the code; Claude is the discusser and verifier and checks everything independently | "just launch a single opus 55 agent to fix it, you have to be my discusser and verifier" | active |
| D79 | 2026-10-19 | human | Parallelise independent work, each piece in its own worktree, and prune the worktrees afterwards | "you dont have to be so slow when you can parallise work fast"; "use worktrees and prune them when work is done" | active |
| D80 | 2026-10-19 | human | Show UI progress quickly with screenshots opened on the user's screen | "I WANT TO SEE TUI UPDATES MAN"; "i dont see the picture in the ss you sent" | active |
| D81 | 2026-10-19 | model | Use cheaper models for chores (Sonnet, Haiku) and Opus for design-heavy work | Cost | active |
| D82 | 2026-10-19 | human | Keep a decisions log (this file) and a flow-of-execution doc (`docs/flow.md`), check the plan's priors, and clean up redundant code | Asked for alongside the playground build order | active |
| D83 | 2026-10-19 | human | `main` is stable and `dev` gets new features first; `ytm update dev` switches a copy to dev, `ytm update stable` goes back | "Add one option to go back to a stable release. Mark main as stable." The user runs dev on the real install and needs a way back if it breaks | active |
| D85 | 2026-10-20 | human | `theme` opens a picker like `layout`'s: one shared `Picker` popup, centred, rows with a colour swatch and motif, live preview, Enter is a manual pick, Esc goes back. Automatic restyles while it is open are held, so they neither clobber the preview nor leave Esc on a stale theme. Rows are cut at a word with … | "when i type layout or themes i should be able to have a list which i can pick from"; the first screenshot was off-centre and cut descriptions mid-word | active |
| D88 | 2026-10-20 | human | One quiet border and title tone for every panel, the accent only on the focused one; a mini mode (F2 / Ctrl+P) that collapses to one song line, a thin bar and the prompt, automatic when the player panel doesn't fit; a global key for every control (Ctrl+↑↓ volume, Ctrl+L like, Ctrl+R autoplay, Ctrl+T / Ctrl+G pickers, F1 help) | "The designs are creative but don't merge together", "it should be minimalist", "a keybind to pop the miniplayer". Keys are Ctrl/F-keys so typing a song name never triggers them; each was checked against Textual's parser and Windows Terminal's defaults (no Ctrl+M, Ctrl+Shift, Alt+Enter). Mini mode only hides panels, so leaving it restores the layout, pins and focus | active |
| D89 | 2026-10-20 | human | Two clocks: housekeeping once a second (plus 0.3 s after a resize), and an animation timer at 12 fps that runs only while playing with something animated on screen (1 fps for `motion low` or a blurred terminal, none for `off`). Motion moves by elapsed time, not frame count; the equaliser eases each bar; animation frames skip the layout pass and identical text. A blurred terminal drops to 1 fps rather than stopping, since it is often still visible | "Minimalist with better animations, faster ticks, smoother … make it resource efficient." Measured headless at 190x50: 3x the frame rate for ~1.4x the CPU in stage, and far less with motion off or nothing animated | active |
| D90 | 2026-10-20 | human | Pixel art in half blocks (`ytm/pixel.py`), coloured only from the theme's six colours: the equaliser (bars, gradient, eased rise, gravity fall, caps that stay near their bar); a mood scene in `#art` whenever there's no cover (sun, moon or campfire by energy, mood, club tag and texture; seeded by the video id; built once per song, size and palette, redrawn at most 4 times a second); a cassette (a vinyl for the vinyl motif) beside the popped mini line on windows ≥ 8 rows, turning 1–4 steps a second by pace. Foreground-only styles and one colour per cell row keep the span count low, since spans are what Textual pays for per redraw | "Put these three pixel pieces into ytm", picked from prototypes; the UI is minimal, so the motion stays slow. Measured headless at 190x50 in neon rave, Mcycles/s before → after: stage 117 → ~177, dashboard 221 → ~318, classic 43 → ~110 (51 with a real cover), popped mini 33 → ~59 | active |

---

## Priors: what the next plan assumes, checked

This section checks the assumptions behind the plan in D65 and D66 against the installed code: Textual 8.2.8 in `G:\Projects\ho;jf\.venv`, and `ytm/app.py` at `36521c2`. "Script" means a throwaway headless `run_test()` script; no app or mpv was launched. Verdicts are TRUE, FALSE or PARTLY.

**Step 1: widgets as pieces**

| # | We assumed | Verdict | Evidence | What it changes |
|---|---|---|---|---|
| P1 | The panels can be moved out of `app.py` mostly as-is | PARTLY | Moving the classes is safe: App-level `query_one("#title")` always searches the default screen (`textual/app.py:941`), so the ids keep resolving wherever the class lives. But the panels don't own their behaviour. `tick` (`app.py:657`) drives both the player (`#info`, `#motif`, `#eq`) and the visualizer (`#viz_eq`, `#viz_cap`). `render_now` writes 6 player ids. `fit_art` toggles a `tall` class on the Screen and `#art`'s display. The state they read (`layout`, `_bar_width`, `_art_id`, `song_feats`, `state`) lives on the app, and the colours live in the module-global `C` (15 uses). `app.py` makes 38 `query_one` calls in all | Move `compose` + CSS per panel first, keep every id, and keep the update logic in the app. Moving the update methods into the panels is a second, separate move. `try.py dev/breaks/*.json` must pass after each move |
| P2 | The 5 layouts are about panel placement, so a map can express each one | FALSE | Of the 26 `Screen.layout-*` rules (`app.py:242-274`), about 10 place or size panels. About 16 restyle a panel's inside: stage shows `#eq`, hero has double-size art and a spaced title, focus hides the art and centres the text, and the dashboard has 2-row controls, the log shown and the motif hidden. Classic, hero and stage have the same placement | A layout file needs the map **plus a look for each panel** (e.g. `player = "hero"`, applied as a class on the panel). Keep those ~16 rules as panel-class CSS. Without this, hero, stage and focus can't be written as maps |
| P3 | Refactoring costs negligible RAM | TRUE | Script: an extra `Container` costs about 27 KB of Python heap (tracemalloc, 50 containers). The refactor removes 3 wrappers (`#body`, `#left`, `#right`) and adds a few spacers, against 118 MB measured (D06) | None |

**Step 2: layouts as text maps**

| # | We assumed | Verdict | Evidence | What it changes |
|---|---|---|---|---|
| P4 | Textual has `grid-template-areas` | FALSE (caught earlier) | No match for `template-areas` anywhere in `textual/`; only `grid-size`, `grid-rows`/`grid-columns` and `column-span`/`row-span` (`css/styles.py:448-461`) | The map is converted to spans |
| P5 | Grid auto-placement fills the next free cell in reading order, so listing the map's rectangles by top-left cell in reading order reproduces the map | TRUE | `layouts/grid.py:155-181`: a forward-only scan from (0,0) that skips occupied cells. Script: the 3×3 map `art now now / art viz viz / list list ask` (art spans 2 rows) was placed exactly, at 90×30 and in a 74×24 box | The converter emits panels in that order and sets their spans |
| P6 | `.` cells can simply be left out | FALSE | Script: in the map `art now / . now / list ask` without a filler, `list` slid into the empty cell at (0,10) and `ask` dropped a row. With an empty `Static` in place of `.`, the placement was exact | Emit one empty spacer widget per `.` rectangle |
| P7 | The grid's row count follows the map | PARTLY | If `grid-size` sets only the columns, the rows default to the last placed row + 1 (`grid.py:184`), so trailing `.` rows vanish. Script: `a b / c c / . .` gave 2 rows | Always set both `grid-size` values |
| P8 | Panels fill their cells | PARTLY | The grid sizes cells but doesn't stretch children: a `Static` (height auto) took 1 row of a 10-row cell until it was given `height: 100%`. `Vertical` defaults to `height: 1fr` (`containers.py:127`), but the app overrides it (`#right` auto; dashboard `#player`/`#ask` fixed) | Grid-mode CSS sets the panels to `height: 1fr` and drops the per-layout heights |
| P9 | Rows and columns can be sized per layout with fr/auto, and the player can get a fixed height | PARTLY | Script: `grid-rows: 7 1fr` puts row 2 at y=7, and `auto 1fr` sizes row 1 to its content. **But auto rows ignore widgets that span more than one row** (`grid.py:296`; script: row 1 came out 1 tall next to a 4-tall spanning player). Scalars repeat when there are fewer than rows (`repeat_scalars`) | Allow `rows = "auto 1fr"`-style sizing in the layout file. A fixed-height panel (the player) must not row-span an `auto` row: give that row a number, or reject the map with a message |
| P10 | Textual reports bad maps | FALSE | The grid never raises: the spans are rectangles and the scan just skips occupied cells (`grid.py:165-180`) | All validation is ours: ragged rows, non-rectangular or split names, unknown panel names, panel used twice, no player |
| P11 | Layouts can be swapped at runtime without remounting, keeping state | TRUE, with conditions | Script, on live widgets: `move_child` + new spans + new `grid-size`/`grid-rows` kept the ListView index (7), the Input text and the focus, and the objects were the same. A remount reset the ListView index to 0. Mounting an already-mounted widget into another parent **silently does nothing** (it stayed in its old parent). Hidden (`display: none`) children take no cells (`_arrange.py:61`) | All panels must be direct children of one grid container. Reorder them with `move_child` (the placement follows DOM order). Hide panels a map doesn't use instead of removing them. Never move a panel between containers |
| P12 | Too-small windows can fall back to classic | TRUE | The pattern already exists: `fits()` / `DASH_MIN` (`app.py:40, 520-522`), but only for the dashboard | Each map needs a minimum size (derived, or a `min = "100x30"` key) |
| P13 | User layouts live in `~/.config/ytm/layouts/` as TOML | TRUE | Same root as the settings (`settings.py:13`); `tomllib` is already used (`settings.py:10`) | None |

**Step 3: the `layout edit` playground**

| # | We assumed | Verdict | Evidence | What it changes |
|---|---|---|---|---|
| P14 | A 74×24 preview can be drawn inside a bigger screen | PARTLY | Script: a fixed 74×24 grid container inside a 90×30 screen laid out the map correctly (art 24×16, now 50×8 …). But the app's size rules read the **window**: `tight` (<28 rows, `app.py:534`), art `roomy` (`:455`), `tall` (`:456`), `fits` (`:522`), footer (`:788`), and the layout classes go on the Screen, not the panel. Also, App-level `query_one` searches only the default screen (`textual/app.py:941`), so the app's render methods never update panel copies on an editor screen | A preview shows the right **geometry** but not the right **looks** at 74×24. Either preview with labelled placeholder boxes (cheapest), or make the size rules read the panel's own container size and let panels draw from passed-in state (`draw(state, theme)`) |
| P15 | Clicks work in Windows Terminal | TRUE | The driver enables SGR mouse reporting (`drivers/windows_driver.py:61-64`) with VT input (`drivers/win32.py:179`); the buttons have been clickable since 0.4.0 | None |
| P16 | Drag works (MouseDown/Move/Up + `capture_mouse`) | PARTLY | The driver enables any-motion tracking (`?1003h`). Script: after `capture_mouse`, `MouseMove` events with `button=1` arrived even outside the widget, then the up. **Not tested in a real Windows Terminal** | Keep drag for "later", as planned; check it in the real terminal first |
| P17 | The editor keys work (Shift+arrows, Delete, `+`, `s`) | PARTLY | Textual parses Shift+Up (`_ansi_sequences.py:234`) and Delete (`:71`). The app binds arrows, `s`, `a`, `l`, `d` and `delete` (`app.py:314-329`, not priority), but a pushed screen's bindings are checked before the app's, so the editor's win. The `ctrl+` priority bindings still control playback | Define the editor keys on its Screen. Whether Windows Terminal sends Shift+arrows unchanged was not tested live |

**Step 4: the braille visualizer**

| # | We assumed | Verdict | Evidence | What it changes |
|---|---|---|---|---|
| P18 | Braille renders one cell wide in Windows Terminal with the default font | TRUE (as far as checkable) | Rich `cell_len` = 1 for all of U+2800–28FF (script). The user's WT settings set no font, so WT uses its default, Cascadia Mono, which has all 256 braille glyphs at the same advance as `M` (Pillow glyph check; Cascadia Code too). Consolas has none of them | Fine with the default font; users on Consolas get fallback glyphs. Not checked visually in WT |

**Step 5: yolo widgets.** This step assumes only D18 (the LLM writes a spec, a renderer draws it). It has no technical prior to check yet. The spec format should reuse the layout map and panel looks from P2, so one validator covers both.

### What changes in the plan

1. A layout is a map **plus a look per panel** (P2). Without the looks, maps can't express hero, stage or focus.
2. The converter adds a spacer for each `.` (P6), sets both grid dimensions (P7), gives panels `height: 1fr` (P8), and does all the validation itself (P10).
3. Swap layouts by reordering and hiding the children of one flat grid container. Never remount (P11).
4. Move the code in step 1 in two passes: first the compose and CSS per panel, then the update logic (P1).
5. For now, the 74×24 preview shows geometry only (placeholder boxes), unless the size rules move from the window to each panel (P14).

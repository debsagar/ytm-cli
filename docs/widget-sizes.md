# Widget sizes: how small, how many

Measured by rendering, not guessed: `uv run python dev/gallery.py --measure` draws each widget alone in a
terminal of its comfortable size, shrinks the height until it stops "working", then the width. "Working"
means the text a user needs is on screen (`CHECKS` in `dev/gallery.py`); for buttons, every glyph is drawn,
so every button is clickable. All sizes include the widget's border (2 cells each way) and padding (1 cell
each side), so a box costs **4 columns and 2 rows** before any content.

The `app #...` rows are the real app's panels (dev/try.py's fake player, other panels hidden). The others are
gallery widgets built from the real renderers; **mock** ones don't exist in ytm yet.

## Min and comfortable size per widget (cols × rows)

| widget | min | comfortable | what decides the minimum |
|---|---|---|---|
| app #player | 38×7 | 74×12 | the 9 control buttons in one row |
| app #library | 51×7 | 74×12 | the tab row + the action row, 3 songs |
| app #ask | 17×4 | 74×4 | message line + a readable prompt |
| now playing (motif, title, artist, bar, controls) | 38×7 | 50×8 | the controls row |
| mini player (title + bar) | 21×4 | 40×4 | "1:23 / 4:03" plus a few cells of bar |
| controls, one row | 38×3 | 40×3 | 9 buttons, 3 cells + 1 gap each |
| controls, two rows | 26×4 | 28×4 | 6 buttons on the first row |
| list | 17×5 | 50×12 | 3 rows, start of each title |
| library (tabs, actions, list) | 44×7 | 56×14 | the tab row |
| prompt | 17×4 | 50×4 | "search a song" readable |
| visualiser (bars + caption) | 25×4 | 30×8 | the caption ("theme · mood") |
| art | 10×5 | 22×12 | a 6×3-cell thumbnail |
| clock (mock) | 17×7 | 24×7 | 3-row digits "1:23" + bar + title |
| stats (mock) | 19×4 | 26×6 | "1h 12m listened" |
| up next (mock) | 15×5 | 30×7 | 3 titles, truncated |
| lyrics (mock) | 25×5 | 40×8 | 3 lines, readable |
| mood gauge (mock) | 18×5 | 26×5 | 2 bars of 3+ cells and the mood line |
| motif | 9×3 | 20×3 | one row of the pattern |

Minimums shift by a cell or two between themes, because the progress bar's label and cursor are themed
(in `09-min-vs-comfy`, the velvet theme cuts the mini player's "4:03" at 21 columns).

## How many fit

`uv run python dev/gallery.py --count`. The 12 small widgets (mini, controls (2 rows), list, prompt, clock,
up next, stats, visualiser, art, lyrics, mood, motif) are packed in that priority order, round after
round, into the terminal minus one row for the footer. "Distinct" means how many of the 12 fit once each.
Borders are counted. The packing is greedy (skyline, highest-then-leftmost), so these are lower bounds,
and not always monotonic: a slightly larger widget can pack better.

| terminal | at min: total | at min: distinct | comfortable: total | comfortable: distinct |
|---|---|---|---|---|
| 60×18 | 13 | 9/12 | 5 | 5/12 |
| 74×24 (the usual window) | 19 | 12/12 | 8 | 7/12 |
| 100×30 (`DASH_MIN`) | 33 | 12/12 | 13 | 10/12 |
| 140×40 | 58 | 12/12 | 25 | 12/12 |
| 200×55 | 116 | 12/12 | 47 | 12/12 |
| **190×50 (the real full screen, 1920×1080)** | **99** | 12/12 | **40** | 12/12 |

What this means: at 190×50 the limit is taste, not space. All 12 widgets fit at comfortable size with room
to spare (the cockpit board uses 12 with a big library and visualiser). At 74×24 everything fits only at
minimum size, and at 60×18 the user has to choose.

## Textual limits we hit

- `position: absolute` with `offset` places widgets anywhere, at exact sizes. The packed and windowed boards
  use it, and a widget playground could use it too, with no grid maths.
- Text wraps by default. A long line silently becomes two and pushes the last rows out of the box, so
  every drawn widget needs `text-wrap: nowrap; text-overflow: ellipsis`.
- Border titles truncate with "…" when the box is narrow ("mo…" for a 9-column motif). At minimum size the
  title is often the first thing to go.
- `App.__init__` already calls `get_css_variables()`, so a subclass has to set its colours before
  `super().__init__()`.
- The real `#viz` panel draws only in the dashboard layout, so it was measured through the mock, which uses
  the same `theme.equaliser`.
- `hatch: right $colour` dims the cells outside a box cheaply. The gallery uses it to show "not your window".

## Gallery

`uv run python dev/gallery.py` writes 12 SVGs, every one a full 190×50 screen: a cockpit in 3 themes, a calm
two-panel layout, a strip column, splits in halves and thirds, small windows drawn inside the screen,
windows packed at minimum size, each widget at min vs comfortable size, and the whole screen packed at min
and at comfortable size.

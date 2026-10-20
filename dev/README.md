# Breaking ytm on purpose

There are no hand-written test lists here. Each round, someone (usually an LLM agent) reads the code and writes the scenarios **most likely to break it**, the counterexamples. Only scenarios that actually broke something are kept, in `breaks/`.

```powershell
uv run python dev/check.py                     # before a commit: ruff + history self-check + every break, one summary line
uv run python dev/try.py dev/breaks/*.json     # replay every known break (6 child processes in parallel, ~1 min)
uv run python dev/try.py my_idea.json --svg    # try a new idea; screens go to %TEMP%\ytm-try
uv run python dev/try.py dev/shots/motion.json --png --open   # PNG screenshots (headless Chrome or Edge), opened
```

`--png` needs Chrome or Edge (set `CHROME` to its path if it isn't found). A `{"shot": "f1", "wait": 0.1}` step saves a screen mid-scenario, e.g. animation frames; `dev/shots/` holds scenarios that are only for looking at. `--jobs 1` runs everything in one process (slower, easier to debug).

`try.py` renders the real UI with a fake player: no mpv, no network and no API spend. The scenario format is described at the top of the file.

The loop:
1. **Hunt.** Write scenarios aimed at edge cases nobody tried yet: odd sizes, odd data, odd sequences of actions. Read `breaks/` first so you don't repeat known ground.
2. **Keep the breaks.** Save each failing scenario as `breaks/<what-broke>.json`, with a `why` field explaining it.
3. **Fix.** Change the app until `try.py dev/breaks/*.json` passes. The breaks stay as regression checks.

## ytm vs ytmdev

- `ytm` runs a normal install of the latest release (a clone of `main`, e.g. `C:\Tools\ytm`). `ytm update` pulls the next release.
- `ytmdev` runs this checkout on a copy of your data in `%USERPROFILE%\.ytmdev`.

A `ytm.home` file next to the code (git-ignored) names the folder holding `data\ytm.db` and `mpv\history.tsv` for that copy; `YTM_HOME` overrides it. Without either, the data lives inside the code folder.

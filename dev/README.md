# Breaking ytm on purpose

There are no hand-written test lists here. Each round, someone (usually an LLM agent) reads the code and writes the scenarios **most likely to break it**, the counterexamples. Only scenarios that actually broke something are kept, in `breaks/`.

```powershell
python dev/try.py dev/breaks/*.json            # replay every known break
python dev/try.py my_idea.json --svg           # try a new idea; screens go to %TEMP%\ytm-try
```

`try.py` renders the real UI with a fake player: no mpv, no network and no API spend. The scenario format is described at the top of the file.

The loop:
1. **Hunt.** Write scenarios aimed at edge cases nobody tried yet: odd sizes, odd data, odd sequences of actions. Read `breaks/` first so you don't repeat known ground.
2. **Keep the breaks.** Save each failing scenario as `breaks/<what-broke>.json`, with a `why` field explaining it.
3. **Fix.** Change the app until `try.py dev/breaks/*.json` passes. The breaks stay as regression checks.

## ytm vs ytmdev

- `ytm` runs a pinned copy of the code (a git worktree at `G:\Projects\ytm-stable`) on your real library.
- `ytmdev` runs this checkout on a copy of your data in `%USERPROFILE%\.ytmdev`.

A `ytm.home` file next to the code (git-ignored) says which data folder that copy uses; `YTM_HOME` overrides it.

To move the stable copy forward to a newer commit:

```powershell
git -C G:\Projects\ytm-stable checkout --detach <commit>
```

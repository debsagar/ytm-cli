# Contributing

## Setup

Python refuses paths containing `;`, so keep the venv outside the repo:

```powershell
winget install shinchiro.mpv
winget install yt-dlp.yt-dlp
python -m venv $env:USERPROFILE\.venvs\ytm
& $env:USERPROFILE\.venvs\ytm\Scripts\python.exe -m pip install -r requirements.txt -r requirements-dev.txt
```

Run it with `ytm` (own small window) or `ytm here` (current terminal). See the README for putting `ytm` on your `PATH`.

## ytm vs ytmdev

`ytm` runs a pinned copy of the code on your real library. `ytmdev` runs your working checkout on a copy of your data in `%USERPROFILE%\.ytmdev`. A git-ignored `ytm.home` file next to the code (or the `YTM_HOME` environment variable) picks the data folder. Details are in [dev/README.md](dev/README.md).

## Branches and pull requests

- `main` holds releases. The owner merges `dev` into `main` and tags `vX.Y.Z` ([semver](https://semver.org)).
- `dev` is the integration branch.
- Do each change on a short branch (`feat/...`, `fix/...`, `chore/...`) and open a pull request into `dev`. Merge once CI is green.

## Before opening a PR

CI runs these on every push and pull request; run them locally first:

```powershell
python -m compileall -q ytm dev
ruff check .
python dev/try.py dev/breaks/*.json
```

`dev/try.py` renders the real UI with a fake player (no mpv, no network). Add a break scenario when you find a way to crash or garble the app: write `dev/breaks/<what-broke>.json` (format at the top of `dev/try.py`, with a `why` field), confirm it fails, then fix the app so it passes.

## Style

- Commit messages: an imperative summary line ("Fix seek past the end"), details below if needed.
- Add a line under `## [Unreleased]` in `CHANGELOG.md` for anything users would notice.
- Never commit secrets. API keys live in `%USERPROFILE%\.config\ytm\secrets.env`, outside the repo.

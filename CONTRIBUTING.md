# Contributing

## Setup

```powershell
winget install shinchiro.mpv
winget install yt-dlp.yt-dlp
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
uv sync    # .venv in the repo with the locked packages, plus ruff
```

Packages live in `pyproject.toml` and are pinned in `uv.lock`. Change them with `uv add` / `uv remove` and commit both files.

Run it with `ytm` (own small window) or `ytm here` (current terminal). See the README for putting `ytm` on your `PATH`.

## ytm vs ytmdev

`ytm` runs a normal install of the latest release on your real library (`ytm update` pulls the next one). `ytmdev` runs your working checkout on a copy of your data in `%USERPROFILE%\.ytmdev`. A git-ignored `ytm.home` file next to the code (or the `YTM_HOME` environment variable) picks the data folder. Details are in [dev/README.md](dev/README.md).

## Branches and pull requests

- `main` holds releases. The owner merges `dev` into `main` and tags `vX.Y.Z` ([semver](https://semver.org)). Bump the version in both `ytm/__init__.py` and `pyproject.toml`, then run `uv lock`.
- `dev` is the integration branch.
- Do each change on a short branch (`feat/...`, `fix/...`, `chore/...`) and open a pull request into `dev`. Merge once CI is green.

## Before opening a PR

CI runs these on every push and pull request; run them locally first:

```powershell
uv run python -m compileall -q ytm dev
uv run ruff check .
uv run python dev/try.py dev/breaks/*.json
```

`dev/try.py` renders the real UI with a fake player (no mpv, no network). Add a break scenario when you find a way to crash or garble the app: write `dev/breaks/<what-broke>.json` (format at the top of `dev/try.py`, with a `why` field), confirm it fails, then fix the app so it passes.

## Style

- Commit messages: an imperative summary line ("Fix seek past the end"), details below if needed.
- Add a line under `## [Unreleased]` in `CHANGELOG.md` for anything users would notice.
- Never commit secrets. API keys live in `%USERPROFILE%\.config\ytm\secrets.env`, outside the repo.

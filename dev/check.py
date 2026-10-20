"""Everything before a commit, in one line:  uv run python dev/check.py
ruff, a history.tsv self-check, and every scenario in dev/breaks (in parallel). Exits 1 on any failure."""

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from ytm import library  # noqa: E402


def history_ok():
    """library.history reads only the file's tail: it must match a plain read of the whole file."""
    library.HISTORY = Path(tempfile.mkdtemp(prefix="ytmcheck-")) / "history.tsv"
    lines = [f"2026-10-02 18:51\thttps://music.youtube.com/watch?v={i % 700:011d}\tSong {i} {'x' * (i % 90)}"
             for i in range(3000)]  # ~200 KB: past the first 64 KB chunk
    library.HISTORY.write_text("\n".join(lines) + "\n", encoding="utf-8")
    want, seen = [], set()
    for line in reversed(lines):
        vid = line.split("v=")[1][:11]
        if vid not in seen:
            seen.add(vid)
            want.append(vid)
    return all([t.video_id for t in library.history(n)] == want[:n] for n in (1, 100, 699, 5000))


sys.stdout.reconfigure(errors="replace")
start = time.time()
ruff = subprocess.run([sys.executable, "-m", "ruff", "check", "."], cwd=REPO, capture_output=True, text=True)
hist = history_ok()
tries = subprocess.run([sys.executable, str(REPO / "dev" / "try.py"), str(REPO / "dev" / "breaks" / "*.json")],
                       cwd=REPO, capture_output=True, encoding="utf-8", errors="replace",
                       env={**os.environ, "PYTHONIOENCODING": "utf-8"})
fails = [line for line in tries.stdout.splitlines() if line.startswith(("FAIL", "     "))]
passed = sum(line.startswith("PASS") for line in tries.stdout.splitlines())
if ruff.returncode:
    print(ruff.stdout.strip())
print("\n".join(fails))
ok = not ruff.returncode and hist and not tries.returncode
print(f"{'OK' if ok else 'FAILED'} · ruff {'clean' if not ruff.returncode else 'errors'} · history {'ok' if hist else 'WRONG'}"
      f" · {passed} passed, {len([f for f in fails if f.startswith('FAIL')])} failed · {time.time() - start:.0f} s")
sys.exit(0 if ok else 1)

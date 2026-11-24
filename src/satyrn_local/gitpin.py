"""Check out a git repository at a pinned commit, only the folders that are needed.

A commit hash names the exact content of every file, so a checkout of it is the same everywhere.
Only that one commit is fetched (``--depth 1``), file contents only for the ``paths`` of a
sparse checkout, so even CPython takes a few seconds and about 30 MB.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def _git(folder: Path, *args: str) -> str:
    out = subprocess.run(["git", "-C", str(folder), *args], check=True, capture_output=True, text=True)  # noqa: S607
    return out.stdout.strip()


def head(folder: Path) -> str | None:
    try:
        return _git(folder, "rev-parse", "HEAD")
    except subprocess.CalledProcessError, FileNotFoundError, NotADirectoryError:
        return None


def checkout(repo: str, commit: str, folder: Path, paths: list[str]) -> None:
    """Make ``folder`` a clean checkout of ``commit`` with only ``paths`` (sparse patterns)."""
    if head(folder) == commit and not _git(folder, "status", "--porcelain", "--untracked-files=no"):
        _git(folder, "sparse-checkout", "set", "--no-cone", *paths)
        print(f"  present  {folder.name} at {commit[:12]}")
        return
    folder.mkdir(parents=True, exist_ok=True)
    if not (folder / ".git").is_dir():
        _git(folder, "init", "--quiet")
        _git(folder, "remote", "add", "origin", repo)
    _git(folder, "remote", "set-url", "origin", repo)
    _git(folder, "sparse-checkout", "set", "--no-cone", *paths)
    print(f"  fetch    {repo} at {commit[:12]}")
    _git(folder, "fetch", "--quiet", "--depth", "1", "--filter=blob:none", "origin", commit)
    _git(folder, "checkout", "--quiet", "--force", "--detach", commit)
    if head(folder) != commit:
        raise SystemExit(f"{folder}: checkout of {commit} failed")

"""Run a command under a hard time limit that also stops everything the command started.

A model that cannot finish its task may keep calling tools forever, or start a program that
never ends. The interpreter runs those programs in terminals of their own (new sessions), so
stopping only the interpreter's process group would leave them running, still holding the
output pipe open. ``run_limited`` therefore collects all descendants before it stops anything,
sends SIGTERM, and follows up with SIGKILL after a grace period.
"""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import time
from collections.abc import Callable
from pathlib import Path

from .layout import IS_WINDOWS

TIME_LIMIT = 3600.0  # seconds per model run; the slowest model here needs ~20 min for sqrt.py
GRACE = 10.0  # seconds between SIGTERM and SIGKILL


def _windows_tool(name: str) -> str:
    return str(Path(os.environ.get("SYSTEMROOT", r"C:\Windows")) / "System32" / f"{name}.exe")


def _parents() -> dict[int, int]:
    """pid -> parent pid for every process (Linux: /proc, macOS: ps)."""
    parents: dict[int, int] = {}
    proc = Path("/proc")
    if proc.is_dir():
        for stat in proc.glob("[0-9]*/stat"):
            with contextlib.suppress(OSError, ValueError, IndexError):
                text = stat.read_text()
                # "pid (comm) state ppid ..."; comm may contain spaces and parentheses.
                parents[int(text.split(" ", 1)[0])] = int(text.rsplit(")", 1)[1].split()[1])
        return parents
    out = subprocess.run(["/bin/ps", "-A", "-o", "pid=,ppid="], capture_output=True, text=True, check=False)
    for line in out.stdout.splitlines():
        with contextlib.suppress(ValueError):
            pid, ppid = (int(field) for field in line.split())
            parents[pid] = ppid
    return parents


def descendants(pid: int) -> set[int]:
    children: dict[int, list[int]] = {}
    for child, parent in _parents().items():
        children.setdefault(parent, []).append(child)
    found: set[int] = set()
    todo = [pid]
    while todo:
        for child in children.get(todo.pop(), []):
            if child not in found:
                found.add(child)
                todo.append(child)
    return found


def alive(pid: int) -> bool:
    """True for a running process (a finished but unreaped "zombie" counts as gone)."""
    stat = Path(f"/proc/{pid}/stat")
    if stat.exists():
        with contextlib.suppress(OSError, IndexError):
            return stat.read_text().rsplit(")", 1)[1].split()[0] != "Z"
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _signal_all(pids: set[int], group: int, sig: signal.Signals) -> None:
    with contextlib.suppress(OSError):
        os.killpg(group, sig)
    for pid in pids:
        with contextlib.suppress(OSError):
            os.kill(pid, sig)


def stop_all(group: int, pids: set[int], grace: float = GRACE) -> None:
    """SIGTERM the process group and ``pids``; SIGKILL whatever still runs after ``grace``."""
    _signal_all(pids, group, signal.SIGTERM)
    deadline = time.monotonic() + grace
    while time.monotonic() < deadline and any(alive(p) for p in pids | {group}):
        time.sleep(0.2)
    _signal_all({p for p in pids | {group} if alive(p)}, group, signal.SIGKILL)


def run_limited(
    cmd: list[str],
    *,
    env: dict[str, str],
    stdout: Path,
    stderr: Path,
    on_line: Callable[[str], None] = lambda _line: None,
    limit: float | None = TIME_LIMIT,
    grace: float = GRACE,
    cwd: Path | None = None,
) -> int | None:
    """Run ``cmd`` with output in files, passing each new stdout line to ``on_line``.

    Returns the exit code, or None when the run reached ``limit`` seconds. Either way, every
    process the run started and left behind is stopped before this returns. Files instead of
    pipes: a stray process holding a pipe open could otherwise block the reader forever.
    """
    with stdout.open("w", encoding="utf-8") as out, stderr.open("w", encoding="utf-8") as err:
        proc = subprocess.Popen(
            cmd, env=env, cwd=cwd, stdin=subprocess.DEVNULL, stdout=out, stderr=err, start_new_session=not IS_WINDOWS
        )
    deadline = None if limit is None else time.monotonic() + limit
    seen: set[int] = set()  # every descendant observed while the run was going
    pending = ""
    timed_out = False
    next_scan = 0.0
    with stdout.open(encoding="utf-8", errors="replace") as follow:
        while True:
            finished = proc.poll() is not None
            pending += follow.read()
            *lines, pending = pending.split("\n")
            for line in lines:
                on_line(line + "\n")
            if finished:
                break
            if deadline is not None and time.monotonic() >= deadline:
                timed_out = True
                break
            if not IS_WINDOWS and time.monotonic() >= next_scan:
                seen |= descendants(proc.pid)
                next_scan = time.monotonic() + 2
            time.sleep(0.5)
        if pending:
            on_line(pending)
    if IS_WINDOWS:
        if timed_out:
            subprocess.run(
                [_windows_tool("taskkill"), "/PID", str(proc.pid), "/T", "/F"], capture_output=True, check=False
            )
    else:
        seen |= descendants(proc.pid)
        leftovers = {p for p in seen if alive(p)}
        if timed_out or leftovers:
            stop_all(proc.pid, leftovers, grace)
    proc.wait()
    return None if timed_out else proc.returncode

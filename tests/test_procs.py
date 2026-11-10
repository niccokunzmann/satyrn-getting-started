"""The time limit stops a run and everything it started. Real processes, nothing mocked."""

from __future__ import annotations

import os
import sys
import textwrap
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from satyrn_local import procs  # noqa: E402
from satyrn_local.layout import IS_WINDOWS  # noqa: E402

# Like a model that never finishes: the parent runs forever and has started a program in its own
# session (as the interpreter does for every command) that also runs forever and inherited stdout.
STUCK = textwrap.dedent("""
    import subprocess, sys, time
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(600)"], start_new_session=True)
    print(child.pid, flush=True)
    time.sleep(600)
""")


def test_normal_run_returns_exit_code_and_lines(tmp_path: Path) -> None:
    lines: list[str] = []
    code = procs.run_limited(
        [sys.executable, "-c", "print('one'); print('two', end='')"],
        env=dict(os.environ),
        stdout=tmp_path / "out.txt",
        stderr=tmp_path / "err.txt",
        on_line=lines.append,
        limit=60,
    )
    assert code == 0
    assert lines == ["one\n", "two"]


@pytest.mark.skipif(IS_WINDOWS, reason="Windows stops the tree with taskkill /T")
def test_time_limit_stops_the_run_and_what_it_started(tmp_path: Path) -> None:
    script = tmp_path / "stuck.py"
    script.write_text(STUCK)
    lines: list[str] = []
    started = time.monotonic()
    code = procs.run_limited(
        [sys.executable, str(script)],
        env=dict(os.environ),
        stdout=tmp_path / "out.txt",
        stderr=tmp_path / "err.txt",
        on_line=lines.append,
        limit=3,
        grace=2,
    )
    elapsed = time.monotonic() - started
    assert code is None, "the run should report that it hit the limit"
    assert elapsed < 3 + 2 + 5, f"stopping took {elapsed:.1f}s"
    child = int(lines[0])
    deadline = time.monotonic() + 5
    while procs.alive(child) and time.monotonic() < deadline:
        time.sleep(0.1)
    assert not procs.alive(child), "the program the run started in its own session is still running"


@pytest.mark.skipif(IS_WINDOWS, reason="POSIX process tree")
def test_programs_left_behind_by_a_finished_run_are_stopped(tmp_path: Path) -> None:
    script = tmp_path / "leaves.py"
    script.write_text(STUCK.replace("time.sleep(600)\n", "time.sleep(3)\n", 1).rstrip() + "\n")
    lines: list[str] = []
    code = procs.run_limited(
        [sys.executable, str(script)],
        env=dict(os.environ),
        stdout=tmp_path / "out.txt",
        stderr=tmp_path / "err.txt",
        on_line=lines.append,
        limit=60,
        grace=2,
    )
    assert code == 0
    child = int(lines[0])
    assert not procs.alive(child), "a program the finished run left behind is still running"

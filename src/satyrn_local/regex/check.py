"""Check an answer the way it will be used: Python's re, the real grep, the real sed.

A task's answer is right when it matches every string in ``match`` and none in ``no_match``
(Python: re.fullmatch or re.search, as the task says; grep: the lines it prints), or, for sed,
when it turns every input into the expected output. Any regex that does this counts, not only
the one in the dataset: there are many ways to write the same regex.

grep and sed run with LC_ALL=C (bytes, ASCII classes) and sed with --sandbox, so a sed answer
cannot run commands or write files (the e, w and r commands are refused).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import warnings

ENV = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LC_ALL": "C"}
TIMEOUT = 10  # seconds; also against regexes that backtrack for ages


def tool_versions() -> dict[str, str]:
    out = {}
    for tool in ("grep", "sed"):
        path = shutil.which(tool)
        if path is None:
            out[tool] = "missing"
            continue
        first = subprocess.run([tool, "--version"], capture_output=True, text=True, check=False, env=ENV)
        out[tool] = first.stdout.splitlines()[0] if first.stdout else "unknown"
    return out


def python(pattern: str, mode: str, match: list[str], no_match: list[str]) -> bool:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # FutureWarning for odd classes such as [[a]
            rx = re.compile(pattern)
    except re.error, RecursionError, OverflowError, ValueError, TypeError:
        return False
    test = rx.fullmatch if mode == "fullmatch" else rx.search
    return all(test(s) for s in match) and not any(test(s) for s in no_match)


def _run(command: list[str], lines: list[str]) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            command,
            input="".join(f"{s}\n" for s in lines),
            capture_output=True,
            text=True,
            env=ENV,
            timeout=TIMEOUT,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return None


def grep(pattern: str, *, extended: bool, match: list[str], no_match: list[str]) -> bool:
    if "\n" in pattern:
        return False
    lines = match + no_match
    done = _run(["grep", "-n", *(["-E"] if extended else []), "-e", pattern], lines)
    if done is None or done.returncode > 1:
        return False
    printed = {int(line.split(":", 1)[0]) for line in done.stdout.splitlines() if ":" in line}
    return printed == set(range(1, len(match) + 1))


SED_SCRIPT = re.compile(r"s(.).*\1.*\1[gI0-9]*")  # one s command; no other sed commands


def sed(script: str, *, extended: bool, pairs: list[list[str]]) -> bool:
    if "\n" in script or not SED_SCRIPT.fullmatch(script):
        return False
    done = _run(["sed", "--sandbox", *(["-E"] if extended else []), "-e", script], [a for a, _ in pairs])
    if done is None or done.returncode:
        return False
    return done.stdout.split("\n")[:-1] == [b for _, b in pairs]


def answer(task: dict, text: str) -> bool:
    """Is ``text`` a right answer to ``task`` (a row of the dataset)?"""
    dialect = task["dialect"]
    if dialect == "python":
        return python(text, task["mode"], task["match"], task["no_match"])
    if dialect in {"grep", "grep -E"}:
        return grep(text, extended=dialect == "grep -E", match=task["match"], no_match=task["no_match"])
    if dialect in {"sed", "sed -E"}:
        return sed(text, extended=dialect == "sed -E", pairs=task["pairs"])
    raise ValueError(f"unknown dialect {dialect}")

"""Score a model's answers to regex tasks: is the answer right by the task's tests?

The answer is taken out of the model's text the same way for every model: the first line, or
the inside of a code block; quotes and backticks around it, a ``re.compile("...")`` or a
``grep -E '...'`` around it are removed. Then it is checked as ``check.answer`` checks the
reference answers, but a Python answer runs in a process of its own with a time limit, because
a model's regex can backtrack for ages.
"""

from __future__ import annotations

import json
import re
import shlex
import subprocess
import sys
from collections import defaultdict

from . import check

ISOLATED = """
import json, re, sys, warnings
warnings.simplefilter("ignore")
task = json.loads(sys.stdin.read())
try:
    rx = re.compile(task["pattern"])
except Exception:
    print(0); raise SystemExit
test = rx.fullmatch if task["mode"] == "fullmatch" else rx.search
print(int(all(test(s) for s in task["match"]) and not any(test(s) for s in task["no_match"])))
"""


def python_isolated(pattern: str, mode: str, match: list[str], no_match: list[str]) -> bool:
    task = json.dumps({"pattern": pattern, "mode": mode, "match": match, "no_match": no_match})
    try:
        done = subprocess.run(
            [sys.executable, "-I", "-c", ISOLATED],
            input=task,
            capture_output=True,
            text=True,
            timeout=check.TIMEOUT,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False
    return done.stdout.strip() == "1"


def _unquote(text: str) -> str:
    """Quotes around a regex taken off, as written: a regex is meant raw, so "\\b" stays \\b."""
    m = re.fullmatch(r"""[rR]?(['"])(.*)\1""", text)
    return m.group(2) if m else text


def extract(output: str, dialect: str) -> str:
    text = output.strip()
    fence = re.search(r"```[\w-]*\n?(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    line = next((s.strip() for s in text.splitlines() if s.strip()), "")
    line = line.strip("`").strip()
    if dialect == "python":
        call = re.search(r"re\.\w+\(\s*([rRbB]?(['\"]).*?(?<!\\)\2)", line)
        if call:
            return _unquote(call.group(1))
        return _unquote(line)
    command = line.split("|")[-1].strip() if re.match(r"(echo|cat|printf)\b", line) else line
    if re.match(r"(grep|egrep|sed)\b", command):  # a whole command: take its regex or script
        try:
            words = shlex.split(command)
        except ValueError:
            return line
        if "-e" in words[:-1]:
            return words[words.index("-e") + 1]
        rest = [w for w in words[1:] if not w.startswith("-")]
        return rest[0] if rest else ""
    return _unquote(line)


def right(task: dict, output: str) -> tuple[str, bool]:
    answer = extract(output, task["dialect"])
    if not answer:
        return answer, False
    if task["dialect"] == "python":
        return answer, python_isolated(answer, task["mode"], task["match"], task["no_match"])
    return answer, check.answer(task, answer)


def group(source: str) -> str:
    return source.split(":", maxsplit=1)[0]


def summary(results: list[dict]) -> dict:
    out: dict = {"right": sum(r["right"] for r in results), "tasks": len(results)}
    for field in ("dialect", "task", "source"):
        counts: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        for r in results:
            key = group(r[field]) if field == "source" else r[field]
            counts[key][0] += r["right"]
            counts[key][1] += 1
        out[field] = {k: {"right": v[0], "tasks": v[1]} for k, v in sorted(counts.items())}
    return out


def table(s: dict) -> str:
    lines = [f"right: {s['right']}/{s['tasks']} ({100 * s['right'] / max(1, s['tasks']):.0f} %)"]
    for field, title in (("dialect", "by dialect"), ("task", "by kind of task"), ("source", "by source")):
        lines.append(f"{title}:")
        for key, v in s[field].items():
            lines.append(f"  {key:22s} {v['right']:4d}/{v['tasks']:<4d} {100 * v['right'] / max(1, v['tasks']):3.0f} %")
    return "\n".join(lines)

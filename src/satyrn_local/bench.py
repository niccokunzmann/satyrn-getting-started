"""The square-root task through `interpreter exec --oss`, for `check` (one run) and `bench` (many).

Nothing is mocked: the prompt goes to the real local model, the model writes sqrt.py with the
interpreter's tools, and the file is then run with three numbers and its output checked.
"""

from __future__ import annotations

import contextlib
import json
import math
import os
import subprocess
import sys
import time
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import agentconfig, ollama, procs
from .layout import Layout, Pins

SQRT_PROMPT = (
    "Create a Python program named sqrt.py in the current directory that takes a number as its "
    "first command-line argument and prints the square root of it. Only create the file."
)
SQRT_CASES = (("16", 4.0), ("2", math.sqrt(2)), ("0.25", 0.5))


@dataclass
class Outcome:
    model: str
    passed: bool
    detail: str
    seconds: float
    exit_code: int | None  # None: stopped at the time limit
    workdir: str
    effort: str | None = None
    load_seconds: float | None = None
    digest: str | None = None
    usage: dict[str, int] = field(default_factory=dict)  # summed over all model turns
    items: dict[str, int] = field(default_factory=dict)  # completed items by type (commands, patches, ...)
    failed_items: int = 0
    errors: list[str] = field(default_factory=list)


def interpreter_env(layout: Layout, pins: Pins) -> dict[str, str]:
    env = dict(os.environ)
    layout.interpreter_home.mkdir(parents=True, exist_ok=True)
    env.update(
        INTERPRETER_HOME=str(layout.interpreter_home),  # keeps ~/.openinterpreter untouched
        CODEX_OSS_BASE_URL=f"http://127.0.0.1:{pins.port}/v1",
        OLLAMA_HOST=f"127.0.0.1:{pins.port}",
    )
    return env


def _describe(item: dict) -> str:
    kind = item.get("type", "?")
    if kind == "command_execution":
        command = " ".join(str(item.get("command", "")).split())
        return f"command (exit {item.get('exit_code')}): {command[:90]}"
    if kind == "file_change":
        changes = ", ".join(f"{c.get('kind')} {Path(c.get('path', '')).name}" for c in item.get("changes", []))
        return f"file change ({item.get('status')}): {changes}"
    if kind in {"agent_message", "error"}:
        text = " ".join(str(item.get("text") or item.get("message", "")).split())
        return f"{kind}: {text[:110]}"
    return kind


def run_sqrt(
    layout: Layout,
    pins: Pins,
    model: str,
    *,
    effort: str | None = None,
    timeout: float | None = procs.TIME_LIMIT,
) -> Outcome:
    """Ask ``model`` for sqrt.py in a fresh directory, then check the program it wrote.

    After ``timeout`` seconds the run is stopped with everything it started, so a model that
    cannot finish (or a program it started that never ends) cannot block a check or benchmark.
    """
    agentconfig.write_catalog(layout, pins)
    work = layout.runtime / "checks" / f"{time.strftime('%Y%m%d-%H%M%S')}-{model.replace(':', '_')}"
    work.mkdir(parents=True)
    cmd = [str(layout.interpreter_exe()), "exec", "--json", "--oss", "-m", model, "--skip-git-repo-check"]
    cmd += ["-s", "workspace-write", "-C", str(work)]
    if effort:
        cmd += ["-c", f'model_reasoning_effort="{effort}"']
    cmd.append(SQRT_PROMPT)
    outcome = Outcome(model=model, passed=False, detail="", seconds=0.0, exit_code=None, workdir=str(work))
    outcome.effort = effort
    usage: Counter[str] = Counter()
    items: Counter[str] = Counter()
    started = time.monotonic()
    print(f"asking {model} via `interpreter exec --oss` in {work} ...", flush=True)
    events = work.parent / f"{work.name}.events.jsonl"
    stderr_log = work.parent / f"{work.name}.stderr.log"

    def on_line(line: str) -> None:
        with contextlib.suppress(json.JSONDecodeError):
            _record(json.loads(line), outcome, usage, items, started)

    exit_code = procs.run_limited(
        cmd, env=interpreter_env(layout, pins), stdout=events, stderr=stderr_log, on_line=on_line, limit=timeout
    )
    outcome.seconds = round(time.monotonic() - started, 1)
    outcome.exit_code = exit_code
    outcome.usage, outcome.items = dict(usage), dict(items)
    # Calls the interpreter refuses (unknown tool, bad arguments) only show up in its log.
    refused = [line for line in stderr_log.read_text(encoding="utf-8").splitlines() if "tools::router: error=" in line]
    outcome.failed_items += len(refused)
    outcome.errors += sorted({line.split("error=", 1)[1][:200] for line in refused})
    outcome.passed, outcome.detail = _verify(work / "sqrt.py")
    if exit_code is None:
        outcome.passed = False  # a run that had to be stopped does not count, whatever it left behind
        outcome.detail = f"stopped at the {timeout:.0f}s time limit; {outcome.detail}"
        # Ollama only notices the closed connection after the batch it is working on (minutes for
        # a dense model on a CPU). Unloading ends its model process at once.
        print(f"  time limit reached: unloading {model} so the server stops working on it", flush=True)
        ollama.unload(pins, model)
    return outcome


def _record(event: dict, outcome: Outcome, usage: Counter, items: Counter, started: float) -> None:
    kind = event.get("type", "")
    if kind == "turn.completed":
        usage.update({k: v for k, v in (event.get("usage") or {}).items() if isinstance(v, int)})
    elif kind in {"error", "turn.failed"}:
        message = str(event.get("message") or (event.get("error") or {}).get("message", ""))
        outcome.errors.append(message[:300])
        print(f"  [{time.monotonic() - started:5.0f}s] {kind}: {message[:110]}", flush=True)
    elif kind == "item.completed":
        item = event.get("item") or {}
        items[item.get("type", "?")] += 1
        if item.get("status") == "failed" or item.get("type") == "error":
            outcome.failed_items += 1
        if item.get("type") != "reasoning":
            print(f"  [{time.monotonic() - started:5.0f}s] {_describe(item)}", flush=True)


def _numbers(text: str) -> list[float]:
    """All numbers printed in ``text`` (e.g. "4.0" or "sqrt(16) = 4.0")."""
    values = []
    for token in text.replace(":", " ").replace("=", " ").split():
        with contextlib.suppress(ValueError):
            values.append(float(token))
    return values


def _verify(program: Path) -> tuple[bool, str]:
    if not program.is_file():
        return False, "sqrt.py was not created"
    for number, expected in SQRT_CASES:
        try:
            run = subprocess.run(
                [sys.executable, str(program), number],
                stdin=subprocess.DEVNULL,  # a program that asks for input gets EOF, not a wait
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return False, f"sqrt.py {number} did not finish within 30s"
        printed = run.stdout.strip() or run.stderr.strip()
        if run.returncode != 0 or not any(math.isclose(v, expected, rel_tol=1e-6) for v in _numbers(run.stdout)):
            return False, f"sqrt.py {number} printed {printed[:80]!r}"
    return True, "sqrt.py prints 4.0 / 1.414.. / 0.5 for 16 / 2 / 0.25"


# --- benchmark -------------------------------------------------------------------------------
def benchmark(
    layout: Layout,
    pins: Pins,
    models: list[str],
    *,
    runs: int,
    effort: str | None,
    timeout: float,
) -> list[Outcome]:
    out = layout.bench / f"{time.strftime('%Y%m%d-%H%M%S')}.jsonl"
    layout.bench.mkdir(parents=True, exist_ok=True)
    outcomes = []
    for model in models:
        digest = ollama.model_digest(pins, model)
        for run in range(1, runs + 1):
            print(f"\n=== {model}, run {run}/{runs}", flush=True)
            # One model in memory at a time, and no prompt cache left over from an earlier run.
            for loaded in ollama.loaded_models(pins):
                ollama.unload(pins, loaded)
            load_seconds = ollama.load(pins, model)
            print(f"  loaded in {load_seconds:.0f}s", flush=True)
            outcome = run_sqrt(layout, pins, model, effort=effort, timeout=timeout)
            outcome.load_seconds, outcome.digest = round(load_seconds, 1), digest
            print(f"  {'PASS' if outcome.passed else 'FAIL'} in {outcome.seconds:.0f}s: {outcome.detail}", flush=True)
            with out.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(asdict(outcome)) + "\n")
            outcomes.append(outcome)
    for loaded in ollama.loaded_models(pins):
        ollama.unload(pins, loaded)
    print(f"\nresults: {out}\n")
    print(table(outcomes))
    return outcomes


def _minutes(seconds: float) -> str:
    return f"{int(seconds // 60)}:{int(seconds % 60):02d}"


def table(outcomes: list[Outcome]) -> str:
    """Markdown table of benchmark outcomes."""
    rows = [
        "| Model | Effort | Result | Time (m:s) | Load (s) | Prompt tokens (cached) | Output tokens "
        "| Commands | Failed calls |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for o in outcomes:
        prompt = o.usage.get("input_tokens", 0)
        cached = o.usage.get("cached_input_tokens", 0)
        result = "pass" if o.passed else ("timeout" if o.exit_code is None else "fail")
        rows.append(
            f"| {o.model} | {o.effort or 'default'} | {result} | {_minutes(o.seconds)} | {o.load_seconds or 0:.0f} "
            f"| {prompt:,} ({cached:,}) | {o.usage.get('output_tokens', 0):,} "
            f"| {o.items.get('command_execution', 0)} | {o.failed_items} |"
        )
    return "\n".join(rows)

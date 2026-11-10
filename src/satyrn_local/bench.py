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

from . import agentconfig, ollama, piagent, procs
from .layout import Layout, Pins

SQRT_PROMPT = (
    "Create a Python program named sqrt.py in the current directory that takes a number as its "
    "first command-line argument and prints the square root of it. Only create the file."
)
SQRT_CASES = (("16", 4.0), ("2", math.sqrt(2)), ("0.25", 0.5))
WARMUP_PROMPT = "Reply with OK."  # makes the agent send its whole context once, with little to write
PI_TOOL_KINDS = {"bash": "command_execution", "write": "file_change", "edit": "file_change"}


@dataclass(frozen=True)
class Variant:
    """What `bench` may vary besides the model."""

    label: str = "default"
    effort: str | None = None
    instructions: Path | None = None  # another system prompt instead of config/context/open-interpreter.md
    overrides: tuple[str, ...] = ()  # interpreter config overrides, KEY=VALUE (TOML value)
    warm: bool = False  # keep the model loaded between runs (Ollama reuses its prompt cache)
    harness: str = "open-interpreter"  # the coding agent: "open-interpreter" or "pi"
    warmup: bool = False  # let the agent answer WARMUP_PROMPT first, in the same folder; time only the task


@dataclass
class Outcome:
    model: str
    passed: bool
    detail: str
    seconds: float
    exit_code: int | None  # None: stopped at the time limit
    workdir: str
    effort: str | None = None
    variant: str = "default"
    warm: bool = False
    harness: str = "open-interpreter"
    warmup_seconds: float | None = None
    load_seconds: float | None = None
    digest: str | None = None
    usage: dict[str, int] = field(default_factory=dict)  # summed over all model turns
    items: dict[str, int] = field(default_factory=dict)  # completed items by type (commands, patches, ...)
    failed_items: int = 0
    errors: list[str] = field(default_factory=list)
    # From the server log: one entry per model request (read = prompt processing, write = generation).
    requests: list[dict[str, float]] = field(default_factory=list)

    @property
    def intake_seconds(self) -> float | None:
        """Time to read the context before the first answer (the first request's prompt processing)."""
        return self.requests[0]["read_s"] if self.requests else None


def interpreter_env(layout: Layout, pins: Pins) -> dict[str, str]:
    env = dict(os.environ)
    layout.interpreter_home.mkdir(parents=True, exist_ok=True)
    env.update(
        INTERPRETER_HOME=str(layout.interpreter_home),  # keeps ~/.openinterpreter untouched
        CODEX_OSS_BASE_URL=f"http://127.0.0.1:{pins.port}/v1",
        OLLAMA_HOST=f"127.0.0.1:{pins.port}",
        # The name Open Interpreter shows instead of "Codex"/"Open Interpreter". Releases up to the
        # pinned 0.0.60 ignore it; a change that adds it was prepared for Open Interpreter.
        OPEN_INTERPRETER_PRODUCT_NAME="Satyrn",
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
    variant: Variant | None = None,
) -> Outcome:
    """Ask ``model`` for sqrt.py in a fresh directory, then check the program it wrote.

    After ``timeout`` seconds the run is stopped with everything it started, so a model that
    cannot finish (or a program it started that never ends) cannot block a check or benchmark.
    """
    variant = variant or Variant(effort=effort)
    agentconfig.write_catalog(layout, pins)
    work = layout.runtime / "checks" / f"{time.strftime('%Y%m%d-%H%M%S')}-{model.replace(':', '_')}"
    work.mkdir(parents=True)
    outcome = Outcome(model=model, passed=False, detail="", seconds=0.0, exit_code=None, workdir=str(work))
    outcome.effort, outcome.variant, outcome.warm = variant.effort, variant.label, variant.warm
    outcome.harness = variant.harness
    if variant.warmup:
        began = time.monotonic()
        print(f"warming up {variant.harness} with {model} in {work} ...", flush=True)
        cmd, env, cwd = agent_command(layout, pins, model, variant, work, WARMUP_PROMPT)
        procs.run_limited(
            cmd,
            env=env,
            cwd=cwd,
            stdout=work.parent / f"{work.name}.warmup.jsonl",
            stderr=work.parent / f"{work.name}.warmup.stderr.log",
            limit=timeout,
        )
        outcome.warmup_seconds = round(time.monotonic() - began, 1)
        print(f"  warm-up took {outcome.warmup_seconds:.0f}s", flush=True)
    log_start = layout.logfile.stat().st_size if layout.logfile.is_file() else None
    usage: Counter[str] = Counter()
    items: Counter[str] = Counter()
    started = time.monotonic()
    print(f"asking {model} via {variant.harness} in {work} ...", flush=True)
    events = work.parent / f"{work.name}.events.jsonl"
    stderr_log = work.parent / f"{work.name}.stderr.log"

    record = _record_pi if variant.harness == "pi" else _record

    def on_line(line: str) -> None:
        with contextlib.suppress(json.JSONDecodeError):
            record(json.loads(line), outcome, usage, items, started)

    cmd, env, cwd = agent_command(layout, pins, model, variant, work, SQRT_PROMPT)
    exit_code = procs.run_limited(
        cmd, env=env, cwd=cwd, stdout=events, stderr=stderr_log, on_line=on_line, limit=timeout
    )
    outcome.seconds = round(time.monotonic() - started, 1)
    outcome.exit_code = exit_code
    if log_start is not None:
        with layout.logfile.open(encoding="utf-8", errors="replace") as log:
            log.seek(log_start)
            outcome.requests = ollama.request_timings(log.read())
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


def agent_command(
    layout: Layout, pins: Pins, model: str, variant: Variant, work: Path, prompt: str
) -> tuple[list[str], dict[str, str], Path | None]:
    """Command line, environment and working folder for one request to the chosen coding agent."""
    if variant.harness == "pi":
        piagent.write_config(layout, pins)
        args = ["--mode", "json", "--model", piagent.model_ref(model), "--no-session"]
        if variant.instructions:
            args += ["--system-prompt", variant.instructions.read_text(encoding="utf-8")]
        return piagent.command(layout, [*args, prompt]), piagent.env(layout, pins), work
    agentconfig.write_catalog(layout, pins)
    cmd = [str(layout.interpreter_exe()), "exec", "--json", "--oss", "-m", model, "--skip-git-repo-check"]
    cmd += ["-s", "workspace-write", "-C", str(work)]
    if variant.effort:
        cmd += ["-c", f'model_reasoning_effort="{variant.effort}"']
    if variant.instructions:
        catalog = agentconfig.write_catalog(
            layout, pins, variant.instructions, layout.bench / f"catalog-{variant.instructions.stem}.json"
        )
        cmd += ["-c", f"model_catalog_json={json.dumps(str(catalog))}"]
    for override in variant.overrides:
        cmd += ["-c", override]
    return [*cmd, prompt], interpreter_env(layout, pins), None


def _record_pi(event: dict, outcome: Outcome, usage: Counter, items: Counter, started: float) -> None:
    """pi's JSON events: tool calls and the model's messages."""
    kind = event.get("type", "")
    when = f"  [{time.monotonic() - started:5.0f}s]"
    if kind == "tool_execution_end":
        name = str(event.get("toolName", "?"))
        items[PI_TOOL_KINDS.get(name, name)] += 1
        if event.get("isError"):
            outcome.failed_items += 1
        print(f"{when} {name} ({'error' if event.get('isError') else 'ok'})", flush=True)
    elif kind == "message_end":
        message = event.get("message") or {}
        for key, value in (message.get("usage") or {}).items():
            if isinstance(value, int):
                usage[key] += value
        if message.get("role") == "assistant":
            parts = message.get("content") or []
            text = " ".join(p.get("text", "") for p in parts if isinstance(p, dict) and p.get("type") == "text")
            if text.strip():
                print(f"{when} answer: {' '.join(text.split())[:110]}", flush=True)
    elif kind in {"error", "agent_error"}:
        outcome.errors.append(str(event)[:300])


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
    timeout: float,
    variant: Variant,
) -> list[Outcome]:
    out = layout.bench / f"{time.strftime('%Y%m%d-%H%M%S')}.jsonl"
    layout.bench.mkdir(parents=True, exist_ok=True)
    outcomes = []
    for model in models:
        digest = ollama.model_digest(pins, model)
        for run in range(1, runs + 1):
            print(f"\n=== {model}, run {run}/{runs} ({variant.label})", flush=True)
            load_seconds = 0.0
            if run == 1 or not variant.warm:
                # One model in memory at a time, and no prompt cache left over from an earlier run.
                for loaded in ollama.loaded_models(pins):
                    ollama.unload(pins, loaded)
                load_seconds = ollama.load(pins, model)
                print(f"  loaded in {load_seconds:.0f}s", flush=True)
            outcome = run_sqrt(layout, pins, model, timeout=timeout, variant=variant)
            outcome.load_seconds, outcome.digest = round(load_seconds, 1), digest
            outcome.warm = variant.warm and run > 1
            intake = f", context read in {outcome.intake_seconds:.0f}s" if outcome.intake_seconds is not None else ""
            print(
                f"  {'PASS' if outcome.passed else 'FAIL'} in {outcome.seconds:.0f}s{intake}: {outcome.detail}",
                flush=True,
            )
            with out.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(asdict(outcome) | {"intake_seconds": outcome.intake_seconds}) + "\n")
            outcomes.append(outcome)
    for loaded in ollama.loaded_models(pins):
        ollama.unload(pins, loaded)
    print(f"\nresults: {out}\n")
    print(table(outcomes))
    return outcomes


def _minutes(seconds: float) -> str:
    return f"{int(seconds // 60)}:{int(seconds % 60):02d}"


def table(outcomes: list[Outcome]) -> str:
    """Markdown table of benchmark outcomes. Read/write: the server's prompt processing and
    generation time summed over all requests of the run; context: the first request's reading."""
    rows = [
        "| Model | Variant | Result | Time (m:s) | Load (s) | Context read (s / tokens) | Read (s) "
        "| Write (s / tokens) | Requests | Commands | Failed calls |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for o in outcomes:
        result = "pass" if o.passed else ("timeout" if o.exit_code is None else "fail")
        variant = f"{o.harness}, {o.variant}" + (", warm" if o.warm else "") + (", warm-up" if o.warmup_seconds else "")
        variant += f", effort {o.effort}" if o.effort else ""
        first = o.requests[0] if o.requests else None
        context = f"{first['read_s']:.0f} / {first['read_tokens']:.0f}" if first else "-"
        read = sum(r["read_s"] for r in o.requests)
        write_s = sum(r["write_s"] for r in o.requests)
        write_tokens = sum(r["write_tokens"] for r in o.requests)
        rows.append(
            f"| {o.model} | {variant} | {result} | {_minutes(o.seconds)} | {o.load_seconds or 0:.0f} | {context} "
            f"| {read:.0f} | {write_s:.0f} / {write_tokens:.0f} | {len(o.requests)} "
            f"| {o.items.get('command_execution', 0)} | {o.failed_items} |"
        )
    return "\n".join(rows)

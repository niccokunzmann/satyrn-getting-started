#!/usr/bin/env python3
"""How fast does a model read a prompt under different Ollama settings?

    python3.14 experiments/prompt_speed.py [--port 11434] [--model gpt-oss:20b] [--runs 2] [--cold]

Sends the same prompt of about 1,500 tokens (documentation text, like the context a coding agent
sends) straight to Ollama, with a random first line so that Ollama's cache cannot help, and asks
for a single output token. Reports Ollama's own measurements: load time and prompt reading time.
Every request option variant below is tried in turn; results also go to .runtime/bench/.

--cold unloads the model first, to measure loading too. --write N lets the model write N tokens
and reports its writing speed as well. --label marks a run against a server started with other
settings (only the default request settings are tried then). --server-env KEY=VALUE (repeatable)
starts a temporary Ollama on a free port with these settings, measures against it and stops it;
unload the model from the main server first, so that memory is free.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import secrets
import socket
import subprocess
import sys
import time
import urllib.request
from collections.abc import Iterator
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VARIANTS: list[tuple[str, dict]] = [
    ("default (batch 1024, 10 threads)", {}),
    ("batch 256", {"num_batch": 256}),
    ("batch 2048", {"num_batch": 2048}),
    ("8 threads", {"num_thread": 8}),
    ("6 threads", {"num_thread": 6}),
]


def call(port: int, path: str, body: dict, timeout: float = 1800) -> dict:
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - local server
        return json.load(response)


def prompt_text(chars: int = 6000) -> str:
    text = (ROOT / "docs" / "how-it-works.md").read_text(encoding="utf-8")
    return text[:chars]


def measure(port: int, model: str, options: dict, write: int = 1) -> dict:
    body = {
        "model": model,
        "prompt": f"Session {secrets.token_hex(8)}.\n\n{prompt_text()}",  # new first line: no cache reuse
        "raw": True,
        "stream": False,
        "keep_alive": "30m",
        "options": {"num_predict": write, **options},
    }
    started = time.monotonic()
    result = call(port, "/api/generate", body)
    return {
        "load_s": round(result.get("load_duration", 0) / 1e9, 1),
        "tokens": result.get("prompt_eval_count", 0),
        "read_s": round(result.get("prompt_eval_duration", 0) / 1e9, 1),
        "written": result.get("eval_count", 0),
        "write_s": round(result.get("eval_duration", 0) / 1e9, 1),
        "wall_s": round(time.monotonic() - started, 1),
    }


@contextlib.contextmanager
def temporary_server(settings: list[str]) -> Iterator[int]:
    """An Ollama with extra environment settings on a free port, using the project's models."""
    sys.path.insert(0, str(ROOT / "src"))
    from satyrn_local import ollama  # noqa: PLC0415 - only needed here
    from satyrn_local.layout import Layout, Pins  # noqa: PLC0415

    layout, pins = Layout(ROOT), Pins.load(ROOT / "pins.toml")
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    env = ollama.server_env(layout, pins) | {"OLLAMA_HOST": f"127.0.0.1:{port}"}
    env |= dict(setting.split("=", 1) for setting in settings)
    log = (layout.runtime / f"ollama-{port}.log").open("w")
    proc = subprocess.Popen([str(layout.ollama_exe()), "serve"], env=env, stdout=log, stderr=log)
    try:
        for _ in range(120):
            with contextlib.suppress(OSError):
                urllib.request.urlopen(f"http://127.0.0.1:{port}/api/version", timeout=1)
                break
            time.sleep(0.5)
        yield port
    finally:
        proc.terminate()
        proc.wait(timeout=60)
        log.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=11434)
    parser.add_argument("--model", default="gpt-oss:20b")
    parser.add_argument("--runs", type=int, default=2)
    parser.add_argument("--cold", action="store_true", help="unload the model first and measure loading")
    parser.add_argument("--label", default="", help="added to every row, e.g. the server settings")
    parser.add_argument("--write", type=int, default=1, help="tokens the model writes (to measure writing speed)")
    parser.add_argument("--server-env", action="append", default=[], metavar="KEY=VALUE", help="temporary server")
    args = parser.parse_args()
    if args.server_env:
        with temporary_server(args.server_env) as port:
            args.port, args.label = port, args.label or " ".join(args.server_env)
            return run(args)
    return run(args)


def run(args: argparse.Namespace) -> int:
    out = ROOT / ".runtime" / "bench" / f"prompt-speed-{time.strftime('%Y%m%d-%H%M%S')}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    variants = VARIANTS if not args.label else VARIANTS[:1]
    if args.cold:
        call(args.port, "/api/generate", {"model": args.model, "keep_alive": 0}, timeout=120)
        time.sleep(3)
    print("| Settings | Run | Load (s) | Tokens | Read (s) | Read tokens/s | Write tokens/s |")
    print("| --- | ---: | ---: | ---: | ---: | ---: | ---: |")
    for run in range(1, args.runs + 1):
        for name, options in variants:
            row = measure(args.port, args.model, options, args.write)
            row |= {"variant": f"{name} {args.label}".strip(), "run": run}
            rate = row["tokens"] / row["read_s"] if row["read_s"] else 0
            writing = row["written"] / row["write_s"] if row["write_s"] else 0
            print(
                f"| {row['variant']} | {run} | {row['load_s']} | {row['tokens']} | {row['read_s']} "
                f"| {rate:.1f} | {writing:.1f} |",
                flush=True,
            )
            with out.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row) + "\n")
    print(f"\nresults: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

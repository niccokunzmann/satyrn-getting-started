#!/usr/bin/env python3
"""How fast does a model read a prompt under different Ollama settings?

    python3.14 experiments/prompt_speed.py [--port 11434] [--model gpt-oss:20b] [--runs 2] [--cold]

Sends the same prompt of about 1,500 tokens (documentation text, like the context a coding agent
sends) straight to Ollama, with a random first line so that Ollama's cache cannot help, and asks
for a single output token. Reports Ollama's own measurements: load time and prompt reading time.
Every request option variant below is tried in turn; results also go to .runtime/bench/.

--cold unloads the model first, to measure loading too.
"""

from __future__ import annotations

import argparse
import json
import secrets
import time
import urllib.request
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


def measure(port: int, model: str, options: dict) -> dict:
    body = {
        "model": model,
        "prompt": f"Session {secrets.token_hex(8)}.\n\n{prompt_text()}",  # new first line: no cache reuse
        "raw": True,
        "stream": False,
        "keep_alive": "30m",
        "options": {"num_predict": 1, **options},
    }
    started = time.monotonic()
    result = call(port, "/api/generate", body)
    return {
        "load_s": round(result.get("load_duration", 0) / 1e9, 1),
        "tokens": result.get("prompt_eval_count", 0),
        "read_s": round(result.get("prompt_eval_duration", 0) / 1e9, 1),
        "wall_s": round(time.monotonic() - started, 1),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=11434)
    parser.add_argument("--model", default="gpt-oss:20b")
    parser.add_argument("--runs", type=int, default=2)
    parser.add_argument("--cold", action="store_true", help="unload the model first and measure loading")
    parser.add_argument("--label", default="", help="added to every row, e.g. the server settings")
    args = parser.parse_args()
    out = ROOT / ".runtime" / "bench" / f"prompt-speed-{time.strftime('%Y%m%d-%H%M%S')}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    variants = VARIANTS if not args.label else VARIANTS[:1]
    if args.cold:
        call(args.port, "/api/generate", {"model": args.model, "keep_alive": 0}, timeout=120)
        time.sleep(3)
    print("| Settings | Run | Load (s) | Tokens | Read (s) | Tokens/s |")
    print("| --- | ---: | ---: | ---: | ---: | ---: |")
    for run in range(1, args.runs + 1):
        for name, options in variants:
            row = measure(args.port, args.model, options) | {"variant": f"{name} {args.label}".strip(), "run": run}
            rate = row["tokens"] / row["read_s"] if row["read_s"] else 0
            print(f"| {row['variant']} | {run} | {row['load_s']} | {row['tokens']} | {row['read_s']} | {rate:.1f} |")
            with out.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row) + "\n")
    print(f"\nresults: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

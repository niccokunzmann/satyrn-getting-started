#!/usr/bin/env python3
"""How long does the first request of an interactive `satyrn code` session take?

    python3.14 experiments/first_answer.py [--think 30] [--harness pi] [-- satyrn code options]

A real terminal session (pseudo-terminal, real model): the model is unloaded first, as after a
break; `satyrn code` starts in a new folder; after --think seconds (a person reading and typing)
the request is sent, and the time until the model is done is measured. Done means: hello.py exists
and the screen has been still for 8 seconds. Run it with and without `--no-warmup`.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import select
import struct
import subprocess
import sys
import tempfile
import termios
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUEST = "Create hello.py that prints Hello, World! Then run it."


def unload(model: str, port: int = 11434) -> None:
    for name in [m["name"] for m in json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/api/ps"))["models"]]:
        body = json.dumps({"model": name, "keep_alive": 0}).encode()
        request = urllib.request.Request(f"http://127.0.0.1:{port}/api/generate", data=body)
        urllib.request.urlopen(request, timeout=120).read()  # noqa: S310 - local server
    time.sleep(3)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--think", type=float, default=30, help="seconds before the request is sent")
    parser.add_argument("--model", default="gpt-oss:20b")
    parser.add_argument("options", nargs="*", help="more `satyrn code` options, e.g. --no-warmup")
    args = parser.parse_args()
    unload(args.model)
    folder = Path(tempfile.mkdtemp(prefix="first-answer-"))
    controller, terminal = os.openpty()
    fcntl.ioctl(terminal, termios.TIOCSWINSZ, struct.pack("HHHH", 40, 120, 0, 0))
    command = ["satyrn", "code", str(folder), "-m", args.model, *args.options]
    proc = subprocess.Popen(
        command,
        stdin=terminal,
        stdout=terminal,
        stderr=terminal,
        env=dict(os.environ, TERM="xterm-256color"),
        start_new_session=True,
    )
    os.close(terminal)
    last_output = time.monotonic()

    def pump(seconds: float) -> None:
        nonlocal last_output
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if select.select([controller], [], [], 0.2)[0]:
                try:
                    os.read(controller, 65536)
                except OSError:
                    return
                last_output = time.monotonic()

    pump(args.think)
    for char in REQUEST:
        os.write(controller, char.encode())
        pump(0.02)
    os.write(controller, b"\r")
    sent = time.monotonic()
    program = folder / "hello.py"
    while not (program.exists() and time.monotonic() - last_output > 8):
        if time.monotonic() - sent > 1800:
            print(json.dumps({"options": args.options, "error": "not done within 30 minutes"}))
            proc.kill()
            return 1
        pump(0.5)
    seconds = round(last_output - sent, 1)
    proc.terminate()
    output = subprocess.run([sys.executable, str(program)], capture_output=True, text=True, check=False).stdout
    print(
        json.dumps(
            {"options": args.options, "think_s": args.think, "first_answer_s": seconds, "output": output.strip()}
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

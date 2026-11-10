#!/usr/bin/env python3
# /// script
# requires-python = ">=3.14"
# dependencies = ["pyte==0.8.2", "pillow==13.0.0"]
# ///
"""Record the hello-world example of the documentation with the real model, then render it.

    satyrn start
    uv run docs/example/record.py

A real terminal session: bash runs `satyrn code ~/ai-code` (with HOME set to a fresh temporary
folder), trusts the folder, types the request, waits until the model is done, leaves with
Ctrl+C and runs the program the model wrote. Nothing is staged. Writes next to this script:

    hello-world.cast   the whole session in asciicast v2 format (output with its timing)
    hello-world.gif    a 10-second animation of the important moments, each a real screen of
                       the session (see KEYFRAMES)
    hello-world.txt    the whole session as text, including what scrolled off the screen
    hello-world.json   durations of the real session, for the text in the docs

`uv run docs/example/record.py --render` renders the files again from hello-world.cast.
"""

from __future__ import annotations

import json
import os
import re
import select
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

import pyte
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
COLS, ROWS = 100, 30
REQUEST = "Create hello.py that prints Hello, World! Then run it."
# Keyboard-protocol switches (CSI > 1 u and similar) that pyte does not know and would print.
UNKNOWN_SEQUENCES = re.compile(r"\x1b\[[<>=?]?[0-9;]*u")


class Session:
    """A shell in a pseudo-terminal; everything it prints is recorded with its time."""

    def __init__(self, home: Path) -> None:
        import fcntl  # noqa: PLC0415 - POSIX only
        import pty  # noqa: PLC0415
        import struct  # noqa: PLC0415
        import termios  # noqa: PLC0415

        self.controller, terminal = pty.openpty()
        fcntl.ioctl(terminal, termios.TIOCSWINSZ, struct.pack("HHHH", ROWS, COLS, 0, 0))
        env = {
            "PATH": os.environ["PATH"],
            "HOME": str(home),
            "TERM": "xterm-256color",
            "LANG": "C.UTF-8",
            "PS1": "$ ",
            "SHELL": "/bin/bash",
        }
        bash = shutil.which("bash") or "/bin/bash"
        self.proc = subprocess.Popen(
            [bash, "--noprofile", "--norc", "-i"],
            stdin=terminal,
            stdout=terminal,
            stderr=terminal,
            env=env,
            cwd=home,
            start_new_session=True,
        )
        os.close(terminal)
        self.start = time.monotonic()
        self.last_output = self.start
        self.events: list[tuple[float, str]] = []
        self.screen = pyte.Screen(COLS, ROWS)
        self.stream = pyte.Stream(self.screen)  # only to see what is on the screen while recording

    def pump(self, seconds: float) -> None:
        end = time.monotonic() + seconds
        while (left := end - time.monotonic()) > 0:
            ready, _, _ = select.select([self.controller], [], [], min(left, 0.05))
            if not ready:
                continue
            try:
                data = os.read(self.controller, 65536).decode("utf-8", "replace")
            except OSError:
                return
            now = time.monotonic()
            self.events.append((now - self.start, data))
            self.stream.feed(UNKNOWN_SEQUENCES.sub("", data))
            self.last_output = now

    def text(self) -> str:
        return "\n".join(line.rstrip() for line in self.screen.display).strip("\n")

    def expect(self, needle: str, timeout: float) -> None:
        end = time.monotonic() + timeout
        while needle not in self.text():
            if time.monotonic() > end:
                raise SystemExit(f"timed out waiting for {needle!r}; screen:\n{self.text()}")
            self.pump(0.2)

    def expect_prompt(self, timeout: float) -> None:
        """Wait until the line with the cursor is a fresh shell prompt."""
        end = time.monotonic() + timeout
        while self.screen.display[self.screen.cursor.y].rstrip() != "$":
            if time.monotonic() > end:
                raise SystemExit(f"timed out waiting for the shell prompt; screen:\n{self.text()}")
            self.pump(0.2)

    def type(self, text: str, delay: float = 0.06) -> None:
        for char in text:
            os.write(self.controller, char.encode())
            self.pump(delay)

    def press(self, keys: str) -> None:
        os.write(self.controller, keys.encode())
        self.pump(0.3)


def record(home: Path) -> tuple[Session, dict[str, float]]:
    session = Session(home)
    times: dict[str, float] = {}
    session.expect_prompt(10)
    session.pump(1)
    session.type("satyrn code ~/ai-code")
    session.press("\r")
    session.expect("Trust this folder", 120)
    session.pump(2)
    session.press("\r")
    session.expect("to do anything", 120)
    session.pump(1.5)
    session.type(REQUEST)
    session.press("\r")
    asked = time.monotonic()
    program = home / "ai-code" / "hello.py"
    deadline = asked + 15 * 60
    # Done: the program exists and the screen has been still for a while (no more spinner).
    while not (program.exists() and time.monotonic() - session.last_output > 8):
        if time.monotonic() > deadline:
            raise SystemExit("the model did not finish within 15 minutes")
        session.pump(0.5)
    times["model_seconds"] = round(session.last_output - asked, 1)
    session.pump(2)
    session.press("\x03")
    session.pump(0.7)
    session.press("\x03")
    session.expect_prompt(30)
    session.pump(1)
    session.type("python3 ai-code/hello.py")
    session.press("\r")
    session.expect("Hello, World", 30)
    session.pump(3)
    session.type("exit")
    session.press("\r")
    session.proc.wait(timeout=30)
    times["session_seconds"] = round(time.monotonic() - session.start, 1)
    return session, times


# --- rendering --------------------------------------------------------------------------------
FONT_DIR = Path("/usr/share/fonts/truetype/dejavu")
FONT = ImageFont.truetype(str(FONT_DIR / "DejaVuSansMono.ttf"), 15)
BOLD = ImageFont.truetype(str(FONT_DIR / "DejaVuSansMono-Bold.ttf"), 15)
CELL_W, CELL_H, PAD = round(FONT.getlength("M")), 19, 12
BACKGROUND, FOREGROUND = "1e1e2e", "d4d4d4"
NAMED = {
    "black": "1e1e2e", "red": "e06c75", "green": "98c379", "brown": "e5c07b", "yellow": "e5c07b",
    "blue": "61afef", "magenta": "c678dd", "cyan": "56b6c2", "white": "d4d4d4",
    "brightblack": "7f848e", "brightred": "ff7b86", "brightgreen": "b5e890", "brightbrown": "ffd68a",
    "brightyellow": "ffd68a", "brightblue": "82c4ff", "brightmagenta": "de9bff", "brightcyan": "7fd8e3",
    "brightwhite": "ffffff",
}  # fmt: skip


def color(value: str, default: str) -> str:
    if value == "default":
        return default
    return NAMED.get(value, value if len(value) == 6 else default)  # names, or rrggbb from 256/24-bit colors


def draw(screen: pyte.Screen) -> Image.Image:
    image = Image.new("RGB", (COLS * CELL_W + 2 * PAD, ROWS * CELL_H + 2 * PAD), f"#{BACKGROUND}")
    pen = ImageDraw.Draw(image)
    for y in range(ROWS):
        line = screen.buffer[y]
        for x in range(COLS):
            char = line[x]
            fg, bg = color(char.fg, FOREGROUND), color(char.bg, BACKGROUND)
            if char.reverse:
                fg, bg = bg, fg
            left, top = PAD + x * CELL_W, PAD + y * CELL_H
            if bg != BACKGROUND:
                pen.rectangle([left, top, left + CELL_W - 1, top + CELL_H - 1], fill=f"#{bg}")
            if char.data.strip():
                pen.text((left, top + 1), char.data, font=BOLD if char.bold else FONT, fill=f"#{fg}")
    return image


def transcript(screen: pyte.HistoryScreen) -> str:
    """Everything that scrolled off the top, then the screen."""
    rows = [*screen.history.top, *(screen.buffer[y] for y in range(ROWS))]
    lines = ["".join(row[x].data for x in range(COLS)).rstrip() for row in rows]
    return "\n".join(lines).strip("\n") + "\n"


def program_ran_in_shell(lines: list[str]) -> bool:
    if "$ python3 ai-code/hello.py" not in lines:
        return False
    return "Hello, World!" in lines[lines.index("$ python3 ai-code/hello.py") + 1 :]


# The important moments: a screen is taken the first time its condition is true (in this order),
# and shown for the given seconds. Together they make a 10-second animation.
KEYFRAMES: list[tuple[str, Callable[[list[str]], bool], float]] = [
    ("command typed", lambda lines: "$ satyrn code ~/ai-code" in lines, 1.0),
    ("trust question", lambda lines: any("Trust this folder" in line for line in lines), 1.3),
    ("interpreter ready", lambda lines: any("to do anything" in line for line in lines), 0.7),
    ("request typed", lambda lines: any(REQUEST in line for line in lines), 1.1),
    ("model working", lambda lines: any("• esc" in line for line in lines), 0.9),
    ("file written", lambda lines: any("Ran cat > hello.py" in line for line in lines), 0.9),
    ("program run", lambda lines: any("└ Hello, World!" in line for line in lines), 0.9),
    ("answer", lambda lines: any("Worked for" in line for line in lines), 1.5),
    ("program run in the shell", program_ran_in_shell, 1.7),
]


def render(events: list[tuple[float, str]], gif: Path) -> tuple[float, str]:
    """Write the animation of the KEYFRAMES; return its length in seconds and the session as text."""
    screen = pyte.HistoryScreen(COLS, ROWS, history=100_000)
    stream = pyte.Stream(screen)
    frames: list[Image.Image] = []
    for _when, data in events:
        stream.feed(UNKNOWN_SEQUENCES.sub("", data))
        lines = [line.rstrip() for line in screen.display]
        while len(frames) < len(KEYFRAMES) and KEYFRAMES[len(frames)][1](lines):
            frames.append(draw(screen))
    if len(frames) < len(KEYFRAMES):
        raise SystemExit(f"the session never showed: {KEYFRAMES[len(frames)][0]}")
    durations = [round(seconds * 1000) for _name, _condition, seconds in KEYFRAMES]
    palette = frames[-1].quantize(colors=128)
    images = [frame.quantize(palette=palette, dither=Image.Dither.NONE) for frame in frames]
    images[0].save(gif, save_all=True, append_images=images[1:], duration=durations, loop=0, optimize=True)
    return sum(durations) / 1000, transcript(screen)


def read_cast(path: Path) -> list[tuple[float, str]]:
    lines = path.read_text(encoding="utf-8").splitlines()[1:]  # the first line is the header
    return [(when, data) for when, kind, data in map(json.loads, lines) if kind == "o"]


def main() -> int:
    if sys.platform == "win32":
        raise SystemExit("recording needs a POSIX pseudo-terminal")
    cast, info = HERE / "hello-world.cast", HERE / "hello-world.json"
    if "--render" in sys.argv[1:]:
        events, times = read_cast(cast), json.loads(info.read_text(encoding="utf-8"))
    else:
        config = ROOT / ".runtime" / "interpreter-home" / "config.toml"
        saved_config = config.read_text(encoding="utf-8")
        home = Path(tempfile.mkdtemp(prefix="satyrn-example-"))
        try:
            session, times = record(home)
        finally:
            config.write_text(saved_config, encoding="utf-8")  # forget the demo folder's trust decision
            shutil.rmtree(home, ignore_errors=True)
        events = session.events
        with cast.open("w", encoding="utf-8") as out:
            header = {
                "version": 2,
                "width": COLS,
                "height": ROWS,
                "env": {"TERM": "xterm-256color", "SHELL": "/bin/bash"},
            }
            out.write(json.dumps(header) + "\n")
            for when, data in events:
                out.write(json.dumps([round(when, 3), "o", data]) + "\n")
    seconds, text = render(events, HERE / "hello-world.gif")
    times["animation_seconds"] = round(seconds, 1)
    (HERE / "hello-world.txt").write_text(text, encoding="utf-8")
    info.write_text(json.dumps(times, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(times))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

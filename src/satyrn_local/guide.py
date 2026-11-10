"""`satyrn` without a command: show what is ready and offer each missing step.

Every question has a default (Enter accepts it). Nothing is started without asking, and when
the input is not a terminal, the guide only reports and names the next command.
"""

from __future__ import annotations

from collections.abc import Callable

from . import fetch, machine, modelinfo, ollama, piagent, settings
from .layout import Layout, Pins

Step = Callable[[], object]


def tools_ready(layout: Layout, pins: Pins) -> bool:
    return (
        all(
            fetch.is_unpacked(target, pins.asset(component).sha256)
            for component, target in (("ollama", layout.ollama_dir), ("interpreter", layout.interpreter_dir))
        )
        and (layout.interpreter_home / "config.toml").is_file()
        and piagent.is_installed(layout, pins)
    )


HARNESS_CHOICES = (
    ("pi", "pi: tools to read, write and edit files; runs commands without asking (no sandbox)"),
    ("open-interpreter", "Open Interpreter: commands run in a sandbox and may ask for your approval"),
)


def ask_harness() -> str:
    print("Which coding agent should `satyrn code` use?")
    for number, (_name, text) in enumerate(HARNESS_CHOICES, 1):
        print(f"  {number}  {text}")
    try:
        answer = input("Number or name [1] ").strip() or "1"
    except EOFError:
        answer = "1"
    names = [name for name, _text in HARNESS_CHOICES]
    if answer.isdigit() and 1 <= int(answer) <= len(names):
        return names[int(answer) - 1]
    return answer if answer in names else names[0]


def ask_yes(question: str, *, default: bool = True) -> bool:
    hint = "[Y/n]" if default else "[y/N]"
    try:
        answer = input(f"{question} {hint} ").strip().lower()
    except EOFError:
        return default
    return default if not answer else answer in {"y", "yes"}


def ask_model(found: list[modelinfo.Choice]) -> str | None:
    best = modelinfo.recommended(found)
    default = str(found.index(best) + 1) if best else ""
    try:
        answer = input(f"Which model? Number or name [{default}] ").strip() or default
    except EOFError:
        answer = default
    if not answer:
        return None
    return modelinfo.by_number(found, answer)


def _line(name: str, text: str, *, done: bool) -> str:
    return f"  [{'x' if done else ' '}] {name:<8} {text}"


def run(layout: Layout, pins: Pins, *, interactive: bool, setup: Step, pull: Callable[[str], bool]) -> int:
    model = settings.default_model(layout, pins)
    tools = tools_ready(layout, pins)
    pulled = settings.is_pulled(layout, model)
    server = ollama.is_up(pins)
    versions = {name: pins.data[name]["version"] for name in ("ollama", "interpreter", "pi")}
    print("Local code generation: what is ready\n")
    print(
        _line(
            "tools",
            f"Ollama {versions['ollama']}, Open Interpreter {versions['interpreter']} and pi {versions['pi']}"
            + ("" if tools else " are not downloaded yet"),
            done=tools,
        )
    )
    print(_line("model", f"{model}" + (" downloaded" if pulled else " is not downloaded yet"), done=pulled))
    print(_line("server", f"running on 127.0.0.1:{pins.port}" if server else "not running", done=server))
    print()

    if not interactive:
        step = (
            "satyrn setup --no-model"
            if not tools
            else f"satyrn models, then satyrn pull {model}"
            if not pulled
            else "satyrn start"
            if not server
            else "satyrn code ~/ai-code"
        )
        print(f"Next: {step}")
        return 0

    if not tools:
        if not ask_yes("Download and verify Ollama, Open Interpreter and pi now (about 4 GB)?"):
            print("Later: satyrn setup --no-model")
            return 0
        setup()
        print()
    if "harness" not in settings.load(layout):
        harness = ask_harness()
        settings.set_default_harness(layout, harness)
        print(f"`satyrn code` uses {harness} (change it with `satyrn setup --harness NAME`).\n")
    if not pulled:
        here = machine.detect(layout.runtime)
        found = modelinfo.choices(layout, pins, here)
        print(modelinfo.table(found, here), "\n")
        choice = ask_model(found)
        if choice is None:
            print("Later: satyrn models, then satyrn pull MODEL")
            return 0
        if not settings.is_pulled(layout, choice) and not pull(choice):
            print("Later: satyrn models, then satyrn pull MODEL")
            return 0
        settings.set_default_model(layout, choice)
        model = choice
        print(f"\n{model} is your default model (change it with `satyrn use MODEL`).\n")
    if not server:
        if not ask_yes("Start the model server now? It runs until `satyrn stop`."):
            print("Later: satyrn start")
            return 0
        ollama.start(layout, pins)
        print()
    print(f"Ready. Let {model} write code in a folder of your choice:\n\n  satyrn code ~/ai-code\n")
    print("Stop the model server when you are done: satyrn stop")
    return 0

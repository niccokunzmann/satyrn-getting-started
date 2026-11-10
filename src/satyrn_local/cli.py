"""python satyrn.py <command> - project-local Ollama + Open Interpreter, pinned and reproducible."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tomllib
from pathlib import Path

from . import agentconfig, bench, fetch, ollama, procs
from .bench import interpreter_env
from .layout import IS_WINDOWS, Layout, Pins, platform_key


def run_tool(exe: Path, args: list[str], env: dict[str, str]) -> int:
    """Hand the terminal to ``exe`` (exec on POSIX so signals/TTY behave natively)."""
    if IS_WINDOWS:
        return subprocess.call([str(exe), *args], env=env)
    os.execve(exe, [str(exe), *args], env)  # noqa: S606 - pinned, verified binary
    return 0  # unreachable


# --- generated files ---------------------------------------------------------------------
def write_interpreter_config(layout: Layout, pins: Pins) -> None:
    template = (layout.root / "config" / "interpreter.toml").read_text(encoding="utf-8")
    catalog = agentconfig.write_catalog(layout, pins)
    target = layout.interpreter_home / "config.toml"
    # json.dumps gives a valid TOML string, also for Windows paths with backslashes.
    text = template.replace("@MODEL@", pins.model).replace("@CATALOG@", json.dumps(str(catalog)))
    target.write_text(text + _kept_projects(target), encoding="utf-8")
    print(f"  config   {target}")
    print(f"  models   {catalog} ({', '.join(agentconfig.known_models(layout))})")


def _kept_projects(config: Path) -> str:
    """The `[projects."<dir>"]` tables the interpreter adds when you trust a folder, as TOML."""
    try:
        projects = tomllib.loads(config.read_text(encoding="utf-8")).get("projects", {})
    except OSError, tomllib.TOMLDecodeError:
        return ""
    tables = []
    for folder, settings in projects.items():
        values = "".join(f"{key} = {json.dumps(value)}\n" for key, value in settings.items())
        tables.append(f"\n[projects.{json.dumps(folder)}]\n{values}")
    return "".join(tables)


def write_launchers(layout: Layout) -> None:
    """Tiny generated launchers so `interpreter` / `ollama` work after activating the env."""
    layout.bin.mkdir(parents=True, exist_ok=True)
    py, script = sys.executable, layout.root / "satyrn.py"
    for name in ("interpreter", "ollama"):
        if IS_WINDOWS:
            (layout.bin / f"{name}.cmd").write_text(f'@"{py}" "{script}" {name} %*\r\n', encoding="utf-8")
        else:
            launcher = layout.bin / name
            launcher.write_text(f'#!/bin/sh\nexec "{py}" "{script}" {name} "$@"\n', encoding="utf-8")
            launcher.chmod(0o755)
    (layout.runtime / "activate").write_text(f'export PATH="{layout.bin}:$PATH"\n', encoding="utf-8")
    (layout.runtime / "activate.ps1").write_text(f'$env:PATH = "{layout.bin};" + $env:PATH\n', encoding="utf-8")
    (layout.runtime / "activate.bat").write_text(f'@set "PATH={layout.bin};%PATH%"\r\n', encoding="utf-8")
    print(f"  launchers {layout.bin}")


# --- commands ----------------------------------------------------------------------------
def check_model_digest(pins: Pins, model: str, digest: str) -> None:
    print(f"  model    {model} digest {digest}")
    pinned = pins.digest(model)
    if pinned is None:
        print(f'  note     not pinned; to pin it add  "{model}" = "{digest}"  to [model.digests] in pins.toml')
    elif digest != pinned:
        raise SystemExit(f"{model} resolved to {digest}, but pins.toml pins {pinned} (upstream tag changed)")
    else:
        print("  verified model digest matches pins.toml")


def cmd_setup(layout: Layout, pins: Pins, args: argparse.Namespace) -> int:
    print(f"platform {platform_key()}, everything goes to {layout.runtime}")
    for component, target in (("ollama", layout.ollama_dir), ("interpreter", layout.interpreter_dir)):
        print(f"{component} {pins.data[component]['version']}:")
        asset = pins.asset(component)
        archive = fetch.download(asset, layout.downloads)
        if component == "ollama" and not fetch.is_unpacked(target, asset.sha256) and ollama.is_up(pins):
            raise SystemExit(
                "Ollama must be (re)installed but a server is running; stop it first: python satyrn.py stop"
            )
        fetch.unpack(archive, target, asset.sha256)
    print("configuration:")
    write_interpreter_config(layout, pins)
    write_launchers(layout)
    if not args.no_model:
        model = args.model or pins.model
        print(f"model {model}:")
        with ollama.running(layout, pins):
            check_model_digest(pins, model, ollama.pull(layout, pins, model))
    print("\nsetup complete. Next:\n  python satyrn.py start\n  python satyrn.py interpreter --oss")
    return 0


def cmd_verify(layout: Layout, pins: Pins, _args: argparse.Namespace) -> int:
    failures = 0
    for component, target in (("ollama", layout.ollama_dir), ("interpreter", layout.interpreter_dir)):
        asset = pins.asset(component)
        archive = layout.downloads / f"{asset.component}-{asset.version}-{asset.file}"
        stamp = target / fetch.STAMP
        ok_archive = archive.is_file() and fetch.sha256_file(archive) == asset.sha256
        ok_unpacked = stamp.is_file() and stamp.read_text().strip() == asset.sha256
        archive_state = "ok" if ok_archive else "MISSING/BAD"
        unpacked_state = "ok" if ok_unpacked else "MISSING/STALE"
        print(f"{component:12s} archive {archive_state}, unpacked {unpacked_state}")
        failures += not (ok_archive and ok_unpacked)
    with ollama.running(layout, pins):
        pulled = {model: ollama.model_digest(pins, model) for model in pins.digests}
    for model, digest in pulled.items():
        if digest is None:
            print(f"model        {model} not pulled" + (" (the default!)" if model == pins.model else ""))
            failures += model == pins.model  # other pinned models are optional
            continue
        try:
            check_model_digest(pins, model, digest)
        except SystemExit as error:
            print(f"model        {error}")
            failures += 1
    print("all pinned inputs verified" if not failures else f"{failures} problem(s); run: python satyrn.py setup")
    return 1 if failures else 0


def cmd_status(layout: Layout, pins: Pins, _args: argparse.Namespace) -> int:
    if not ollama.is_up(pins):
        print(f"Ollama: not running on port {pins.port} (start: python satyrn.py start)")
        return 1
    version = ollama.api(pins, "/api/version")["version"]
    models = [m["name"] for m in ollama.api(pins, "/api/tags").get("models", [])]
    loaded = [m["name"] for m in ollama.api(pins, "/api/ps").get("models", [])]
    print(f"Ollama {version} on 127.0.0.1:{pins.port}")
    print(f"  models: {', '.join(models) or '-'}")
    print(f"  loaded: {', '.join(loaded) or '-'}")
    return 0


def cmd_pull(layout: Layout, pins: Pins, args: argparse.Namespace) -> int:
    with ollama.running(layout, pins):
        check_model_digest(pins, args.model, ollama.pull(layout, pins, args.model))
    return 0


def cmd_check(layout: Layout, pins: Pins, args: argparse.Namespace) -> int:
    """Acceptance test: the local model, through `interpreter exec --oss`, writes a working sqrt.py."""
    if not ollama.is_up(pins):
        raise SystemExit("Ollama is not running; start it first: python satyrn.py start")
    outcome = bench.run_sqrt(layout, pins, args.model or pins.model, effort=args.effort, timeout=args.timeout)
    exit_code = "time limit" if outcome.exit_code is None else outcome.exit_code
    print(f"interpreter finished in {outcome.seconds:.0f}s ({exit_code}); {outcome.detail}")
    if not outcome.passed:
        print("FAIL: the model did not write a working square-root program")
        return 1
    print("SUCCESS: the local model wrote a working square-root program")
    return 0


def cmd_bench(layout: Layout, pins: Pins, args: argparse.Namespace) -> int:
    """Time every model on the square-root task and print a table."""
    if not ollama.is_up(pins):
        raise SystemExit("Ollama is not running; start it first: python satyrn.py start")
    models = args.models or agentconfig.known_models(layout)
    missing = [m for m in models if ollama.model_digest(pins, m) is None]
    if missing:
        raise SystemExit("not pulled: " + ", ".join(missing) + "\n  python satyrn.py pull " + " ".join(missing))
    outcomes = bench.benchmark(layout, pins, models, runs=args.runs, effort=args.effort, timeout=args.timeout)
    return 0 if all(o.passed for o in outcomes) else 1


# --- entry point ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python satyrn.py", description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    s = sub.add_parser("setup", help="download + verify Ollama and Open Interpreter, write config, pull the model")
    s.add_argument("--model", help="model to pull instead of [model].default")
    s.add_argument("--no-model", action="store_true", help="skip the model download")
    sub.add_parser("verify", help="re-check every pinned checksum and the model digest")
    sub.add_parser("serve", help="run Ollama in the foreground (Ctrl+C stops it)")
    sub.add_parser("start", help="start Ollama in the background")
    sub.add_parser("stop", help="stop the Ollama started with 'start'")
    sub.add_parser("status", help="show server, installed and loaded models")
    pl = sub.add_parser("pull", help="pull another model into .runtime/models")
    pl.add_argument("model")
    c = sub.add_parser("check", help="acceptance test: let the model write and verify sqrt.py")
    c.add_argument("--model", help="model to test instead of [model].default")
    b = sub.add_parser("bench", help="time models on the sqrt.py task (default: all in config/models.toml)")
    b.add_argument("models", nargs="*", help="models to benchmark")
    b.add_argument("--runs", type=int, default=1, help="runs per model (default 1)")
    for task in (c, b):
        task.add_argument("--effort", help="reasoning effort for models that have one (e.g. low)")
        task.add_argument(
            "--timeout",
            type=float,
            default=procs.TIME_LIMIT,
            help=f"stop a run, and everything it started, after this many seconds (default {procs.TIME_LIMIT:.0f})",
        )
    for name, what in (("interpreter", "Open Interpreter"), ("ollama", "Ollama CLI")):
        t = sub.add_parser(name, help=f"run the pinned {what} with project settings", add_help=False)
        t.add_argument("args", nargs=argparse.REMAINDER)
    return p


def main(root: Path, argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    layout = Layout(root)
    pins = Pins.load(layout.pins_file)
    # Pass-through commands: hand every following argument (including --options) to the tool.
    if argv and argv[0] == "interpreter":
        agentconfig.write_catalog(layout, pins)
        return run_tool(layout.interpreter_exe(), argv[1:], interpreter_env(layout, pins))
    if argv and argv[0] == "ollama":
        return run_tool(layout.ollama_exe(), argv[1:], ollama.server_env(layout, pins))
    args = build_parser().parse_args(argv)
    simple = {"serve": ollama.serve, "start": ollama.start, "stop": ollama.stop}
    if args.command in simple:
        return simple[args.command](layout, pins) or 0
    handlers = {
        "setup": cmd_setup,
        "verify": cmd_verify,
        "status": cmd_status,
        "pull": cmd_pull,
        "check": cmd_check,
        "bench": cmd_bench,
    }
    return handlers[args.command](layout, pins, args)

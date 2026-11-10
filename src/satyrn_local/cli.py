"""satyrn - generate code with a local model: Open Interpreter + Ollama, pinned and reproducible.

Run it without a command to see what is ready and be guided through the missing steps."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tomllib
from collections.abc import Callable
from pathlib import Path

from . import (
    agentconfig,
    bench,
    completion,
    fetch,
    guide,
    install,
    machine,
    modelinfo,
    modelpins,
    ollama,
    piagent,
    procs,
    settings,
)
from .bench import interpreter_env
from .layout import IS_WINDOWS, Layout, Pins, platform_key


def run_tool(exe: Path, args: list[str], env: dict[str, str], cwd: Path | None = None) -> int:
    """Hand the terminal to ``exe`` (exec on POSIX so signals/TTY behave natively)."""
    if IS_WINDOWS:
        return subprocess.call([str(exe), *args], env=env, cwd=cwd)
    if cwd is not None:
        os.chdir(cwd)
    os.execve(exe, [str(exe), *args], env)  # noqa: S606 - pinned, verified binary
    return 0  # unreachable


def run_pi(layout: Layout, pins: Pins, args: list[str], cwd: Path | None = None) -> int:
    piagent.write_config(layout, pins)
    node, *rest = piagent.command(layout, args)
    return run_tool(Path(node), rest, piagent.env(layout, pins), cwd)


# --- generated files ---------------------------------------------------------------------
def write_interpreter_config(layout: Layout, pins: Pins, *, quiet: bool = False) -> None:
    template = (layout.root / "config" / "interpreter.toml").read_text(encoding="utf-8")
    catalog = agentconfig.write_catalog(layout, pins)
    target = layout.interpreter_home / "config.toml"
    # json.dumps gives a valid TOML string, also for Windows paths with backslashes.
    model = settings.default_model(layout, pins)
    text = template.replace("@MODEL@", model).replace("@CATALOG@", json.dumps(str(catalog)))
    target.write_text(text + _kept_projects(target), encoding="utf-8")
    if not quiet:
        print(f"  config   {target}")
        print(f"  models   {catalog} ({', '.join(agentconfig.known_models(layout))})")


def _kept_projects(config: Path) -> str:
    """The `[projects."<dir>"]` tables the interpreter adds when you trust a folder, as TOML."""
    try:
        projects = tomllib.loads(config.read_text(encoding="utf-8")).get("projects", {})
    except OSError, tomllib.TOMLDecodeError:
        return ""
    tables = []
    for folder, options in projects.items():
        values = "".join(f"{key} = {json.dumps(value)}\n" for key, value in options.items())
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
def interactive() -> bool:
    """Questions are asked only in a terminal; elsewhere the default answer applies."""
    return sys.stdin.isatty() and sys.stdout.isatty()


def cmd_setup(layout: Layout, pins: Pins, args: argparse.Namespace) -> int:
    print(f"platform {platform_key()}, everything goes to {layout.runtime}")
    for component, target in (("ollama", layout.ollama_dir), ("interpreter", layout.interpreter_dir)):
        print(f"{component} {pins.data[component]['version']}:")
        asset = pins.asset(component)
        archive = fetch.download(asset, layout.downloads)
        if component == "ollama" and not fetch.is_unpacked(target, asset.sha256) and ollama.is_up(pins):
            raise SystemExit("Ollama must be (re)installed but a server is running; stop it first: satyrn stop")
        fetch.unpack(archive, target, asset.sha256)
    print(f"node {pins.data['node']['version']} and pi {pins.data['pi']['version']}:")
    piagent.install(layout, pins)
    if args.harness:
        settings.set_default_harness(layout, args.harness)
    print("configuration:")
    write_interpreter_config(layout, pins)
    piagent.write_config(layout, pins)
    print(f"  pi       {layout.pi_home}")
    print(f"  default coding agent: {settings.default_harness(layout)}")
    write_launchers(layout)
    if not args.no_model:
        model = args.model or settings.default_model(layout, pins)
        print(f"model {model}:")
        if not modelpins.pull(layout, pins, model, ask=interactive()):
            print("  setup continues without a model; choose one later: satyrn models")
    print("\nsetup complete. Next: satyrn (shows what is still missing)")
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
        elif digest == pins.digest(model):
            print(f"model        {model} is the build pinned in pins.toml")
        elif digest == settings.accepted_digest(layout, model):
            print(f"model        {model} differs from pins.toml; you accepted this build")
        else:
            print(f"model        {model} differs from pins.toml ({digest}); see {modelpins.DOCS}")
            failures += 1
    print("all pinned inputs verified" if not failures else f"{failures} problem(s); run: satyrn setup")
    return 1 if failures else 0


def cmd_status(layout: Layout, pins: Pins, _args: argparse.Namespace) -> int:
    if not ollama.is_up(pins):
        print(f"Ollama: not running on port {pins.port} (start: satyrn start)")
        return 1
    version = ollama.api(pins, "/api/version")["version"]
    models = [m["name"] for m in ollama.api(pins, "/api/tags").get("models", [])]
    loaded = [m["name"] for m in ollama.api(pins, "/api/ps").get("models", [])]
    print(f"Ollama {version} on 127.0.0.1:{pins.port}")
    print(f"  models: {', '.join(models) or '-'}")
    print(f"  loaded: {', '.join(loaded) or '-'}")
    return 0


def cmd_pull(layout: Layout, pins: Pins, args: argparse.Namespace) -> int:
    return 0 if modelpins.pull(layout, pins, args.model, ask=interactive()) else 1


def cmd_check(layout: Layout, pins: Pins, args: argparse.Namespace) -> int:
    """Acceptance test: the local model, through `interpreter exec --oss`, writes a working sqrt.py."""
    if not ollama.is_up(pins):
        raise SystemExit("Ollama is not running; start it first: satyrn start")
    model = args.model or settings.default_model(layout, pins)
    outcome = bench.run_sqrt(layout, pins, model, effort=args.effort, timeout=args.timeout)
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
        raise SystemExit("Ollama is not running; start it first: satyrn start")
    models = args.models or agentconfig.known_models(layout)
    missing = [m for m in models if ollama.model_digest(pins, m) is None]
    if missing:
        raise SystemExit("not pulled: " + ", ".join(missing) + "\n  satyrn pull " + " ".join(missing))
    variant = bench.Variant(
        label=args.label or (args.instructions.stem if args.instructions else "default"),
        effort=args.effort,
        instructions=args.instructions,
        overrides=tuple(args.set),
        warm=args.warm,
    )
    outcomes = bench.benchmark(layout, pins, models, runs=args.runs, timeout=args.timeout, variant=variant)
    return 0 if all(o.passed for o in outcomes) else 1


def _start_if_wanted(layout: Layout, pins: Pins) -> None:
    if ollama.is_up(pins):
        return
    if sys.stdin.isatty() and guide.ask_yes("The model server is not running. Start it now?"):
        ollama.start(layout, pins)
        return
    raise SystemExit("The model server is not running; start it first: satyrn start")


def cmd_code(layout: Layout, pins: Pins, args: argparse.Namespace) -> int:
    """Open Interpreter on the local model in a folder: a conversation, or one request (-p)."""
    folder = Path(args.dir).expanduser().resolve()
    found = modelinfo.choices(layout, pins, machine.detect(layout.runtime))
    model = modelinfo.listed(found, args.model or settings.default_model(layout, pins))
    exe = layout.interpreter_exe()
    if not settings.is_pulled(layout, model):
        raise SystemExit(f"{model} is not downloaded yet: satyrn pull {model}  (or run `satyrn` to be guided)")
    _start_if_wanted(layout, pins)
    folder.mkdir(parents=True, exist_ok=True)
    if (args.harness or settings.default_harness(layout)) == "pi":
        prompt = ["--print", args.prompt] if args.prompt else []
        return run_pi(layout, pins, ["--model", piagent.model_ref(model), *prompt], cwd=folder)
    agentconfig.write_catalog(layout, pins)
    if args.prompt:
        argv = ["exec", "--oss", "-m", model, "--skip-git-repo-check", "-s", "workspace-write", "-C", str(folder)]
        return run_tool(exe, [*argv, args.prompt], interpreter_env(layout, pins))
    return run_tool(exe, ["--oss", "-m", model, "-C", str(folder)], interpreter_env(layout, pins))


def cmd_models(layout: Layout, pins: Pins, _args: argparse.Namespace) -> int:
    here = machine.detect(layout.runtime)
    found = modelinfo.choices(layout, pins, here)
    print(modelinfo.table(found, here))
    print()
    print(modelinfo.selection_help(found))
    return 0


def cmd_use(layout: Layout, pins: Pins, args: argparse.Namespace) -> int:
    args.model = modelinfo.listed(modelinfo.choices(layout, pins, machine.detect(layout.runtime)), args.model)
    if not settings.is_pulled(layout, args.model):
        print(f"note: {args.model} is not downloaded yet: satyrn pull {args.model}")
    settings.set_default_model(layout, args.model)
    if (layout.interpreter_home / "config.toml").is_file():
        write_interpreter_config(layout, pins, quiet=True)
    print(f"{args.model} is your default model")
    return 0


def cmd_guide(layout: Layout, pins: Pins, _args: argparse.Namespace) -> int:
    def setup() -> int:
        return cmd_setup(layout, pins, argparse.Namespace(model=None, no_model=True))

    def pull(model: str) -> bool:
        return modelpins.pull(layout, pins, model, ask=True)

    return guide.run(layout, pins, interactive=interactive(), setup=setup, pull=pull)


# --- entry point ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="satyrn", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = p.add_subparsers(dest="command")
    i = sub.add_parser("install", help="install the `satyrn` command (linked to this folder) and tab completion")
    i.add_argument("--shell", choices=completion.SHELLS, help="shell for tab completion (default: yours)")
    sub.add_parser("uninstall", help="remove the `satyrn` command and its tab completion")
    co = sub.add_parser("code", help="let the model work in a folder: a conversation, or one request with -p")
    co.add_argument("dir", nargs="?", default=".", help="folder to work in (default: the current one)")
    co.add_argument("-p", "--prompt", help="one request; the model works on it until done, then exits")
    co.add_argument("-m", "--model", help="a listed model (name or number) instead of your default")
    agent = co.add_mutually_exclusive_group()
    agent.add_argument("--pi", dest="harness", action="store_const", const="pi", help="use pi this time")
    agent.add_argument(
        "--open-interpreter",
        dest="harness",
        action="store_const",
        const="open-interpreter",
        help="use Open Interpreter this time",
    )
    sub.add_parser("models", help="rate the prepared models for this computer")
    u = sub.add_parser("use", help="make a model your default")
    u.add_argument("model", help="model name, or its number in `satyrn models`")
    cp = sub.add_parser("completion", help="print the tab-completion script for a shell")
    cp.add_argument("shell", choices=completion.SHELLS)
    s = sub.add_parser("setup", help="download + verify Ollama and Open Interpreter, write config, pull the model")
    s.add_argument("--model", help="model to pull instead of [model].default")
    s.add_argument("--no-model", action="store_true", help="skip the model download")
    s.add_argument("--harness", choices=settings.HARNESSES, help="default coding agent for `satyrn code` (default: pi)")
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
    b.add_argument("--warm", action="store_true", help="keep the model loaded between runs (prompt cache reused)")
    b.add_argument(
        "--instructions", type=Path, help="try another system prompt instead of config/context/open-interpreter.md"
    )
    b.add_argument(
        "--set", action="append", default=[], metavar="KEY=VALUE", help="interpreter config override (repeatable)"
    )
    b.add_argument("--label", help="name of this variant in the results")
    for task in (c, b):
        task.add_argument("--effort", help="reasoning effort for models that have one (e.g. low)")
        task.add_argument(
            "--timeout",
            type=float,
            default=procs.TIME_LIMIT,
            help=f"stop a run, and everything it started, after this many seconds (default {procs.TIME_LIMIT:.0f})",
        )
    for name, what in (("pi", "pi"), ("interpreter", "Open Interpreter"), ("ollama", "Ollama CLI")):
        t = sub.add_parser(name, help=f"run the pinned {what} with project settings", add_help=False)
        t.add_argument("args", nargs=argparse.REMAINDER)
    return p


def cmd_install(layout: Layout, _pins: Pins, args: argparse.Namespace) -> int:
    return install.install(layout, args.shell)


def cmd_uninstall(layout: Layout, _pins: Pins, _args: argparse.Namespace) -> int:
    return install.uninstall(layout)


def cmd_completion(_layout: Layout, _pins: Pins, args: argparse.Namespace) -> int:
    print(completion.SCRIPTS[args.shell], end="")
    return 0


def _simple(action: Callable[[Layout, Pins], object]) -> Callable[[Layout, Pins, argparse.Namespace], int]:
    return lambda layout, pins, _args: action(layout, pins) or 0  # type: ignore[return-value]


HANDLERS: dict[str | None, Callable[[Layout, Pins, argparse.Namespace], int]] = {
    None: cmd_guide,
    "install": cmd_install,
    "uninstall": cmd_uninstall,
    "completion": cmd_completion,
    "code": cmd_code,
    "models": cmd_models,
    "use": cmd_use,
    "setup": cmd_setup,
    "verify": cmd_verify,
    "status": cmd_status,
    "pull": cmd_pull,
    "check": cmd_check,
    "bench": cmd_bench,
    "serve": _simple(ollama.serve),
    "start": _simple(ollama.start),
    "stop": _simple(ollama.stop),
}


def main(root: Path, argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    layout = Layout(root)
    pins = Pins.load(layout.pins_file)
    # Pass-through commands: hand every following argument (including --options) to the tool.
    if argv and argv[0] == "interpreter":
        agentconfig.write_catalog(layout, pins)
        return run_tool(layout.interpreter_exe(), argv[1:], interpreter_env(layout, pins))
    if argv and argv[0] == "pi":
        return run_pi(layout, pins, argv[1:])
    if argv and argv[0] == "ollama":
        return run_tool(layout.ollama_exe(), argv[1:], ollama.server_env(layout, pins))
    if argv and argv[0] == "__complete":  # called by the shell on Tab: `__complete INDEX WORDS...`
        found = completion.complete(build_parser(), argv[2:], int(argv[1]), lambda: agentconfig.known_models(layout))
        print("\n".join(found))
        return 0
    args = build_parser().parse_args(argv)
    return HANDLERS[args.command](layout, pins, args)


def run() -> int:
    """Entry point of the installed `satyrn` command (an editable install of a clone)."""
    root = Path(__file__).resolve().parents[2]
    if not (root / "pins.toml").is_file():
        raise SystemExit(
            "satyrn must be installed from a clone of satyrn-getting-started with `python3.14 satyrn.py install`"
        )
    return main(root)

"""satyrn-codegen: describe the code you want in plain English; a local Satyrn model writes it."""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import satyrn_agent
from ds4py import Ds4pyError, ThinkMode

from .agent import CodegenAgent
from .tools import Workspace

if TYPE_CHECKING:
    from collections.abc import Callable

THINK = {
    "none": ThinkMode.NONE,
    "low": ThinkMode.LOW,
    "medium": ThinkMode.MEDIUM,
    "high": ThinkMode.HIGH,
    "max": ThinkMode.MAX,
}
EPILOG = """\
examples:
  satyrn-codegen -m ~/models/Qwen3.8-27B-Q4_K_M.gguf --lib out/libds4.dylib \\
      "add a CLI to fizzbuzz.py with argparse and a test"
  satyrn-codegen -i -C ./myproject                            # interactive session

environment: SATYRN_MODEL, SATYRN_DRAFTER, SATYRN_LIB, SATYRN_CONFIG provide defaults
for --model, --drafter, --lib and --config.
"""


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="satyrn-codegen", description=__doc__, epilog=EPILOG, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("prompt", nargs="*", help="what to build; omit (or use -i) for an interactive session")
    p.add_argument("-i", "--interactive", action="store_true", help="keep chatting after the first prompt")
    p.add_argument(
        "-C", "--workdir", type=Path, default=Path.cwd(), help="workspace the model may read/write (default: cwd)"
    )

    m = p.add_argument_group("model")
    m.add_argument(
        "-m", "--model", default=os.environ.get("SATYRN_MODEL"), help="target GGUF (e.g. Qwen3.8-27B-Q4_K_M.gguf)"
    )
    m.add_argument(
        "--drafter", default=os.environ.get("SATYRN_DRAFTER"), help="DFlash drafter GGUF for speculative decoding"
    )
    m.add_argument(
        "--lib", default=os.environ.get("SATYRN_LIB"), help="patched libds4 (.dylib/.so) built via satyrn-agent"
    )
    m.add_argument(
        "--config",
        default=os.environ.get("SATYRN_CONFIG"),
        help="JSON file matching satyrn-agent/schemas/satyrn-config.schema.json",
    )
    m.add_argument("--dflash", choices=["auto", "on", "off"], help="speculative decoding policy (overrides config)")
    m.add_argument("--backend", choices=["metal", "cuda", "rocm", "cpu"], help="require a specific backend")
    m.add_argument("--think", choices=list(THINK), default="high", help="reasoning effort (default: high)")
    m.add_argument("--ctx", type=int, default=32_768, help="context window in tokens (default: 32768)")
    m.add_argument("--temperature", type=float, help="sampling temperature override")
    m.add_argument("--seed", type=int, help="RNG seed for reproducible output")

    r = p.add_argument_group("agent")
    r.add_argument("--max-tokens", type=int, default=8192, help="max tokens per model round (default: 8192)")
    r.add_argument("--max-steps", type=int, default=25, help="max tool-call rounds per request (default: 25)")
    r.add_argument("-y", "--yes", action="store_true", help="apply file changes and run commands without asking")
    r.add_argument("--no-commands", action="store_true", help="never let the model run shell commands")
    r.add_argument("--show-thinking", action="store_true", help="stream the model's reasoning to stderr")
    return p


def load_config(args: argparse.Namespace) -> satyrn_agent.SatyrnConfig:
    data: dict[str, object] = {}
    if args.config:
        data = json.loads(Path(args.config).expanduser().read_text())
    config = satyrn_agent.config_from_dict(data)
    changes: dict[str, object] = {}
    if args.drafter:
        changes["drafter_path"] = Path(args.drafter).expanduser()
    if args.dflash:
        changes["dflash"] = satyrn_agent.DFlashMode(args.dflash)
    if args.temperature is not None:
        changes["sampling"] = dataclasses.replace(config.sampling, temperature=args.temperature)
    return dataclasses.replace(config, **changes) if changes else config


def make_confirm(*, auto_yes: bool) -> Callable[[str], bool]:
    def confirm(summary: str) -> bool:
        print(summary, file=sys.stderr)
        if auto_yes:
            return True
        if not sys.stdin.isatty():
            print("(not a terminal and --yes not given: rejected)", file=sys.stderr)
            return False
        try:
            return input("apply? [y/N] ").strip().lower() in {"y", "yes"}
        except EOFError:
            return False

    return confirm


def repl(agent: CodegenAgent) -> None:
    print("satyrn-codegen interactive session. Describe what to build; /exit to quit.", file=sys.stderr)
    while True:
        try:
            line = input("\nsatyrn> ").strip()
        except EOFError, KeyboardInterrupt:
            print(file=sys.stderr)
            return
        if not line:
            continue
        if line in {"/exit", "/quit", "exit", "quit"}:
            return
        run_once(agent, line)


def run_once(agent: CodegenAgent, prompt: str) -> int:
    try:
        result = agent.ask(prompt)
    except KeyboardInterrupt:
        print("\n[interrupted]", file=sys.stderr)
        return 130
    if result.files_changed:
        print(f"\nfiles changed: {', '.join(result.files_changed)}", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.model:
        print("error: pass --model PATH (or set SATYRN_MODEL)", file=sys.stderr)
        return 2
    model = Path(args.model).expanduser()
    if not model.is_file():
        print(f"error: model file not found: {model}", file=sys.stderr)
        return 2
    try:
        config = load_config(args)
    except (OSError, ValueError, TypeError) as error:
        print(f"error: invalid config: {error}", file=sys.stderr)
        return 2

    open_kwargs: dict[str, object] = {
        "config": config,
        "ctx": args.ctx,
        "think": THINK[args.think],
        "seed": args.seed,
        "backend": args.backend,
    }
    open_kwargs["lib"] = Path(args.lib).expanduser() if args.lib else None

    workspace = Workspace(args.workdir, confirm=make_confirm(auto_yes=args.yes), allow_commands=not args.no_commands)
    prompt = " ".join(args.prompt).strip()
    try:
        with satyrn_agent.open(model, **open_kwargs) as engine:  # type: ignore[arg-type]
            session = engine.session()
            mode = "dflash" if engine.dflash_metrics is not None else "serial"
            print(f"[satyrn] model={model} decode={mode} workspace={workspace.root}", file=sys.stderr)
            agent = CodegenAgent(
                session,
                workspace,
                max_tokens=args.max_tokens,
                max_steps=args.max_steps,
                show_thinking=args.show_thinking,
            )
            status = run_once(agent, prompt) if prompt else 0
            if args.interactive or not prompt:
                repl(agent)
            if (metrics := engine.dflash_metrics) is not None:
                print(f"[satyrn] dflash: {metrics}", file=sys.stderr)
            return status
    except (satyrn_agent.SatyrnError, Ds4pyError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

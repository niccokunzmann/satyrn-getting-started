"""satyrn train: the root command for training a model on a dataset (docs/train.md).

`satyrn train small` runs a small LoRA training on the CPU (runners/train_small.py) in a venv of
its own, with a pinned model; its tools live in .runtime/train/, its runs in training/<run>/.
Real training needs a rented NVIDIA GPU and is not part of satyrn yet.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from . import fetch, pyenv
from .layout import IS_WINDOWS, Asset, Layout, Pins

RUNNER = Path(__file__).parent / "runners" / "train_small.py"
DEFAULT_DATA = "datasets/python3.15/cpt.jsonl"
STEPS, LR, RANK, SEQ_LEN, SEED = 200, 1e-4, 16, 512, 3407  # seed and lr as in satyrn-models
ACTIVE = {"preparing", "validating", "training"}
# PyTorch's threads wait for each other at every step, so one busy CPU holds all of them up. Measured
# on 13 CPUs (docs/train.md): 13 threads 17.9 s/step, 12: 9.8, 8: 9.2, 6: 10.1, 4: 13.8.
THREADS = max(1, (os.cpu_count() or 3) * 2 // 3)
TUTORIAL = "https://github.com/satyrn-ai/satyrn-models/blob/main/docs/trainer_tutorial.md"


def hms(seconds: float) -> str:
    seconds = round(seconds)
    return f"{seconds // 3600}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"


def model_dir(layout: Layout, pins: Pins) -> Path:
    return layout.train_dir / "models" / pins.data["train"]["model"]["name"].split("/")[-1]


def prepare(layout: Layout, pins: Pins) -> tuple[Path, Path]:
    """The venv's Python and the model folder, made or checked."""
    print("Python packages (PyTorch for the CPU, transformers, peft):")
    requirements = layout.root / "config" / "train" / "requirements.txt"
    python = pyenv.ensure(layout.train_dir / "venv", requirements, layout.train_dir)
    model = pins.data["train"]["model"]
    target = model_dir(layout, pins)
    print(f"model {model['name']} at revision {model['revision'][:12]}:")
    base = f"https://huggingface.co/{model['name']}/resolve/{model['revision']}"
    for file, sha256 in model["files"].items():
        asset = Asset(target.name, model["revision"], f"{base}/{file}", file, sha256)
        fetch.download(asset, target, name=file)
    return python, target


def env(layout: Layout) -> dict[str, str]:
    """No network and nothing in ~/.cache: the model is already in .runtime/train."""
    return pyenv.env(layout.train_dir) | {
        "HF_HOME": str(layout.train_dir / "hf-home"),
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "HF_HUB_DISABLE_TELEMETRY": "1",
        "TOKENIZERS_PARALLELISM": "false",
    }


def small(layout: Layout, pins: Pins, args: argparse.Namespace) -> int:
    data = (args.data or layout.root / DEFAULT_DATA).resolve()
    if not data.is_file():
        raise SystemExit(f"dataset {data} not found; create it first: satyrn data cpython")
    if args.steps < 1:
        raise SystemExit("--steps must be at least 1")
    run = layout.training / (args.name or f"{datetime.now().astimezone():%Y%m%d-%H%M}-small")
    if run.exists() and any(run.iterdir()):
        raise SystemExit(f"{run} exists already; choose another --name")
    python, model = prepare(layout, pins)
    print(f"training (watch it from another terminal: satyrn train status {run.name}):")
    command = [str(python), "-P", str(RUNNER), "--model", str(model), "--data", str(data), "--out", str(run)]
    command += ["--steps", str(args.steps), "--lr", str(args.lr), "--rank", str(args.rank)]
    command += ["--seq-len", str(SEQ_LEN), "--seed", str(SEED), "--threads", str(args.threads)]
    sys.stdout.flush()  # our lines before the trainer's, also in a log file
    process = subprocess.Popen(command, env=env(layout))
    try:
        return process.wait()
    except KeyboardInterrupt:  # the trainer got Ctrl+C too and records "stopped"
        return process.wait()


def is_alive(pid: int) -> bool:
    if IS_WINDOWS:
        return True  # no cheap check without extra packages; the state file says the rest
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def describe(name: str, state: dict, *, alive: bool) -> list[str]:
    """Lines for `satyrn train status`."""
    phase = state.get("state", "unknown")
    if phase in ACTIVE and not alive:
        phase = "ended unexpectedly (its process is gone)"
    lines = [f"run {name}: {phase}"]
    steps, step = state.get("steps"), state.get("step")
    if step is not None and steps:
        loss = f", loss {state['loss']:.3f}" if "loss" in state else ""
        speed = f", {state['seconds_per_step']:.1f} s/step" if "seconds_per_step" in state else ""
        lines.append(f"  step {step}/{steps} ({100 * step // steps}%){loss}{speed}")
    if "elapsed" in state:
        remaining = f", remaining ~{hms(state['remaining'])}" if phase in ACTIVE and "remaining" in state else ""
        lines.append(f"  elapsed {hms(state['elapsed'])}{remaining}")
    if "eval_loss_start" in state:
        lines.append(f"  validation loss {state['eval_loss_start']:.3f} at the start, {state['eval_loss']:.3f} latest")
    if state.get("error"):
        lines.append(f"  error: {state['error']}")
    if state.get("adapter"):
        lines.append(f"  adapter: {state['adapter']}")
    return lines


def runs(layout: Layout) -> list[Path]:
    return sorted(p.parent for p in layout.training.glob("*/status.json"))


def status(layout: Layout, name: str | None) -> int:
    found = runs(layout)
    if not found:
        print("no training runs yet; start one: satyrn train small")
        return 1
    run = layout.training / name if name else max(found, key=lambda p: (p / "status.json").stat().st_mtime)
    if not (run / "status.json").is_file():
        raise SystemExit(f"no run {run.name}; runs: {', '.join(p.name for p in found)}")
    state = json.loads((run / "status.json").read_text(encoding="utf-8"))
    print("\n".join(describe(run.name, state, alive=is_alive(int(state.get("pid", 0))))))
    print(f"  log: {(run / 'train.log').relative_to(layout.root)}")
    return 1 if state.get("state") in {"failed", "stopped"} else 0


def show(layout: Layout) -> int:
    print("Train a model on a dataset (docs: train.md):\n")
    print("  satyrn train small     a small LoRA training on this computer's CPU: Qwen2.5-0.5B on")
    print(f"                         {DEFAULT_DATA}; checks that dataset and training work")
    print("  satyrn train status    progress of the newest run\n")
    print("Real training needs a rented NVIDIA GPU and is not part of satyrn yet; until then use")
    print(f"satyrn-models' tutorial: {TUTORIAL}")
    if not (layout.root / DEFAULT_DATA).is_file():
        print("\nFirst create the dataset: satyrn data cpython")
    return 0

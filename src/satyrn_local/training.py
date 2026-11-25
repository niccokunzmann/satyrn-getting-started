"""satyrn train: the root command for training a model on a dataset (docs/train.md).

`satyrn train small` runs a small LoRA training on the CPU (runners/train_small.py) in a venv of
its own, with a pinned model; its tools live in .runtime/train/, its runs in training/<run>/.
`satyrn train export` merges a run's adapter into the model and imports it into the project's
Ollama as ``trained:<run>``, so that `satyrn code -m trained:<run>` can use it.
Real training needs a rented NVIDIA GPU and is not part of satyrn yet.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from . import fetch, gitpin, ollama, pyenv, settings
from .layout import IS_WINDOWS, Asset, Layout, Pins

RUNNER = Path(__file__).parent / "runners" / "train_small.py"
EXPORTER = Path(__file__).parent / "runners" / "export_model.py"
PREFIX = "trained:"  # Ollama name of a run's model: trained:<run>
MODEL_FILE = "model.json"  # in training/<run>/ once the run's model is in Ollama
# The Qwen2.5 defaults from the model's generation_config.json.
PARAMETERS = {"temperature": 0.7, "top_p": 0.8, "top_k": 20, "repeat_penalty": 1.1}
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
        code = process.wait()
    except KeyboardInterrupt:  # the trainer got Ctrl+C too and records "stopped"
        return process.wait()
    if code != 0:
        return code
    try:
        layout.ollama_exe()
    except SystemExit:
        print(f"to use it with satyrn code: satyrn setup, then satyrn train export {run.name}")
        return 0
    return export(layout, pins, run.name)


def model_name(run: str) -> str:
    """The run's model in Ollama; a tag allows letters, digits, `_`, `.` and `-`."""
    return PREFIX + re.sub(r"[^A-Za-z0-9_.-]", "-", run)[:128]


def modelfile(layout: Layout, weights: Path) -> str:
    template = (layout.root / "config" / "train" / "qwen2.5.template").read_text(encoding="utf-8")
    lines = [f"FROM {weights}", f'TEMPLATE """{template}"""']
    lines += [f'PARAMETER stop "{stop}"' for stop in ("<|im_start|>", "<|im_end|>")]
    lines += [f"PARAMETER {key} {value}" for key, value in PARAMETERS.items()]
    return "\n".join(lines) + "\n"


def export(layout: Layout, pins: Pins, name: str | None = None) -> int:
    """Merge the run's adapter into the model and import the result into Ollama as trained:<run>."""
    with_adapter = [run for run in runs(layout) if (run / "adapter" / "adapter_config.json").is_file()]
    if name:
        run = layout.training / name
        if run not in with_adapter:
            names = ", ".join(r.name for r in with_adapter) or "-"
            raise SystemExit(f"run {name} has no adapter; runs with one: {names}")
    elif with_adapter:
        run = max(with_adapter, key=lambda p: (p / "status.json").stat().st_mtime)
    else:
        raise SystemExit("no training run with an adapter yet; train one: satyrn train small")
    state = json.loads((run / "status.json").read_text(encoding="utf-8"))
    target = model_name(run.name)
    print(f"model of run {run.name} for satyrn code, as {target}:")
    if state.get("state") != "finished":
        print(f"  note     the run is {state.get('state')}; its adapter is from the last validation")
    python, base = prepare(layout, pins)
    convert = pins.data["train"]["convert"]
    print("llama.cpp's converter (git commit from pins.toml):")
    converter = layout.train_dir / "llama.cpp"
    gitpin.checkout(convert["repo"], convert["commit"], converter, convert["paths"])
    work = layout.train_dir / "export" / run.name
    gguf = work / "model.gguf"
    print("export:")
    command = [str(python), "-P", str(EXPORTER), "--model", str(base), "--adapter", str(run / "adapter")]
    sys.stdout.flush()
    subprocess.run([*command, "--out", str(work / "weights")], env=env(layout), check=True)
    with (work / "convert.log").open("w", encoding="utf-8") as log:
        command = [str(python), "-P", str(converter / "convert_hf_to_gguf.py"), "--outtype", "f16"]
        done = subprocess.run(
            [*command, "--outfile", str(gguf), str(work / "weights")],
            env=env(layout) | {"PYTHONPATH": str(converter)},  # its package conversion/ is next to it
            stdout=log,
            stderr=log,
            check=False,
        )
    if done.returncode != 0:
        raise SystemExit(f"the conversion to GGUF failed; see {work / 'convert.log'}")
    shutil.rmtree(work / "weights")
    print(f"  gguf     {gguf.stat().st_size / 1e9:.1f} GB, 16 bit")
    (work / "Modelfile").write_text(modelfile(layout, gguf), encoding="utf-8")
    print("  import   into Ollama")
    sys.stdout.flush()
    with ollama.running(layout, pins):
        create = [str(layout.ollama_exe()), "create", target, "-f", str(work / "Modelfile")]
        subprocess.run(create, env=ollama.server_env(layout, pins), check=True)
        capabilities = ollama.api(pins, "/api/show", {"model": target}, timeout=60).get("capabilities", [])
        digest = ollama.model_digest(pins, target)
    shutil.rmtree(work)  # Ollama has its own copy now
    if "tools" not in capabilities:
        raise SystemExit(f"Ollama does not offer tool calls for {target} ({capabilities}); satyrn code needs them")
    record = {"model": target, "digest": digest, "state": state.get("state"), "step": state.get("step")}
    (run / MODEL_FILE).write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(f"  ready    {target} ({', '.join(capabilities)})")
    print(f"\nuse it once:        satyrn code DIR -m {target}")
    print(f"make it the default: satyrn use {target}")
    return 0


def trained_models(layout: Layout) -> dict[str, dict]:
    """The runs' models that are in Ollama, with what `satyrn models` and the agents need."""
    found = {}
    for record_file in sorted(layout.training.glob(f"*/{MODEL_FILE}")):
        try:
            record = json.loads(record_file.read_text(encoding="utf-8"))
        except OSError, ValueError:
            continue
        name = record.get("model", "")
        if name.startswith(PREFIX) and settings.is_pulled(layout, name):
            found[name] = {
                "description": f"Qwen2.5-0.5B-Instruct trained with satyrn train (run {record_file.parent.name})",
                "kind": "dense, 0.5B parameters, trained here",
                "download_gb": 0,
                "memory_gb": 1.5,
                "dense": False,
                "trained": True,
            }
    return found


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
    if (run / MODEL_FILE).is_file():
        model = json.loads((run / MODEL_FILE).read_text(encoding="utf-8"))["model"]
        print(f"  model: {model}, for satyrn code -m {model}")
    return 1 if state.get("state") in {"failed", "stopped"} else 0


def show(layout: Layout) -> int:
    print("Train a model on a dataset (docs: train.md):\n")
    print("  satyrn train small     a small LoRA training on this computer's CPU: Qwen2.5-0.5B on")
    print(f"                         {DEFAULT_DATA}; checks that dataset and training work")
    print("  satyrn train status    progress of the newest run")
    print("  satyrn train export    make a run's model usable: satyrn code -m trained:<run>\n")
    print("Real training needs a rented NVIDIA GPU and is not part of satyrn yet; until then use")
    print(f"satyrn-models' tutorial: {TUTORIAL}")
    if not (layout.root / DEFAULT_DATA).is_file():
        print("\nFirst create the dataset: satyrn data cpython")
    return 0

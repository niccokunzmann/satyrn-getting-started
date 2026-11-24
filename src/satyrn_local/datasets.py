"""satyrn data: create training datasets from pinned sources, and check them (docs/data.md).

Separate from the coding setup: its own Python packages, git checkouts and temporary files in
.runtime/data/; the datasets go to datasets/, with the same paths as in satyrn-models.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from . import gitpin, pyenv
from .fetch import sha256_file
from .layout import Layout, Pins

RUNNER = Path(__file__).parent / "runners" / "build_cpython_data.py"
DATASETS = {
    "cpython": "what is new in a Python version: the CPython docs that changed, its PEPs and What's New "
    "(continued pretraining, as in satyrn-models)",
}
VERSIONS = ("3.15", "3.14")
STEPS = ("collect", "inputs", "cpt")


def output(layout: Layout, version: str) -> Path:
    return layout.datasets / f"python{version}" / "cpt.jsonl"


def pinned(pins: Pins, version: str) -> dict:
    return pins.data["data"]["cpython"][version]


def prepare(layout: Layout, pins: Pins) -> tuple[Path, dict[str, Path]]:
    """The venv's Python and the pinned checkouts, made or checked."""
    print("Python packages:")
    requirements = layout.root / "config" / "data" / "requirements.txt"
    python = pyenv.ensure(layout.data_dir / "venv", requirements, layout.data_dir)
    print("sources (git commits from pins.toml):")
    sources = {}
    for name, source in pins.data["data"]["sources"].items():
        folder = layout.data_dir / "sources" / name
        gitpin.checkout(source["repo"], source["commit"], folder, source["paths"])
        sources[name] = folder
    return python, sources


def count_rows(path: Path) -> int:
    with path.open("rb") as handle:
        return sum(1 for _ in handle)


def build_cpython(layout: Layout, pins: Pins, version: str) -> int:
    target = output(layout, version)
    part = layout.data_dir / "build" / f"python{version}" / target.name  # moved to target once verified
    log = layout.data_dir / "logs" / f"cpython-{version}.log"
    print(f"dataset cpython for Python {version} -> {target.relative_to(layout.root)}")
    python, sources = prepare(layout, pins)
    print(f"building (details: {log.relative_to(layout.root)}):")
    env = pyenv.env(layout.data_dir) | {"PYTHONPATH": str(sources["satyrn-models"] / "corpus_builder" / "src")}
    # Sphinx's cache goes to the temporary folder: one per version, so builds can run side by side.
    tmp = layout.data_dir / "tmp" / f"python{version}"
    tmp.mkdir(parents=True, exist_ok=True)
    env |= {"TMPDIR": str(tmp), "TEMP": str(tmp), "TMP": str(tmp)}
    command = [str(python), "-P", str(RUNNER), "--version", version, "--output", str(part), "--log", str(log)]
    for name in ("satyrn-models", "cpython", "peps"):
        command += [f"--{name}", str(sources[name])]
    sys.stdout.flush()  # our lines before the runner's, also in a log file
    for step in STEPS:  # one process per step, see the runner's docstring
        if subprocess.run([*command, "--step", step], env=env, check=False).returncode:
            print(f"FAIL: building the dataset failed; see {log}")
            return 1
    return check(layout, pins, version, part, target)


def check(layout: Layout, pins: Pins, version: str, part: Path, target: Path) -> int:
    digest, rows = sha256_file(part), count_rows(part)
    print(f"{target.relative_to(layout.root)}: {rows} rows, {part.stat().st_size / 1e6:.1f} MB")
    expected = pinned(pins, version)["sha256"]
    if digest == expected:
        target.parent.mkdir(parents=True, exist_ok=True)
        part.replace(target)
        print(f"reproduced: identical to the pinned build (sha256 {digest[:8]}…)")
        return 0
    kept = part.relative_to(layout.root)
    if not expected:
        print(f"no checksum pinned for Python {version} yet; kept in {kept}. To pin this build, set")
    else:
        print(f"FAIL: sha256 {digest} differs from the pinned {expected}; kept in {kept}.")
        print("Something in the chain changed (see docs/data.md#how-it-is-made). If that is intended, set")
    print(f'  [data.cpython] "{version}" = {{ sha256 = "{digest}", rows = {rows} }}   in pins.toml')
    return 1


def show(layout: Layout, pins: Pins) -> int:
    print("datasets satyrn data can create:\n")
    for name, what in DATASETS.items():
        print(f"  {name}: {what}")
        for version in VERSIONS:
            target = output(layout, version)
            if not target.is_file():
                state = "not created yet"
            elif sha256_file(target) == pinned(pins, version)["sha256"]:
                state = f"created, {count_rows(target)} rows, matches its pin"
            else:
                state = "created, but differs from its pin"
            flag = "" if version == VERSIONS[0] else f" --python {version}"
            print(f"    satyrn data {name}{flag:14s} {target.relative_to(layout.root)}: {state}")
    print("\nThe datasets are the input of training: satyrn train")
    return 0

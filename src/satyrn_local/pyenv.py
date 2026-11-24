"""Python environments with hash-pinned packages, for `satyrn data` and `satyrn train`.

Each environment is a venv made with the Python that runs satyrn. Its packages come from a
requirements file in which every package has a version and SHA-256 (`pip --require-hashes`), and
only wheels are installed, so nothing is built from source. A stamp records the requirements'
SHA-256 and the Python version; when either changes, the venv is made again.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from .fetch import sha256_file
from .layout import IS_WINDOWS

STAMP = ".satyrn-requirements"


def python(venv: Path) -> Path:
    return venv / ("Scripts/python.exe" if IS_WINDOWS else "bin/python")


def env(area: Path) -> dict[str, str]:
    """Environment for pip and the tools: temporary files and caches stay inside ``area``."""
    tmp = area / "tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    clean = {k: v for k, v in os.environ.items() if not k.startswith(("PYTHON", "PIP_", "VIRTUAL_ENV"))}
    return clean | {
        "TMPDIR": str(tmp),
        "TEMP": str(tmp),
        "TMP": str(tmp),
        "PIP_CACHE_DIR": str(area / "pip-cache"),
        "PIP_DISABLE_PIP_VERSION_CHECK": "1",
        "PIP_NO_INPUT": "1",
        "PYTHONUTF8": "1",
    }


def _wanted(requirements: Path) -> str:
    return f"{sha256_file(requirements)} python {sys.version.split()[0]}\n"


def is_ready(venv: Path, requirements: Path) -> bool:
    stamp = venv / STAMP
    return python(venv).is_file() and stamp.is_file() and stamp.read_text() == _wanted(requirements)


def ensure(venv: Path, requirements: Path, area: Path) -> Path:
    """Return the venv's Python, creating the venv from ``requirements`` if it is missing or stale."""
    if is_ready(venv, requirements):
        print(f"  present  {venv} ({requirements.name} unchanged)")
        return python(venv)
    if venv.exists():
        shutil.rmtree(venv)
    print(f"  create   {venv}")
    subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True, env=env(area))
    print(f"  install  {requirements} (every package checked against its SHA-256)")
    subprocess.run(
        [
            str(python(venv)),
            *("-m", "pip", "install", "--quiet", "--require-hashes", "--no-deps", "--only-binary", ":all:"),
            *("-r", str(requirements)),
        ],
        check=True,
        env=env(area),
    )
    (venv / STAMP).write_text(_wanted(requirements))
    return python(venv)

"""Live acceptance test for satyrn-codegen on Satyrn's own engine (ds4 + Metal).

The real model must write a working square-root program. It needs an Apple Silicon Mac
(dense qwen35 runs on the Metal graph only):

    export SATYRN_MODEL=~/models/Qwen3.8-27B-Q4_K_M.gguf
    export SATYRN_DRAFTER=~/models/dflash-Qwen3.8-27B-Q4_0.gguf   # optional
    export SATYRN_LIB=~/.ds4py/lib/libds4.dylib                   # optional
    uv run pytest -m live tests/test_live_sqrt.py

For the Ollama + Open Interpreter path on Linux/Windows see tests/test_local_model.py.
"""

from __future__ import annotations

import math
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.live

PROMPT = (
    "Create a Python program named sqrt.py that takes a number as its first command-line "
    "argument and prints the square root of it."
)


@pytest.fixture
def model() -> Path:
    value = os.environ.get("SATYRN_MODEL")
    if not value:
        pytest.skip("SATYRN_MODEL is not set; this test needs a real GGUF on an Apple Silicon Mac")
    path = Path(value).expanduser()
    if not path.is_file():
        pytest.fail(f"SATYRN_MODEL points at a missing file: {path}")
    return path


def test_model_writes_working_sqrt_program(model: Path, tmp_path: Path) -> None:
    cli = [sys.executable, "-m", "satyrn_codegen", "--yes", "--no-commands", "--seed", "1", "-C", str(tmp_path)]
    run = subprocess.run(
        [*cli, "--model", str(model), PROMPT], capture_output=True, text=True, timeout=1800, check=False
    )
    assert run.returncode == 0, run.stderr

    program = tmp_path / "sqrt.py"
    candidates = [program] if program.is_file() else sorted(tmp_path.rglob("*.py"))
    assert candidates, f"the model wrote no Python file.\nstdout:\n{run.stdout}\nstderr:\n{run.stderr}"

    for number, expected in [("16", 4.0), ("2", math.sqrt(2)), ("0.25", 0.5)]:
        result = subprocess.run(
            [sys.executable, str(candidates[0]), number],
            input=f"{number}\n",
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        printed = [float(tok) for tok in result.stdout.replace(":", " ").split() if _is_float(tok)]
        assert any(math.isclose(value, expected, rel_tol=1e-6) for value in printed), (
            f"sqrt({number}) should print {expected}; got {result.stdout!r}"
        )


def _is_float(text: str) -> bool:
    try:
        float(text)
    except ValueError:
        return False
    return True

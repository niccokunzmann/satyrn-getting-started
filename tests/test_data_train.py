"""satyrn data and satyrn train: pins, hashed packages, git checkouts, run status. No mocks.

The full runs (CPython docs, PyTorch) need the network and minutes to hours; they are covered by
running the commands themselves (docs/data.md, docs/train.md). Here: everything around them, with
real git repositories, real files and the real command line.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from satyrn_local import completion, datasets, gitpin, training  # noqa: E402
from satyrn_local.cli import build_parser  # noqa: E402
from satyrn_local.layout import Pins  # noqa: E402

PINS = Pins.load(ROOT / "pins.toml")


def satyrn(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(root / "satyrn.py"), *args], capture_output=True, text=True, check=False, timeout=60
    )


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "satyrn-getting-started"
    shutil.copytree(
        ROOT,
        root,
        ignore=shutil.ignore_patterns(
            ".runtime", ".venv", "build", ".git", "__pycache__", ".prompts", "datasets", "training"
        ),
    )
    return root


# --- pins -------------------------------------------------------------------------------------
def test_every_source_is_a_git_commit() -> None:
    for name, source in PINS.data["data"]["sources"].items():
        assert re.fullmatch(r"[0-9a-f]{40}", source["commit"]), name
        assert source["repo"].startswith("https://")
        assert source["paths"]


def test_every_dataset_has_a_pinned_checksum() -> None:
    for version in datasets.VERSIONS:
        pin = datasets.pinned(PINS, version)
        assert re.fullmatch(r"[0-9a-f]{64}", pin["sha256"]), version
        assert pin["rows"] > 100


def test_every_model_file_has_a_checksum() -> None:
    model = PINS.data["train"]["model"]
    assert re.fullmatch(r"[0-9a-f]{40}", model["revision"])
    assert {"config.json", "model.safetensors", "tokenizer.json"} <= set(model["files"])
    for file, sha256 in model["files"].items():
        assert re.fullmatch(r"[0-9a-f]{64}", sha256), file


@pytest.mark.parametrize("area", ["data", "train"])
def test_every_package_is_pinned_with_a_hash(area: str) -> None:
    lines = (ROOT / "config" / area / "requirements.txt").read_text().splitlines()
    text = "\n".join(line for line in lines if line and not line.startswith(("#", "--index-url", "--extra-index-url")))
    for requirement in re.split(r"\n(?=[a-z])", text):
        if requirement.strip():
            assert "==" in requirement.split()[0], requirement
            assert "--hash=sha256:" in requirement, requirement


# --- git checkouts at a commit ----------------------------------------------------------------
def git(folder: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(folder), *args], check=True, capture_output=True, text=True).stdout.strip()


def test_checkout_gets_only_the_pinned_commit_and_paths(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    upstream = tmp_path / "upstream"
    (upstream / "Doc").mkdir(parents=True)
    (upstream / "Lib").mkdir()
    (upstream / "Doc" / "index.rst").write_text("pinned\n")
    (upstream / "Lib" / "big.py").write_text("not needed\n")
    git(upstream, "init", "-q")
    git(upstream, "add", ".")
    git(upstream, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-qm", "one")
    pinned = git(upstream, "rev-parse", "HEAD")
    (upstream / "Doc" / "index.rst").write_text("newer\n")
    git(upstream, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-qam", "two")

    folder = tmp_path / "checkout"
    gitpin.checkout(upstream.as_uri(), pinned, folder, ["/Doc/"])
    assert gitpin.head(folder) == pinned
    assert (folder / "Doc" / "index.rst").read_text() == "pinned\n"
    assert not (folder / "Lib").exists()
    gitpin.checkout(upstream.as_uri(), pinned, folder, ["/Doc/"])
    assert "present" in capsys.readouterr().out


# --- satyrn data ------------------------------------------------------------------------------
def test_data_lists_the_datasets(project: Path) -> None:
    out = satyrn(project, "data")
    assert out.returncode == 0
    assert "satyrn data cpython " in out.stdout
    assert "satyrn data cpython --python 3.14" in out.stdout
    assert "datasets/python3.15/cpt.jsonl: not created yet" in out.stdout


def test_a_different_result_fails_and_is_kept(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from satyrn_local.layout import Layout

    layout = Layout(project)
    target = datasets.output(layout, "3.15")
    part = project / ".runtime" / "data" / "build" / "python3.15" / "cpt.jsonl"
    part.parent.mkdir(parents=True)
    part.write_text('{"filename": "x.rst", "text": "not the pinned build"}\n')
    assert datasets.check(layout, PINS, "3.15", part, target) == 1
    assert part.is_file()
    assert not target.exists()
    assert "differs from the pinned" in capsys.readouterr().out


# --- satyrn train -----------------------------------------------------------------------------
def test_train_small_needs_the_dataset(project: Path) -> None:
    out = satyrn(project, "train", "small")
    assert out.returncode != 0
    assert "create it first: satyrn data cpython" in out.stderr


def test_train_status_without_runs(project: Path) -> None:
    out = satyrn(project, "train", "status")
    assert out.returncode == 1
    assert "no training runs yet" in out.stdout


RUNNING = {
    "state": "training",
    "steps": 200,
    "step": 40,
    "loss": 1.9234,
    "seconds_per_step": 4.1,
    "elapsed": 164,
    "remaining": 656,
    "eval_loss_start": 2.41,
    "eval_loss": 2.41,
}


def test_status_of_a_running_training() -> None:
    lines = training.describe("run1", RUNNING, alive=True)
    assert lines[0] == "run run1: training"
    assert "step 40/200 (20%), loss 1.923, 4.1 s/step" in lines[1]
    assert "elapsed 0:02:44, remaining ~0:10:56" in lines[2]


def test_status_when_the_process_is_gone() -> None:
    assert "ended unexpectedly" in training.describe("run1", RUNNING, alive=False)[0]


def test_status_of_a_failed_training() -> None:
    failed = RUNNING | {"state": "failed", "error": "FloatingPointError: the loss at step 41 is nan"}
    lines = training.describe("run1", failed, alive=False)
    assert lines[0] == "run run1: failed"
    assert not any("remaining" in line for line in lines)
    assert any("error: FloatingPointError" in line for line in lines)


def test_status_reads_the_newest_run(project: Path) -> None:
    run = project / "training" / "20261124-2130-small"
    run.mkdir(parents=True)
    (run / "status.json").write_text('{"state": "finished", "steps": 2, "step": 2, "adapter": "a"}')
    out = satyrn(project, "train", "status")
    assert out.returncode == 0
    assert "run 20261124-2130-small: finished" in out.stdout


# --- tab completion ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("words", "index", "expected"),
    [
        (["satyrn", "da"], 1, ["data"]),
        (["satyrn", "data", ""], 2, ["cpython"]),
        (["satyrn", "train", "s"], 2, ["small", "status"]),
        (["satyrn", "data", "cpython", "--python", ""], 4, ["3.14", "3.15"]),
        (["satyrn", "train", "small", "--st"], 3, ["--steps"]),
    ],
)
def test_completion_of_data_and_train(words: list[str], index: int, expected: list[str]) -> None:
    assert completion.complete(build_parser(), words, index, list) == expected

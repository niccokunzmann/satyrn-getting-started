"""satyrn data and satyrn train: pins, hashed packages, git checkouts, run status. No mocks.

The full runs (CPython docs, PyTorch) need the network and minutes to hours; they are covered by
running the commands themselves (docs/data.md, docs/train.md). Here: everything around them, with
real git repositories, real files and the real command line.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from satyrn_local import agentconfig, completion, datasets, gitpin, settings, training  # noqa: E402
from satyrn_local.cli import build_parser  # noqa: E402
from satyrn_local.layout import Layout, Pins  # noqa: E402

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


# --- continuing a training --------------------------------------------------------------------
def earlier_run(project: Path, name: str, *, state: str = "finished", step: int = 200, **config: object) -> Path:
    """A run as train_small.py leaves it: config, status, metrics and the adapter's config."""
    data = project / "data.jsonl"
    data.write_text('{"text": "x"}\n')
    run = project / "training" / name
    (run / "adapter").mkdir(parents=True)
    (run / "adapter" / "adapter_config.json").write_text('{"r": 16}')
    (run / "config.json").write_text(json.dumps({"data": str(data), **config}))
    (run / "status.json").write_text(json.dumps({"state": state, "steps": 200, "step": step}))
    metrics = [{"step": 0, "eval_loss": 2.1}, {"step": 50, "eval_loss": 2.0}, {"step": 60, "loss": 1.9}]
    (run / "metrics.jsonl").write_text("".join(json.dumps(m) + "\n" for m in metrics))
    return run


def continue_args(run: str, **given: object) -> argparse.Namespace:
    return argparse.Namespace(continue_run=run, data=given.get("data"), rank=given.get("rank"))


def test_a_continued_run_starts_after_the_pieces_of_the_earlier_ones(project: Path) -> None:
    earlier_run(project, "round2", offset=200, steps_before=200)  # itself the second round
    args = continue_args("round2")
    extra = training.continuation(Layout(project), args)
    values = dict(zip(extra[::2], extra[1::2], strict=True))
    assert values["--offset"] == "400"
    assert values["--steps-before"] == "400"
    assert values["--continues"] == "round2"
    assert values["--resume"].endswith("round2/adapter")
    assert args.rank == 16
    assert args.data == project / "data.jsonl"


def test_a_stopped_run_continues_from_its_last_saved_adapter(project: Path) -> None:
    earlier_run(project, "stopped", state="stopped", step=60)
    extra = training.continuation(Layout(project), continue_args("stopped"))
    assert extra[extra.index("--offset") + 1] == "50"  # the adapter of the validation at step 50


def test_continue_refuses_other_settings_and_a_changed_dataset(project: Path) -> None:
    run = earlier_run(project, "r1", data_sha256="0" * 64)
    with pytest.raises(SystemExit, match="--rank comes from the run"):
        training.continuation(Layout(project), continue_args("r1", rank=8))
    with pytest.raises(SystemExit, match="has changed since run r1"):
        training.continuation(Layout(project), continue_args("r1"))
    shutil.rmtree(run / "adapter")
    out = satyrn(project, "train", "small", "--continue", "r1")
    assert "run r1 has no adapter to continue from" in out.stderr


def test_status_shows_which_run_is_continued() -> None:
    state = {"state": "finished", "steps": 200, "step": 200, "continues": "round1", "steps_before": 200}
    assert "  continues round1 (the model had 200 steps before)" in training.describe("round2", state, alive=False)


# --- the trained model in satyrn code ---------------------------------------------------------
def exported(project: Path, run: str) -> str:
    """A run whose model is in Ollama: its model.json and Ollama's manifest, as export leaves them."""
    folder = project / "training" / run
    folder.mkdir(parents=True)
    name = training.model_name(run)
    (folder / training.MODEL_FILE).write_text(f'{{"model": "{name}", "digest": "abc"}}')
    manifest = settings.manifests(Layout(project), name)[0]  # where Ollama 0.40's `create` writes it
    manifest.parent.mkdir(parents=True)
    manifest.write_text("{}")
    return name


def test_model_name_is_a_valid_ollama_tag() -> None:
    assert training.model_name("20261124-small") == "trained:20261124-small"
    assert training.model_name("my run/2") == "trained:my-run-2"


def test_modelfile_has_a_template_with_tool_calls(project: Path) -> None:
    text = training.modelfile(Layout(project), Path("/x/model.gguf"))
    assert text.startswith("FROM /x/model.gguf\n")
    template = text.split('TEMPLATE """', 1)[1].split('"""', 1)[0]
    assert ".Tools" in template
    assert "<tool_call>" in template
    assert ".ToolCalls" in template
    # Ollama prints a bare {{ .Function }} as a Go struct, which the model cannot read as a tool.
    assert "{{ json .Function }}" in template
    assert "{{ json .Function.Arguments }}" in template
    assert 'PARAMETER stop "<|im_end|>"' in text


def test_exported_models_are_listed_for_the_agents(project: Path) -> None:
    layout = Layout(project)
    name = exported(project, "20261124-small")
    models = agentconfig.load_models(layout)
    assert models[name]["trained"] is True
    assert models[name]["tool_output_tokens"] == models["gpt-oss:20b"]["tool_output_tokens"]  # defaults apply
    assert name not in agentconfig.known_models(layout, trained=False)  # bench: only the prepared models
    assert name in agentconfig.known_models(layout)


def test_a_model_no_longer_in_ollama_is_not_listed(project: Path) -> None:
    layout = Layout(project)
    name = exported(project, "20261124-small")
    settings.manifests(layout, name)[0].unlink()
    assert name not in agentconfig.known_models(layout)


def test_satyrn_use_and_models_accept_a_trained_model(project: Path) -> None:
    name = exported(project, "20261124-small")
    out = satyrn(project, "use", name)
    assert out.returncode == 0, out.stderr
    assert f"{name} is your default model" in out.stdout
    listing = satyrn(project, "models")
    assert re.search(rf"{re.escape(name)}\s+0 GB", listing.stdout), listing.stdout


def test_export_needs_a_run_with_an_adapter(project: Path) -> None:
    out = satyrn(project, "train", "export")
    assert out.returncode != 0
    assert "no training run with an adapter yet" in out.stderr
    run = project / "training" / "stopped-early"
    run.mkdir(parents=True)
    (run / "status.json").write_text('{"state": "stopped", "steps": 200, "step": 14}')
    out = satyrn(project, "train", "export", "stopped-early")
    assert "run stopped-early has no adapter" in out.stderr


# --- tab completion ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("words", "index", "expected"),
    [
        (["satyrn", "da"], 1, ["data"]),
        (["satyrn", "data", ""], 2, ["cpython"]),
        (["satyrn", "train", "s"], 2, ["small", "status"]),
        (["satyrn", "train", "e"], 2, ["export"]),
        (["satyrn", "data", "cpython", "--python", ""], 4, ["3.14", "3.15"]),
        (["satyrn", "train", "small", "--st"], 3, ["--steps"]),
    ],
)
def test_completion_of_data_and_train(words: list[str], index: int, expected: list[str]) -> None:
    assert completion.complete(build_parser(), words, index, list) == expected

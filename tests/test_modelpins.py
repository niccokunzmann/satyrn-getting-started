"""A model whose build differs from pins.toml: satyrn asks (or warns) instead of failing.

No mocks: the decisions use real settings files, and the terminal test asks the real Ollama
registry and answers in a real pseudo-terminal (declining, so that nothing is downloaded).
"""

from __future__ import annotations

import contextlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from satyrn_local import modelpins, ollama, settings  # noqa: E402
from satyrn_local.layout import IS_WINDOWS, Layout, Pins  # noqa: E402

MODEL = "gpt-oss:20b"
OTHER_BUILD = "0" * 64


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "satyrn-getting-started"
    shutil.copytree(
        ROOT, root, ignore=shutil.ignore_patterns(".runtime", ".venv", "build", ".git", "__pycache__", ".prompts")
    )
    return root


def test_pinned_and_unpinned_builds_are_used(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    layout, pins = Layout(project), Pins.load(project / "pins.toml")
    assert modelpins.use_digest(layout, pins, MODEL, pins.digest(MODEL), ask=False, download=True)
    assert modelpins.use_digest(layout, pins, "llama3:8b", OTHER_BUILD, ask=False, download=True)
    assert "has changed" not in capsys.readouterr().out


def test_changed_build_is_used_with_a_warning_without_a_terminal(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    layout, pins = Layout(project), Pins.load(project / "pins.toml")
    assert modelpins.use_digest(layout, pins, MODEL, OTHER_BUILD, ask=False, download=True)
    out = capsys.readouterr().out
    assert f"{MODEL} has changed since this project tested and pinned it" in out
    assert "To avoid this question" in out
    assert f'"{MODEL}" = "{OTHER_BUILD}"' in out
    assert settings.accepted_digest(layout, MODEL) is None, "only an explicit yes is remembered"


def test_accepted_build_is_not_asked_about_again(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    layout, pins = Layout(project), Pins.load(project / "pins.toml")
    settings.set_default_model(layout, "qwen3.6:35b-a3b")
    settings.accept_digest(layout, MODEL, OTHER_BUILD)
    assert settings.default_model(layout, pins) == "qwen3.6:35b-a3b", "other settings are kept"
    assert modelpins.use_digest(layout, pins, MODEL, OTHER_BUILD, ask=True, download=True)
    assert "has changed" not in capsys.readouterr().out


@pytest.mark.skipif(IS_WINDOWS, reason="needs a POSIX pseudo-terminal")
def test_pull_asks_before_downloading_a_changed_build(project: Path) -> None:
    if ollama.remote_digest(MODEL) is None:
        pytest.skip("the Ollama registry cannot be reached")
    import pty  # POSIX only

    pins_file = project / "pins.toml"
    pinned = Pins.load(pins_file).digest(MODEL)
    pins_file.write_text(pins_file.read_text().replace(pinned, OTHER_BUILD))  # as if upstream moved on
    controller, terminal = pty.openpty()
    proc = subprocess.Popen(
        [sys.executable, str(project / "satyrn.py"), "pull", MODEL], stdin=terminal, stdout=terminal, stderr=terminal
    )
    os.close(terminal)
    output = b""
    while b"[Y/n]" not in output:
        output += os.read(controller, 4096)
    os.write(controller, b"n\n")
    with contextlib.suppress(OSError):
        while chunk := os.read(controller, 4096):
            output += chunk
    assert proc.wait(timeout=60) == 1
    os.close(controller)
    text = output.decode()
    assert "has changed since this project tested and pinned it" in text
    assert "Download and use it anyway?" in text
    assert f"{MODEL} was not downloaded." in text
    assert not (project / ".runtime" / "models").exists(), "declining must not download anything"

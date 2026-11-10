"""The `satyrn` command: guide, model ratings, `use`, tab completion and installation.

Nothing is mocked: the completion tests run real bash with the real script, and the
installation test installs the command with uv into a temporary place and runs it.
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from satyrn_local import completion, modelinfo, settings  # noqa: E402
from satyrn_local.cli import build_parser  # noqa: E402
from satyrn_local.layout import IS_WINDOWS, Layout, Pins  # noqa: E402
from satyrn_local.machine import Machine  # noqa: E402

MODELS = ["gpt-oss:20b", "qwen3.6:35b-a3b", "qwen3-coder:30b", "qwen3.8:27b"]
BASH_COMPLETION = Path("/usr/share/bash-completion/bash_completion")


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """A fresh copy of the project, without .runtime/ (nothing downloaded, nothing chosen)."""
    root = tmp_path / "satyrn-getting-started"
    shutil.copytree(
        ROOT, root, ignore=shutil.ignore_patterns(".runtime", ".venv", "build", ".git", "__pycache__", ".prompts")
    )
    return root


def satyrn(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(root / "satyrn.py"), *args],
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        check=False,
        timeout=60,
    )


# --- completion -------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("words", "index", "expected"),
    [
        (["satyrn", "mo"], 1, ["models"]),
        (["satyrn", "code", "-m", "gpt"], 3, ["gpt-oss:20b"]),
        (["satyrn", "use"], 2, MODELS),
        (["satyrn", "code", ""], 2, [completion.DIRS]),
        (["satyrn", "check", "--effort", "l"], 3, ["low"]),
        (["satyrn", "completion", "f"], 2, ["fish"]),
        (["satyrn", "interpreter", "--o"], 2, [completion.FILES]),
    ],
)
def test_completion_candidates(words: list[str], index: int, expected: list[str]) -> None:
    assert completion.complete(build_parser(), words, index, lambda: MODELS) == expected


def test_every_command_is_completed() -> None:
    found = completion.complete(build_parser(), ["satyrn", ""], 1, lambda: MODELS)
    for command in ("code", "models", "use", "install", "setup", "start", "stop", "check", "bench"):
        assert command in found


def run_bash_completion(tmp_path: Path, words: list[str], *, with_helpers: bool) -> list[str]:
    """Complete the last word of ``words`` in real bash, with the real completion script."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    shim = bin_dir / "satyrn"
    shim.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{ROOT / "satyrn.py"}" "$@"\n')
    shim.chmod(0o755)
    script = tmp_path / "satyrn.bash"
    script.write_text(completion.BASH)
    line = " ".join(words)
    setup = f"source {BASH_COMPLETION}\n" if with_helpers else ""
    # bash splits the line at COMP_WORDBREAKS, which contains ":" - like a real Tab press.
    program = f"""{setup}source {script}
COMP_LINE={json.dumps(line)}; COMP_POINT=${{#COMP_LINE}}
read -ra COMP_WORDS <<< "$(sed 's/:/ : /g' <<< "$COMP_LINE")"
[[ "$COMP_LINE" == *" " ]] && COMP_WORDS+=("")
COMP_CWORD=$(( ${{#COMP_WORDS[@]}} - 1 ))
_satyrn
printf '%s\\n' "${{COMPREPLY[@]}}"
"""
    env = dict(os.environ, PATH=f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    out = subprocess.run(["bash", "-c", program], capture_output=True, text=True, env=env, timeout=60, check=True)
    return [word for word in out.stdout.splitlines() if word]


@pytest.mark.skipif(IS_WINDOWS or not shutil.which("bash"), reason="needs bash")
def test_bash_completes_commands(tmp_path: Path) -> None:
    assert run_bash_completion(tmp_path, ["satyrn", "mod"], with_helpers=False) == ["models"]


@pytest.mark.skipif(not BASH_COMPLETION.is_file(), reason="needs the bash-completion package")
def test_bash_completes_model_names_with_colons(tmp_path: Path) -> None:
    # bash would split "gpt-oss:2" at the colon; bash-completion's helpers put it back together.
    assert run_bash_completion(tmp_path, ["satyrn", "code", "-m", "gpt-oss:2"], with_helpers=True) == ["20b"]


# --- models -----------------------------------------------------------------------------------
INFO = {"memory_gb": 14.1, "download_gb": 13.8}


@pytest.mark.parametrize(
    ("machine", "pulled", "fit"),
    [
        (Machine(40, 100, 10, None, 0), False, "fits"),
        (Machine(16, 100, 4, None, 0), False, "tight"),
        (Machine(8, 100, 4, None, 0), False, "too big"),
        (Machine(40, 10, 10, None, 0), False, "not enough disk"),
        (Machine(40, 10, 10, None, 0), True, "fits"),  # already downloaded: disk does not matter
        (Machine(16, 100, 8, "NVIDIA test (24 GB)", 24), False, "fits on GPU"),
    ],
)
def test_rating(machine: Machine, *, pulled: bool, fit: str) -> None:
    assert modelinfo.rate(INFO, machine, pulled=pulled) == fit


def test_models_ranked_and_recommended(project: Path) -> None:
    layout, pins = Layout(project), Pins.load(project / "pins.toml")
    big = modelinfo.choices(layout, pins, Machine(64, 500, 16, None, 0))
    assert big[0].model == "gpt-oss:20b"
    assert modelinfo.recommended(big).model == "gpt-oss:20b"
    assert next(c for c in big if c.model == "qwen3.8:27b").slow  # dense, no GPU
    small = modelinfo.choices(layout, pins, Machine(16, 500, 4, None, 0))
    assert [c.fit for c in small if c.model != "gpt-oss:20b"] == ["too big"] * 3
    assert modelinfo.recommended(small).model == "gpt-oss:20b"  # tight, but the only one


def test_models_command_shows_every_model(project: Path) -> None:
    out = satyrn(project, "models")
    assert out.returncode == 0, out.stderr
    assert out.stdout.startswith("This computer: ")
    for model in MODELS:
        assert model in out.stdout


def test_table_says_when_nothing_fits(project: Path) -> None:
    layout, pins = Layout(project), Pins.load(project / "pins.toml")
    tiny = Machine(8, 2, 2, None, 0)
    text = modelinfo.table(modelinfo.choices(layout, pins, tiny), tiny)
    assert "recommended" not in text
    assert "No prepared model fits this computer" in text


# --- guide and `use` --------------------------------------------------------------------------
def test_guide_reports_missing_steps(project: Path) -> None:
    out = satyrn(project)  # no command; stdin is not a terminal, so it only reports
    assert out.returncode == 0, out.stderr
    assert "[ ] tools" in out.stdout
    assert "[ ] model" in out.stdout
    assert "Next: satyrn setup --no-model" in out.stdout


def test_use_sets_the_default_model(project: Path) -> None:
    out = satyrn(project, "use", "qwen3.6:35b-a3b")
    assert out.returncode == 0, out.stderr
    layout = Layout(project)
    assert settings.default_model(layout, Pins.load(project / "pins.toml")) == "qwen3.6:35b-a3b"
    assert "not downloaded yet" in out.stdout


@pytest.mark.skipif(IS_WINDOWS, reason="needs a POSIX pseudo-terminal")
def test_guide_asks_and_accepts_no(project: Path) -> None:
    """In a terminal the guide asks before downloading anything; answering no stops it."""
    import pty  # POSIX only

    controller, terminal = pty.openpty()
    proc = subprocess.Popen(
        [sys.executable, str(project / "satyrn.py")], stdin=terminal, stdout=terminal, stderr=terminal
    )
    os.close(terminal)
    output = b""
    while b"[Y/n]" not in output:
        output += os.read(controller, 4096)
    os.write(controller, b"n\n")
    with contextlib.suppress(OSError):  # the terminal closes when the guide exits
        while chunk := os.read(controller, 4096):
            output += chunk
    assert proc.wait(timeout=30) == 0
    os.close(controller)
    text = output.decode()
    assert "Download and verify Ollama and Open Interpreter now" in text
    assert "Later: satyrn setup --no-model" in text
    assert not (project / ".runtime" / "downloads").exists(), "nothing may be downloaded after answering no"


# --- installation -----------------------------------------------------------------------------
@pytest.mark.skipif(IS_WINDOWS or not shutil.which("uv"), reason="POSIX with uv")
def test_install_and_uninstall(project: Path, tmp_path: Path) -> None:
    """Real `uv tool install --editable`, into temporary folders instead of ~/.local."""
    env = dict(
        os.environ,
        UV_TOOL_DIR=str(tmp_path / "tools"),
        UV_TOOL_BIN_DIR=str(tmp_path / "bin"),
        XDG_DATA_HOME=str(tmp_path / "data"),
        SHELL="/bin/bash",
    )
    install = subprocess.run(
        [sys.executable, str(project / "satyrn.py"), "install"], capture_output=True, text=True, env=env, check=False
    )
    assert install.returncode == 0, install.stdout + install.stderr
    command = tmp_path / "bin" / "satyrn"
    completion_file = tmp_path / "data" / "bash-completion" / "completions" / "satyrn"
    assert command.is_file()
    assert completion_file.read_text() == completion.BASH
    # The installed command runs the copy it was installed from (editable), with its .runtime/.
    out = subprocess.run([command, "__complete", "1", "satyrn", "mod"], capture_output=True, text=True, check=True)
    assert out.stdout.split() == ["models"]
    guide = subprocess.run([command], capture_output=True, text=True, stdin=subprocess.DEVNULL, check=True)
    assert "Next: satyrn setup --no-model" in guide.stdout
    # The engine is an optional extra: `satyrn-codegen` explains that instead of crashing.
    codegen = subprocess.run(
        [tmp_path / "bin" / "satyrn-codegen", "--help"], capture_output=True, text=True, check=False
    )
    assert codegen.returncode == 1
    assert "needs Satyrn's own engine" in codegen.stderr
    assert "Traceback" not in codegen.stderr

    uninstall = subprocess.run([command, "uninstall"], capture_output=True, text=True, env=env, check=False)
    assert uninstall.returncode == 0, uninstall.stdout + uninstall.stderr
    assert not command.exists()
    assert not completion_file.exists()

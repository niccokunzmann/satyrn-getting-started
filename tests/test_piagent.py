"""pi, the default coding agent: its generated settings and the command line. Nothing mocked."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from satyrn_local import agentconfig, piagent, settings  # noqa: E402
from satyrn_local.cli import build_parser  # noqa: E402
from satyrn_local.layout import Layout, Pins  # noqa: E402

PINS = Pins.load(ROOT / "pins.toml")


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "satyrn-getting-started"
    shutil.copytree(
        ROOT, root, ignore=shutil.ignore_patterns(".runtime", ".venv", "build", ".git", "__pycache__", ".prompts")
    )
    return root


def test_pi_settings_list_every_model_and_carry_the_satyrn_context(project: Path) -> None:
    layout = Layout(project)
    piagent.write_config(layout, PINS)
    provider = json.loads((layout.pi_home / "models.json").read_text())["providers"][piagent.PROVIDER]
    assert provider["baseUrl"] == f"http://127.0.0.1:{PINS.port}/v1"
    assert [m["id"] for m in provider["models"]] == agentconfig.known_models(layout)
    assert {m["contextWindow"] for m in provider["models"]} == {PINS.context_length}
    assert json.loads((layout.pi_home / "settings.json").read_text())["enableInstallTelemetry"] is False
    system = (layout.pi_home / "SYSTEM.md").read_text()
    assert system == (project / "config" / "context" / "pi.md").read_text()
    assert "You are Satyrn" in system
    assert "Put each sentence of your answers on its own line." in system


def test_both_contexts_name_satyrn_and_ask_for_one_sentence_per_line() -> None:
    for name in ("pi.md", "open-interpreter.md"):
        text = (ROOT / "config" / "context" / name).read_text()
        assert "You are Satyrn" in text, name
        assert "Put each sentence of your answers on its own line." in text, name


def test_pi_is_the_default_coding_agent(project: Path) -> None:
    layout = Layout(project)
    assert settings.default_harness(layout) == "pi"
    settings.set_default_harness(layout, "open-interpreter")
    assert settings.default_harness(layout) == "open-interpreter"


def test_code_chooses_the_agent_for_one_session() -> None:
    parser = build_parser()
    assert parser.parse_args(["code", "dir", "--pi"]).harness == "pi"
    assert parser.parse_args(["code", "dir", "--open-interpreter"]).harness == "open-interpreter"
    assert parser.parse_args(["code", "dir"]).harness is None
    with pytest.raises(SystemExit):
        parser.parse_args(["code", "dir", "--pi", "--open-interpreter"])


def test_pi_runs_through_satyrn() -> None:
    layout = Layout(ROOT)
    if not piagent.is_installed(layout, PINS):
        pytest.skip("run `satyrn setup` first")
    out = subprocess.run(
        [sys.executable, str(ROOT / "satyrn.py"), "pi", "--version"], capture_output=True, text=True, check=True
    )
    assert PINS.data["pi"]["version"] in out.stdout

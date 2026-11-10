"""The generated Open Interpreter config and model catalog, checked by the real pinned interpreter.

No model is needed: the interpreter loads and validates the config, then stops because no
Ollama server listens on the port given to it.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from satyrn_local import agentconfig  # noqa: E402
from satyrn_local.cli import write_interpreter_config  # noqa: E402
from satyrn_local.layout import Layout, Pins  # noqa: E402

PINS = Pins.load(ROOT / "pins.toml")
NO_SERVER = "http://127.0.0.1:9"  # discard port: nothing answers


@pytest.fixture
def generated(tmp_path: Path) -> Layout:
    """A copy of the project's config, generated into a temporary .runtime."""
    shutil.copytree(ROOT / "config", tmp_path / "config")
    shutil.copy(ROOT / "pins.toml", tmp_path / "pins.toml")
    layout = Layout(tmp_path)
    write_interpreter_config(layout, PINS)
    return layout


def interpreter(layout: Layout, *args: str) -> subprocess.CompletedProcess[str]:
    exe = Layout(ROOT).interpreter_dir / "bin" / "interpreter"
    if not exe.exists() and not exe.with_suffix(".exe").exists():
        pytest.skip("run `python satyrn.py setup` first")
    env = dict(os.environ, INTERPRETER_HOME=str(layout.interpreter_home), CODEX_OSS_BASE_URL=f"{NO_SERVER}/v1")
    env["OLLAMA_HOST"] = NO_SERVER.removeprefix("http://")
    return subprocess.run(
        [str(Layout(ROOT).interpreter_exe()), *args], capture_output=True, text=True, env=env, timeout=60, check=False
    )


def test_catalog_has_every_model_with_our_instructions(generated: Layout) -> None:
    catalog = json.loads(generated.catalog.read_text(encoding="utf-8"))
    instructions = (ROOT / "config" / "context" / "open-interpreter.md").read_text(encoding="utf-8")
    entries = {entry["slug"]: entry for entry in catalog["models"]}
    assert set(entries) == set(agentconfig.known_models(generated))
    assert PINS.model in entries
    for entry in entries.values():
        assert entry["model_messages"]["instructions_template"] == instructions
        assert entry["context_window"] == PINS.context_length
        assert entry["apply_patch_tool_type"] is None  # Ollama cannot deliver freeform calls
    # The prompt must not name a tool the interpreter does not register.
    assert "apply_patch" not in instructions
    assert chr(92) + "u003e" in instructions  # the note on JSON escapes kept its backslash
    assert [level["effort"] for level in entries["gpt-oss:20b"]["supported_reasoning_levels"]] == [
        "low",
        "medium",
        "high",
    ]


def test_interpreter_accepts_generated_config_and_catalog(generated: Layout) -> None:
    """--strict-config rejects unknown keys; a bad catalog fails to parse before the server check."""
    for model in agentconfig.known_models(generated):
        run = interpreter(generated, "exec", "--strict-config", "--oss", "-m", model, "--skip-git-repo-check", "hi")
        output = run.stdout + run.stderr
        assert "No running Ollama server" in output, output[-600:]
        assert "Model metadata" not in output, output[-600:]  # the fallback warning


def test_prompt_input_is_short(generated: Layout) -> None:
    """Under `exec` settings the model gets only the sandbox note, its environment and the task."""
    args = ("-c", 'sandbox_mode="workspace-write"', "-c", 'approval_policy="never"', "hi")
    run = interpreter(generated, "debug", "prompt-input", *args)
    assert run.returncode == 0, run.stderr
    items = json.loads(run.stdout)
    texts = ["".join(part.get("text", "") for part in item["content"]) for item in items]
    assert [item["role"] for item in items] == ["developer", "user", "user"]
    assert texts[0].startswith("<permissions instructions>")
    assert "skills" not in texts[0]
    assert len(texts[0]) < 1000, texts[0]


def test_setup_keeps_trusted_projects(generated: Layout) -> None:
    """Re-running setup must not drop the folders the user trusted in the interpreter."""
    config = generated.interpreter_home / "config.toml"
    folder = str(generated.root / 'a "quoted" dir')
    config.write_text(config.read_text() + f'\n[projects.{json.dumps(folder)}]\ntrust_level = "trusted"\n')
    write_interpreter_config(generated, PINS)
    data = tomllib.loads(config.read_text())
    assert data["projects"] == {folder: {"trust_level": "trusted"}}
    assert data["model_catalog_json"] == str(generated.catalog)

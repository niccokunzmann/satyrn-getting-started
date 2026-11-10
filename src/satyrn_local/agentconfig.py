"""Tell Open Interpreter how to drive local models.

Open Interpreter 0.0.60 ships metadata only for OpenAI's hosted models. Any other model gets a
fallback: a 17 KB generic system prompt that tells it to use an ``apply_patch`` tool which is
never registered, plus about 18 KB of tools a local model cannot use (sub-agents, goals, web
search). On a CPU that is ~6.7k prompt tokens (about five minutes) before the model starts, and
the model wastes many turns calling the missing tool.

``write_catalog`` turns config/models.toml plus config/context/open-interpreter.md into the interpreter's
``model_catalog_json``: one entry per model with our system prompt and the server's context
window. config/interpreter.toml points the interpreter at it and switches the unused tools off.

``apply_patch`` stays unregistered on purpose. The interpreter offers it only as a "freeform"
(custom grammar) tool; Ollama's Responses API returns such calls as JSON function calls, which
the interpreter rejects ("tool apply_patch invoked with incompatible payload"). The models
therefore create and edit files through ``exec_command``, as config/context/open-interpreter.md explains.
"""

from __future__ import annotations

import json
import os
import tomllib
from pathlib import Path

from .layout import IS_WINDOWS, Layout, Pins

# Fields every catalog entry needs (the interpreter rejects entries without them), with values
# that suit a local model. Per-model values from config/models.toml are applied on top.
BASE_ENTRY: dict = {
    "visibility": "list",
    "supported_in_api": True,
    "priority": 1,
    "shell_type": "unified_exec",  # tools `exec_command` + `write_stdin`
    "input_modalities": ["text"],
    "support_verbosity": False,
    "supports_reasoning_summaries": False,
    "supports_parallel_tool_calls": False,
    "experimental_supported_tools": [],
}


def load_models(layout: Layout) -> dict[str, dict]:
    """Per-model settings from config/models.toml, with [defaults] applied."""
    with (layout.root / "config" / "models.toml").open("rb") as handle:
        data = tomllib.load(handle)
    defaults = data.pop("defaults", {})
    return {name: defaults | settings for name, settings in data.items()}


def catalog_entry(name: str, settings: dict, instructions: str, context_window: int) -> dict:
    efforts = list(settings.get("reasoning_efforts", []))
    entry = BASE_ENTRY | {
        "slug": name,
        "display_name": name,
        "description": settings.get("description", f"{name} on the local Ollama server"),
        "model_messages": {"instructions_template": instructions},
        "context_window": context_window,
        "max_context_window": context_window,
        # Compact the conversation before the server would have to cut the prompt.
        "auto_compact_token_limit": int(context_window * 0.8),
        "truncation_policy": {"mode": "tokens", "limit": int(settings["tool_output_tokens"])},
        "apply_patch_tool_type": None,  # see the module docstring
        "supported_reasoning_levels": [{"effort": e, "description": f"{e} reasoning"} for e in efforts],
    }
    if efforts:
        entry["default_reasoning_level"] = settings.get("default_effort", efforts[0])
    return entry


def shell_name() -> str:
    """The shell the interpreter runs commands in, for the instructions (@SHELL@)."""
    return "PowerShell" if IS_WINDOWS else Path(os.environ.get("SHELL") or "/bin/sh").name


def write_catalog(
    layout: Layout, pins: Pins, instructions_file: Path | None = None, target: Path | None = None
) -> Path:
    """(Re)write the model catalog; cheap, so commands call it before every interpreter run.

    ``instructions_file`` and ``target`` let `bench` try other instructions without touching
    the catalog that `interpreter` uses.
    """
    source = instructions_file or layout.root / "config" / "context" / "open-interpreter.md"
    instructions = source.read_text(encoding="utf-8").replace("@SHELL@", shell_name())
    models = load_models(layout)
    catalog = {
        "models": [catalog_entry(name, s, instructions, pins.context_length) for name, s in models.items()],
    }
    target = target or layout.catalog
    target.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(catalog, indent=2) + "\n"
    if not target.is_file() or target.read_text(encoding="utf-8") != text:
        target.write_text(text, encoding="utf-8")
    return target


def known_models(layout: Layout) -> list[str]:
    return list(load_models(layout))

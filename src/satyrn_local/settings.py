"""The user's own choices (for example `satyrn use MODEL`), kept in .runtime/settings.toml."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

from .layout import Layout, Pins


def load(layout: Layout) -> dict:
    try:
        return tomllib.loads(layout.settings.read_text(encoding="utf-8"))
    except FileNotFoundError, tomllib.TOMLDecodeError:
        return {}


def save(layout: Layout, values: dict) -> None:
    """Write top-level values, then tables (a dict value becomes a [table] of strings)."""
    layout.runtime.mkdir(parents=True, exist_ok=True)
    lines = ["# Written by `satyrn`; your choices. Delete this file to return to the defaults.\n"]
    lines += [f"{key} = {json.dumps(value)}\n" for key, value in sorted(values.items()) if not isinstance(value, dict)]
    for name, table in sorted((key, value) for key, value in values.items() if isinstance(value, dict)):
        lines.append(f"\n[{name}]\n")
        lines += [f"{json.dumps(key)} = {json.dumps(value)}\n" for key, value in sorted(table.items())]
    layout.settings.write_text("".join(lines), encoding="utf-8")


def default_model(layout: Layout, pins: Pins) -> str:
    """The model from `satyrn use`, else the project default in pins.toml."""
    return load(layout).get("model") or pins.model


def set_default_model(layout: Layout, model: str) -> None:
    save(layout, load(layout) | {"model": model})


def manifest(layout: Layout, model: str) -> Path:
    """Where Ollama keeps the manifest of ``model`` (exists once the model is downloaded)."""
    name, _, tag = model.partition(":")
    namespace, _, short = name.rpartition("/")
    return layout.models / "manifests" / "registry.ollama.ai" / (namespace or "library") / short / (tag or "latest")


def is_pulled(layout: Layout, model: str) -> bool:
    """Downloaded? Works without a running server."""
    return manifest(layout, model).is_file()


def accepted_digest(layout: Layout, model: str) -> str | None:
    """The build of ``model`` the user accepted although it differs from pins.toml."""
    return load(layout).get("accepted_digests", {}).get(model)


def accept_digest(layout: Layout, model: str, digest: str) -> None:
    values = load(layout)
    values["accepted_digests"] = values.get("accepted_digests", {}) | {model: digest}
    save(layout, values)

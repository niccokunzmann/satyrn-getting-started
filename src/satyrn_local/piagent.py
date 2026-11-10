"""pi (https://pi.dev), the default coding agent: installation, settings and command line.

Node.js comes from a pinned, checksum-verified download (pins.toml [node]); pi and every npm
package it needs come from config/pi/package-lock.json, installed with `npm ci --ignore-scripts`
into .runtime/pi. pi's settings live in .runtime/pi-home (PI_CODING_AGENT_DIR), so a pi you may
have installed yourself (~/.pi) is not touched.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from . import agentconfig, fetch
from .layout import Layout, Pins

PACKAGE = "@earendil-works/pi-coding-agent"
PROVIDER = "local"  # pi's name for the Ollama server; models are "local/<model>"
STAMP = ".satyrn-npm-ci"


def model_ref(model: str) -> str:
    return f"{PROVIDER}/{model}"


def _lock_files(layout: Layout) -> list[Path]:
    return [layout.root / "config" / "pi" / name for name in ("package.json", "package-lock.json")]


def _npm_cli(layout: Layout) -> Path:
    found = sorted(layout.node_dir.glob("*/lib/node_modules/npm/bin/npm-cli.js")) or sorted(
        layout.node_dir.glob("*/node_modules/npm/bin/npm-cli.js")  # Windows layout
    )
    if not found:
        raise SystemExit(f"npm is missing in {layout.node_dir}; run: satyrn setup")
    return found[0]


def cli(layout: Layout) -> Path:
    """pi's entry script, from its package.json `bin` field."""
    package_dir = layout.pi_dir / "node_modules" / Path(*PACKAGE.split("/"))
    try:
        manifest = json.loads((package_dir / "package.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"pi is not installed in {layout.pi_dir}; run: satyrn setup") from None
    entry = manifest["bin"] if isinstance(manifest["bin"], str) else manifest["bin"]["pi"]
    return package_dir / entry


def is_installed(layout: Layout, pins: Pins) -> bool:
    stamp = layout.pi_dir / STAMP
    return (
        fetch.is_unpacked(layout.node_dir, pins.asset("node").sha256)
        and stamp.is_file()
        and stamp.read_text().strip() == fetch.sha256_file(_lock_files(layout)[1])
    )


def env(layout: Layout, pins: Pins) -> dict[str, str]:
    node_bin = layout.node_exe().parent
    values = dict(os.environ)
    values.update(
        PATH=f"{node_bin}{os.pathsep}{values.get('PATH', '')}",
        PI_CODING_AGENT_DIR=str(layout.pi_home),  # keeps ~/.pi untouched
        PI_TELEMETRY="0",
        PI_SKIP_VERSION_CHECK="1",
        npm_config_cache=str(layout.runtime / "npm-cache"),  # not ~/.npm
        npm_config_update_notifier="false",
        npm_config_fund="false",
        npm_config_audit="false",
    )
    return values


def install(layout: Layout, pins: Pins) -> None:
    """Download Node.js and install pi from the lock file; finished steps are skipped."""
    node = pins.asset("node")
    archive = fetch.download(node, layout.downloads)
    fetch.unpack(archive, layout.node_dir, node.sha256)
    lock = _lock_files(layout)[1]
    stamp = layout.pi_dir / STAMP
    if stamp.is_file() and stamp.read_text().strip() == fetch.sha256_file(lock):
        print(f"  pi {pins.data['pi']['version']} already installed in {layout.pi_dir}")
        return
    if layout.pi_dir.exists():
        shutil.rmtree(layout.pi_dir)
    layout.pi_dir.mkdir(parents=True)
    for source in _lock_files(layout):
        shutil.copy(source, layout.pi_dir / source.name)
    print(f"  installing pi {pins.data['pi']['version']} with npm ci (every package is checked against the lock file)")
    command = [str(layout.node_exe()), str(_npm_cli(layout)), "ci", "--ignore-scripts", "--prefix", str(layout.pi_dir)]
    subprocess.run(command, env=env(layout, pins), check=True)
    stamp.write_text(fetch.sha256_file(lock) + "\n")
    print(f"  installed pi in {layout.pi_dir}")


def write_config(layout: Layout, pins: Pins) -> None:
    """pi's model list, settings and system prompt; cheap, so it is rewritten before every start."""
    layout.pi_home.mkdir(parents=True, exist_ok=True)
    models = []
    for name, info in agentconfig.load_models(layout).items():
        model = {"id": name, "name": name, "contextWindow": pins.context_length, "maxTokens": 8192}
        if info.get("reasoning_efforts"):  # pi then passes its thinking level on as reasoning_effort
            model |= {"reasoning": True, "compat": {"supportsReasoningEffort": True}}
        models.append(model)
    providers = {
        PROVIDER: {
            "name": "Ollama on this computer",
            "baseUrl": f"http://127.0.0.1:{pins.port}/v1",
            "api": "openai-completions",
            "apiKey": "ollama",  # Ollama ignores it; pi needs some key to list the models
            "models": models,
        }
    }
    files = {
        "models.json": json.dumps({"providers": providers}, indent=2) + "\n",
        # No install telemetry; a long idle timeout, because a CPU may read a prompt for minutes.
        "settings.json": json.dumps({"enableInstallTelemetry": False, "httpIdleTimeoutMs": 3_600_000}, indent=2) + "\n",
        "SYSTEM.md": (layout.root / "config" / "context" / "pi.md").read_text(encoding="utf-8"),
    }
    for name, text in files.items():
        target = layout.pi_home / name
        if not target.is_file() or target.read_text(encoding="utf-8") != text:
            target.write_text(text, encoding="utf-8")


def command(layout: Layout, args: list[str]) -> list[str]:
    return [str(layout.node_exe()), str(cli(layout)), *args]

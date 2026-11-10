"""Pinned inputs (pins.toml) and the on-disk layout under .runtime/."""

from __future__ import annotations

import platform
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

IS_WINDOWS = sys.platform == "win32"
EXE = ".exe" if IS_WINDOWS else ""


def platform_key() -> str:
    """Return the pins.toml asset key for this machine, e.g. ``linux-x86_64``."""
    machine = platform.machine().lower()
    arch = {"amd64": "x86_64", "x86_64": "x86_64", "x64": "x86_64", "arm64": "aarch64", "aarch64": "aarch64"}.get(
        machine
    )
    if arch is None:
        raise SystemExit(f"unsupported CPU architecture: {machine}")
    if sys.platform.startswith("linux"):
        return f"linux-{arch}"
    if IS_WINDOWS:
        return f"windows-{arch}"
    if sys.platform == "darwin":
        return "macos-arm64" if arch == "aarch64" else "macos-x86_64"
    raise SystemExit(f"unsupported operating system: {sys.platform}")


@dataclass(frozen=True)
class Asset:
    component: str
    version: str
    url: str
    file: str
    sha256: str


@dataclass(frozen=True)
class Pins:
    data: dict

    @classmethod
    def load(cls, path: Path) -> Pins:
        with path.open("rb") as handle:
            return cls(tomllib.load(handle))

    @property
    def model(self) -> str:
        return self.data["model"]["default"]

    @property
    def digests(self) -> dict[str, str]:
        """Pinned manifest digests by model name ([model.digests])."""
        return dict(self.data["model"].get("digests", {}))

    def digest(self, model: str) -> str | None:
        return self.digests.get(model if ":" in model else f"{model}:latest")

    @property
    def context_length(self) -> int:
        return int(self.data["model"]["context_length"])

    @property
    def port(self) -> int:
        return int(self.data["ollama"]["port"])

    def asset(self, component: str, key: str | None = None) -> Asset:
        section = self.data[component]
        key = key or platform_key()
        try:
            entry = section["assets"][key]
        except KeyError:
            raise SystemExit(f"{component} has no pinned download for {key} in pins.toml") from None
        return Asset(
            component, section["version"], f"{section['base_url']}/{entry['file']}", entry["file"], entry["sha256"]
        )


@dataclass(frozen=True)
class Layout:
    """Every file this tool creates lives below ``root/.runtime``."""

    root: Path

    @property
    def pins_file(self) -> Path:
        return self.root / "pins.toml"

    @property
    def runtime(self) -> Path:
        return self.root / ".runtime"

    @property
    def downloads(self) -> Path:
        return self.runtime / "downloads"

    @property
    def ollama_dir(self) -> Path:
        return self.runtime / "ollama"

    @property
    def interpreter_dir(self) -> Path:
        return self.runtime / "interpreter"

    @property
    def models(self) -> Path:
        return self.runtime / "models"

    @property
    def home(self) -> Path:
        """HOME/USERPROFILE for the Ollama server, so its keys never land in ~/.ollama."""
        return self.runtime / "home"

    @property
    def interpreter_home(self) -> Path:
        return self.runtime / "interpreter-home"

    @property
    def catalog(self) -> Path:
        """Model catalog for Open Interpreter, generated from config/models.toml."""
        return self.interpreter_home / "models.json"

    @property
    def settings(self) -> Path:
        """The user's choices, for example the model from `satyrn use`."""
        return self.runtime / "settings.toml"

    @property
    def install_record(self) -> Path:
        """What `install` put outside this folder, so that `uninstall` can remove it."""
        return self.runtime / "installed.json"

    @property
    def bench(self) -> Path:
        return self.runtime / "bench"

    @property
    def bin(self) -> Path:
        return self.runtime / "bin"

    @property
    def pidfile(self) -> Path:
        return self.runtime / "ollama.pid"

    @property
    def logfile(self) -> Path:
        return self.runtime / "ollama.log"

    def ollama_exe(self) -> Path:
        for candidate in (self.ollama_dir / "bin" / f"ollama{EXE}", self.ollama_dir / f"ollama{EXE}"):
            if candidate.is_file():
                return candidate
        raise SystemExit(f"Ollama is not installed in {self.ollama_dir}; run: satyrn setup")

    def interpreter_exe(self) -> Path:
        candidate = self.interpreter_dir / "bin" / f"interpreter{EXE}"
        if not candidate.is_file():
            raise SystemExit(f"Open Interpreter is not installed in {self.interpreter_dir}; run: satyrn setup")
        return candidate

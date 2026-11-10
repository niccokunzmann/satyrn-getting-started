"""Tests for the project-local Ollama + Open Interpreter setup. Nothing is mocked:
archives, checksums and downloads are real (file:// URLs), and the live test sends the
square-root task through the real model via `interpreter exec --oss`."""

from __future__ import annotations

import hashlib
import io
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from satyrn_local import fetch, ollama, procs  # noqa: E402
from satyrn_local.layout import Asset, Layout, Pins, platform_key  # noqa: E402

PINS = Pins.load(ROOT / "pins.toml")


def test_pins_cover_linux_windows_macos() -> None:
    for component in ("ollama", "interpreter"):
        keys = set(PINS.data[component]["assets"])
        assert {"linux-x86_64", "windows-x86_64", "macos-arm64"} <= keys
        for entry in PINS.data[component]["assets"].values():
            assert len(entry["sha256"]) == 64
    assert PINS.asset("ollama", platform_key()).url.startswith("https://github.com/")


def _archive(tmp_path: Path, kind: str) -> Path:
    payload = b"#!/bin/sh\necho hi\n"
    path = tmp_path / f"pkg.{kind}"
    if kind == "zip":
        with zipfile.ZipFile(path, "w") as zf:
            zf.writestr("bin/tool", payload)
    else:
        with tarfile.open(path, {"tar.zst": "w:zst", "tar.xz": "w:xz", "tgz": "w:gz"}[kind]) as tf:
            info = tarfile.TarInfo("bin/tool")
            info.size, info.mode = len(payload), 0o755
            tf.addfile(info, io.BytesIO(payload))
    return path


@pytest.mark.parametrize("kind", ["tar.zst", "tar.xz", "tgz", "zip"])
def test_download_verify_and_unpack(tmp_path: Path, kind: str) -> None:
    archive = _archive(tmp_path, kind)
    sha = hashlib.sha256(archive.read_bytes()).hexdigest()
    asset = Asset("demo", "1.0", archive.as_uri(), archive.name, sha)
    local = fetch.download(asset, tmp_path / "downloads")
    fetch.unpack(local, tmp_path / "out", sha)
    assert (tmp_path / "out" / "bin" / "tool").read_bytes().startswith(b"#!/bin/sh")
    fetch.unpack(local, tmp_path / "out", sha)  # second run is a no-op (stamp matches)


def test_download_rejects_wrong_checksum(tmp_path: Path) -> None:
    archive = _archive(tmp_path, "tgz")
    asset = Asset("demo", "1.0", archive.as_uri(), archive.name, "0" * 64)
    with pytest.raises(fetch.ChecksumError):
        fetch.download(asset, tmp_path / "downloads")
    assert not list((tmp_path / "downloads").iterdir())  # nothing unverified is kept


def test_satyrn_py_runs_with_this_python() -> None:
    out = subprocess.run(
        [sys.executable, str(ROOT / "satyrn.py"), "--help"], capture_output=True, text=True, check=True
    )
    assert "setup" in out.stdout and "check" in out.stdout


# --- live: through the real model ---------------------------------------------------------
@pytest.mark.live
def test_model_writes_working_sqrt_program() -> None:
    layout = Layout(ROOT)
    if not ollama.is_up(PINS):
        pytest.skip("Ollama is not running: python satyrn.py start")
    if ollama.model_digest(PINS, PINS.model) is None:
        pytest.skip(f"{PINS.model} is not pulled: python satyrn.py setup")
    layout.interpreter_exe()  # fails clearly if setup has not run
    # `check` stops itself at procs.TIME_LIMIT; the margin lets it clean up before pytest gives up.
    run = subprocess.run(
        [sys.executable, str(ROOT / "satyrn.py"), "check"], text=True, timeout=procs.TIME_LIMIT + 300, check=False
    )
    assert run.returncode == 0, "the model did not produce a working sqrt.py (see output above)"


def test_interpreter_passthrough_keeps_options() -> None:
    """`satyrn.py interpreter --version` must reach the pinned binary, not argparse."""
    if not Layout(ROOT).interpreter_dir.exists():
        pytest.skip("run `python satyrn.py setup` first")
    out = subprocess.run(
        [sys.executable, str(ROOT / "satyrn.py"), "interpreter", "--version"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert PINS.data["interpreter"]["version"] in out.stdout

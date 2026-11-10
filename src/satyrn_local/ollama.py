"""Run the project-local Ollama server: foreground, background (pidfile) or temporarily."""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path

from . import settings
from .layout import IS_WINDOWS, Layout, Pins

KEEP_ALIVE = "30m"  # how long an idle model stays in memory (OLLAMA_KEEP_ALIVE overrides it)


def server_env(layout: Layout, pins: Pins) -> dict[str, str]:
    env = dict(os.environ)
    layout.home.mkdir(parents=True, exist_ok=True)
    layout.models.mkdir(parents=True, exist_ok=True)
    env.update(
        HOME=str(layout.home),
        USERPROFILE=str(layout.home),  # Windows: Ollama keeps its keys under %USERPROFILE%\.ollama
        OLLAMA_MODELS=str(layout.models),
        OLLAMA_HOST=f"127.0.0.1:{pins.port}",
        OLLAMA_CONTEXT_LENGTH=str(pins.context_length),
    )
    env.setdefault("OLLAMA_KEEP_ALIVE", KEEP_ALIVE)
    return env


def api(pins: Pins, path: str, body: dict | None = None, timeout: float = 5) -> dict:
    """GET ``path`` (or POST ``body`` as JSON) on the local server."""
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(
        f"http://127.0.0.1:{pins.port}{path}", data=data, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed local URL
        return json.load(response)


def is_up(pins: Pins) -> bool:
    try:
        api(pins, "/api/version", timeout=1)
    except urllib.error.URLError, OSError:
        return False
    return True


def wait_up(pins: Pins, timeout: float = 60) -> None:
    deadline = time.monotonic() + timeout
    while not is_up(pins):
        if time.monotonic() > deadline:
            raise SystemExit(f"Ollama did not start on port {pins.port} within {timeout:.0f}s")
        time.sleep(0.5)


def _popen(layout: Layout, pins: Pins, *, detach: bool, log) -> subprocess.Popen:  # noqa: ANN001
    kwargs: dict = {
        "env": server_env(layout, pins),
        "stdin": subprocess.DEVNULL,
        "stdout": log,
        "stderr": subprocess.STDOUT,
    }
    if detach:
        if IS_WINDOWS:
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        else:
            kwargs["start_new_session"] = True
    return subprocess.Popen([str(layout.ollama_exe()), "serve"], **kwargs)


def serve(layout: Layout, pins: Pins) -> int:
    """Run in the foreground until Ctrl+C."""
    print(f"Ollama on 127.0.0.1:{pins.port}, models in {layout.models} (Ctrl+C to stop)")
    try:
        return subprocess.call([str(layout.ollama_exe()), "serve"], env=server_env(layout, pins))
    except KeyboardInterrupt:
        return 0


def _pid(layout: Layout) -> int | None:
    try:
        return int(layout.pidfile.read_text().strip())
    except OSError, ValueError:
        return None


def windows_tool(name: str) -> str:
    """Absolute path of a Windows system tool (avoids PATH lookups)."""
    return str(Path(os.environ.get("SYSTEMROOT", r"C:\Windows")) / "System32" / f"{name}.exe")


def _alive(pid: int) -> bool:
    if IS_WINDOWS:
        out = subprocess.run(
            [windows_tool("tasklist"), "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True, check=False
        )
        return str(pid) in out.stdout
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def start(layout: Layout, pins: Pins) -> None:
    pid = _pid(layout)
    if pid and _alive(pid) and is_up(pins):
        print(f"Ollama already running (pid {pid}) on 127.0.0.1:{pins.port}")
        return
    if is_up(pins):
        raise SystemExit(f"another server already listens on port {pins.port}; stop it or change [ollama].port")
    layout.runtime.mkdir(parents=True, exist_ok=True)
    with layout.logfile.open("ab") as log:
        proc = _popen(layout, pins, detach=True, log=log)
    layout.pidfile.write_text(f"{proc.pid}\n")
    wait_up(pins)
    print(f"Ollama started (pid {proc.pid}) on 127.0.0.1:{pins.port}; log: {layout.logfile}")
    preload(pins, settings.default_model(layout, pins))
    print("stop it with: satyrn stop")


def preload(pins: Pins, model: str) -> None:
    """Load ``model`` into memory in the background, so the first request does not wait for it."""
    if not is_up(pins):
        return
    body = json.dumps({"model": model, "keep_alive": KEEP_ALIVE}).encode()
    code = (
        "import sys, urllib.request\n"
        "request = urllib.request.Request(sys.argv[1], data=sys.argv[2].encode(), "
        "headers={'Content-Type': 'application/json'})\n"
        "urllib.request.urlopen(request, timeout=900)\n"
    )
    subprocess.Popen(
        [sys.executable, "-c", code, f"http://127.0.0.1:{pins.port}/api/generate", body.decode()],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=not IS_WINDOWS,
    )
    print(f"loading {model} into memory in the background (about half a minute)")


def stop(layout: Layout, pins: Pins) -> None:
    pid = _pid(layout)
    if pid is None or not _alive(pid):
        layout.pidfile.unlink(missing_ok=True)
        print(
            "Ollama is not running (no live pid from 'start')"
            + (f"; something else answers on port {pins.port}" if is_up(pins) else "")
        )
        return
    if IS_WINDOWS:
        subprocess.run([windows_tool("taskkill"), "/PID", str(pid), "/T", "/F"], capture_output=True, check=False)
    else:
        os.killpg(pid, signal.SIGTERM)
    for _ in range(40):
        if not _alive(pid):
            break
        time.sleep(0.25)
    layout.pidfile.unlink(missing_ok=True)
    print(f"Ollama stopped (pid {pid})")


@contextlib.contextmanager
def running(layout: Layout, pins: Pins) -> Iterator[None]:
    """Use the running server, or start one just for the duration of the block."""
    if is_up(pins):
        yield
        return
    print("  starting a temporary Ollama server ...")
    with (layout.runtime / "ollama-temp.log").open("ab") as log:
        proc = _popen(layout, pins, detach=False, log=log)
    try:
        wait_up(pins)
        yield
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            proc.kill()
        print("  temporary Ollama server stopped")


def model_digest(pins: Pins, model: str) -> str | None:
    name = model if ":" in model else f"{model}:latest"
    for entry in api(pins, "/api/tags").get("models", []):
        if entry.get("name") == name:
            return entry.get("digest")
    return None


def pull(layout: Layout, pins: Pins, model: str) -> str:
    subprocess.run([str(layout.ollama_exe()), "pull", model], env=server_env(layout, pins), check=True)
    digest = model_digest(pins, model)
    if digest is None:
        raise SystemExit(f"{model} is not listed after pulling it")
    return digest


def loaded_models(pins: Pins) -> list[str]:
    # Generous timeout: while a 20 GB model is being unloaded, the server answers slowly.
    return [m["name"] for m in api(pins, "/api/ps", timeout=120).get("models", [])]


def load(pins: Pins, model: str) -> float:
    """Load ``model`` into memory (an empty generate request); returns the seconds it took."""
    started = time.monotonic()
    api(pins, "/api/generate", {"model": model, "keep_alive": "30m"}, timeout=900)
    return time.monotonic() - started


def unload(pins: Pins, model: str, timeout: float = 300) -> None:
    """Unload ``model`` and wait until it has left memory."""
    api(pins, "/api/generate", {"model": model, "keep_alive": 0}, timeout=120)
    deadline = time.monotonic() + timeout
    while model in loaded_models(pins):
        if time.monotonic() > deadline:
            raise SystemExit(f"{model} is still loaded {timeout:.0f}s after asking Ollama to unload it")
        time.sleep(1)


_PROMPT_TIMING = re.compile(r"task (\d+) \| prompt eval time =\s+([\d.]+) ms /\s+(\d+) tokens")
_GENERATE_TIMING = re.compile(r"task (\d+) \|\s+eval time =\s+([\d.]+) ms /\s+(\d+) tokens")


def request_timings(log_text: str) -> list[dict[str, float]]:
    """Per-request timings from the server log: tokens read and written, and the seconds for each.

    "read" is prompt processing (only the tokens not already in Ollama's cache), "write" is
    generation. Present when the server was started with `start` (its log is .runtime/ollama.log).
    """
    requests: list[dict[str, float]] = []
    for line in log_text.splitlines():
        if match := _PROMPT_TIMING.search(line):
            requests.append(
                {"read_tokens": int(match[3]), "read_s": float(match[2]) / 1000, "write_tokens": 0, "write_s": 0.0}
            )
        elif (match := _GENERATE_TIMING.search(line)) and requests:
            requests[-1].update(write_tokens=int(match[3]), write_s=float(match[2]) / 1000)
    return requests


REGISTRY = "https://registry.ollama.ai/v2"


def remote_digest(model: str) -> str | None:
    """The build the tag points to in the Ollama registry now (what a pull would download).

    Its digest is the SHA-256 of the manifest the registry sends. None when the registry
    cannot be asked (offline, for example); the digest is then checked after the pull.
    """
    name, _, tag = model.partition(":")
    namespace, _, short = name.rpartition("/")
    request = urllib.request.Request(  # noqa: S310 - fixed https registry URL
        f"{REGISTRY}/{namespace or 'library'}/{short}/manifests/{tag or 'latest'}",
        headers={"Accept": "application/vnd.docker.distribution.manifest.v2+json", "User-Agent": "satyrn"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:  # noqa: S310 - fixed https registry
            return hashlib.sha256(response.read()).hexdigest()
    except urllib.error.URLError, OSError:
        return None

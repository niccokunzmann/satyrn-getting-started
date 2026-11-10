"""`satyrn.py install`: the `satyrn` command (linked to this clone) and tab completion.

Everything placed outside the clone is recorded in .runtime/installed.json, so `uninstall`
removes exactly that and nothing else.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from . import completion
from .layout import IS_WINDOWS, Layout

DISTRIBUTION = "satyrn-cli"
BEGIN, END = "# >>> satyrn completion >>>", "# <<< satyrn completion <<<"


def _home_dir(variable: str, fallback: str) -> Path:
    return Path(os.environ.get(variable) or Path.home() / fallback)


def current_shell() -> str | None:
    if IS_WINDOWS:
        return "powershell"
    name = Path(os.environ.get("SHELL", "")).name
    return name if name in completion.SHELLS else None


def _installer() -> tuple[str, list[str]] | None:
    """uv (preferred) or pipx, with the arguments for an editable install of this clone."""
    if uv := shutil.which("uv"):
        return "uv", [uv, "tool", "install", "--force", "--python", sys.executable, "--editable"]
    if pipx := shutil.which("pipx"):
        return "pipx", [pipx, "install", "--force", "--python", sys.executable, "--editable"]
    return None


def _powershell_profile() -> Path | None:
    for exe in ("pwsh", "powershell"):
        if path := shutil.which(exe):
            out = subprocess.run(
                [path, "-NoProfile", "-Command", "$PROFILE"], capture_output=True, text=True, check=False
            )
            if out.returncode == 0 and out.stdout.strip():
                return Path(out.stdout.strip())
    return None


def _add_block(rc_file: Path, lines: str) -> None:
    text = rc_file.read_text(encoding="utf-8") if rc_file.is_file() else ""
    if BEGIN not in text:
        rc_file.parent.mkdir(parents=True, exist_ok=True)
        rc_file.write_text(f"{text.rstrip()}\n\n{BEGIN}\n{lines}{END}\n".lstrip(), encoding="utf-8")


def _remove_block(rc_file: Path) -> None:
    if not rc_file.is_file():
        return
    text = rc_file.read_text(encoding="utf-8")
    if BEGIN in text and END in text:
        before, rest = text.split(BEGIN, 1)
        after = rest.split(END, 1)[1]
        rc_file.write_text(before.rstrip() + "\n" + after.lstrip("\n"), encoding="utf-8")


def install_completion(shell: str) -> dict[str, list[str]]:
    """Write the completion script where the shell finds it; returns what was written."""
    script = completion.SCRIPTS[shell]
    data = _home_dir("XDG_DATA_HOME", ".local/share")
    record: dict[str, list[str]] = {"files": [], "blocks": []}
    if shell == "bash":  # loaded on demand by bash-completion
        target = data / "bash-completion" / "completions" / "satyrn"
    elif shell == "zsh":
        target = data / "zsh" / "site-functions" / "_satyrn"
        rc_file = _home_dir("ZDOTDIR", "") / ".zshrc"
        _add_block(rc_file, f"fpath=({target.parent} $fpath)\nautoload -Uz compinit && compinit\n")
        record["blocks"].append(str(rc_file))
    elif shell == "fish":
        target = _home_dir("XDG_CONFIG_HOME", ".config") / "fish" / "completions" / "satyrn.fish"
    else:
        profile = _powershell_profile()
        if profile is None:
            raise SystemExit("PowerShell not found; run `satyrn completion powershell` and add it to your profile")
        _add_block(profile, "satyrn completion powershell | Out-String | Invoke-Expression\n")
        record["blocks"].append(str(profile))
        return record
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(script, encoding="utf-8")
    record["files"].append(str(target))
    return record


def install(layout: Layout, shell: str | None) -> int:
    installer = _installer()
    if installer is None:
        raise SystemExit(
            "Installing the `satyrn` command needs uv or pipx; install one of them:\n"
            "  https://docs.astral.sh/uv/getting-started/installation/\n"
            f"Without installing, run: {Path(sys.executable).name} satyrn.py <command>"
        )
    name, command = installer
    print(f"installing the `satyrn` command with {name}, linked to {layout.root} ...", flush=True)
    subprocess.run([*command, str(layout.root)], check=True)
    record: dict = {"installer": name, "files": [], "blocks": []}
    shell = shell or current_shell()
    if shell is None:
        print("tab completion: unknown shell; install it later with `satyrn install --shell SHELL`")
    else:
        written = install_completion(shell)
        record["files"] += written["files"]
        record["blocks"] += written["blocks"]
        print(f"tab completion for {shell}: {', '.join(written['files'] + written['blocks'])}")
        print("  open a new terminal to use it")
    layout.runtime.mkdir(parents=True, exist_ok=True)
    layout.install_record.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    on_path = shutil.which("satyrn")
    if on_path is None:
        hint = "uv tool update-shell" if name == "uv" else "pipx ensurepath"
        print(f"\n`satyrn` is installed but not on your PATH yet: run `{hint}` and open a new terminal.")
    print("\nNext: run `satyrn` - it shows what is missing and guides you through it.")
    return 0


def uninstall(layout: Layout) -> int:
    try:
        record = json.loads(layout.install_record.read_text(encoding="utf-8"))
    except FileNotFoundError:
        record = {"installer": None, "files": [], "blocks": []}
    for file in record["files"]:
        Path(file).unlink(missing_ok=True)
        print(f"removed {file}")
    for rc_file in record["blocks"]:
        _remove_block(Path(rc_file))
        print(f"removed the satyrn lines from {rc_file}")
    names = [record["installer"]] if record["installer"] else ["uv", "pipx"]
    for name in names:
        if exe := shutil.which(name):
            command = [exe, "tool", "uninstall", DISTRIBUTION] if name == "uv" else [exe, "uninstall", DISTRIBUTION]
            if subprocess.run(command, check=False).returncode == 0:
                break
    layout.install_record.unlink(missing_ok=True)
    print(f"The `satyrn` command is removed. {layout.root} with its .runtime/ stays; delete it to remove the rest.")
    return 0

"""Workspace-confined tools the model can call to inspect and write code."""

from __future__ import annotations

import difflib
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from ds4py.engine.tool_prompt import ToolDefinition

MAX_READ_BYTES = 200_000
MAX_LIST_ENTRIES = 500
SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", ".devenv", ".ds4", ".mypy_cache", ".ruff_cache"}

type Confirm = Callable[[str], bool]


def _str_param(description: str) -> dict[str, object]:
    return {"type": "string", "description": description}


TOOL_DEFINITIONS: tuple[ToolDefinition, ...] = (
    ToolDefinition(
        "list_files",
        "List files under a directory of the workspace (recursive, skips VCS and virtualenv dirs).",
        {
            "type": "object",
            "properties": {"path": _str_param("Directory relative to the workspace root; '.' for root.")},
            "required": ["path"],
        },
    ),
    ToolDefinition(
        "read_file",
        "Read a UTF-8 text file from the workspace.",
        {
            "type": "object",
            "properties": {"path": _str_param("File path relative to the workspace root.")},
            "required": ["path"],
        },
    ),
    ToolDefinition(
        "write_file",
        "Create or overwrite a file in the workspace with the complete new content.",
        {
            "type": "object",
            "properties": {
                "path": _str_param("File path relative to the workspace root."),
                "content": _str_param("The full file content."),
            },
            "required": ["path", "content"],
        },
    ),
    ToolDefinition(
        "edit_file",
        "Replace one exact, unique occurrence of old_text with new_text in an existing file.",
        {
            "type": "object",
            "properties": {
                "path": _str_param("File path relative to the workspace root."),
                "old_text": _str_param("Exact text to replace; must occur exactly once."),
                "new_text": _str_param("Replacement text."),
            },
            "required": ["path", "old_text", "new_text"],
        },
    ),
    ToolDefinition(
        "run_command",
        "Run a shell command in the workspace root (e.g. tests). The user must approve each command.",
        {"type": "object", "properties": {"command": _str_param("Shell command to run.")}, "required": ["command"]},
    ),
)


class ToolError(Exception):
    """A tool call was invalid; the message is returned to the model."""


@dataclass
class Workspace:
    """Executes tool calls, confined to ``root``. Mutations go through ``confirm``."""

    root: Path
    confirm: Confirm = field(default=lambda _summary: True)
    allow_commands: bool = True
    command_timeout: float = 120.0
    changed: list[Path] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.root = self.root.expanduser().resolve()

    # -- helpers -----------------------------------------------------------
    def _resolve(self, raw: object) -> Path:
        if not isinstance(raw, str) or not raw:
            raise ToolError("path must be a non-empty string")
        path = (self.root / raw).resolve()
        if not path.is_relative_to(self.root):
            raise ToolError(f"{raw!r} is outside the workspace")
        return path

    def _rel(self, path: Path) -> str:
        return str(path.relative_to(self.root)) or "."

    @staticmethod
    def _text(args: Mapping[str, object], name: str) -> str:
        value = args.get(name)
        if not isinstance(value, str):
            raise ToolError(f"{name} must be a string")
        return value

    # -- dispatch ----------------------------------------------------------
    def call(self, name: str, args: Mapping[str, object]) -> str:
        """Run one tool; always returns text for the model, never raises ToolError."""
        handler = getattr(self, f"tool_{name}", None)
        if handler is None:
            return f"error: unknown tool {name!r}"
        try:
            return handler(args)
        except ToolError as error:
            return f"error: {error}"
        except OSError as error:
            return f"error: {type(error).__name__}: {error}"

    # -- tools -------------------------------------------------------------
    def tool_list_files(self, args: Mapping[str, object]) -> str:
        base = self._resolve(args.get("path", ".") or ".")
        if not base.is_dir():
            raise ToolError(f"{self._rel(base)} is not a directory")
        entries: list[str] = []
        for path in sorted(base.rglob("*")):
            if any(part in SKIP_DIRS for part in path.relative_to(self.root).parts):
                continue
            if path.is_file():
                entries.append(self._rel(path))
                if len(entries) >= MAX_LIST_ENTRIES:
                    entries.append(f"... truncated at {MAX_LIST_ENTRIES} entries")
                    break
        return "\n".join(entries) or "(empty)"

    def tool_read_file(self, args: Mapping[str, object]) -> str:
        path = self._resolve(args.get("path"))
        if not path.is_file():
            raise ToolError(f"{self._rel(path)} does not exist")
        data = path.read_bytes()[:MAX_READ_BYTES]
        return data.decode("utf-8", errors="replace")

    def tool_write_file(self, args: Mapping[str, object]) -> str:
        path = self._resolve(args.get("path"))
        content = self._text(args, "content")
        old = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
        return self._apply(path, old, content, "create" if not path.exists() else "overwrite")

    def tool_edit_file(self, args: Mapping[str, object]) -> str:
        path = self._resolve(args.get("path"))
        if not path.is_file():
            raise ToolError(f"{self._rel(path)} does not exist")
        old_text, new_text = self._text(args, "old_text"), self._text(args, "new_text")
        old = path.read_text(encoding="utf-8")
        count = old.count(old_text)
        if count != 1:
            raise ToolError(f"old_text occurs {count} times in {self._rel(path)}; it must occur exactly once")
        return self._apply(path, old, old.replace(old_text, new_text, 1), "edit")

    def tool_run_command(self, args: Mapping[str, object]) -> str:
        command = self._text(args, "command")
        if not self.allow_commands:
            raise ToolError("command execution is disabled (--no-commands)")
        if not self.confirm(f"run command in {self.root}:\n  $ {command}"):
            return "the user declined to run this command"
        try:
            proc = subprocess.run(  # noqa: S602 - user-approved shell command
                command,
                shell=True,
                cwd=self.root,
                capture_output=True,
                text=True,
                timeout=self.command_timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return f"error: command timed out after {self.command_timeout:g}s"
        out = (proc.stdout + proc.stderr)[-20_000:]
        return f"exit code {proc.returncode}\n{out}"

    def _apply(self, path: Path, old: str, new: str, verb: str) -> str:
        rel = self._rel(path)
        if old == new:
            return f"{rel} unchanged"
        diff = "".join(
            difflib.unified_diff(old.splitlines(keepends=True), new.splitlines(keepends=True), f"a/{rel}", f"b/{rel}")
        )
        if not self.confirm(f"{verb} {rel}:\n{diff}"):
            return f"the user rejected the change to {rel}"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(new, encoding="utf-8")
        self.changed.append(path)
        return f"wrote {rel} ({len(new.encode())} bytes)"

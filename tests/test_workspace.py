"""Workspace tools against the real filesystem and real subprocesses (no model needed)."""

from __future__ import annotations

from pathlib import Path

import pytest

from satyrn_codegen.cli import main
from satyrn_codegen.tools import Workspace


@pytest.mark.parametrize("path", ["../escape.py", "/etc/passwd"])
def test_paths_outside_workspace_are_refused(tmp_path: Path, path: str) -> None:
    ws = Workspace(tmp_path)
    assert ws.call("read_file", {"path": path}).startswith("error:")
    assert ws.call("write_file", {"path": path, "content": "x"}).startswith("error:")


def test_write_read_and_list(tmp_path: Path) -> None:
    ws = Workspace(tmp_path)
    assert ws.call("write_file", {"path": "pkg/mod.py", "content": "x = 1\n"}).startswith("wrote pkg/mod.py")
    assert ws.call("read_file", {"path": "pkg/mod.py"}) == "x = 1\n"
    assert ws.call("list_files", {"path": "."}) == "pkg/mod.py"
    assert ws.changed == [tmp_path.resolve() / "pkg/mod.py"]


def test_rejected_change_is_not_written(tmp_path: Path) -> None:
    ws = Workspace(tmp_path, confirm=lambda _summary: False)
    assert "rejected" in ws.call("write_file", {"path": "a.py", "content": "x"})
    assert not (tmp_path / "a.py").exists()


def test_edit_file_requires_unique_match(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x = 1\nx = 1\n")
    ws = Workspace(tmp_path)
    assert "occurs 2 times" in ws.call("edit_file", {"path": "a.py", "old_text": "x = 1", "new_text": "y"})
    assert ws.call("edit_file", {"path": "a.py", "old_text": "x = 1\nx", "new_text": "y = 2\nx"}).startswith("wrote")
    assert (tmp_path / "a.py").read_text() == "y = 2\nx = 1\n"


def test_run_command_executes_in_workspace(tmp_path: Path) -> None:
    ws = Workspace(tmp_path)
    assert ws.call("run_command", {"command": "pwd"}) == f"exit code 0\n{tmp_path.resolve()}\n"


def test_run_command_respects_disable_and_decline(tmp_path: Path) -> None:
    assert "disabled" in Workspace(tmp_path, allow_commands=False).call("run_command", {"command": "true"})
    assert "declined" in Workspace(tmp_path, confirm=lambda _s: False).call("run_command", {"command": "true"})


def test_cli_requires_a_model() -> None:
    assert main(["--model", "", "do something"]) == 2


def test_cli_reports_missing_model_file(tmp_path: Path) -> None:
    assert main(["--model", str(tmp_path / "missing.gguf"), "do something"]) == 2


def test_cli_reports_missing_native_library_cleanly(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    model = tmp_path / "model.gguf"
    model.write_bytes(b"")
    code = main(["--model", str(model), "--lib", str(tmp_path / "libds4.so"), "-C", str(tmp_path), "hi"])
    assert code == 1
    assert "library not found" in capsys.readouterr().err

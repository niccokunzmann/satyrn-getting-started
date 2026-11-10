"""The tool-calling loop: user prompt -> model rounds -> tool calls -> results -> ... -> answer."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, TextIO

from ds4py.engine.events import ReserveReached, Stopped, TextDelta, ToolCalls, ToolSyntax

from .tools import TOOL_DEFINITIONS, Workspace

if TYPE_CHECKING:
    from ds4py import Session
    from ds4py.engine.tool_syntax.model import ToolCall

SYSTEM_PROMPT = """\
You are satyrn-codegen, a local coding assistant working inside the user's workspace.
Turn the user's natural-language request into working code.

Rules:
- Use list_files and read_file to understand existing code before changing it.
- Create or change files ONLY with write_file or edit_file; never just print code you meant to save.
- Prefer small, focused edits (edit_file) to existing files; use write_file for new files.
- Use run_command to run tests or the program when that helps verify your work.
- Paths are relative to the workspace root.
- When finished, reply with a short summary of what you changed and how to run it.
"""

DIM, RESET = "\033[2m", "\033[0m"


@dataclass
class TurnResult:
    text: str = ""
    rounds: int = 0
    tool_calls: int = 0
    stop_reason: str | None = None
    files_changed: list[str] = field(default_factory=list)


class CodegenAgent:
    """Drives one ds4py chat ``Session`` (already configured by satyrn_agent) as a coding agent."""

    def __init__(
        self,
        session: Session,
        workspace: Workspace,
        *,
        max_tokens: int = 8192,
        max_steps: int = 25,
        show_thinking: bool = False,
        out: TextIO | None = None,
        err: TextIO | None = None,
        color: bool | None = None,
    ) -> None:
        self.session = session
        self.workspace = workspace
        self.max_tokens = max_tokens
        self.max_steps = max_steps
        self.show_thinking = show_thinking
        self.out = out if out is not None else sys.stdout
        self.err = err if err is not None else sys.stderr
        self.color = self.err.isatty() if color is None else color
        self._started = False

    def _start(self) -> None:
        if not self._started:
            # Tools and instructions can only be set once, when the chat begins.
            self.session.start_chat(tools=TOOL_DEFINITIONS, instructions=SYSTEM_PROMPT)
            self._started = True

    def _note(self, text: str) -> None:
        self.err.write(f"{DIM}{text}{RESET}\n" if self.color else f"{text}\n")
        self.err.flush()

    def ask(self, prompt: str) -> TurnResult:
        """Run one user request to completion (possibly many model rounds)."""
        self._start()
        result = TurnResult()
        before = len(self.workspace.changed)
        self.session.append_user(prompt)
        for _ in range(self.max_steps):
            calls, reason = self._round(result)
            result.rounds += 1
            result.stop_reason = reason
            if not calls:
                break
            outputs = []
            for call in calls:
                summary = ", ".join(f"{k}={str(v)[:60]!r}" for k, v in call.args.items() if k != "content")
                self._note(f"→ {call.name}({summary})")
                output = self.workspace.call(call.name, call.args)
                self._note(f"  {output.splitlines()[0] if output else '(no output)'}")
                outputs.append(f"[{call.name}]\n{output}")
                result.tool_calls += 1
            self.session.append_tool_results(outputs)
        else:
            self._note(f"stopped after {self.max_steps} tool steps (--max-steps)")
        result.files_changed = [str(p.relative_to(self.workspace.root)) for p in self.workspace.changed[before:]]
        return result

    def _round(self, result: TurnResult) -> tuple[list[ToolCall], str | None]:
        """Run one model round; stream visible text, collect tool calls."""
        calls: list[ToolCall] = []
        reason: str | None = None
        stream = _TextStream(self)
        events = self.session.run_round(max_tokens=self.max_tokens)
        try:
            for event in events:
                if isinstance(event, ToolSyntax):
                    stream.in_tool_markup = event.state != "SEARCH"
                elif isinstance(event, TextDelta):
                    stream.write(event)
                elif isinstance(event, ToolCalls):
                    calls.extend(event.calls)
                elif isinstance(event, ReserveReached):
                    event.fail()  # out of context: end this assistant turn cleanly
                elif isinstance(event, Stopped):
                    reason = event.reason
        except KeyboardInterrupt:
            self.session.cancel()  # ask the worker to stop, then drain the round
            events.close()
            raise
        result.text += stream.finish()
        if reason not in (None, "stop_token", "tool_call_complete"):
            self._note(f"[round stopped: {reason}]")
        return calls, reason


@dataclass
class _TextStream:
    """Prints one round's visible text: hides tool-call markup, routes thinking to stderr."""

    agent: CodegenAgent
    in_tool_markup: bool = False  # ds4py streams <tool_call> markup as TextDelta too
    thinking_open: bool = False
    printed: str = ""

    def write(self, event: TextDelta) -> None:
        if self.in_tool_markup:
            return
        agent = self.agent
        if event.thinking:
            if agent.show_thinking:
                agent.err.write(f"{DIM}{event.text}{RESET}" if agent.color else event.text)
                agent.err.flush()
                self.thinking_open = True
            return
        if self.thinking_open:
            agent.err.write("\n")
            self.thinking_open = False
        text = event.text if self.printed else event.text.lstrip()  # drop blank lines after </think>
        if text:
            agent.out.write(text)
            agent.out.flush()
            self.printed += text

    def finish(self) -> str:
        if self.printed.strip() and not self.printed.endswith("\n"):
            self.agent.out.write("\n")
        return self.printed

"""Rate the prepared models for this computer and rank them, for `satyrn models` and the guide."""

from __future__ import annotations

from dataclasses import dataclass

from . import agentconfig, settings
from .layout import Layout, Pins
from .machine import Machine

HEADROOM_GB = 4.0  # memory left for the system and other programs
DISK_MARGIN_GB = 1.0


@dataclass(frozen=True)
class Choice:
    model: str
    info: dict
    fit: str  # "fits on GPU", "fits", "tight", "too big" or "not enough disk"
    pulled: bool
    default: bool

    @property
    def usable(self) -> bool:
        return self.fit in {"fits", "fits on GPU", "tight"}

    @property
    def slow(self) -> bool:
        return bool(self.info.get("dense")) and self.fit != "fits on GPU"

    @property
    def score(self) -> tuple[float, float]:
        """Rank: most reliable first, then fastest (benchmark results)."""
        bench = self.info.get("benchmark", {})
        runs = bench.get("runs") or 0
        return (-(bench.get("passed", 0) / runs) if runs else 0.0, bench.get("median_s", float("inf")))


def rate(info: dict, machine: Machine, *, pulled: bool) -> str:
    need = float(info.get("memory_gb", 0))
    if not pulled and machine.free_disk_gb < float(info.get("download_gb", 0)) + DISK_MARGIN_GB:
        return "not enough disk"
    if machine.gpu_memory_gb >= need > 0:
        return "fits on GPU"
    if machine.memory_gb >= need + HEADROOM_GB:
        return "fits"
    if machine.memory_gb >= need:
        return "tight"
    return "too big"


def choices(layout: Layout, pins: Pins, machine: Machine) -> list[Choice]:
    """All prepared models, best first."""
    default = settings.default_model(layout, pins)
    found = []
    for model, info in agentconfig.load_models(layout).items():
        pulled = settings.is_pulled(layout, model)
        found.append(Choice(model, info, rate(info, machine, pulled=pulled), pulled, model == default))
    return sorted(found, key=lambda c: (not c.usable, c.fit == "tight", c.score))


def recommended(found: list[Choice]) -> Choice | None:
    return next((c for c in found if c.usable and c.fit != "tight" and not c.slow), None) or next(
        (c for c in found if c.usable), None
    )


def _minutes(seconds: float) -> str:
    return f"{int(seconds // 60)}:{int(seconds % 60):02d}"


def table(found: list[Choice], machine: Machine) -> str:
    best = recommended(found)
    lines = [
        f"This computer: {machine.describe()}",
        "",
        "  #  Model              Download  Memory  This computer    Small program*  Passed*",
    ]
    for number, choice in enumerate(found, 1):
        bench = choice.info.get("benchmark", {})
        fit = choice.fit + (", slow" if choice.slow and choice.usable else "")
        notes = [
            note
            for note, present in (
                ("recommended", choice is best),
                ("downloaded", choice.pulled),
                ("your default", choice.default),
            )
            if present
        ]
        lines.append(
            f"  {number}  {choice.model:<17} {choice.info.get('download_gb', 0):>5.0f} GB"
            f" {choice.info.get('memory_gb', 0):>4.0f} GB  {fit:<16}"
            f" {_minutes(bench['median_s']) if 'median_s' in bench else '-':>8}"
            f"       {f'{bench["passed"]}/{bench["runs"]}' if 'runs' in bench else '-':<5}"
            f"  {', '.join(notes)}".rstrip()
        )
    if best is None:
        lines += ["", "  No prepared model fits this computer: free up disk space or use one with more memory."]
    machine_note = next((c.info.get("benchmark_machine") for c in found if c.info.get("benchmark_machine")), "")
    lines += [
        "",
        f"  * on {machine_note}: median time to write and check sqrt.py,",
        "    and the runs that passed in two benchmark rounds",
    ]
    return "\n".join(lines)


def selection_help(found: list[Choice]) -> str:
    """How to select a model, with the recommended one (else the first) as the example."""
    example = recommended(found) or (found[0] if found else None)
    if example is None:
        return ""
    number, name = found.index(example) + 1, example.model
    commands = [
        (f"satyrn pull {name}", "download it, if it is not downloaded yet"),
        (f"satyrn use {name}", f"make it your default (or by number: satyrn use {number})"),
        (f"satyrn code DIR -m {name}", "use a model just once"),
    ]
    width = max(len(command) for command, _ in commands) + 2
    return "How to select a model:\n" + "\n".join(f"  {command:<{width}} {text}" for command, text in commands)


def by_number(found: list[Choice], answer: str) -> str:
    """A model name for a row number of the list (as shown by `satyrn models`); names pass through."""
    if answer.isdigit():
        if not 1 <= int(answer) <= len(found):
            raise SystemExit(f"there is no model number {answer}; see `satyrn models`")
        return found[int(answer) - 1].model
    return answer

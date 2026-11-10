"""Natural-language code generation CLI built on satyrn-agent (Satyrn's own engine, Apple Silicon).

The engine (satyrn-agent, ds4py) is an optional extra, `satyrn-cli[engine]`, so the names below
are imported only when used: the `satyrn-codegen` command can then explain what is missing.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .agent import CodegenAgent
    from .tools import Workspace

__all__ = ["CodegenAgent", "Workspace"]


def __getattr__(name: str) -> object:
    if name == "CodegenAgent":
        from .agent import CodegenAgent  # noqa: PLC0415 - optional engine, imported on use

        return CodegenAgent
    if name == "Workspace":
        from .tools import Workspace  # noqa: PLC0415

        return Workspace
    raise AttributeError(name)

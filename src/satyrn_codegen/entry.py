"""Entry point of `satyrn-codegen`: explain a missing engine instead of crashing on import."""

from importlib.util import find_spec

DOCS = "https://niccokunzmann.github.io/satyrn-getting-started/satyrn-engine.html"


def main() -> int:
    missing = [name for name in ("ds4py", "satyrn_agent") if find_spec(name) is None]
    if missing:
        raise SystemExit(
            f"satyrn-codegen needs Satyrn's own engine, which is not installed ({', '.join(missing)} missing).\n"
            "It runs on Apple Silicon Macs only; install it there with `make install-codegen`.\n"
            f"See {DOCS}\n"
            "On other computers, use `satyrn` (Open Interpreter on Ollama)."
        )
    from .cli import main as cli_main  # noqa: PLC0415 - only after the check above

    return cli_main()

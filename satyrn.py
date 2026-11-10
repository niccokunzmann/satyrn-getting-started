#!/usr/bin/env python3
"""Entry point: python satyrn.py <setup|start|stop|status|interpreter|...>

Standard library only. Needs Python 3.14+ (for .tar.zst support in tarfile); with uv you can
run it without installing Python yourself:  uv run --no-project --python 3.14 satyrn.py setup
"""

import sys
from pathlib import Path

if sys.version_info < (3, 14):  # noqa: UP036 - guard for users starting it with an older Python
    sys.exit(
        f"satyrn.py needs Python 3.14 or newer (this is {sys.version.split()[0]}).\n"
        "Try:  uv run --no-project --python 3.14 satyrn.py " + " ".join(sys.argv[1:])
    )

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from satyrn_local.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main(ROOT))

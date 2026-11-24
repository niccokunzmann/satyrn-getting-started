"""Make satyrn-models' CPT dataset for one Python version. Runs in `satyrn data`'s own venv.

The steps of satyrn-models' docs/dataset_generator.md, with its own code (corpus_builder), but
every input taken from the pinned checkouts instead of the newest version on the internet:

1. ``collect-doc-changes``: the sections of the CPython docs that changed in the version,
2. the version's PEPs and What's New page, the files ``download-inputs`` would fetch,
3. ``cpt``: everything converted to Markdown, one JSON line per document.

Each step runs in a process of its own, as the separate commands of satyrn-models do: the
CPython docs' Sphinx extensions register their directives for the whole process, and the
plain Sphinx of ``cpt`` must not see them. Sphinx's output goes to the log file; the terminal
gets a line or two per step.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import time
from pathlib import Path

from satyrn.dataset import cpt
from satyrn.dataset.inputs import collect_doc_changes
from satyrn.dataset.inputs.download_inputs import SOURCES

STEPS = ("collect", "inputs", "cpt")


def source_file(url: str, cpython: Path, peps: Path) -> Path:
    """The pinned local copy of a file that download-inputs fetches from a repository's main branch."""
    for repo, root in (("python/peps", peps), ("python/cpython", cpython)):
        prefix = f"https://raw.githubusercontent.com/{repo}/main/"
        if url.startswith(prefix):
            return root / url.removeprefix(prefix)
    raise SystemExit(f"unexpected source {url}")


def main() -> int:
    p = argparse.ArgumentParser()
    for name in ("satyrn-models", "cpython", "peps", "output", "log"):
        p.add_argument(f"--{name}", type=Path, required=True)
    p.add_argument("--version", required=True)
    p.add_argument("--step", choices=STEPS, required=True)
    args = p.parse_args()

    terminal = os.fdopen(os.dup(1), "w", buffering=1)
    args.log.parent.mkdir(parents=True, exist_ok=True)
    with args.log.open("w" if args.step == STEPS[0] else "a", encoding="utf-8") as log:
        os.dup2(log.fileno(), 1)
        os.dup2(log.fileno(), 2)
        print(f"== {args.step}", flush=True)
        inputs = args.satyrn_models / "datasets" / f"python{args.version}" / "input"
        started = time.monotonic()
        if args.step == "collect":
            terminal.write("  reading the CPython documentation, collecting what changed (about 2 minutes)\n")
            if inputs.exists():
                shutil.rmtree(inputs)  # nothing left over from an earlier run
            # A fresh Sphinx cache each time, so that the result never depends on an earlier run.
            shutil.rmtree(collect_doc_changes.DOCTREE_CACHE_DIRECTORY, ignore_errors=True)
            os.chdir(args.satyrn_models)  # collect-doc-changes writes below the checkout
            collect_doc_changes.main([args.version, str(args.cpython / "Doc")], standalone_mode=False)
            changes = sorted((inputs / "docs" / "changes").rglob("*.rst"))
            terminal.write(f"  {len(changes)} documents with changes ({time.monotonic() - started:.0f} s)\n")
        elif args.step == "inputs":
            documents = SOURCES[args.version]["docs"]
            for name, url in documents.items():
                shutil.copyfile(source_file(url, args.cpython, args.peps), inputs / "docs" / f"{name}.rst")
            terminal.write(f"  added the PEPs and What's New: {', '.join(documents)}\n")
        else:
            terminal.write("  converting everything to Markdown\n")
            args.output.parent.mkdir(parents=True, exist_ok=True)
            cpt.main(["--input-dir", str(inputs / "docs"), "--output", str(args.output)], standalone_mode=False)
            terminal.write(f"  done ({time.monotonic() - started:.0f} s)\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

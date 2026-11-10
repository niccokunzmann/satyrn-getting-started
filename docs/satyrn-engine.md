# Satyrn's own engine (Apple Silicon)

Besides Open Interpreter on Ollama, this project contains `satyrn-codegen`, a small coding CLI
on top of [satyrn-agent](https://github.com/satyrn-ai/satyrn-agent). That engine runs the
dense Qwen3.8-27B model with DFlash speculative decoding, where a small drafter model proposes
tokens that the large model checks in parallel.

```{important}
satyrn-agent's dense model path runs on Apple's Metal only. You need an Apple Silicon Mac with
macOS 15 or newer and 32 GB or more of unified memory. On Linux and Windows, use Open
Interpreter as described in [Set up](setup.md); the same base model is available there as
`qwen3.8:27b` (see [Choose a model](models.md)).
```

This path has not been tested on a Mac by this project yet.

## Setup

1. Clone [satyrn-agent](https://github.com/satyrn-ai/satyrn-agent) next to this project, so
   that both folders share a parent folder.
2. Download the pinned model pair as described in satyrn-agent's README (section *Models*):
   `Qwen3.8-27B-Q4_K_M.gguf` (the model) and `dflash-Qwen3.8-27B-Q4_0.gguf` (the drafter).
3. Build the patched `libds4` in satyrn-agent: `ds4-check --model qwen35 --build`. The
   library goes to `~/.ds4py/lib/libds4.dylib`.
4. Install the CLI with [pipx](https://pipx.pypa.io/) and run it:

```bash
make install-codegen   # builds satyrn-agent and satyrn-codegen wheels, installs them with pipx
export SATYRN_MODEL=~/models/Qwen3.8-27B-Q4_K_M.gguf
export SATYRN_DRAFTER=~/models/dflash-Qwen3.8-27B-Q4_0.gguf
satyrn-codegen "create a program that takes a number and outputs the square root of it"
satyrn-codegen -i  # conversation; /exit leaves
```

The model asks for tools (list, read, write and edit files, run commands), and you approve
every change unless you pass `-y`. Other options: `-C DIR` (folder to work in),
`--dflash auto|on|off`, `--think none…max`, `--no-commands`, `--show-thinking`.
`satyrn-codegen --help` lists all of them.

The same square-root test exists for this path:
`uv run pytest -m live tests/test_live_sqrt.py`.

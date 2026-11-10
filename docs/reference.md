# Reference

## `satyrn.py` commands

Run them as `python3.14 satyrn.py COMMAND` (Windows: `py -3.14 satyrn.py COMMAND`).

| Command | What it does |
| --- | --- |
| `setup [--model M] [--no-model]` | Download, verify and unpack Ollama and Open Interpreter, write their settings, pull the default model (or `M`). |
| `start` | Start the Ollama server in the background. |
| `stop` | Stop the server started with `start`. |
| `serve` | Run the server in the foreground; {kbd}`Ctrl+C` stops it. |
| `status` | Show the server, the installed models and the loaded ones. |
| `interpreter ARGS…` | Run the project's Open Interpreter with the project's settings. All arguments are passed on, for example `--oss`, `-m MODEL`, `-C DIR`, `exec`. |
| `ollama ARGS…` | Run the project's Ollama command line, for example `ollama list` or `ollama rm MODEL`. |
| `pull MODEL` | Download another model and compare its digest with `pins.toml`. |
| `check [--model M] [--effort E] [--timeout S]` | The model writes `sqrt.py` through `interpreter exec`; the program is then run and its output checked. |
| `bench [MODEL…] [--runs N] [--effort E] [--timeout S]` | Time models on the same task; default: every model in `config/models.toml`, one run each. |
| `verify` | Re-check every pinned archive, unpacked tool and pulled model. |

`--effort` sets the reasoning effort for models that have one (`gpt-oss:20b`: `low`, `medium`,
`high`). `--timeout` is the time limit per run in seconds, 3600 by default.

## `make` targets

The Makefile is only a shortcut on systems with `make`; all logic is in `satyrn.py`.

| Target | Same as |
| --- | --- |
| `make setup`, `start`, `stop`, `serve`, `status`, `verify`, `check`, `bench` | `python3.14 satyrn.py …` |
| `make oss` | `python3.14 satyrn.py interpreter --oss` |
| `make test`, `test-live`, `lint`, `format`, `docs` | see [Contributing](contributing.md) |
| `make install` | install `satyrn-codegen` with pipx ([Satyrn's own engine](satyrn-engine.md)) |

## Files you may edit

`pins.toml`
: Default model, model digests, context window, port, tool versions and checksums.

`config/instructions.md`
: The system prompt every local model gets.

`config/models.toml`
: The models Open Interpreter knows how to drive, with their reasoning efforts.

`config/interpreter.toml`
: Open Interpreter settings. After editing, run `python3.14 satyrn.py setup` again.

## Environment

`satyrn.py` sets these for the tools it starts; you do not need to set them yourself.

| Variable | Value | Why |
| --- | --- | --- |
| `INTERPRETER_HOME` | `.runtime/interpreter-home` | keeps the interpreter's settings out of `~/.openinterpreter` |
| `CODEX_OSS_BASE_URL` | `http://127.0.0.1:11434/v1` | where `--oss` finds the model server |
| `OLLAMA_HOST` | `127.0.0.1:11434` | the server listens on this computer only |
| `OLLAMA_MODELS` | `.runtime/models` | model files stay in the project |
| `OLLAMA_CONTEXT_LENGTH` | `32768` | context window offered to the interpreter |
| `OLLAMA_KEEP_ALIVE` | `30m` unless you set it | how long an idle model stays in memory |
| `HOME`, `USERPROFILE` (Ollama only) | `.runtime/home` | Ollama's key pair stays out of `~/.ollama` |

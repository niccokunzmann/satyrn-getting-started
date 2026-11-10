# Reference

## `satyrn` commands

Without the installed command, write `python3.14 satyrn.py COMMAND` in the project folder
(Windows: `py -3.14 satyrn.py COMMAND`).

| Command | What it does |
| --- | --- |
| *(none)* | Show what is ready and offer each missing step: tools, model, server. |
| `install` | Install the `satyrn` command (linked to this folder) and tab completion for your shell. Run as `python3.14 satyrn.py install`. |
| `uninstall` | Remove the command and the tab completion. The folder stays. |
| `code [DIR] [-p REQUEST] [-m MODEL]` | Work with the model in `DIR` (default: the current folder): a conversation, or one request with `-p`. `MODEL` is a listed model, by name or number. |
| `models` | Rate every prepared model for this computer, with benchmark results. |
| `use MODEL` | Make a listed model your default, by name or by its number in `satyrn models`. |
| `setup [--model M] [--no-model]` | Download, verify and unpack Ollama and Open Interpreter, write their settings, download the default model (or `M`). |
| `pull MODEL` | Download a model; asks first if the available build differs from `pins.toml`. |
| `start` / `stop` | Start the Ollama server in the background / stop it. |
| `serve` | Run the server in the foreground; {kbd}`Ctrl+C` stops it. |
| `status` | Show the server, the installed models and the loaded ones. |
| `check [--model M] [--effort E] [--timeout S]` | The model writes `sqrt.py`; the program is then run and its output checked. |
| `bench [MODEL…] [--runs N] [--warm] [--instructions FILE] [--set KEY=VALUE] [--effort E] [--timeout S]` | Time models on the same task; default: every model in `config/models.toml`, one run each. |
| `verify` | Re-check every pinned archive, unpacked tool and downloaded model (accepted model versions pass). |
| `interpreter ARGS…` | Run the project's Open Interpreter with the project's settings; all arguments are passed on. |
| `ollama ARGS…` | Run the project's Ollama command line, for example `satyrn ollama list`. |
| `completion SHELL` | Print the tab-completion script for `bash`, `zsh`, `fish` or `powershell`. |

`--effort` sets the reasoning effort for models that have one (`gpt-oss:20b`: `low`, `medium`,
`high`). `--timeout` is the time limit per run in seconds, 3600 by default.

## `make` targets

The Makefile is only a shortcut on systems with `make`; all logic is in `satyrn.py`.

| Target | Same as |
| --- | --- |
| `make setup`, `start`, `stop`, `serve`, `status`, `verify`, `check`, `bench` | `satyrn …` |
| `make oss` | `satyrn code` |
| `make test`, `test-live`, `lint`, `format`, `html`, `livehtml` | see [Contributing](contributing.md) |
| `make install` | `python3.14 satyrn.py install` |
| `make install-codegen` | install `satyrn-codegen` with pipx ([Satyrn's own engine](satyrn-engine.md)) |

## Files you may edit

`pins.toml`
: Default model, model digests, context window, port, tool versions and checksums.

`config/instructions.md`
: The system prompt every local model gets.

`config/models.toml`
: The models Open Interpreter knows how to drive: reasoning efforts, sizes and benchmark results for
  `satyrn models`.

`config/interpreter.toml`
: Open Interpreter settings. After editing, run `satyrn setup` again.

## Environment

`satyrn.py` sets these for the tools it starts; you do not need to set them yourself.

| Variable | Value | Why |
| --- | --- | --- |
| `INTERPRETER_HOME` | `.runtime/interpreter-home` | keeps the interpreter's settings out of `~/.openinterpreter` |
| `CODEX_OSS_BASE_URL` | `http://127.0.0.1:11434/v1` | where `--oss` finds the model server |
| `OLLAMA_HOST` | `127.0.0.1:11434` | the server listens on this computer only |
| `OPEN_INTERPRETER_PRODUCT_NAME` | `Satyrn` | the name Open Interpreter shows; not supported by 0.0.60 yet |
| `OLLAMA_MODELS` | `.runtime/models` | model files stay in the project |
| `OLLAMA_CONTEXT_LENGTH` | `32768` | context window offered to the interpreter |
| `OLLAMA_KEEP_ALIVE` | `30m` unless you set it | how long an idle model stays in memory |
| `HOME`, `USERPROFILE` (Ollama only) | `.runtime/home` | Ollama's key pair stays out of `~/.ollama` |

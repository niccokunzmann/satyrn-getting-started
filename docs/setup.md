# Set up

Two commands install everything; the `satyrn` command then guides you through the rest. Every
question it asks has a default, so you can press {kbd}`Enter` throughout.

## What you need

| | Minimum | Notes |
| --- | --- | --- |
| Computer | 64-bit Linux, macOS or Windows | Tested on Debian 13 (Linux). The scripts support macOS and Windows, but those have not been tested yet. |
| Memory | 16 GB RAM | For the smallest benchmarked model. `satyrn models` shows which models fit your computer. |
| Disk | 20 GB free | 13–23 GB per model, about 4 GB for the tools and their downloads. |
| Processor | any recent x86-64 or ARM CPU | No GPU needed. Ollama uses a supported GPU automatically. |
| Software | `git`, Python 3.14, and uv or pipx | uv can also provide Python 3.14, see below. |
| Network | while downloading | The tools are about 4 GB, a model 13–23 GB. |

## Python 3.14

`satyrn` uses only Python's standard library, but needs version 3.14 or newer. Check with
`python3.14 --version` (Windows: `py -3.14 --version`).

If you do not have it, either install it from [python.org](https://www.python.org/downloads/)
or your package manager, or use [uv](https://docs.astral.sh/uv/getting-started/installation/),
which downloads Python 3.14 into its own cache without changing your system.

## Install the `satyrn` command

::::{tab-set}

:::{tab-item} Linux and macOS
:sync: posix

```bash
git clone https://github.com/niccokunzmann/satyrn-getting-started.git
cd satyrn-getting-started
python3.14 satyrn.py install
```

:::

:::{tab-item} Windows (PowerShell)
:sync: windows

```powershell
git clone https://github.com/niccokunzmann/satyrn-getting-started.git
cd satyrn-getting-started
py -3.14 satyrn.py install
```

:::

:::{tab-item} `uv`
:sync: uv

```bash
git clone https://github.com/niccokunzmann/satyrn-getting-started.git
cd satyrn-getting-started
uv run --no-project --python 3.14 satyrn.py install
```

:::

::::

`install` does two things:

- It installs the `satyrn` command with [uv](https://docs.astral.sh/uv/) (`uv tool install`)
  or, if uv is missing, with [pipx](https://pipx.pypa.io/). The command is linked to this
  folder: it runs the code here, and everything it downloads goes into this folder's
  `.runtime/`.
- It installs tab completion for your shell (bash, zsh, fish or PowerShell), so
  {kbd}`Tab` completes commands, options, model names and folders. Open a new terminal to use
  it. For bash it goes where the bash-completion package finds it
  (`~/.local/share/bash-completion/completions/satyrn`); for zsh and PowerShell, `install` adds
  marked lines to `~/.zshrc` or your PowerShell profile, which `uninstall` removes again.
  Completion is tested with bash; the zsh, fish and PowerShell versions are not tested yet.

If your shell reports `satyrn: command not found`, the folder with uv's or pipx's commands is
not on your `PATH` yet. `uv tool update-shell` or `pipx ensurepath` adds it.

You can also skip the installation: every `satyrn …` command on these pages works as
`python3.14 satyrn.py …` inside the folder.

## Let `satyrn` guide you

Run `satyrn` without a command. It shows what is ready and offers the next step:

```text
$ satyrn
Local code generation: what is ready

  [ ] tools    Ollama 0.40.15, Open Interpreter 0.0.60 and pi 1.5.2 are not downloaded yet
  [ ] model    gpt-oss:20b is not downloaded yet
  [ ] server   not running

Download and verify Ollama, Open Interpreter and pi now (about 4 GB)? [Y/n]
```

It then asks which coding agent `satyrn code` should use (see
[Choose the coding agent](#choose-the-coding-agent); pi is the default) and continues with the
models rated for this computer (see [Choose a model](models.md)), asks
which one to download (press {kbd}`Enter` for the recommended one, or type its number or name),
and offers to start the model server. When everything is ready, it
shows how to start working. Run `satyrn` again at any time to see where things stand; it only
asks about steps that are still missing.

The guide never starts anything without asking, and nothing starts automatically later: the
model server runs only after you start it, until you stop it or restart the computer.

## Choose the coding agent

satyrn installs two coding agents. Both work with the same models; `satyrn code` uses your
default, and `--pi` or `--open-interpreter` picks the other one for a single session.

| | [pi](https://pi.dev) (default) | [Open Interpreter](https://github.com/openinterpreter/openinterpreter) |
| --- | --- | --- |
| Tools of the model | read, write and edit files, run commands | run commands (files are written with the shell) |
| Before a command runs | nothing: pi runs every command right away | commands run in a sandbox; it may ask for approval |
| Installed from | npm, with a pinned Node.js | one pinned binary per platform |

```{warning}
pi has no sandbox and does not ask before it runs a command: the model can do whatever your
user account can do. Work in a folder made for this, as `satyrn code ~/ai-code` does, and use
Open Interpreter if you want commands confined and approved.
```

To change the default, answer the guide's question again or run:

```bash
satyrn setup --harness open-interpreter   # or: --harness pi
```

## The same steps by hand

```bash
satyrn setup --no-model        # download and verify Ollama, Open Interpreter, Node.js and pi
satyrn models                  # which models fit this computer
satyrn pull gpt-oss:20b        # download a model
satyrn use gpt-oss:20b         # make it the default
satyrn start                   # start the model server in the background
satyrn status                  # what is installed, running and loaded
```

`satyrn setup` without `--no-model` also downloads the default model. Running `setup` again is
safe: finished steps are skipped.

## Defaults

| Setting | Default | How to change it |
| --- | --- | --- |
| Coding agent | pi | `satyrn setup --harness NAME`, or `--pi` / `--open-interpreter` for one session |
| Model | the guide's recommendation, else `gpt-oss:20b` | `satyrn use MODEL`, or `-m MODEL` for one session |
| Folder the model works in | the folder you name, or the current one | `satyrn code DIR` |
| Server address | `127.0.0.1:11434`, local only | `[ollama].port` in `pins.toml` |
| Context window | 32,768 tokens | `[model].context_length` in `pins.toml` |
| Reasoning effort (`gpt-oss:20b`) | medium | `default_effort` in `config/models.toml` |
| Where everything is stored | `.runtime/` inside the project folder | not configurable |
| Time limit for `check` and `bench` | 1 hour per run | `--timeout SECONDS` |

## Check that it works

```bash
satyrn check
```

`check` asks the model to write a square-root program, then runs that program with 16, 2 and
0.25 and compares the output. It prints `SUCCESS` after about two minutes with `gpt-oss:20b` on
a laptop CPU.

## Stop and remove

```bash
satyrn stop                    # stop the model server
satyrn uninstall               # remove the `satyrn` command and its tab completion
```

Then delete the `satyrn-getting-started` folder. That removes everything else: the model, the
tools, their settings and their keys all live in its `.runtime/` subfolder.

## Troubleshooting

`satyrn: command not found`
: See [Install the `satyrn` command](#install-the-satyrn-command), or use
  `python3.14 satyrn.py` instead.

`another server already listens on port 11434`
: Another Ollama is running, for example one you installed earlier. Stop it, or set a different
  `[ollama].port` in `pins.toml`.

`Ollama is not running; start it first`
: Run `satyrn start`. The server does not survive a restart of the computer.

`satyrn.py needs Python 3.14 or newer`
: See [Python 3.14](#python-314).

The model is very slow or the computer swaps
: The model needs more memory than is free. `satyrn models` shows what fits; close other
  programs or choose a smaller model.

`... has changed since this project tested and pinned it`
: The model's publisher has released a newer build under the same name. Answer yes to use it;
  see [When a model has changed](reproducibility.md#when-a-model-has-changed) for how to avoid
  the question.

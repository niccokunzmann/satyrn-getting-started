# Set up

Setup is four commands. Each step uses a default, so you only change something if you want to.

## What you need

| | Minimum | Notes |
| --- | --- | --- |
| Computer | 64-bit Linux, macOS or Windows | Tested on Debian 13 (Linux). The scripts support macOS and Windows, but those have not been tested yet. |
| Memory | 16 GB RAM | For the default model. The larger models in [Choose a model](models.md) need up to 25 GB. |
| Disk | 20 GB free | 13 GB model, about 4 GB for the tools and their downloads. |
| Processor | any recent x86-64 or ARM CPU | No GPU needed. Ollama uses a supported GPU automatically. |
| Software | `git` and Python 3.14 | Or [uv](#python-314) instead of Python. |
| Network | for `setup` only | It downloads about 17 GB. |

## Python 3.14

`satyrn.py` uses only Python's standard library, but needs version 3.14 or newer. Check with
`python3.14 --version` (Windows: `py -3.14 --version`).

If you do not have it, either install it from [python.org](https://www.python.org/downloads/)
or your package manager, or use [uv](https://docs.astral.sh/uv/getting-started/installation/),
which downloads Python 3.14 into its own cache without changing your system. With uv, write
`uv run --no-project --python 3.14 satyrn.py` wherever these pages say `python3.14 satyrn.py`:

```bash
uv run --no-project --python 3.14 satyrn.py setup
```

## Step by step

::::{tab-set}

:::{tab-item} Linux and macOS
:sync: posix

```bash
git clone https://github.com/niccokunzmann/satyrn-getting-started.git
cd satyrn-getting-started
python3.14 satyrn.py setup
python3.14 satyrn.py start
```

:::

:::{tab-item} Windows (PowerShell)
:sync: windows

```powershell
git clone https://github.com/niccokunzmann/satyrn-getting-started.git
cd satyrn-getting-started
py -3.14 satyrn.py setup
py -3.14 satyrn.py start
```

:::

::::

`setup`
: Downloads Ollama and Open Interpreter for your platform, checks each download against the
  SHA-256 checksum in `pins.toml`, and unpacks them into `.runtime/`. It writes the
  interpreter's configuration and pulls the default model. Most of the time goes to the 13 GB
  model download. Running `setup` again is safe: finished steps are skipped.

`start`
: Starts the Ollama model server in the background on `127.0.0.1:11434`. It keeps running until
  you run `stop` (or restart the computer). Nothing ever starts it automatically.

Now [generate code](generate.md).

## Defaults

| Setting | Default | How to change it |
| --- | --- | --- |
| Model | `gpt-oss:20b` | `-m MODEL` per session, or `[model].default` in `pins.toml` ([Choose a model](models.md)) |
| Server address | `127.0.0.1:11434`, local only | `[ollama].port` in `pins.toml` |
| Context window | 32,768 tokens | `[model].context_length` in `pins.toml` |
| Reasoning effort (`gpt-oss:20b`) | medium | `default_effort` in `config/models.toml` |
| Where everything is stored | `.runtime/` inside the project folder | not configurable |
| Time limit for `check` and `bench` | 1 hour per run | `--timeout SECONDS` |

## Check that it works

```bash
python3.14 satyrn.py status    # server, installed and loaded models
python3.14 satyrn.py check     # the model writes sqrt.py; the script then runs it
```

`check` asks the model to write a square-root program, then runs that program with 16, 2 and
0.25 and compares the output. It prints `SUCCESS` after about two minutes with the default
model on a laptop CPU.

## Stop and remove

```bash
python3.14 satyrn.py stop      # stop the model server
```

To remove everything, stop the server and delete the `satyrn-getting-started` folder. Nothing
was installed anywhere else: the model, the tools, their settings and their keys all live in
its `.runtime/` subfolder.

## Troubleshooting

`another server already listens on port 11434`
: Another Ollama is running, for example one you installed earlier. Stop it, or set a different
  `[ollama].port` in `pins.toml`.

`Ollama is not running; start it first`
: Run `python3.14 satyrn.py start`. The server does not survive a restart of the computer.

`satyrn.py needs Python 3.14 or newer`
: See [Python 3.14](#python-314).

The model is very slow or the computer swaps
: The model needs more memory than is free. Close other programs, or use the default
  `gpt-oss:20b`, the smallest of the [benchmarked models](models.md).

`... resolved to ..., but pins.toml pins ...`
: The model tag was changed upstream since this project pinned it. This stops the setup on
  purpose, so you never get a different model without noticing. Update the digest in
  `pins.toml` if you want the new version.

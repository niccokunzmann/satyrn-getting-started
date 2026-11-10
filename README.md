# satyrn-getting-started

Generate code with a model that runs on your own computer: describe a program, and the model
writes it, runs it and checks it. [Open Interpreter](https://github.com/openinterpreter/openinterpreter)
is the coding agent, [Ollama](https://ollama.com) serves the model, and one Python script,
`satyrn.py`, sets both up. Nothing is installed outside this folder, and every download is
pinned and checksum-verified.

**Documentation: <https://niccokunzmann.github.io/satyrn-getting-started/>**

## Quick start

You need 16 GB of RAM, 20 GB of free disk space, `git` and Python 3.14 (or
[uv](https://docs.astral.sh/uv/): write `uv run --no-project --python 3.14 satyrn.py` instead
of `python3.14 satyrn.py`). Every setting has a default.

```bash
git clone https://github.com/niccokunzmann/satyrn-getting-started.git
cd satyrn-getting-started
python3.14 satyrn.py setup     # downloads Ollama, Open Interpreter and the model (~17 GB)
python3.14 satyrn.py start     # starts the model server in the background
mkdir -p ~/ai-code             # a folder for the code the model writes
python3.14 satyrn.py interpreter --oss -C ~/ai-code
```

Then type what you want, for example *Create a Python program sqrt.py that prints the square
root of its first argument, and run it with 2.* Stop the server with
`python3.14 satyrn.py stop`. On Windows, use `py -3.14` instead of `python3.14`.

The default model, `gpt-oss:20b`, writes and checks a program like that in about two minutes
on a laptop CPU without a GPU.

## Documentation

- [Set up](https://niccokunzmann.github.io/satyrn-getting-started/setup.html): requirements,
  defaults, troubleshooting
- [Generate code](https://niccokunzmann.github.io/satyrn-getting-started/generate.html):
  conversations, single requests, good requests
- [Choose a model](https://niccokunzmann.github.io/satyrn-getting-started/models.html):
  benchmark of four models, adding your own
- [How it works](https://niccokunzmann.github.io/satyrn-getting-started/how-it-works.html):
  what the models are told and why, time limits, where files live
- [Reproducibility](https://niccokunzmann.github.io/satyrn-getting-started/reproducibility.html),
  [Satyrn's own engine](https://niccokunzmann.github.io/satyrn-getting-started/satyrn-engine.html)
  (Apple Silicon), [Reference](https://niccokunzmann.github.io/satyrn-getting-started/reference.html)

The pages are built from [`docs/`](docs/) with Sphinx (`make docs`).

## The Satyrn projects

| Repository | What it is |
| --- | --- |
| [satyrn-agent](https://github.com/satyrn-ai/satyrn-agent) | `satyrn_agent` Python package and ds4 patch series (dense Qwen on Metal, DFlash speculative decoding). The engine behind `satyrn-codegen` in this repository. |
| ds4-py (external, pinned) | Python bindings for the ds4 C engine: sessions, chat templates, tool-call parsing. |
| [satyrn-models](https://github.com/satyrn-ai/satyrn-models) | Fine-tuning pipeline (datasets, Unsloth trainer); exports 4-bit GGUF models that Ollama can serve. |
| [satyrn-evals-collector](https://github.com/satyrn-ai/satyrn-evals-collector) | Community reports on coding agents with local models. |
| [satyrn-website](https://github.com/satyrn-ai/satyrn-website), [satyrn-zen](https://github.com/satyrn-ai/satyrn-zen), [team-compass](https://github.com/satyrn-ai/team-compass) | Documentation sites. |

## Development

```bash
make test        # no model needed; nothing is mocked
make test-live   # the square-root task through the real model (run `start` first)
make lint        # ruff
make docs        # the documentation site, into build/docs
```

See [Contributing](https://niccokunzmann.github.io/satyrn-getting-started/contributing.html).
`plan.md` holds the goals, `todo.md` every request and its state.

## License

[MIT](LICENSE)

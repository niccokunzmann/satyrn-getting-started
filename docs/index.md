# Generate code with a local model

Describe a program in plain language, and a model on your own computer writes it, runs it and
checks it. There is no cloud service and no API key.
A coding agent, [pi](https://pi.dev) or
[Open Interpreter](https://github.com/openinterpreter/openinterpreter), talks to a model that
[Ollama](https://ollama.com) serves on your machine. The `satyrn` command downloads them in
pinned, checksum-verified versions into a single folder, helps you choose a model that fits
your computer, and starts and stops the model server for you.

## Quick start

You need `git` and Python 3.14 (or [uv](setup.md#python-314), which fetches Python for you).
Clone the project and install the `satyrn` command:

::::{tab-set}

:::{tab-item} Linux and macOS
:sync: posix

```bash
git clone https://github.com/niccokunzmann/satyrn-getting-started.git
cd satyrn-getting-started
python3.14 satyrn.py install   # the `satyrn` command and its shell completion
satyrn                         # shows what is missing and guides you through it
```

:::

:::{tab-item} Windows (PowerShell)
:sync: windows

```powershell
git clone https://github.com/niccokunzmann/satyrn-getting-started.git
cd satyrn-getting-started
py -3.14 satyrn.py install     # the `satyrn` command and its shell completion
satyrn                         # shows what is missing and guides you through it
```

:::

:::{tab-item} `uv`
:sync: uv

```bash
git clone https://github.com/niccokunzmann/satyrn-getting-started.git
cd satyrn-getting-started
uv run --no-project --python 3.14 satyrn.py install   # uv fetches Python 3.14 for you
satyrn                         # shows what is missing and guides you through it
```

:::

::::

`satyrn` checks this computer, lists the models that fit it, and offers each missing step with a
default answer: download the tools, download a model, start the model server. Press
{kbd}`Enter` to accept the defaults. Then start working in a folder of your choice:

```bash
satyrn code ~/ai-code
```

Type what you want, for example:

> Create hello.py that prints Hello, World! Then run it.

![The important moments of a real session: satyrn code ~/ai-code, the folder trust question, the request, the model writing hello.py with a shell command and running it, its answer, and python3 ai-code/hello.py printing Hello, World! in the shell.](example/hello-world.gif)

The model writes the file into `~/ai-code`, runs it and tells you what it did. The animation
shows the important moments of a real session with Open Interpreter; see
[the whole session as text](generate.md#example-hello-world). When you are
done, leave with {kbd}`Ctrl+C` and stop the server with `satyrn stop`. Nothing starts by
itself, and everything the tools download stays in the `satyrn-getting-started` folder.

```{admonition} How fast is it?
:class: tip

On a laptop CPU without a GPU (Intel i7-13700H), the default model `gpt-oss:20b` writes and
checks a small program like the one above in about two minutes. A GPU is used automatically
if Ollama finds one. [Choose a model](models.md) compares four models.
```

```{toctree}
:maxdepth: 2
:caption: Use it

setup
generate
models
```

```{toctree}
:maxdepth: 2
:caption: Background

how-it-works
reproducibility
satyrn-engine
projects
reference
contributing
```

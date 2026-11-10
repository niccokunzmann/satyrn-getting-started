# Generate code with a local model

Describe a program in plain language, and a model on your own computer writes it, runs it and
checks it. There is no cloud service and no API key.
[Open Interpreter](https://github.com/openinterpreter/openinterpreter) is the coding agent; it
talks to a model that [Ollama](https://ollama.com) serves on your machine. One Python script,
`satyrn.py`, downloads both in pinned, checksum-verified versions into a single folder and
starts and stops the model server for you.

## Quick start

You need 16 GB of RAM, 20 GB of free disk space, `git`, and Python 3.14
(or [uv](setup.md#python-314), which fetches Python for you). Every setting has a default, so
these commands are all it takes:

::::{tab-set}

:::{tab-item} Linux and macOS
:sync: posix

```bash
git clone https://github.com/niccokunzmann/satyrn-getting-started.git
cd satyrn-getting-started
python3.14 satyrn.py setup     # downloads Ollama, Open Interpreter and the model (~17 GB)
python3.14 satyrn.py start     # starts the model server in the background
mkdir -p ~/ai-code             # a folder for the code the model writes
python3.14 satyrn.py interpreter --oss -C ~/ai-code
```

:::

:::{tab-item} Windows (PowerShell)
:sync: windows

```powershell
git clone https://github.com/niccokunzmann/satyrn-getting-started.git
cd satyrn-getting-started
py -3.14 satyrn.py setup       # downloads Ollama, Open Interpreter and the model (~17 GB)
py -3.14 satyrn.py start       # starts the model server in the background
mkdir $HOME\ai-code            # a folder for the code the model writes
py -3.14 satyrn.py interpreter --oss -C $HOME\ai-code
```

:::

::::

Then type what you want, for example:

> Create a Python program sqrt.py that prints the square root of the number given as its
> first argument, and run it with 2.

The model writes the file into `~/ai-code`, runs it and tells you what it did. When you are
done, leave the interpreter with {kbd}`Ctrl+C` and stop the server with
`python3.14 satyrn.py stop`. Nothing starts by itself, and nothing is installed outside the
`satyrn-getting-started` folder.

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

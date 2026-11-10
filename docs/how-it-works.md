# How it works

## The pieces

```text
 you ──► Open Interpreter ──HTTP──► Ollama ──► model (e.g. gpt-oss:20b)
            │  runs the commands the model asks for
            ▼
         your folder (-C)

 satyrn:    downloads and verifies both tools, rates and downloads models,
            writes their settings, starts and stops Ollama, runs checks and benchmarks
```

Open Interpreter
: The coding agent and its terminal interface. It sends your request to the model together
  with a list of tools, runs the tool calls the model makes (shell commands) and sends the
  results back, until the model gives a final answer.

Ollama
: Runs the model on your CPU or GPU and offers it on `127.0.0.1:11434` through an
  OpenAI-compatible API. `--oss` tells Open Interpreter to use it.

`satyrn`
: Pure Python with no dependencies outside the standard library, so it works the same on Linux,
  macOS and Windows. `satyrn.py install` links the `satyrn` command to the cloned folder;
  everything it downloads or creates goes into that folder's `.runtime/`.

## Two coding agents

[pi](https://pi.dev) and [Open Interpreter](https://github.com/openinterpreter/openinterpreter) do
the same job: they send your request and their tools to the model, run the tool calls it makes
and send back the results until the model answers. satyrn installs both and gives each the
same model, its own context and its own settings folder; `satyrn code` starts the one you chose.

Each agent gets a context file written for its tools:

`config/context/pi.md`
: For pi: its tools `read`, `write`, `edit` and `bash`. satyrn installs it as pi's system prompt
  (`SYSTEM.md` in `.runtime/pi-home`).

`config/context/open-interpreter.md`
: For Open Interpreter: its tools `exec_command` and `write_stdin`, and writing files with the
  shell (see below).

Both tell the model that it is Satyrn, a coding agent on the user's computer, and to put each
sentence of its answers on its own line, which keeps answers readable in a terminal. pi gets its
model list from `config/models.toml` as well (context window and reasoning settings), and its
telemetry, update checks and session sharing are switched off.

## What the model is told

Open Interpreter 0.0.60 only has settings for OpenAI's hosted models. A local model would get a
fallback (`warning: Model metadata for gpt-oss:20b not found`): a 17 KB generic system prompt
that tells it to edit files with an `apply_patch` tool that is never registered, plus 18 KB of
tools it cannot use (sub-agents, goals, web search) and a list of skills that need OpenAI's
services. That is about 6,700 prompt tokens, about five minutes of reading on a laptop CPU
before the model even starts. The model then spends many turns on the missing tool. A logging
proxy between the interpreter and Ollama showed all of this.

This project gives every model context written for it:

`config/context/open-interpreter.md`
: The system prompt. It names the two tools that exist (`exec_command` to run a shell command,
  `write_stdin` to answer a running command), shows how to create and change files with them
  (a heredoc, a short Python replacement, PowerShell), and says how to work: look first, make
  the change, run it to check, then finish with a short summary. It also covers runs nobody
  watches: no questions, no repeated failing calls.

`config/models.toml`
: One entry per model: reasoning efforts and how much command output to keep. `satyrn.py` turns
  it into the interpreter's model catalog (`.runtime/interpreter-home/models.json`), together
  with the system prompt and the context window of the server.

`config/interpreter.toml`
: Points the interpreter at that catalog and switches off what a local model cannot use: web
  search, sub-agents, goals, image viewing, questions to the user and the skills list.

With this, the tools sent with every request shrink from 18 KB to 3 KB and the extra
instructions from 3.5–7 KB to a 0.6 KB note about the sandbox. `gpt-oss:20b` went from about
33 minutes to about 2 minutes for the square-root task.

`apply_patch` stays switched off. The interpreter offers it only as a "freeform" tool, and
Ollama returns calls to such tools as ordinary JSON function calls, which the interpreter
rejects (`tool apply_patch invoked with incompatible payload`). The models write files with the
shell instead.

Changes to `config/models.toml` and the files in `config/context/` apply the next time you start
a coding agent. Changes to `config/interpreter.toml` need `satyrn setup` again.

## Runs that cannot finish

A model that cannot solve a task might keep trying forever. `check` and `bench` therefore stop
a run after one hour (`--timeout`) and count it as failed. They stop everything the run started,
including programs the model launched in their own terminal sessions: first politely, then by
force after ten seconds. They then unload the model, because Ollama would otherwise finish the
batch of prompt tokens it is working on, which takes minutes for a slow model.

When you talk to the interpreter yourself, you are the time limit: {kbd}`Ctrl+C` stops it.

## Where everything lives

```text
satyrn-getting-started/
  satyrn.py                   entry point; `satyrn.py install` adds the `satyrn` command
  pins.toml                   versions, download checksums, model digests, port, context window
  config/                     instructions and settings for the interpreter
  src/satyrn_local/           the Python code behind satyrn.py
  .runtime/                   everything downloaded or generated (delete it to start over)
    downloads/                verified archives
    ollama/  interpreter/     the unpacked tools
    models/                   model files
    home/                     Ollama's home folder (its key pair), instead of ~/.ollama
    interpreter-home/         interpreter settings, model catalog, conversations, logs
    settings.toml             your choices, for example the model from `satyrn use`
    bin/  activate*           launchers for `interpreter` and `ollama`
    ollama.pid  ollama.log    the server started with `start`
    checks/  bench/           files and results of `check` and `bench`
```

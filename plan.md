# Plan: goals of satyrn-getting-started

## Purpose

A getting-started kit in which a developer describes code in natural language and a
**local** model writes it. The model reads the project, creates or edits files and runs
them. Everything needed for that lives in this one directory.

## Goals

1. **Natural-language code generation with a local model.** The model must act as an
   agent: plan, write files, run them, iterate. Chat alone is not enough.
2. **Open Interpreter is the front end.** Users work through `interpreter --oss`, not
   a self-developed shell. The `--oss` mode must work out of the box with the local model.
3. **Ollama serves the models.** One model works end to end first (`gpt-oss:20b`, the
   `--oss` default). The model is configurable: a default in `pins.toml`, plus switching
   per session or per run. The Satyrn-relevant models should be runnable on the
   development machine.
4. **Verified by the real model, never mocked.** The acceptance test is the
   square-root program: the model, through `interpreter exec --oss`, must create `sqrt.py`
   that takes a number and prints its square root. The test runs the generated program.
   No fake models, scripted replies or mocked outputs.
5. **Self-contained.** Everything lives in this directory (`.runtime/`). The system is
   not modified: no system packages, no services, nothing in `/etc` or `/usr`. The home
   directory is used only if it is part of a reproducible install procedure.
6. **Reproducible build.** Every external input is pinned: tool versions, download
   URLs, sha256 per platform, and the model manifest digest. A changed upstream input
   fails loudly instead of being used silently. `verify` re-checks everything.
7. **Manual control.** Nothing starts automatically. The user starts and stops the
   model server (`start`/`stop`/`serve`).
8. **Mostly Python, cross-platform.** The logic is Python (standard library) with as
   little shell as possible, so the same steps work on Windows (and macOS). The Makefile
   is only a convenience wrapper.
9. **Understand the satyrn codebase.** Explain how the satyrn repositories fit together
   and how to use them. Keep the Satyrn-engine path (`satyrn-codegen` on satyrn-agent/ds4
   with DFlash) for Apple Silicon, with the same square-root acceptance test.
10. **Easy install of the CLI.** `make install` installs `satyrn-codegen` globally with
    pipx.
11. **The models know how to use Open Interpreter.** Every local model gets context written
    for it: which tools exist and how to call them, how to work and when to finish, and a
    context window that matches the server. No tool is named that the interpreter does not
    register, and nothing a local model cannot use is sent with each request.
12. **Comparable models.** `bench` measures the models on the same square-root task, through
    the real interpreter, so the choice of default model rests on numbers from this machine.
13. **No endless runs.** A model that cannot finish must not run forever: `check` and `bench`
    stop a run after one hour, together with everything it started, and count it as failed.

## Non-goals

- Mocked or scripted model output, in tests or demos.
- Autostart, system services, or changes outside this directory (except reproducible
  install steps the user runs).
- A custom chat shell as the primary interface. Open Interpreter fills that role.

## Development machine

Debian 13 (Trixie), x86_64 Intel i7-13700H (AVX2, AVX-VNNI), no GPU, about 40 GB RAM,
100 GB private storage. Satyrn's own engine (dense qwen35 on Metal) cannot run here, so
this machine uses the Ollama + Open Interpreter path.

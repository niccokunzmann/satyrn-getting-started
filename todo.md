# TODO

Every request is recorded here as a todo, in the order it was given. The goals behind these are in [plan.md](plan.md).

## From the requests

- [x] Create a new directory with all the code needed for a natural-language CLI that
      generates code. → `satyrn-getting-started/`
- [x] Analyse the satyrn codebase and explain how to use it. → README "The satyrn folder at a glance"
- [x] Name the directory `satyrn-getting-started`.
- [x] Add a `make install` step that installs the CLI globally with pipx.
      → `make install` (tested into an isolated pipx home)
- [x] Ask the model to create a program that takes a number and prints its square root;
      report success, or say if it is out of scope.
  - [x] Satyrn engine (ds4/Metal) on this machine: out of scope (Metal only); test kept
        for Apple Silicon (`tests/test_live_sqrt.py`).
  - [x] Ollama + Open Interpreter on this machine: `python3.14 satyrn.py check` → SUCCESS
        (gpt-oss:20b on CPU, 33 min; sqrt.py prints 4.0 / 1.4142135623730951 / 0.5)
  - [x] Reproduced through the pytest live test (`make test-live`): 1 passed in 33:33.
- [x] Explain which machine is required to run a local model (and the minimal specs for
      the Satyrn models). → README Path A requirements / Path B hardware note
- [x] No mocking: remove the fake model and scripted tests.
- [x] Make the model configurable (which model to talk to). → `pins.toml` default,
      `pull MODEL`, `interpreter --oss -m MODEL`, `check --model MODEL`
- [x] Use Ollama and make one model work agentically. → `gpt-oss:20b` wrote the file via the shell tool,
      then checked it with `ls`/`sed` on its own
- [ ] `interpreter --oss` must work with that Ollama model.
  - [x] `interpreter exec --oss` (non-interactive) works end to end.
  - [ ] Try the interactive TUI: `source .runtime/activate && interpreter --oss` (needs a terminal).
- [x] Prefer Open Interpreter over a self-developed shell. → Path A is primary
- [x] Play a sound when all work is done, in every session. → existing user-level `Stop`
      hook verified (`paplay complete.oga`)
- [x] No autostart; everything is started manually. → `start`/`stop`/`serve`, no services
- [x] Do not modify the system. → moved Ollama/model/keys from `~/.local` and `~/.ollama`
      into `.runtime/`; nothing outside the directory
- [x] Everything in this directory; home only if part of a reproducible install.
- [x] Reproducible build. → versions + sha256 pinned per platform in `pins.toml`
  - [x] Pin the `gpt-oss:20b` manifest digest in `pins.toml`. → `f38aa0c5…`
  - [x] Run a clean `setup` from the cached archives (re-extract) and `verify` to prove it.
        → setup in 11 s from cache; `verify`: all pinned inputs verified
- [x] Describe the machine as Debian 13 (Trixie); do not mention the virtualization host.
- [x] Check whether the 100 GB private storage needs expanding. → no: about 70 GB stays
      free with `gpt-oss:20b`
- [x] Mostly Python, little shell, so it can work on Windows. → `satyrn.py` + `src/satyrn_local`
      (stdlib only); Makefile is a thin wrapper
  - [ ] Run `setup`/`start`/`check` on a real Windows machine (not available here).
- [x] Use the square-root file as the test, through the model, with no mocked output.
      → `satyrn.py check` and `tests/test_local_model.py::test_model_writes_working_sqrt_program`
- [x] Write the goals into `plan.md` and every request as a todo into `todo.md`.
  - [x] `plan.md` is the goals (the intention, formulated as well as possible).
  - [x] Todos use `- [ ]` checkboxes.
- [x] Continue until one model shows that it can solve the task (sqrt.py through the model). → done, see above
- [x] Use lint and ruff. → `[tool.ruff]` in pyproject.toml, `make lint` / `make format`; whole project passes
- [x] Use uv when a newer Python is required. → `uv run --no-project --python 3.14 satyrn.py …`
      (3.14 is enough; 3.15 is not needed)
- [x] Try a non-interactive session with `interpreter` (as a user would: `source .runtime/activate`,
      then `interpreter exec --oss …`), with a task that writes and runs code.
      → FizzBuzz: wrote fizzbuzz.py, ran it, reported correct output; 8 min 21 s, 7,952 tokens,
        0 `apply_patch` retries (prompt said "create files with shell commands")
- [x] Report how long the models take for the sqrt.py task. → only `gpt-oss:20b` measured:
      32 min 43 s and 33 min 33 s; sqrt.py appeared after ~31–33 min, the rest took under 1.5 min.
      Other models and Path B not measured.
- [x] Benchmark the models on the sqrt.py task, and give them enough context that they know how
      to use Open Interpreter. → README "Benchmark"; default stays gpt-oss:20b (fastest, 6/6)
  - [x] Find out what the model is told. → a logging proxy showed the interpreter has no metadata
        for Ollama models: it sends a 17 KB generic prompt that says "use `apply_patch`" (never
        registered) and 18 KB of tools a local model cannot use (sub-agents, goals, web search):
        ~6.7k tokens, about 5 min of CPU prompt processing before the first answer.
  - [x] Give every model a catalog entry (`model_catalog_json`, generated from `config/models.toml`)
        with our system prompt `config/instructions.md` (tools, workflow, how to finish) and the
        server's context window; switch off unused tools and the bundled skills in
        `config/interpreter.toml`. Tests check it with the real interpreter.
  - [x] Confirm with a real run that the interpreter executes Ollama's `apply_patch` calls.
        → it does not: Ollama returns the freeform call as a JSON function call and the interpreter
        rejects it ("incompatible payload", 13× in 18 min). `apply_patch` is now off and the
        instructions teach file writing through `exec_command` (heredoc / Python replace / PowerShell).
  - [x] Smoke test `bench gpt-oss:20b` with the new context → pass in 1:56 (was ~33 min),
        1 command, 0 failed calls, 3.2k prompt tokens (was 76k).
  - [x] Pull `qwen3-coder:30b`, `qwen3.6:35b-a3b` and `qwen3.8:27b` (Satyrn's base model) and pin their digests.
        → `[model.digests]` in pins.toml; `verify` checks all four (17 GB of disk left)
  - [x] Round 1 (`bench`, 3 runs each): 11/12 passed. gpt-oss:20b 2:11–4:51, qwen3-coder:30b
        5:09/5:51 + 1 fail, qwen3.6:35b-a3b 3:01–4:02, qwen3.8:27b 10:12–12:05.
        qwen3-coder's fail: it typed its tool-call markup as reply text (and chose `write_stdin`);
        gpt-oss once sent `justification` without `sandbox_permissions` (refused, then fixed).
        → instructions now say tool-call markup in text does nothing, `write_stdin` does not write
        files, and when `justification` is refused.
  - [x] Round 2 with the updated instructions: 11/12 again. gpt-oss:20b 1:33–2:25,
        qwen3-coder:30b 3:59/4:09 + the same fail (tool call typed as text, not fixable by
        instructions), qwen3.6:35b-a3b 3:12–3:49, qwen3.8:27b 11:45–19:32.
  - [x] gpt-oss:20b at `--effort low` (3 runs): 3/3, median 2:45 (1:54–3:56), not faster than
        the default medium (2:08); results and measured read/write speeds are in the README.
- [x] Make sure a model cannot loop forever when it cannot finish the task; 1 h is the cut-off
      (the slowest model needs ~20 min). → `procs.run_limited`: `check`/`bench` stop a run at
      `--timeout` (default 3600 s) together with every program it started (also those in their
      own sessions), SIGTERM then SIGKILL; output goes to files so a stray process cannot block
      the reader; leftovers of finished runs are stopped too; a stopped run counts as failed;
      the model is unloaded so Ollama stops at once (it otherwise finishes its current
      1,024-token batch: ~2 min for the dense model). Generated programs get no stdin and 30 s.
      Tests with real stuck processes; real check with `--timeout 90`: stopped after 90 s,
      nothing left running.
  - [x] Fix found on the way: unloading a 17 GB model made Ollama answer `/api/ps` after 6 s,
        past the 5 s client timeout, which crashed the next `bench`. `unload` now waits until
        the model is gone, with longer timeouts.

- [x] Publish the project as a Sphinx site on GitHub Pages under `github.com/niccokunzmann/`:
      people follow a few setup steps that have defaults, then generate code with local models.
  - [x] Sphinx project in `docs/` (pinned, hash-checked build requirements; warnings are errors).
        → Furo + MyST; quick start with defaults on the front page; `make docs`; linkcheck clean;
        README shortened to a quick start that links to the site
  - [x] GitHub Actions workflow that builds the site and deploys it to Pages (actions pinned by SHA).
  - [x] Create the GitHub repository and push (needs the user's GitHub login).
        → https://github.com/niccokunzmann/satyrn-getting-started (public), Pages from Actions:
        https://niccokunzmann.github.io/satyrn-getting-started/ (all pages 200; a fresh clone works on its own)
  - [ ] Choose a license (none yet, so others may not reuse the code; the satyrn-ai repos use MIT).

## Follow-ups found along the way

- [x] Make it faster (→ ~2 min for gpt-oss:20b with the model catalog, see the benchmark todo). Both runs took ~33 min; most of it is gpt-oss:20b retrying `apply_patch`
      (`unsupported call`: the interpreter has no metadata for this model, so it prompts for
      apply_patch without registering the tool) before falling back to the shell.
      `include_apply_patch_tool = true` is accepted but ignored by 0.0.60. CPU prompt eval ~20 tokens/s.
  - [x] Find a supported way to register apply_patch (or drop it from the prompt) for Ollama models.
        → `model_catalog_json` entry with `apply_patch_tool_type = "freeform"` (see the benchmark todo)
  - [x] Put the hint into the config instead of every prompt. → the catalog's system prompt
        (`config/instructions.md`) replaces it. Note: `--strict-config --version` validates nothing;
        only a real `exec --strict-config` rejects unknown keys (now covered by tests).
  - [x] Try a lower reasoning effort and compare `check` times (`bench --effort low`). → not faster

- [ ] Run `satyrn-codegen` (Path B) and its live test on an Apple Silicon Mac.
- [ ] Decide whether `satyrn-agent/.venv` (created while analysing; git-ignored) should be deleted.

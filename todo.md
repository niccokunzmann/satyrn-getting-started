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
- [x] `interpreter --oss` must work with that Ollama model.
  - [x] `interpreter exec --oss` (non-interactive) works end to end.
  - [x] Try the interactive TUI: `source .runtime/activate && interpreter --oss` (needs a terminal).
        → tested in a pseudo-terminal via `satyrn code`: header shows `model: ollama gpt-oss:20b`
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
- [x] "Are you done?" → not yet at that point: the last benchmark (gpt-oss low effort) and the README
      results were still open; finished right after.

- [x] Publish the project as a Sphinx site on GitHub Pages under `github.com/niccokunzmann/`:
      people follow a few setup steps that have defaults, then generate code with local models.
  - [x] Sphinx project in `docs/` (pinned, hash-checked build requirements; warnings are errors).
        → Furo + MyST; quick start with defaults on the front page; `make docs`; linkcheck clean;
        README shortened to a quick start that links to the site
  - [x] GitHub Actions workflow that builds the site and deploys it to Pages (actions pinned by SHA).
  - [x] Create the GitHub repository and push (needs the user's GitHub login).
        → https://github.com/niccokunzmann/satyrn-getting-started (public), Pages from Actions:
        https://niccokunzmann.github.io/satyrn-getting-started/ (all pages 200; a fresh clone works on its own)
  - [x] Choose a license. → MIT (`LICENSE`, like the satyrn-ai repos), declared in pyproject.toml
  - [x] Location: `github.com/niccokunzmann/` → `niccokunzmann/satyrn-getting-started`
  - [x] "gh command is authenticated" → repository created (public), Pages set to GitHub Actions, pushed

- [x] License: MIT. → `LICENSE`, pyproject.toml, README, docs footer
- [x] Use the REUSE project (reuse.software): every file has its license and copyright; `reuse lint` passes.
      → `REUSE.toml` (MIT for the project; GPL-3.0-only for the files ai-prompt-auto-commit installs,
      as its LICENSE has no "or later" statement), `LICENSES/`; `reuse` pre-commit hook
- [x] Add a pre-commit hook for formatting, like in icalendar. → `.pre-commit-config.yaml`: ruff check
      + format (v0.17.4, same as pyproject), debug-statements, REUSE; `make hooks`
- [x] Install the latest ai-prompt-auto-commit. → v0.1.0 (icalendar is on v0.0.10); git hooks
      installed, `prepare-ai-repository` ran (.claude/, .codex/, AGENTS.md, assistant guidelines)
- [x] Make the README mostly empty and point to the docs. → the Satyrn projects table moved to docs/projects.md
- [x] Create a commit and publish the project so I can view it. → pushed; Pages deploy checked live

- [x] Find instructions that make the models solve tasks faster; check with the fastest model
      (gpt-oss:20b) whether code execution gets faster. → results below; the default is a decision for the user
  - [x] Measured (gpt-oss:20b, 3 runs each): current context 2:33 cold / 1:00 warm; lean context
        (0.8 KB prompt, no environment block, no sandbox note) 1:48 cold / 1:07 warm. Context read:
        1,675 tokens in 88 s vs 870 in 39 s; warm 21 s vs 6 s. Writing dominates warm runs (~45 s).
        Tools (2.5 KB) cannot be changed; `shell_type`/`unified_exec` switches do not change them.
        → docs/models.md "What makes it faster"; `bench --instructions/--set/--warm`
  - [ ] Make a compact context the default (keep the sandbox note for interactive approvals,
        name the shell via @SHELL@, drop the environment block) and validate it with `bench`.
- [x] Measure how long the models take to read the context before the instruction.
      → gpt-oss:20b 73 s (1,559 tokens), qwen3.6:35b-a3b 85 s (2,760), qwen3-coder:30b 132 s
      (3,012), qwen3.8:27b 464 s (2,886); about 40-65 % of a run; docs/models.md
- [x] Install a `satyrn` command so the docs do not need `python3.14 satyrn.py`. Name: `satyrn-agent`
      or `satyrn-cli`? → `satyrn-agent` is the engine package of the satyrn-ai org; `satyrn-cli` is
      free on PyPI (`satyrn` there is an unrelated SAT solver): package `satyrn-cli`, command `satyrn`.
- [x] Clone, install, then just run `satyrn`: it guides you through the steps that still need doing.
      → `python3.14 satyrn.py install` (uv tool / pipx, editable: keeps using the clone's .runtime/),
      `satyrn` = guide (asks only in a terminal; tested in a pseudo-terminal), `satyrn code DIR [-p]`
- [x] `satyrn` evaluates which models can run on this computer and lists all models so people can
      make a good choice. → `satyrn models`: memory/disk/GPU rating, benchmark results, ranking,
      recommendation; `satyrn use MODEL`; memory measured with /api/ps at 32k context
- [x] The installation also installs auto-completion for the shell. → bash (tested in real bash with
      bash-completion), zsh, fish, PowerShell (not tested: shells not available here); `uninstall`
      removes everything it added
  - [ ] Test the zsh, fish and PowerShell completion on machines that have those shells.
  - [x] Docs first: quick start, Set up (install, guide, steps by hand, completion, uninstall),
        Generate code (`satyrn code`), Choose a model (`satyrn models`, `use`, context reading times), Reference.
- [x] For now, always commit and push when done; the user reviews the docs. Docs-first project from now on.
      → docs are written and pushed before the code; saved as a project memory

- [x] `satyrn-codegen --help` failed with `No module named 'ds4py'`: what is this? → `satyrn install`
      also installs the package's second command, `satyrn-codegen` (Apple Silicon engine), whose
      dependencies are the optional `engine` extra. It now explains what it needs instead of crashing
      (lazy imports, `satyrn_codegen.entry`); the install test checks it.
- [x] Remember: in this project, done is when the changes are live (pushed, deployed, visible).

- [x] `satyrn models` should say how to select a model. → "How to select a model" with the
      recommended model as the example (pull, use, `code -m`); `satyrn use NUMBER` selects by row

- [x] "`satyrn code` executes codex; the arguments do not seem to be passed." → it runs the pinned
      Open Interpreter (`ps` shows `.runtime/interpreter/bin/interpreter --oss -m gpt-oss:20b -C DIR`);
      its header shows `model: ollama gpt-oss:20b` and the folder. The trust question and the hint
      "Ask Codex to do anything" are Codex wording compiled into Open Interpreter (a Codex fork).
      → explained in docs/generate.md; its "1 warning" (an unfinished feature it enables itself) is
      silenced with `suppress_unstable_features_warning`.
- [x] `satyrn code` can only use a model that is listed. → `code -m` and `use` accept only listed
      models, by name or number; anything else gets the list and the docs link, nothing is changed

- [x] Clone Open Interpreter and draft a PR that removes the Codex wording and lets the shown name be
      configured (so it can say Satyrn). → patch on the local branch `product-name-override` in
      `../openinterpreter` (product-info: `OPEN_INTERPRETER_PRODUCT_NAME` at runtime; trust prompt and
      placeholder use the product name; FORK_BRANDING.md). Upstream asks for an issue first; per the
      user, nothing was published (the fork `niccokunzmann/openinterpreter` exists, unchanged).
  - [x] "It also says 'Ask codex to do anything' in the prompt" → replaced in the same patch.
  - [x] Do not publish anything to them; give the issue text and the link. → handed over in the chat.
- [x] Never publish an issue, PR or anything without the user's consent. → saved as a memory for all sessions
- [x] Push the Open Interpreter patch to a branch in the user's fork (consented). → `niccokunzmann/openinterpreter`
      branch `product-name-override`; no PR, no issue
  - [x] Verified: `cargo test -p codex-product-info`, `cargo fmt --check`, `cargo check -p codex-tui --tests`
        (Rust 1.95.0 in `../openinterpreter/.toolchain`, OpenSSL headers unpacked there; no system change)
- [x] Are there example files and prompts to test the speed of the models? Something online for really
      simple benchmarks? → answered: LocalScore, llama-bench, Ollama `--verbose`, HumanEval/MBPP
      (benchllama), Aider Polyglot; `satyrn bench` for the agent task
- [x] What is the simplest and fastest benchmark the model could run, like hello world? → answered:
      hello.py (one tool call); its floor is the context reading, so barely faster than sqrt.py
  - [ ] Optional: add small tasks (hello, sqrt, fizzbuzz) to `satyrn bench` if the user wants them.
- [x] Still record all prompts as todos for this project and check them off. → this list, in order

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

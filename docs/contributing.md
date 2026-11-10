# Contributing

Development uses [uv](https://docs.astral.sh/uv/) and needs
[satyrn-agent](https://github.com/satyrn-ai/satyrn-agent) cloned next to this project, because
`satyrn-codegen` (the [Apple Silicon path](satyrn-engine.md)) depends on it.

```bash
make hooks       # once per clone: git hooks for formatting, licensing and AI prompts
make test        # tests that need no model; no mocks: real archives, real interpreter
make test-live   # the square-root test through the real model (start the server first)
make lint        # ruff check and ruff format --check
make format      # apply ruff's formatting and safe fixes
make html        # build this site into build/html (warnings are errors)
make livehtml    # serve it in your browser; rebuilt and reloaded on every change
```

The tests never mock the model. The live tests send their task through the real model and run
the program it wrote. `make test` checks the generated interpreter settings with the real
pinned interpreter, which rejects unknown keys, and tests the time limit with real stuck
processes.

## Git hooks

`make hooks` installs [pre-commit](https://pre-commit.com/) hooks, configured in
`.pre-commit-config.yaml` as in [icalendar](https://github.com/collective/icalendar):

- [ruff](https://docs.astral.sh/ruff/) checks and formats the Python code, and
  `debug-statements` stops forgotten breakpoints.
- [REUSE](https://reuse.software/) checks that every file states its copyright and license.
  `REUSE.toml` assigns them: MIT for this project, GPL-3.0 for the files that
  ai-prompt-auto-commit installs. The license texts are in `LICENSES/`.
- [ai-prompt-auto-commit](https://github.com/pycalendar/ai-prompt-auto-commit) records the
  prompts you give Claude Code or Codex in `.prompts/` and appends them to the next commit
  message, so the history shows which AI requests shaped the code. `make hooks` also runs its
  one-time repository setup (`.claude/`, `.codex/`, `AGENTS.md`).

## The documentation

The site is built with [Sphinx](https://www.sphinx-doc.org/), the
[Furo](https://pradyunsg.me/furo/) theme and [MyST](https://myst-parser.readthedocs.io/)
Markdown from the `docs/` folder. `make livehtml` is the way to write it: it serves the site
with [sphinx-autobuild](https://github.com/sphinx-doc/sphinx-autobuild) on a free port (so it
runs next to other documentation servers), opens it in your browser, rebuilds it when a file
changes and reloads the page; {kbd}`Ctrl+C` stops it. For a fixed address, use
`make livehtml LIVEHTML_ARGS="--port 8001"`. `make html` is the
strict build that CI runs. The build requirements are pinned with hashes in
`docs/requirements.txt`; to update them, edit `docs/requirements.in` and run:

```bash
uv pip compile docs/requirements.in --generate-hashes --python-version 3.14 -o docs/requirements.txt
```

A GitHub Actions workflow (`.github/workflows/docs.yml`) builds the site for every pull request
and publishes it to GitHub Pages for every push to `main`.

## Goals and open work

`plan.md` lists the goals of the project, and `todo.md` every request so far with its state.

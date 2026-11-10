# Contributing

Development uses [uv](https://docs.astral.sh/uv/) and needs
[satyrn-agent](https://github.com/satyrn-ai/satyrn-agent) cloned next to this project, because
`satyrn-codegen` (the [Apple Silicon path](satyrn-engine.md)) depends on it.

```bash
make test        # tests that need no model; no mocks: real archives, real interpreter
make test-live   # the square-root test through the real model (start the server first)
make lint        # ruff check and ruff format --check
make format      # apply ruff's formatting and safe fixes
make docs        # build this site into build/docs (warnings are errors)
```

The tests never mock the model. The live tests send their task through the real model and run
the program it wrote. `make test` checks the generated interpreter settings with the real
pinned interpreter, which rejects unknown keys, and tests the time limit with real stuck
processes.

## The documentation

The site is built with [Sphinx](https://www.sphinx-doc.org/), the
[Furo](https://pradyunsg.me/furo/) theme and [MyST](https://myst-parser.readthedocs.io/)
Markdown from the `docs/` folder. Its build requirements are pinned with hashes in
`docs/requirements.txt`; to update them, edit `docs/requirements.in` and run:

```bash
uv pip compile docs/requirements.in --generate-hashes --python-version 3.14 -o docs/requirements.txt
```

A GitHub Actions workflow (`.github/workflows/docs.yml`) builds the site for every pull request
and publishes it to GitHub Pages for every push to `main`.

## Goals and open work

`plan.md` lists the goals of the project, and `todo.md` every request so far with its state.

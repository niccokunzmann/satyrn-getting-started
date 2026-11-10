# Convenience targets. All logic lives in Python (satyrn.py / src/), so Windows users can run
# the same steps without make:  python satyrn.py <command>
#
#   make setup       download + verify pinned Ollama and Open Interpreter, pull the model
#   make start       start the local model server (background)   | make serve: foreground
#   make stop        stop it
#   make oss         open Open Interpreter on the local model (interpreter --oss)
#   make check       acceptance test: the model writes a working sqrt.py
#   make bench       time every model in config/models.toml on that test
#   make verify      re-check every pinned checksum and the model digest
#   make test        tests that need no model   | make test-live: through the real model
#   make lint        ruff check + format check  | make format: apply ruff format and safe fixes
#   make install     install the satyrn-codegen CLI globally with pipx
#   make docs        build the documentation site into build/docs
#   make hooks       install the git hooks (ruff, REUSE, AI prompts in commit messages)

PY    ?= $(shell command -v python3.14 2>/dev/null || echo "uv run --no-project --python 3.14")
SATYRN = $(PY) satyrn.py

.PHONY: help setup verify serve start stop status oss check bench test test-live lint format docs hooks dev wheels install reinstall uninstall clean

help:
	@sed -n 's/^#   //p' Makefile

setup:  ; $(SATYRN) setup
verify: ; $(SATYRN) verify
serve:  ; $(SATYRN) serve
start:  ; $(SATYRN) start
stop:   ; $(SATYRN) stop
status: ; $(SATYRN) status
oss:    ; $(SATYRN) interpreter --oss
check:  ; $(SATYRN) check
bench:  ; $(SATYRN) bench

dev:
	uv sync

# Once per clone. The second step sets up AI prompt recording (ai-prompt-auto-commit).
hooks: dev
	uv run pre-commit install
	uv run pre-commit run --hook-stage manual prepare-ai-repository || true

test: dev
	uv run pytest -q -m "not live"

test-live: dev
	uv run pytest -v -s -m live

lint: dev
	uv run ruff check .
	uv run ruff format --check .

format: dev
	uv run ruff check --fix .
	uv run ruff format .

# Separate environment with hash-pinned requirements: needs neither the project nor satyrn-agent.
DOCS_VENV := build/docs-venv

docs:
	uv venv -q --allow-existing --python 3.14 $(DOCS_VENV)
	uv pip install -q --python $(DOCS_VENV) --require-hashes -r docs/requirements.txt
	$(DOCS_VENV)/bin/sphinx-build -W --keep-going -q -b html docs build/docs

# --- satyrn-codegen (ds4/Metal CLI) packaged for pipx ------------------------------------
PIPX      ?= $(shell command -v pipx 2>/dev/null || echo "uvx pipx")
AGENT_DIR ?= ../satyrn-agent
WHEELS    := build/wheels

wheels:
	rm -rf $(WHEELS)
	uv build --wheel --out-dir $(WHEELS) $(AGENT_DIR)
	uv build --wheel --out-dir $(WHEELS) .

install: wheels
	$(PIPX) install --force --python python3.14 \
		--pip-args="--find-links=$(abspath $(WHEELS))" \
		$(firstword $(wildcard $(WHEELS)/satyrn_codegen-*.whl))

reinstall: uninstall install

uninstall:
	-$(PIPX) uninstall satyrn-codegen

clean:
	rm -rf build dist .pytest_cache

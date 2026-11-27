# Reproducibility

Every input is pinned in `pins.toml`, so two setups made months apart get the same tools and
the same models, or stop with an error.

| Input | Pinned by |
| --- | --- |
| Ollama 0.40.15 | download URL and SHA-256 per platform: Linux x86-64 and ARM64, Windows, macOS |
| Open Interpreter 0.0.60 | download URL and SHA-256 per platform, including Windows and macOS on ARM |
| Node.js 24.22.2 | download URL and SHA-256 per platform, from nodejs.org's checksum list |
| pi 1.5.2 | `config/pi/package-lock.json`: every npm package with its version and integrity hash, installed with `npm ci --ignore-scripts` |
| Models | manifest digest per model tag |
| Dataset sources | git commit of satyrn-models, CPython and python/peps ([Create a dataset](data.md#how-it-is-made)); of StructuredRegex, deep-regex and Lingua Franca for the regex tasks ([Regex tasks](data.md#how-the-regex-tasks-are-made)) |
| Datasets | SHA-256 of each dataset that `satyrn data` creates; a different result fails |
| Python packages for datasets and training | `config/data/requirements.txt`, `config/train/requirements.txt`: version and SHA-256 of every package |
| Training model | Hugging Face revision of Qwen2.5-0.5B-Instruct and the SHA-256 of each of its files |
| GGUF converter | git commit of llama.cpp, for `satyrn train export` ([Use the trained model](train.md#use-the-trained-model-with-satyrn-code)) |
| Settings | `config/` (instructions, model catalog, interpreter settings with update checks off), context window, port |

Each archive is downloaded into `.runtime/downloads`, checked against its SHA-256 and only then
unpacked, with Python's `tarfile` (using the safe `data` filter) or `zipfile`. A wrong checksum
deletes the download and stops: a tool archive that differs from its pin is never used.

Models are different: Ollama downloads a model by its tag (such as `gpt-oss:20b`), and the
model's publisher can move a tag to a newer build at any time. An older build cannot be
downloaded any more. So a model that differs from its pin is not an error; satyrn asks first.
See [When a model has changed](#when-a-model-has-changed).

To check an existing setup:

```bash
satyrn verify
```

It re-checks every archive, every unpacked tool and every pulled model against `pins.toml`. A
model that differs from its pin counts as a problem here, unless you accepted that version.

## When a model has changed

Before `satyrn pull`, `satyrn setup` or the guide download a model, satyrn asks the Ollama
registry which build the tag points to now. If that is not the build pinned in `pins.toml`, it
explains and asks:

```text
gpt-oss:20b has changed since this project tested and pinned it:
  pinned in pins.toml  f38aa0c53da5f8c49d08c43a99df24ff53167fe68e24664a7777288e7656fdfe
  available now        <the new digest>
It is most likely a newer build of the same model, but satyrn has not been tested with it.
Download and use it anyway? [Y/n]
```

Press {kbd}`Enter` to use it. Without a terminal to ask in (in scripts), satyrn uses the new
build and prints a warning. To avoid the question:

- **Answer yes once.** satyrn remembers your answer for this installation (in
  `.runtime/settings.toml`) and does not ask again for that build.
- **Update this project** with `git pull`. When a newer build has been tested, its digest is in
  the newer `pins.toml`.
- **Pin it yourself:** put the new digest under `[model.digests]` in `pins.toml`, as satyrn
  shows it, then run `satyrn check` to test the model.

## Updating a pin

Change a version only together with all of its checksums: download the new release files,
compute their SHA-256 (`python3.14 -c "import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest())" FILE`)
and update `pins.toml`. For a model, `satyrn pull NAME:TAG` shows the new digest.
Then run `setup`, `verify` and `check` (or `bench`) to see that everything still works.

For datasets and training:

- **A source of `satyrn data`** (`[data.sources.*]`): set `commit` to the new commit
  (`git ls-remote REPO refs/heads/main` shows the newest). Then run `satyrn data cpython` for each
  Python version: the dataset will differ, and the command prints the line with the new
  checksum to put into `[data.cpython]`.
- **Python packages** (`config/data/requirements.txt`, `config/train/requirements.txt`): change
  the `.in` file next to it and run the `uv pip compile` command written at its top. Delete the
  `.txt` file first to get the newest versions of everything, not only of what you changed. A
  new Sphinx can change a dataset too.
- **The training model** (`[train.model]`): set `revision` to the new Hugging Face commit and
  the SHA-256 of each file. The large files' checksums are listed on the model's page on
  Hugging Face (*Files*, then the file); compute the others as above.
- **The GGUF converter** (`[train.convert]`): set `commit` to a newer llama.cpp commit
  (`git ls-remote https://github.com/ggml-org/llama.cpp.git HEAD`) and run `satyrn train export`.

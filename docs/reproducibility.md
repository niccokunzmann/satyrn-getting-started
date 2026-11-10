# Reproducibility

Every input is pinned in `pins.toml`, so two setups made months apart get the same tools and
the same models, or stop with an error.

| Input | Pinned by |
| --- | --- |
| Ollama 0.40.15 | download URL and SHA-256 per platform: Linux x86-64 and ARM64, Windows, macOS |
| Open Interpreter 0.0.60 | download URL and SHA-256 per platform, including Windows and macOS on ARM |
| Models | manifest digest per model tag |
| Settings | `config/` (instructions, model catalog, interpreter settings with update checks off), context window, port |

Each archive is downloaded into `.runtime/downloads`, checked against its SHA-256 and only then
unpacked, with Python's `tarfile` (using the safe `data` filter) or `zipfile`. A wrong checksum
deletes the download and stops. A model whose tag now points to a different digest stops
`setup`, `pull` and `verify`.

To check an existing setup:

```bash
python3.14 satyrn.py verify
```

It re-checks every archive, every unpacked tool and every pulled model against `pins.toml`.

## Updating a pin

Change a version only together with all of its checksums: download the new release files,
compute their SHA-256 (`python3.14 -c "import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest())" FILE`)
and update `pins.toml`. For a model, `python3.14 satyrn.py pull NAME:TAG` prints the new digest.
Then run `setup`, `verify` and `check` (or `bench`) to see that everything still works.

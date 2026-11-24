# Create a dataset

A model learns new things from a **dataset**: a file with one training example per line
(JSON Lines, `.jsonl`). `satyrn data` creates datasets on your computer, from sources that are
pinned to exact versions. The same command creates the same file for everyone, byte for byte,
and checks that it did.

Creating a dataset needs no GPU and no model server, and it does not touch what `satyrn setup`
installed. It prepares its own tools the first time you use it.

## The example dataset

The example teaches a model what is new in Python 3.15. It is the same kind of dataset that
the [Satyrn models](projects.md) are trained with first (*continued pretraining*: the model
reads text and learns to continue it):

```bash
satyrn data cpython
```

It takes about three minutes, most of it for reading the CPython documentation (the first time
also a few minutes to download its tools and sources), and writes `datasets/python3.15/cpt.jsonl`: about 160 documents, 2.6 MB of text, made from

- every section of the [CPython documentation](https://docs.python.org/3.15/) that says it
  changed in Python 3.15 (`versionadded`, `versionchanged`, `deprecated` … `3.15`),
- the Python 3.15 *What's New* page,
- the PEPs that describe the new features of Python 3.15, such as
  [PEP 810](https://peps.python.org/pep-0810/) (explicit lazy imports) and
  [PEP 814](https://peps.python.org/pep-0814/) (`frozendict`).

At the end it compares the file with the checksum in `pins.toml`:

```text
datasets/python3.15/cpt.jsonl: 156 rows, 2.6 MB
reproduced: identical to the pinned build (sha256 ba1524ed…)
```

For Python 3.14 instead:

```bash
satyrn data cpython --python 3.14
```

Run `satyrn data` without a dataset name to see which datasets exist and which you have
created already.

### Look at it

Each line is one document, converted to Markdown:

```json
{"filename": "PEP810.rst", "text": "# PEP 810 – Explicit lazy imports\n..."}
```

A quick look with Python:

```bash
python3 -c "import json; [print(json.loads(l)['filename']) for l in open('datasets/python3.15/cpt.jsonl')]"
```

## How it is made

`satyrn data cpython` runs the dataset tools of
[satyrn-models](https://github.com/satyrn-ai/satyrn-models) (`corpus_builder`), the same code
that made the datasets the Satyrn models are trained on, but with every input pinned:

| Input | Pinned by |
| --- | --- |
| satyrn-models (the dataset code) | git commit in `pins.toml` |
| CPython (its `Doc/` folder) | git commit in `pins.toml` |
| PEPs | git commit of [python/peps](https://github.com/python/peps) in `pins.toml` |
| Sphinx and the other Python packages | `config/data/requirements.txt`: every package with its version and SHA-256 |
| The result | SHA-256 of each dataset in `pins.toml` |

The steps are those of satyrn-models'
[dataset guide](https://github.com/satyrn-ai/satyrn-models/blob/main/docs/dataset_generator.md):

1. Fetch only the needed folders of the three repositories at their pinned commits, with `git`.
2. Read the whole CPython documentation with Sphinx and collect the sections that changed in
   the Python version (`collect-doc-changes`).
3. Add the version's PEPs and *What's New* page. satyrn-models downloads these from the newest
   version of each repository; `satyrn data` takes them from the pinned commits instead.
4. Convert everything to Markdown, one row per document (`cpt`).
5. Compare the result with its pinned SHA-256.

If the result differs from the pin, the command fails and the file stays in `.runtime/data/build/`
instead of `datasets/`.
That happens when something in the chain changed, for example a different version of a Python
package. Updating a pin is described in [Reproducibility](reproducibility.md#updating-a-pin).

Everything except the dataset stays in `.runtime/data/`; delete that folder to start over.
Temporary files go there too, not to the system's temporary folder.

## Other datasets

satyrn-models also creates conversation datasets (*supervised fine-tuning*) and programming
tasks with tests (*reinforcement learning*). Those are written by a large language model through
the DeepSeek API, so they need an API key, cost money and are not byte-for-byte reproducible.
They are not part of `satyrn data` yet.

## Next: train a model

The dataset is the input for [training](train.md).

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

## Regex tasks

A small model cannot learn all of Python on a CPU, but it may learn something small. A regular
expression (*regex*) is such a thing: a short answer, and a program can check whether it is
right. This dataset teaches writing regexes for Python's `re`, for `grep` and for `sed`:

```bash
satyrn data regex
```

It takes about a minute and writes `datasets/regex/`:

| File | Content |
| --- | --- |
| `train.jsonl` | 15,533 tasks for training |
| `test.jsonl` | 648 tasks to measure a model with (`satyrn train test`); none of their regexes is in `train.jsonl` |
| `report.json` | how many tasks came from each source, and what was left out |
| `licenses/` | the licenses of the sources |

Each row is a question with its answer, as a chat, and the tests that check any answer:

```json
{"id": "train-00543", "source": "concept:date", "task": "describe+examples", "dialect": "grep -E", "mode": "line",
 "messages": [
  {"role": "user", "content": "grep -E: a pattern for the lines that are exactly a date like 2026-11-25: four digits, a dash, two digits, a dash, two digits.\nMatches: \"1821-98-57\", \"3395-65-02\"\nDoes not match: \"5454-454-7\", \"5454-45-47-\"\nAnswer with only the regular expression."},
  {"role": "assistant", "content": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$"}],
 "answer": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$",
 "match": ["1821-98-57", "3395-65-02", "5454-45-47", "0290-98-16", "1969-95-33", "9800-15-11"],
 "no_match": ["5454-454-7", "5454-45-47-", "0290-98#-1", "339-565-02", "182-198-57", "81821-98-57"]}
```

The prompt shows two strings of each kind; the tests have six. The near misses are the
interesting ones: `5454-45-47-` and `81821-98-57` are matching strings with one character
added, which a regex without `^` and `$` would wrongly accept.

An answer is right when it matches every string in `match` and none in `no_match` (for sed:
when it turns every input in `pairs` into its output). So any regex that does the job counts,
not only the one in the dataset. There are many ways to write the same regex.

### What is in it

| Kind (`task`) | The prompt gives | Tasks |
| --- | --- | ---: |
| `describe` | what to match, in words | 4,808 |
| `describe+examples` | the same, with two strings that match and two that do not | 4,951 |
| `examples` | only strings that match and strings that do not | 3,095 |
| `substitute` | what a sed command should do, with two examples | 1,360 |
| `translate` | a regex in one dialect, to rewrite for another | 660 |
| `fix` | a wrong regex and a string it gets wrong | 659 |

The dialects are Python (`re.fullmatch` or `re.search`, as the prompt says; 7,601 tasks),
`grep -E` (4,276), `grep` with basic regexes (2,296), `sed -E` (704) and `sed` (656).

The tasks come from these sources:

| Source | What | Tasks | License |
| --- | --- | ---: | --- |
| this project's concepts | 30 hand-written kinds of regex with natural descriptions: dates, times, versions, identifiers, IP addresses, file names, log lines, … with varying details | 4,298 | MIT (this project) |
| this project's generator | random regexes with a mechanical description ("two digits, then a dash") | 2,890 | MIT (this project) |
| this project's sed tasks | 16 kinds of substitution: swap words, reformat dates, remove tags, … | 1,360 | MIT (this project) |
| [StructuredRegex](https://github.com/xiye17/StructuredRegex) (Ye et al. 2020) | descriptions written by people, each with strings that match and that do not | 1,328 | MIT |
| [NL-RX-Turk and KB13](https://github.com/nicholaslocascio/deep-regex) (Locascio et al. 2016; Kushman and Barzilay 2013) | descriptions written by people, such as "lines with the word dog before a number" | 2,929 | MIT |
| [Lingua Franca](https://github.com/davisjam/LinguaFranca-FSE19) (Davis et al. 2019) | regexes from the code of real PyPI packages, with test strings made here | 2,728 | MIT |

Some regexes of the outside sources do not fit: StructuredRegex's `and`/`not` and NL-RX's `&`
and `~` (intersection, complement) need lookaheads, which grep and sed lack. Of the 43,896
regexes that PyPI packages use, 29,187 fit; the dataset takes the 2,838 that more than one
package uses and a sample of the others. `report.json` has the numbers.

### How the regex tasks are made

Every regex, from whatever source, is read into one small tree (characters, classes, repeats,
alternatives, groups, anchors). From the tree come

- the answer in each dialect: `\d{4}` in Python, `[0-9]{4}` for `grep -E`, `[0-9]\{4\}` for `grep`;
- a description, for the generated regexes and the real-world ones;
- the test strings: strings the regex matches, made by walking the tree, and *near misses*,
  matching strings with one character deleted, inserted, replaced, doubled or swapped that the
  regex no longer matches. Near misses show where a regex ends.

Then every reference answer is checked against its own tests, the Python ones with Python, the
grep and sed ones with the real `grep` and `sed`, with `LC_ALL=C` and sed's `--sandbox`. A task
whose answer fails is dropped (none did). The test split gets about 4 % of the regexes, chosen by
a hash of the regex, so that no regex is in both splits, and 150 descriptions from StructuredRegex's
own test split. In the test split, one answer appears at most three times per dialect: the concepts
and the sed substitutions make many tasks with the same answer, and without this limit they would
be half of the test tasks (336 test tasks are left out for this).

| Input | Pinned by |
| --- | --- |
| StructuredRegex, deep-regex, Lingua Franca | git commit in `pins.toml` (`[data.regex.sources]`) |
| The generator | the code in `src/satyrn_local/regex/` and a fixed seed; standard library only |
| The checks | GNU grep and GNU sed of this computer; their versions are in `report.json` |
| The result | SHA-256 of `train.jsonl` and `test.jsonl` in `pins.toml` |

### Sources that were not used

- **Stack Overflow** has many regex questions, but its posts are under CC BY-SA, which makes
  every model trained on them share-alike. The official dump sits behind an agreement that
  forbids training language models, and it is 69 GB.
- **RegexLib.com** and the datasets scraped from it (RegexEval) have no license.
- **regex101.com** forbids scraping in its terms; the datasets made from it inherit that.
- Test suites of regex engines (PCRE2, Rust's regex, RE2, GNU grep) are freely licensed, but
  they test unusual edge cases of the engines, not tasks someone would ask a model for.

## Other datasets

satyrn-models also creates conversation datasets (*supervised fine-tuning*) and programming
tasks with tests (*reinforcement learning*). Those are written by a large language model through
the DeepSeek API, so they need an API key, cost money and are not byte-for-byte reproducible.
They are not part of `satyrn data` yet.

## Next: train a model

The dataset is the input for [training](train.md).

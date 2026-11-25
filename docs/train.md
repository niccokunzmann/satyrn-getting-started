# Train a model

Training changes a model's weights so that it learns from a [dataset](data.md). `satyrn train`
is the command for it. There are two kinds of training run:

| | Small training | Real training |
| --- | --- | --- |
| Where | this computer, on the CPU | a rented NVIDIA GPU, for example on [RunPod](https://www.runpod.io/) or [Molab](https://molab.marimo.io/) |
| Model | Qwen2.5-0.5B-Instruct (0.5 billion parameters) | the Satyrn base models, for example Qwen3.8-27B |
| Purpose | check that the dataset and the training work, see what training looks like | a model that is better at new Python and that you can use with `satyrn code` |
| Command | `satyrn train small` | not in `satyrn` yet; use satyrn-models' [tutorial](https://github.com/satyrn-ai/satyrn-models/blob/main/docs/trainer_tutorial.md) |

A GPU is not just faster for real training: satyrn-models' trainer
([Unsloth](https://unsloth.ai/)) runs only on NVIDIA GPUs, and a 27-billion-parameter model
needs about 54 GB of memory just for its weights. The small training uses plain
[PyTorch](https://pytorch.org/) on the CPU instead, so it runs on any computer with 8 GB of
free memory.

## Small training on this computer

Create the example dataset first, then train:

```bash
satyrn data cpython
satyrn train small
```

The first run downloads its tools (PyTorch for the CPU and the Hugging Face libraries, about
1 GB) and the model (1 GB) into `.runtime/train/`. The trained adapter is 35 MB. All of them are pinned with their SHA-256.

`satyrn train small` then

1. splits the dataset into pieces of 512 tokens and keeps about one in ten back to test with
   (the *validation* set),
2. measures how well the untrained model predicts the validation pieces (the *validation loss*),
3. trains a [LoRA adapter](https://huggingface.co/docs/peft/main/en/conceptual_guides/lora):
   small extra weights next to the model's own, the same method satyrn-models uses,
4. measures the validation loss again every quarter of the run and at the end,
5. saves the adapter to `training/<run>/adapter/`.

While it trains, it shows its progress, the time it still needs and the loss:

```text
step 100/200   50%  loss 2.012  9.5 s/step  elapsed 0:16:50  remaining ~0:19:35
```

The loss tells you how badly the model predicted the next word of the text; it should go down.
If the validation loss goes down as well, the model has learned something general about the
documents and not only memorized the pieces it trained on.

At the end it prints the result:

```text
validation loss 2.145 -> 1.930 after 200 steps (0:36:03)
adapter: training/20261124-small/adapter
```

A whole run takes about 35 minutes on a laptop CPU (Intel i7-13700H). This is a real run with
the defaults on the example dataset:

| After step | 0 | 50 | 100 | 150 | 200 |
| --- | --- | --- | --- | --- | --- |
| Validation loss | 2.145 | 2.009 | 1.963 | 1.937 | 1.930 |

200 steps read 0.16 of the dataset, so this shows that the training works, not a finished model.

### Use the trained model with satyrn code

At the end, `satyrn train small` makes the trained model ready for `satyrn code`: it adds the
adapter to the model's own weights and imports the result into the project's Ollama as
`trained:<run>`. Then:

```bash
satyrn code ~/ai-code -m trained:20261124-small   # use it once
satyrn use trained:20261124-small                 # or make it your default
satyrn models                                     # it is listed with the prepared models
```

Tab completion knows the trained models too. `satyrn train export` does the same step for an
earlier run, or again after you deleted the model:

```bash
satyrn train export                    # the newest run with an adapter
satyrn train export 20261124-small     # a named run
```

It needs `satyrn setup` (for Ollama) and starts a temporary model server if none is running,
like `satyrn pull`. In Ollama the model takes 1 GB; the adapter in `training/<run>/adapter/`
stays as it is. Remove the model again with `satyrn ollama rm trained:<run>`.

How it is made:

1. the adapter is merged into a copy of the pinned base model (`merge_and_unload` of peft),
2. llama.cpp's converter, at a commit pinned in `pins.toml`, turns the merged weights into a
   GGUF file with 16-bit weights, the format Ollama runs,
3. Ollama imports the file with the chat template of Qwen2.5 in
   `config/train/qwen2.5.template`, which includes tool calls,
4. the export checks that Ollama reports the model as able to call tools; `satyrn code` needs
   that.

The intermediate files in `.runtime/train/export/` are deleted at the end.

```{warning}
The small model is for seeing the whole path work, from dataset to `satyrn code`. With half a
billion parameters it is far too small to work as a coding agent. In `satyrn check` it called
the `write` tool correctly and finished after a minute, but it wrote a wrong one-line program
to `/tmp/sqrt.py` instead of its working folder and then claimed to have run it. Asked what
PEP 750 adds, it answered in fluent English and wrongly (PEP 750 adds template strings): 200
steps over a sixth of the dataset do not teach it the new Python. Real training of a large
model is what makes a model that is better at new Python.
```

### Watch a running training

From another terminal:

```bash
satyrn train status
```

It shows the state of the newest run: running, finished or failed, the step, the loss and the
time remaining. Every run keeps its files in `training/<run>/`:

| File | Content |
| --- | --- |
| `train.log` | everything the run printed |
| `metrics.jsonl` | one line per step: loss, learning rate, seconds per step; one line per validation |
| `status.json` | the latest state, which `satyrn train status` reads |
| `adapter/` | the trained LoRA weights |

### When something goes wrong

The training stops with an error instead of carrying on with a broken model:

- when the loss is not a number (`nan` or `inf`), the usual sign that training has diverged
  (try a lower `--lr`),
- when the dataset is missing or empty,
- when the run is interrupted with {kbd}`Ctrl+C`; the state becomes `stopped`.

`status.json` and `train.log` then say what happened.

### Options

| Option | Default | Meaning |
| --- | --- | --- |
| `--data FILE` | `datasets/python3.15/cpt.jsonl` | the dataset to train on |
| `--steps N` | 200 | number of training steps, one 512-token piece each |
| `--lr RATE` | 1e-4 | learning rate, as satyrn-models uses for this stage |
| `--rank R` | 16 | LoRA rank: more extra weights with a higher rank |
| `--name NAME` | date and time + `small` | name of the run folder in `training/` |
| `--threads N` | two thirds of the CPUs | CPU threads for PyTorch; see [Speed](#speed) |

The data order and the starting weights of the adapter come from a fixed seed, so a run is
repeatable. Its numbers can still differ slightly on another computer.

### Speed

PyTorch's threads wait for each other at every step, so a single busy CPU holds all of them up.
Using every CPU is therefore the slowest choice. Measured on the development machine
(13 CPUs, Intel i7-13700H), one step of 512 tokens:

| Threads | 4 | 6 | 8 | 12 | 13 (all) |
| --- | --- | --- | --- | --- | --- |
| Seconds per step | 13.8 | 10.1 | **9.2** | 9.8 | 17.9 |

The default, two thirds of the CPUs, is 8 there. Leave the computer to itself while it trains:
other work, such as building a dataset at the same time, made steps two to three times slower.

## Real training on a GPU

Real training is the next step and not part of `satyrn` yet. Until it is, train with
satyrn-models directly, following its
[tutorial](https://github.com/satyrn-ai/satyrn-models/blob/main/docs/trainer_tutorial.md) on a
rented GPU. The dataset that `satyrn data cpython` creates has the same path and format as the
one in satyrn-models (`datasets/python3.15/cpt.jsonl`), so you can copy it there. The trained
model is exported as a 4-bit GGUF file, which Ollama can run.

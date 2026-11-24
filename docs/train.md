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
1 GB) and the model (1 GB) into `.runtime/train/`. All of them are pinned with their SHA-256.

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
step  40/200  20%  loss 1.92  4.1 s/step  elapsed 0:02:44  remaining ~0:10:56
```

The loss tells you how badly the model predicted the next word of the text; it should go down.
If the validation loss goes down as well, the model has learned something general about the
documents and not only memorized the pieces it trained on.

At the end it prints the result:

```text
validation loss 2.41 -> 1.87 after 200 steps (0:13:40)
adapter: training/20261124-2130-small/adapter
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

The data order and the starting weights of the adapter come from a fixed seed, so a run is
repeatable. Its numbers can still differ slightly on another computer.

## Real training on a GPU

Real training is the next step and not part of `satyrn` yet. Until it is, train with
satyrn-models directly, following its
[tutorial](https://github.com/satyrn-ai/satyrn-models/blob/main/docs/trainer_tutorial.md) on a
rented GPU. The dataset that `satyrn data cpython` creates has the same path and format as the
one in satyrn-models (`datasets/python3.15/cpt.jsonl`), so you can copy it there. The trained
model is exported as a 4-bit GGUF file, which Ollama can run.

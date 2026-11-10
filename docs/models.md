# Choose a model

Four models are prepared. `satyrn models` shows which of them fit your computer, together with
how they did in the benchmark below, so you can choose. The guide (`satyrn` without a command)
shows the same list when you have no model yet and recommends one.

## Which models fit your computer

```text
$ satyrn models
This computer: 40 GB memory, 72 GB free disk, 10 CPU cores, no GPU

  #  Model              Download  Memory  This computer    Small program*  Passed*
  1  gpt-oss:20b          14 GB   14 GB  fits                 2:08       6/6    recommended
  2  qwen3.6:35b-a3b      23 GB   22 GB  fits                 3:40       6/6
  3  qwen3.8:27b          18 GB   18 GB  fits, slow          11:55       6/6
  4  qwen3-coder:30b      19 GB   22 GB  fits                 4:04       4/6

  * on an Intel i7-13700H laptop CPU without GPU: median time to write and check sqrt.py,
    and the runs that passed in two benchmark rounds

How to select a model:
  satyrn pull gpt-oss:20b          download it, if it is not downloaded yet
  satyrn use gpt-oss:20b           make it your default (or by number: satyrn use 1)
  satyrn code DIR -m gpt-oss:20b   use a model just once
```

Download
: The size of the model files.

Memory
: What the model occupies while it runs, with the 32k-token context this project uses.
  Measured with Ollama.

This computer
: *fits* when the memory is there with 4 GB to spare for everything else, *tight* when the
  model fits only if you close other programs, *too big* when it does not fit, and
  *not enough disk* when the download does not fit. *slow* marks dense models on a computer
  without a suitable GPU. With an NVIDIA GPU that has enough memory, Ollama runs the model on
  the GPU, which is much faster than the times shown.

The list is sorted by how reliable and fast the models were. The recommended model is the
first one that fits without being slow; the guide offers it as the default answer. The last
column also marks models you have downloaded and your default.

## Select a model

The end of the list says how, with the recommended model as the example:

```bash
satyrn pull qwen3.6:35b-a3b    # download it; its digest is checked against pins.toml
satyrn use qwen3.6:35b-a3b     # make it your default for `satyrn code` and `satyrn check`
satyrn use 2                   # the same, by its number in `satyrn models`
satyrn code ~/ai-code -m qwen3-coder:30b   # or use another model just once
```

`satyrn use` stores your choice in `.runtime/`; the project's default in `pins.toml` stays
`gpt-oss:20b`.

## Benchmark

Every model got the same task as `check`: *create `sqrt.py` that prints the square root of
its argument*. The generated program was then run with 16, 2 and 0.25. Three runs per model,
each with the model freshly loaded and nothing else in memory.

Measured on Debian 13 with an Intel i7-13700H (10 cores available), no GPU, 32k context,
Ollama 0.40.15 and Open Interpreter 0.0.60:

| Model | Kind, size | Passed | Median time | Range | Read / write speed (tokens/s) |
| --- | --- | --- | ---: | --- | ---: |
| `gpt-oss:20b` (default) | MoE, 13 GB | 3/3 | 2:08 | 1:33–2:25 | 20 / 5.3 |
| `gpt-oss:20b`, low reasoning effort | MoE, 13 GB | 3/3 | 2:45 | 1:54–3:56 | 20 / 5.3 |
| `qwen3.6:35b-a3b` | MoE, 22 GB | 3/3 | 3:40 | 3:12–3:49 | 33 / 3.3 |
| `qwen3-coder:30b` | MoE, 18 GB | 2/3 | 4:04 | 3:59–4:09 | 22 / 4.3 |
| `qwen3.8:27b` (base model of [Satyrn's engine](satyrn-engine.md)) | dense, 17 GB | 3/3 | 11:55 | 11:45–19:32 | 6.2 / 1.6 |

Times are minutes:seconds for passing runs, without the 15–55 s it takes to load a model.
Read speed is how fast the model processes the prompt, write speed how fast it generates;
both are Ollama's own measurements.

- **`gpt-oss:20b`** passed every run. Low reasoning effort was not faster.
- **`qwen3.6:35b-a3b`** passed every run and is a good second choice if you have the memory.
- **`qwen3-coder:30b`** failed one run in three, the same way in two rounds of the
  benchmark: it typed its tool call into the answer as text instead of calling the tool, so
  nothing was created.
- **`qwen3.8:27b`** is reliable but slow without a GPU. It is a dense model: every generated
  token reads all 17 GB of weights, while the mixture-of-experts (MoE) models only read their
  3–4 billion active parameters.

Before this project gave the models [proper instructions](how-it-works.md#what-the-model-is-told),
the same task took `gpt-oss:20b` about 33 minutes.

## Reading the context before your request

Before a model can act on a request, it has to read everything that comes with it: the system
prompt, the tool definitions, a note about the sandbox and the environment. That is the same
7 KB of text for every request; the request itself is small. On a CPU, reading takes a large
part of the total time:

| Model | Context (tokens) | Read speed (tokens/s) | Time to read the context | Share of a typical run |
| --- | ---: | ---: | ---: | ---: |
| `gpt-oss:20b` | 1,559 | 21 | 73 s (64–80) | about 55 % |
| `qwen3.6:35b-a3b` | 2,760 | 33 | 85 s (81–117) | about 40 % |
| `qwen3-coder:30b` | 3,012 | 23 | 132 s (115–142) | about 55 % |
| `qwen3.8:27b` | 2,886 | 6.2 | 464 s (433–503) | about 65 % |

Medians of six runs each, freshly loaded model, from Ollama's own timings. The same text is
more tokens for the Qwen models because their tokenizers and chat templates differ.

This is the cost of the *first* request after a model was loaded. Ollama keeps what it has read
in a cache, so later requests in the same conversation only read what is new, and a new
conversation reuses the part of the context that has not changed while the model is still in
memory (30 minutes after the last request).

### What makes it faster

Measured with `gpt-oss:20b` and `satyrn bench`, three runs per row: the current context, and a
lean one (a 0.8 KB system prompt instead of 2.6 KB, without the environment block and the
sandbox note), each with a freshly loaded model and with the model still loaded from the run
before (`--warm`):

| Context | Model | Context read | Total time (median) |
| --- | --- | ---: | ---: |
| current, 7.1 KB | freshly loaded | 1,675 tokens in 88 s | 2:33 |
| current, 7.1 KB | still loaded | 495 new tokens in 21 s | 1:00 |
| lean, 3.5 KB | freshly loaded | 870 tokens in 39 s | 1:48 |
| lean, 3.5 KB | still loaded | 124 new tokens in 6 s | 1:07 |

- **Keep the model loaded.** Once Ollama has read the context, later tasks only read what is
  new, and a task takes about a minute. The first task after `satyrn start` (or after 30
  idle minutes) pays the full reading time.
- **A shorter context halves the reading time** of that first task, about 50 seconds here.
  The 2.5 KB of tool definitions are fixed by Open Interpreter and cannot be shortened.
- **Once loaded, writing dominates:** about 45 seconds of a one-minute task is the model
  generating its reasoning, the command and its answer. Low reasoning effort did not help.
- With the lean instructions, the model ran its program to check it in half of the runs,
  which adds a step; the current instructions rarely led to that for this task.

One run with the current context took 6:13 and one lean run 3:05, both while other work ran on
the same computer; the medians are not affected much. The lean variant is in
`experiments/instructions/lean.md`; making a compact context the default is the next step.

## Benchmark your own computer

```bash
satyrn bench                       # each model in config/models.toml once
satyrn bench gpt-oss:20b --runs 3
```

`bench` loads one model at a time, runs the square-root task and prints a table like the one
above, including how long the model took to read the context. Results are kept in
`.runtime/bench/`. A run that takes longer than an hour is stopped and counts as failed
(`--timeout` changes the limit). `--warm` keeps the model loaded between runs, and
`--instructions FILE` and `--set KEY=VALUE` try other instructions and interpreter settings.

## Add a model that is not listed

`satyrn code` and `satyrn use` accept only the listed models, because Open Interpreter has to be
told how to work with each model. To add one from the
[Ollama library](https://ollama.com/library):

1. `satyrn pull NAME:TAG`. It prints the line to add to `[model.digests]` in
   `pins.toml`; add it.
2. Add a `["NAME:TAG"]` table to `config/models.toml`. An empty table is enough; models with a
   reasoning-effort setting list it there, as `gpt-oss:20b` does.
3. Add its sizes and, if you benchmarked it, its results to that table, so that
   `satyrn models` can rate it.
4. Try it: `satyrn check --model NAME:TAG`.

The model must support tool calls in Ollama. Models with a "tools" tag in the library do.

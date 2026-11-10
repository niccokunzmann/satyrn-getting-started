# Choose a model

The default, `gpt-oss:20b`, was the fastest and most reliable model in the benchmark below, so
you do not need to change it. Three more models are prepared and can be pulled when you want to
compare.

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

## Use another model

```bash
python3.14 satyrn.py pull qwen3.6:35b-a3b                    # download it (22 GB)
python3.14 satyrn.py interpreter --oss -m qwen3.6:35b-a3b -C ~/ai-code
python3.14 satyrn.py check --model qwen3.6:35b-a3b           # the square-root test
```

`pull` compares the downloaded model with the digest in `pins.toml`, so you get exactly the
model that was benchmarked here. To make another model the default, set `[model].default` in
`pins.toml` and run `python3.14 satyrn.py setup` again.

## Benchmark your own computer

```bash
python3.14 satyrn.py bench                     # each model in config/models.toml once
python3.14 satyrn.py bench gpt-oss:20b --runs 3
```

`bench` loads one model at a time, runs the square-root task and prints a table like the one
above. Results are kept in `.runtime/bench/`. A run that takes longer than an hour is stopped
and counts as failed (`--timeout` changes the limit).

## Add a model that is not listed

Open Interpreter has to be told how to work with each model. To add one from the
[Ollama library](https://ollama.com/library):

1. `python3.14 satyrn.py pull NAME:TAG`. It prints the line to add to `[model.digests]` in
   `pins.toml`; add it.
2. Add a `["NAME:TAG"]` table to `config/models.toml`. An empty table is enough; models with a
   reasoning-effort setting list it there, as `gpt-oss:20b` does.
3. Try it: `python3.14 satyrn.py check --model NAME:TAG`.

The model must support tool calls in Ollama. Models with a "tools" tag in the library do.

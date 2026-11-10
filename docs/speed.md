# Speed: how to get the first answer sooner

What makes a local model slow to give its first answer, and what helps? This page tests one
guess at a time on the development machine and records the result. Speed-ups that do not change
what the model sees are built in; the ones that trade quality are described with their
trade-off. satyrn's defaults are the fastest settings that still give reasonable quality.

Measured on Debian 13 with an Intel i7-13700H (10 cores available), no GPU, 40 GB of memory,
Ollama 0.40.15 and `gpt-oss:20b` with a 32k context, unless a section says otherwise.

## Overview

| # | Guess | Result | In satyrn |
| --- | --- | --- | --- |
| 1 | Loading the model costs time on the first request | **confirmed:** 25–29 s per load | `satyrn start` loads the default model in the background (no quality effect) |
| 2 | Reading the agent's fixed context dominates the first answer; reading it in advance helps | measuring | `satyrn code` warms up in the background (no quality effect); `--no-warmup` |
| 3 | pi sends a smaller context than Open Interpreter | measuring | — |
| 4 | Ollama's batch size or thread count leave CPU speed unused | batch: **no** (within ±5 %); threads: measuring | — |
| 5 | Flash attention or a compressed context cache read faster | measuring | — |
| 6 | Open Interpreter's interactive mode sends an extra request that delays the first answer | measuring | — |
| 7 | Less reasoning gets to the first action sooner | **no** for whole tasks: low effort took 2:45 vs 2:08 ([benchmark](models.md#benchmark)) | — |

## 1. Loading the model

Before the first request, Ollama loads the model from disk into memory. Every load measured
here took 25–29 s for the 14 GB `gpt-oss:20b`. A model stays loaded for 30 minutes after its
last request (`OLLAMA_KEEP_ALIVE`).

Built in: `satyrn start` loads your default model in the background, so it is ready when you
open `satyrn code`. Memory is used the same way as before, only earlier.

## 4. Ollama settings: batch size and threads

How fast the model reads a prompt of about 1,430 tokens (`experiments/prompt_speed.py`, a new
first line each time so that Ollama's cache cannot help):

| Settings | Reading time |
| --- | ---: |
| default: batch 1,024, 10 threads | 63.5 s |
| batch 256 | 69.2 s |
| batch 2,048 | 60.6 s |

Batch size makes no difference beyond measuring noise, so satyrn keeps Ollama's defaults.
Thread counts are being measured.

## 2. Reading the context in advance (warm-up)

Built in, measurement pending: when `satyrn code` opens a conversation, it lets the same coding
agent answer "Reply with OK." in the same folder in the background, as a separate session. By
the time you send your first request, Ollama has the model loaded and the agent's whole fixed
context in its cache, so it only reads your request. Your conversation sees nothing of the
warm-up. `satyrn code --no-warmup` turns it off; `-p` requests skip it, as they are the first
request themselves.

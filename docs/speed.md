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
| 4 | Ollama's batch size or thread count leave CPU speed unused | **no:** batch size within ±5 %; fewer threads are slower | Ollama's defaults stay |
| 5 | Flash attention or a compressed context cache read faster | measuring | — |
| 6 | Open Interpreter's interactive mode sends an extra request that delays the first answer | **confirmed:** a task-title request, up to ~1.5 min | pi (the default) does not send it; no setting turns it off in Open Interpreter |
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
| 8 threads | 66.7 s |
| 6 threads | 82.2 s |

Batch size makes no difference beyond measuring noise, and fewer threads are slower: Ollama
already uses all 10 cores. So satyrn keeps Ollama's defaults. Changing these settings also
reloads the model, which took 17–29 s each time (guess 1).

## 2. Reading the context in advance (warm-up)

Built in, measurement pending: when `satyrn code` opens a conversation, it lets the same coding
agent answer "Reply with OK." in the same folder in the background, as a separate session. By
the time you send your first request, Ollama has the model loaded and the agent's whole fixed
context in its cache, so it only reads your request. Your conversation sees nothing of the
warm-up. `satyrn code --no-warmup` turns it off; `-p` requests skip it, as they are the first
request themselves.

## 6. Open Interpreter's extra title request

In a conversation, Open Interpreter names the task on screen. For that it sends a second
request to the model at the same moment as your first one: "Generate a concise, single-line task
title of at most 36 characters …", with the same 2.6 KB of instructions and medium reasoning.
Ollama on a CPU works on one request at a time, so your request can wait for the title: in the
recorded [hello-world session](generate.md#example-hello-world), the title took about 1.5 of
the 4.4 minutes. Found by recording the requests of the interactive mode
(`tui/src/app/thread_routing.rs` and `thread_title.rs` in Open Interpreter: a title is made
whenever a conversation without a name gets its first message).

There is no setting to turn it off. pi, satyrn's default coding agent, does not send such a
request: it names a session only when you do. Open Interpreter's single requests
(`satyrn code -p`) do not send it either.

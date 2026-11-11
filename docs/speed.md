# Speed: how to get the first answer sooner

What makes a local model slow to give its first answer, and what helps? This page tests one
guess at a time on the development machine and records the result. Speed-ups that do not change
what the model sees are built in; the ones that trade quality are described with their
trade-off. satyrn's defaults are the fastest settings that still give reasonable quality.

Measured on Debian 13 with an Intel i7-13700H (10 cores available), no GPU, 40 GB of memory,
Ollama 0.40.15 and `gpt-oss:20b` with a 32k context, unless a section says otherwise.

## Result

The default way to work, a conversation with `satyrn code`, now gets its first answer much
sooner, at the same quality (every measured run solved its task):

| Conversation, model not loaded at the start | First answer |
| --- | ---: |
| Open Interpreter (the recorded [hello-world session](generate.md#example-hello-world)) | 4 min 23 s |
| pi, without warm-up | 66 s |
| pi with warm-up, satyrn's default now | 37 s |

What brought it: pi as the default coding agent (a third less context, and no extra title
request), the warm-up while you type, and loading the model at `satyrn start`. What did not
help: Ollama's batch size and thread count, lower reasoning effort, and switching flash
attention (it is already on). The recorded Open Interpreter session also lost time to the
title request and to another session using the server, so the first row is not a clean
measurement; the two pi rows are.

Options that trade something else for speed:

- `OLLAMA_KV_CACHE_TYPE=q8_0` with `OLLAMA_FLASH_ATTENTION=1` when starting the server: about
  12 % faster writing, less memory for the context, but the context is stored less precisely.
  Not tested for quality here, so it is not the default.
- `OLLAMA_KEEP_ALIVE` (default 30 minutes): a longer time keeps the model and its cached
  context in memory across breaks, at the cost of 14–22 GB of memory while idle.
- A shorter system prompt for Open Interpreter (the lean variant in
  [Choose a model](models.md#what-makes-it-faster)): faster first reading, less guidance.

## Overview

| # | Guess | Result | In satyrn |
| --- | --- | --- | --- |
| 1 | Loading the model costs time on the first request | **confirmed:** 25–29 s per load | `satyrn start` loads the default model in the background (no quality effect) |
| 2 | Reading the agent's fixed context dominates the first answer; reading it in advance helps | **confirmed:** first task 1:27 → 0:40 with pi | `satyrn code` warms up in the background (no quality effect); `--no-warmup` |
| 3 | pi sends a smaller context than Open Interpreter | **confirmed:** 1,103 vs 1,692 tokens | pi is the default coding agent |
| 4 | Ollama's batch size or thread count leave CPU speed unused | **no:** batch size within ±5 %; fewer threads are slower | Ollama's defaults stay |
| 5 | Flash attention or a compressed context cache read faster | flash attention: **already on**; 8-bit cache: writes ~12 % faster | option, not default (stores the context less precisely) |
| 6 | Open Interpreter's interactive mode sends an extra request that delays the first answer | **confirmed:** a task-title request, up to ~1.5 min | pi (the default) does not send it; no setting turns it off in Open Interpreter |
| 7 | Less reasoning gets to the first action sooner | **no:** low effort 0:53 vs medium 0:47 (pi, after warm-up) | medium stays (Ollama's default for `gpt-oss`) |

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

Before a model can act on your first request, it reads the coding agent's whole fixed context:
the system prompt, the tool definitions and the working folder. On this CPU that takes most of
the first answer. Ollama caches what it has read, so the same context is read only once while
the model stays in memory.

Built in: when `satyrn code` opens a conversation, it lets the same coding agent answer "Reply
with OK." in the same folder in the background, as a separate session. By the time you send
your first request, Ollama has the model loaded and the context cached, and reads only your
request. Your conversation sees nothing of the warm-up, so quality is unchanged.
`satyrn code --no-warmup` turns it off; `-p` requests skip it, because they are the first
request themselves.

Measured with `satyrn bench gpt-oss:20b --harness pi --runs 2 [--warmup]`: the `sqrt.py` task,
the model freshly loaded each time, and with `--warmup` the warm-up first:

| | Read before the task | Task | Passed |
| --- | ---: | ---: | ---: |
| without warm-up | 1,103 tokens in 46–50 s | 1:20, 1:34 | 2/2 |
| after a warm-up | 37 new tokens in 2 s | 0:34, 0:47 | 2/2 |

The warm-up itself took 47–52 s; it runs while you read and type.

The same in a real conversation, measured with `experiments/first_answer.py`: `satyrn code`
with pi in a terminal, the model not loaded at the start (as after a break), the request sent
after 30 seconds of reading and typing, and the time from sending it until the model is done:

| | First answer | Result |
| --- | ---: | --- |
| `satyrn code` (with warm-up) | 36.5 s | `hello.py` prints `Hello, World!` |
| `satyrn code --no-warmup` | 65.9 s | `hello.py` prints `Hello, World!` |

Without the warm-up, that first request had to load the model and read 947 tokens of context
first; with it, both had happened while the request was being typed.

## 3. The size of the context per coding agent

The first request of each agent, with satyrn's contexts (same task as above, without warm-up):

| Coding agent | Context before the request | Reading it | Task |
| --- | ---: | ---: | ---: |
| pi | 1,103 tokens | 46–50 s | 1:20, 1:34 |
| Open Interpreter | 1,692 tokens | 66 s | 1:45 |

pi needs about a third fewer tokens: a short system prompt and four small tool definitions,
against Open Interpreter's larger tool definitions, sandbox note and environment block. Both
passed the task. pi is satyrn's default coding agent.

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

## 7. Less reasoning

`gpt-oss:20b` thinks before it acts; its reasoning effort can be low, medium (the default) or
high. Less reasoning could mean fewer tokens to write before the first command. Measured with
`satyrn bench gpt-oss:20b --harness pi --warmup --effort low` against the default, so that the
context is already read and only writing counts:

| Reasoning effort | Task | Written tokens | Passed |
| --- | ---: | ---: | ---: |
| low | 0:53, 1:17, 0:40 | 262, 553, 257 | 3/3 |
| medium (default) | 0:49, 0:45 | 363, 323 | 2/2 |

Low effort is not faster: the model sometimes writes more instead of less. Medium stays the
default. With Open Interpreter the result was the same (2:45 low against 2:08 medium in the
[benchmark](models.md#benchmark)). To try it anyway: `satyrn pi --thinking low` or, for Open
Interpreter, `satyrn interpreter -c model_reasoning_effort=\"low\"`.

## 5. Flash attention and a compressed context cache

Server settings, measured with `experiments/prompt_speed.py --write 128 --server-env ...` on a
temporary server, the same 1,436-token prompt, the model writing 128 tokens, two runs each:

| Server setting | Reading (tokens/s) | Writing (tokens/s) |
| --- | ---: | ---: |
| default (flash attention "auto") | 23.5, 25.1 | 8.0, 8.2 |
| `OLLAMA_FLASH_ATTENTION=0` | 20.7, 20.2 | 7.8, 7.4 |
| `OLLAMA_FLASH_ATTENTION=1` | 23.4, 25.1 | 8.1, 8.2 |
| `OLLAMA_FLASH_ATTENTION=1`, `OLLAMA_KV_CACHE_TYPE=q8_0` | 23.4, 22.6 | 9.0, 9.2 |

"auto" already turns flash attention on; turning it off is slower. The 8-bit context cache
writes about 12 % faster and needs less memory, but keeps the context less precisely; it stays
an option (see [Result](#result)).

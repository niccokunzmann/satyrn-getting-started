# Generate code

The model works in one folder: it can read and write files there and run programs. Give it a
folder for this purpose, not your home directory. `satyrn code` creates the folder if needed.
If the model server is not running, it asks whether to start it.

## Talk to it

```bash
satyrn code ~/ai-code
```

The first time you use a folder, Open Interpreter asks whether you trust it, because settings
inside a folder can run code. Choose *1. Trust and continue* for a folder of your own; the answer
is remembered. Its screens still say "Codex" in places, as in that question and in the hint
*Ask Codex to do anything*: Open Interpreter is based on OpenAI's Codex CLI. `satyrn` asks it to
call itself Satyrn (`OPEN_INTERPRETER_PRODUCT_NAME`); version 0.0.60 does not support that yet,
and a change that adds it has been prepared for Open Interpreter. The header shows what
actually runs:

```text
>_ Open Interpreter (v0.0.60)
model:     ollama gpt-oss:20b
directory: /home/you/ai-code
```

Type a request and press {kbd}`Enter`. The interpreter shows each command the model runs and
its output, and may ask for your approval first. You can ask for changes in the same
conversation. {kbd}`Ctrl+C` leaves. Without a folder, `satyrn code` works in the current one.

## One request, no conversation

```bash
satyrn code ~/ai-code -p "Write fizzbuzz.py that prints FizzBuzz for 1 to 15. Run it and tell me the output."
```

With `-p`, the model works on the request until it is done, prints its answer and exits. This
is handy in scripts; it is also how this project's tests and benchmarks drive the model. The
model may write files only in the folder (and in temporary folders).

Both forms accept `-m MODEL` to use another model than your default for this one time, for
example `-m qwen3.6:35b-a3b` or its number, `-m 2`. Only the models that `satyrn models` lists
can be used: Open Interpreter needs instructions and settings for each model, and those exist
only for the listed ones. See [Add a model that is not listed](models.md#add-a-model-that-is-not-listed).

## Write good requests

The model only knows what you tell it and what it finds in the folder.

- Name the file and the language: *Create `wordcount.py` that …* works better than *count words*.
- Say how to check the result: *… then run it on `README.md` and show the output.*
- For changes, point at the file: *In `wordcount.py`, ignore case when counting.*
- Keep each request to one step. Ask for the next change after you have seen the result.

The model is told to check its work by running it and to finish with a short summary of what
it changed. See [How it works](how-it-works.md) for everything it is told.

## Use Open Interpreter directly

`satyrn interpreter …` runs the project's copy of Open Interpreter with the project's settings
and passes every argument on, so all of its own options are available:

```bash
satyrn interpreter --oss -C ~/ai-code             # what `satyrn code ~/ai-code` runs
satyrn interpreter exec --help                     # its non-interactive mode
```

The interpreter keeps its settings and history in `.runtime/interpreter-home`, so an Open
Interpreter you may have installed before is not touched. `satyrn ollama …` does the same for
Ollama's command line, for example `satyrn ollama list`.

## Stop

```bash
satyrn stop
```

The model stays in memory for 30 minutes after its last request, then Ollama frees the memory
on its own. `stop` ends the server right away.

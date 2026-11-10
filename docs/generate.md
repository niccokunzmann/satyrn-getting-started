# Generate code

Start the model server first (`python3.14 satyrn.py start`), then use Open Interpreter in one
of two ways. In both, the model works in one folder: it can read and write files there and
run programs, so give it a folder for this purpose, not your home directory.

## Talk to it

```bash
mkdir -p ~/ai-code
python3.14 satyrn.py interpreter --oss -C ~/ai-code
```

`--oss` selects the local model, `-C` the folder to work in. Type a request and press
{kbd}`Enter`. The interpreter shows each command the model runs and its output, and may ask for
your approval first. You can ask for changes in the same conversation. {kbd}`Ctrl+C` leaves.

## One request, no conversation

`interpreter exec` runs a single request to the end and prints the model's answer. This is
handy in scripts, and it is how this project's tests and benchmarks drive the model:

```bash
python3.14 satyrn.py interpreter exec --oss --skip-git-repo-check -s workspace-write -C ~/ai-code \
  "Write fizzbuzz.py that prints FizzBuzz for 1 to 15. Run it and tell me the output."
```

`-s workspace-write`
: Lets the model write files in the `-C` folder (and temporary folders), nowhere else.

`--skip-git-repo-check`
: Allows folders that are not git repositories.

`-m MODEL`
: Uses another model for this request, for example `-m qwen3.6:35b-a3b`.

## Type `interpreter` instead of `python3.14 satyrn.py interpreter`

`setup` creates small launchers. Put them on your `PATH` for the current terminal, and
`interpreter` and `ollama` run the project's copies with the project's settings:

::::{tab-set}

:::{tab-item} bash / zsh
:sync: posix

```bash
source .runtime/activate
cd ~/ai-code
interpreter --oss
```

:::

:::{tab-item} PowerShell
:sync: windows

```powershell
. .runtime\activate.ps1
cd $HOME\ai-code
interpreter --oss
```

:::

:::{tab-item} cmd.exe

```bat
.runtime\activate.bat
cd %USERPROFILE%\ai-code
interpreter --oss
```

:::

::::

Without `-C`, the model works in the current folder. The interpreter keeps its settings and
history in `.runtime/interpreter-home`, so an Open Interpreter you may have installed before is
not touched.

## Write good requests

The model only knows what you tell it and what it finds in the folder.

- Name the file and the language: *Create `wordcount.py` that …* works better than *count words*.
- Say how to check the result: *… then run it on `README.md` and show the output.*
- For changes, point at the file: *In `wordcount.py`, ignore case when counting.*
- Keep each request to one step. Ask for the next change after you have seen the result.

The model is told to check its work by running it and to finish with a short summary of what
it changed. See [How it works](how-it-works.md) for everything it is told.

## Stop

```bash
python3.14 satyrn.py stop
```

The model stays in memory for 30 minutes after its last request, then Ollama frees the memory
on its own. `stop` ends the server right away.

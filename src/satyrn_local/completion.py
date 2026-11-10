"""Tab completion for bash, zsh, fish and PowerShell.

The shell scripts are thin: they call `satyrn __complete INDEX WORDS...` and show what it prints.
The candidates come from the argparse parser itself (commands and options) and from
config/models.toml (model names), so completion cannot drift from the real command line.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable

DIRS, FILES = "@dirs", "@files"  # tell the shell script to complete paths itself

SHELLS = ("bash", "zsh", "fish", "powershell")

BASH = r"""# Tab completion for satyrn (installed by `satyrn install`).
_satyrn() {
    local cur words cword out
    if declare -F _get_comp_words_by_ref >/dev/null; then
        _get_comp_words_by_ref -n : cur words cword  # keep "gpt-oss:20b" in one piece
    else
        cur=${COMP_WORDS[COMP_CWORD]}; words=("${COMP_WORDS[@]}"); cword=$COMP_CWORD
    fi
    local IFS=$'\n'
    out=$(satyrn __complete "$cword" "${words[@]}" 2>/dev/null)
    case "$out" in
        @dirs) COMPREPLY=($(compgen -d -- "$cur")) ;;
        @files) COMPREPLY=($(compgen -f -- "$cur")) ;;
        *) COMPREPLY=($(compgen -W "$out" -- "$cur")) ;;
    esac
    if declare -F __ltrim_colon_completions >/dev/null; then __ltrim_colon_completions "$cur"; fi
}
complete -o filenames -F _satyrn satyrn
"""

ZSH = r"""#compdef satyrn
# Tab completion for satyrn (installed by `satyrn install`).
local -a out
out=("${(@f)$(satyrn __complete $((CURRENT - 1)) "${words[@]}" 2>/dev/null)}")
case "$out[1]" in
    @dirs) _path_files -/ ;;
    @files) _files ;;
    *) compadd -- $out ;;
esac
"""

FISH = r"""# Tab completion for satyrn (installed by `satyrn install`).
function __satyrn_complete
    set -l words (commandline -opc) (commandline -ct)
    set -l out (satyrn __complete (math (count $words) - 1) $words 2>/dev/null)
    switch "$out[1]"
        case @dirs
            __fish_complete_directories (commandline -ct)
        case @files
            __fish_complete_path (commandline -ct)
        case '*'
            printf '%s\n' $out
    end
end
complete -c satyrn -f -a '(__satyrn_complete)'
"""

POWERSHELL = r"""# Tab completion for satyrn (installed by `satyrn install`).
Register-ArgumentCompleter -Native -CommandName satyrn -ScriptBlock {
    param($wordToComplete, $commandAst, $cursorPosition)
    $words = @($commandAst.CommandElements | ForEach-Object { $_.ToString() })
    $index = if ($wordToComplete) { $words.Count - 1 } else { $words.Count }
    $out = @(satyrn __complete $index @words 2>$null)
    if ($out.Count -gt 0 -and $out[0] -in '@dirs', '@files') {
        Get-ChildItem -Path "$wordToComplete*" -Directory:($out[0] -eq '@dirs') -ErrorAction Ignore |
            ForEach-Object { [System.Management.Automation.CompletionResult]::new($_.Name) }
    } else {
        $out | ForEach-Object { [System.Management.Automation.CompletionResult]::new($_) }
    }
}
"""

SCRIPTS = {"bash": BASH, "zsh": ZSH, "fish": FISH, "powershell": POWERSHELL}

# Which values an option or a command's positional argument takes.
MODEL_OPTIONS = {"-m", "--model"}
VALUE_CHOICES = {"--effort": ("low", "medium", "high")}
PATH_OPTIONS = {"--instructions": FILES}
POSITIONALS = {"pull": "models", "use": "models", "bench": "models", "code": DIRS, "completion": "shells"}
PASS_THROUGH = {"interpreter", "ollama"}


def _subparsers(parser: argparse.ArgumentParser) -> dict[str, argparse.ArgumentParser]:
    for action in parser._actions:  # argparse has no public way to list them
        if isinstance(action, argparse._SubParsersAction):
            return dict(action.choices)
    return {}


def _options(parser: argparse.ArgumentParser) -> list[str]:
    return [option for action in parser._actions for option in action.option_strings]


def complete(
    parser: argparse.ArgumentParser, words: list[str], index: int, models: Callable[[], list[str]]
) -> list[str]:
    """Candidates for ``words[index]``; ``words[0]`` is the program name."""
    current = words[index] if index < len(words) else ""
    previous = words[index - 1] if 0 < index <= len(words) else ""
    commands = _subparsers(parser)
    if index <= 1:
        found = [name for name in commands if not name.startswith("_")] + ["--help"]
    else:
        command = words[1]
        sub = commands.get(command)
        if sub is None or command in PASS_THROUGH:
            return [FILES]
        if previous in MODEL_OPTIONS:
            found = models()
        elif previous in VALUE_CHOICES:
            found = list(VALUE_CHOICES[previous])
        elif previous in PATH_OPTIONS:
            return [PATH_OPTIONS[previous]]
        elif current.startswith("-"):
            found = _options(sub)
        else:
            kind = POSITIONALS.get(command)
            if kind == DIRS:
                return [DIRS]
            found = models() if kind == "models" else list(SHELLS) if kind == "shells" else []
    return [word for word in found if word.startswith(current)]

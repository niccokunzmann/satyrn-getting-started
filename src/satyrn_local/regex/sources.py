"""Regexes from outside: real descriptions and real-world patterns, each read into the tree.

- StructuredRegex (Ye et al. 2020, MIT): descriptions written by people, each with strings that
  must and must not match. Written in its own notation (concat, repeatatleast, ...), translated
  here; the parts with ``and``/``not`` need lookaheads and are left out.
- NL-RX-Turk and KB13 (Locascio et al. 2016, Kushman and Barzilay 2013; MIT): descriptions by
  people for regexes; ``&`` (intersection) and ``~`` (complement) are left out.
- Lingua Franca (Davis et al. 2019, MIT): regexes from the code of real packages; the ones used
  in PyPI packages that the tree can hold.

Every translated regex is checked against the source's own examples where it has some.
"""

from __future__ import annotations

import json
import random
import re
import warnings
from pathlib import Path

from .describe import describe
from .tasks import Item
from .tree import (
    ALNUM,
    DIGIT,
    LETTER,
    LOWER,
    UPPER,
    Anchor,
    AnyChar,
    Cls,
    Lit,
    Node,
    Rep,
    Seq,
    alt,
    ch,
    from_python,
    opt,
    rep,
    risky,
    seq,
    simplify,
    size,
    to_python,
    walk,
)

START, END = Anchor("start"), Anchor("end")
ANY_RUN = Rep(AnyChar(), 0, None)

# --- StructuredRegex -------------------------------------------------------------------------

SPEC = "-,;.+:!@#_$%&*=^"  # its <spec>: the special characters of its examples
TOKENS = {
    "<num>": DIGIT,
    "<let>": LETTER,
    "<low>": LOWER,
    "<cap>": UPPER,
    "<alphanum>": ALNUM,
    "<any>": AnyChar(),
    "<spec>": Cls(tuple(ch(c) for c in SPEC)),
}


class Unsupported(Exception):  # noqa: N818 - a reason to skip, not an error
    pass


def _streg(text: str) -> Node:
    pos = 0

    def node() -> Node:
        nonlocal pos
        if text.startswith("<", pos):
            end = text.index(">", pos + 2)  # a token holds at least one character, even <>>
            token = text[pos : end + 1]
            pos = end + 1
            if token in TOKENS:
                return TOKENS[token]
            return Lit(token[1:-1])
        name = re.match(r"[a-z]+", text[pos:])
        if not name:
            raise Unsupported(text[pos:])
        op = name.group()
        pos += len(op)
        if text[pos] != "(":
            raise Unsupported(op)
        pos += 1
        args: list = []
        while True:
            if text[pos].isdigit():
                number = re.match(r"\d+", text[pos:]).group()
                pos += len(number)
                args.append(int(number))
            else:
                args.append(node())
            if text[pos] == ",":
                pos += 1
                continue
            if text[pos] == ")":
                pos += 1
                break
            raise Unsupported(text[pos:])
        match op, args:
            case "concat", [a, b]:
                return seq(a, b)
            case "or", [a, b]:
                return alt(a, b)
            case "repeat", [a, n]:
                return rep(a, n, n)
            case "repeatatleast", [a, n]:
                return rep(a, n, None)
            case "repeatrange", [a, n, m]:
                return rep(a, n, m)
            case "optional", [a]:
                return opt(a)
            case "star", [a]:
                return rep(a, 0, None)
            case "contain", [a]:
                return seq(ANY_RUN, a, ANY_RUN)
            case "startwith", [a]:
                return seq(a, ANY_RUN)
            case "endwith", [a]:
                return seq(ANY_RUN, a)
            case "notcc", [Cls(items, False)]:
                return Cls(items, negate=True)
            case "const", [Lit() as a]:
                return a
        raise Unsupported(op)  # and, not: they need lookaheads

    tree = node()
    if pos != len(text):
        raise Unsupported(text[pos:])
    return tree


def as_line(tree: Node) -> tuple[Node, str]:
    """``.*x.*`` as the "contains" regex ``x``, ``x.*`` as ``^x``, ``.*x`` as ``x$``; else whole."""
    parts = list(tree.parts) if isinstance(tree, Seq) else [tree]
    lead, trail = parts[0] == ANY_RUN, parts[-1] == ANY_RUN
    if len(parts) < 2 or not (lead or trail):
        return tree, "whole"
    inner = parts[1 if lead else 0 : -1 if trail else None]
    if not inner:
        return tree, "whole"
    return seq(*([] if lead else [START]), *inner, *([] if trail else [END])), "line"


def _brief(examples: str) -> list[str]:
    return [s for s in examples.split(" ") if s]


def structured_regex(folder: Path) -> tuple[list[Item], list[Item], dict]:
    """(training items, test items, counts): its train and dev splits, and its test splits."""
    train, test, counts = [], [], {"rows": 0, "and/not": 0, "examples disagree": 0}
    for split in ("train", "dev", "teste", "testi"):
        lines = (folder / "data" / "raw" / f"{split}.tsv").read_text(encoding="utf-8").splitlines()
        for line in lines[1:]:
            problem, text, notation, good, bad = line.split("\t")
            counts["rows"] += 1
            try:
                tree = simplify(_streg(notation))
            except Unsupported:
                counts["and/not"] += 1
                continue
            good, bad = _brief(good), _brief(bad)
            rx = re.compile(to_python(tree))
            if not all(rx.fullmatch(s) for s in good) or any(rx.fullmatch(s) for s in bad):
                counts["examples disagree"] += 1
                continue
            item = Item(
                tree,
                " ".join(text.split()),
                "whole",
                "structured-regex",
                natural=True,
                sentence=True,
                given=(good, bad),
                group=problem,
            )
            (test if split.startswith("test") else train).append(item)
    return train, test, counts


# --- NL-RX and KB13 ------------------------------------------------------------------------


def nl_rx(folder: Path, name: str) -> tuple[list[Item], dict]:
    sources = (folder / "datasets" / name / "src.txt").read_text(encoding="utf-8").splitlines()
    targets = (folder / "datasets" / name / "targ.txt").read_text(encoding="utf-8").splitlines()
    items, counts = [], {"rows": len(sources), "& or ~": 0, "not readable": 0}
    for line, target in zip(sources, targets, strict=True):
        if "&" in target or "~" in target:
            counts["& or ~"] += 1
            continue
        tree = from_python(target)
        if tree is None or risky(tree):
            counts["not readable"] += 1
            continue
        tree, kind = as_line(simplify(tree))
        text = " ".join(line.split()).rstrip(".")
        items.append(Item(tree, text, kind, name.lower(), natural=True, sentence=True))
    return items, counts


# --- Lingua Franca -------------------------------------------------------------------------


def lingua_franca(path: Path, r: random.Random, limit: int) -> tuple[list[Item], dict]:
    """Regexes used in PyPI packages: all used by more than one package, the rest a sample."""
    used: dict[str, int] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        entry = json.loads(line)
        pattern, pypi = entry["pattern"], entry["useCount_registry_to_nModules"].get("pypi", 0)
        if isinstance(pattern, str) and pypi:
            used[pattern] = pypi
    counts = {"pypi regexes": len(used)}
    usable = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for pattern in sorted(used):
            tree = from_python(pattern)
            if tree is None or risky(tree) or not 4 <= size(tree) <= 40:
                continue
            if all(isinstance(n, Lit | Seq) for n in walk(tree)):
                continue  # plain text, no regex in it
            usable.append((pattern, tree))
    counts["the tree can hold"] = len(usable)
    popular = [(p, t) for p, t in usable if used[p] > 1]
    rest = [(p, t) for p, t in usable if used[p] == 1]
    chosen = popular + r.sample(rest, max(0, min(len(rest), limit - len(popular))))
    counts["chosen"] = len(chosen)
    items = [Item(t, f"contain {describe(t, r)}", "line", "lingua-franca", natural=False, group=p) for p, t in chosen]
    return items, counts

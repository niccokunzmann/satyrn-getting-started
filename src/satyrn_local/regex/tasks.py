"""Tasks: a prompt, the reference answer and the tests that any right answer must pass.

Kinds of task (``task``):

- ``describe``: a description in words, the regex is the answer,
- ``describe+examples``: the same with a few examples,
- ``examples``: only strings that must and must not match,
- ``translate``: a regex in one dialect, rewritten for another,
- ``fix``: a wrong regex and a string it gets wrong, the corrected regex is the answer,
- ``substitute``: a sed s command that turns the inputs into the outputs.

Dialects: ``python`` (re.fullmatch or re.search, as the prompt says), ``grep -E``, ``grep``
(basic regular expressions), ``sed -E`` and ``sed``.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, replace

from . import sample
from .describe import CHAR_NAMES, describe, quote
from .tree import (
    DIGIT,
    HEX,
    LETTER,
    LOWER,
    LOWER_HEX,
    SPACE,
    UPPER,
    WORD,
    Alt,
    Anchor,
    AnyChar,
    Cls,
    Group,
    Lit,
    Node,
    Rep,
    Seq,
    alt,
    ch,
    cls,
    render,
    rep,
    risky,
    seq,
    size,
    to_python,
    walk,
)

START, END, BOUNDARY = Anchor("start"), Anchor("end"), Anchor("word")
ONLY = "Answer with only the regular expression."
ONLY_SED = "Answer with only the sed command, an s/regex/replacement/ expression."
GREP = {"grep -E": "grep -E", "grep": "grep (basic regular expressions, without -E)"}
SED = {"sed -E": "sed -E", "sed": "sed (basic regular expressions, without -E)"}
POSITIVES, NEGATIVES = 6, 6  # tests per task; the prompt shows a few of them


@dataclass
class Item:
    """Something to make tasks from: a tree and what it means."""

    tree: Node
    text: str  # kind "whole": what the whole string is; kind "line": what a line does
    kind: str  # "whole" or "line"
    source: str
    natural: bool  # a description by a person, not a mechanical one
    sentence: bool = False  # the description is a sentence of its own, not a phrase
    given: tuple[list[str], list[str]] | None = None  # the source's own tests (whole strings)
    group: str | None = None  # items of one group go to the same split (training or test)

    def key(self) -> str:
        return self.group or to_python(self.tree)


def examples_text(match: list[str], no_match: list[str]) -> str:
    lines = []
    if match:
        lines.append("Matches: " + ", ".join(quote(s) for s in match))
    if no_match:
        lines.append("Does not match: " + ", ".join(quote(s) for s in no_match))
    return "\n".join(lines)


def row(source: str, task: str, dialect: str, mode: str, prompt: str, answer: str, **tests: list) -> dict:
    return {
        "source": source,
        "task": task,
        "dialect": dialect,
        "mode": mode,
        "messages": [{"role": "user", "content": prompt}, {"role": "assistant", "content": answer}],
        "answer": answer,
        **tests,
    }


def tests_for(tree: Node, mode: str, r: random.Random) -> tuple[list[str], list[str]] | None:
    good = sample.positives(tree, mode, r, POSITIVES)
    if len(good) < 2:
        return None
    bad = sample.negatives(tree, mode, good, r, NEGATIVES)
    if len(bad) < 2:
        return None
    return good, bad


def _head(item: Item, dialect: str, r: random.Random, *, whole: bool) -> str:
    """The first line of a prompt, with {} for the description."""
    if item.sentence:
        if dialect == "python":
            func = "re.fullmatch" if whole else "re.search"
            return f"Write a Python regular expression for {func} from this description:\n{{}}"
        what = "whole lines" if whole else "lines"
        return f"Write a regular expression for {GREP[dialect]} that selects {what} as described:\n{{}}"
    if dialect == "python" and whole:
        return r.choice(
            (
                "Write a Python regular expression for re.fullmatch that matches {}.",
                "Give me a Python regex, used with re.fullmatch, for {}.",
                "Python regular expression (re.fullmatch) for {}.",
            )
        )
    if dialect == "python":
        return r.choice(
            (
                "Write a Python regular expression for re.search that matches the strings that {}.",
                "Give me a Python regex for re.search that finds the lines that {}.",
            )
        )
    return r.choice(
        (
            f"Write a regular expression for {GREP[dialect]} that selects the lines that "
            + ("consist of {}." if whole else "{}."),
            f"{GREP[dialect]}: a pattern for the lines that " + ("are exactly {}." if whole else "{}."),
        )
    )


def match_task(item: Item, dialect: str, task: str, r: random.Random) -> dict | None:
    """describe, describe+examples or examples, for a match dialect (python, grep -E, grep)."""
    whole = item.kind == "whole" and (dialect == "python" or item.sentence or r.random() < 0.8)
    contains = item.kind == "whole" and not whole
    mode = "fullmatch" if whole else "search"
    tests = item.given if item.given and whole else tests_for(item.tree, mode, r)
    if tests is None:
        return None
    good, bad = list(tests[0]), list(tests[1])
    if dialect == "python":
        answer = to_python(item.tree)
        mode_name = mode
    else:
        answer = render(seq(START, item.tree, END) if whole else item.tree, dialect)
        if answer is None:
            return None
        mode_name = "line" if whole else "contains"
    text = f"contain {item.text}" if contains else item.text
    if task == "examples":
        shown_good, shown_bad = good[:4], bad[:4]
        if dialect == "python":
            func = "re.fullmatch" if whole else "re.search"
            prompt = (
                f"Write a Python regular expression for {func} that matches the strings below that should match, "
                "and none of the others."
            )
        else:
            what = "whole lines" if whole else "lines"
            prompt = (
                f"Write a regular expression for {GREP[dialect]} that selects the {what} below that should match, "
                "and none of the others."
            )
        prompt += "\n" + examples_text(shown_good, shown_bad)
        good, bad = shown_good, shown_bad
    else:
        prompt = _head(item, dialect, r, whole=whole).format(text)
        if task == "describe+examples":
            prompt += "\n" + examples_text(good[:2], bad[:2])
    prompt += "\n" + ONLY
    return row(item.source, task, dialect, mode_name, prompt, answer, match=good, no_match=bad)


def translate_task(item: Item, r: random.Random) -> dict | None:
    pairs = [("python", "grep -E"), ("python", "grep"), ("grep -E", "python"), ("grep", "grep -E"), ("grep -E", "grep")]
    source, target = r.choice(pairs)
    src, answer = render(item.tree, source), render(item.tree, target)
    if src is None or answer is None or src == answer:
        return None
    tests = tests_for(item.tree, "search", r)
    if tests is None:
        return None
    names = {"python": "Python (re.search)", **GREP}
    prompt = (
        f"Rewrite this {names[source]} regular expression for {names[target]}, so that it matches the same:"
        f"\n{src}\n{ONLY}"
    )
    mode = "search" if target == "python" else "contains"
    return row(item.source, "translate", target, mode, prompt, answer, match=tests[0], no_match=tests[1])


# --- fix: a wrong regex and what it gets wrong ------------------------------------------------

BROADER = {DIGIT: WORD, LOWER: LETTER, UPPER: LETTER, LOWER_HEX: HEX, LETTER: WORD}


def _mutations(node: Node) -> list[Node]:
    out: list[Node] = []
    match node:
        case Rep(inner, lo, hi, lazy):
            if hi is not None and hi > lo:
                out.append(Rep(inner, lo, None, lazy))
            if hi is not None and lo == hi and lo > 1:
                out += [Rep(inner, lo - 1, hi - 1, lazy), Rep(inner, 1, None, lazy)]
            if (lo, hi) == (1, None):
                out.append(Rep(inner, 0, None, lazy))
            if (lo, hi) == (0, 1):
                out.append(inner)
        case Cls():
            if node in BROADER:
                out.append(BROADER[node])
            out.append(AnyChar())
        case Lit(text) if len(text) > 1:
            out.append(Lit(text[:-1]))
        case Anchor("start" | "end" | "word"):
            out.append(Lit(""))
    return out


def _replace(node: Node, target: int, new: Node, counter: list[int]) -> Node:
    """``node`` with its ``target``-th subnode (in walk order) replaced by ``new``."""
    index = counter[0]
    counter[0] += 1
    if index == target:
        return new
    match node:
        case Seq(parts):
            return seq(*(_replace(p, target, new, counter) for p in parts))
        case Alt(options):
            return Alt(tuple(_replace(o, target, new, counter) for o in options))
        case Rep() | Group():
            return replace(node, node=_replace(node.node, target, new, counter))
    return node


def fix_task(item: Item, r: random.Random) -> dict | None:
    dialect = r.choice(("python", "python", "grep -E"))
    whole = item.kind == "whole"
    mode = "fullmatch" if whole else "search"
    tests = tests_for(item.tree, mode, r)
    if tests is None:
        return None
    good, bad = tests
    nodes = list(walk(item.tree))
    choices = [(i, m) for i, n in enumerate(nodes) for m in _mutations(n)]
    if not choices:
        return None
    i, mutation = r.choice(choices)
    wrong = _replace(item.tree, i, mutation, [0])
    if risky(wrong) or wrong == item.tree:
        return None
    right_test, wrong_test = sample.matcher(to_python(item.tree), mode), sample.matcher(to_python(wrong), mode)
    pool = good + bad + sample.positives(wrong, mode, r, 6)
    differ = [s for s in pool if bool(right_test(s)) != bool(wrong_test(s))]
    if not differ:
        return None
    s = differ[0]
    shown = seq(START, wrong, END) if dialect != "python" and whole else wrong
    answer_tree = seq(START, item.tree, END) if dialect != "python" and whole else item.tree
    shown_text, answer = render(shown, dialect), render(answer_tree, dialect)
    if shown_text is None or answer is None:
        return None
    feedback = (
        f"It does not match {quote(s)}, but it should."
        if right_test(s)
        else f"It matches {quote(s)}, but it should not."
    )
    use = (
        "Python regular expression for re.fullmatch"
        if dialect == "python" and whole
        else ("Python regular expression for re.search" if dialect == "python" else "grep -E regular expression")
    )
    goal = item.text if whole else f"the lines that {item.text}"
    prompt = (
        f"This {use} should match {goal}:\n{shown_text}\n{feedback} Write the corrected regular expression.\n{ONLY}"
    )
    if right_test(s):
        good = [*good, s] if s not in good else good
    else:
        bad = [*bad, s] if s not in bad else bad
    mode_name = mode if dialect == "python" else ("line" if whole else "contains")
    return row(item.source, "fix", dialect, mode_name, prompt, answer, match=good, no_match=bad)


# --- random regexes, described mechanically ----------------------------------------------------

PUNCT = "-_.:/#@+=,;"
SHORT_WORDS = ("id", "v", "x", "ab", "log", "key", "img", "tmp", "no", "ok", "user", "file", "test", "src")


def _atom(r: random.Random) -> Node:
    k = r.randrange(11)
    if k <= 5:
        return (DIGIT, LOWER, UPPER, LETTER, WORD, HEX)[k]
    if k == 6:
        return Lit(r.choice(PUNCT))
    if k == 7:
        return Lit(r.choice(SHORT_WORDS))
    if k == 8:
        chars = sorted(set(r.sample("abcxyz" + PUNCT + "0123", r.randint(2, 4))))
        return cls(*(ch(c) for c in chars))
    if k == 9:
        return cls(*(ch(c) for c in sorted(set(r.sample(PUNCT + " ", r.randint(1, 2))))), negate=True)
    return SPACE


def _quantified(node: Node, r: random.Random) -> Node:
    k = r.randrange(9)
    if k <= 1 or (isinstance(node, Lit) and len(node.text) > 1 and k < 6):
        return node
    if k == 2:
        n = r.randint(2, 5)
        return rep(node, n, n)
    if k == 3:
        n = r.randint(0, 3)
        return rep(node, n, n + r.randint(1, 3))
    if k == 4:
        return rep(node, 1, None)
    if k == 5:
        return rep(node, 0, None)
    if k == 6:
        return rep(node, 0, 1)
    return rep(node, r.randint(1, 3), None)


def random_tree(r: random.Random, depth: int = 0) -> Node:
    parts = []
    for _ in range(r.randint(2, 4)):
        k = r.random()
        if k < 0.12 and depth == 0:
            inner = random_tree(r, depth + 1)
            parts.append(rep(Group(inner, capture=False), *r.choice(((0, 1), (1, None), (2, 2), (1, 3)))))
        elif k < 0.22:
            parts.append(Group(alt(*(Lit(w) for w in sorted(r.sample(SHORT_WORDS, r.randint(2, 3))))), capture=False))
        else:
            parts.append(_quantified(_atom(r), r))
    return seq(*parts)


def random_item(r: random.Random) -> Item | None:
    tree = random_tree(r)
    if risky(tree) or size(tree) < 3:
        return None
    k = r.random()
    if k < 0.7:
        return Item(tree, describe(tree, r), "whole", "generated", natural=False)
    if k < 0.85:
        return Item(seq(START, tree), f"start with {describe(tree, r)}", "line", "generated", natural=False)
    return Item(seq(tree, END), f"end with {describe(tree, r)}", "line", "generated", natural=False)


def pattern_item(pattern: str, source: str, r: random.Random) -> Item | None:
    """A regex from a source (CPython's code, a test suite), as a "contains" item."""
    from .tree import from_python  # noqa: PLC0415 - next to its only use

    tree = from_python(pattern)
    if tree is None or risky(tree) or not 3 <= size(tree) <= 40:
        return None
    if all(isinstance(n, Lit | Seq) for n in walk(tree)):
        return None  # plain text, no regex in it
    return Item(tree, f"contain {describe(tree, r)}", "line", source, natural=False)


# --- sed substitutions ---------------------------------------------------------------------------


@dataclass
class Sub:
    tree: Node
    repl: list  # ("text", s) | ("group", n) | ("whole",)
    text: str  # what the command does: "swaps the first two words"
    inputs: list[str]
    glob: bool = False  # the g flag: every match in a line, not only the first


def sed_repl(parts: list, delim: str) -> str:
    out = []
    for part in parts:
        if part[0] == "text":
            out.append(re.sub(r"([\\&\n" + re.escape(delim) + "])", r"\\\1", part[1]))
        elif part[0] == "group":
            out.append(f"\\{part[1]}")
        else:
            out.append("&")
    return "".join(out)


def python_repl(parts: list) -> str:
    out = []
    for part in parts:
        if part[0] == "text":
            out.append(part[1].replace("\\", "\\\\"))
        elif part[0] == "group":
            out.append(f"\\g<{part[1]}>")
        else:
            out.append("\\g<0>")
    return "".join(out)


def _words(r: random.Random, n: int) -> str:
    pool = (
        "alpha",
        "beta",
        "gamma",
        "delta",
        "hello",
        "world",
        "one",
        "two",
        "red",
        "blue",
        "cat",
        "dog",
        "data",
        "file",
    )
    return " ".join(r.choice(pool) for _ in range(n))


def _mixed(r: random.Random) -> str:
    return "".join(r.choice("abc xyz 0123456789-.") for _ in range(r.randint(4, 14))).strip() or "a1"


def sub_family(r: random.Random) -> Sub:
    k = r.randrange(16)
    if k == 0:
        tree = seq(Group(rep(LOWER, 1, None)), Lit(" "), Group(rep(LOWER, 1, None)))
        inputs = [_words(r, r.randint(2, 4)) for _ in range(5)]
        return Sub(
            tree,
            [("group", 2), ("text", " "), ("group", 1)],
            "swaps the first two words of each line (lowercase words separated by a space)",
            inputs,
        )
    if k == 1:
        tree = seq(Group(rep(DIGIT, 4, 4)), Lit("-"), Group(rep(DIGIT, 2, 2)), Lit("-"), Group(rep(DIGIT, 2, 2)))
        inputs = [f"due {r.randint(2000, 2030)}-{r.randint(1, 12):02d}-{r.randint(1, 28):02d}" for _ in range(3)]
        inputs += [
            f"from {r.randint(2000, 2030)}-0{r.randint(1, 9)}-1{r.randint(0, 9)} "
            f"to {r.randint(2000, 2030)}-1{r.randint(0, 2)}-2{r.randint(0, 8)}",
            "no date here",
        ]
        return Sub(
            tree,
            [("group", 3), ("text", "."), ("group", 2), ("text", "."), ("group", 1)],
            "rewrites every date like 2026-11-25 as 25.11.2026",
            inputs,
            glob=True,
        )
    if k == 2:
        tree = seq(Group(rep(DIGIT, 2, 2)), Lit("/"), Group(rep(DIGIT, 2, 2)), Lit("/"), Group(rep(DIGIT, 4, 4)))
        inputs = [f"on {r.randint(1, 12):02d}/{r.randint(1, 28):02d}/{r.randint(2000, 2030)}" for _ in range(4)] + [
            "2026"
        ]
        return Sub(
            tree,
            [("group", 3), ("text", "-"), ("group", 1), ("text", "-"), ("group", 2)],
            "turns US dates like 11/25/2026 (month/day/year) into 2026-11-25",
            inputs,
            glob=True,
        )
    if k == 3:
        return Sub(DIGIT, [], "deletes every digit", [_mixed(r) for _ in range(5)], glob=True)
    if k == 4:
        inputs = [_words(r, 2) + " " * r.randint(0, 3) for _ in range(5)]
        return Sub(seq(rep(SPACE, 1, None), END), [], "removes the whitespace at the end of each line", inputs)
    if k == 5:
        inputs = [" " * r.randint(0, 6) + _words(r, 2) for _ in range(5)]
        return Sub(
            seq(START, rep(SPACE, 1, None)),
            [],
            "removes the indentation (whitespace at the start) of each line",
            inputs,
        )
    if k == 6:
        inputs = [
            f"x = {r.randint(1, 99)}  # {_words(r, 2)}",
            "# only a comment",
            "no comment",
            f"{_words(r, 1)} # a # b",
        ]
        return Sub(
            seq(Lit("#"), rep(AnyChar(), 0, None)),
            [],
            "deletes everything from the first # to the end of the line",
            inputs,
        )
    if k == 7:
        tags = ("b", "i", "p", "em", "div", "span")
        inputs = []
        for _ in range(4):
            t = r.choice(tags)
            inputs.append(f"<{t}>{_words(r, 2)}</{t}> {_words(r, 1)}")
        inputs.append("plain text")
        return Sub(
            seq(Lit("<"), rep(cls(ch(">"), negate=True), 0, None), Lit(">")),
            [],
            "removes all HTML tags",
            inputs,
            glob=True,
        )
    if k == 8:
        a, b = r.choice(((",", ";"), (";", ","), (" ", "_"), ("-", "_"), (":", "="), ("_", "-"), (".", ",")))
        inputs = [a.join(_words(r, 1) for _ in range(r.randint(1, 4))) for _ in range(5)]
        return Sub(
            Lit(a),
            [("text", b)],
            f"replaces every {CHAR_NAMES.get(a, (quote(a),))[0].split(' ', 1)[-1]} "
            f"with {CHAR_NAMES.get(b, (quote(b),))[0]}",
            inputs,
            glob=True,
        )
    if k == 9:
        inputs = [(" " * r.randint(1, 3)).join(_words(r, 1) for _ in range(3)) for _ in range(5)]
        return Sub(
            rep(Lit(" "), 2, None),
            [("text", " ")],
            "replaces runs of two or more spaces with a single space",
            inputs,
            glob=True,
        )
    if k == 10:
        a, b = r.choice(
            (("color", "colour"), ("center", "centre"), ("foo", "bar"), ("cat", "dog"), ("old", "new"), ("is", "was"))
        )
        inputs = [f"the {a} is {a}", f"{a}s and {a}", "no match", f"{a}"]
        return Sub(
            seq(BOUNDARY, Lit(a), BOUNDARY),
            [("text", b)],
            f"replaces the whole word {quote(a)} with {quote(b)} (not inside other words)",
            inputs,
            glob=True,
        )
    if k == 11:
        left, right = r.choice((("[", "]"), ("(", ")"), ('"', '"'), ("<", ">")))
        inputs = [f"{_words(r, 1)} {r.randint(0, 999)} {_words(r, 1)} {r.randint(0, 99)}" for _ in range(4)] + ["none"]
        return Sub(
            rep(DIGIT, 1, None),
            [("text", left), ("whole",), ("text", right)],
            f"puts {left} and {right} around every number",
            inputs,
            glob=True,
        )
    if k == 12:
        first = ("Jane", "John", "Ada", "Alan", "Grace", "Linus")
        last = ("Doe", "Smith", "Lovelace", "Turing", "Hopper", "Torvalds")
        name = seq(UPPER, rep(LOWER, 1, None))
        inputs = [f"{r.choice(last)}, {r.choice(first)}" for _ in range(4)] + ["nobody"]
        return Sub(
            seq(Group(name), Lit(", "), Group(name)),
            [("group", 2), ("text", " "), ("group", 1)],
            'turns "Doe, Jane" into "Jane Doe"',
            inputs,
        )
    if k == 13:
        a, b = r.choice((("txt", "md"), ("jpeg", "jpg"), ("htm", "html"), ("yml", "yaml")))
        inputs = [f"{_words(r, 1)}.{a}" for _ in range(3)] + [f"{a}.{b}", f"notes.{a}.bak"]
        return Sub(
            seq(Lit("." + a), END),
            [("text", "." + b)],
            f"changes the extension .{a} at the end of each line to .{b}",
            inputs,
        )
    if k == 14:
        prefix = r.choice(("> ", "# ", "    ", "- "))
        inputs = [_words(r, r.randint(1, 3)) for _ in range(4)]
        return Sub(START, [("text", prefix)], f"puts {quote(prefix)} in front of every line", inputs)
    tree = seq(
        START, rep(Cls((("cat", "digit"),), negate=True), 0, None), Group(rep(DIGIT, 1, None)), rep(AnyChar(), 0, None)
    )
    inputs = [f"{_words(r, 1)} {r.randint(0, 999)} {_words(r, 1)} {r.randint(0, 9)}" for _ in range(4)] + ["no number"]
    return Sub(
        tree,
        [("group", 1)],
        "keeps only the first number of each line (lines without a number stay as they are)",
        inputs,
    )


def sed_task(r: random.Random) -> dict | None:
    sub = sub_family(r)
    dialect = r.choice(("sed -E", "sed"))
    pattern = render(sub.tree, dialect)
    if pattern is None:
        return None
    rx = re.compile(to_python(sub.tree))
    py = python_repl(sub.repl)
    pairs = [[s, rx.sub(py, s, count=0 if sub.glob else 1)] for s in dict.fromkeys(sub.inputs)]
    changed = [p for p in pairs if p[0] != p[1]]
    if len(changed) < 2:
        return None
    delim = "/"
    texts = [p[1] for p in sub.repl if p[0] == "text"]
    if "/" in pattern or any("/" in t for t in texts):
        delim = "|" if "|" not in pattern and not any("|" in t for t in texts) else "/"
    body = pattern.replace(delim, "\\" + delim)
    answer = f"s{delim}{body}{delim}{sed_repl(sub.repl, delim)}{delim}{'g' if sub.glob else ''}"
    shown = changed[:2]
    examples = "\n".join(f"{quote(a)} becomes {quote(b)}" for a, b in shown)
    prompt = f"Write a {SED[dialect]} substitution that {sub.text}.\nFor example:\n{examples}\n{ONLY_SED}"
    return row("sed", "substitute", dialect, "substitute", prompt, answer, pairs=pairs)

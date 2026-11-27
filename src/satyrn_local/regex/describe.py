"""English for a regex tree: what a regex matches, in words, with some variety of wording.

The descriptions are mechanical ("two digits, then a dash"). The hand-written concepts in
tasks.py have natural ones ("a date like 2026-11-25"); both go into the dataset.
"""

from __future__ import annotations

import json
import random

from .tree import Alt, Anchor, AnyChar, Cls, Group, Lit, Node, Rep, Seq, members

_DIGITS = frozenset("0123456789")
_LOWER = frozenset("abcdefghijklmnopqrstuvwxyz")
_UPPER = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
EXACT = {  # whole classes with a name of their own: members -> (singular, plural)
    _DIGITS | frozenset("abcdefABCDEF"): ("a hexadecimal digit", "hexadecimal digits"),
    _DIGITS | frozenset("abcdef"): ("a lowercase hexadecimal digit", "lowercase hexadecimal digits"),
    _DIGITS | frozenset("ABCDEF"): ("an uppercase hexadecimal digit", "uppercase hexadecimal digits"),
}
PARTS = (  # named parts of a class, the largest first: members, singular, plural
    (_LOWER | _UPPER | _DIGITS | {"_"}, ("letter", "digit", "underscore"), ("letters", "digits", "underscores")),
    (_LOWER | _UPPER | _DIGITS, ("letter", "digit"), ("letters", "digits")),
    (_LOWER | _UPPER, ("letter",), ("letters",)),
    (_LOWER, ("lowercase letter",), ("lowercase letters",)),
    (_UPPER, ("uppercase letter",), ("uppercase letters",)),
    (_DIGITS, ("digit",), ("digits",)),
)
CHAR_NAMES = {
    " ": ("a space", "spaces"),
    ".": ("a dot", "dots"),
    "-": ("a dash", "dashes"),
    "_": ("an underscore", "underscores"),
    ",": ("a comma", "commas"),
    ":": ("a colon", "colons"),
    ";": ("a semicolon", "semicolons"),
    "/": ("a slash", "slashes"),
    "\\": ("a backslash", "backslashes"),
    '"': ("a double quote", "double quotes"),
    "'": ("a single quote", "single quotes"),
    "(": ("an opening parenthesis", "opening parentheses"),
    ")": ("a closing parenthesis", "closing parentheses"),
}
NUMBERS = ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten")


def quote(text: str) -> str:
    return json.dumps(text)


def join(items: list[str], word: str) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + f" {word} " + items[-1]


def number(n: int, r: random.Random) -> str:
    return NUMBERS[n] if n < len(NUMBERS) and r.random() < 0.6 else str(n)


def _runs(chars: list[str]) -> list[list[str]]:
    """Consecutive characters together: a, b, c, x -> [a, b, c], [x]."""
    runs: list[list[str]] = []
    for c in chars:
        if runs and ord(c) == ord(runs[-1][-1]) + 1 and c.isalnum() == runs[-1][-1].isalnum():
            runs[-1].append(c)
        else:
            runs.append([c])
    return runs


class Describer:
    def __init__(self, r: random.Random) -> None:
        self.r = r

    def pick(self, *options: str) -> str:
        return self.r.choice(options)

    # nouns: (singular, plural) for things that can be counted, None for the others
    def noun(self, node: Node) -> tuple[str, str] | None:
        match node:
            case AnyChar():
                return ("any character", "characters")
            case Lit(text) if len(text) == 1:
                return CHAR_NAMES.get(text, (quote(text), f"{quote(text)} characters"))
            case Cls():
                return self.class_noun(node)
            case Group(inner, _):
                return self.noun(inner)
        return None

    def class_noun(self, node: Cls) -> tuple[str, str]:
        """Named parts (letters, digits) first, then the other characters, ranges for long runs."""
        found = set(members(Cls(node.items)))
        if not node.negate and frozenset(found) in EXACT:
            return EXACT[frozenset(found)]
        singular: list[str] = []
        plural: list[str] = []
        if ("cat", "space") in node.items:
            found.discard(" ")
            singular.append("whitespace character")
            plural.append("whitespace characters")
        for part, one, many in PARTS:
            if part <= found:
                found -= part
                singular += one
                plural += many
        named = bool(singular)
        for run in _runs(sorted(found)):
            if len(run) >= 3 and all(c.isalnum() for c in run):
                text = f"{quote(run[0])} to {quote(run[-1])}"
                singular.append(text)
                plural.append(text)
            else:
                for c in run:
                    one, many = CHAR_NAMES.get(c, (quote(c), quote(c)))
                    singular.append(one.split(" ", 1)[1] if c in CHAR_NAMES else one)
                    plural.append(many)
        if node.negate:
            return f"any character except {join(plural, 'and')}", f"characters other than {join(plural, 'and')}"
        if named:
            first = singular[0]
            return f"{'an' if first[0] in 'aeiou' else 'a'} {join(singular, 'or')}", join(plural, "or")
        return f"one of {join(singular, 'or')}", f"characters from {join(singular, 'and')}"

    def count(self, lo: int, hi: int | None, singular: str, plural: str) -> str:
        r = self.r
        if (lo, hi) == (0, 1):
            if singular.startswith(("a ", "an ")):
                return self.pick(f"optionally {singular}", f"an optional {singular.split(' ', 1)[1]}")
            return f"optionally {singular}"
        if (lo, hi) == (1, None):
            return f"one or more {plural}"
        if (lo, hi) == (0, None):
            return self.pick(f"any number of {plural}", f"zero or more {plural}")
        if hi is None:
            return f"at least {number(lo, r)} {plural}"
        if lo == hi:
            if lo == 1:
                return singular
            return self.pick(f"{number(lo, r)} {plural}", f"exactly {number(lo, r)} {plural}")
        low, high = number(lo, r), number(hi, r)
        return self.pick(f"{low} to {high} {plural}", f"between {low} and {high} {plural}")

    def times(self, lo: int, hi: int | None) -> str:
        r = self.r
        if (lo, hi) == (1, None):
            return "one or more times"
        if (lo, hi) == (0, None):
            return self.pick("any number of times", "zero or more times")
        if hi is None:
            return f"at least {number(lo, r)} times"
        if lo == hi:
            return {1: "once", 2: "twice"}.get(lo, f"{number(lo, r)} times")
        if (lo, hi) == (1, 2):
            return "once or twice"
        return f"{number(lo, r)} to {number(hi, r)} times"

    def phrase(self, node: Node) -> str:
        noun = self.noun(node)
        if noun and not isinstance(node, Rep):
            return noun[0]
        match node:
            case Lit(text):
                return quote(text)
            case Rep(inner, lo, hi, _):
                inner_noun = self.noun(inner)
                if inner_noun:
                    return self.count(lo, hi, *inner_noun)
                text = self.phrase(inner)
                if isinstance(inner, Seq | Alt | Rep) or (
                    isinstance(inner, Group) and isinstance(inner.node, Seq | Alt | Rep)
                ):
                    text = f"({text})"
                if (lo, hi) == (0, 1):
                    return f"optionally {text}"
                return f"{text} {self.times(lo, hi)}"
            case Group(inner, _):
                return self.phrase(inner)
            case Alt(options):
                words = [self.phrase(o) for o in options]
                return self.pick("either ", "") + join(words, "or") if len(words) == 2 else join(words, "or")
            case Seq(parts):
                return self.sequence(list(parts))
            case Anchor("word"):
                return "a word boundary"
            case Anchor(kind):
                return f"the {kind}"
        raise TypeError(node)

    def sequence(self, parts: list[Node]) -> str:
        at_start = bool(parts) and parts[0] == Anchor("start")
        at_end = bool(parts) and parts[-1] == Anchor("end")
        parts = parts[1 if at_start else 0 : -1 if at_end else None]
        if not parts:
            return "an empty line" if at_start and at_end else "the start" if at_start else "the end"
        text = self.words(parts)
        if at_start and at_end:
            return f"nothing but {text}"
        if at_start:
            return f"{text} at the start"
        return f"{text} at the end" if at_end else text

    def words(self, parts: list[Node]) -> str:
        if len(parts) >= 3 and parts[0] == Anchor("word") and parts[-1] == Anchor("word"):
            inner = parts[1:-1]
            return f"{self.phrase(inner[0]) if len(inner) == 1 else self.words(inner)} as a whole word"
        words = [self.phrase(p) for p in parts]
        if len(words) == 1:
            text = words[0]
        else:
            style = self.r.randrange(3)
            if style == 0:
                text = ", then ".join(words)
            elif style == 1:
                text = join(words, "and")
            else:
                text = ", ".join(words[:-1]) + ", followed by " + words[-1]
        return text


def describe(node: Node, r: random.Random) -> str:
    return Describer(r).phrase(node)

"""Test strings for a regex tree: strings it matches, and near misses that it must not match.

Matching strings come from walking the tree (a class gives one of its characters, a repeat a
count within its limits). Near misses come from small edits of matching strings: one character
deleted, inserted, replaced, doubled or swapped. They teach more than random strings, because
they show where the borders of a regex are.
"""

from __future__ import annotations

import random
import re
from functools import cache

from .tree import UNIVERSE, Alt, Anchor, AnyChar, Cls, Group, Lit, Node, Rep, Seq, members, to_python

EXTRA = 3  # a repeat without limit gives at most this many more than its minimum
CONTEXT = "abcxyz XYZ 0123 .,;:-_"  # what surrounds a match in a "contains" task
EDIT_CHARS = "aZ09 .-_:/#x"  # inserted or replaced in near misses, besides neighbours


@cache
def _members(node: Cls) -> tuple[str, ...]:
    return tuple(sorted(members(node)))


def generate(node: Node, r: random.Random) -> str | None:
    match node:
        case Lit(text):
            return text
        case AnyChar():
            return r.choice(UNIVERSE)
        case Cls():
            chars = _members(node)
            return r.choice(chars) if chars else None
        case Seq(parts):
            out = [generate(p, r) for p in parts]
            return None if None in out else "".join(out)
        case Alt(options):
            return generate(r.choice(options), r)
        case Rep(inner, lo, hi, _):
            top = lo + EXTRA if hi is None else hi
            n = r.randint(lo, min(top, lo + EXTRA))
            out = [generate(inner, r) for _ in range(n)]
            return None if None in out else "".join(out)
        case Group(inner, _):
            return generate(inner, r)
        case Anchor():
            return ""
    raise TypeError(node)


def matcher(pattern: str, mode: str):  # noqa: ANN201 - a match function
    rx = re.compile(pattern)
    return rx.fullmatch if mode == "fullmatch" else rx.search


def positives(node: Node, mode: str, r: random.Random, n: int) -> list[str]:
    test = matcher(to_python(node), mode)
    found: list[str] = []
    for _ in range(n * 12):
        s = generate(node, r)
        if s is None:
            break
        if mode == "search":
            s = "".join(r.sample(CONTEXT, r.randint(0, 4))) + s + "".join(r.sample(CONTEXT, r.randint(0, 4)))
        if s not in found and test(s):
            found.append(s)
            if len(found) == n:
                break
    return found


def edit(s: str, r: random.Random) -> str:
    pool = EDIT_CHARS + s
    i = r.randrange(len(s) + 1) if s else 0
    kind = r.randrange(6) if s else 1
    if kind == 0:
        return s[:i] + s[i + 1 :]  # delete
    if kind == 1:
        return s[:i] + r.choice(pool) + s[i:]  # insert
    if kind == 2:
        return s[:i] + r.choice(pool) + s[i + 1 :]  # replace
    if kind == 3:
        return s[:i] + s[i : i + 1] * 2 + s[i + 1 :]  # double
    if kind == 4 and len(s) > 1:
        i = min(i, len(s) - 2)
        return s[:i] + s[i + 1] + s[i] + s[i + 2 :]  # swap
    return s[:-1] if r.random() < 0.5 else s + r.choice(pool)


def negatives(node: Node, mode: str, good: list[str], r: random.Random, n: int) -> list[str]:
    test = matcher(to_python(node), mode)
    found: list[str] = []
    for _ in range(n * 15):
        s = r.choice(good)
        for _ in range(r.choice((1, 1, 1, 2))):
            s = edit(s, r)
        if s not in found and s not in good and not test(s):
            found.append(s)
            if len(found) == n:
                break
    return found

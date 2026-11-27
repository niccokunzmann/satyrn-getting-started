"""A small regex tree, written as Python's re, grep -E (extended), grep and sed (basic) regexes.

One tree is the reference answer of a task. From it come the answers in every dialect, an
English description and the test strings (see sample.py). Python regexes from other sources are
read into the same tree with Python's own parser (``from_python``), so they get the same
treatment; constructs that grep cannot express (lookarounds, lazy repeats, backreferences) are
not part of the tree, or yield ``None`` for the POSIX dialects.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from re import _constants as C  # noqa: N812 - the names of Python's own regex parser
from re import _parser as P  # noqa: N812

UNIVERSE = tuple(chr(c) for c in range(0x20, 0x7F))  # printable ASCII; no newline: one test string per line


@dataclass(frozen=True)
class Lit:
    text: str


@dataclass(frozen=True)
class Cls:
    """A character class. Items: ("char", c), ("range", a, b) or ("cat", "digit" | "word" | "space")."""

    items: tuple
    negate: bool = False


@dataclass(frozen=True)
class AnyChar:
    pass


@dataclass(frozen=True)
class Seq:
    parts: tuple


@dataclass(frozen=True)
class Alt:
    options: tuple


@dataclass(frozen=True)
class Rep:
    node: object
    lo: int
    hi: int | None  # None: no upper limit
    lazy: bool = False


@dataclass(frozen=True)
class Group:
    node: object
    capture: bool = True


@dataclass(frozen=True)
class Anchor:
    kind: str  # "start", "end" or "word" (a word boundary)


Node = Lit | Cls | AnyChar | Seq | Alt | Rep | Group | Anchor


# --- building ---------------------------------------------------------------------------------


def seq(*parts: Node) -> Node:
    """A sequence, flattened, with neighbouring literals joined."""
    flat: list[Node] = []
    for part in parts:
        for p in part.parts if isinstance(part, Seq) else (part,):
            if isinstance(p, Lit) and not p.text:
                continue
            if isinstance(p, Lit) and flat and isinstance(flat[-1], Lit):
                flat[-1] = Lit(flat[-1].text + p.text)
            else:
                flat.append(p)
    return flat[0] if len(flat) == 1 else Seq(tuple(flat))


def alt(*options: Node) -> Alt:
    return Alt(tuple(options))


def rep(node: Node, lo: int, hi: int | None) -> Rep:
    return Rep(node, lo, hi)


def opt(node: Node) -> Rep:
    return Rep(node, 0, 1)


def cls(*items: tuple, negate: bool = False) -> Cls:
    return Cls(tuple(items), negate)


def rng(a: str, b: str) -> tuple:
    return ("range", a, b)


def ch(c: str) -> tuple:
    return ("char", c)


DIGIT = cls(("cat", "digit"))
WORD = cls(("cat", "word"))
SPACE = cls(("cat", "space"))
LOWER = cls(rng("a", "z"))
UPPER = cls(rng("A", "Z"))
LETTER = cls(rng("a", "z"), rng("A", "Z"))
ALNUM = cls(rng("a", "z"), rng("A", "Z"), rng("0", "9"))
HEX = cls(rng("0", "9"), rng("a", "f"), rng("A", "F"))
LOWER_HEX = cls(rng("0", "9"), rng("a", "f"))


# --- Python -----------------------------------------------------------------------------------

PY_SPECIAL = frozenset(".^$*+?{}[]\\|()")
PY_CLASS_SPECIAL = frozenset("\\]^-[")
PY_CATS = {"digit": r"\d", "word": r"\w", "space": r"\s"}
PY_NOT_CATS = {"digit": r"\D", "word": r"\W", "space": r"\S"}


def quantifier(lo: int, hi: int | None, *, basic: bool = False) -> str:
    b = "\\" if basic else ""
    if (lo, hi) == (0, None):
        return "*"
    if (lo, hi) == (1, None):
        return b + "+"
    if (lo, hi) == (0, 1):
        return b + "?"
    if hi is None:
        body = f"{lo},"
    elif lo == hi:
        body = f"{lo}"
    else:
        body = f"{lo},{hi}"
    return f"{b}{{{body}{b}}}"


def _py_class_item(item: tuple) -> str:
    match item:
        case ("char", c):
            return "\\" + c if c in PY_CLASS_SPECIAL else c
        case ("range", a, b):
            return f"{_py_class_item(ch(a))}-{_py_class_item(ch(b))}"
        case ("cat", name):
            return PY_CATS[name]
    raise ValueError(item)


def _is_atom(node: Node) -> bool:
    return isinstance(node, Cls | AnyChar | Group) or (isinstance(node, Lit) and len(node.text) == 1)


def to_python(node: Node) -> str:
    match node:
        case Lit(text):
            return "".join("\\" + c if c in PY_SPECIAL else c for c in text)
        case AnyChar():
            return "."
        case Cls(items, negate):
            if len(items) == 1 and items[0][0] == "cat":
                return (PY_NOT_CATS if negate else PY_CATS)[items[0][1]]
            return "[" + ("^" if negate else "") + "".join(_py_class_item(i) for i in items) + "]"
        case Seq(parts):
            return "".join(f"(?:{to_python(p)})" if isinstance(p, Alt) else to_python(p) for p in parts)
        case Alt(options):
            return "|".join(to_python(o) for o in options)
        case Rep(inner, lo, hi, lazy):
            atom = to_python(inner) if _is_atom(inner) else f"(?:{to_python(inner)})"
            return atom + quantifier(lo, hi) + ("?" if lazy else "")
        case Group(inner, capture):
            return ("(" if capture else "(?:") + to_python(inner) + ")"
        case Anchor(kind):
            return {"start": "^", "end": "$", "word": r"\b"}[kind]
    raise TypeError(node)


# --- POSIX: grep -E and sed -E (extended), grep and sed (basic, with GNU's \+ \? \|) ------------

ERE_SPECIAL = frozenset(".[]()*+?{}|^$\\")
BRE_SPECIAL = frozenset(".[]*^$\\")
POSIX_CATS = {"digit": "0-9", "word": "[:alnum:]_", "space": "[:space:]"}


def _posix_class(node: Cls) -> str | None:
    chars, rest = [], []
    for item in node.items:
        match item:
            case ("char", c):
                chars.append(c)
            case ("range", a, b):
                if "]" in (a, b) or a == "^" or "-" in (a, b) or "[" in (a, b):
                    return None
                rest.append(f"{a}-{b}")
            case ("cat", name):
                rest.append(POSIX_CATS[name])
    # "]" must come first, "^" anywhere but first, "-" last; "[" last before them, so that it
    # cannot start a [:name:] by accident.
    body = ("]" if "]" in chars else "") + "".join(rest) + "".join(c for c in chars if c not in "]^-[")
    if "[" in chars:
        body += "["
    if "^" in chars:
        if body or node.negate:
            body += "^"
        elif "-" in chars:
            return "[-^]"
        else:
            return None
    if "-" in chars:
        body += "-"
    return "[" + ("^" if node.negate else "") + body + "]"


def to_posix(node: Node, *, extended: bool) -> str | None:
    """The regex for grep/sed (``extended``: grep -E, sed -E), or None if POSIX cannot express it."""
    open_, close, bar = ("(", ")", "|") if extended else ("\\(", "\\)", "\\|")
    special = ERE_SPECIAL if extended else BRE_SPECIAL

    def go(n: Node) -> str | None:
        match n:
            case Lit(text):
                return "".join("\\" + c if c in special else c for c in text)
            case AnyChar():
                return "."
            case Cls(items, negate):
                if len(items) == 1 and items[0][0] == "char" and not negate:
                    return go(Lit(items[0][1]))
                if len(items) == 1 and items[0][0] == "cat":
                    return "[" + ("^" if negate else "") + POSIX_CATS[items[0][1]] + "]"
                return _posix_class(n)
            case Seq(parts):
                out = []
                for p in parts:
                    s = go(p)
                    if s is None:
                        return None
                    out.append(f"{open_}{s}{close}" if isinstance(p, Alt) else s)
                return "".join(out)
            case Alt(options):
                out = [go(o) for o in options]
                return None if None in out else bar.join(out)
            case Rep(inner, lo, hi, lazy):
                s = go(inner)
                if s is None or lazy:
                    return None
                atom = s if _is_atom(inner) else f"{open_}{s}{close}"
                return atom + quantifier(lo, hi, basic=not extended)
            case Group(inner, _):
                s = go(inner)
                return None if s is None else f"{open_}{s}{close}"
            case Anchor(kind):
                return {"start": "^", "end": "$", "word": r"\b"}[kind]
        raise TypeError(n)

    return go(node)


def render(node: Node, dialect: str) -> str | None:
    if dialect == "python":
        return to_python(node)
    return to_posix(node, extended=dialect in {"grep -E", "sed -E"})


# --- reading Python regexes -------------------------------------------------------------------


def from_python(pattern: str) -> Node | None:
    """The tree of a Python regex, or None if it uses something outside the tree (or flags)."""
    try:
        parsed = P.parse(pattern)
    except re.error, RecursionError, OverflowError, ValueError:
        return None
    if parsed.state.flags & ~C.SRE_FLAG_UNICODE:
        return None  # inline flags such as (?i) or (?x)
    return _from_items(list(parsed))


def _char(code: int) -> str | None:
    c = chr(code)
    return c if c in UNIVERSE else None


def _from_items(items: list) -> Node | None:
    parts = []
    for op, av in items:
        node = _from_item(str(op), av)
        if node is None:
            return None
        parts.append(node)
    return seq(*parts) if parts else Lit("")


def _class_items(av: list) -> tuple[tuple, bool] | None:
    negate, out = False, []
    for op, value in av:
        name = str(op)
        if name == "NEGATE":
            negate = True
        elif name == "LITERAL":
            c = _char(value)
            if c is None:
                return None
            out.append(ch(c))
        elif name == "RANGE":
            a, b = _char(value[0]), _char(value[1])
            if a is None or b is None:
                return None
            out.append(rng(a, b))
        elif name == "CATEGORY" and str(value) in CATEGORIES:
            out.append(("cat", CATEGORIES[str(value)]))
        else:
            return None
    return tuple(out), negate


CATEGORIES = {"CATEGORY_DIGIT": "digit", "CATEGORY_WORD": "word", "CATEGORY_SPACE": "space"}
NOT_CATEGORIES = {"CATEGORY_NOT_DIGIT": "digit", "CATEGORY_NOT_WORD": "word", "CATEGORY_NOT_SPACE": "space"}
ANCHORS = {"AT_BEGINNING": "start", "AT_BEGINNING_STRING": "start", "AT_END": "end", "AT_END_STRING": "end"}


def _from_item(name: str, av: object) -> Node | None:
    if name == "LITERAL":
        c = _char(av)
        return None if c is None else Lit(c)
    if name == "NOT_LITERAL":
        c = _char(av)
        return None if c is None else Cls((ch(c),), negate=True)
    if name == "ANY":
        return AnyChar()
    if name == "IN":
        items = _class_items(av)
        return None if items is None else Cls(*items)
    if name == "CATEGORY":
        if str(av) in CATEGORIES:
            return Cls((("cat", CATEGORIES[str(av)]),))
        if str(av) in NOT_CATEGORIES:
            return Cls((("cat", NOT_CATEGORIES[str(av)]),), negate=True)
        return None
    if name == "BRANCH":
        options = [_from_items(list(b)) for b in av[1]]
        return None if None in options else Alt(tuple(options))
    if name == "SUBPATTERN":
        group, add_flags, del_flags, inner = av
        if add_flags or del_flags:
            return None
        node = _from_items(list(inner))
        return None if node is None else Group(node, capture=group is not None)
    if name in {"MAX_REPEAT", "MIN_REPEAT"}:
        lo, hi, inner = av
        node = _from_items(list(inner))
        if node is None:
            return None
        return Rep(node, lo, None if hi == C.MAXREPEAT else hi, lazy=name == "MIN_REPEAT")
    if name == "AT":
        if str(av) in ANCHORS:
            return Anchor(ANCHORS[str(av)])
        return Anchor("word") if str(av) == "AT_BOUNDARY" else None
    return None  # backreferences, lookarounds, possessive repeats, atomic groups


# --- properties ---------------------------------------------------------------------------------


def walk(node: Node):  # noqa: ANN201 - a generator of nodes
    yield node
    match node:
        case Seq(parts) | Alt(parts):
            for p in parts:
                yield from walk(p)
        case Rep() | Group():
            yield from walk(node.node)


def risky(node: Node) -> bool:
    """A repeat without limit inside another one: the shape that can backtrack for ages ((a+)+b)."""
    for n in walk(node):
        if isinstance(n, Rep) and n.hi is None and any(isinstance(m, Rep) and m.hi is None for m in walk(n.node)):
            return True
    return False


def size(node: Node) -> int:
    return sum(1 for _ in walk(node))


def members(node: Cls) -> frozenset[str]:
    """The characters of UNIVERSE that a class matches."""
    rx = re.compile(to_python(node))
    return frozenset(c for c in UNIVERSE if rx.fullmatch(c))


def simplify(node: Node) -> Node:
    """Without groups (the rendering adds those it needs), alternatives of characters as one class.

    For sources whose groups only structure the regex: ``(([a-z]){7,})(dog)`` becomes
    ``[a-z]{7,}dog``, ``([0-9]|[a-z])`` becomes ``[0-9a-z]``. Not for sed, whose groups are used.
    """
    match node:
        case Group(inner, _):
            return simplify(inner)
        case Seq(parts):
            out: list[Node] = []
            for p in (simplify(p) for p in parts):
                if not (out and p == out[-1] == Rep(AnyChar(), 0, None)):  # .*.* is .*
                    out.append(p)
            return seq(*out)
        case Rep(inner, lo, hi, lazy):
            return Rep(simplify(inner), lo, hi, lazy)
        case Alt(options):
            flat: list[Node] = []
            for o in (simplify(o) for o in options):
                flat.extend(o.options if isinstance(o, Alt) else [o])
            chars = all(
                (isinstance(o, Cls | AnyChar) and not getattr(o, "negate", False))
                or (isinstance(o, Lit) and len(o.text) == 1)
                for o in flat
            )
            if chars and any(isinstance(o, AnyChar) for o in flat):
                return AnyChar()  # . covers every character
            if chars:
                items: list[tuple] = []
                for o in flat:
                    for item in o.items if isinstance(o, Cls) else (("char", o.text),):
                        if item not in items:
                            items.append(item)
                wide = Cls(tuple(i for i in items if i[0] != "char"))
                covered = members(wide) if wide.items else frozenset()
                return Cls(tuple(i for i in items if i[0] != "char" or i[1] not in covered))
            return Alt(tuple(flat))
    return node

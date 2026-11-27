"""Hand-written regex concepts with natural descriptions: dates, versions, identifiers, log lines.

Each concept is a function of a random generator that returns ``(tree, description, kind)``:

- kind "whole": the description says what a whole string (or line) is, for example
  "a date like 2026-11-25";
- kind "line": the description says what a line does, for example "start with TODO"; the
  tree carries its anchors.

The parameters (separators, word lists, counts) vary, so one concept gives many tasks.
"""

from __future__ import annotations

import random
from collections.abc import Callable

from .describe import CHAR_NAMES, join, number, quote
from .sample import generate
from .tree import (
    DIGIT,
    HEX,
    LETTER,
    LOWER,
    LOWER_HEX,
    SPACE,
    UPPER,
    WORD,
    Anchor,
    AnyChar,
    Group,
    Lit,
    Node,
    alt,
    ch,
    cls,
    opt,
    rep,
    rng,
    seq,
)

Concept = Callable[[random.Random], tuple[Node, str, str]]
CONCEPTS: dict[str, Concept] = {}

START, END, BOUNDARY = Anchor("start"), Anchor("end"), Anchor("word")
WORDS = {
    "colors": ("red", "green", "blue", "yellow", "black", "white", "orange", "purple"),
    "animals": ("cat", "dog", "bird", "fish", "horse", "mouse", "snake", "tiger"),
    "levels": ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"),
    "methods": ("GET", "POST", "PUT", "DELETE", "PATCH", "HEAD"),
    "answers": ("yes", "no", "y", "n", "true", "false", "on", "off"),
    "fruits": ("apple", "banana", "cherry", "grape", "lemon", "mango", "pear", "plum"),
}
WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
EXTENSIONS = ("py", "txt", "csv", "json", "md", "log", "png", "jpg", "toml", "html", "c", "rs")
KEYWORDS = ("TODO", "FIXME", "NOTE", "XXX", "import", "def", "class", "return", "error", "warning")


def concept(fn: Concept) -> Concept:
    CONCEPTS[fn.__name__] = fn
    return fn


def d(n: int, m: int | None = -1) -> Node:
    return rep(DIGIT, n, n if m == -1 else m)


def lit(text: str) -> Lit:
    return Lit(text)


def char_name(c: str) -> str:
    return CHAR_NAMES[c][0] if c in CHAR_NAMES else quote(c)


def char_plural(c: str) -> str:
    return CHAR_NAMES[c][1] if c in CHAR_NAMES else f"{quote(c)} characters"


def like(tree: Node, r: random.Random) -> str:
    return generate(tree, r) or ""


def words(group: tuple[str, ...], r: random.Random, low: int = 2, high: int = 4) -> list[str]:
    return sorted(r.sample(group, r.randint(low, min(high, len(group)))))


def word_alt(chosen: list[str]) -> Node:
    return alt(*(lit(w) for w in chosen))


# --- numbers --------------------------------------------------------------------------------


@concept
def integer(r: random.Random) -> tuple[Node, str, str]:
    k = r.randrange(5)
    if k == 0:
        return seq(opt(lit("-")), rep(DIGIT, 1, None)), "a whole number, optionally starting with a minus sign", "whole"
    if k == 1:
        return seq(opt(cls(ch("+"), ch("-"))), rep(DIGIT, 1, None)), "an integer with an optional + or - sign", "whole"
    if k == 2:
        tree = alt(seq(cls(rng("1", "9")), rep(DIGIT, 0, None)), lit("0"))
        return tree, "a whole number without leading zeros (0 itself is allowed)", "whole"
    if k == 3:
        tree = seq(d(1, 3), rep(Group(seq(lit(","), d(3)), capture=False), 0, None))
        return tree, "a number with commas as thousands separators, like 1,234,567", "whole"
    n, m = sorted(r.sample(range(1, 9), 2))
    return d(n, m), f"a number with {number(n, r)} to {number(m, r)} digits", "whole"


@concept
def decimal(r: random.Random) -> tuple[Node, str, str]:
    k = r.randrange(6)
    if k == 0:
        return (
            seq(opt(lit("-")), rep(DIGIT, 1, None), lit("."), rep(DIGIT, 1, None)),
            ("a decimal number with a dot, like 3.14 or -0.5"),
            "whole",
        )
    if k == 1:
        return (
            seq(rep(DIGIT, 1, None), opt(Group(seq(lit("."), rep(DIGIT, 1, None))))),
            ("a number with an optional decimal part, like 42 or 42.5"),
            "whole",
        )
    if k == 2:
        return seq(rep(DIGIT, 1, None), lit("."), d(2)), "a price with exactly two decimals, like 19.99", "whole"
    if k == 3:
        cur = r.choice("$€£")
        tree = seq(lit(cur), rep(DIGIT, 1, None), opt(Group(seq(lit("."), d(2)))))
        return tree, f"an amount in {cur}, like {cur}5 or {cur}12.50", "whole"
    if k == 4:
        tree = seq(
            opt(cls(ch("+"), ch("-"))),
            rep(DIGIT, 1, None),
            opt(Group(seq(lit("."), rep(DIGIT, 1, None)))),
            cls(ch("e"), ch("E")),
            opt(cls(ch("+"), ch("-"))),
            rep(DIGIT, 1, None),
        )
        return tree, "a number in scientific notation, like 6.02e23 or -1E-9", "whole"
    tree = alt(lit("100"), seq(opt(cls(rng("1", "9"))), DIGIT))
    return seq(Group(tree, capture=False), lit("%")), "a percentage from 0% to 100% (whole numbers)", "whole"


@concept
def number_base(r: random.Random) -> tuple[Node, str, str]:
    k = r.randrange(5)
    if k == 0:
        return rep(cls(ch("0"), ch("1")), 1, None), "a binary number: only the digits 0 and 1", "whole"
    if k == 1:
        return seq(lit("0b"), rep(cls(ch("0"), ch("1")), 1, None)), "a binary number with the prefix 0b", "whole"
    if k == 2:
        return seq(lit("0x"), rep(HEX, 1, None)), "a hexadecimal number with the prefix 0x, like 0x1F", "whole"
    if k == 3:
        return seq(lit("0o"), rep(cls(rng("0", "7")), 1, None)), "an octal number with the prefix 0o", "whole"
    n = r.choice((7, 8, 12, 40, 64))
    what = {7: "a short git commit hash", 40: "a full git commit hash", 64: "a SHA-256 checksum"}
    tree = rep(LOWER_HEX, n, n) if n != 7 else rep(LOWER_HEX, 7, 40)
    text = what.get(n, f"{number(n, r)} lowercase hexadecimal digits")
    if n == 7:
        text = "a git commit hash: 7 to 40 lowercase hexadecimal digits"
    elif n in what:
        text += f" ({n} lowercase hexadecimal digits)"
    return tree, text, "whole"


# --- dates and times ------------------------------------------------------------------------


@concept
def date(r: random.Random) -> tuple[Node, str, str]:
    sep = r.choice("-/.")
    k = r.randrange(4)
    if k == 0:
        tree = seq(d(4), lit(sep), d(2), lit(sep), d(2))
        if sep == "-":
            return tree, "a date like 2026-11-25: four digits, a dash, two digits, a dash, two digits", "whole"
        return tree, f"a date like 2026{sep}11{sep}25 (year, month and day, separated by {char_plural(sep)})", "whole"
    if k == 1:
        tree = seq(d(2), lit(sep), d(2), lit(sep), d(4))
        return tree, f"a date in the form DD{sep}MM{sep}YYYY, like 25{sep}11{sep}2026", "whole"
    if k == 2:
        month = alt(seq(lit("0"), cls(rng("1", "9"))), seq(lit("1"), cls(rng("0", "2"))))
        day = alt(
            seq(lit("0"), cls(rng("1", "9"))), seq(cls(ch("1"), ch("2")), DIGIT), seq(lit("3"), cls(ch("0"), ch("1")))
        )
        tree = seq(d(4), lit("-"), Group(month), lit("-"), Group(day))
        return tree, "an ISO date YYYY-MM-DD whose month is 01 to 12 and whose day is 01 to 31", "whole"
    tree = seq(Group(alt(*(lit(m) for m in MONTHS)), capture=False), lit(" "), d(1, 2), lit(", "), d(4))
    return tree, "a date like Nov 25, 2026: a three-letter month, the day and the year", "whole"


@concept
def time(r: random.Random) -> tuple[Node, str, str]:
    k = r.randrange(4)
    hours = alt(seq(cls(ch("0"), ch("1")), DIGIT), seq(lit("2"), cls(rng("0", "3"))))
    minutes = seq(cls(rng("0", "5")), DIGIT)
    if k == 0:
        return (
            seq(Group(hours, capture=False), lit(":"), minutes),
            ("a time in 24-hour format HH:MM, hours 00 to 23 and minutes 00 to 59"),
            "whole",
        )
    if k == 1:
        return seq(d(2), lit(":"), d(2)), "a time like 09:30: two digits, a colon and two digits", "whole"
    if k == 2:
        tree = seq(Group(hours, capture=False), lit(":"), minutes, lit(":"), minutes)
        return tree, "a time HH:MM:SS in 24-hour format, like 23:59:07", "whole"
    hour12 = alt(seq(opt(lit("0")), cls(rng("1", "9"))), seq(lit("1"), cls(rng("0", "2"))))
    tree = seq(
        Group(hour12, capture=False), lit(":"), minutes, opt(lit(" ")), Group(alt(lit("AM"), lit("PM")), capture=False)
    )
    return tree, "a time in 12-hour format with AM or PM, like 9:05 PM or 11:30AM", "whole"


@concept
def datetime(r: random.Random) -> tuple[Node, str, str]:
    sep = r.choice(("T", " "))
    tree = seq(d(4), lit("-"), d(2), lit("-"), d(2), lit(sep), d(2), lit(":"), d(2), lit(":"), d(2))
    if r.random() < 0.5:
        tree = seq(tree, opt(lit("Z")))
        return tree, f"an ISO timestamp like 2026-11-25{sep}14:30:00, optionally ending in Z", "whole"
    return tree, f"a date and time like 2026-11-25{sep}14:30:00", "whole"


@concept
def weekday(r: random.Random) -> tuple[Node, str, str]:
    if r.random() < 0.5:
        return alt(*(lit(w) for w in WEEKDAYS)), "a weekday abbreviation from Mon to Sun", "whole"
    return alt(*(lit(m) for m in MONTHS)), "a three-letter month abbreviation from Jan to Dec", "whole"


# --- codes and identifiers ------------------------------------------------------------------


@concept
def code(r: random.Random) -> tuple[Node, str, str]:
    letters, digits = r.randint(1, 4), r.randint(2, 6)
    case = r.choice(("uppercase", "lowercase"))
    sep = r.choice(("-", "", " ", "/", "_"))
    tree = seq(rep(UPPER if case == "uppercase" else LOWER, letters, letters), lit(sep), d(digits))
    parts = [f"{number(letters, r)} {case} letter{'s' if letters > 1 else ''}"]
    if sep:
        parts.append(char_name(sep))
    parts.append(f"{number(digits, r)} digits")
    return tree, f"a code like {like(tree, r)}: {join(parts, 'and')}", "whole"


@concept
def identifier(r: random.Random) -> tuple[Node, str, str]:
    k = r.randrange(7)
    if k == 0:
        return (
            seq(cls(rng("A", "Z"), rng("a", "z"), ch("_")), rep(WORD, 0, None)),
            ("a Python identifier: a letter or underscore, then letters, digits or underscores"),
            "whole",
        )
    if k == 1:
        return (
            seq(rep(LOWER, 1, None), rep(Group(seq(lit("_"), rep(LOWER, 1, None)), capture=False), 0, None)),
            ("a snake_case name: lowercase words joined by single underscores"),
            "whole",
        )
    if k == 2:
        return (
            rep(Group(seq(UPPER, rep(LOWER, 1, None)), capture=False), 1, None),
            ("a CamelCase name like HttpServer: capitalized words without separators"),
            "whole",
        )
    if k == 3:
        return (
            seq(rep(UPPER, 1, None), rep(Group(seq(lit("_"), rep(UPPER, 1, None)), capture=False), 0, None)),
            ("a constant name like MAX_SIZE: uppercase words joined by underscores"),
            "whole",
        )
    if k == 4:
        return (
            seq(rep(LOWER, 1, None), rep(Group(seq(lit("-"), rep(LOWER, 1, None)), capture=False), 0, None)),
            ("a kebab-case name like my-project: lowercase words joined by dashes"),
            "whole",
        )
    if k == 5:
        return (
            seq(rep(LOWER, 1, None), rep(Group(seq(UPPER, rep(LOWER, 1, None)), capture=False), 0, None)),
            ("a camelCase name like parseHttpHeader"),
            "whole",
        )
    lo, hi = r.choice(((3, 16), (2, 20), (4, 12), (3, 30)))
    tree = seq(LETTER, rep(cls(rng("a", "z"), rng("A", "Z"), rng("0", "9"), ch("_")), lo - 1, hi - 1))
    return tree, f"a username of {lo} to {hi} letters, digits or underscores that starts with a letter", "whole"


@concept
def word(r: random.Random) -> tuple[Node, str, str]:
    k = r.randrange(5)
    if k == 0:
        return (
            seq(UPPER, rep(LOWER, 0, None)),
            "a word that starts with a capital letter followed by lowercase letters",
            "whole",
        )
    if k == 1:
        return rep(LOWER, 1, None), "one or more lowercase letters a to z, nothing else", "whole"
    if k == 2:
        n = r.randint(2, 8)
        return rep(LETTER, n, n), f"a word of exactly {number(n, r)} letters", "whole"
    if k == 3:
        n, m = sorted(r.sample(range(1, 12), 2))
        return rep(LETTER, n, m), f"a word of {number(n, r)} to {number(m, r)} letters", "whole"
    return rep(UPPER, 1, None), "a word in capital letters only", "whole"


@concept
def word_choice(r: random.Random) -> tuple[Node, str, str]:
    group = r.choice(sorted(WORDS))
    chosen = words(WORDS[group], r)
    k = r.randrange(3)
    if k == 0:
        return word_alt(chosen), f"exactly one of the words {join([quote(w) for w in chosen], 'or')}", "whole"
    if k == 1:
        return (
            seq(BOUNDARY, Group(word_alt(chosen), capture=False), BOUNDARY),
            (f"contain one of the words {join([quote(w) for w in chosen], 'or')} as a whole word"),
            "line",
        )
    return (
        seq(START, Group(word_alt(chosen), capture=False)),
        (f"start with {join([quote(w) for w in chosen], 'or')}"),
        "line",
    )


@concept
def repeated(r: random.Random) -> tuple[Node, str, str]:
    c = r.choice("xyzab0-=*.#")
    k = r.randrange(3)
    if k == 0:
        n = r.randint(2, 5)
        return rep(lit(c), n, None), f"{number(n, r)} or more {quote(c)} characters", "whole"
    if k == 1:
        n = r.randint(2, 6)
        return rep(lit(c), n, n), f"exactly {number(n, r)} {quote(c)} characters", "whole"
    pair = r.choice(("ab", "ha", "xy", "01", "na"))
    return (
        rep(Group(lit(pair), capture=False), 1, None),
        f"{quote(pair)} repeated one or more times, like {pair * 3}",
        "whole",
    )


@concept
def version(r: random.Random) -> tuple[Node, str, str]:
    k = r.randrange(5)
    num = rep(DIGIT, 1, None)
    if k == 0:
        return (
            seq(num, lit("."), num, lit("."), num),
            "a version number like 1.2.3: three numbers separated by dots",
            "whole",
        )
    if k == 1:
        return (
            seq(opt(lit("v")), num, lit("."), num, opt(Group(seq(lit("."), num)))),
            ("a version like v1.2 or 1.2.3: an optional v, then two or three numbers separated by dots"),
            "whole",
        )
    if k == 2:
        return seq(lit("3."), num), "a Python 3 version like 3.14", "whole"
    if k == 3:
        tree = seq(
            num,
            lit("."),
            num,
            lit("."),
            num,
            opt(Group(seq(lit("-"), rep(cls(rng("0", "9"), rng("a", "z"), ch(".")), 1, None)))),
        )
        return tree, "a semantic version like 2.0.1 with an optional pre-release part such as -rc.1", "whole"
    return (
        seq(lit("Python "), lit("3."), num, lit("."), num),
        "the text Python followed by a version like 3.14.2",
        "whole",
    )


@concept
def hex_color(r: random.Random) -> tuple[Node, str, str]:
    k = r.randrange(3)
    if k == 0:
        tree = seq(lit("#"), Group(alt(rep(HEX, 6, 6), rep(HEX, 3, 3)), capture=False))
        return tree, "a hexadecimal color like #a1b2c3 or #FFF: a hash and 3 or 6 hex digits", "whole"
    if k == 1:
        return (
            seq(lit("#"), rep(LOWER_HEX, 6, 6)),
            "a color like #ff8800: a hash and six lowercase hexadecimal digits",
            "whole",
        )
    return (
        seq(opt(lit("#")), rep(HEX, 6, 6)),
        "six hexadecimal digits for a color, with an optional # in front",
        "whole",
    )


@concept
def uuid(r: random.Random) -> tuple[Node, str, str]:
    parts = [rep(LOWER_HEX, n, n) for n in (8, 4, 4, 4, 12)]
    tree = seq(parts[0], lit("-"), parts[1], lit("-"), parts[2], lit("-"), parts[3], lit("-"), parts[4])
    return tree, "a UUID like 123e4567-e89b-12d3-a456-426614174000 (lowercase)", "whole"


# --- network --------------------------------------------------------------------------------


@concept
def ipv4(r: random.Random) -> tuple[Node, str, str]:
    if r.random() < 0.6:
        tree = seq(d(1, 3), rep(Group(seq(lit("."), d(1, 3)), capture=False), 3, 3))
        return tree, "an IPv4 address made of four groups of 1 to 3 digits separated by dots", "whole"
    octet = alt(
        seq(lit("25"), cls(rng("0", "5"))),
        seq(lit("2"), cls(rng("0", "4")), DIGIT),
        seq(lit("1"), d(2)),
        seq(opt(cls(rng("1", "9"))), DIGIT),
    )
    tree = seq(Group(octet, capture=False), rep(Group(seq(lit("."), Group(octet, capture=False)), capture=False), 3, 3))
    return tree, "an IPv4 address whose four numbers are each from 0 to 255", "whole"


@concept
def mac(r: random.Random) -> tuple[Node, str, str]:
    sep = r.choice(":-")
    tree = seq(rep(HEX, 2, 2), rep(Group(seq(lit(sep), rep(HEX, 2, 2)), capture=False), 5, 5))
    return tree, f"a MAC address: six pairs of hexadecimal digits separated by {char_plural(sep)}", "whole"


@concept
def email(r: random.Random) -> tuple[Node, str, str]:
    local = rep(cls(("cat", "word"), ch("."), ch("+"), ch("-")), 1, None)
    domain = rep(cls(("cat", "word"), ch("-")), 1, None)
    tree = seq(local, lit("@"), domain, rep(Group(seq(lit("."), domain)), 1, None))
    return tree, "a simple email address like jane.doe+news@mail.example.org", "whole"


@concept
def url(r: random.Random) -> tuple[Node, str, str]:
    host = rep(cls(("cat", "word"), ch("."), ch("-")), 1, None)
    if r.random() < 0.5:
        tree = seq(
            lit("http"),
            opt(lit("s")),
            lit("://"),
            host,
            opt(Group(seq(lit("/"), rep(cls(("cat", "word"), ch("."), ch("/"), ch("-")), 0, None)))),
        )
        return tree, "an http or https URL like https://example.org/docs/index.html", "whole"
    return seq(lit("https://"), host), "an https URL that is only a host name, like https://example.org", "whole"


@concept
def phone(r: random.Random) -> tuple[Node, str, str]:
    k = r.randrange(3)
    if k == 0:
        return seq(lit("("), d(3), lit(") "), d(3), lit("-"), d(4)), "a US phone number like (555) 123-4567", "whole"
    if k == 1:
        sep = r.choice("-. ")
        return seq(d(3), lit(sep), d(3), lit(sep), d(4)), f"a phone number like 555{sep}123{sep}4567", "whole"
    return seq(lit("+"), d(1, 3), lit(" "), d(4, 14)), "an international phone number like +49 3012345678", "whole"


@concept
def path(r: random.Random) -> tuple[Node, str, str]:
    part = rep(cls(("cat", "word"), ch("."), ch("-")), 1, None)
    k = r.randrange(3)
    if k == 0:
        return (
            rep(Group(seq(lit("/"), part), capture=False), 1, None),
            "an absolute Unix path like /usr/local/bin",
            "whole",
        )
    if k == 1:
        ext = r.choice(EXTENSIONS)
        return (
            seq(rep(cls(("cat", "word"), ch("-")), 1, None), lit("." + ext)),
            f"a file name ending in .{ext}",
            "whole",
        )
    chosen = words(EXTENSIONS, r)
    tree = seq(rep(cls(("cat", "word"), ch("-")), 1, None), lit("."), Group(word_alt(chosen), capture=False))
    return tree, f"a file name with one of the extensions {join(['.' + e for e in chosen], 'or')}", "whole"


# --- text and markup ------------------------------------------------------------------------


@concept
def quoted(r: random.Random) -> tuple[Node, str, str]:
    q = r.choice("\"'")
    tree = seq(lit(q), rep(cls(ch(q), negate=True), 0, None), lit(q))
    name = "double" if q == '"' else "single"
    return tree, f"a string in {name} quotes with no {name} quote inside, like {q}hello world{q}", "whole"


@concept
def html_tag(r: random.Random) -> tuple[Node, str, str]:
    k = r.randrange(3)
    if k == 0:
        return (
            seq(lit("<"), LOWER, rep(cls(rng("a", "z"), rng("0", "9")), 0, None), lit(">")),
            ("an HTML opening tag without attributes, like <div> or <h1>"),
            "whole",
        )
    if k == 1:
        return seq(lit("</"), rep(LOWER, 1, None), lit(">")), "an HTML closing tag like </p>", "whole"
    return (
        seq(lit("<"), rep(cls(ch(">"), negate=True), 1, None), lit(">")),
        "contain an HTML tag: < then anything but > then >",
        "line",
    )


@concept
def tag(r: random.Random) -> tuple[Node, str, str]:
    c = r.choice("#@")
    what = "hashtag" if c == "#" else "mention"
    return (
        seq(lit(c), rep(WORD, 1, None)),
        f"a {what} like {c}python: {quote(c)} followed by letters, digits or underscores",
        "whole",
    )


@concept
def key_value(r: random.Random) -> tuple[Node, str, str]:
    k = r.randrange(3)
    if k == 0:
        return (
            seq(rep(WORD, 1, None), lit("="), rep(cls(ch(" "), negate=True), 0, None)),
            ("a key=value pair: a name, an equals sign and a value without spaces (it may be empty)"),
            "whole",
        )
    if k == 1:
        return (
            seq(lit("["), rep(cls(("cat", "word"), ch("."), ch("-")), 1, None), lit("]")),
            ("an INI or TOML section header like [tool.ruff]"),
            "whole",
        )
    return (
        seq(rep(WORD, 1, None), lit(": "), rep(AnyChar(), 1, None)),
        ("a line like name: value, a name, a colon and a space, then the value"),
        "whole",
    )


@concept
def card(r: random.Random) -> tuple[Node, str, str]:
    sep = r.choice(" -")
    tree = seq(d(4), rep(Group(seq(lit(sep), d(4)), capture=False), 3, 3))
    return tree, f"sixteen digits in four groups of four, separated by {char_plural(sep)}", "whole"


@concept
def postal(r: random.Random) -> tuple[Node, str, str]:
    k = r.randrange(3)
    if k == 0:
        return (
            seq(d(5), opt(Group(seq(lit("-"), d(4)), capture=False))),
            ("a US ZIP code: five digits, optionally followed by a dash and four digits"),
            "whole",
        )
    if k == 1:
        return d(5), "a five-digit postal code", "whole"
    return seq(d(4), lit(" "), rep(UPPER, 2, 2)), "a Dutch postal code like 1234 AB", "whole"


@concept
def coordinates(r: random.Random) -> tuple[Node, str, str]:
    num = seq(opt(lit("-")), d(1, 3), lit("."), rep(DIGIT, 1, None))
    tree = seq(num, lit(","), opt(lit(" ")), num)
    return tree, "a pair of coordinates like 52.52, -13.405: two decimal numbers separated by a comma", "whole"


# --- lines ----------------------------------------------------------------------------------


@concept
def line(r: random.Random) -> tuple[Node, str, str]:
    k = r.randrange(14)
    kw = r.choice(KEYWORDS)
    if k == 0:
        return seq(START, lit(kw)), f"start with {quote(kw)}", "line"
    if k == 1:
        c = r.choice(";:,.)")
        return seq(lit(c), END), f"end with {char_name(c)}", "line"
    if k == 2:
        return seq(START, rep(SPACE, 0, None), END), "are empty or contain only whitespace", "line"
    if k == 3:
        return seq(rep(SPACE, 1, None), END), "end with whitespace (trailing spaces)", "line"
    if k == 4:
        return seq(START, rep(SPACE, 0, None), lit("#")), "are comments: optional whitespace, then #", "line"
    if k == 5:
        return seq(BOUNDARY, lit(kw), BOUNDARY), f"contain the word {quote(kw)} as a whole word", "line"
    if k == 6:
        return (
            seq(START, lit("def "), rep(WORD, 1, None), lit("(")),
            "are Python function definitions at the start of the line, like def main(",
            "line",
        )
    if k == 7:
        return (
            seq(START, Group(alt(lit("import "), lit("from ")), capture=False)),
            "are Python import lines (starting with import or from)",
            "line",
        )
    if k == 8:
        return (
            seq(START, rep(lit("#"), 1, 6), lit(" ")),
            "are Markdown headings: one to six # and a space at the start",
            "line",
        )
    if k == 9:
        return seq(START, d(1, None), lit(". ")), "are numbered list items like 1. or 12. at the start", "line"
    if k == 10:
        return seq(DIGIT), "contain at least one digit", "line"
    if k == 11:
        return seq(START, rep(DIGIT, 1, None), END), "contain only digits", "line"
    if k == 12:
        level = r.choice(WORDS["levels"])
        return (
            seq(START, d(4), lit("-"), d(2), lit("-"), d(2), lit(" "), rep(AnyChar(), 0, None), lit(level)),
            (f"are log lines that start with a date like 2026-11-25 and contain {level}"),
            "line",
        )
    n = r.choice((80, 100, 120))
    return rep(AnyChar(), n + 1, None), f"are longer than {n} characters", "line"


def names() -> list[str]:
    return sorted(CONCEPTS)

"""satyrn data regex: the regex tree, its dialects, descriptions, tests and checks. No mocks.

grep and sed are the real ones of this computer. The full build needs the pinned sources from
the network and a minute; it is covered by running `satyrn data regex`, which checks its result
against the SHA-256 in pins.toml. Here: the parts, each generated task checked for real.
"""

from __future__ import annotations

import random
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "src" / "satyrn_local" / "runners"))

import answer_tasks  # noqa: E402
import train_small  # noqa: E402

from satyrn_local import datasets  # noqa: E402
from satyrn_local.layout import Pins  # noqa: E402
from satyrn_local.regex import check, sample, score, sources, tasks  # noqa: E402
from satyrn_local.regex.concepts import CONCEPTS  # noqa: E402
from satyrn_local.regex.describe import describe  # noqa: E402
from satyrn_local.regex.tree import from_python, render, risky, simplify, to_posix, to_python  # noqa: E402

PINS = Pins.load(ROOT / "pins.toml")


# --- the tree and its dialects --------------------------------------------------------------
@pytest.mark.parametrize(
    ("python", "extended", "basic"),
    [
        (r"\d{4}-\d{2}-\d{2}", "[0-9]{4}-[0-9]{2}-[0-9]{2}", r"[0-9]\{4\}-[0-9]\{2\}-[0-9]\{2\}"),
        (r"-?\d+(\.\d+)?", r"-?[0-9]+(\.[0-9]+)?", r"-\?[0-9]\+\(\.[0-9]\+\)\?"),
        (r"[A-Za-z_]\w*", "[A-Za-z_][[:alnum:]_]*", "[A-Za-z_][[:alnum:]_]*"),
        (r"\bcat\b|dog", r"\bcat\b|dog", r"\bcat\b\|dog"),
        (r"[]^a-]", "[]a^-]", "[]a^-]"),
        (r"^\s+$", "^[[:space:]]+$", r"^[[:space:]]\+$"),
        (r"a+b{2,}c?", "a+b{2,}c?", r"a\+b\{2,\}c\?"),
    ],
)
def test_one_tree_in_three_dialects(python: str, extended: str, basic: str) -> None:
    tree = from_python(python)
    assert to_posix(tree, extended=True) == extended
    assert to_posix(tree, extended=False) == basic


@pytest.mark.parametrize("pattern", [r"(?<=a)b", r"(a)\1", r"(?i)abc", r"a++", "é+"])
def test_what_the_tree_cannot_hold(pattern: str) -> None:
    assert from_python(pattern) is None


def test_lazy_repeats_have_no_posix_form() -> None:
    tree = from_python(r"a.*?b")
    assert to_python(tree) == "a.*?b"
    assert to_posix(tree, extended=True) is None


def test_nested_unlimited_repeats_are_risky() -> None:
    assert risky(from_python(r"(a+)+b"))
    assert not risky(from_python(r"(ab)+c+"))


@pytest.mark.parametrize(
    ("pattern", "simple"),
    [
        (r"(([a-z])|(.)){7,}", ".{7,}"),
        (r"(([AEIOUaeiou])|([A-Z])){6,}", "[aeiouA-Z]{6,}"),
        (r"(dog).*.*(.)", "dog.*."),
        (r"([0-9]|[a-zA-Z]){3,4}", "[0-9a-zA-Z]{3,4}"),
    ],
)
def test_simplify_drops_groups_and_merges_classes(pattern: str, simple: str) -> None:
    assert to_python(simplify(from_python(pattern))) == simple


@pytest.mark.parametrize(
    ("pattern", "text"),
    [
        (r"x{3,}", 'at least three "x" characters'),
        (r"[a-z0-9]+", "one or more lowercase letters or digits"),
        (r"[^0-9]", "any character except digits"),
        (r"^\s+$", "nothing but one or more whitespace characters"),
        (r"[A-Za-z_]\w*", "a letter or underscore, followed by any number of letters, digits or underscores"),
    ],
)
def test_descriptions(pattern: str, text: str) -> None:
    assert describe(from_python(pattern), random.Random(1)) == text


# --- test strings ---------------------------------------------------------------------------
@pytest.mark.parametrize("name", sorted(CONCEPTS))
def test_every_concept_gives_strings_that_match_and_near_misses_that_do_not(name: str) -> None:
    r = random.Random(name)
    usable = 0
    for _ in range(8):
        tree, text, kind = CONCEPTS[name](r)
        assert text
        mode = "fullmatch" if kind == "whole" else "search"
        tests = tasks.tests_for(tree, mode, r)  # None for a regex with one string only, such as ---
        if tests is not None:
            usable += 1
            assert check.python(to_python(tree), mode, *tests)
            assert not set(tests[0]) & set(tests[1])
    assert usable >= 4, name


def test_grep_agrees_with_python_on_every_concept() -> None:
    """The POSIX rendering means the same as the Python one: checked with the real grep."""
    r = random.Random(7)
    for name in sorted(CONCEPTS):
        tree, _, kind = CONCEPTS[name](r)
        mode = "fullmatch" if kind == "whole" else "search"
        good = sample.positives(tree, mode, r, 6)
        bad = sample.negatives(tree, mode, good, r, 6)
        for dialect in ("grep -E", "grep"):
            line = tasks.seq(tasks.START, tree, tasks.END) if kind == "whole" else tree
            pattern = render(line, dialect)
            if pattern is not None:
                assert check.grep(pattern, extended=dialect == "grep -E", match=good, no_match=bad), (name, pattern)


# --- checks: any right answer counts, wrong ones and unsafe ones do not ---------------------
def test_an_equivalent_answer_counts() -> None:
    good, bad = ["2026-11-25", "1999-01-01"], ["2026-1-25", "2026/11/25"]
    assert check.python(r"\d{4}-\d{2}-\d{2}", "fullmatch", good, bad)
    assert check.python(r"[0-9]{4}(-[0-9][0-9]){2}", "fullmatch", good, bad)
    assert not check.python(r"\d+-\d+-\d+", "fullmatch", good, [*bad, "1-2-3"])


def test_grep_answers_are_checked_by_grep() -> None:
    task = {"dialect": "grep -E", "match": ["cat", "a dog"], "no_match": ["cow"]}
    assert check.answer(task, "cat|dog")
    assert not check.answer(task, "cat")
    assert not check.answer(task, "(")  # a grep error is a wrong answer
    basic = task | {"dialect": "grep"}
    assert check.answer(basic, r"cat\|dog")
    assert not check.answer(basic, "cat|dog")  # in basic regexes | is a plain character


def test_sed_answers_run_in_the_sandbox(tmp_path: Path) -> None:
    task = {"dialect": "sed -E", "pairs": [["hello world", "world hello"], ["a b", "b a"]]}
    assert check.answer(task, r"s/([a-z]+) ([a-z]+)/\2 \1/")
    assert check.answer(task, r"s|(\w+) (\w+)|\2 \1|")
    assert not check.answer(task, r"s/([a-z]+) ([a-z]+)/\1 \2/")
    written = tmp_path / "written"
    assert not check.answer(task, rf"s/([a-z]+) ([a-z]+)/\2 \1/w {written}")
    assert not check.answer(task, "e touch " + str(written))
    assert not written.exists()


def test_a_python_answer_that_backtracks_for_ages_is_wrong_not_stuck() -> None:
    assert not score.python_isolated(r"(a+)+b", "fullmatch", ["ab"], ["a" * 40 + "c"])


@pytest.mark.parametrize(
    ("output", "dialect", "answer"),
    [
        ("```regex\n\\d+\n```", "python", r"\d+"),
        ("`^a+$`", "python", "^a+$"),
        ('re.compile(r"\\d{3}")', "python", r"\d{3}"),
        ("r'[a-z]+'", "python", "[a-z]+"),
        ('"\\bcat\\b"', "python", "\\bcat\\b"),
        ("grep -E '^[0-9]+$' file.txt", "grep -E", "^[0-9]+$"),
        ("echo x | sed -E 's/a/b/g'", "sed -E", "s/a/b/g"),
        ("cat|dog\nExplanation: ...", "grep -E", "cat|dog"),
    ],
)
def test_the_answer_is_taken_out_the_same_way_for_every_model(output: str, dialect: str, answer: str) -> None:
    assert score.extract(output, dialect) == answer


# --- tasks ----------------------------------------------------------------------------------
def _made(make, n: int, seed: str) -> list[dict]:
    r = random.Random(seed)
    out = []
    for _ in range(n * 6):
        row = make(r)
        if row is not None:
            out.append(row)
        if len(out) == n:
            break
    return out


def _concept_item(r: random.Random) -> tasks.Item:
    name = r.choice(sorted(CONCEPTS))
    tree, text, kind = CONCEPTS[name](r)
    return tasks.Item(tree, text, kind, f"concept:{name}", natural=True)


@pytest.mark.parametrize(
    "kind",
    ["describe", "describe+examples", "examples", "translate", "fix", "substitute", "generated"],
)
def test_every_kind_of_task_passes_its_own_tests(kind: str) -> None:
    def make(r: random.Random) -> dict | None:
        if kind == "substitute":
            return tasks.sed_task(r)
        if kind == "translate":
            return tasks.translate_task(_concept_item(r), r)
        if kind == "fix":
            return tasks.fix_task(_concept_item(r), r)
        if kind == "generated":
            item = tasks.random_item(r)
            dialect = r.choice(("python", "grep -E", "grep"))
            return None if item is None else tasks.match_task(item, dialect, "describe", r)
        return tasks.match_task(_concept_item(r), r.choice(("python", "grep -E", "grep")), kind, r)

    rows = _made(make, 25, kind)
    assert len(rows) >= 20
    for row in rows:
        assert row["messages"][1]["content"] == row["answer"]
        assert row["messages"][0]["content"].endswith(("regular expression.", "expression."))
        assert check.answer(row, row["answer"]), row


def test_tasks_are_the_same_with_the_same_seed() -> None:
    first = _made(tasks.sed_task, 10, "same")
    assert first == _made(tasks.sed_task, 10, "same")


def test_fix_tasks_show_a_string_the_wrong_regex_gets_wrong() -> None:
    for row in _made(lambda r: tasks.fix_task(_concept_item(r), r), 20, "fix"):
        prompt = row["messages"][0]["content"]
        wrong = prompt.splitlines()[1]
        assert wrong != row["answer"]
        assert "but it should" in prompt
        assert not check.answer(row, wrong)


# --- sources --------------------------------------------------------------------------------
def test_structured_regex_notation() -> None:
    notation = "concat(<num>,concat(repeat(<h>,3),concat(optional(repeat(<low>,2)),repeatatleast(<cap>,3))))"
    tree = sources._streg(notation)
    assert to_python(tree) == r"\dh{3}(?:[a-z]{2})?[A-Z]{3,}"
    assert to_python(simplify(sources._streg("contain(or(<,>,<->))"))) == ".*[,\\-].*"
    assert to_python(sources._streg("notcc(<num>)")) == r"\D"
    with pytest.raises(sources.Unsupported):
        sources._streg("and(contain(<a>),not(contain(<b>)))")


def test_contains_regexes_become_search_regexes() -> None:
    tree, kind = sources.as_line(simplify(from_python("(.*)dog(.*)")))
    assert (to_python(tree), kind) == ("dog", "line")
    tree, kind = sources.as_line(simplify(from_python("dog.*")))
    assert (to_python(tree), kind) == ("^dog", "line")
    tree, kind = sources.as_line(simplify(from_python("[a-z]+")))
    assert (to_python(tree), kind) == ("[a-z]+", "whole")


def test_every_regex_source_is_a_pinned_git_commit_with_a_license() -> None:
    regex = PINS.data["data"]["regex"]
    assert set(regex["sources"]) == {"structured-regex", "deep-regex", "lingua-franca"}
    for name, source in regex["sources"].items():
        assert re.fullmatch(r"[0-9a-f]{40}", source["commit"]), name
        assert source["repo"].startswith("https://github.com/")
        assert source["license"]
        assert any(p.lstrip("/") in source["license"] or source["license"] in p for p in source["paths"])
    for split in datasets.REGEX_FILES:
        assert re.fullmatch(r"[0-9a-f]{64}", regex[split]["sha256"]), split
        assert regex[split]["rows"] > 500


def test_training_and_answering_use_the_same_chat_format() -> None:
    assert train_small.chat("question") == answer_tasks.chat("question")
    assert train_small.chat("q") == "<|im_start|>user\nq<|im_end|>\n<|im_start|>assistant\n"


def test_satyrn_train_test_needs_one_model() -> None:
    out = subprocess.run(
        [sys.executable, str(ROOT / "satyrn.py"), "train", "test"],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert out.returncode != 0
    assert "name one model" in out.stderr

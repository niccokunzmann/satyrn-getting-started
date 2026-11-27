"""Build the regex dataset: tasks from every source, each checked, split into training and test.

The same sources and seed give the same files, byte for byte. The tests of the test split never
share a regex (or a StructuredRegex problem) with the training split.
"""

from __future__ import annotations

import hashlib
import json
import random
from collections import Counter
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import check, sources
from .concepts import CONCEPTS
from .tasks import Item, fix_task, match_task, random_item, sed_task, translate_task

SEED = 2026
TEST_SHARE = 40  # of 1000: the share of regexes that go to the test split
STREG_TEST = 150  # descriptions from StructuredRegex's own test splits in the test split
TEST_REPEATS = 3  # at most this many test rows with the same answer in the same dialect
COUNTS = {  # how many tasks of each kind to make, for the training and test splits together
    "concept": 4000,
    "generated": 2500,
    "lingua-franca": 3000,
    "nl-rx-turk": 2500,
    "kb13": 600,
    "sed": 1500,
    "translate": 700,
    "fix": 700,
}
MATCH_DIALECTS = (("python", 0.55), ("grep -E", 0.3), ("grep", 0.15))
MATCH_TASKS = (("describe", 0.45), ("describe+examples", 0.3), ("examples", 0.25))


def weighted(r: random.Random, choices: tuple) -> str:
    return r.choices([c for c, _ in choices], [w for _, w in choices])[0]


def is_test(key: str) -> bool:
    return int(hashlib.sha256(key.encode()).hexdigest()[:8], 16) % 1000 < TEST_SHARE


def concept_item(r: random.Random) -> Item:
    name = r.choice(sorted(CONCEPTS))
    tree, text, kind = CONCEPTS[name](r)
    return Item(tree, text, kind, f"concept:{name}", natural=True)


def fill(n: int, make: Callable[[random.Random], tuple[str, dict] | None], r: random.Random, tries: int = 6) -> list:
    """Up to ``n`` (key, row) pairs from ``make``, each prompt once."""
    out, prompts = [], set()
    for _ in range(n * tries):
        made = make(r)
        if made is None:
            continue
        key, row = made
        prompt = row["messages"][0]["content"]
        if prompt in prompts:
            continue
        prompts.add(prompt)
        out.append((key, row))
        if len(out) == n:
            break
    return out


def from_items(items: list[Item], task_kinds: tuple = MATCH_TASKS) -> Callable:
    pool = list(items)

    def make(r: random.Random) -> tuple[str, dict] | None:
        if not pool:
            return None
        item = pool.pop(r.randrange(len(pool)))
        kinds = task_kinds if item.sentence or item.kind == "line" or item.natural else MATCH_TASKS
        task = weighted(r, kinds)
        row = match_task(item, weighted(r, MATCH_DIALECTS), task, r)
        return None if row is None else (item.key(), row)

    return make


def build(folders: dict[str, Path], log: Callable[[str], None]) -> tuple[list[dict], list[dict], dict]:  # noqa: PLR0915
    """(training rows, test rows, report)."""
    report: dict = {"sources": {}}
    rows: list[tuple[str, dict]] = []

    def section(name: str, made: list) -> None:
        rows.extend(made)
        report["sources"][name] = report["sources"].get(name, 0) + len(made)
        log(f"  {name:22s} {len(made):6d} tasks")

    def one(new_item: Callable[[random.Random], Item | None]) -> Callable:
        def make(r: random.Random) -> tuple[str, dict] | None:
            item = new_item(r)
            if item is None:
                return None
            row = match_task(item, weighted(r, MATCH_DIALECTS), weighted(r, MATCH_TASKS), r)
            return None if row is None else (item.key(), row)

        return make

    section("concepts", fill(COUNTS["concept"], one(concept_item), random.Random(f"{SEED}:concept")))
    section("generated", fill(COUNTS["generated"], one(random_item), random.Random(f"{SEED}:generated")))

    streg_train, streg_test, counts = sources.structured_regex(folders["structured-regex"])
    report["structured-regex"] = counts | {"training items": len(streg_train), "test items": len(streg_test)}
    r = random.Random(f"{SEED}:structured-regex")
    streg_kinds = (("describe", 0.6), ("describe+examples", 0.4))
    made = fill(len(streg_train), from_items(streg_train, streg_kinds), r, tries=2)
    section("structured-regex", [(f"train:{k}", row) for k, row in made])
    test_items = r.sample(streg_test, min(STREG_TEST, len(streg_test)))
    made = fill(len(test_items), from_items(test_items, streg_kinds), r, tries=2)
    section("structured-regex test", [(f"test:{k}", row) for k, row in made])

    for name, folder_name in (("nl-rx-turk", "NL-RX-Turk"), ("kb13", "KB13")):
        items, counts = sources.nl_rx(folders["deep-regex"], folder_name)
        report[name] = counts | {"items": len(items)}
        r = random.Random(f"{SEED}:{name}")
        section(
            name, fill(COUNTS[name], from_items(items, (("describe", 0.7), ("describe+examples", 0.3))), r, tries=3)
        )

    r = random.Random(f"{SEED}:lingua-franca")
    items, counts = sources.lingua_franca(
        folders["lingua-franca"] / "data" / "production-regexes" / "uniq-regexes-8.json", r, COUNTS["lingua-franca"]
    )
    report["lingua-franca"] = counts
    lf_kinds = (("examples", 0.5), ("describe+examples", 0.5))
    lf_items = list(items)
    section("lingua-franca", fill(COUNTS["lingua-franca"], from_items(items, lf_kinds), r, tries=2))

    r = random.Random(f"{SEED}:sed")

    def sed(r: random.Random) -> tuple[str, dict] | None:
        row = sed_task(r)
        return None if row is None else (row["answer"], row)

    section("sed", fill(COUNTS["sed"], sed, r))

    def mixed_item(r: random.Random) -> Item | None:
        k = r.random()
        if k < 0.5:
            return concept_item(r)
        if k < 0.8:
            return random_item(r)
        return r.choice(lf_items) if lf_items else None

    for name, task in (("translate", translate_task), ("fix", fix_task)):
        r = random.Random(f"{SEED}:{name}")

        def make(r: random.Random, task: Callable = task) -> tuple[str, dict] | None:
            item = mixed_item(r)
            if item is None:
                return None
            row = task(item, r)
            return None if row is None else (item.key(), row)

        section(name, fill(COUNTS[name], make, r))

    log("checking every answer with Python, grep and sed")
    verdicts = verify([row for _, row in rows])
    failed = Counter(row["dialect"] for (_, row), ok in zip(rows, verdicts, strict=True) if not ok)
    report["dropped: answer failed its tests"] = dict(sorted(failed.items()))
    train, test = [], []
    repeats: Counter = Counter()
    for (key, row), ok in zip(rows, verdicts, strict=True):
        if not ok:
            continue
        if key.startswith("test:") or (not key.startswith("train:") and is_test(key)):
            repeats[row["dialect"], row["answer"]] += 1
            if repeats[row["dialect"], row["answer"]] <= TEST_REPEATS:
                test.append(row)
        else:
            train.append(row)
    report[f"test rows left out: same answer more than {TEST_REPEATS} times"] = sum(
        n - TEST_REPEATS for n in repeats.values() if n > TEST_REPEATS
    )
    for i, row in enumerate(train):
        row["id"] = f"train-{i:05d}"
    for i, row in enumerate(test):
        row["id"] = f"test-{i:04d}"
    report["training rows"], report["test rows"] = len(train), len(test)
    report["tools"] = check.tool_versions()
    return train, test, report


def verify(rows: list[dict]) -> list[bool]:
    """Each reference answer against its own tests; grep and sed run in parallel."""
    with ThreadPoolExecutor(max_workers=8) as pool:
        return list(pool.map(lambda row: check.answer(row, row["answer"]), rows))


def write(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as out:
        for row in rows:
            ordered = {"id": row["id"], **{k: v for k, v in row.items() if k != "id"}}
            out.write(json.dumps(ordered, ensure_ascii=False) + "\n")

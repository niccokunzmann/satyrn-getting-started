"""A small LoRA training on the CPU. Runs in `satyrn train`'s own venv (docs/train.md).

Continued pretraining as in satyrn-models' first stage, made small enough for a CPU: the dataset's
documents are joined and cut into pieces of ``--seq-len`` tokens, about one in ten (at most 16) is
kept back for validation, and a LoRA adapter (same target modules and alpha = 2 * rank as
satyrn-models) learns to predict the training pieces, one piece per step.

The run reports to three files in ``--out``: train.log (what it prints), metrics.jsonl (one line
per step and per validation) and status.json (the latest state, for `satyrn train status`). It
stops with an error when the loss is not a finite number.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import sys
import time
import traceback
from collections import deque
from datetime import UTC, datetime
from pathlib import Path

TARGET_MODULES = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]
MAX_VALIDATION_PIECES = 16
PRINT_EVERY = 30.0  # seconds between progress lines
EVALUATIONS = 4  # validation after each quarter of the run


def hms(seconds: float) -> str:
    seconds = round(seconds)
    return f"{seconds // 3600}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"


class Report:
    """train.log, metrics.jsonl and status.json of one run."""

    def __init__(self, out: Path) -> None:
        self.out = out
        self.log = (out / "train.log").open("a", encoding="utf-8", buffering=1)
        self.metrics = (out / "metrics.jsonl").open("a", encoding="utf-8", buffering=1)
        self.state: dict = {}

    def say(self, text: str) -> None:
        print(text, flush=True)
        self.log.write(text + "\n")

    def metric(self, **fields: object) -> None:
        self.metrics.write(json.dumps(fields) + "\n")

    def status(self, **fields: object) -> None:
        self.state |= fields | {"updated": datetime.now(UTC).isoformat(timespec="seconds")}
        part = self.out / "status.json.part"
        part.write_text(json.dumps(self.state, indent=2) + "\n", encoding="utf-8")
        part.replace(self.out / "status.json")


def finite(value: float, what: str) -> float:
    if not math.isfinite(value):
        raise FloatingPointError(f"{what} is {value}: the training diverged; try a lower --lr")
    return value


def pieces(data: Path, tokenizer: object, seq_len: int, seed: int) -> tuple[list, list, int, int]:
    rows = [json.loads(line) for line in data.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not rows:
        raise ValueError(f"{data} has no rows")
    ids: list[int] = []
    for row in rows:
        ids += tokenizer(row["text"])["input_ids"] + [tokenizer.eos_token_id]
    blocks = [ids[i : i + seq_len] for i in range(0, len(ids) - seq_len + 1, seq_len)]
    if len(blocks) < 2:
        raise ValueError(f"{data} is too small: fewer than two pieces of {seq_len} tokens")
    random.Random(seed).shuffle(blocks)  # noqa: S311 - a repeatable data order, not a secret
    n_valid = max(1, min(MAX_VALIDATION_PIECES, len(blocks) // 10))
    return blocks[n_valid:], blocks[:n_valid], len(rows), len(ids)


def train(args: argparse.Namespace, report: Report) -> int:  # noqa: PLR0915 - one straight training story
    import torch  # noqa: PLC0415 - heavy imports after the status says "preparing"
    from peft import LoraConfig, get_peft_model  # noqa: PLC0415
    from transformers import AutoModelForCausalLM, AutoTokenizer  # noqa: PLC0415
    from transformers.utils import logging as transformers_logging  # noqa: PLC0415

    transformers_logging.disable_progress_bar()  # one line per event in train.log, no progress bars

    torch.manual_seed(args.seed)
    torch.set_num_threads(args.threads)
    tokenizer = AutoTokenizer.from_pretrained(args.model)
    train_blocks, valid_blocks, n_docs, n_tokens = pieces(args.data, tokenizer, args.seq_len, args.seed)
    epochs = args.steps / len(train_blocks)
    report.say(
        f"dataset: {n_docs} documents, {n_tokens:,} tokens -> {len(train_blocks)} training and "
        f"{len(valid_blocks)} validation pieces of {args.seq_len} tokens ({epochs:.2f} passes in {args.steps} steps)"
    )
    model = AutoModelForCausalLM.from_pretrained(args.model, dtype=torch.float32)
    lora = LoraConfig(
        r=args.rank, lora_alpha=2 * args.rank, lora_dropout=0.0, target_modules=TARGET_MODULES, task_type="CAUSAL_LM"
    )
    model = get_peft_model(model, lora)
    trainable, total = model.get_nb_trainable_parameters()
    report.say(
        f"model: {args.model.name}, {total / 1e9:.2f} B weights, {trainable / 1e6:.1f} M of them trainable (LoRA rank "
        f"{args.rank}); CPU with {torch.get_num_threads()} threads"
    )
    params = [p for p in model.parameters() if p.requires_grad]
    optimizer = torch.optim.AdamW(params, lr=args.lr, weight_decay=0.0)
    warmup = max(1, args.steps // 20)
    schedule = torch.optim.lr_scheduler.LambdaLR(
        optimizer, lambda s: min((s + 1) / warmup, max(0.0, (args.steps - s) / max(1, args.steps - warmup)))
    )

    def validate() -> float:
        model.eval()
        with torch.no_grad():
            losses = [model(input_ids=torch.tensor([b]), labels=torch.tensor([b])).loss.item() for b in valid_blocks]
        model.train()
        return finite(sum(losses) / len(losses), "the validation loss")

    report.status(state="validating", step=0)
    report.say("validating the untrained model ...")
    started = time.monotonic()
    first = validate()
    valid_seconds = time.monotonic() - started
    report.say(f"validation loss before training: {first:.3f} ({valid_seconds:.0f} s)")
    report.metric(step=0, eval_loss=first)
    report.status(eval_loss_start=first, eval_loss=first)

    checkpoints = sorted({max(1, round(args.steps * k / EVALUATIONS)) for k in range(1, EVALUATIONS + 1)})
    recent: deque[float] = deque(maxlen=10)
    begin = last_print = time.monotonic()
    latest = first
    model.train()
    for step in range(1, args.steps + 1):
        tick = time.monotonic()
        block = torch.tensor([train_blocks[(step - 1) % len(train_blocks)]])
        loss = model(input_ids=block, labels=block).loss
        value = finite(loss.item(), f"the loss at step {step}")
        loss.backward()
        torch.nn.utils.clip_grad_norm_(params, 1.0)
        optimizer.step()
        schedule.step()
        optimizer.zero_grad()
        now = time.monotonic()
        recent.append(now - tick)
        per_step = sum(recent) / len(recent)
        remaining = per_step * (args.steps - step) + valid_seconds * sum(c >= step for c in checkpoints)
        elapsed = now - begin
        lr = schedule.get_last_lr()[0]
        report.metric(step=step, loss=value, lr=lr, seconds=now - tick)
        report.status(
            state="training", step=step, loss=value, seconds_per_step=per_step, elapsed=elapsed, remaining=remaining
        )
        if step <= 3 or step in checkpoints or now - last_print >= PRINT_EVERY:
            last_print = now
            report.say(
                f"step {step:{len(str(args.steps))}d}/{args.steps}  {100 * step // args.steps:3d}%  loss {value:.3f}  "
                f"{per_step:.1f} s/step  elapsed {hms(elapsed)}  remaining ~{hms(remaining)}"
            )
        if step in checkpoints:
            report.status(state="validating")
            latest = validate()
            report.say(f"validation loss {latest:.3f} (before training {first:.3f})")
            report.metric(step=step, eval_loss=latest)
            model.save_pretrained(args.out / "adapter")
            report.status(state="training", eval_loss=latest)
    took = time.monotonic() - begin
    report.say(f"validation loss {first:.3f} -> {latest:.3f} after {args.steps} steps ({hms(took)})")
    report.say(f"adapter: {args.out / 'adapter'}")
    report.status(state="finished", elapsed=took, remaining=0, adapter=str(args.out / "adapter"))
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--model", type=Path, required=True)
    p.add_argument("--data", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--steps", type=int, required=True)
    p.add_argument("--lr", type=float, required=True)
    p.add_argument("--rank", type=int, required=True)
    p.add_argument("--seq-len", type=int, required=True)
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--threads", type=int, required=True)
    args = p.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    report = Report(args.out)
    settings = {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()}
    report.status(
        state="preparing", pid=os.getpid(), steps=args.steps, started=datetime.now(UTC).isoformat(timespec="seconds")
    )
    (args.out / "config.json").write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    report.say(f"run {args.out.name}: {args.steps} steps on {args.data.name}, settings in {args.out / 'config.json'}")
    try:
        return train(args, report)
    except KeyboardInterrupt:
        report.status(state="stopped", error="interrupted with Ctrl+C")
        kept = "the adapter of the last validation is kept" if (args.out / "adapter").is_dir() else "no adapter yet"
        report.say(f"stopped (Ctrl+C); {kept}")
        return 130
    except Exception as error:  # noqa: BLE001 - every failure must end up in status.json
        report.status(state="failed", error=f"{type(error).__name__}: {error}")
        report.log.write(traceback.format_exc())
        report.say(f"FAILED: {type(error).__name__}: {error}")
        return 1


if __name__ == "__main__":
    sys.exit(main())

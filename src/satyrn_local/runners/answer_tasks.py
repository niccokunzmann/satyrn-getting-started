"""Answer the prompts of a question dataset with the small model. Runs in `satyrn train`'s venv.

For `satyrn train test`: the base model, or the base model with the adapter of a training run,
answers each prompt in the chat format of the training (the same text Ollama sends), greedily
(always the most likely next token, so the result is repeatable). The answers go to a JSON Lines
file; `satyrn train test` checks them (Python, grep, sed) without this venv.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

BATCH = 8
MAX_NEW_TOKENS = 96


def chat(prompt: str) -> str:
    """The same as train_small.chat (a test checks it): what Ollama sends for one question."""
    return f"<|im_start|>user\n{prompt}<|im_end|>\n<|im_start|>assistant\n"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--model", type=Path, required=True)
    p.add_argument("--adapter", type=Path)
    p.add_argument("--data", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--limit", type=int)
    p.add_argument("--threads", type=int, required=True)
    args = p.parse_args()

    import torch  # noqa: PLC0415 - heavy imports after the arguments are checked
    from transformers import AutoModelForCausalLM, AutoTokenizer  # noqa: PLC0415
    from transformers.utils import logging as transformers_logging  # noqa: PLC0415

    transformers_logging.disable_progress_bar()
    transformers_logging.set_verbosity_error()
    torch.set_num_threads(args.threads)
    rows = [json.loads(line) for line in args.data.read_text(encoding="utf-8").splitlines() if line.strip()]
    rows = rows[: args.limit] if args.limit else rows
    tokenizer = AutoTokenizer.from_pretrained(args.model, padding_side="left")
    model = AutoModelForCausalLM.from_pretrained(args.model, dtype=torch.float32)
    if args.adapter:
        from peft import PeftModel  # noqa: PLC0415

        model = PeftModel.from_pretrained(model, args.adapter).merge_and_unload()
    model.eval()
    stop = tokenizer.convert_tokens_to_ids("<|im_end|>")
    started = time.monotonic()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as out, torch.no_grad():
        for start in range(0, len(rows), BATCH):
            batch = rows[start : start + BATCH]
            prompts = [chat(row["messages"][0]["content"]) for row in batch]
            encoded = tokenizer(prompts, return_tensors="pt", padding=True)
            generated = model.generate(
                **encoded,
                max_new_tokens=MAX_NEW_TOKENS,
                do_sample=False,
                eos_token_id=stop,
                pad_token_id=tokenizer.pad_token_id,
            )
            for row, ids in zip(batch, generated[:, encoded["input_ids"].shape[1] :], strict=True):
                text = tokenizer.decode(ids, skip_special_tokens=True)
                out.write(json.dumps({"id": row["id"], "output": text}) + "\n")
            done = start + len(batch)
            elapsed = time.monotonic() - started
            print(
                f"  answered {done}/{len(rows)}  ({elapsed / done:.1f} s each, "
                f"~{elapsed / done * (len(rows) - done) / 60:.0f} min left)",
                flush=True,
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())

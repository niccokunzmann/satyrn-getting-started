"""Merge a run's LoRA adapter into the base model, for Ollama. Runs in `satyrn train`'s venv.

The result is a plain Hugging Face model folder (safetensors, 16-bit) that `ollama create` can
convert. The weights come from peft's ``merge_and_unload``; every other file is the base
model's own: the architecture is unchanged, and transformers 5 writes ``config.json`` in a
newer form (``rope_parameters``) than Ollama's converter reads (``rope_theta``).
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM
from transformers.utils import logging

WEIGHTS = "model.safetensors"


def main() -> int:
    p = argparse.ArgumentParser()
    for name in ("model", "adapter", "out"):
        p.add_argument(f"--{name}", type=Path, required=True)
    args = p.parse_args()
    logging.disable_progress_bar()
    if args.out.exists():
        shutil.rmtree(args.out)
    model = AutoModelForCausalLM.from_pretrained(args.model, dtype=torch.float32)
    merged = PeftModel.from_pretrained(model, args.adapter).merge_and_unload()
    merged.to(torch.bfloat16).save_pretrained(args.out)  # bfloat16, as the base model
    for source in sorted(args.model.iterdir()):
        if source.is_file() and source.name != WEIGHTS:
            shutil.copyfile(source, args.out / source.name)
    print(f"  merged   {args.adapter} into a copy of {args.model.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

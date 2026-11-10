"""A model whose build differs from pins.toml: ask before using it, never fail.

Ollama downloads a model by its tag, and the publisher can move the tag to a newer build at any
time; the older build cannot be downloaded any more. So a difference from the pin is expected
for users of an older checkout of this project. It is explained and, in a terminal, asked about
(default: yes); the answer is remembered in .runtime/settings.toml.
"""

from __future__ import annotations

from . import guide, ollama, settings
from .layout import Layout, Pins

DOCS = "https://niccokunzmann.github.io/satyrn-getting-started/reproducibility.html#when-a-model-has-changed"

CHANGED = """{model} has changed since this project tested and pinned it:
  pinned in pins.toml  {pinned}
  available now        {digest}
It is most likely a newer build of the same model, but satyrn has not been tested with it."""

AVOID = """To avoid this question:
  - answer yes once: satyrn remembers it for this installation,
  - update this project (git pull): newer versions pin tested builds, or
  - pin it yourself: set  "{model}" = "{digest}"  under [model.digests] in pins.toml,
    then run `satyrn check`.
Details: {docs}"""


def use_digest(layout: Layout, pins: Pins, model: str, digest: str, *, ask: bool, download: bool) -> bool:
    """May this build of ``model`` be used? Pinned, unpinned and accepted builds may."""
    pinned = pins.digest(model)
    if pinned is None:
        print(f'  note     {model} is not pinned; to pin it, add  "{model}" = "{digest}"  to [model.digests]')
        return True
    if digest == pinned:
        print(f"  verified {model} is the build pinned in pins.toml")
        return True
    if settings.accepted_digest(layout, model) == digest:
        print(f"  note     {model} differs from pins.toml; you accepted this build before")
        return True
    print(CHANGED.format(model=model, pinned=pinned, digest=digest))
    if not ask:
        print("Using it anyway (there is no terminal to ask in).")
        print(AVOID.format(model=model, digest=digest, docs=DOCS))
        return True
    if guide.ask_yes("Download and use it anyway?" if download else "Use it anyway?"):
        settings.accept_digest(layout, model, digest)
        print("Accepted for this installation; satyrn will not ask again for this build.")
        return True
    print(AVOID.format(model=model, digest=digest, docs=DOCS))
    return False


def pull(layout: Layout, pins: Pins, model: str, *, ask: bool) -> bool:
    """Download ``model`` unless the user declines a build that differs from the pin."""
    available = ollama.remote_digest(model)
    if available is not None and not use_digest(layout, pins, model, available, ask=ask, download=True):
        print(f"{model} was not downloaded.")
        return False
    with ollama.running(layout, pins):
        digest = ollama.pull(layout, pins, model)
    # Normally the build checked above; otherwise the registry could not be asked first.
    if digest != available and not use_digest(layout, pins, model, digest, ask=ask, download=False):
        print(f"{model} is downloaded but you chose not to use it; remove it with: satyrn ollama rm {model}")
        return False
    return True

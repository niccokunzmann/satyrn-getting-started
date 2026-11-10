"""Download pinned archives, verify sha256, unpack them (zip, tar.gz, tar.xz, tar.zst)."""

from __future__ import annotations

import hashlib
import shutil
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

from .layout import Asset

CHUNK = 1 << 20
STAMP = ".satyrn-installed"


class ChecksumError(Exception):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def download(asset: Asset, downloads: Path) -> Path:
    """Return a verified local copy of ``asset``, downloading it only if needed."""
    downloads.mkdir(parents=True, exist_ok=True)
    target = downloads / f"{asset.component}-{asset.version}-{asset.file}"
    if target.is_file() and sha256_file(target) == asset.sha256:
        print(f"  cached   {target.name} (sha256 ok)")
        return target
    partial = target.with_name(target.name + ".part")
    print(f"  download {asset.url}")
    with urllib.request.urlopen(asset.url) as response, partial.open("wb") as out:  # noqa: S310 - pinned https URL
        total = int(response.headers.get("Content-Length") or 0)
        done = 0
        while chunk := response.read(CHUNK):
            out.write(chunk)
            done += len(chunk)
            if total and sys.stderr.isatty():
                print(f"\r  {done * 100 // total:3d}% of {total >> 20} MB", end="", file=sys.stderr)
    if sys.stderr.isatty():
        print(file=sys.stderr)
    actual = sha256_file(partial)
    if actual != asset.sha256:
        partial.unlink()
        raise ChecksumError(f"{asset.file}: sha256 {actual} does not match pinned {asset.sha256}")
    partial.replace(target)
    print(f"  verified {target.name} (sha256 ok)")
    return target


def is_unpacked(destination: Path, sha256: str) -> bool:
    stamp = destination / STAMP
    return stamp.is_file() and stamp.read_text().strip() == sha256


def unpack(archive: Path, destination: Path, sha256: str) -> None:
    """Unpack ``archive`` into a fresh ``destination`` unless that exact archive is already there."""
    stamp = destination / STAMP
    if is_unpacked(destination, sha256):
        print(f"  present  {destination}")
        return
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    name = archive.name
    if name.endswith(".zip"):
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(destination)  # noqa: S202 - zipfile drops absolute and ".." member paths
    else:
        mode = "r:zst" if name.endswith(".zst") else "r:xz" if name.endswith(".xz") else "r:gz"
        with tarfile.open(archive, mode) as tf:
            tf.extractall(destination, filter="data")  # "data" filter blocks unsafe members
    stamp.write_text(sha256 + "\n")
    print(f"  unpacked {destination}")

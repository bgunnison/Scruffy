from __future__ import annotations

from pathlib import Path


def repo_root() -> Path:
    # src/util/paths.py -> src -> repo
    return Path(__file__).resolve().parents[2]


def src_root() -> Path:
    return repo_root() / "src"


def out_dir() -> Path:
    d = repo_root() / "out"
    d.mkdir(parents=True, exist_ok=True)
    return d


def adapter_dir() -> Path:
    return src_root() / "adapter"


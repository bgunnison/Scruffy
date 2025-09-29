from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv


def load_env(dotenv_path: str | Path | None = None) -> None:
    load_dotenv(dotenv_path if dotenv_path else None, override=False)


def get_env_str(key: str, default: str | None = None) -> str | None:
    return os.environ.get(key, default)


def require_env_str(key: str) -> str:
    val = os.environ.get(key)
    if not val:
        raise RuntimeError(f"Missing environment variable: {key}")
    return val


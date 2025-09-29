"""
Author: Brian Gunnison

Brief: Toggle and emit verbose logs of LLM prompts and responses.

Details: Global on/off flag with simple pretty logging used throughout planner
modules when debugging.
"""
# SPDX-License-Identifier: MIT
from __future__ import annotations

from typing import Any, Dict, List, Optional

from . import log

_VERBOSE: bool = False


def set_verbose(v: bool) -> None:
    global _VERBOSE
    _VERBOSE = bool(v)
    log.info(f"LLM verbose logging {'ENABLED' if _VERBOSE else 'disabled'}")


def is_verbose() -> bool:
    return _VERBOSE


def log_messages(label: str, messages: List[Dict[str, Any]], extra: Optional[Dict[str, Any]] = None) -> None:
    if not _VERBOSE:
        return
    log.info(f"LLM prompt → {label}")
    for m in messages:
        role = m.get("role")
        content = m.get("content")
        log.info(f"[{role}] {content}")
    if extra:
        for k, v in extra.items():
            log.info(f"[{label}:{k}] {v}")

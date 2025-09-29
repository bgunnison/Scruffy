"""
Author: Brian Gunnison

Brief: Launch the interactive 3D viewer in a separate process for a plan JSON.

Details: Spawns src/3dviewer.py with DF_VIEW_JSON/DF_VIEW_TITLE env vars so the
viewer window opens without blocking the main process.
"""
# SPDX-License-Identifier: MIT
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from src.util import log
from src.util.paths import repo_root


def _viewer_script_path() -> Path:
    p = repo_root() / "src" / "3dviewer.py"
    if not p.exists():
        raise FileNotFoundError(f"3dviewer.py not found at: {p}")
    return p


def run_pyviewer_preview(plan_path: Path, title: str | None = None) -> int:
    """Launch 3dviewer.py in a separate process for interactive preview.

    Does not wait; returns immediately after spawning the window.
    """
    try:
        viewer = _viewer_script_path()
    except FileNotFoundError as e:
        log.error(str(e))
        return 1

    env = dict(os.environ)
    try:
        abs_json = str(Path(plan_path).resolve())
    except Exception:
        abs_json = str(plan_path)
    env["DF_VIEW_JSON"] = abs_json
    if title:
        env["DF_VIEW_TITLE"] = title

    try:
        # Launch normally so the window appears immediately. Avoid pipes.
        kwargs = {"cwd": str(repo_root())}
        if os.name != "nt":
            # Start a new session on POSIX so closing the parent doesn't kill the window.
            kwargs["start_new_session"] = True

        subprocess.Popen(
            [sys.executable, str(viewer)],
            env=env,
            **kwargs,
        )
        # Do not wait; return success
        return 0
    except Exception as ex:
        log.error(f"Failed to launch 3d viewer: {ex}")
        return 2

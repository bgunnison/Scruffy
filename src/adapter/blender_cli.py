"""
Author: Brian Gunnison

Brief: Helpers to run Blender headless for animation/stills and open Blender GUI from a plan.

Details: Invokes src/adapter/blender_script.py with either animation, still, or
GUI-edit modes, using a detected or provided Blender executable path.
"""
# SPDX-License-Identifier: MIT
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

from src.util import log
from src.util.paths import adapter_dir


def run_blender_headless(plan_path: Path, out_mp4: Path, blender_path: Optional[Path]) -> int:
    script = adapter_dir() / "blender_script.py"
    if not script.exists():
        raise FileNotFoundError(f"Blender script not found: {script}")

    if blender_path is None:
        raise RuntimeError("BLENDER_PATH not set or not provided.")

    # Ensure directories exist
    out_mp4.parent.mkdir(parents=True, exist_ok=True)

    # Build command: blender -b -P script -- --plan plan.json --out out.mp4 --profile fast
    cmd = [
        str(blender_path),
        "-b",
        "-noaudio",
        "-P",
        str(script),
        "--",
        "--plan",
        str(plan_path),
        "--out",
        str(out_mp4),
        "--profile",
        "fast",
        "--render-mode",
        "animation",
    ]

    quiet = os.environ.get("TIMINGS_ONLY", "").lower() in ("1", "true", "on", "yes")
    if not quiet:
        log.info("Invoking Blender headless for fast preview...")
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    except FileNotFoundError:
        raise RuntimeError(f"Blender not found at: {blender_path}")

    if not quiet:
        # Stream summarized output
        out = proc.stdout or ""
        # Keep output short in CLI
        for line in out.splitlines()[-20:]:
            print(line)

        if proc.returncode != 0:
            log.error("Blender render failed")
        else:
            log.success(f"Blender render completed: {out_mp4}")
    return proc.returncode


def run_blender_still(plan_path: Path, out_png: Path, blender_path: Optional[Path]) -> int:
    script = adapter_dir() / "blender_script.py"
    if not script.exists():
        raise FileNotFoundError(f"Blender script not found: {script}")
    if blender_path is None:
        raise RuntimeError("BLENDER_PATH not set or not provided.")
    out_png.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(blender_path),
        "-b",
        "-noaudio",
        "-P",
        str(script),
        "--",
        "--plan",
        str(plan_path),
        "--out",
        str(out_png),
        "--profile",
        "fast",
        "--render-mode",
        "still",
    ]
    quiet = os.environ.get("TIMINGS_ONLY", "").lower() in ("1", "true", "on", "yes")
    if not quiet:
        log.info("Invoking Blender headless for still preview...")
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if not quiet:
        out = proc.stdout or ""
        for line in out.splitlines()[-20:]:
            print(line)
        if proc.returncode != 0:
            log.error("Blender still render failed")
        else:
            log.success(f"Blender still saved: {out_png}")
    return proc.returncode


def open_blender_gui(plan_path: Path, blender_path: Optional[Path]) -> int:
    script = adapter_dir() / "blender_script.py"
    if not script.exists():
        raise FileNotFoundError(f"Blender script not found: {script}")
    if blender_path is None:
        raise RuntimeError("BLENDER_PATH not set or not provided.")

    # First, build and save a temporary .blend in background to ensure GUI matches preview
    tmp_blend = plan_path.with_suffix('.blend')
    build_cmd = [
        str(blender_path),
        "-b",
        "-noaudio",
        "-P",
        str(script),
        "--",
        "--plan",
        str(plan_path),
        "--profile",
        "fast",
        "--render-mode",
        "none",
        "--save",
        str(tmp_blend),
    ]
    log.info("Preparing editable .blend from plan...")
    proc1 = subprocess.run(build_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if proc1.returncode != 0:
        log.error("Failed to prepare .blend for editing")
        return proc1.returncode

    # Then open Blender GUI with the saved .blend
    log.info("Opening Blender GUI for edits (close Blender to continue)...")
    try:
        proc2 = subprocess.run([str(blender_path), str(tmp_blend)])
        return proc2.returncode
    except FileNotFoundError:
        raise RuntimeError(f"Blender not found at: {blender_path}")

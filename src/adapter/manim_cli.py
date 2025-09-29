"""
Author: Brian Gunnison

Brief: CLI helpers to render a plan with Manim (optional preview path).

Details: Locates src/json2manim.py and executes still/animation rendering via
subprocess; requires Manim/OpenGL stack when used.
"""
# SPDX-License-Identifier: MIT
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

from src.util import log
from src.util.paths import repo_root


def _json2manim_path() -> Path:
    # json2manim.py is under src/
    p = repo_root() / "src" / "json2manim.py"
    if not p.exists():
        raise FileNotFoundError(f"json2manim.py not found at: {p}")
    return p


def run_manim_still(plan_path: Path, out_png: Path) -> int:
    script = _json2manim_path()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    quiet = os.environ.get("TIMINGS_ONLY", "").lower() in ("1", "true", "on", "yes")
    cmd = [
        sys.executable,
        str(script),
        "--plan",
        str(plan_path),
        "--out",
        str(out_png),
        "--mode",
        "still",
    ]
    if not quiet:
        log.info("Invoking Manim for still preview...")
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if not quiet:
        out = proc.stdout or ""
        for line in out.splitlines()[-20:]:
            print(line)
        if proc.returncode != 0:
            log.error("Manim still render failed. Install manim with: pip install manim")
        else:
            log.success(f"Manim still saved: {out_png}")
    return proc.returncode


def run_manim_animation(plan_path: Path, out_mp4: Path) -> int:
    script = _json2manim_path()
    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    quiet = os.environ.get("TIMINGS_ONLY", "").lower() in ("1", "true", "on", "yes")
    cmd = [
        sys.executable,
        str(script),
        "--plan",
        str(plan_path),
        "--out",
        str(out_mp4),
        "--mode",
        "animation",
    ]
    if not quiet:
        log.info("Invoking Manim for animation...")
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if not quiet:
        out = proc.stdout or ""
        for line in out.splitlines()[-20:]:
            print(line)
        if proc.returncode != 0:
            log.error("Manim animation render failed. Install manim with: pip install manim")
        else:
            log.success(f"Manim MP4 saved: {out_mp4}")
    return proc.returncode


def run_manim_preview(plan_path: Path) -> int:
    script = _json2manim_path()
    # Always run preview quietly (no extra logs); window itself is interactive
    quiet = True
    # Ensure no headless OpenGL is forced
    env = dict(os.environ)
    for k in ("PYOPENGL_PLATFORM", "MANIM_RENDERER_OPENGL_HEADLESS"):
        if k in env:
            env.pop(k)
    cmd = [
        sys.executable,
        str(script),
        "--plan",
        str(plan_path),
        "--mode",
        "preview",
    ]
    # Do not pipe stdio; let Manim manage its own OpenGL window/event loop
    proc = subprocess.run(cmd, env=env)
    # Only print on error
    if proc.returncode != 0:
        log.error("Manim preview failed. Install manim with: pip install manim")
    return proc.returncode

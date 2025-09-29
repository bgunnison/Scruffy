"""
Author: Brian Gunnison

Brief: Render a DreamFast plan JSON with Manim (optional preview path).

Details: Builds simple Manim 3D primitives from a plan, supports still/animation
outputs, and a preview mode (OpenGL). Requires Manim and its OpenGL stack.

Usage:
  python json2manim.py --plan path/to/plan.json --out out.png --mode still
  python json2manim.py --plan path/to/plan.json --out out.mp4 --mode animation
"""
# SPDX-License-Identifier: MIT

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
import os as _os

import numpy as np
from manim import (
    ThreeDScene,
    Cube,
    Sphere,
    Cylinder,
    Cone,
    Rectangle,
    config,
    DEGREES,
    RIGHT,
    UP,
    OUT,
    tempconfig,
)
from manim import logger as _manim_logger
import logging as _logging


def _as_floats(vals):
    return [float(x) for x in vals]


def rgb01(c):
    """Normalize JSON color to (r,g,b) in 0..1.
       Accepts dict {r,g,b} (0..1 or 0..255) or list/tuple."""
    if isinstance(c, dict):
        r, g, b = _as_floats([c.get("r", 0.8), c.get("g", 0.8), c.get("b", 0.8)])
    else:
        seq = list(c) if c is not None else [0.8, 0.8, 0.8]
        r, g, b = _as_floats(seq[:3] + [0.8] * (3 - len(seq)))
    if max(r, g, b) > 1.0:
        r, g, b = r / 255.0, g / 255.0, b / 255.0
    return r, g, b


def rgb_to_hex(c):
    r, g, b = rgb01(c)
    return f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"


def build_mobject(o):
    typ = str(o.get("type", "")).lower()
    dims = [float(x) for x in o.get("dimensions", [1, 1, 1])]
    t = o.get("transform", {})
    rdeg = t.get("rotation_degrees", [0, 0, 0])
    rx, ry, rz = [float(a) * DEGREES for a in (rdeg + [0, 0, 0])[:3]]
    pos = np.array(t.get("location", [0, 0, 0]), dtype=float)
    col_hex = rgb_to_hex(o.get("color", {"r": 0.8, "g": 0.8, "b": 0.8}))

    # Match Blender semantics: dims are overall extents; Blender primitives default to ~2 units per axis
    if typ == "cube":
        # Start with side_length=2 so initial extents are 2 on each axis
        m = Cube(2.0).set_fill(color=col_hex, opacity=1.0).set_stroke(width=0)
        m.stretch(dims[0] / 2.0, 0)
        m.stretch(dims[1] / 2.0, 1)
        m.stretch(dims[2] / 2.0, 2)
    elif typ == "sphere":
        # Start with radius=1 (extents 2) and stretch per-axis to allow ellipsoids
        m = Sphere(radius=1.0).set_fill(color=col_hex, opacity=1.0).set_stroke(width=0)
        m.stretch(dims[0] / 2.0, 0)
        m.stretch(dims[1] / 2.0, 1)
        m.stretch(dims[2] / 2.0, 2)
    elif typ == "cylinder":
        # Canonical cylinder: radius=1, height=2 (extents x=y=2, z=2), then stretch to dims
        m = Cylinder(radius=1.0, height=2.0).set_fill(color=col_hex, opacity=1.0).set_stroke(width=0)
        m.stretch(dims[0] / 2.0, 0)
        m.stretch(dims[1] / 2.0, 1)
        m.stretch(dims[2] / 2.0, 2)
    elif typ == "cone":
        # Canonical cone: base radius=1, height=2, then stretch to dims
        try:
            m = Cone(base_radius=1.0, height=2.0).set_fill(color=col_hex, opacity=1.0).set_stroke(width=0)
        except Exception:
            m = Cylinder(radius=1.0, height=2.0).set_fill(color=col_hex, opacity=1.0).set_stroke(width=0)
        m.stretch(dims[0] / 2.0, 0)
        m.stretch(dims[1] / 2.0, 1)
        m.stretch(dims[2] / 2.0, 2)
    elif typ == "plane":  # zero thickness in XY
        w = dims[0]
        h = dims[1] if len(dims) > 1 else dims[0]
        # Start with 2x2 plane, then stretch to desired size
        m = Rectangle(width=2.0, height=2.0).set_fill(color=col_hex, opacity=1.0).set_stroke(width=0)
        m.stretch(w / 2.0, 0)
        m.stretch(h / 2.0, 1)
    else:
        return None

    return (
        m.rotate(rx, axis=RIGHT)
        .rotate(ry, axis=UP)
        .rotate(rz, axis=OUT)
        .shift(pos)
    )


def load_json(path: str | os.PathLike[str]):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


class SceneFromJSON(ThreeDScene):
    def __init__(self, scene_data: dict, preview_mode: bool = False, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._scene_data = scene_data
        self._preview_mode = preview_mode

    def construct(self):
        data = self._scene_data
        positions: list[np.ndarray] = []
        dims_list: list[np.ndarray] = []
        objs = data.get("objects", [])
        for o in objs:
            m = build_mobject(o)
            if m:
                self.add(m)
            # Collect stats for auto-framing
            t = o.get("transform", {})
            pos = np.array(t.get("location", [0, 0, 0]), dtype=float)
            positions.append(pos)
            dims = np.array([float(x) for x in o.get("dimensions", [1, 1, 1])], dtype=float)
            dims_list.append(dims)
        # Camera
        cam = data.get("camera", {})
        rot = cam.get("transform", {}).get("rotation_degrees")
        if rot and len(rot) >= 2:
            phi = float(rot[0])
            theta = float(rot[2] if len(rot) >= 3 else rot[1])
            self.move_camera(phi=phi * DEGREES, theta=theta * DEGREES, animate=False)
        else:
            self.move_camera(phi=65 * DEGREES, theta=45 * DEGREES, distance=10, animate=False)
        # Auto-frame: center on average position and set distance based on spread
        if positions:
            center = np.mean(np.stack(positions, axis=0), axis=0)
            # Approximate radius: max distance to center + half of dims magnitude
            import math as _m
            r = 0.0
            for p, d in zip(positions, dims_list):
                dist = _m.sqrt(float(((p - center) ** 2).sum()))
                sc = float(np.abs(d).sum()) / 2.0
                r = max(r, dist + sc)
            r = max(r, 1.5)
            d_cam = max(6.0, 2.5 * r)
            self.move_camera(frame_center=(float(center[0]), float(center[1]), float(center[2])), distance=d_cam, animate=False)
        if getattr(self, "_preview_mode", False):
            # Keep the window open; allow user to rotate/zoom in OpenGL preview
            # Use a long wait to keep the interactive window alive until closed
            self.wait(3600)
        else:
            # Advance by a single frame so Manim can render (must be > 0)
            fps = int(getattr(config, "frame_rate", 24) or 24)
            dt = 1.0 / max(1, fps)
            self.wait(dt)


def _find_last_frame_image(media_dir: Path) -> Path | None:
    # Manim writes images under media_dir/images/<SceneName>/<file>.png
    images_root = media_dir / "images"
    if not images_root.exists():
        return None
    latest: Path | None = None
    for root, _dirs, files in os.walk(images_root):
        for f in files:
            if f.lower().endswith((".png", ".jpg", ".jpeg")):
                p = Path(root) / f
                if (latest is None) or (p.stat().st_mtime > latest.stat().st_mtime):
                    latest = p
    return latest


def _find_movie(media_dir: Path) -> Path | None:
    # Manim writes movies under media_dir/videos/<module>/<quality>/<file>.mp4
    videos_root = media_dir / "videos"
    if not videos_root.exists():
        return None
    latest: Path | None = None
    for root, _dirs, files in os.walk(videos_root):
        for f in files:
            if f.lower().endswith((".mp4", ".mov", ".webm")):
                p = Path(root) / f
                if (latest is None) or (p.stat().st_mtime > latest.stat().st_mtime):
                    latest = p
    return latest


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", required=True, help="Path to DreamFast ScenePlan JSON")
    ap.add_argument("--out", required=False, help="Output path (.png for still, .mp4 for animation)")
    ap.add_argument("--mode", choices=["still", "animation", "preview"], default="still")
    args = ap.parse_args(argv)

    plan_path = Path(args.plan)
    if not plan_path.exists():
        print(f"[MANIM] Plan not found: {plan_path}", file=sys.stderr)
        return 2
    data = load_json(plan_path)

    # Extract basic render config
    r = data.get("render", {})
    bg_hex = rgb_to_hex(r.get("background_color", {"r": 0.0, "g": 0.0, "b": 0.0}))
    width = int(r.get("resolution_x", 1280))
    height = int(r.get("resolution_y", 720))
    fps = int(r.get("fps", 24))

    tmp_media = Path(tempfile.mkdtemp(prefix="manim_media_"))
    out_path = Path(args.out) if args.out else None

    quiet = (_os.environ.get("TIMINGS_ONLY", "").lower() in ("1", "true", "on", "yes"))
    # Reduce Manim's own logging in quiet/preview mode
    if quiet or args.mode == "preview":
        _os.environ.setdefault("MANIM_LOG_LEVEL", "ERROR")
        _os.environ.setdefault("MANIM_PROGRESS_BAR", "none")
        try:
            _manim_logger.setLevel(_logging.ERROR)
            _logging.getLogger("manim").setLevel(_logging.ERROR)
        except Exception:
            pass

    cfg = {
        "renderer": "opengl",
        "pixel_width": width,
        "pixel_height": height,
        "background_color": bg_hex,
        "frame_rate": fps,
        "media_dir": str(tmp_media),
        "disable_caching": True,
    }

    if args.mode == "still":
        cfg["save_last_frame"] = True
        cfg["write_to_movie"] = False
    elif args.mode == "animation":
        cfg["write_to_movie"] = True
        cfg["movie_file_extension"] = ".mp4"
    else:  # preview
        cfg["write_to_movie"] = False
        cfg["save_last_frame"] = False
    # Silence progress bar when quiet or preview
    if quiet or args.mode == "preview":
        cfg["progress_bar"] = "none"

    # Extra diagnostics for preview mode
    if args.mode == "preview":
        try:
            import manim as _m
            import moderngl as _mgl
            import moderngl_window as _mglw
            import pyglet as _pyg
            print(
                f"[json2manim] manim={getattr(_m, '__version__', 'unknown')} moderngl={getattr(_mgl, '__version__', 'unknown')} "
                f"moderngl_window={getattr(_mglw, '__version__', 'unknown')} pyglet={getattr(_pyg, '__version__', 'unknown')}"
            )
        except Exception as e:
            print(f"[json2manim] Package diagnostics error: {e}")
        print(
            f"[json2manim] env: PYOPENGL_PLATFORM={_os.environ.get('PYOPENGL_PLATFORM')} "
            f"MANIM_RENDERER_OPENGL_HEADLESS={_os.environ.get('MANIM_RENDERER_OPENGL_HEADLESS')}"
        )
    try:
        with tempconfig(cfg):
            if quiet or args.mode == "preview":
                try:
                    config.progress_bar = "none"
                    # Hint to always show a window
                    setattr(config, "preview", True)
                except Exception:
                    pass
                try:
                    print(
                        f"[json2manim] renderer={getattr(config, 'renderer', None)} write_to_movie={getattr(config, 'write_to_movie', None)} "
                        f"save_last_frame={getattr(config, 'save_last_frame', None)} progress_bar={getattr(config, 'progress_bar', None)}"
                    )
                except Exception:
                    pass
            SceneFromJSON(scene_data=data, preview_mode=(args.mode == "preview")).render()
    except Exception as e:
        print(f"[MANIM] Render failed: {e}", file=sys.stderr)
        return 1

    # Move artifact to requested output
    if out_path is not None:
        try:
            if args.mode == "still":
                src = _find_last_frame_image(tmp_media)
            else:
                src = _find_movie(tmp_media)
            if not src:
                print("[MANIM] Could not locate output artifact.", file=sys.stderr)
                return 3
            out_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, out_path)
            if not quiet:
                # Avoid non-ASCII to prevent Windows console encoding errors
                print(f"[MANIM] Saved -> {out_path}")
        except Exception as e:
            print(f"[MANIM] Failed to save output: {e}", file=sys.stderr)
            return 4

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

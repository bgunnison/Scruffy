"""
Author: Brian Gunnison

Brief: Normalize and clamp ScenePlan values for fast, safe previews.

Details: Applies bounds, defaults, and rejects unsupported operations to keep
renders predictable and performant.
"""
# SPDX-License-Identifier: MIT
from __future__ import annotations

from typing import List
from src.planner.structured_plan import ScenePlan, ObjectSpec, CameraSpec, Color


SUPPORTED = {"cube", "sphere", "cylinder", "cone", "plane", "torus"}


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(v)))


def _clamp_vec(vals: List[float], lo: float, hi: float, length: int) -> List[float]:
    arr = list(vals) + [0.0] * max(0, length - len(vals))
    return [
        _clamp(arr[i], lo, hi) for i in range(length)
    ]


def normalize_plan(plan: ScenePlan) -> ScenePlan:
    # Clamp render settings
    r = plan.render
    r.duration_seconds = _clamp(r.duration_seconds, 0.5, 5.0)
    r.fps = int(_clamp(float(r.fps), 12, 60))
    r.resolution_x = int(_clamp(float(r.resolution_x), 320, 1920))
    r.resolution_y = int(_clamp(float(r.resolution_y), 180, 1080))
    # background_color already clamps by Color model
    plan.render = r

    # Camera defaults
    cam = plan.camera or CameraSpec()
    cam.transform.location = _clamp_vec(cam.transform.location, -100, 100, 3)
    cam.transform.rotation_degrees = _clamp_vec(cam.transform.rotation_degrees, -360, 360, 3)
    cam.transform.scale = _clamp_vec(cam.transform.scale, 0.05, 50, 3)
    plan.camera = cam

    # Objects normalization
    objs: List[ObjectSpec] = []
    for o in plan.objects:
        if o.type not in SUPPORTED:
            # reject unsupported ops
            continue
        o.transform.location = _clamp_vec(o.transform.location, -100, 100, 3)
        o.transform.rotation_degrees = _clamp_vec(o.transform.rotation_degrees, -360, 360, 3)
        o.transform.scale = _clamp_vec(o.transform.scale, 0.05, 50, 3)
        o.dimensions = _clamp_vec(o.dimensions, 0.05, 50, 3)
        # Heuristic: keep planes horizontal to serve as ground/water
        if o.type == "plane":
            o.transform.rotation_degrees = [0.0, 0.0, 0.0]
            # snap close-to-zero Z to exactly 0 for stability
            if abs(o.transform.location[2]) < 0.01:
                o.transform.location[2] = 0.0
        # Color model clamps itself
        objs.append(o)

    # Ensure at least one object exists
    if not objs:
        objs = [
            ObjectSpec(
                name="DefaultCube",
                type="cube",
                color=Color(r=0.6, g=0.7, b=0.9),
                dimensions=[1, 1, 1],
            )
        ]
    plan.objects = objs
    return plan

from __future__ import annotations

import json
import time
from pathlib import Path
from datetime import datetime
import re
from typing import List, Dict, Any, Optional, Tuple
import sys

from src.util import log
from src.util.env import load_env, get_env_str
from src.util.paths import out_dir, repo_root
from src.util.blender_path import ensure_blender_path
from src.planner.semantic_filter import semantic_filter_with_openai
from src.planner.llm_kitbash import synthesize_kitbash
from src.planner.structured_plan import ScenePlan
from src.validate.normalizer import normalize_plan
from src.adapter.blender_cli import run_blender_still, open_blender_gui
from src.adapter.pyviewer_cli import run_pyviewer_preview


def _prim_nice_name(t: str) -> str:
    t = (t or "").strip().lower()
    return {
        "cube": "Box",
        "sphere": "Sphere",
        "cylinder": "Cylinder",
        "cone": "Cone",
        "plane": "Plane",
        "torus": "Torus",
    }.get(t, t.title() or "Part")


def _clean_part_name(n: str, prefix: str) -> str:
    s = str(n or "").strip()
    if prefix and s.lower().startswith((prefix or "").strip().lower() + "_"):
        s = s[len(prefix)+1:]
    s = s.replace("_", " ").strip()
    return s[:1].upper() + s[1:] if s else "Part"


def _max_parts_for(reality_factor: int) -> int:
    # Direct mapping: rf = max parts (clamped 1..100). rf=0 handled as placeholder elsewhere.
    rf_int = int(reality_factor)
    return max(1, min(rf_int, 100))


def _build_object_plan(object_entry: Dict[str, Any], rf: int, max_parts: int) -> Tuple[ScenePlan, List[Tuple[str, str]]]:
    # Determine a preferred color if provided by the object
    parts = []
    preferred_color = None
    c = object_entry.get("color") if isinstance(object_entry, dict) else None
    if isinstance(c, dict) and all(k in c for k in ("r", "g", "b")):
        try:
            preferred_color = {"r": float(c["r"]), "g": float(c["g"]), "b": float(c["b"]) }
        except Exception:
            preferred_color = None
    # Placeholder: single box colored if possible
    if rf <= 0:
        plan = normalize_plan(ScenePlan(
            description=f"placeholder for {object_entry.get('name','Object')}",
            objects=[{
                "name": f"{object_entry.get('name','Object')}_Cube",
                "type": "cube",
                "dimensions": [1, 1, 1],
                "transform": {"location": [0, 0, 0.5]},
                "color": preferred_color or {"r": 0.7, "g": 0.7, "b": 0.7},
            }],
        ))
        comps = [("Body", "Box")]
        return plan, comps

    # Synthesize kitbash for a single object
    kb = synthesize_kitbash([object_entry], reality_factor=rf)
    comps: List[Tuple[str, str]] = []
    # max_parts provided by caller; already capped if needed

    for entry in kb:
        prefix = entry.get("name") or object_entry.get("name") or "Object"
        for part in entry.get("parts", [])[:max_parts]:
            comps.append((_clean_part_name(part.get('name', 'Part'), prefix), _prim_nice_name(part.get("type", "part"))))
            parts.append({
                "name": f"{prefix}_{part.get('name','Part')}",
                "type": part["type"],
                "dimensions": part.get("dimensions", [1, 1, 1]),
                "transform": {
                    "location": part.get("location", [0, 0, 0]),
                    "rotation_degrees": part.get("rotation_degrees", [0, 0, 0]),
                    "scale": [1, 1, 1],
                },
                "color": preferred_color or part.get("color", {"r": 0.7, "g": 0.7, "b": 0.7}),
            })
    if not parts:
        # fallback simple cube
        parts = [{
            "name": f"{object_entry.get('name','Object')}_Cube",
            "type": "cube",
            "dimensions": [1, 1, 1],
            "transform": {"location": [0, 0, 0.5]},
            "color": {"r": 0.7, "g": 0.7, "b": 0.7},
        }]
        if not comps:
            comps = [("Body", "Box")]

    plan = ScenePlan(
        description=f"kitbash for {object_entry.get('name','Object')}",
        objects=parts,
    )
    return normalize_plan(plan), comps


def _ask_yes_no(question: str, default: bool = True) -> bool:
    yn = "Y/n" if default else "y/N"
    try:
        ans = input(f"{question} [{yn}]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return default
    if not ans:
        return default
    return ans in ("y", "yes")


def iterative(prompt: str, approve: bool = True) -> None:
    """Iterative flow: extract objects → approve → per-object kitbash → per-object still preview → optional edits."""
    load_env()
    timings_only = (get_env_str("TIMINGS_ONLY", "") or "").lower() in ("1", "true", "on", "yes")
    backend = (get_env_str("RENDER_BACKEND", "python") or "python").lower()
    blender_path = None
    if backend == "blender":
        blender_path = ensure_blender_path(interactive=True)
        if not blender_path:
            log.error("Blender not configured; cannot proceed.")
            return

    if not timings_only:
        print("Extracting objects")
    _t0_extract = time.perf_counter()
    objects, actions, paths = semantic_filter_with_openai(prompt)
    # Deduplicate objects defensively (by normalized name, fallback to category)
    def _norm_name(n: str) -> str:
        s = (n or "").strip().lower()
        # naive singular: drop trailing 's' for plurals like 'books'
        if len(s) > 3 and s.endswith('s'):
            s = s[:-1]
        return s
    uniq = []
    seen = set()
    for o in objects:
        nm = _norm_name(str(o.get('name') or ''))
        cat = (o.get('category') or '').strip().lower()
        key = nm or cat
        if key and key not in seen:
            seen.add(key)
            uniq.append(o)
    objects = uniq
    _dt_extract = time.perf_counter() - _t0_extract
    print(f"AI took {_dt_extract:.1f} seconds to extract objects")
    if not objects:
        log.error("No objects found by the AI. Refine your prompt and try again.")
        return

    # Show found objects (no categories; no approval prompt)
    if not timings_only:
        print("\nObjects detected:")
        for i, o in enumerate(objects, 1):
            print(f"  {i}. {o.get('name')}")

    # Use all detected objects; no selection prompt
    approved: List[Dict[str, Any]] = list(objects)

    if not approved:
        log.error("No objects selected. Aborting.")
        return

    run_root = out_dir()
    run_dir = run_root / "iterative"
    run_dir.mkdir(parents=True, exist_ok=True)

    finalized_parts: List[Dict[str, Any]] = []

    def _sanitize(name: str) -> str:
        base = re.sub(r"[^A-Za-z0-9]+", "", name).lower()
        return base or "object"

    total_plan_time = 0.0
    total_json_time = 0.0
    total_render_time = 0.0

    # Determine reality/cap once for this run
    try:
        rf_env = get_env_str("REALITY_FACTOR", "") or ""
        rf = int(float(rf_env)) if rf_env.strip() else 5
    except Exception:
        rf = 5
    max_parts = _max_parts_for(rf)
    try:
        cap_env = (get_env_str("KITBASH_MAX_PARTS", "") or "").strip()
        if cap_env:
            cap = max(1, int(float(cap_env)))
            max_parts = min(max_parts, cap)
    except Exception:
        pass

    # Prepare sketches directory (repo-root/sketches) for reusable object JSONs
    sketches_dir = repo_root() / "sketches"
    sketches_dir.mkdir(parents=True, exist_ok=True)

    for idx, obj in enumerate(approved, 1):
        if not timings_only:
            print(f"\nCreating {obj.get('name')} sketch")
        # Build plan and render (if selected backend)
        _t0_plan = time.perf_counter()
        # reality_factor can be controlled via env REALITY_FACTOR (1..10)
        plan, comps = _build_object_plan(obj, rf=rf, max_parts=max_parts)
        _dt_plan = time.perf_counter() - _t0_plan
        total_plan_time += _dt_plan
        obj_name_raw = str(obj.get('name') or f'object{idx:02d}')
        obj_name = _sanitize(obj_name_raw)
        if not timings_only:
            print(f"AI took {_dt_plan:.1f} seconds to sketch '{obj_name.lower()}'")
            if comps:
                print("Components:")
                for i, (cname, ctype) in enumerate(comps, 1):
                    print(f"  {i}. {cname}: {ctype}")
        base = _sanitize(str(obj.get('name') or f'object{idx:02d}'))
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        stem = f"{base}_{ts}"
        # Save sketch JSON under repo-root/sketches for reuse
        plan_json = sketches_dir / f"{stem}.json"
        _t0_json = time.perf_counter()
        with plan_json.open("w", encoding="utf-8") as f:
            json.dump(plan.model_dump(mode="json"), f, indent=2)
        _dt_json = time.perf_counter() - _t0_json
        total_json_time += _dt_json

        # Open an interactive 3D viewer window for this object (non-blocking)
        try:
            title = f"{obj.get('name') or f'object{idx:02d}'} (reality={rf})"
            rc_view = run_pyviewer_preview(plan_json, title=title)
            if rc_view != 0:
                log.warn("Could not open 3D preview window for this object.")
        except Exception:
            log.warn("Viewer launch failed; continuing.")

        if backend == "blender":
            still_path = run_dir / f"{stem}.png"
            _t0_render = time.perf_counter()
            rc = run_blender_still(plan_json, still_path, blender_path)
            _dt_render = time.perf_counter() - _t0_render
            total_render_time += _dt_render
            if rc != 0 and not timings_only:
                log.warn("Still render failed; continuing")
            elif not timings_only:
                print(f"Preview image: {still_path}")
            print(f"Rendered {still_path} in {_dt_render:.1f} seconds")
        else:
            # No Blender render in non-blender backend
            pass

        # Optionally open for edits, only when Blender is the renderer
        if backend == "blender" and approve and _ask_yes_no("Open in Blender to tweak this object?", default=False):
            rc = open_blender_gui(plan_json, blender_path)
            if rc != 0:
                log.warn("Blender GUI exited with a non-zero status.")

        finalized_parts.extend(plan.objects)

    # Build a combined plan (no complex animation here; user can run the main CLI for full render)
    combined = ScenePlan(
        description=f"Iterative build for: {prompt}",
        objects=finalized_parts,
    )
    combined = normalize_plan(combined)
    combined_json = run_dir / "combined_plan.json"
    with combined_json.open("w", encoding="utf-8") as f:
        json.dump(combined.model_dump(mode="json"), f, indent=2)

    # Emit totals only when timings_only is enabled
    if timings_only:
        print(
            f"Totals — AI object extraction: {_dt_extract:.3f}s, AI objects to model: {total_plan_time:.3f}s, rendering: {total_render_time:.3f}s"
        )

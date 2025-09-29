"""
Author: Brian Gunnison

Brief: Interactive pyrender/trimesh viewer for JSON primitive scenes (orbit/pan/zoom).

Details: Loads a plan/kitbash JSON, builds meshes (cube/sphere/cylinder/cone/plane/torus),
auto-frames a camera, and opens an interactive window. Often launched via
src.adapter.pyviewer_cli.
"""
# SPDX-License-Identifier: MIT

# json3d_viewer.py
# Interactive viewer for "primitives + transforms" JSON (mouse orbit/pan/zoom).
# Usage:  python src/3dviewer.py

import argparse, json, sys, os, re
import numpy as _np
# --- NumPy 2.0 compat for pyrender (expects np.infty) ---
if not hasattr(_np, "infty"):
    _np.infty = _np.inf

import numpy as np
import trimesh
import pyrender
from trimesh.transformations import euler_matrix, translation_matrix

file_name = r"C:\projects\scruffy\out\iterative\pig01.json"
# Optional override without CLI args: set DF_VIEW_JSON to a JSON path
ENV_JSON_KEY = "DF_VIEW_JSON"
ENV_TITLE_KEY = "DF_VIEW_TITLE"

# ---------- helpers ----------
def rgb01(c):
    if isinstance(c, dict):
        r, g, b = float(c.get("r", 0.8)), float(c.get("g", 0.8)), float(c.get("b", 0.8))
    else:
        r, g, b = [float(x) for x in (c or (0.8, 0.8, 0.8))[:3]]
    if max(r, g, b) > 1.0: r, g, b = r/255.0, g/255.0, b/255.0
    return r, g, b

def rgb255(c):
    r, g, b = rgb01(c)
    return np.array([int(r*255), int(g*255), int(b*255), 255], dtype=np.uint8)

def scale_matrix(sx, sy, sz):
    S = np.eye(4); S[0,0], S[1,1], S[2,2] = sx, sy, sz
    return S

def look_at(eye, target, up=(0,0,1)):
    eye, target, up = np.array(eye, float), np.array(target, float), np.array(up, float)
    f = target - eye
    f = f / max(np.linalg.norm(f), 1e-9)
    u = up / max(np.linalg.norm(up), 1e-9)
    s = np.cross(f, u)
    s = s / max(np.linalg.norm(s), 1e-9)
    u2 = np.cross(s, f)
    # For pyrender: pose is camera-to-world, with columns as basis vectors
    M = np.eye(4)
    M[:3, 0] = s
    M[:3, 1] = u2
    M[:3, 2] = -f
    M[:3, 3] = eye
    return M

# ---------- mesh builders ----------
def make_mesh(obj):
    typ  = str(obj["type"]).lower()
    dims = obj.get("dimensions", [])
    col  = rgb255(obj.get("color", {"r": 200, "g": 200, "b": 200}))

    if   typ == "cube":
        mesh = trimesh.creation.box(extents=[dims[0], dims[1], dims[2]])
    elif typ == "sphere":
        # Interpret dims as [sx, sy, sz] (ellipsoid). If only one given, it's radius.
        if len(dims) == 1:
            mesh = trimesh.creation.icosphere(subdivisions=3, radius=float(dims[0]))
        else:
            mesh = trimesh.creation.icosphere(subdivisions=3, radius=1.0)
            mesh.apply_transform(scale_matrix(dims[0], dims[1], dims[2]))
    elif typ == "cylinder":
        r = float(dims[0]); h = float(dims[2] if len(dims) > 2 else dims[1])
        mesh = trimesh.creation.cylinder(radius=r, height=h, sections=64)
    elif typ == "cone":
        # dims: [radius, ?, height] or [radius, height]
        r = float(dims[0]); h = float(dims[2] if len(dims) > 2 else dims[1])
        mesh = trimesh.creation.cone(radius=r, height=h, sections=64)
    elif typ == "plane":
        w, h = float(dims[0]), float(dims[1]); t = float(dims[2]) if len(dims)>2 else 0.01
        mesh = trimesh.creation.box(extents=[w, h, max(t, 1e-3)])
    elif typ == "torus":
        # Interpret dims as [major_diameter_x, major_diameter_y, thickness]
        # Use average of X/Y for a round torus; thickness as minor diameter
        R = float((dims[0] + (dims[1] if len(dims) > 1 else dims[0])) / 2.0) * 0.5
        r = float((dims[2] if len(dims) > 2 else max(0.1, 0.2 * (dims[0] or 1.0)))) * 0.5

        def _parametric_torus(R: float, r: float, seg_u: int = 64, seg_v: int = 32) -> trimesh.Trimesh:
            import math
            seg_u = max(8, int(seg_u))
            seg_v = max(6, int(seg_v))
            verts = []
            for i in range(seg_u):
                u = 2.0 * math.pi * (i / seg_u)
                cu, su = math.cos(u), math.sin(u)
                for j in range(seg_v):
                    v = 2.0 * math.pi * (j / seg_v)
                    cv, sv = math.cos(v), math.sin(v)
                    x = (R + r * cv) * cu
                    y = (R + r * cv) * su
                    z = r * sv
                    verts.append([x, y, z])
            faces = []
            def vid(i, j):
                return (i % seg_u) * seg_v + (j % seg_v)
            for i in range(seg_u):
                for j in range(seg_v):
                    a = vid(i, j)
                    b = vid(i + 1, j)
                    c = vid(i + 1, j + 1)
                    d = vid(i, j + 1)
                    faces.append([a, b, c])
                    faces.append([a, c, d])
            return trimesh.Trimesh(vertices=_np.array(verts, dtype=float), faces=_np.array(faces, dtype=int), process=False)

        try:
            if hasattr(trimesh.creation, "torus"):
                mesh = trimesh.creation.torus(major_radius=R, minor_radius=r, sections=64)
            else:
                mesh = _parametric_torus(R, r)
        except Exception:
            mesh = _parametric_torus(R, r)
    else:
        return None

    mesh.visual.vertex_colors = np.tile(col, (len(mesh.vertices), 1))

    tr = obj.get("transform", {})
    loc = tr.get("location", [0,0,0])
    rot = tr.get("rotation_degrees", [0,0,0])
    T = translation_matrix(loc) @ euler_matrix(
        np.deg2rad(rot[0]), np.deg2rad(rot[1]), np.deg2rad(rot[2]), "sxyz"
    )
    mesh.apply_transform(T)
    return mesh

def _load_json_lenient(path: str):
    """Load JSON, allowing C/CPP-style comments. Falls back to strict on success."""
    with open(path, "r", encoding="utf-8") as f:
        txt = f.read()
    try:
        return json.loads(txt)
    except Exception:
        pass
    # Strip /* ... */ and // ... comments, then retry
    try:
        no_block = re.sub(r"/\*.*?\*/", "", txt, flags=re.S)
        no_line = re.sub(r"(^|\s)//.*?$", "", no_block, flags=re.M)
        return json.loads(no_line)
    except Exception:
        # Re-raise original strict error for clearer tracebacks
        return json.loads(txt)


def _flatten_kitbash_if_needed(data: dict) -> dict:
    """Accept kitbash JSON shape ({objects:[{name, parts:[...] }], meta}) and
    convert to viewer objects list with transform blocks.
    """
    if not isinstance(data, dict):
        return data
    objs = data.get("objects")
    if not isinstance(objs, list):
        return data
    has_parts = False
    for o in objs:
        if isinstance(o, dict) and isinstance(o.get("parts"), list):
            has_parts = True
            break
    if not has_parts:
        return data

    out_objects = []
    for o in objs:
        base = (o.get("name") or "object").strip() if isinstance(o, dict) else "object"
        parts = (o.get("parts") if isinstance(o, dict) else None) or []
        for p in parts:
            if not isinstance(p, dict):
                continue
            col = p.get("color")
            if isinstance(col, list) and len(col) >= 3:
                try:
                    col = {"r": float(col[0]), "g": float(col[1]), "b": float(col[2])}
                except Exception:
                    col = None
            tr = {
                "location": p.get("location", [0, 0, 0]),
                "rotation_degrees": p.get("rotation_degrees", [0, 0, 0]),
                "scale": [1, 1, 1],
            }
            out_objects.append({
                "name": f"{base}_{p.get('name','part')}",
                "type": p.get("type", "cube"),
                "dimensions": p.get("dimensions", [1, 1, 1]),
                "transform": tr,
                "color": col or {"r": 0.7, "g": 0.7, "b": 0.7},
            })

    # Preserve render settings if present; else provide a minimal default
    render = data.get("render") if isinstance(data.get("render"), dict) else {
        "resolution_x": 1280,
        "resolution_y": 720,
        "background_color": {"r": 0.05, "g": 0.08, "b": 0.12},
    }
    return {"objects": out_objects, "render": render}


def load_scene(json_path):
    data = _load_json_lenient(json_path)
    data = _flatten_kitbash_if_needed(data)
    bg = rgb01(data.get("render", {}).get("background_color", {"r":12,"g":12,"b":18}))
    scene = pyrender.Scene(bg_color=[bg[0], bg[1], bg[2], 1.0])

    meshes = []
    for obj in data.get("objects", []):
        m = make_mesh(obj)
        if m is not None:
            meshes.append(m)
            scene.add(pyrender.Mesh.from_trimesh(m, smooth=False))

    # Auto-frame camera
    if meshes:
        all_bounds = np.vstack([m.bounds for m in meshes])  # (2N,3)
        mins, maxs = all_bounds[::2].min(axis=0), all_bounds[1::2].max(axis=0)
        center = (mins + maxs) * 0.5
        size = np.linalg.norm(maxs - mins)
        dist = max(1.0, 1.8 * size)  # step back based on diagonal
    else:
        center = np.zeros(3); dist = 5.0

    eye = center + np.array([1.2, 1.2, 0.8]) * dist
    cam_pose = look_at(eye=eye, target=center, up=(0,0,1))
    cam = pyrender.PerspectiveCamera(yfov=np.deg2rad(45.0))
    scene.add(cam, pose=cam_pose)

    # Lighting (use viewer's Raymond rig for robust visibility)
    return scene, data

def main():
    #ap = argparse.ArgumentParser(description="Interactive 3D viewer for JSON primitives")
    #ap.add_argument("json", help="Path to JSON (e.g., pig01.json)")
    #args = ap.parse_args()
    json_path = (os.environ.get(ENV_JSON_KEY) or "").strip() or file_name
    win_title = (os.environ.get(ENV_TITLE_KEY) or "").strip()
    scene, data = load_scene(json_path)
    
    resx = int(data.get("render", {}).get("resolution_x", 1280))
    resy = int(data.get("render", {}).get("resolution_y", 720))

    viewer_kwargs = dict(
        viewport_size=(resx, resy),
        use_raymond_lighting=True,   # robust default 3-point lighting
        run_in_thread=False,
        record=False,
    )
    if win_title:
        try:
            pyrender.Viewer(scene, window_title=win_title, **viewer_kwargs)
            return
        except TypeError:
            pass
    pyrender.Viewer(scene, **viewer_kwargs)

if __name__ == "__main__":
    main()

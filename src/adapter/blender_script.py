"""
Author: Brian Gunnison

Brief: Blender in‑process script to build primitives from a plan/kitbash and render/save outputs.

Details: Parses CLI args passed after "--" by Blender, constructs scene objects,
auto-frames a camera, renders animation/still or prepares a .blend for GUI edits.
"""
# SPDX-License-Identifier: MIT
# This script runs inside Blender (bpy available)
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path


def parse_args(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=str, required=False, help="Path to DreamFast ScenePlan JSON")
    parser.add_argument("--kitbash", type=str, required=False, help="Path to GPT+ kitbash JSON (components/materials)")
    parser.add_argument("--out", type=str, required=False, help="Output path (MP4 for animation or PNG for still)")
    parser.add_argument("--profile", type=str, default="fast")
    parser.add_argument("--render-mode", type=str, default="animation", choices=["animation", "still", "none"], help="Render animation, a still image, or skip render (keep Blender open)")
    parser.add_argument("--save", type=str, required=False, help="Optional path to save a .blend after building the scene")
    return parser.parse_args(argv)


def radians_deg(vec):
    return [math.radians(float(v)) for v in vec]


def ensure_material(obj, rgba):
    import bpy  # type: ignore

    mat = bpy.data.materials.new(name=f"Mat_{obj.name}")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs[0].default_value = (rgba[0], rgba[1], rgba[2], 1.0)
        # Make preview matte to avoid blown highlights
        try:
            bsdf.inputs[5].default_value = 0.6  # Roughness
            bsdf.inputs[7].default_value = 0.1  # Specular
        except Exception:
            pass
    if obj.data.materials:
        obj.data.materials[0] = mat
    else:
        obj.data.materials.append(mat)


def look_at_euler(from_loc, to_loc):
    # Robust camera look-at using Blender mathutils: cameras look down -Z, up is +Y
    import mathutils  # type: ignore

    origin = mathutils.Vector((from_loc[0], from_loc[1], from_loc[2]))
    target = mathutils.Vector((to_loc[0], to_loc[1], to_loc[2]))
    direction = (target - origin)
    if direction.length == 0:
        direction = mathutils.Vector((0.0, 0.0, -1.0))
    rot_quat = direction.to_track_quat('-Z', 'Y')
    eul = rot_quat.to_euler()
    return [eul.x, eul.y, eul.z]


def build_primitive(obj_spec, fps):
    import bpy  # type: ignore

    t = obj_spec.get("transform", {})
    loc = t.get("location", [0, 0, 0])
    rot_deg = t.get("rotation_degrees", [0, 0, 0])
    sca = t.get("scale", [1, 1, 1])
    dims = obj_spec.get("dimensions", [1, 1, 1])
    color = obj_spec.get("color", {"r": 0.8, "g": 0.8, "b": 0.8})
    rgba = [float(color.get("r", 0.8)), float(color.get("g", 0.8)), float(color.get("b", 0.8)), 1.0]

    prim_type = obj_spec.get("type", "cube")
    name = obj_spec.get("name", prim_type.capitalize())

    # Add primitive
    if prim_type == "cube":
        bpy.ops.mesh.primitive_cube_add(location=loc)
    elif prim_type == "sphere":
        bpy.ops.mesh.primitive_uv_sphere_add(location=loc)
    elif prim_type == "cylinder":
        bpy.ops.mesh.primitive_cylinder_add(location=loc)
    elif prim_type == "cone":
        bpy.ops.mesh.primitive_cone_add(location=loc)
    elif prim_type == "plane":
        bpy.ops.mesh.primitive_plane_add(location=loc)
    elif prim_type == "torus":
        # Interpret dimensions as [major_diameter_x, major_diameter_y, thickness]
        # Use average of X/Y for a round torus; thickness as minor diameter
        maj_d = max(0.001, float(dims[0] + dims[1]) / 2.0)
        min_d = max(0.001, float(dims[2]))
        bpy.ops.mesh.primitive_torus_add(major_radius=maj_d / 2.0, minor_radius=min_d / 2.0, location=loc)
    else:
        return None

    obj = bpy.context.active_object
    obj.name = name
    obj.rotation_euler = radians_deg(rot_deg)
    # scale to approximate dimensions (Blender primitives default to ~2 units)
    if prim_type != "torus":
        obj.scale = [max(0.001, d / 2.0) for d in dims]
    ensure_material(obj, rgba)

    # Keyframe animation if any
    anim = obj_spec.get("animation") or {}
    for k in anim.get("location_keys", []):
        frame = int(round(float(k.get("time", 0.0)) * fps))
        loc_k = k.get("location")
        if loc_k:
            obj.location = loc_k
            obj.keyframe_insert(data_path="location", frame=frame)
    for k in anim.get("rotation_keys", []):
        frame = int(round(float(k.get("time", 0.0)) * fps))
        rot_k = k.get("rotation_degrees")
        if rot_k:
            obj.rotation_euler = radians_deg(rot_k)
            obj.keyframe_insert(data_path="rotation_euler", frame=frame)
    for k in anim.get("scale_keys", []):
        frame = int(round(float(k.get("time", 0.0)) * fps))
        sca_k = k.get("scale")
        if sca_k:
            obj.scale = sca_k
            obj.keyframe_insert(data_path="scale", frame=frame)

    return obj


def build_scene_from_kitbash(k: dict):
    import bpy  # type: ignore

    # Clear default
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)

    # Basic render settings
    scene = bpy.context.scene
    configure_fast_eevee(scene, 1280, 720, 24)
    scene.frame_start = 1
    scene.frame_end = 120

    # Lighting and world
    set_world_color({"r": 0.05, "g": 0.08, "b": 0.12})
    add_sun_light()

    # Materials lookup
    mats = k.get("materials") or {}

    def mat_color(name):
        if not name:
            return (0.7, 0.7, 0.7)
        m = mats.get(name)
        if isinstance(m, dict):
            base = m.get("base_color") or m.get("color")
            if isinstance(base, list) and len(base) >= 3:
                try:
                    return (float(base[0]), float(base[1]), float(base[2]))
                except Exception:
                    pass
        return (0.7, 0.7, 0.7)

    built = []
    comps = k.get("components") or []
    for c in comps:
        ctype = str(c.get("type", "")).lower()
        name = c.get("id") or c.get("name") or ctype.capitalize()
        pos = c.get("position") or c.get("location") or [0.0, 0.0, 0.0]
        rot = c.get("rotation") or c.get("rotation_degrees") or [0.0, 0.0, 0.0]
        col = mat_color(c.get("material"))

        if ctype == "box":
            size = c.get("size") or [1.0, 1.0, 1.0]
            bpy.ops.mesh.primitive_cube_add(location=pos)
            ob = bpy.context.active_object
            ob.name = name
            ob.rotation_euler = radians_deg(rot)
            ob.scale = [max(0.001, float(size[0]) / 2.0), max(0.001, float(size[1]) / 2.0), max(0.001, float(size[2]) / 2.0)]
            ensure_material(ob, (col[0], col[1], col[2], 1.0))
            built.append(ob)
        elif ctype == "cylinder":
            r = float(c.get("radius", 0.5))
            h = float(c.get("height", 1.0))
            bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=h, location=pos)
            ob = bpy.context.active_object
            ob.name = name
            ob.rotation_euler = radians_deg(rot)
            ensure_material(ob, (col[0], col[1], col[2], 1.0))
            built.append(ob)
        elif ctype == "torus":
            R = float(c.get("major_radius", 0.3))
            r = float(c.get("minor_radius", 0.08))
            bpy.ops.mesh.primitive_torus_add(major_radius=R, minor_radius=r, location=pos)
            ob = bpy.context.active_object
            ob.name = name
            ob.rotation_euler = radians_deg(rot)
            ensure_material(ob, (col[0], col[1], col[2], 1.0))
            built.append(ob)
        else:
            continue

    # Camera: auto-frame around built objects
    bpy.ops.object.camera_add(location=[6, -6, 4])
    cam = bpy.context.active_object
    cam.name = "Camera"
    scene.camera = cam
    if built:
        cx = sum(o.location[0] for o in built) / len(built)
        cy = sum(o.location[1] for o in built) / len(built)
        cz = sum(o.location[2] for o in built) / len(built)
        import math as _m
        r = 0.0
        for o in built:
            dx, dy, dz = o.location[0] - cx, o.location[1] - cy, o.location[2] - cz
            dist = _m.sqrt(dx*dx + dy*dy + dz*dz)
            sc = sum(abs(s) for s in o.scale)
            r = max(r, dist + sc)
        r = max(r, 2.0)
        d = max(6.0, 2.5 * r)
        target = [cx, cy, cz]
        cam.location = [cx + 0.7 * d, cy - 0.7 * d, cz + 0.5 * d]
        cam.rotation_euler = look_at_euler(cam.location, target)
        cam.data.lens = 35.0
        cam.data.clip_end = max(100.0, 4.0 * d)
    return scene


def configure_fast_eevee(scene, resx, resy, fps):
    import bpy  # type: ignore

    # Choose the best available real-time engine
    chosen = None
    for eng in ("BLENDER_EEVEE", "BLENDER_EEVEE_NEXT", "BLENDER_WORKBENCH"):
        try:
            scene.render.engine = eng
            chosen = eng
            break
        except Exception:
            continue

    scene.render.resolution_x = int(resx)
    scene.render.resolution_y = int(resy)
    scene.render.fps = int(fps)

    # Apply fast settings where possible (EEVEE and EEVEE_NEXT share many names)
    eevee = getattr(scene, "eevee", None)
    if eevee is not None:
        for attr, value in (
            ("taa_samples", 1),
            ("taa_render_samples", 1),
            ("use_shadow", False),
            ("use_gtao", False),
            ("use_bloom", False),
            ("use_ssr", False),
            ("use_motion_blur", False),
            ("use_shadow_high_bitdepth", False),
        ):
            try:
                setattr(eevee, attr, value)
            except Exception:
                pass


def set_world_color(color_dict):
    import bpy  # type: ignore

    r = float(color_dict.get("r", 0.05))
    g = float(color_dict.get("g", 0.08))
    b = float(color_dict.get("b", 0.12))
    if bpy.data.worlds:
        world = bpy.data.worlds[0]
    else:
        world = bpy.data.worlds.new("World")
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs[0].default_value = (r, g, b, 1.0)
        # Keep world lighting dim to prevent washout
        try:
            bg.inputs[1].default_value = 0.2
        except Exception:
            pass
    bpy.context.scene.world = world


def add_sun_light():
    import bpy  # type: ignore

    bpy.ops.object.light_add(type='SUN', location=(4, -4, 6))
    sun = bpy.context.active_object
    sun.data.energy = 3.0
    sun.data.use_shadow = False
    # Aim sun at origin to ensure objects are lit
    try:
        sun.rotation_euler = look_at_euler(sun.location, (0.0, 0.0, 0.0))
    except Exception:
        pass
    return sun


def build_scene(plan: dict):
    import bpy  # type: ignore

    # Clear default
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)

    rs = plan.get("render", {})
    fps = int(rs.get("fps", 24))
    dur = float(rs.get("duration_seconds", 5.0))
    resx = int(rs.get("resolution_x", 1280))
    resy = int(rs.get("resolution_y", 720))

    scene = bpy.context.scene
    configure_fast_eevee(scene, resx, resy, fps)
    scene.frame_start = 1
    scene.frame_end = max(1, int(round(dur * fps)))

    set_world_color(rs.get("background_color", {}))
    add_sun_light()

    # Camera
    cam_spec = plan.get("camera", {})
    bpy.ops.object.camera_add(location=cam_spec.get("transform", {}).get("location", [6, -6, 4]))
    cam = bpy.context.active_object
    cam.name = cam_spec.get("name", "Camera")
    cam.data.lens = float(cam_spec.get("focal_length_mm", 35.0))
    rot_deg = cam_spec.get("transform", {}).get("rotation_degrees", [60, 0, 45])
    cam.rotation_euler = radians_deg(rot_deg)
    look = cam_spec.get("look_at")
    if look:
        cam.rotation_euler = look_at_euler(cam.location, look)
    # Ensure scene uses this camera
    scene.camera = cam

    anim = cam_spec.get("animation") or {}
    for k in anim.get("location_keys", []):
        frame = int(round(float(k.get("time", 0.0)) * fps))
        loc_k = k.get("location")
        if loc_k:
            cam.location = loc_k
            cam.keyframe_insert(data_path="location", frame=frame)
    for k in anim.get("rotation_keys", []):
        frame = int(round(float(k.get("time", 0.0)) * fps))
        rot_k = k.get("rotation_degrees")
        if rot_k:
            cam.rotation_euler = radians_deg(rot_k)
            cam.keyframe_insert(data_path="rotation_euler", frame=frame)

    # Objects
    built = []
    for o in plan.get("objects", []):
        ob = build_primitive(o, fps)
        if ob is not None:
            built.append(ob)

    # Auto-frame camera if no explicit look-at and objects exist
    if not look and built:
        cx = sum(o.location[0] for o in built) / len(built)
        cy = sum(o.location[1] for o in built) / len(built)
        cz = sum(o.location[2] for o in built) / len(built)
        # approximate radius using distance to center plus object scale magnitude
        import math as _m
        r = 0.0
        for o in built:
            dx, dy, dz = o.location[0] - cx, o.location[1] - cy, o.location[2] - cz
            dist = _m.sqrt(dx*dx + dy*dy + dz*dz)
            sc = sum(abs(s) for s in o.scale)
            r = max(r, dist + sc)
        r = max(r, 2.0)
        d = max(6.0, 2.5 * r)
        target = [cx, cy, cz]
        cam.location = [cx + 0.7 * d, cy - 0.7 * d, cz + 0.5 * d]
        cam.rotation_euler = look_at_euler(cam.location, target)
        cam.data.clip_end = max(100.0, 4.0 * d)

    return scene


def configure_output(scene, out_path: Path, mode: str):
    import bpy  # type: ignore
    if mode == 'still':
        scene.render.image_settings.file_format = 'PNG'
        scene.render.filepath = str(out_path)
    else:
        scene.render.image_settings.file_format = 'FFMPEG'
        scene.render.ffmpeg.format = 'MPEG4'
        scene.render.ffmpeg.codec = 'H264'
        scene.render.ffmpeg.constant_rate_factor = 'MEDIUM'
        scene.render.filepath = str(out_path)


def main(argv):
    # Parse args after the '--'
    args = parse_args(argv)
    plan_path = Path(args.plan) if args.plan else None
    kitbash_path = Path(args.kitbash) if getattr(args, 'kitbash', None) else None
    out_path = Path(args.out) if args.out else None

    # Lazy import bpy only after arguments are ready
    import bpy  # type: ignore

    if not plan_path and not kitbash_path:
        raise SystemExit("Provide either --plan or --kitbash")

    if plan_path:
        with plan_path.open("r", encoding="utf-8") as f:
            plan = json.load(f)
        scene = build_scene(plan)
    else:
        with kitbash_path.open("r", encoding="utf-8") as f:
            kitbash = json.load(f)
        scene = build_scene_from_kitbash(kitbash)
    mode = args.render_mode
    # If no out_path provided for 'none', set a dummy path
    if not args.out and mode != 'none':
        raise SystemExit("--out path is required unless --render-mode none")
    if mode != 'none':
        configure_output(scene, out_path, mode)

    if mode == 'animation':
        print("[BLENDER] Rendering animation...")
        bpy.ops.render.render(animation=True, write_still=False)
        print("[BLENDER] Done.")
    elif mode == 'still':
        print("[BLENDER] Rendering still image...")
        # pick the mid frame
        mid = max(scene.frame_start, int((scene.frame_start + scene.frame_end) / 2))
        scene.frame_set(mid)
        bpy.ops.render.render(write_still=True)
        print("[BLENDER] Still saved.")
    else:
        print("[BLENDER] Built scene; leaving Blender open for edits.")

    # Save .blend if requested (after building and optional render)
    if args.save:
        import bpy  # type: ignore
        print(f"[BLENDER] Saving blend → {args.save}")
        bpy.ops.wm.save_mainfile(filepath=str(args.save))


if __name__ == "__main__":
    # Blender passes its own args; find '--' and parse after it
    argv = sys.argv
    if "--" in argv:
        idx = argv.index("--")
        cli_args = argv[idx + 1 :]
    else:
        cli_args = []
    main(cli_args)

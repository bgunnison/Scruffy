from __future__ import annotations

from typing import List, Dict, Any


def kitbash_tugboat(name_prefix: str = "Tugboat") -> List[Dict[str, Any]]:
    """Return a list of primitive object dicts approximating a small tugboat.

    Layout (units ~ meters):
    - Hull: long low box along +X, centered at Z=0.6 (waterline ~0.6)
    - Cabin: sits on hull top, slightly aft (negative X)
    - Stack: on cabin roof, slightly forward
    - Bow cap: cone pointing +X for recognizable bow
    - Fenders: small spheres at port/starboard midships
    """
    hull_dims = [4.0, 2.0, 1.2]
    hull_center = [0.0, 0.0, 0.6]
    hull_top_z = hull_center[2] + hull_dims[2] / 2.0  # 1.2

    cabin_dims = [1.6, 1.4, 1.0]
    cabin_center = [-0.6, 0.0, hull_top_z + cabin_dims[2] / 2.0]  # 1.2 + 0.5 = 1.7
    cabin_top_z = cabin_center[2] + cabin_dims[2] / 2.0  # 2.2

    stack_dims = [0.5, 0.5, 1.2]
    stack_center = [0.2, 0.0, cabin_top_z + stack_dims[2] / 2.0]  # 2.2 + 0.6 = 2.8

    bow_dims = [0.8, 1.8, 0.8]
    bow_center = [hull_center[0] + hull_dims[0] / 2.0 + bow_dims[0] * 0.25, 0.0, hull_center[2] + 0.2]

    fender_dims = [0.4, 0.4, 0.4]
    fender_port = [0.0, -(hull_dims[1] / 2.0 + fender_dims[1] / 2.0 - 0.05), hull_center[2]]
    fender_starboard = [0.0, (hull_dims[1] / 2.0 + fender_dims[1] / 2.0 - 0.05), hull_center[2]]

    return [
        {
            "name": f"{name_prefix}_Hull",
            "type": "cube",
            "dimensions": hull_dims,
            "transform": {"location": hull_center},
            "color": {"r": 0.63, "g": 0.19, "b": 0.15},
        },
        {
            "name": f"{name_prefix}_Cabin",
            "type": "cube",
            "dimensions": cabin_dims,
            "transform": {"location": cabin_center},
            "color": {"r": 0.85, "g": 0.85, "b": 0.8},
        },
        {
            "name": f"{name_prefix}_Stack",
            "type": "cylinder",
            "dimensions": stack_dims,
            "transform": {"location": stack_center},
            "color": {"r": 0.2, "g": 0.2, "b": 0.2},
        },
        {
            "name": f"{name_prefix}_Bow",
            "type": "cone",
            "dimensions": bow_dims,
            "transform": {"location": bow_center, "rotation_degrees": [0.0, 90.0, 0.0]},
            "color": {"r": 0.63, "g": 0.19, "b": 0.15},
        },
        {
            "name": f"{name_prefix}_FenderPort",
            "type": "sphere",
            "dimensions": fender_dims,
            "transform": {"location": fender_port},
            "color": {"r": 0.1, "g": 0.1, "b": 0.1},
        },
        {
            "name": f"{name_prefix}_FenderStarboard",
            "type": "sphere",
            "dimensions": fender_dims,
            "transform": {"location": fender_starboard},
            "color": {"r": 0.1, "g": 0.1, "b": 0.1},
        },
    ]


def kitbash_house(name_prefix: str = "House") -> List[Dict[str, Any]]:
    """Return a minimal house shape with integrated windows and a door.

    - Body: cube
    - Roof: cone on top, pointing up
    - Windows: two thin cubes on the front face
    - Door: thin cube centered front, below windows
    """
    body_dims = [4.0, 4.0, 2.0]
    body_center = [0.0, 0.0, body_dims[2] / 2.0]  # z = 1.0
    body_top_z = body_center[2] + body_dims[2] / 2.0  # 2.0

    roof_dims = [4.5, 4.5, 1.5]
    roof_center = [0.0, 0.0, body_top_z + roof_dims[2] / 2.0]  # 2.75

    # Front face at negative Y (towards default camera)
    front_y = -(body_dims[1] / 2.0 + 0.01)
    win_dims = [0.8, 0.1, 0.8]
    win_offset_x = 1.0
    win_z = body_center[2] + 0.5  # mid height of body
    door_dims = [1.0, 0.15, 1.6]
    door_z = body_center[2] - 0.2  # lower

    return [
        {
            "name": f"{name_prefix}_Body",
            "type": "cube",
            "dimensions": body_dims,
            "transform": {"location": body_center},
            "color": {"r": 0.75, "g": 0.72, "b": 0.68},
        },
        {
            "name": f"{name_prefix}_Roof",
            "type": "cone",
            "dimensions": roof_dims,
            "transform": {"location": roof_center, "rotation_degrees": [0.0, 0.0, 0.0]},
            "color": {"r": 0.5, "g": 0.15, "b": 0.12},
        },
        {
            "name": f"{name_prefix}_WindowL",
            "type": "cube",
            "dimensions": win_dims,
            "transform": {"location": [-win_offset_x, front_y, win_z]},
            "color": {"r": 0.6, "g": 0.85, "b": 1.0},
        },
        {
            "name": f"{name_prefix}_WindowR",
            "type": "cube",
            "dimensions": win_dims,
            "transform": {"location": [win_offset_x, front_y, win_z]},
            "color": {"r": 0.6, "g": 0.85, "b": 1.0},
        },
        {
            "name": f"{name_prefix}_Door",
            "type": "cube",
            "dimensions": door_dims,
            "transform": {"location": [0.0, front_y, door_z]},
            "color": {"r": 0.3, "g": 0.2, "b": 0.1},
        },
    ]


def kitbash_for_category(name: str, category: str) -> List[Dict[str, Any]]:
    c = category.lower()
    if "tugboat" in c or ("boat" in c and "tug" in name.lower()):
        return kitbash_tugboat(name)
    if "house" in c or "home" in c:
        return kitbash_house(name)
    if c == "cube" or c == "box":
        return [
            {
                "name": name,
                "type": "cube",
                "dimensions": [1.0, 1.0, 1.0],
                "transform": {"location": [0.0, 0.0, 0.5]},
                "color": {"r": 0.8, "g": 0.2, "b": 0.2},
            }
        ]
    # Default: a small cube as placeholder
    return [
        {
            "name": f"{name}_Placeholder",
            "type": "cube",
            "dimensions": [1.0, 1.0, 1.0],
            "transform": {"location": [0.0, 0.0, 0.5]},
            "color": {"r": 0.6, "g": 0.6, "b": 0.6},
        }
    ]

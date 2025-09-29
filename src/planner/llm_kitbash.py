"""
Author: Brian Gunnison

Brief: LLM‑based kitbashing to convert objects into primitive parts under a strict schema.

Details: Selects a prompt variant, hardens a JSON schema, and requests parts
for each object with bounded sizes and counts (reality factor / max parts).
"""
# SPDX-License-Identifier: MIT
from __future__ import annotations

import json
from typing import Any, Dict, List

from src.util.env import get_env_str
from src.util import log
from src.util.strict_schema import harden_schema
from src.util.llm_debug import is_verbose, log_messages
from src.util.paths import repo_root


KITBASH_SYSTEM_PROMPT = """
You convert objects into kitbashed primitives.
Rules:
- Primitives only: {cube,sphere,cylinder,cone,plane,torus}.
- Each part has: name, type, dimensions[x,y,z], location[x,y,z], rotation_degrees[x,y,z], color[r,g,b 0..1].
- Use as few parts as possible. Only add parts that materially improve recognition.
- Sizes in meters within [0.1..20]. Keep assembly near origin; no environment/camera/animation fields.
- Silhouette-first: prefer one or two large volumes; add minimal accents.
- Maintain coherent relative placement: parts should connect or nest logically; avoid floating, intersecting unnaturally, or drifting apart.
- Align axes and centers where natural; keep assemblies compact and balanced around the origin.
- Local axes: cylinders/cones/torus are +Z–aligned before rotation; cubes/planes are box-aligned.
- Budget: do not exceed max_parts; prefer the minimum that remains recognizable.
Output exactly this JSON shape: {"objects":[{"name":<string>,"parts":[...] }],"meta":{"reality_factor":<int>}}
"""


def _max_parts_for(reality_factor: int) -> int:
    """Direct mapping: rf is the max parts budget (1..100)."""
    try:
        rf = int(reality_factor)
    except Exception:
        rf = 5
    return max(1, min(rf, 100))


# Intentionally no object-specific hints; the model must infer components.


def _load_default_reality_factor() -> int | None:
    """Read top-level 'reality_factor' from prompts/aiprompts.json if present."""
    try:
        import json as _json
        p = repo_root() / "prompts" / "aiprompts.json"
        with p.open("r", encoding="utf-8") as f:
            data = _json.load(f)
        rf = data.get("reality_factor")
        if isinstance(rf, int):
            return max(1, min(rf, 10))
        if isinstance(rf, str) and rf.strip().isdigit():
            v = int(rf.strip())
            return max(1, min(v, 10))
        if isinstance(rf, dict):
            dv = rf.get("default")
            if isinstance(dv, int):
                return max(1, min(dv, 10))
            if isinstance(dv, str) and dv.strip().isdigit():
                v = int(dv.strip())
                return max(1, min(v, 10))
    except Exception:
        pass
    return None


def _load_prompt_variant(name: str, reality_factor: int, max_parts: int) -> tuple[str, str | None, bool, str | None]:
    """Select and load a kitbash system prompt.

    Returns a tuple: (prompt_text, selected_name, used_builtin_fallback, warning_reason).
    - If a valid variant is found, selected_name is its key and used_builtin_fallback is False.
    - On any error or invalid selection, falls back to KITBASH_SYSTEM_PROMPT and sets warning_reason.

    Supports formatting placeholders {reality_factor} and {max_parts}.
    """
    data = None
    try:
        import json as _json
        p = repo_root() / "prompts" / "aiprompts.json"
        with p.open("r", encoding="utf-8") as f:
            data = _json.load(f)
    except Exception as e:
        return (KITBASH_SYSTEM_PROMPT, None, True, f"Failed to read prompts/aiprompts.json: {e.__class__.__name__}")

    # Resolve selected name: explicit match, else file default, else first non-meta entry
    selected: str | None = None
    entry = data.get(name) if name else None
    if name and isinstance(entry, (str, dict)):
        selected = name
    else:
        dflt = data.get("default")
        if isinstance(dflt, str):
            dv = data.get(dflt)
            if isinstance(dv, (str, dict)):
                selected = dflt
    if not selected:
        for k, v in data.items():
            if k not in ("default", "reality_factor", "object_extraction") and isinstance(v, (str, dict)):
                selected = k
                break

    if not selected:
        return (KITBASH_SYSTEM_PROMPT, None, True, "No usable variant found in prompts file; using built-in prompt")

    val = data.get(selected)
    text: str | None = None
    if isinstance(val, str):
        text = val
    elif isinstance(val, dict):
        if isinstance(val.get("text"), str):
            text = val["text"]
        elif isinstance(val.get("lines"), list):
            text = "\n".join(str(x) for x in val["lines"])

    if not (isinstance(text, str) and text.strip()):
        return (KITBASH_SYSTEM_PROMPT, selected, True, f"Variant '{selected}' has no text/lines; using built-in prompt")

    # Safely substitute only known placeholders without interpreting other braces
    try:
        formatted = (
            text.replace("{reality_factor}", str(int(reality_factor)))
                .replace("{max_parts}", str(int(max_parts)))
        )
    except Exception:
        formatted = text
    return (formatted, selected, False, None)


def synthesize_kitbash(objects: List[Dict[str, Any]], reality_factor: int | None = None) -> List[Dict[str, Any]]:
    """Return a list of kitbashed objects with parts for each input object.

    Uses multiple prompt variants and selects the best candidate under a heuristic
    and the provided reality_factor (or env REALITY_FACTOR, default 5).
    """
    api_key = get_env_str("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set; use --mock or set your key.")

    try:
        from openai import OpenAI  # type: ignore
    except Exception as e:  # pragma: no cover
        raise RuntimeError(
            "openai package not installed; install requirements or use --mock"
        ) from e

    client = OpenAI(api_key=api_key)

    if reality_factor is None:
        # Prefer env var; else pull from prompts file default; else 5
        env_rf = get_env_str("REALITY_FACTOR", "") or ""
        if env_rf.strip():
            try:
                reality_factor = int(env_rf)
            except Exception:
                reality_factor = 5
        else:
            reality_factor = _load_default_reality_factor() or 5
    max_parts = _max_parts_for(reality_factor)
    # Optional hard cap via env override (e.g., KITBASH_MAX_PARTS=6)
    try:
        cap_env = (get_env_str("KITBASH_MAX_PARTS", "") or "").strip()
        if cap_env:
            cap = max(1, int(float(cap_env)))
            max_parts = min(max_parts, cap)
    except Exception:
        pass
    # Prefer env; if not set, defer to file's 'default' selection
    variant_name = (get_env_str("KITBASH_PROMPT", "") or "").strip()
    system_prompt, selected_name, used_builtin, warn_reason = _load_prompt_variant(variant_name, reality_factor, max_parts)
    # Emit helpful logs if selection is invalid or fell back
    if variant_name and (used_builtin or (selected_name and selected_name != variant_name)):
        # User asked for a specific variant but it's invalid or redirected
        if selected_name and not used_builtin:
            log.warn(f"KITBASH_PROMPT='{variant_name}' not found; using '{selected_name}' from prompts file")
        elif used_builtin and selected_name:
            log.warn(f"KITBASH_PROMPT='{variant_name}' invalid; using built-in prompt (variant '{selected_name}' unusable)")
        else:
            log.warn(f"KITBASH_PROMPT='{variant_name}' invalid; using built-in prompt")
    elif used_builtin and not variant_name:
        # No explicit request but file invalid
        if warn_reason:
            log.warn(warn_reason)
        else:
            log.warn("prompts/aiprompts.json invalid; using built-in kitbash prompt")

    schema = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "properties": {
            "objects": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "parts": {
                            "type": "array",
                            "maxItems": 0,
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                        "type": {"type": "string", "enum": ["cube", "sphere", "cylinder", "cone", "plane", "torus"]},
                                    "dimensions": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
                                    "location": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
                                    "rotation_degrees": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
                                    "color": {
                                        "type": "object",
                                        "properties": {
                                            "r": {"type": "number"},
                                            "g": {"type": "number"},
                                            "b": {"type": "number"}
                                        },
                                        "required": ["r", "g", "b"],
                                        "additionalProperties": False
                                    }
                                },
                                "required": ["name", "type", "dimensions", "location", "rotation_degrees", "color"],
                                "additionalProperties": False
                            }
                        }
                    },
                    "required": ["name", "parts"],
                    "additionalProperties": False
                }
            },
            "meta": {
                "type": "object",
                "properties": {
                    "reality_factor": {"type": "integer", "minimum": 1, "maximum": 10}
                },
                "required": ["reality_factor"],
                "additionalProperties": False
            },
        },
        "required": ["objects", "meta"],
        "additionalProperties": False,
    }

    # Inject dynamic max items for parts based on computed max_parts (soft upper bound only).
    try:
        mp = int(max_parts)
        schema["properties"]["objects"]["items"]["properties"]["parts"]["maxItems"] = mp
    except Exception:
        pass

    schema = harden_schema(schema)

    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": (
                f"reality_factor={reality_factor}; max_parts={max_parts}.\n"
                + "Use at most 'max_parts' parts per object; prefer the fewest parts that yield a clear, recognizable silhouette. Do not add unrelated accessories or tiny decorative details.\n"
                + "Create parts for these objects (name, category, optional color {r,g,b}):\n"
                + json.dumps(objects)
                + "\nIf an object includes a 'color' with r,g,b in [0..1], use it as the base color for its parts."
            ),
        },
    ]
    if is_verbose():
        log_messages("synthesize_kitbash", messages)

    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        response_format={
            "type": "json_schema",
            "json_schema": {"name": "kitbash_parts", "schema": schema, "strict": True},
        },
        temperature=0.1,
    )
    content = completion.choices[0].message.content or "{}"
    data = json.loads(content)
    if isinstance(data, dict) and "meta" not in data:
        data["meta"] = {"reality_factor": int(reality_factor)}
    return data.get("objects") or []

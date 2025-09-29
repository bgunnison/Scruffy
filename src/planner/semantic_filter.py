"""
Author: Brian Gunnison

Brief: LLM‑based object/action/path extraction from a scene description.

Details: Loads a configurable system prompt and requests structured JSON with
objects, actions, and paths; used by the iterative flow.
"""
# SPDX-License-Identifier: MIT
from __future__ import annotations

import json
from typing import Any, Dict, List, Tuple

from src.util.env import get_env_str
from src.util import log
from src.util.strict_schema import harden_schema
from src.util.llm_debug import is_verbose, log_messages
from src.util.paths import repo_root


SEMANTIC_SYSTEM_PROMPT = (
    "Extract only the objects mentioned in the user's description.\n"
    "Return JSON with key 'objects': an array of {name, category, color}.\n"
    "Use concise, singular names; deduplicate by type and near-synonyms.\n"
    "Category should be the specific object type (e.g., 'chair', 'box').\n"
    "Include color as {r,g,b} in [0..1]; if unspecified, use neutral gray {r:0.7,g:0.7,b:0.7}."
)


def _load_semantic_system_prompt() -> str:
    """Load object extraction system prompt from prompts/aiprompts.json if present.

    Supports either {"text": str} or {"lines": list[str]} under key "object_extraction".
    Falls back to SEMANTIC_SYSTEM_PROMPT on any error.
    """
    try:
        import json as _json
        p = repo_root() / "prompts" / "aiprompts.json"
        with p.open("r", encoding="utf-8") as f:
            data = _json.load(f)
        val = data.get("object_extraction")
        text = None
        if isinstance(val, str):
            text = val
        elif isinstance(val, dict):
            if isinstance(val.get("text"), str):
                text = val["text"]
            elif isinstance(val.get("lines"), list):
                text = "\n".join(str(x) for x in val["lines"])
        if isinstance(text, str) and text.strip():
            return text
    except Exception:
        pass
    return SEMANTIC_SYSTEM_PROMPT


def semantic_filter_with_openai(original_prompt: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
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
                        "category": {"type": "string"},
                        "color": {
                            "type": "object",
                            "properties": {
                                "r": {"type": "number", "minimum": 0, "maximum": 1},
                                "g": {"type": "number", "minimum": 0, "maximum": 1},
                                "b": {"type": "number", "minimum": 0, "maximum": 1}
                            },
                            "required": ["r", "g", "b"],
                            "additionalProperties": False
                        }
                    },
                    "required": ["name", "category", "color"],
                    "additionalProperties": False
                }
            },
            "actions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string", "enum": ["move_along_path", "none"]},
                        "subject": {"type": "string"},
                        "path_name": {"type": "string"}
                    },
                    "required": ["type", "subject"],
                    "additionalProperties": False
                }
            },
            "paths": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "points": {
                            "type": "array",
                            "items": {
                                "type": "array",
                                "items": {"type": "number"},
                                "minItems": 3,
                                "maxItems": 3
                            },
                            "minItems": 2
                        }
                    },
                    "required": ["name", "points"],
                    "additionalProperties": False
                }
            }
        },
        "required": ["objects"],
        "additionalProperties": False
    }

    schema = harden_schema(schema)

    system_prompt = _load_semantic_system_prompt()
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": original_prompt},
    ]
    if is_verbose():
        log_messages("semantic_filter_with_openai", messages, {"schema":"semantic"})

    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        response_format={
            "type": "json_schema",
            "json_schema": {"name": "semantic_breakdown", "schema": schema, "strict": True},
        },
        temperature=0.0,
    )
    content = completion.choices[0].message.content or "{}"
    data = json.loads(content)
    return data.get("objects") or [], data.get("actions") or [], data.get("paths") or []

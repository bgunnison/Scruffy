"""
Author: Brian Gunnison

Brief: Harden a JSON schema for strict LLM JSON responses.

Details: Recursively sets defaults like additionalProperties=False and required
keys to ensure compliant outputs from JSON mode.
"""
# SPDX-License-Identifier: MIT
from __future__ import annotations

def harden_schema(schema: dict) -> dict:
    """Recursively harden JSON schema for strict LLM JSON mode.

    - Ensure objects declare type=object, properties, additionalProperties=False, and
      required includes every property key.
    - Recurse into properties, $defs/definitions, items, and anyOf/oneOf/allOf.
    """
    if not isinstance(schema, dict):
        return schema

    if schema.get("type") == "object" or "properties" in schema or "required" in schema:
        schema.setdefault("type", "object")
        schema.setdefault("properties", {})
        schema["additionalProperties"] = False
        prop_keys = list(schema.get("properties", {}).keys())
        schema["required"] = prop_keys

    for key in ("properties", "definitions", "$defs"):
        if key in schema and isinstance(schema[key], dict):
            for k, v in list(schema[key].items()):
                schema[key][k] = harden_schema(v)

    if "items" in schema:
        schema["items"] = harden_schema(schema["items"])

    for key in ("anyOf", "oneOf", "allOf"):
        if key in schema and isinstance(schema[key], list):
            schema[key] = [harden_schema(s) for s in schema[key]]

    return schema

from __future__ import annotations

"""
Manual test to open the 3D viewer for a given JSON plan.

Usage:
  python tests/manual_3dviewer_test.py --json out/iterative/pig01.json

Notes:
- This launches the interactive 3D viewer window (non-blocking) so you can
  visually inspect the sketch. It does not assert or close the window.
- By default it will try 'out/iterative/pig01.json' relative to repo root.
"""

import argparse
import os
import sys
from pathlib import Path

# Ensure repo root is on sys.path when running from tests/ directly
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.util.paths import repo_root
from src.adapter.pyviewer_cli import run_pyviewer_preview


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Open 3D viewer for a JSON file (manual visual test)")
    ap.add_argument("--json", required=False, help="Path to JSON scene (defaults to out/iterative/pig01.json)")
    args = ap.parse_args(argv)

    root = repo_root()
    json_path = (Path(args.json).resolve() if args.json else (root / "out" / "iterative" / "pig01.json").resolve())
    if not json_path.exists():
        print(f"JSON not found: {json_path}")
        return 2

    title = json_path.stem
    rc = run_pyviewer_preview(json_path, title=title)
    if rc != 0:
        print("Failed to launch 3D viewer.")
    else:
        print(f"Launched 3D viewer for: {json_path}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

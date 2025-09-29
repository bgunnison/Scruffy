#!/usr/bin/env python
from __future__ import annotations

import os
import sys
from src.orchestrator.interactive import iterative as iterative_flow
from src.util.llm_debug import set_verbose, is_verbose


def _repl_help() -> None:
    print(
        """
DreamFast REPL
- Type a prompt to build a quick per-object preview
- Commands:
  - verbose [on|off]: toggle/show LLM prompt logging
  - timings [on|off]: only print stage timings (AI + render)
  - reality [0..100]: set/show part budget directly (0 = placeholder box; default 5)
  - help: show this help
  - exit: press Enter on an empty line or Ctrl+C
""".strip()
    )


def repl() -> None:
    timings_only = os.environ.get("TIMINGS_ONLY", "").lower() in ("1", "true", "on", "yes")
    if not timings_only:
        _repl_help()
    while True:
        try:
            prompt = input("prompt> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not prompt:
            break
        # Commands
        if prompt.lower() in ("help", "?"):
            if not timings_only:
                _repl_help()
            continue
        if prompt.lower() in ("exit", "quit"):
            break
        if prompt.lower().startswith("verbose"):
            parts = prompt.split()
            if len(parts) == 1:
                # toggle
                set_verbose(not is_verbose())
            elif parts[1].lower() in ("on", "true", "1"):
                set_verbose(True)
            elif parts[1].lower() in ("off", "false", "0"):
                set_verbose(False)
            else:
                print("Usage: verbose [on|off]")
            continue
        if prompt.lower().startswith("timings"):
            parts = prompt.split()
            if len(parts) == 1:
                # toggle
                timings_only = not timings_only
            elif parts[1].lower() in ("on", "true", "1"):
                timings_only = True
            elif parts[1].lower() in ("off", "false", "0"):
                timings_only = False
            else:
                print("Usage: timings [on|off]")
                continue
            os.environ["TIMINGS_ONLY"] = "1" if timings_only else "0"
            if not timings_only:
                _repl_help()
            continue
        if prompt.lower().startswith("reality"):
            parts = prompt.replace("="," ").split()
            cur = os.environ.get("REALITY_FACTOR", "")
            if len(parts) == 1:
                shown = cur if cur else "(default 5)"
                print("Reality maps directly to max parts. 0 uses a placeholder box.")
                print(f"Reality factor is {shown}. Set 0..100, e.g., 'reality 5'.")
                continue
            try:
                v = int(float(parts[1]))
                if v < 0 or v > 100:
                    raise ValueError
                os.environ["REALITY_FACTOR"] = str(v)
                print(f"Reality factor is {v}")
            except ValueError:
                print("Usage: reality [0..100]")
            continue
        try:
            iterative_flow(prompt=prompt, approve=True)
        except SystemExit:
            # Typer may call Exit; ignore and continue
            pass

def main(argv: list[str]) -> None:
    # For now we only support the interactive REPL.
    repl()


if __name__ == "__main__":
    main(sys.argv)

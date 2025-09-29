from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Iterable, Optional

from .paths import repo_root
import shutil


def _exists_exe(p: Path) -> bool:
    try:
        return p.is_file() and os.access(str(p), os.X_OK)
    except Exception:
        return False


def _candidate_paths() -> Iterable[Path]:
    # Cross-platform guesses for Blender binary
    paths: list[Path] = []
    # From PATH
    for name in ("blender", "Blender", "blender.exe"):
        p = shutil.which(name)
        if p:
            paths.append(Path(p))

    # Windows common installs
    if os.name == 'nt':
        prog = os.environ.get('ProgramFiles', r"C:\\Program Files")
        progx86 = os.environ.get('ProgramFiles(x86)', r"C:\\Program Files (x86)")
        for base in (prog, progx86):
            base_p = Path(base) / "Blender Foundation"
            if base_p.exists():
                try:
                    for sub in sorted(base_p.glob("Blender*"), reverse=True):
                        cand = sub / "blender.exe"
                        if cand.exists():
                            paths.append(cand)
                except Exception:
                    pass
    else:
        # macOS default app bundle
        mac_app = Path("/Applications/Blender.app/Contents/MacOS/Blender")
        if mac_app.exists():
            paths.append(mac_app)
        # Common Linux locations
        for p in (Path("/usr/bin/blender"), Path("/usr/local/bin/blender"), Path("/snap/bin/blender")):
            if p.exists():
                paths.append(p)
    return paths


def _update_env_file(key: str, value: str) -> None:
    env_path = repo_root() / ".env"
    lines: list[str] = []
    if env_path.exists():
        try:
            lines = env_path.read_text(encoding="utf-8").splitlines()
        except Exception:
            lines = []
    updated = False
    out_lines: list[str] = []
    for line in lines:
        if line.strip().startswith(f"{key}="):
            out_lines.append(f"{key}={value}")
            updated = True
        else:
            out_lines.append(line)
    if not updated:
        out_lines.append(f"{key}={value}")
    try:
        env_path.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
    except Exception:
        # Best effort; ignore persistence errors
        pass


def ensure_blender_path(interactive: bool = True) -> Optional[Path]:
    """Return a usable Blender path.

    - If BLENDER_PATH is set and valid, return it.
    - Else try to auto-detect from common locations and PATH.
    - If interactive and TTY, ask once to confirm or input a path; persist to .env.
    - If non-interactive and not found, return None.
    """
    from .env import get_env_str
    import shutil

    # 1) Env var
    env_val = get_env_str("BLENDER_PATH")
    if env_val:
        p = Path(env_val)
        if _exists_exe(p):
            return p

    # 2) Auto-detect
    for cand in _candidate_paths():
        if _exists_exe(cand):
            # If interactive, confirm and persist; otherwise use without persisting
            if interactive and sys.stdin and sys.stdin.isatty():
                ans = input(f"Use detected Blender at '{cand}'? [Y/n]: ").strip().lower()
                use = ans in ("", "y", "yes")
                if use:
                    os.environ["BLENDER_PATH"] = str(cand)
                    _update_env_file("BLENDER_PATH", str(cand))
                    return cand
            else:
                return cand

    # 3) Prompt user once if possible
    if interactive and sys.stdin and sys.stdin.isatty():
        default_path = (r"C:\\Program Files\\Blender Foundation\\Blender 4.1\\blender.exe" if os.name == 'nt' else "/Applications/Blender.app/Contents/MacOS/Blender")
        entered = input(f"Blender not found. Enter full path to Blender [{default_path}]: ").strip() or default_path
        p = Path(entered.strip('"'))
        if _exists_exe(p):
            os.environ["BLENDER_PATH"] = str(p)
            _update_env_file("BLENDER_PATH", str(p))
            return p
    return None

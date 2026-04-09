"""
Lightweight import/smoke check — portable (no shell scripts).

Must be run with THIS repository’s `.venv` interpreter only (not system Python).

From repository root:
    .venv/Scripts/python.exe tools/dev_smoke.py    (Windows)
    .venv/bin/python3 tools/dev_smoke.py           (macOS / Linux)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_VENV_DIR = ".venv"
_EXPECTED_VENV = (_REPO_ROOT / _VENV_DIR).resolve()


def _venv_python_hint() -> Path:
    if os.name == "nt":
        return _REPO_ROOT / _VENV_DIR / "Scripts" / "python.exe"
    return _REPO_ROOT / _VENV_DIR / "bin" / "python3"


def _venv_check_failed() -> str | None:
    """Return error message if not running under <repo>/.venv."""
    prefix = Path(sys.prefix).resolve()
    if prefix == _EXPECTED_VENV:
        return None
    vp = _venv_python_hint()
    return (
        "This script must run with the project’s .venv interpreter only "
        "(not system / global Python).\n"
        f"  Expected sys.prefix: {_EXPECTED_VENV}\n"
        f"  Actual sys.prefix:   {prefix}\n"
        f"Run for example:\n  {vp} tools/dev_smoke.py"
    )


def main() -> int:
    msg = _venv_check_failed()
    if msg is not None:
        print(msg, file=sys.stderr)
        return 2

    root = str(_REPO_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)
    try:
        import XDM1041_GUI  # noqa: F401
    except ModuleNotFoundError as e:
        vp = _venv_python_hint()
        print(
            f"Import failed ({e}). Install deps with the venv’s pip:\n"
            f"  {vp} -m pip install -r requirements.txt",
            file=sys.stderr,
        )
        return 1

    print("ok: XDM1041_GUI imports (.venv)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

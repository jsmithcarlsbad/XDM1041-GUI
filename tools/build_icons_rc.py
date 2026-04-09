#!/usr/bin/env python3
"""
Build Qt icon resources for the GUI: scan ICONS/*.png → icons.qrc → icons_rc.py.

Run from the repository root with this project’s .venv (so pyside6-rcc is available):

    python tools/build_icons_rc.py

- **Development:** If ``icons_rc.py`` is missing, ``XDM1041_GUI`` loads PNGs from the ``ICONS/`` folder.
- **Windows executable (PyInstaller):** Run this before packaging, then include ``icons_rc.py`` and add
  ``hiddenimports=['icons_rc']`` so the bundle does not need a separate ``ICONS/`` directory.

Requires: PySide6 (provides ``pyside6-rcc``).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ICONS = REPO / "ICONS"
QRC_OUT = REPO / "icons.qrc"
RC_OUT = REPO / "icons_rc.py"


def write_qrc() -> int:
    lines = [
        '<!DOCTYPE RCC><RCC version="1.0">',
        "  <qresource prefix=\"/icons\">",
    ]
    n = 0
    if ICONS.is_dir():
        for p in sorted(ICONS.glob("*.png")):
            rel = p.relative_to(REPO).as_posix()
            lines.append(f'    <file alias="{p.name}">{rel}</file>')
            n += 1
    lines.extend(["  </qresource>", "</RCC>", ""])
    QRC_OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {QRC_OUT} ({n} PNGs)")
    return n


def rcc_argv() -> list[str]:
    if sys.platform == "win32":
        exe = Path(sys.prefix) / "Scripts" / "pyside6-rcc.exe"
    else:
        exe = Path(sys.prefix) / "bin" / "pyside6-rcc"
    if exe.is_file():
        return [str(exe), str(QRC_OUT), "-o", str(RC_OUT)]
    return ["pyside6-rcc", str(QRC_OUT), "-o", str(RC_OUT)]


def main() -> int:
    n = write_qrc()
    if n == 0:
        if RC_OUT.is_file():
            RC_OUT.unlink()
            print(f"Removed {RC_OUT} (pyside6-rcc would produce a broken module with zero assets).")
        print("Add PNGs under ICONS/ then run this script again.")
        return 0
    cmd = rcc_argv()
    print("Running:", " ".join(cmd))
    subprocess.run(cmd, check=True, cwd=str(REPO))
    print(f"Wrote {RC_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""
Crop icons from multimeter sprite sheets.

Default cell size is **48×48** (e.g. Nano Banana output). PNGs are saved at that resolution;
the GUI scales them down (~24×24 in the icon frames) so they stay sharp.

Older 24×24 sheets: pass ``--width 24 --height 24``.

Sheet 1 — **legacy** multimeter_sheet.png (2×4, 48px cells): mode glyphs → ICONS/<mode_id>.png.

Sheet 1 — **OWON panel** multimeter_sheet.png (3×4): twelve front-panel keys; row 0–1 map to modes;
  row 2 (HOLD / REL / AUTO·MAN / MIN·MAX) is skipped. The diode+continuity key saves to both
  ``diode.png`` and ``continuity.png``.

Sheet 2 — **legacy** multimeter_sheet2.png (4×5): ranges with blank cells.

Sheet 2 — **OWON panel** multimeter_sheet_2.png / multimeter_sheet2.png (3×5): fifteen range/unit
  icons (no blank cells) → same ``ICONS/<stem>.png`` names as the legacy sheet2 mapping.

Icon Grid Reference (sheet2, row-major, 5 columns)
  Column 1          Column 2           Column 3        Column 4        Column 5
  mA (Milliamps)    mA (Milliamps)     (unused)        (unused)        (unused)
  µA (Microamps)    10A (High curr.)   kV (Kilovolts)  (unused)        (unused)
  mV (Millivolts)   V (Volts)          kV (Kilovolts)  k (Kilohms)     M (Megaohms)
  Ω (Ohms)          k (Kilohms)        AUTO            MAN (Manual)    HOLD (Data hold)

Unused cells in the PNG are still cropped but no file is written (None in mapping).

Optional: ``--save-width`` / ``--save-height`` resize each crop with LANCZOS before save
(e.g. ``--save-width 24 --save-height 24`` for smaller files on disk).

If saved icons show a **sliver of the next cell**, re-extract with ``--inset 2`` (or 1–3) and/or
``--margin L T R B`` to drop sheet bezel. Grid splits use **integer** column/row boundaries
(no ``round()`` drift). For legacy 2×4 / 4×5 sheets whose PNG size is not an exact multiple of
the nominal cell size, try ``--auto-cell``.

Requires: Pillow (listed in requirements.txt; install only with this repo’s .venv interpreter).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    _repo = Path(__file__).resolve().parents[1]
    _venv_py = _repo / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python3")
    print(
        f"Install dependencies with this repo’s .venv only, e.g.:\n"
        f"  {_venv_py} -m pip install -r {_repo / 'requirements.txt'}",
        file=sys.stderr,
    )
    raise SystemExit(1) from None

# 2 rows × 4 columns, left-to-right then top-to-bottom.
# Each tuple: function id(s) used as filename stem(s) → ICONS/<id>.png
SHEET1_CELLS: list[tuple[str, ...]] = [
    ("ac_volts",),
    ("dc_volts",),
    ("ohms",),
    ("continuity",),
    ("diode",),
    ("capacitance",),
    ("dc_current", "ac_current"),
    ("frequency",),
]

FUNCTIONS_NOT_ON_SHEET1 = ("temperature",)

# 4 rows × 5 columns — same order as “Icon Grid Reference” above.
# None = skip writing (blank cell in sheet).
SHEET2_CELL_IDS: list[str | None] = [
    "range_ma",
    "range_ma_2",
    None,
    None,
    None,
    "range_ua",
    "range_10a",
    "range_kv",
    None,
    None,
    "range_mv",
    "range_v",
    "range_kv_2",
    "range_kohm",
    "range_mohm",
    "range_ohms",
    "range_kohm_2",
    "range_auto",
    "range_manual",
    "range_hold",
]

SHEET2_ROWS = 4
SHEET2_COLS = 5

# OWON-style 3×4 mode sheet (row-major). None = skip cell (e.g. bottom function row).
SHEET1_CELLS_3X4: list[tuple[str, ...] | None] = [
    ("ac_volts",),
    ("dc_volts",),
    ("ohms",),
    ("diode", "continuity"),
    ("capacitance",),
    ("ac_current",),
    ("dc_current",),
    ("frequency",),
    None,
    None,
    None,
    None,
]

# OWON-style 3×5 range sheet (row-major) — matches SHEET2 stems without blank slots.
SHEET2_IDS_3X5: tuple[str, ...] = (
    "range_ma",
    "range_ma_2",
    "range_ua",
    "range_10a",
    "range_kv",
    "range_mv",
    "range_v",
    "range_kv_2",
    "range_kohm",
    "range_mohm",
    "range_ohms",
    "range_kohm_2",
    "range_auto",
    "range_manual",
    "range_hold",
)

# Sprite cell size in the PNG (Nano Banana default); UI scales down for display.
DEFAULT_ICON_CELL = 48


def _grid_crop_boxes(img_w: int, img_h: int, cols: int, rows: int) -> list[tuple[int, int, int, int]]:
    """
    Pixel boxes (left, top, right, bottom) partitioning the image into a cols×rows grid.

    Uses integer division so column/row boundaries never drift (``round()`` on some widths
    can skew cells and pull in a strip of the neighbour icon — especially on OWON panel caps).
    """
    boxes: list[tuple[int, int, int, int]] = []
    for r in range(rows):
        for c in range(cols):
            left = c * img_w // cols
            right = (c + 1) * img_w // cols
            top = r * img_h // rows
            bottom = (r + 1) * img_h // rows
            boxes.append((left, top, right, bottom))
    return boxes


def _inset_box(box: tuple[int, int, int, int], inset: int) -> tuple[int, int, int, int]:
    """Shrink (l,t,r,b) by ``inset`` pixels on each side; no-op if inset <= 0 or would invert."""
    if inset <= 0:
        return box
    l, t, r, b = box
    l2, t2, r2, b2 = l + inset, t + inset, r - inset, b - inset
    if r2 <= l2 or b2 <= t2:
        return box
    return (l2, t2, r2, b2)


def _crop_sheet_margins(sheet: Image.Image, left: int, top: int, right: int, bottom: int) -> Image.Image:
    """Remove L/T/R/B margin pixels before grid split (sheet includes bezel / padding)."""
    if left <= 0 and top <= 0 and right <= 0 and bottom <= 0:
        return sheet
    w, h = sheet.size
    box = (left, top, w - right, h - bottom)
    if box[2] <= box[0] or box[3] <= box[1]:
        return sheet
    return sheet.crop(box)


def _maybe_resize(img: Image.Image, save_w: int | None, save_h: int | None) -> Image.Image:
    if save_w is None or save_h is None:
        return img
    if img.size == (save_w, save_h):
        return img
    return img.resize((save_w, save_h), Image.Resampling.LANCZOS)


def _paired_save_dims(sw: int | None, sh: int | None) -> tuple[int | None, int | None]:
    if sw is not None and sh is None:
        return sw, sw
    if sh is not None and sw is None:
        return sh, sh
    return sw, sh


def find_sheet(names: tuple[str, ...]) -> Path | None:
    """Look in cwd and parent (works from repo root or tools/)."""
    for base in (Path.cwd(), Path.cwd().parent):
        for name in names:
            p = base / name
            if p.is_file():
                return p
    return None


def extract_sheet1(
    sheet_path: Path,
    output_dir: Path,
    icon_w: int = DEFAULT_ICON_CELL,
    icon_h: int = DEFAULT_ICON_CELL,
    save_w: int | None = None,
    save_h: int | None = None,
    *,
    auto_cell: bool = False,
    cell_inset: int = 0,
    margin_ltrb: tuple[int, int, int, int] = (0, 0, 0, 0),
) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    sheet = Image.open(sheet_path)
    sheet = _crop_sheet_margins(sheet, *margin_ltrb)
    w, h = sheet.size
    cols, rows = 4, 2
    if auto_cell:
        icon_w, icon_h = w // cols, h // rows
        if icon_w < 1 or icon_h < 1:
            print(f"Warning: sheet after margins is {w}x{h}; cannot derive cells.", file=sys.stderr)
            return 0
    expected_w, expected_h = icon_w * cols, icon_h * rows
    if w < expected_w or h < expected_h:
        print(
            f"Warning: sheet is {w}x{h}; expected at least {expected_w}x{expected_h}.",
            file=sys.stderr,
        )

    n = 0
    for i, stems in enumerate(SHEET1_CELLS):
        col = i % 4
        row = i // 4
        left = col * icon_w
        top = row * icon_h
        box = (left, top, left + icon_w, top + icon_h)
        box = _inset_box(box, cell_inset)
        icon = _maybe_resize(sheet.crop(box), save_w, save_h)
        for stem in stems:
            out = output_dir / f"{stem}.png"
            icon.save(out)
            print(f"Saved {out}")
            n += 1
    return n


def extract_sheet2(
    sheet_path: Path,
    output_dir: Path,
    icon_w: int = DEFAULT_ICON_CELL,
    icon_h: int = DEFAULT_ICON_CELL,
    save_w: int | None = None,
    save_h: int | None = None,
    *,
    auto_cell: bool = False,
    cell_inset: int = 0,
    margin_ltrb: tuple[int, int, int, int] = (0, 0, 0, 0),
) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    sheet = Image.open(sheet_path)
    sheet = _crop_sheet_margins(sheet, *margin_ltrb)
    w, h = sheet.size
    if auto_cell:
        icon_w, icon_h = w // SHEET2_COLS, h // SHEET2_ROWS
        if icon_w < 1 or icon_h < 1:
            print(f"Warning: sheet2 after margins is {w}x{h}; cannot derive cells.", file=sys.stderr)
            return 0
    expected_w, expected_h = icon_w * SHEET2_COLS, icon_h * SHEET2_ROWS
    if w < expected_w or h < expected_h:
        print(
            f"Warning: sheet2 is {w}x{h}; expected at least {expected_w}x{expected_h}.",
            file=sys.stderr,
        )

    n = 0
    for i, stem in enumerate(SHEET2_CELL_IDS):
        row = i // SHEET2_COLS
        col = i % SHEET2_COLS
        left = col * icon_w
        top = row * icon_h
        box = (left, top, left + icon_w, top + icon_h)
        box = _inset_box(box, cell_inset)
        icon = _maybe_resize(sheet.crop(box), save_w, save_h)
        if stem is None:
            continue
        out = output_dir / f"{stem}.png"
        icon.save(out)
        print(f"Saved {out}")
        n += 1
    return n


def extract_sheet1_3x4(
    sheet_path: Path,
    output_dir: Path,
    save_w: int | None = None,
    save_h: int | None = None,
    *,
    cell_inset: int = 0,
    margin_ltrb: tuple[int, int, int, int] = (0, 0, 0, 0),
) -> int:
    """3×4 panel photo/sprite (e.g. 1408×768): eight mode icons + four skipped bottom keys."""
    output_dir.mkdir(parents=True, exist_ok=True)
    sheet = Image.open(sheet_path)
    sheet = _crop_sheet_margins(sheet, *margin_ltrb)
    w, h = sheet.size
    cols, rows = 4, 3
    boxes = [_inset_box(b, cell_inset) for b in _grid_crop_boxes(w, h, cols, rows)]
    if len(boxes) != len(SHEET1_CELLS_3X4):
        raise RuntimeError("internal: box count mismatch")

    n = 0
    for i, stems in enumerate(SHEET1_CELLS_3X4):
        if stems is None:
            continue
        icon = _maybe_resize(sheet.crop(boxes[i]), save_w, save_h)
        for stem in stems:
            out = output_dir / f"{stem}.png"
            icon.save(out)
            print(f"Saved {out}")
            n += 1
    return n


def extract_sheet2_3x5(
    sheet_path: Path,
    output_dir: Path,
    save_w: int | None = None,
    save_h: int | None = None,
    *,
    cell_inset: int = 0,
    margin_ltrb: tuple[int, int, int, int] = (0, 0, 0, 0),
) -> int:
    """3×5 range sheet (e.g. 1408×768): fifteen icons, same filenames as legacy sheet2."""
    output_dir.mkdir(parents=True, exist_ok=True)
    sheet = Image.open(sheet_path)
    sheet = _crop_sheet_margins(sheet, *margin_ltrb)
    w, h = sheet.size
    cols, rows = 5, 3
    boxes = [_inset_box(b, cell_inset) for b in _grid_crop_boxes(w, h, cols, rows)]
    if len(boxes) != len(SHEET2_IDS_3X5):
        raise RuntimeError("internal: box count mismatch")

    n = 0
    for i, stem in enumerate(SHEET2_IDS_3X5):
        icon = _maybe_resize(sheet.crop(boxes[i]), save_w, save_h)
        out = output_dir / f"{stem}.png"
        icon.save(out)
        print(f"Saved {out}")
        n += 1
    return n


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract multimeter icons from sprite sheets.")
    parser.add_argument(
        "sheet",
        type=Path,
        nargs="?",
        default=None,
        help="Path to sheet PNG (optional if multimeter_sheet.png is in cwd)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("ICONS"),
        help="Output directory (default: ./ICONS)",
    )
    parser.add_argument(
        "--layout",
        choices=("sheet1", "sheet2", "sheet1_3x4", "sheet2_3x5", "auto"),
        default="auto",
        help=(
            "sheet1 = 2×4 modes; sheet2 = 4×5 ranges; sheet1_3x4 / sheet2_3x5 = OWON 1408×768-style grids; "
            "auto = infer from filename and image size"
        ),
    )
    parser.add_argument(
        "--width",
        type=int,
        default=DEFAULT_ICON_CELL,
        help=f"Cell width in the sprite sheet (default: {DEFAULT_ICON_CELL})",
    )
    parser.add_argument(
        "--height",
        type=int,
        default=DEFAULT_ICON_CELL,
        help=f"Cell height in the sprite sheet (default: {DEFAULT_ICON_CELL})",
    )
    parser.add_argument(
        "--save-width",
        type=int,
        default=None,
        metavar="PX",
        help="Optional: resize saved PNG to this width (LANCZOS), e.g. 24",
    )
    parser.add_argument(
        "--save-height",
        type=int,
        default=None,
        metavar="PX",
        help="Optional: resize saved PNG to this height (LANCZOS), e.g. 24",
    )
    parser.add_argument(
        "--inset",
        type=int,
        default=0,
        metavar="PX",
        help="Shrink each cell crop by PX on every side (drops neighbour bleed / gutters). Try 1–3 for tight sheets.",
    )
    parser.add_argument(
        "--margin",
        type=int,
        nargs=4,
        metavar=("L", "T", "R", "B"),
        default=None,
        help="Crop L,T,R,B pixels off the sheet before splitting (bezel / uneven border). Example: --margin 8 8 8 8",
    )
    parser.add_argument(
        "--auto-cell",
        action="store_true",
        help="For sheet1/sheet2 fixed grids: set cell size to image_size//cols_rows (ignore --width/--height).",
    )
    args = parser.parse_args()

    sheet_path = args.sheet
    if sheet_path is None:
        sheet_path = find_sheet(
            (
                "multimeter_sheet.png",
                "multimeter_sheet_2.png",
                "multimeter_sheet2.png",
            )
        )
        if sheet_path is None:
            print(
                "No sheet found. Place multimeter_sheet.png (and multimeter_sheet_2.png) in the repo root,\n"
                "or pass the path explicitly:\n"
                "  python tools/extract_multimeter_icons.py multimeter_sheet.png --layout sheet1_3x4\n"
                "  python tools/extract_multimeter_icons.py multimeter_sheet_2.png --layout sheet2_3x5",
                file=sys.stderr,
            )
            return 1
    else:
        sheet_path = sheet_path.resolve()
        if not sheet_path.is_file():
            print(f"Not found: {sheet_path}", file=sys.stderr)
            return 1

    layout = args.layout
    if layout == "auto":
        low = sheet_path.name.lower()
        if "sheet_2" in low or "sheet2" in low:
            layout = "sheet2_3x5"
        else:
            try:
                probe = Image.open(sheet_path)
                pw, ph = probe.size
                probe.close()
            except OSError:
                pw, ph = (0, 0)
            # Large OWON panel captures (e.g. 1408×768) use 3×4 mode grid; legacy Nano sheets stay small.
            layout = "sheet1_3x4" if pw >= 400 and ph >= 400 else "sheet1"

    out = args.output.resolve()
    sw, sh = _paired_save_dims(args.save_width, args.save_height)
    margin_ltrb: tuple[int, int, int, int] = (
        tuple(args.margin) if args.margin is not None else (0, 0, 0, 0)
    )
    inset = max(0, int(args.inset))
    auto_cell = bool(args.auto_cell)

    if layout == "sheet2":
        n = extract_sheet2(
            sheet_path,
            out,
            args.width,
            args.height,
            sw,
            sh,
            auto_cell=auto_cell,
            cell_inset=inset,
            margin_ltrb=margin_ltrb,
        )
        print(f"Extracted {n} sheet2 icon file(s) into {out}")
    elif layout == "sheet2_3x5":
        n = extract_sheet2_3x5(
            sheet_path, out, sw, sh, cell_inset=inset, margin_ltrb=margin_ltrb
        )
        print(f"Extracted {n} sheet2 (3×5) icon file(s) into {out}")
    elif layout == "sheet1_3x4":
        n = extract_sheet1_3x4(
            sheet_path, out, sw, sh, cell_inset=inset, margin_ltrb=margin_ltrb
        )
        print(f"Extracted {n} sheet1 (3×4) icon file(s) into {out}")
        if FUNCTIONS_NOT_ON_SHEET1:
            print(
                "Note: add manually if needed: "
                + ", ".join(f"ICONS/{name}.png" for name in FUNCTIONS_NOT_ON_SHEET1),
            )
    else:
        n = extract_sheet1(
            sheet_path,
            out,
            args.width,
            args.height,
            sw,
            sh,
            auto_cell=auto_cell,
            cell_inset=inset,
            margin_ltrb=margin_ltrb,
        )
        print(f"Extracted {n} sheet1 icon file(s) into {out}")
        if FUNCTIONS_NOT_ON_SHEET1:
            print(
                "Note: not on this 8-cell sheet — add manually if needed: "
                + ", ".join(f"ICONS/{name}.png" for name in FUNCTIONS_NOT_ON_SHEET1),
            )
    print("Optional — Qt resources for PyInstaller: python tools/build_icons_rc.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""
Generate monochrome meter icons for the XDM1041 GUI (white on transparent RGBA).

Layout matches common DMM dial art (your snipped “Multimeter settings” chart):
  - AC voltage/current: **V~** / **A~** (tilde to the right of the letter).
  - DC voltage/current: **V** or **A** with a **solid horizontal line** and **three short dashes**
    beneath it, stacked to the **right** of the letter (same idea as V— on many meters).

Also aligned with general references:
  https://www.pcbtok.com/multimeter-symbols/
  https://www.thespruce.com/multimeter-symbols-8414239

Range words: **AUTO**, **MAN**. Hold matches many dials as a single **H** (data hold).

Run from the repository root (use this repo’s .venv):

    python tools/generate_meter_icons.py

Requires: Pillow (see requirements.txt).
"""

from __future__ import annotations

import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

REPO = Path(__file__).resolve().parents[1]
ICONS_DIR = REPO / "ICONS"
SIZE = 72
WHITE = (255, 255, 255, 255)
STROKE = 2


def _font_paths() -> list[Path]:
    windir = Path(os.environ.get("WINDIR", "C:/Windows"))
    return [
        windir / "Fonts" / "segoeui.ttf",
        windir / "Fonts" / "arialbd.ttf",
        windir / "Fonts" / "arial.ttf",
        windir / "Fonts" / "seguisym.ttf",
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
        Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
    ]


def _truetype(size: int) -> ImageFont.FreeTypeFont:
    for p in _font_paths():
        if p.is_file():
            try:
                return ImageFont.truetype(str(p), size=size)
            except OSError:
                continue
    return ImageFont.load_default()


def _canvas() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    im = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    return im, ImageDraw.Draw(im)


def _text_mm(
    draw: ImageDraw.ImageDraw,
    xy: tuple[float, float],
    text: str,
    font_size: int,
    fill=WHITE,
) -> None:
    font = _truetype(font_size)
    draw.text(xy, text, font=font, fill=fill, anchor="mm")


def _text_lm(
    draw: ImageDraw.ImageDraw,
    xy: tuple[float, float],
    text: str,
    font: ImageFont.FreeTypeFont,
    fill=WHITE,
) -> None:
    draw.text(xy, text, font=font, fill=fill, anchor="lm")


def _draw_ac_letter_tilde(draw: ImageDraw.ImageDraw, letter: str, letter_px: int, tilde_px: int) -> None:
    """AC voltage/current: letter with ~ immediately to the right (snipped chart / many DMMs)."""
    cy = SIZE / 2 + 1
    font_l = _truetype(letter_px)
    font_t = _truetype(tilde_px)
    w_l = float(draw.textlength(letter, font=font_l))
    w_t = float(draw.textlength("~", font=font_t))
    gap = 1.0
    total = w_l + gap + w_t
    x_l = (SIZE - total) / 2
    _text_lm(draw, (x_l, cy), letter, font_l)
    _text_lm(draw, (x_l + w_l + gap, cy + 1), "~", font_t)


def _draw_dc_letter_marks(draw: ImageDraw.ImageDraw, letter: str, letter_px: int) -> None:
    """
    DC voltage/current: letter with DC glyph to the right — solid bar with three short dashes below
    (stacked), as on the snipped infographic / PCBTok “V with solid and dashed line”.
    """
    cy = SIZE / 2 + 1
    font_l = _truetype(letter_px)
    w_l = float(draw.textlength(letter, font=font_l))
    gap = 5.0
    sym_w = 16.0
    sym_h = 14.0
    total = w_l + gap + sym_w
    x_l = (SIZE - total) / 2
    _text_lm(draw, (x_l, cy), letter, font_l)
    sx = x_l + w_l + gap
    sy = cy - sym_h / 2 + 1
    # Solid horizontal (top of stack)
    draw.line([(sx, sy), (sx + sym_w, sy)], fill=WHITE, width=STROKE)
    # Three short dashes under the solid line
    dash_y = sy + 6
    seg = 3.5
    step = 5.0
    x0 = sx + 1
    for i in range(3):
        xa = x0 + i * step
        draw.line([(xa, dash_y), (xa + seg, dash_y)], fill=WHITE, width=STROKE)


def icon_dc_volts() -> Image.Image:
    im, draw = _canvas()
    _draw_dc_letter_marks(draw, "V", 32)
    return im


def icon_ac_volts() -> Image.Image:
    im, draw = _canvas()
    _draw_ac_letter_tilde(draw, "V", 32, 24)
    return im


def icon_ohms() -> Image.Image:
    im, draw = _canvas()
    _text_mm(draw, (SIZE / 2, SIZE / 2 + 2), "\u03a9", 36)  # Ω
    return im


def icon_dc_current() -> Image.Image:
    im, draw = _canvas()
    _draw_dc_letter_marks(draw, "A", 32)
    return im


def icon_ac_current() -> Image.Image:
    im, draw = _canvas()
    _draw_ac_letter_tilde(draw, "A", 32, 24)
    return im


def icon_frequency() -> Image.Image:
    im, draw = _canvas()
    _text_mm(draw, (SIZE / 2, SIZE / 2 + 2), "Hz", 26)
    return im


def icon_capacitance() -> Image.Image:
    """Farads — large F (matches snipped chart; PCBTok also documents capacitance on the dial)."""
    im, draw = _canvas()
    _text_mm(draw, (SIZE / 2, SIZE / 2 + 2), "F", 34)
    return im


def icon_diode() -> Image.Image:
    """Triangle + bar on horizontal baseline."""
    im, draw = _canvas()
    cy = SIZE // 2 + 2
    left, right = SIZE // 2 - 14, SIZE // 2 + 10
    mid_y = cy - 10
    bot_y = cy + 10
    draw.polygon([(left, mid_y), (right - 6, cy), (left, bot_y)], outline=WHITE, width=STROKE)
    draw.line([(right - 6, mid_y), (right - 6, bot_y)], fill=WHITE, width=STROKE)
    draw.line([(SIZE // 2 - 20, cy), (SIZE // 2 + 18, cy)], fill=WHITE, width=STROKE)
    return im


def icon_continuity() -> Image.Image:
    """Dot on the left; three concentric arcs opening to the right (buzzer / continuity)."""
    im, draw = _canvas()
    ox, oy = int(SIZE * 0.30), SIZE // 2
    draw.ellipse([ox - 4, oy - 4, ox + 4, oy + 4], fill=WHITE)
    for r in (10, 17, 24):
        bbox = [ox - r, oy - r, ox + r, oy + r]
        draw.arc(bbox, start=270, end=90, fill=WHITE, width=STROKE)
    return im


def icon_temperature() -> Image.Image:
    im, draw = _canvas()
    _text_mm(draw, (SIZE / 2, SIZE / 2 + 2), "\u00b0C", 28)  # °C
    return im


def icon_text_line(text: str, size: int) -> Image.Image:
    im, draw = _canvas()
    _text_mm(draw, (SIZE / 2, SIZE / 2 + 1), text, size)
    return im


MODE_ICONS: dict[str, Image.Image] = {
    "dc_volts": icon_dc_volts(),
    "ac_volts": icon_ac_volts(),
    "ohms": icon_ohms(),
    "dc_current": icon_dc_current(),
    "ac_current": icon_ac_current(),
    "frequency": icon_frequency(),
    "capacitance": icon_capacitance(),
    "diode": icon_diode(),
    "continuity": icon_continuity(),
    "temperature": icon_temperature(),
}

# Range stems: units compact; AUTO / MAN full word; hold = single H (dial style).
RANGE_ICONS: dict[str, tuple[str, int]] = {
    "range_ma": ("mA", 24),
    "range_ma_2": ("mA", 24),
    "range_ua": ("\u00b5A", 22),  # µA
    "range_10a": ("10A", 22),
    "range_kv": ("kV", 24),
    "range_mv": ("mV", 24),
    "range_v": ("V", 30),
    "range_kv_2": ("kV", 24),
    "range_kohm": ("k\u03a9", 22),
    "range_mohm": ("M\u03a9", 22),
    "range_ohms": ("\u03a9", 30),
    "range_kohm_2": ("k\u03a9", 22),
    "range_auto": ("AUTO", 15),
    "range_manual": ("MAN", 18),
    "range_hold": ("H", 34),
}


def main() -> int:
    ICONS_DIR.mkdir(parents=True, exist_ok=True)
    n = 0
    for stem, img in MODE_ICONS.items():
        path = ICONS_DIR / f"{stem}.png"
        img.save(path, "PNG")
        print(path)
        n += 1
    for stem, (text, sz) in RANGE_ICONS.items():
        path = ICONS_DIR / f"{stem}.png"
        icon_text_line(text, sz).save(path, "PNG")
        print(path)
        n += 1
    print(f"Wrote {n} PNGs under {ICONS_DIR}")
    print("Optional: python tools/build_icons_rc.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

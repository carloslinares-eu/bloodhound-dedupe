"""Draws the Bloodhound icon (a paw print under a magnifying glass) and writes it to bloodhound/assets/.

The generated files are committed, so this only needs to run after changing the
design. Requires Pillow:  python scripts/generate_icon.py
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw

ASSETS = Path(__file__).resolve().parent.parent / "bloodhound" / "assets"

CANVAS = 1024  # drawn large, then scaled down for smooth edges
BACKGROUND_TOP = (178, 40, 58)
BACKGROUND_BOTTOM = (96, 14, 30)
CREAM = (250, 236, 208)
GOLD = (240, 176, 64)
GOLD_DARK = (176, 116, 30)
GLASS = (255, 255, 255, 46)

LENS_CENTER = (440, 430)
LENS_RADIUS = 268  # to the middle of the ring
RING_WIDTH = 70
ICO_SIZES = [16, 20, 24, 32, 40, 48, 64, 96, 128, 256]


def _rounded_background() -> Image.Image:
    gradient = Image.new("RGBA", (CANVAS, CANVAS))
    pixels = gradient.load()
    for y in range(CANVAS):
        t = y / (CANVAS - 1)
        color = tuple(round(a + (b - a) * t) for a, b in zip(BACKGROUND_TOP, BACKGROUND_BOTTOM)) + (255,)
        for x in range(CANVAS):
            pixels[x, y] = color
    mask = Image.new("L", (CANVAS, CANVAS), 0)
    ImageDraw.Draw(mask).rounded_rectangle((40, 40, CANVAS - 40, CANVAS - 40), radius=210, fill=255)
    background = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    background.paste(gradient, mask=mask)
    return background


def _rotated_ellipse(image: Image.Image, center: tuple[float, float], size: tuple[float, float],
                     angle: float, fill: tuple[int, ...]) -> None:
    """Paste an ellipse of ``size`` rotated by ``angle`` degrees (clockwise) centred on ``center``."""
    width, height = size
    side = int(max(width, height)) + 4
    layer = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    ImageDraw.Draw(layer).ellipse(
        ((side - width) / 2, (side - height) / 2, (side + width) / 2, (side + height) / 2), fill=fill
    )
    layer = layer.rotate(-angle, resample=Image.BICUBIC, expand=True)
    image.alpha_composite(layer, (int(center[0] - layer.width / 2), int(center[1] - layer.height / 2)))


def _thick_segment(draw: ImageDraw.ImageDraw, start: tuple[float, float], end: tuple[float, float],
                   width: float, fill: tuple[int, ...]) -> None:
    """A straight bar with rounded ends."""
    angle = math.atan2(end[1] - start[1], end[0] - start[0])
    dx, dy = math.sin(angle) * width / 2, -math.cos(angle) * width / 2
    draw.polygon(
        [(start[0] + dx, start[1] + dy), (end[0] + dx, end[1] + dy),
         (end[0] - dx, end[1] - dy), (start[0] - dx, start[1] - dy)],
        fill=fill,
    )
    for x, y in (start, end):
        draw.ellipse((x - width / 2, y - width / 2, x + width / 2, y + width / 2), fill=fill)


def draw_icon() -> Image.Image:
    image = _rounded_background()
    draw = ImageDraw.Draw(image)
    cx, cy = LENS_CENTER

    # Handle first, so the lens ring sits on top of its end.
    diagonal = (math.cos(math.radians(45)), math.sin(math.radians(45)))
    handle_start = (cx + diagonal[0] * (LENS_RADIUS + 20), cy + diagonal[1] * (LENS_RADIUS + 20))
    handle_end = (cx + diagonal[0] * (LENS_RADIUS + 300), cy + diagonal[1] * (LENS_RADIUS + 300))
    _thick_segment(draw, handle_start, handle_end, 128, GOLD_DARK)
    _thick_segment(draw, handle_start, handle_end, 104, GOLD)
    collar_end = (cx + diagonal[0] * (LENS_RADIUS + 95), cy + diagonal[1] * (LENS_RADIUS + 95))
    _thick_segment(draw, handle_start, collar_end, 128, CREAM)

    # Glass and ring.
    glass = Image.new("RGBA", image.size, (0, 0, 0, 0))
    inner = LENS_RADIUS - RING_WIDTH / 2
    ImageDraw.Draw(glass).ellipse((cx - inner, cy - inner, cx + inner, cy + inner), fill=GLASS)
    image.alpha_composite(glass)
    outer = LENS_RADIUS + RING_WIDTH / 2
    draw.ellipse((cx - outer, cy - outer, cx + outer, cy + outer), outline=CREAM, width=RING_WIDTH)

    # Paw print inside the lens: a main pad and four toes fanned above it.
    _rotated_ellipse(image, (cx, cy + 70), (210, 170), 0, CREAM)
    for offset_x, offset_y, angle in ((-128, -38, -28), (-50, -118, -8), (50, -118, 8), (128, -38, 28)):
        _rotated_ellipse(image, (cx + offset_x, cy + offset_y), (78, 104), angle, CREAM)
    return image


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    master = draw_icon()
    master.resize((256, 256), Image.LANCZOS).save(ASSETS / "bloodhound.png")
    for size in (48, 64):
        master.resize((size, size), Image.LANCZOS).save(ASSETS / f"bloodhound-{size}.png")
    master.save(ASSETS / "bloodhound.ico", sizes=[(s, s) for s in ICO_SIZES])
    print(f"Icons written to {ASSETS}")


if __name__ == "__main__":
    main()

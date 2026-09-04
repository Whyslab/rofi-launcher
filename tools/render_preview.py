#!/usr/bin/env python3
"""
Draws one preview image per animation preset.

Rofi cannot show an animated preview: its binary only links
gdk_pixbuf_new_from_file_at_scale, the single-frame loader, and has no
gdk_pixbuf_animation_new_from_file at all. A GIF handed to it renders as its
first frame — for a fade-out animation, usually an empty rectangle.

So the preview is a strobe instead: the same window drawn at several points
along the preset's own motion, earlier phases fainter. It is computed from the
preset's numbers — its bezier curve, its duration, its style — not recorded off
the screen, which keeps it deterministic and reproducible in a test.

Run:  python3 tools/render_preview.py [--out DIR]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw

REPO = Path(__file__).resolve().parent.parent
PRESET_DIR = REPO / "data" / "presets"
DEFAULT_OUT = Path.home() / ".cache" / "rofi-launcher" / "anim-previews"

WIDTH, HEIGHT = 320, 200
BG = (16, 16, 16, 255)
FG = (255, 255, 255)
FRAME = (48, 48, 48, 255)

# The window drawn inside the tile, as a fraction of the tile. Kept small enough
# that a ghost trail has somewhere to go, and chunky enough to survive being
# scaled down to an icon.
BOX = (0.46, 0.34, 0.80, 0.66)


def bezier_y(points, t):
    """A cubic bezier from (0,0) to (1,1) with two control points, evaluated
    the way Hyprland's own curves are: t is the parameter, not the x value.

    Close enough for a picture. Sampling by x would need a solve per point and
    would not change what the image communicates."""
    if len(points) < 4:
        return t
    _, y0, _, y1 = points[0], points[1], points[2], points[3]
    u = 1 - t
    return 3 * u * u * t * y0 + 3 * u * t * t * y1 + t ** 3


def _first_curve(preset):
    beziers = preset.get("beziers") or {}
    for points in beziers.values():
        if len(points) >= 4:
            return list(points)
    return [0.0, 0.75, 0.15, 1.0]  # Hyprland's own "default"


def _rect(scale=1.0, dx=0.0, dy=0.0):
    x0, y0, x1, y1 = BOX
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    hw, hh = (x1 - x0) / 2 * scale, (y1 - y0) / 2 * scale
    return (
        (cx - hw + dx) * WIDTH, (cy - hh + dy) * HEIGHT,
        (cx + hw + dx) * WIDTH, (cy + hh + dy) * HEIGHT,
    )


def _ghosts(motion, count, curve):
    """The trailing positions, faintest first. The final window is drawn
    separately — these are only where it has been."""
    out = []
    for i in range(count - 1):
        t = i / max(1, count - 1)
        eased = bezier_y(curve, t)
        alpha = int(45 + 90 * t)
        if motion == "slide":
            out.append((_rect(dx=-0.66 * (1 - eased)), alpha))
        elif motion == "scale":
            # Deliberately drawn growing past the final window rather than up to
            # it: ghosts that stay inside end up hidden underneath the solid
            # rectangle, which is a tile that says nothing.
            out.append((_rect(scale=0.30 + 1.05 * eased), alpha))
    return out


def _draw_ghost(draw, rect, alpha):
    """An outline plus a barely-there fill. Drawn onto a transparent overlay:
    PIL's rectangle writes the colour it is given rather than blending it, so
    the alpha has to end up in the pixels and be composited afterwards."""
    draw.rectangle(rect, fill=FG + (max(8, alpha // 6),), outline=FG + (alpha,), width=3)


def _draw_dust(draw, rect, preset):
    """The pixel cloud, shaped by the dissolve plugin's own numbers.

    block_size sets how chunky the debris is, spread how far sideways it goes,
    rise how far up, and dust_life how many particles are still around — so two
    dissolve presets that differ only in those numbers get visibly different
    pictures, which is the entire point of showing a picture."""
    plugin = preset.get("dissolve") or {}
    size = max(2, int(plugin.get("block_size", 4)))
    spread = float(plugin.get("spread", 0.55))
    rise = float(plugin.get("rise", 200))
    life = float(plugin.get("dust_life", 0.35))

    x0, y0, x1, y1 = rect
    width, height = x1 - x0, y1 - y0
    count = int(90 + 260 * life)
    reach_x = width * (0.35 + spread)
    reach_y = height * (rise / 200.0) * 0.9

    rng = _Rng(seed=int(size * 131 + spread * 977 + rise))
    for _ in range(count):
        # Particles leave from the right-hand side and travel up and out, so the
        # window still reads as a window rather than as noise.
        origin = rng.next_float() ** 0.6
        px = x0 + width * (0.45 + 0.55 * rng.next_float()) + origin * reach_x
        py = y0 + height * rng.next_float() - origin * reach_y
        fade = int(230 * (1 - origin) ** 1.4)
        if fade < 10:
            continue
        jitter = size * (0.7 + 0.6 * rng.next_float())
        draw.rectangle([px, py, px + jitter, py + jitter], fill=FG + (fade,))


class _Rng:
    """A tiny deterministic generator.

    random.Random would also be reproducible, but only as long as CPython's
    implementation of it never changes; the image is compared byte for byte in a
    test, so the arithmetic is spelled out here instead."""

    def __init__(self, seed):
        self.state = (seed * 2654435761) & 0xFFFFFFFF or 1

    def next_float(self):
        self.state ^= (self.state << 13) & 0xFFFFFFFF
        self.state ^= self.state >> 17
        self.state ^= (self.state << 5) & 0xFFFFFFFF
        self.state &= 0xFFFFFFFF
        return self.state / 0xFFFFFFFF


def render(preset):
    spec = preset.get("preview") or {}
    motion = spec.get("motion", "scale")
    count = max(1, int(spec.get("phases", 5)))
    curve = _first_curve(preset)

    image = Image.new("RGBA", (WIDTH, HEIGHT), BG)
    ImageDraw.Draw(image).rectangle([0, 0, WIDTH - 1, HEIGHT - 1], outline=FRAME)
    window = _rect()

    # Translucent parts go onto their own layer and are composited in. Drawing
    # them straight onto the image would paint them opaque — PIL's rectangle
    # does not blend, whatever draw mode it is given.
    trail = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    trail_draw = ImageDraw.Draw(trail)
    for rect, alpha in _ghosts(motion, count, curve):
        _draw_ghost(trail_draw, rect, alpha)
    if motion == "dissolve":
        _draw_dust(trail_draw, window, preset)
    image = Image.alpha_composite(image, trail)

    # The window itself is opaque and lands on top of its own trail.
    draw = ImageDraw.Draw(image)
    draw.rectangle(window, fill=FG)

    if motion == "none":
        # Nothing moves, so say so with a shape rather than leaving a tile
        # indistinguishable from "scale" with its trail cropped off.
        cx = (window[0] + window[2]) / 2
        cy = (window[1] + window[3]) / 2
        draw.line([cx - 30, cy, cx + 30, cy], fill=BG[:3], width=9)

    return image.convert("RGB")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    count = 0
    for path in sorted(PRESET_DIR.glob("*.json")):
        try:
            preset = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            print(f"пропущен {path.name}: {exc}", file=sys.stderr)
            continue
        target = args.out / f"{preset['id']}.png"
        # optimize=False and no timestamp chunk: the same preset must produce
        # the same bytes on every run, or the determinism test is meaningless.
        render(preset).save(target, "PNG", optimize=False)
        count += 1
    print(f"{count} превью → {args.out}")


if __name__ == "__main__":
    main()

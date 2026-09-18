#!/usr/bin/env python3
"""Generate audioPrime application icons (.icns for macOS, .ico for Windows).

Produces:
    assets/audioPrime.icns   — macOS app icon
    assets/audioPrime.ico    — Windows app icon
    assets/icon_1024.png     — High-res PNG (for Linux / general use)

Design: Dark rounded-square background with symmetric audio waveform bars
in steel-blue, evoking both audio processing and professional quality.
"""

import math
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"

# ── Colors (from the app's "grey" theme palette) ──────────────────────────────
BG_DARK = (22, 30, 42)       # deep navy — icon background (bottom)
BG_MID = (30, 42, 56)        # slightly lighter — icon background (top)
BAR_COLOR = (74, 111, 165)   # steel-blue #4a6fa5 — waveform bars
BAR_HIGHLIGHT = (107, 140, 186)  # lighter steel-blue #6b8cba — bar top highlight
GLOW_COLOR = (74, 111, 165, 40)  # subtle glow behind bars


def _round_rect(draw: ImageDraw.Draw, xy, radius, fill):
    """Draw a rounded rectangle."""
    x0, y0, x1, y1 = xy
    draw.rounded_rectangle(xy, radius=radius, fill=fill)


def _render_icon(size: int) -> Image.Image:
    """Render the icon at the given pixel size."""
    # Work at 4x for antialiasing, then downscale
    s = max(size * 4, 1024)
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # ── Background: rounded square with subtle gradient ──────────────────
    corner_radius = int(s * 0.22)
    # Draw gradient by layering horizontal strips
    for y in range(s):
        t = y / s
        r = int(BG_DARK[0] + (BG_MID[0] - BG_DARK[0]) * (1 - t))
        g = int(BG_DARK[1] + (BG_MID[1] - BG_DARK[1]) * (1 - t))
        b = int(BG_DARK[2] + (BG_MID[2] - BG_DARK[2]) * (1 - t))
        draw.line([(0, y), (s - 1, y)], fill=(r, g, b, 255))

    # Mask to rounded rectangle
    mask = Image.new("L", (s, s), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle(
        [0, 0, s - 1, s - 1], radius=corner_radius, fill=255
    )
    img.putalpha(mask)

    # ── Waveform bars ────────────────────────────────────────────────────
    # Symmetric pattern of bar heights (normalized 0-1)
    # Creates an aesthetically pleasing audio waveform silhouette
    bar_heights = [
        0.25, 0.45, 0.35, 0.65, 0.50, 0.85, 0.70, 1.0,
        0.70, 0.85, 0.50, 0.65, 0.35, 0.45, 0.25,
    ]
    num_bars = len(bar_heights)

    # Layout: bars centered in the icon
    bar_region_w = s * 0.68   # total width for all bars
    bar_region_h = s * 0.52   # max bar height
    bar_region_x = (s - bar_region_w) / 2
    bar_region_y_center = s * 0.48  # vertical center of bars

    gap_ratio = 0.35  # gap as fraction of bar+gap unit
    unit_w = bar_region_w / (num_bars + (num_bars - 1) * gap_ratio)
    bar_w = unit_w
    gap_w = unit_w * gap_ratio
    bar_radius = int(bar_w * 0.35)

    # Draw subtle glow layer behind bars
    glow_layer = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow_layer)

    for i, h in enumerate(bar_heights):
        bx = bar_region_x + i * (bar_w + gap_w)
        bar_h = bar_region_h * h
        by_top = bar_region_y_center - bar_h / 2
        by_bot = bar_region_y_center + bar_h / 2

        # Glow (slightly wider, blurred later)
        glow_expand = bar_w * 0.3
        glow_draw.rounded_rectangle(
            [bx - glow_expand, by_top - glow_expand,
             bx + bar_w + glow_expand, by_bot + glow_expand],
            radius=bar_radius + int(glow_expand),
            fill=GLOW_COLOR,
        )

    # Blur the glow
    glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(radius=s * 0.02))
    img = Image.alpha_composite(img, glow_layer)
    draw = ImageDraw.Draw(img)

    # Draw the actual bars
    for i, h in enumerate(bar_heights):
        bx = bar_region_x + i * (bar_w + gap_w)
        bar_h = bar_region_h * h
        by_top = bar_region_y_center - bar_h / 2
        by_bot = bar_region_y_center + bar_h / 2

        # Main bar body
        draw.rounded_rectangle(
            [bx, by_top, bx + bar_w, by_bot],
            radius=bar_radius,
            fill=BAR_COLOR,
        )

        # Top highlight gradient (lighter at top 30%)
        highlight_h = bar_h * 0.30
        for dy in range(int(highlight_h)):
            t = 1 - (dy / highlight_h)  # 1 at top, 0 at bottom of highlight
            alpha = int(80 * t)
            yr = by_top + dy
            # Only draw within the rounded rect area
            draw.rounded_rectangle(
                [bx, yr, bx + bar_w, yr + 1],
                radius=min(bar_radius, int(bar_w * 0.35)),
                fill=(
                    BAR_HIGHLIGHT[0], BAR_HIGHLIGHT[1], BAR_HIGHLIGHT[2], alpha
                ),
            )

    # ── Downscale with high-quality resampling ───────────────────────────
    if s != size:
        img = img.resize((size, size), Image.LANCZOS)

    return img


def generate_icns(icon_1024: Image.Image) -> Path:
    """Create .icns from a 1024px master image using macOS iconutil."""
    tmpdir = Path(tempfile.mkdtemp())
    iconset = tmpdir / "audioPrime.iconset"
    iconset.mkdir()

    sizes = [16, 32, 64, 128, 256, 512, 1024]
    for sz in sizes:
        resized = icon_1024.resize((sz, sz), Image.LANCZOS)
        # Standard resolution
        if sz <= 512:
            resized.save(iconset / f"icon_{sz}x{sz}.png")
        # @2x (retina) — the 32px file is icon_16x16@2x, etc.
        if sz >= 32:
            half = sz // 2
            resized.save(iconset / f"icon_{half}x{half}@2x.png")

    out = ASSETS / "audioPrime.icns"
    result = subprocess.run(
        ["iconutil", "-c", "icns", str(iconset), "-o", str(out)],
        capture_output=True, text=True,
    )
    shutil.rmtree(tmpdir)
    if result.returncode != 0:
        print(f"iconutil failed: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    return out


def generate_ico(icon_1024: Image.Image) -> Path:
    """Create .ico with multiple sizes embedded."""
    sizes = [16, 32, 48, 64, 128, 256]
    frames = []
    for sz in sizes:
        frame = icon_1024.resize((sz, sz), Image.LANCZOS).convert("RGBA")
        frames.append(frame)

    out = ASSETS / "audioPrime.ico"
    frames[-1].save(
        out, format="ICO", append_images=frames[:-1],
        sizes=[(sz, sz) for sz in sizes],
    )
    return out


def main():
    ASSETS.mkdir(exist_ok=True)

    print("Rendering 1024x1024 master icon...")
    icon_1024 = _render_icon(1024)

    # Save high-res PNG
    png_path = ASSETS / "icon_1024.png"
    icon_1024.save(png_path, "PNG")
    print(f"  Saved {png_path}")

    # macOS .icns
    if shutil.which("iconutil"):
        icns_path = generate_icns(icon_1024)
        print(f"  Saved {icns_path}")
    else:
        print("  Skipped .icns (iconutil not found — not macOS)")

    # Windows .ico
    ico_path = generate_ico(icon_1024)
    print(f"  Saved {ico_path}")

    print("Done.")


if __name__ == "__main__":
    main()

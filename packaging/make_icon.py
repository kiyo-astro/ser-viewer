"""Generate the application icon (PNG, ICO and ICNS) from code.

Run from the project root::

    python packaging/make_icon.py
"""

from __future__ import annotations

import math
import os
import shutil
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw

SIZE = 1024
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ICON_DIR = os.path.join(HERE, "icons")
RESOURCE_DIR = os.path.join(ROOT, "serview", "resources")


def render(size: int = SIZE) -> Image.Image:
    """A limb-darkened planet on a night-sky rounded square, with a play mark."""
    scale = size / 1024
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    # Background: rounded square with a vertical gradient.
    top, bottom = np.array([26, 32, 54]), np.array([9, 11, 20])
    gradient = np.linspace(0.0, 1.0, size)[:, None]
    background = (top * (1 - gradient) + bottom * gradient).astype(np.uint8)
    background = np.repeat(background[:, None, :], size, axis=1)
    layer = Image.fromarray(background, "RGB").convert("RGBA")
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, size - 1, size - 1), radius=int(220 * scale), fill=255)
    image.paste(layer, (0, 0), mask)

    # Stars.
    rng = np.random.default_rng(7)
    for _ in range(70):
        x, y = rng.uniform(60 * scale, size - 60 * scale, 2)
        radius = rng.uniform(1.5, 4.0) * scale
        alpha = int(rng.uniform(70, 210))
        draw.ellipse((x - radius, y - radius, x + radius, y + radius),
                     fill=(255, 255, 255, alpha))

    # The planet, drawn with limb darkening and a couple of belts.
    centre = size * 0.47
    radius = size * 0.30
    yy, xx = np.mgrid[0:size, 0:size]
    r = np.hypot(xx - centre, yy - centre) / radius
    mu = np.sqrt(np.clip(1 - r**2, 0, 1))
    brightness = np.where(r <= 1, 0.45 + 0.55 * mu, 0.0)
    belts = 1.0 + 0.13 * np.sin((yy - centre) / (radius * 0.19) + 0.6)
    brightness = np.clip(brightness * belts, 0, 1)
    tint = np.array([1.0, 0.78, 0.52])
    disc = (brightness[..., None] * tint * 255).astype(np.uint8)
    # Hard limb with roughly one pixel of antialiasing.
    alpha = np.clip((1.0 - r) * radius, 0.0, 1.0) * 255.0
    alpha = alpha.astype(np.uint8)
    planet = Image.fromarray(np.dstack([disc, alpha]), "RGBA")
    image.alpha_composite(planet)

    # Play triangle in the lower right corner, on a translucent disc.
    badge = size * 0.20
    bx, by = size * 0.755, size * 0.775
    draw.ellipse((bx - badge, by - badge, bx + badge, by + badge),
                 fill=(20, 24, 38, 225), outline=(235, 238, 250, 235),
                 width=int(10 * scale))
    tip = badge * 0.52
    draw.polygon(
        [(bx - tip * 0.55, by - tip), (bx - tip * 0.55, by + tip), (bx + tip, by)],
        fill=(235, 238, 250, 240),
    )
    return image


def main() -> int:
    os.makedirs(ICON_DIR, exist_ok=True)
    os.makedirs(RESOURCE_DIR, exist_ok=True)
    master = render()

    png_path = os.path.join(RESOURCE_DIR, "serview.png")
    master.resize((512, 512), Image.LANCZOS).save(png_path)

    ico_path = os.path.join(ICON_DIR, "serview.ico")
    master.save(ico_path, sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])

    icns_path = os.path.join(ICON_DIR, "serview.icns")
    if sys.platform == "darwin" and shutil.which("iconutil"):
        iconset = os.path.join(ICON_DIR, "serview.iconset")
        shutil.rmtree(iconset, ignore_errors=True)
        os.makedirs(iconset)
        for size in (16, 32, 64, 128, 256, 512):
            master.resize((size, size), Image.LANCZOS).save(
                os.path.join(iconset, f"icon_{size}x{size}.png"))
            master.resize((size * 2, size * 2), Image.LANCZOS).save(
                os.path.join(iconset, f"icon_{size}x{size}@2x.png"))
        subprocess.run(["iconutil", "-c", "icns", iconset, "-o", icns_path], check=True)
        shutil.rmtree(iconset, ignore_errors=True)
    else:
        master.resize((512, 512), Image.LANCZOS).save(
            os.path.join(ICON_DIR, "serview_512.png"))

    print(f"wrote {png_path}, {ico_path}"
          + (f" and {icns_path}" if os.path.exists(icns_path) else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

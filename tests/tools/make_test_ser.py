"""Generate synthetic SER files for testing and for trying the player out."""

from __future__ import annotations

import argparse
import math
from datetime import datetime, timedelta, timezone

import numpy as np

from serview.ser import ColourID, SerWriter


def _limb_darkened_disc(h: int, w: int, cx: float, cy: float, radius: float) -> np.ndarray:
    yy, xx = np.mgrid[0:h, 0:w]
    r = np.hypot(xx - cx, yy - cy) / radius
    mu = np.sqrt(np.clip(1.0 - r**2, 0.0, 1.0))
    disc = np.where(r <= 1.0, 0.35 + 0.65 * mu, 0.0)
    return disc


def synth_frame(h: int, w: int, index: int, frames: int, seed: int = 0) -> np.ndarray:
    """A limb-darkened planetary disc that wobbles like real seeing."""
    rng = np.random.default_rng(seed + index)
    phase = 2 * math.pi * index / max(frames, 1)
    cx = w / 2 + 0.02 * w * math.sin(3 * phase) + rng.normal(0, 0.004 * w)
    cy = h / 2 + 0.02 * h * math.cos(2 * phase) + rng.normal(0, 0.004 * h)
    radius = min(h, w) * 0.34
    image = _limb_darkened_disc(h, w, cx, cy, radius)

    # A couple of surface features so alignment/processing is visible.
    for fx, fy, fr, amp in ((0.42, 0.45, 0.06, -0.25), (0.60, 0.58, 0.04, 0.18)):
        yy, xx = np.mgrid[0:h, 0:w]
        d = np.hypot(xx - (cx + (fx - 0.5) * 2 * radius), yy - (cy + (fy - 0.5) * 2 * radius))
        image += amp * np.exp(-(d**2) / (2 * (fr * radius) ** 2)) * (image > 0)

    image += rng.normal(0, 0.01, size=image.shape)
    return np.clip(image, 0, 1)


def make_ser(path: str, width: int, height: int, frames: int, depth: int,
             colour: ColourID, fps: float = 30.0) -> str:
    max_value = (1 << depth) - 1
    dtype = np.uint8 if depth <= 8 else np.uint16
    start = datetime(2026, 3, 14, 21, 30, 0, tzinfo=timezone.utc)
    with SerWriter(
        path, width, height, colour_id=colour,
        pixel_depth=depth if depth <= 8 else 16,
        observer="Test Observer", instrument="Synthetic Camera",
        telescope="SER Viewer Test Suite", start_time=start,
    ) as writer:
        for i in range(frames):
            base = synth_frame(height, width, i, frames)
            if colour.is_colour:
                rgb = np.stack([base, base * 0.82, base * 0.6], axis=-1)
                data = (rgb * max_value).astype(dtype)
            elif colour.is_bayer:
                rgb = np.stack([base, base * 0.82, base * 0.6], axis=-1)
                data = _mosaic(rgb, colour)
                data = (data * max_value).astype(dtype)
            else:
                data = (base * max_value).astype(dtype)
            writer.add_frame(data, timestamp=start + timedelta(seconds=i / fps))
    return path


def _mosaic(rgb: np.ndarray, colour: ColourID) -> np.ndarray:
    """Turn an RGB image into a Bayer mosaic of the given pattern."""
    pattern = colour.bayer_pattern or "RGGB"
    h, w, _ = rgb.shape
    out = np.zeros((h, w), dtype=rgb.dtype)
    channel_index = {"R": 0, "G": 1, "B": 2}
    for pos, letter in enumerate(pattern):
        dy, dx = divmod(pos, 2)
        out[dy::2, dx::2] = rgb[dy::2, dx::2, channel_index.get(letter, 1)]
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output")
    parser.add_argument("--width", type=int, default=320)
    parser.add_argument("--height", type=int, default=240)
    parser.add_argument("--frames", type=int, default=60)
    parser.add_argument("--depth", type=int, default=8, choices=[8, 12, 16])
    parser.add_argument("--colour", default="MONO",
                        choices=[c.name for c in ColourID])
    parser.add_argument("--fps", type=float, default=30.0)
    args = parser.parse_args()
    path = make_ser(args.output, args.width, args.height, args.frames,
                    args.depth, ColourID[args.colour], args.fps)
    print(f"wrote {path}")


if __name__ == "__main__":
    main()

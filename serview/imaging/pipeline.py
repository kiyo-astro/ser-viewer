"""Frame processing: debayer, gain/gamma, colour balance, saturation, crop."""

from __future__ import annotations

from dataclasses import dataclass, field, replace

import cv2
import numpy as np

from ..ser.format import ColourID

#: OpenCV names Bayer conversions after the 2x2 block starting at the second
#: row/column, so the sensor pattern maps to a "reversed" OpenCV code.
_BAYER_TO_CV = {
    "RGGB": cv2.COLOR_BayerBG2RGB,
    "BGGR": cv2.COLOR_BayerRG2RGB,
    "GRBG": cv2.COLOR_BayerGB2RGB,
    "GBRG": cv2.COLOR_BayerGR2RGB,
}

MONO_MODES = {
    "luminance": "Luminance (0.299R + 0.587G + 0.114B)",
    "average": "Average of R, G and B",
    "r": "Red channel only",
    "g": "Green channel only",
    "b": "Blue channel only",
    "rg": "Red and green channels",
    "rb": "Red and blue channels",
    "gb": "Green and blue channels",
}


@dataclass
class CropRect:
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0

    @property
    def valid(self) -> bool:
        return self.width > 0 and self.height > 0

    def clamped(self, width: int, height: int) -> "CropRect":
        x = max(0, min(self.x, width - 1))
        y = max(0, min(self.y, height - 1))
        w = max(1, min(self.width, width - x))
        h = max(1, min(self.height, height - y))
        return CropRect(x, y, w, h)


@dataclass
class ProcessingOptions:
    """Everything the processing dialog can change.

    The defaults are a pass-through pipeline apart from debayering, which is on
    so that colour cameras look right straight away.
    """

    # Debayer
    debayer: bool = True
    bayer_override: str | None = None  # None -> use the pattern from the header

    # Gain and gamma
    gain: float = 1.0            # linear multiplier
    gamma: float = 1.0           # output = input ** (1 / gamma)
    black_level: float = 0.0     # subtracted before gain, in 0..1
    auto_stretch: bool = False   # per-frame min/max stretch (display aid)

    # Colour
    saturation: float = 1.0
    red_balance: float = 1.0
    green_balance: float = 1.0
    blue_balance: float = 1.0
    red_align: tuple[int, int] = (0, 0)   # (dx, dy) in pixels
    blue_align: tuple[int, int] = (0, 0)

    # Monochrome conversion
    to_mono: bool = False
    mono_mode: str = "luminance"

    # Misc
    invert: bool = False
    crop: CropRect = field(default_factory=CropRect)
    flip_horizontal: bool = False
    flip_vertical: bool = False
    rotation: int = 0  # 0, 90, 180 or 270 degrees clockwise

    def is_identity(self) -> bool:
        """True when nothing but debayering would change the pixel values."""
        return (
            self.gain == 1.0
            and self.gamma == 1.0
            and self.black_level == 0.0
            and not self.auto_stretch
            and self.saturation == 1.0
            and self.red_balance == self.green_balance == self.blue_balance == 1.0
            and self.red_align == (0, 0)
            and self.blue_align == (0, 0)
            and not self.to_mono
            and not self.invert
            and not self.crop.valid
            and not self.flip_horizontal
            and not self.flip_vertical
            and self.rotation == 0
        )

    def copy(self) -> "ProcessingOptions":
        return replace(self, crop=CropRect(**vars(self.crop)))


def debayer(frame: np.ndarray, colour_id: ColourID,
            override: str | None = None) -> np.ndarray:
    """Demosaic a Bayer frame into RGB. CMY patterns are approximated."""
    pattern = override or colour_id.bayer_pattern
    if pattern is None:
        raise ValueError(f"{colour_id.label} is not a Bayer format")
    code = _BAYER_TO_CV.get(pattern)
    if code is not None:
        return cv2.cvtColor(frame, code)
    # CYYM/YCMY/YMCY/MYYC: demosaic on the matching RGB grid, then convert the
    # complementary colours to RGB.  Rare in practice but better than failing.
    fallback = {"CYYM": "GBRG", "YCMY": "BGGR", "YMCY": "RGGB", "MYYC": "GRBG"}
    cmy = cv2.cvtColor(frame, _BAYER_TO_CV[fallback.get(pattern, "RGGB")])
    scale = np.iinfo(cmy.dtype).max if cmy.dtype.kind == "u" else 1.0
    inv = scale - cmy.astype(np.float32)
    rgb = np.stack([inv[..., 2], inv[..., 1], inv[..., 0]], axis=-1)
    return np.clip(rgb, 0, scale).astype(cmy.dtype)


def _shift(plane: np.ndarray, dx: int, dy: int) -> np.ndarray:
    if dx == 0 and dy == 0:
        return plane
    out = np.zeros_like(plane)
    h, w = plane.shape
    xs, xd = (0, dx) if dx >= 0 else (-dx, 0)
    ys, yd = (0, dy) if dy >= 0 else (-dy, 0)
    cw, ch = w - abs(dx), h - abs(dy)
    if cw > 0 and ch > 0:
        out[yd:yd + ch, xd:xd + cw] = plane[ys:ys + ch, xs:xs + cw]
    return out


def to_float(frame: np.ndarray, pixel_depth: int) -> np.ndarray:
    """Scale integer pixel data to float32 in the 0..1 range."""
    if frame.dtype.kind == "f":
        return frame.astype(np.float32, copy=False)
    max_value = float((1 << max(pixel_depth, 1)) - 1)
    return frame.astype(np.float32) / max_value


def apply_mono(rgb: np.ndarray, mode: str) -> np.ndarray:
    """Collapse an RGB image to a single plane."""
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    if mode == "average":
        return (r + g + b) / 3.0
    if mode == "r":
        return r
    if mode == "g":
        return g
    if mode == "b":
        return b
    if mode == "rg":
        return (r + g) / 2.0
    if mode == "rb":
        return (r + b) / 2.0
    if mode == "gb":
        return (g + b) / 2.0
    return 0.299 * r + 0.587 * g + 0.114 * b


class FrameProcessor:
    """Applies :class:`ProcessingOptions` to frames of one SER file."""

    def __init__(self, colour_id: ColourID, pixel_depth: int,
                 options: ProcessingOptions | None = None):
        self.colour_id = colour_id
        self.pixel_depth = pixel_depth
        self.options = options or ProcessingOptions()

    # -- helpers ---------------------------------------------------------
    @property
    def produces_colour(self) -> bool:
        opts = self.options
        if opts.to_mono:
            return False
        if self.colour_id.is_colour:
            return True
        return self.colour_id.is_bayer and opts.debayer

    def crop_frame(self, frame: np.ndarray) -> np.ndarray:
        crop = self.options.crop
        if not crop.valid:
            return frame
        h, w = frame.shape[:2]
        c = crop.clamped(w, h)
        if self.colour_id.is_bayer and self.options.debayer:
            # Keep the Bayer phase intact by snapping to even coordinates.
            c = CropRect(c.x - (c.x % 2), c.y - (c.y % 2),
                         c.width - (c.width % 2), c.height - (c.height % 2)).clamped(w, h)
        return frame[c.y:c.y + c.height, c.x:c.x + c.width]

    def demosaic(self, frame: np.ndarray) -> np.ndarray:
        """Debayer if needed; returns mono ``(h,w)`` or RGB ``(h,w,3)``."""
        opts = self.options
        if self.colour_id.is_bayer and opts.debayer and frame.ndim == 2:
            return debayer(frame, self.colour_id, opts.bayer_override)
        return frame

    # -- the pipeline ----------------------------------------------------
    def process(self, frame: np.ndarray, out_dtype: type | None = None) -> np.ndarray:
        """Run the full pipeline and return integer pixel data.

        ``out_dtype`` defaults to the input dtype.  The value range of the
        result spans the full range of ``out_dtype``.
        """
        source_dtype = frame.dtype
        image = self.crop_frame(frame)
        image = self.demosaic(image)
        work = self.process_float(image)
        target = np.dtype(out_dtype or source_dtype)
        if target.kind == "f":
            return work.astype(target, copy=False)
        max_value = float(np.iinfo(target).max)
        return np.clip(work * max_value + 0.5, 0, max_value).astype(target)

    def process_float(self, image: np.ndarray) -> np.ndarray:
        """Pipeline stages that work on 0..1 floats (image already debayered)."""
        opts = self.options
        work = to_float(image, self.pixel_depth)
        is_colour = work.ndim == 3

        if is_colour and (opts.red_align != (0, 0) or opts.blue_align != (0, 0)):
            work = np.stack(
                [
                    _shift(work[..., 0], *opts.red_align),
                    work[..., 1],
                    _shift(work[..., 2], *opts.blue_align),
                ],
                axis=-1,
            )

        if is_colour and (opts.red_balance, opts.green_balance, opts.blue_balance) != (1.0, 1.0, 1.0):
            work = work * np.array(
                [opts.red_balance, opts.green_balance, opts.blue_balance], dtype=np.float32
            )

        if opts.auto_stretch:
            lo, hi = float(np.min(work)), float(np.max(work))
            if hi > lo:
                work = (work - lo) / (hi - lo)
        elif opts.black_level:
            work = (work - opts.black_level) / max(1e-6, 1.0 - opts.black_level)

        if opts.gain != 1.0:
            work = work * opts.gain

        work = np.clip(work, 0.0, 1.0)

        if opts.gamma != 1.0:
            work = np.power(work, 1.0 / max(opts.gamma, 1e-3))

        if is_colour and opts.saturation != 1.0:
            luma = apply_mono(work, "luminance")[..., None]
            work = np.clip(luma + (work - luma) * opts.saturation, 0.0, 1.0)

        if is_colour and opts.to_mono:
            work = apply_mono(work, opts.mono_mode)

        if opts.invert:
            work = 1.0 - work

        if opts.flip_horizontal:
            work = work[:, ::-1]
        if opts.flip_vertical:
            work = work[::-1, :]
        if opts.rotation:
            work = np.rot90(work, k=-(opts.rotation // 90) % 4)

        return np.ascontiguousarray(np.clip(work, 0.0, 1.0))

    def to_display(self, frame: np.ndarray) -> np.ndarray:
        """8 bit RGB or greyscale image ready to be shown on screen."""
        return self.process(frame, out_dtype=np.uint8)

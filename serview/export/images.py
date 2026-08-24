"""Still image export (PNG, TIFF, BMP, JPEG)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Sequence

import cv2
import numpy as np

from ..imaging.pipeline import FrameProcessor
from ..ser.reader import SerReader
from .fits import ExportCancelled, ProgressCallback

#: extension -> whether 16 bit output is possible
IMAGE_FORMATS = {
    ".png": True,
    ".tif": True,
    ".tiff": True,
    ".bmp": False,
    ".jpg": False,
    ".jpeg": False,
}


@dataclass
class ImageExportOptions:
    extension: str = ".png"
    bit_depth: int = 8            # 8 or 16 (16 only for PNG/TIFF)
    jpeg_quality: int = 95
    resize: tuple[int, int] | None = None
    single_file: bool = False     # export exactly one frame to ``path``


class ImageExporter:
    def __init__(self, reader: SerReader, processor: FrameProcessor,
                 options: ImageExportOptions | None = None):
        self.reader = reader
        self.processor = processor
        self.options = options or ImageExportOptions()

    def _render(self, index: int) -> np.ndarray:
        opts = self.options
        supports16 = IMAGE_FORMATS.get(opts.extension.lower(), False)
        dtype = np.uint16 if (opts.bit_depth == 16 and supports16) else np.uint8
        image = self.processor.process(self.reader.frame(index), out_dtype=dtype)
        if opts.resize:
            interp = cv2.INTER_AREA if opts.resize[0] < image.shape[1] else cv2.INTER_CUBIC
            image = cv2.resize(image, opts.resize, interpolation=interp)
        if image.ndim == 3:  # OpenCV writes BGR
            image = image[:, :, ::-1]
        return np.ascontiguousarray(image)

    def _params(self) -> list[int]:
        ext = self.options.extension.lower()
        if ext in (".jpg", ".jpeg"):
            return [cv2.IMWRITE_JPEG_QUALITY, int(self.options.jpeg_quality)]
        if ext == ".png":
            return [cv2.IMWRITE_PNG_COMPRESSION, 5]
        return []

    def export(self, path: str, indices: Sequence[int],
               progress: ProgressCallback | None = None) -> list[str]:
        indices = list(indices)
        base, ext = os.path.splitext(path)
        if ext.lower() not in IMAGE_FORMATS:
            ext = self.options.extension
        digits = max(5, len(str(self.reader.frame_count)))
        written: list[str] = []
        for position, index in enumerate(indices):
            image = self._render(index)
            if self.options.single_file and len(indices) == 1:
                out = base + ext
            else:
                out = f"{base}_{index + 1:0{digits}d}{ext}"
            if not cv2.imwrite(out, image, self._params()):
                raise OSError(f"could not write {out}")
            written.append(out)
            if progress and not progress(position + 1, len(indices)):
                raise ExportCancelled()
        return written

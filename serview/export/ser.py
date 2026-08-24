"""Write a new SER file from a selection of frames (trim, crop, process)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np

from ..imaging.pipeline import FrameProcessor
from ..ser.format import ColourID
from ..ser.reader import SerReader
from ..ser.writer import SerWriter
from .fits import ExportCancelled, ProgressCallback


@dataclass
class SerExportOptions:
    apply_processing: bool = False   # False keeps the original pixel values
    apply_crop: bool = True
    debayer: bool = False            # write RGB instead of the Bayer mosaic
    to_mono: bool = False
    bit_depth: int = 0               # 0 = keep the source depth, else 8 or 16
    observer: str | None = None
    instrument: str | None = None
    telescope: str | None = None


class SerFileExporter:
    def __init__(self, reader: SerReader, processor: FrameProcessor,
                 options: SerExportOptions | None = None):
        self.reader = reader
        self.processor = processor
        self.options = options or SerExportOptions()

    def _prepare(self, index: int) -> np.ndarray:
        opts = self.options
        proc = self.processor
        frame = self.reader.frame(index)
        if opts.apply_crop:
            frame = proc.crop_frame(frame)
        if opts.debayer and self.reader.colour_id.is_bayer:
            frame = proc.demosaic(frame)
        if opts.apply_processing:
            dtype = np.uint8 if self._target_depth() <= 8 else np.uint16
            work = proc.process_float(frame)
            max_value = float(np.iinfo(dtype).max)
            return np.clip(work * max_value + 0.5, 0, max_value).astype(dtype)
        if opts.to_mono and frame.ndim == 3:
            frame = frame.mean(axis=2).astype(frame.dtype)
        return frame

    def _target_depth(self) -> int:
        if self.options.bit_depth:
            return self.options.bit_depth
        return 8 if self.reader.bytes_per_sample == 1 else 16

    def _target_colour(self, sample: np.ndarray) -> ColourID:
        if sample.ndim == 3:
            return ColourID.RGB
        if self.options.debayer or self.options.to_mono:
            return ColourID.MONO
        return self.reader.colour_id if not self.reader.colour_id.is_colour else ColourID.MONO

    def export(self, path: str, indices: Sequence[int],
               progress: ProgressCallback | None = None) -> list[str]:
        indices = list(indices)
        first = self._prepare(indices[0])
        height, width = first.shape[:2]
        header = self.reader.header
        opts = self.options
        writer = SerWriter(
            path, width, height,
            colour_id=self._target_colour(first),
            pixel_depth=self._target_depth(),
            observer=opts.observer if opts.observer is not None else header.observer,
            instrument=opts.instrument if opts.instrument is not None else header.instrument,
            telescope=opts.telescope if opts.telescope is not None else header.telescope,
        )
        try:
            for position, index in enumerate(indices):
                frame = first if position == 0 else self._prepare(index)
                writer.add_frame(frame, timestamp=self.reader.frame_datetime(index))
                if progress and not progress(position + 1, len(indices)):
                    raise ExportCancelled()
        except BaseException:
            writer._file.close()
            raise
        writer.close()
        return [path]

"""Video export: AVI/MP4 through OpenCV and animated GIF through Pillow."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Sequence

import cv2
import numpy as np
from PIL import Image

from ..imaging.pipeline import FrameProcessor
from ..ser.reader import SerReader
from .fits import ExportCancelled, ProgressCallback

#: label -> (extension, fourcc)
#:
#: The classic ``DIB `` fourcc that older tools write is rejected by the FFmpeg
#: backend OpenCV uses, so uncompressed output goes through ``RGBA`` instead;
#: both it and FFV1 were verified to round-trip pixel for pixel.
VIDEO_CODECS = {
    "Uncompressed AVI (lossless)": (".avi", "RGBA"),
    "FFV1 AVI (lossless, compressed)": (".avi", "FFV1"),
    "Motion JPEG AVI": (".avi", "MJPG"),
    "MPEG-4 AVI": (".avi", "MP4V"),
    "MPEG-4 (H.264) MP4": (".mp4", "avc1"),
}


@dataclass
class VideoExportOptions:
    codec: str = "Motion JPEG AVI"
    fps: float = 30.0
    resize: tuple[int, int] | None = None
    #: animated GIF only
    gif_delay_ms: int = 40
    gif_final_delay_ms: int = 40
    gif_loop: bool = True
    gif_colours: int = 256


class VideoExporter:
    def __init__(self, reader: SerReader, processor: FrameProcessor,
                 options: VideoExportOptions | None = None):
        self.reader = reader
        self.processor = processor
        self.options = options or VideoExportOptions()

    def _render(self, index: int) -> np.ndarray:
        image = self.processor.process(self.reader.frame(index), out_dtype=np.uint8)
        if self.options.resize:
            interp = cv2.INTER_AREA if self.options.resize[0] < image.shape[1] else cv2.INTER_CUBIC
            image = cv2.resize(image, self.options.resize, interpolation=interp)
        if image.ndim == 2:
            image = cv2.cvtColor(image, cv2.COLOR_GRAY2RGB)
        return np.ascontiguousarray(image)

    def export(self, path: str, indices: Sequence[int],
               progress: ProgressCallback | None = None) -> list[str]:
        if os.path.splitext(path)[1].lower() == ".gif":
            return self._export_gif(path, list(indices), progress)
        return self._export_video(path, list(indices), progress)

    def _export_video(self, path: str, indices: Sequence[int],
                      progress: ProgressCallback | None) -> list[str]:
        ext, fourcc_name = VIDEO_CODECS.get(self.options.codec, VIDEO_CODECS["Motion JPEG AVI"])
        if os.path.splitext(path)[1] == "":
            path += ext
        first = self._render(indices[0])
        height, width = first.shape[:2]
        writer = cv2.VideoWriter(
            path, cv2.VideoWriter_fourcc(*fourcc_name), self.options.fps, (width, height), True
        )
        if not writer.isOpened():
            raise OSError(f"could not open {path} with codec {fourcc_name}")
        try:
            for position, index in enumerate(indices):
                frame = first if position == 0 else self._render(index)
                writer.write(frame[:, :, ::-1])  # OpenCV expects BGR
                if progress and not progress(position + 1, len(indices)):
                    raise ExportCancelled()
        finally:
            writer.release()
        return [path]

    def _export_gif(self, path: str, indices: Sequence[int],
                    progress: ProgressCallback | None) -> list[str]:
        opts = self.options
        frames: list[Image.Image] = []
        for position, index in enumerate(indices):
            image = Image.fromarray(self._render(index))
            frames.append(
                image.convert("P", palette=Image.ADAPTIVE, colors=max(2, min(256, opts.gif_colours)))
            )
            if progress and not progress(position + 1, len(indices)):
                raise ExportCancelled()
        durations = [opts.gif_delay_ms] * len(frames)
        if durations:
            durations[-1] = opts.gif_final_delay_ms
        frames[0].save(
            path,
            save_all=True,
            append_images=frames[1:],
            duration=durations,
            loop=0 if opts.gif_loop else 1,
            optimize=True,
            disposal=2,
        )
        return [path]

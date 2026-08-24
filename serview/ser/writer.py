"""Writing of SER video files."""

from __future__ import annotations

import os
from datetime import datetime, timezone

import numpy as np

from .format import (
    DEFAULT_FILE_ID,
    TIMESTAMP_SIZE,
    ColourID,
    SerHeader,
    datetime_to_ticks,
)


class SerWriter:
    """Create a SER file frame by frame.

    The header is written first with a placeholder frame count and rewritten on
    :meth:`close`, so the frame count is always correct even when the caller
    stops early.  Timestamps, when supplied, are stored in the trailer.
    """

    def __init__(
        self,
        path: str | os.PathLike,
        width: int,
        height: int,
        colour_id: ColourID = ColourID.MONO,
        pixel_depth: int = 8,
        observer: str = "",
        instrument: str = "",
        telescope: str = "",
        start_time: datetime | None = None,
        utc_offset_seconds: float = 0.0,
    ):
        self.path = str(path)
        self.header = SerHeader(
            file_id=DEFAULT_FILE_ID,
            colour_id=ColourID(colour_id),
            little_endian=0,  # we always write little endian pixel data
            width=int(width),
            height=int(height),
            pixel_depth=int(pixel_depth),
            frame_count=0,
            observer=observer,
            instrument=instrument,
            telescope=telescope,
        )
        self._timestamps: list[int] = []
        self._start_time = start_time
        self._utc_offset = utc_offset_seconds
        self._file = open(self.path, "wb")
        self._file.write(self.header.pack())

    # -- writing ---------------------------------------------------------
    def add_frame(self, frame: np.ndarray, timestamp: datetime | None = None) -> None:
        """Append one frame; ``frame`` is ``(h, w)`` or ``(h, w, 3)`` RGB."""
        data = self._coerce(frame)
        self._file.write(data.tobytes())
        self.header.frame_count += 1
        if timestamp is not None:
            self._timestamps.append(datetime_to_ticks(timestamp))
        elif self._timestamps:
            # Keep the trailer aligned with the frames if it has already begun.
            self._timestamps.append(self._timestamps[-1])

    def _coerce(self, frame: np.ndarray) -> np.ndarray:
        h = self.header
        expected_planes = h.planes
        if frame.ndim == 2:
            frame = frame[:, :, None]
        if frame.shape[:2] != (h.height, h.width):
            raise ValueError(
                f"frame is {frame.shape[1]}x{frame.shape[0]}, expected {h.width}x{h.height}"
            )
        if frame.shape[2] != expected_planes:
            raise ValueError(
                f"frame has {frame.shape[2]} planes, expected {expected_planes}"
            )
        if h.colour_id is ColourID.BGR:
            frame = frame[:, :, ::-1]
        dtype = np.uint8 if h.bytes_per_sample == 1 else "<u2"
        return np.ascontiguousarray(frame, dtype=dtype)

    # -- finishing -------------------------------------------------------
    def close(self) -> None:
        if self._file.closed:
            return
        if self._timestamps:
            self._file.write(np.asarray(self._timestamps, dtype="<u8").tobytes())
            first = self._timestamps[0]
        else:
            first = datetime_to_ticks(self._start_time or datetime.now(timezone.utc))
        self.header.date_time_utc_ticks = first
        self.header.date_time_ticks = first + int(self._utc_offset * 10_000_000)
        self._file.seek(0)
        self._file.write(self.header.pack())
        self._file.close()

    def __enter__(self) -> "SerWriter":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if exc_type is None:
            self.close()
        else:
            self._file.close()

    @property
    def frame_count(self) -> int:
        return self.header.frame_count

    @staticmethod
    def estimated_size(width: int, height: int, frames: int, planes: int,
                       bytes_per_sample: int, with_timestamps: bool = True) -> int:
        from .format import HEADER_SIZE

        size = HEADER_SIZE + frames * width * height * planes * bytes_per_sample
        if with_timestamps:
            size += frames * TIMESTAMP_SIZE
        return size

"""Reading of SER video files."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import numpy as np

from .format import (
    HEADER_SIZE,
    TIMESTAMP_SIZE,
    ColourID,
    SerHeader,
    ticks_to_datetime,
)


class SerError(Exception):
    """Raised when a SER file cannot be opened or is inconsistent."""


@dataclass
class SerWarning:
    """A non fatal problem found while opening a file."""

    code: str
    message: str


class SerReader:
    """Random access reader for a SER file.

    Frames are returned as ``numpy`` arrays in the file's native bit depth,
    shaped ``(height, width)`` for monochrome/Bayer data and
    ``(height, width, 3)`` in **RGB** order for colour data.
    """

    #: number of frames sampled when measuring the effective bit depth
    DEPTH_SCAN_FRAMES = 10

    def __init__(self, path: str | os.PathLike, scan_pixel_depth: bool = True):
        self.path = str(path)
        self.warnings: list[SerWarning] = []
        self._file = open(self.path, "rb")
        try:
            self._filesize = os.path.getsize(self.path)
            raw = self._file.read(HEADER_SIZE)
            self.header = SerHeader.unpack(raw)
            self.header.validate()
            self._truncate_frame_count()
            self._map_frames()
            self.timestamps = self._read_timestamps()
            self.header.effective_pixel_depth = (
                self._measure_pixel_depth() if scan_pixel_depth else self.header.pixel_depth
            )
        except Exception:
            self._file.close()
            raise

    # -- lifecycle ------------------------------------------------------
    def close(self) -> None:
        self._data = None
        if not self._file.closed:
            self._file.close()

    def __enter__(self) -> "SerReader":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # -- basic properties -----------------------------------------------
    @property
    def width(self) -> int:
        return self.header.width

    @property
    def height(self) -> int:
        return self.header.height

    @property
    def frame_count(self) -> int:
        return self.header.frame_count

    @property
    def colour_id(self) -> ColourID:
        return self.header.colour_id

    @property
    def planes(self) -> int:
        return self.header.planes

    @property
    def bytes_per_sample(self) -> int:
        return self.header.bytes_per_sample

    @property
    def pixel_depth(self) -> int:
        """Effective bits per sample, measured from the data when possible."""
        return self.header.effective_pixel_depth or self.header.pixel_depth

    @property
    def has_timestamps(self) -> bool:
        return bool(self.timestamps)

    @property
    def filesize(self) -> int:
        return self._filesize

    # -- opening helpers -------------------------------------------------
    def _truncate_frame_count(self) -> None:
        """Clamp FrameCount to what the file actually contains."""
        available = self._filesize - HEADER_SIZE
        frame_size = self.header.frame_size
        if frame_size <= 0:
            raise SerError("frame size is zero")
        usable = available // frame_size
        if usable <= 0:
            raise SerError(
                "the file is too short to contain a single frame "
                f"({available} bytes after the header, {frame_size} needed)"
            )
        if usable < self.header.frame_count:
            self.warnings.append(
                SerWarning(
                    "truncated",
                    f"The header claims {self.header.frame_count} frames but the file "
                    f"only holds {usable}. The file looks truncated; "
                    f"{usable} frames will be used.",
                )
            )
            self.header.frame_count = int(usable)

    def _map_frames(self) -> None:
        h = self.header
        shape = (h.frame_count, h.height, h.width, h.planes)
        try:
            self._data = np.memmap(
                self.path, dtype=h.numpy_dtype, mode="r", offset=HEADER_SIZE, shape=shape
            )
        except (ValueError, OSError):
            # Fall back to plain file reads (e.g. on filesystems without mmap).
            self._data = None

    def _read_timestamps(self) -> list[datetime]:
        h = self.header
        if h.date_time_ticks == 0 and h.date_time_utc_ticks == 0:
            return []
        trailer_offset = HEADER_SIZE + h.frame_count * h.frame_size
        needed = h.frame_count * TIMESTAMP_SIZE
        if self._filesize < trailer_offset + needed:
            return []
        self._file.seek(trailer_offset)
        raw = self._file.read(needed)
        if len(raw) != needed:
            return []
        ticks = np.frombuffer(raw, dtype="<u8").astype(np.int64)
        if np.all(ticks <= 0):
            return []

        # Some recorders store *local* time in the trailer instead of UTC.
        # Follow SER Player: whichever of the two header times sits closest to
        # the earliest trailer timestamp tells us which one the trailer uses.
        min_ticks = int(ticks[ticks > 0].min())
        utc_offset = h.date_time_utc_ticks - h.date_time_ticks
        d_utc = abs(h.date_time_utc_ticks - min_ticks)
        d_local = abs(h.date_time_ticks - min_ticks)
        correction = 0 if d_utc <= d_local else utc_offset
        if correction:
            self.warnings.append(
                SerWarning(
                    "local_timestamps",
                    "Frame timestamps look like local time; they have been "
                    "converted to UTC using the header's UTC offset.",
                )
            )
        return [ticks_to_datetime(int(t) + correction) for t in ticks]

    def _measure_pixel_depth(self) -> int:
        """Find the real bit depth by OR-ing sample frames together.

        Many capture programs leave ``PixelDepthPerPlane`` at 16 even when the
        camera delivers 10, 12 or 14 bits, which would make the image look far
        too dark.  SER Player solves this by scanning the data; so do we.
        """
        if self.bytes_per_sample == 1:
            return min(self.header.pixel_depth, 8) or 8
        count = self.frame_count
        indices = sorted(
            {0, count - 1, *[(count - 1) * i // (self.DEPTH_SCAN_FRAMES - 1) for i in range(self.DEPTH_SCAN_FRAMES)]}
        )
        accumulator = np.uint16(0)
        for index in indices:
            frame = self.raw_frame(index)
            accumulator |= np.bitwise_or.reduce(frame.reshape(-1).astype(np.uint16))
        value = int(accumulator)
        if value == 0:
            return self.header.pixel_depth
        return max(8, int(value).bit_length())

    # -- frame access ----------------------------------------------------
    def _check_index(self, index: int) -> int:
        if not 0 <= index < self.frame_count:
            raise IndexError(f"frame {index} out of range (0..{self.frame_count - 1})")
        return index

    def raw_frame(self, index: int) -> np.ndarray:
        """Return frame ``index`` exactly as stored, shape ``(h, w, planes)``."""
        self._check_index(index)
        h = self.header
        if self._data is not None:
            frame = np.array(self._data[index], dtype=h.numpy_dtype, copy=True)
        else:
            self._file.seek(HEADER_SIZE + index * h.frame_size)
            raw = self._file.read(h.frame_size)
            if len(raw) != h.frame_size:
                raise SerError(f"could not read frame {index}")
            frame = np.frombuffer(raw, dtype=h.numpy_dtype).reshape(
                h.height, h.width, h.planes
            )
        # Return in native byte order so downstream maths stays fast.
        return frame.astype(frame.dtype.newbyteorder("="), copy=False)

    def frame(self, index: int) -> np.ndarray:
        """Return frame ``index`` as ``(h, w)`` mono or ``(h, w, 3)`` RGB."""
        frame = self.raw_frame(index)
        if self.colour_id is ColourID.BGR:
            frame = frame[:, :, ::-1]
        if frame.shape[2] == 1:
            return frame[:, :, 0]
        return np.ascontiguousarray(frame)

    def timestamp(self, index: int) -> datetime | None:
        self._check_index(index)
        if not self.timestamps:
            return None
        return self.timestamps[index]

    # -- derived information ---------------------------------------------
    @property
    def fps(self) -> float | None:
        """Frame rate derived from the trailer timestamps."""
        if len(self.timestamps) < 2:
            return None
        first, last = self.timestamps[0], self.timestamps[-1]
        if first is None or last is None:
            return None
        span = (last - first).total_seconds()
        if span <= 0:
            return None
        return (len(self.timestamps) - 1) / span

    @property
    def duration(self) -> timedelta | None:
        if len(self.timestamps) < 2 or None in (self.timestamps[0], self.timestamps[-1]):
            return None
        return self.timestamps[-1] - self.timestamps[0]

    def frame_datetime(self, index: int) -> datetime | None:
        """Best available UTC time for a frame, falling back to the header."""
        stamp = self.timestamp(index)
        if stamp is not None:
            return stamp
        start = self.header.utc_datetime
        if start is None:
            return None
        rate = self.fps
        if rate:
            return start + timedelta(seconds=index / rate)
        return start if index == 0 else None

    def describe(self) -> dict[str, str]:
        """Human readable header summary used by the header dialog."""
        h = self.header
        info: dict[str, str] = {
            "File name": os.path.basename(self.path),
            "File size": f"{self._filesize:,} bytes",
            "File ID": h.file_id,
            "LuID": str(h.lu_id),
            "Colour ID": f"{h.colour_id.label} ({int(h.colour_id)})",
            "Image size": f"{h.width} x {h.height}",
            "Pixel depth (header)": f"{h.pixel_depth} bit",
            "Pixel depth (measured)": f"{self.pixel_depth} bit",
            "Bytes per sample": str(h.bytes_per_sample),
            "Byte order": "big endian" if h.big_endian_data else "little endian",
            "Frame count": str(h.frame_count),
            "Observer": h.observer or "-",
            "Instrument": h.instrument or "-",
            "Telescope": h.telescope or "-",
        }
        local = h.local_datetime
        utc = h.utc_datetime
        info["Date/time (local)"] = local.strftime("%Y-%m-%d %H:%M:%S") if local else "-"
        info["Date/time (UTC)"] = utc.strftime("%Y-%m-%d %H:%M:%S") if utc else "-"
        info["Frame timestamps"] = "present" if self.has_timestamps else "absent"
        rate = self.fps
        info["Frame rate"] = f"{rate:.3f} fps" if rate else "-"
        duration = self.duration
        info["Duration"] = f"{duration.total_seconds():.3f} s" if duration else "-"
        return info

"""SER file format definitions.

The SER format is described by the "SER format description" document
(v3) by Heiko Wilkens / Grischa Hahn.  Layout of a SER file::

    offset  size  field
    0       14    FileID           - normally "LUCAM-RECORDER"
    14      4     LuID             - unused (0)
    18      4     ColorID          - see ColourID below
    22      4     LittleEndian     - 0: pixel data little endian
                                     1: pixel data big endian (yes, inverted)
    26      4     ImageWidth
    30      4     ImageHeight
    34      4     PixelDepthPerPlane   1..8 -> 1 byte/pixel, 9..16 -> 2 bytes
    38      4     FrameCount
    42      40    Observer
    82      40    Instrument
    122     40    Telescope
    162     8     DateTime         - local time, 100 ns ticks since 0001-01-01
    170     8     DateTime_UTC
    178     ...   frame data, FrameCount frames, no padding
    (opt)   8*N   trailer: one UTC timestamp per frame, same tick format
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import IntEnum

FILE_ID_SIZE = 14
HEADER_SIZE = 178
DEFAULT_FILE_ID = "LUCAM-RECORDER"
TIMESTAMP_SIZE = 8

#: SER timestamps count 100 ns ticks since 0001-01-01 00:00:00.
SER_EPOCH = datetime(1, 1, 1)
TICKS_PER_SECOND = 10_000_000


class ColourID(IntEnum):
    MONO = 0
    BAYER_RGGB = 8
    BAYER_GRBG = 9
    BAYER_GBRG = 10
    BAYER_BGGR = 11
    BAYER_CYYM = 16
    BAYER_YCMY = 17
    BAYER_YMCY = 18
    BAYER_MYYC = 19
    RGB = 100
    BGR = 101

    @property
    def is_colour(self) -> bool:
        return self in (ColourID.RGB, ColourID.BGR)

    @property
    def is_bayer(self) -> bool:
        return 8 <= int(self) <= 19

    @property
    def planes(self) -> int:
        return 3 if self.is_colour else 1

    @property
    def bayer_pattern(self) -> str | None:
        """FITS ``BAYERPAT`` style string, or ``None`` when not a Bayer sensor."""
        return _BAYER_NAMES.get(int(self))

    @property
    def label(self) -> str:
        if self is ColourID.MONO:
            return "Monochrome"
        if self.is_bayer:
            return f"Bayer {self.bayer_pattern}"
        return self.name


_BAYER_NAMES = {
    8: "RGGB",
    9: "GRBG",
    10: "GBRG",
    11: "BGGR",
    16: "CYYM",
    17: "YCMY",
    18: "YMCY",
    19: "MYYC",
}

#: Bayer patterns that OpenCV can demosaic directly.
RGB_BAYER_IDS = (
    ColourID.BAYER_RGGB,
    ColourID.BAYER_GRBG,
    ColourID.BAYER_GBRG,
    ColourID.BAYER_BGGR,
)


def ticks_to_datetime(ticks: int, utc: bool = True) -> datetime | None:
    """Convert SER 100 ns ticks to a :class:`datetime` (``None`` when unset)."""
    if ticks <= 0:
        return None
    try:
        value = SER_EPOCH + timedelta(microseconds=ticks / 10.0)
    except OverflowError:
        return None
    return value.replace(tzinfo=timezone.utc) if utc else value


def datetime_to_ticks(value: datetime | None) -> int:
    """Convert a :class:`datetime` back to SER 100 ns ticks."""
    if value is None:
        return 0
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    delta = value - SER_EPOCH
    return int(round(delta.total_seconds() * TICKS_PER_SECOND))


def _decode_text(raw: bytes) -> str:
    text = raw.split(b"\x00", 1)[0]
    try:
        return text.decode("utf-8").strip()
    except UnicodeDecodeError:
        return text.decode("latin-1").strip()


def _encode_text(text: str, size: int = 40) -> bytes:
    return text.encode("utf-8", "replace")[:size].ljust(size, b"\x00")


@dataclass
class SerHeader:
    """The 178 byte SER header."""

    file_id: str = DEFAULT_FILE_ID
    lu_id: int = 0
    colour_id: ColourID = ColourID.MONO
    little_endian: int = 0
    width: int = 0
    height: int = 0
    pixel_depth: int = 8
    frame_count: int = 0
    observer: str = ""
    instrument: str = ""
    telescope: str = ""
    date_time_ticks: int = 0
    date_time_utc_ticks: int = 0

    #: effective bit depth measured from the pixel data (see SerReader)
    effective_pixel_depth: int = field(default=0, repr=False)

    _STRUCT = struct.Struct("<14s7i40s40s40sqq")

    @classmethod
    def unpack(cls, raw: bytes) -> "SerHeader":
        if len(raw) < HEADER_SIZE:
            raise ValueError("SER header is truncated")
        (
            file_id,
            lu_id,
            colour_id,
            little_endian,
            width,
            height,
            pixel_depth,
            frame_count,
            observer,
            instrument,
            telescope,
            dt_ticks,
            dt_utc_ticks,
        ) = cls._STRUCT.unpack(raw[:HEADER_SIZE])
        try:
            colour = ColourID(colour_id)
        except ValueError:
            colour = ColourID.MONO
        return cls(
            file_id=_decode_text(file_id),
            lu_id=lu_id,
            colour_id=colour,
            little_endian=little_endian,
            width=width,
            height=height,
            pixel_depth=pixel_depth,
            frame_count=frame_count,
            observer=_decode_text(observer),
            instrument=_decode_text(instrument),
            telescope=_decode_text(telescope),
            date_time_ticks=dt_ticks,
            date_time_utc_ticks=dt_utc_ticks,
        )

    def pack(self) -> bytes:
        return self._STRUCT.pack(
            _encode_text(self.file_id, FILE_ID_SIZE),
            self.lu_id,
            int(self.colour_id),
            self.little_endian,
            self.width,
            self.height,
            self.pixel_depth,
            self.frame_count,
            _encode_text(self.observer),
            _encode_text(self.instrument),
            _encode_text(self.telescope),
            self.date_time_ticks,
            self.date_time_utc_ticks,
        )

    # -- derived values -------------------------------------------------
    @property
    def bytes_per_sample(self) -> int:
        return 1 if self.pixel_depth <= 8 else 2

    @property
    def planes(self) -> int:
        return self.colour_id.planes

    @property
    def frame_size(self) -> int:
        return self.width * self.height * self.planes * self.bytes_per_sample

    @property
    def big_endian_data(self) -> bool:
        """``LittleEndian == 1`` means the pixel data is *big* endian."""
        return self.little_endian == 1

    @property
    def numpy_dtype(self) -> str:
        if self.bytes_per_sample == 1:
            return "u1"
        return ">u2" if self.big_endian_data else "<u2"

    @property
    def local_datetime(self) -> datetime | None:
        return ticks_to_datetime(self.date_time_ticks, utc=False)

    @property
    def utc_datetime(self) -> datetime | None:
        return ticks_to_datetime(self.date_time_utc_ticks, utc=True)

    def validate(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError(f"invalid image size {self.width}x{self.height}")
        if self.frame_count <= 0:
            raise ValueError("frame count is zero")
        if not 1 <= self.pixel_depth <= 16:
            raise ValueError(f"invalid pixel depth {self.pixel_depth}")
        if self.little_endian not in (0, 1):
            raise ValueError(f"invalid LittleEndian value {self.little_endian}")

"""Reading and writing SER files."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from serview.ser import ColourID, SerError, SerReader, SerWriter
from serview.ser.format import (
    HEADER_SIZE,
    SerHeader,
    datetime_to_ticks,
    ticks_to_datetime,
)


def test_header_round_trip():
    header = SerHeader(
        colour_id=ColourID.BAYER_GRBG, width=640, height=480, pixel_depth=16,
        frame_count=123, observer="Obs", instrument="Cam", telescope="Tel",
        date_time_ticks=637000000000000000, date_time_utc_ticks=637000000000000001,
    )
    packed = header.pack()
    assert len(packed) == HEADER_SIZE
    restored = SerHeader.unpack(packed)
    for field in ("colour_id", "width", "height", "pixel_depth", "frame_count",
                  "observer", "instrument", "telescope", "date_time_ticks"):
        assert getattr(restored, field) == getattr(header, field)


def test_timestamp_conversion_round_trip():
    moment = datetime(2026, 3, 14, 21, 30, 12, 345000, tzinfo=timezone.utc)
    ticks = datetime_to_ticks(moment)
    assert abs((ticks_to_datetime(ticks) - moment).total_seconds()) < 1e-6
    assert ticks_to_datetime(0) is None


def test_reader_basics(mono8_ser):
    with SerReader(mono8_ser) as reader:
        assert (reader.width, reader.height) == (64, 48)
        assert reader.frame_count == 10
        assert reader.colour_id is ColourID.MONO
        assert reader.frame(0).shape == (48, 64)
        assert reader.frame(0).dtype == np.uint8
        assert reader.has_timestamps
        assert reader.fps == pytest.approx(25.0, rel=1e-3)
        assert reader.describe()["Colour ID"].startswith("Monochrome")


def test_reader_rejects_out_of_range(mono8_ser):
    with SerReader(mono8_ser) as reader:
        with pytest.raises(IndexError):
            reader.frame(reader.frame_count)


def test_measured_pixel_depth(bayer12_ser):
    """The header says 16 bit but the data only fills 12 bits."""
    with SerReader(bayer12_ser) as reader:
        assert reader.header.pixel_depth == 16   # what the recorder claimed
        assert reader.pixel_depth == 12          # what the data actually holds
        assert reader.raw_frame(0).max() <= 4095


def test_colour_frames_are_rgb(rgb8_ser):
    with SerReader(rgb8_ser) as reader:
        frame = reader.frame(0)
        assert frame.shape == (24, 32, 3)
        # The generator makes red the brightest channel.
        assert frame[..., 0].mean() > frame[..., 1].mean() > frame[..., 2].mean()


def test_bgr_is_converted_to_rgb(tmp_path):
    path = tmp_path / "bgr.ser"
    frame = np.zeros((4, 4, 3), dtype=np.uint8)
    frame[..., 0] = 200  # red
    frame[..., 2] = 10   # blue
    with SerWriter(str(path), 4, 4, ColourID.BGR, 8) as writer:
        writer.add_frame(frame)
    with SerReader(str(path)) as reader:
        assert reader.colour_id is ColourID.BGR
        out = reader.frame(0)
        assert out[0, 0, 0] == 200 and out[0, 0, 2] == 10


def test_writer_round_trip_preserves_pixels(tmp_path):
    path = tmp_path / "written.ser"
    start = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    frames = [np.random.default_rng(i).integers(0, 4096, (16, 20), dtype=np.uint16)
              for i in range(4)]
    with SerWriter(str(path), 20, 16, ColourID.MONO, 16, observer="O",
                   instrument="I", telescope="T") as writer:
        for index, frame in enumerate(frames):
            writer.add_frame(frame, timestamp=start + timedelta(seconds=index))
    with SerReader(str(path)) as reader:
        assert reader.frame_count == 4
        assert reader.header.observer == "O"
        for index, frame in enumerate(frames):
            assert np.array_equal(reader.frame(index), frame)
        assert reader.timestamp(2) == start + timedelta(seconds=2)
        assert reader.fps == pytest.approx(1.0)


def test_big_endian_data_is_decoded(tmp_path):
    """LittleEndian == 1 means the pixel data is big endian."""
    path = tmp_path / "be.ser"
    values = np.array([[1, 2], [3, 4096]], dtype=np.uint16)
    header = SerHeader(colour_id=ColourID.MONO, little_endian=1, width=2, height=2,
                       pixel_depth=16, frame_count=1)
    with open(path, "wb") as handle:
        handle.write(header.pack())
        handle.write(values.astype(">u2").tobytes())
    with SerReader(str(path)) as reader:
        assert np.array_equal(reader.frame(0), values)


def test_truncated_file_is_clamped_with_a_warning(tmp_path, mono8_ser):
    path = tmp_path / "short.ser"
    data = open(mono8_ser, "rb").read()
    frame_size = 64 * 48
    path.write_bytes(data[: HEADER_SIZE + int(frame_size * 4.5)])
    with SerReader(str(path)) as reader:
        assert reader.frame_count == 4
        assert any(w.code == "truncated" for w in reader.warnings)


def test_unreadable_file_raises(tmp_path):
    path = tmp_path / "junk.ser"
    path.write_bytes(b"not a ser file at all")
    with pytest.raises((SerError, ValueError)):
        SerReader(str(path))

"""FITS, image, video and SER export."""

from __future__ import annotations

import os

import numpy as np
import pytest
from astropy.io import fits

from serview.export.fits import ExportCancelled, FitsExportOptions, FitsExporter
from serview.export.images import ImageExportOptions, ImageExporter
from serview.export.ser import SerExportOptions, SerFileExporter
from serview.export.video import VideoExportOptions, VideoExporter
from serview.imaging import CropRect, FrameProcessor, ProcessingOptions
from serview.ser import SerReader


def make_exporter(path, options, processing=None):
    reader = SerReader(path)
    processor = FrameProcessor(reader.colour_id, reader.pixel_depth,
                               processing or ProcessingOptions())
    return reader, FitsExporter(reader, processor, options)


def test_cube_preserves_raw_values(bayer12_ser, tmp_path):
    out = str(tmp_path / "cube.fits")
    reader, exporter = make_exporter(bayer12_ser, FitsExportOptions(colour_mode="raw"))
    exporter.export(out, range(reader.frame_count))
    with fits.open(out) as hdul:
        data = hdul[0].data
        assert data.shape == (reader.frame_count, reader.height, reader.width)
        assert data.dtype == np.uint16
        for index in range(reader.frame_count):
            assert np.array_equal(data[index], reader.raw_frame(index)[:, :, 0])
    reader.close()


def test_cube_header_keywords(bayer12_ser, tmp_path):
    out = str(tmp_path / "cube.fits")
    reader, exporter = make_exporter(
        bayer12_ser,
        FitsExportOptions(colour_mode="raw", object_name="Jupiter",
                          exposure_seconds=0.005, focal_length_mm=2350.0,
                          pixel_size_um=2.9),
    )
    exporter.export(out, range(4))
    with fits.open(out) as hdul:
        header = hdul[0].header
        assert header["BAYERPAT"] == "RGGB"
        assert header["ROWORDER"] == "TOP-DOWN"
        assert header["OBJECT"] == "Jupiter"
        assert header["EXPTIME"] == pytest.approx(0.005)
        assert header["FOCALLEN"] == pytest.approx(2350.0)
        assert header["XPIXSZ"] == pytest.approx(2.9)
        assert header["SERDEPTH"] == 12
        assert header["NFRAMES"] == 4
        assert header["DATE-OBS"].startswith("2026-03-14T21:30:00")
        assert header["MJD-OBS"] == pytest.approx(61113.895833, abs=1e-5)
        assert "SERFILE" in header
        # per frame timestamps live in an extension
        table = hdul["FRAMETIME"].data
        assert len(table) == 4
        assert table["FRAME"][0] == 1
        assert table["DATE_OBS"][1].startswith("2026-03-14T21:30:00.033")
    reader.close()


def test_rgb_cube_axis_order(bayer12_ser, tmp_path):
    out = str(tmp_path / "rgb.fits")
    reader, exporter = make_exporter(bayer12_ser, FitsExportOptions(colour_mode="rgb"))
    exporter.export(out, range(3))
    with fits.open(out) as hdul:
        assert hdul[0].data.shape == (3, 3, reader.height, reader.width)
        assert hdul[0].header["CTYPE3"] == "RGB"
        assert hdul[0].header["NAXIS"] == 4
    reader.close()


def test_single_frame_collapses_to_a_plain_image(mono16_ser, tmp_path):
    out = str(tmp_path / "one.fits")
    reader, exporter = make_exporter(mono16_ser, FitsExportOptions(colour_mode="mono"))
    exporter.export(out, [2])
    with fits.open(out) as hdul:
        assert hdul[0].data.shape == (reader.height, reader.width)
        assert hdul[0].header["SERFRAME"] == 3
        assert "NFRAMES" not in hdul[0].header
    reader.close()


def test_sequence_layout(mono8_ser, tmp_path):
    out = str(tmp_path / "seq.fits")
    reader, exporter = make_exporter(mono8_ser, FitsExportOptions(layout="sequence"))
    written = exporter.export(out, [0, 1, 5])
    assert [os.path.basename(p) for p in written] == [
        "seq_00001.fits", "seq_00002.fits", "seq_00006.fits"]
    with fits.open(written[2]) as hdul:
        assert hdul[0].header["SERFRAME"] == 6
        assert hdul[0].data.dtype == np.uint8
    reader.close()


def test_float32_export_is_normalised(bayer12_ser, tmp_path):
    out = str(tmp_path / "f32.fits")
    reader, exporter = make_exporter(
        bayer12_ser, FitsExportOptions(colour_mode="raw", bit_depth="float32"))
    exporter.export(out, [0])
    with fits.open(out) as hdul:
        data = hdul[0].data
        assert data.dtype.kind == "f"
        assert 0.0 <= data.min() and data.max() <= 1.0
    reader.close()


def test_crop_is_applied_and_bayer_offsets_recorded(bayer12_ser, tmp_path):
    out = str(tmp_path / "crop.fits")
    options = ProcessingOptions(crop=CropRect(8, 6, 16, 12))
    reader, exporter = make_exporter(bayer12_ser, FitsExportOptions(colour_mode="raw"), options)
    exporter.export(out, [0])
    with fits.open(out) as hdul:
        assert hdul[0].data.shape == (12, 16)
        assert hdul[0].header["XBAYROFF"] == 0
    reader.close()


def test_flip_writes_bottom_up(mono8_ser, tmp_path):
    out = str(tmp_path / "flip.fits")
    reader, exporter = make_exporter(
        mono8_ser, FitsExportOptions(colour_mode="mono", flip_vertical=True))
    exporter.export(out, [0])
    with fits.open(out) as hdul:
        assert hdul[0].header["ROWORDER"] == "BOTTOM-UP"
        assert np.array_equal(hdul[0].data, reader.frame(0)[::-1])
    reader.close()


def test_processing_flag_is_recorded_in_history(mono8_ser, tmp_path):
    out = str(tmp_path / "proc.fits")
    reader, exporter = make_exporter(
        mono8_ser, FitsExportOptions(colour_mode="mono", apply_processing=True),
        ProcessingOptions(gamma=2.0))
    exporter.export(out, [0])
    with fits.open(out) as hdul:
        history = " ".join(str(line) for line in hdul[0].header["HISTORY"])
        assert "NOT" in history and "linear" in history
        assert hdul[0].data.mean() > reader.frame(0).mean()
    reader.close()


def test_cancelling_removes_the_partial_file(mono8_ser, tmp_path):
    out = str(tmp_path / "cancel.fits")
    reader, exporter = make_exporter(mono8_ser, FitsExportOptions())

    def progress(done, total):
        return done < 3

    with pytest.raises(ExportCancelled):
        exporter.export(out, range(reader.frame_count), progress)
    assert not os.path.exists(out)
    reader.close()


def test_image_export(mono16_ser, tmp_path):
    import cv2

    reader = SerReader(mono16_ser)
    processor = FrameProcessor(reader.colour_id, reader.pixel_depth, ProcessingOptions())
    exporter = ImageExporter(reader, processor, ImageExportOptions(".png", 16))
    written = exporter.export(str(tmp_path / "img.png"), [0, 1])
    assert len(written) == 2
    image = cv2.imread(written[0], cv2.IMREAD_UNCHANGED)
    assert image.dtype == np.uint16 and image.shape == (reader.height, reader.width)
    reader.close()


def test_video_and_gif_export(mono8_ser, tmp_path):
    reader = SerReader(mono8_ser)
    processor = FrameProcessor(reader.colour_id, reader.pixel_depth, ProcessingOptions())
    avi = VideoExporter(reader, processor, VideoExportOptions("Motion JPEG AVI", 25))
    written = avi.export(str(tmp_path / "movie.avi"), range(reader.frame_count))
    assert os.path.getsize(written[0]) > 0
    gif = VideoExporter(reader, processor, VideoExportOptions())
    written = gif.export(str(tmp_path / "movie.gif"), range(4))
    assert os.path.getsize(written[0]) > 0
    reader.close()


def test_ser_export_is_lossless(bayer12_ser, tmp_path):
    reader = SerReader(bayer12_ser)
    processor = FrameProcessor(reader.colour_id, reader.pixel_depth, ProcessingOptions())
    exporter = SerFileExporter(reader, processor, SerExportOptions())
    out = str(tmp_path / "trimmed.ser")
    exporter.export(out, [2, 3, 4])
    with SerReader(out) as copy:
        assert copy.frame_count == 3
        assert copy.colour_id is reader.colour_id
        assert np.array_equal(copy.frame(0), reader.frame(2))
        assert copy.timestamp(1) == reader.timestamp(3)
    reader.close()

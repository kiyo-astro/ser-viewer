"""The processing pipeline."""

from __future__ import annotations

import numpy as np
import pytest

from serview.imaging import (
    CropRect,
    FrameProcessor,
    ProcessingOptions,
    compute_histogram,
    debayer,
)
from serview.ser import ColourID, SerReader


def mosaic(rgb: np.ndarray, pattern: str) -> np.ndarray:
    out = np.zeros(rgb.shape[:2], dtype=rgb.dtype)
    channels = {"R": 0, "G": 1, "B": 2}
    for position, letter in enumerate(pattern):
        dy, dx = divmod(position, 2)
        out[dy::2, dx::2] = rgb[dy::2, dx::2, channels[letter]]
    return out


@pytest.mark.parametrize("colour_id", [
    ColourID.BAYER_RGGB, ColourID.BAYER_GRBG, ColourID.BAYER_GBRG, ColourID.BAYER_BGGR,
])
def test_debayer_recovers_the_channel_order(colour_id):
    rgb = np.zeros((32, 32, 3), np.uint8)
    rgb[..., 0], rgb[..., 1], rgb[..., 2] = 200, 120, 60
    result = debayer(mosaic(rgb, colour_id.bayer_pattern), colour_id)
    means = result[4:-4, 4:-4].reshape(-1, 3).mean(axis=0)
    assert means[0] > means[1] > means[2]
    assert means == pytest.approx([200, 120, 60], abs=1.0)


def test_identity_pipeline_keeps_the_values(mono8_ser):
    with SerReader(mono8_ser) as reader:
        processor = FrameProcessor(reader.colour_id, reader.pixel_depth, ProcessingOptions())
        frame = reader.frame(0)
        assert np.array_equal(processor.process(frame), frame)
        assert ProcessingOptions().is_identity()


def test_gain_and_gamma(mono8_ser):
    with SerReader(mono8_ser) as reader:
        frame = reader.frame(0)
        brighter = FrameProcessor(reader.colour_id, reader.pixel_depth,
                                  ProcessingOptions(gain=2.0)).process(frame)
        assert brighter.mean() > frame.mean()
        gamma = FrameProcessor(reader.colour_id, reader.pixel_depth,
                               ProcessingOptions(gamma=2.2)).process(frame)
        assert gamma.mean() > frame.mean()   # gamma > 1 lifts the shadows


def test_invert(mono8_ser):
    with SerReader(mono8_ser) as reader:
        frame = reader.frame(0)
        inverted = FrameProcessor(reader.colour_id, reader.pixel_depth,
                                  ProcessingOptions(invert=True)).process(frame)
        assert np.allclose(inverted.astype(int) + frame.astype(int), 255, atol=1)


def test_crop_keeps_the_bayer_phase(bayer12_ser):
    with SerReader(bayer12_ser) as reader:
        options = ProcessingOptions(crop=CropRect(5, 7, 21, 11))
        processor = FrameProcessor(reader.colour_id, reader.pixel_depth, options)
        cropped = processor.crop_frame(reader.frame(0))
        # Odd offsets and sizes are snapped to even values.
        assert cropped.shape == (10, 20)


def test_mono_conversion(rgb8_ser):
    with SerReader(rgb8_ser) as reader:
        options = ProcessingOptions(to_mono=True, mono_mode="r")
        processed = FrameProcessor(reader.colour_id, reader.pixel_depth,
                                   options).process(reader.frame(0))
        assert processed.ndim == 2
        assert np.allclose(processed, reader.frame(0)[..., 0], atol=1)


def test_rotation_and_flip(mono8_ser):
    with SerReader(mono8_ser) as reader:
        frame = reader.frame(0)
        rotated = FrameProcessor(reader.colour_id, reader.pixel_depth,
                                 ProcessingOptions(rotation=90)).process(frame)
        assert rotated.shape == frame.shape[::-1]
        flipped = FrameProcessor(reader.colour_id, reader.pixel_depth,
                                 ProcessingOptions(flip_horizontal=True)).process(frame)
        assert np.array_equal(flipped, frame[:, ::-1])


def test_histogram_statistics():
    image = np.zeros((10, 10), np.uint8)
    image[:5] = 255
    histogram = compute_histogram(image, bin_count=16)
    assert histogram.channels == ("Mono",)
    assert histogram.minimum[0] == 0.0 and histogram.maximum[0] == 1.0
    assert histogram.mean[0] == pytest.approx(0.5, abs=0.01)
    assert histogram.clipped_low[0] == pytest.approx(0.5)
    assert histogram.clipped_high[0] == pytest.approx(0.5)

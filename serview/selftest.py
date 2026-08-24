"""Headless self-test, mainly for checking a packaged build.

``SER Viewer --selftest`` writes a small SER file to a temporary directory, reads
it back, runs it through the processing pipeline and exports FITS and PNG.  It
exercises NumPy, OpenCV and Astropy inside the frozen application, which is
where missing bundled files show up.
"""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone

import numpy as np


def _synthetic_rgb(height: int, width: int, index: int) -> np.ndarray:
    yy, xx = np.mgrid[0:height, 0:width]
    radius = min(height, width) * 0.35
    r = np.hypot(xx - width / 2 - index, yy - height / 2) / radius
    disc = np.where(r <= 1.0, 0.4 + 0.6 * np.sqrt(np.clip(1 - r**2, 0, 1)), 0.0)
    return np.stack([disc, disc * 0.8, disc * 0.6], axis=-1)


def _mosaic(rgb: np.ndarray) -> np.ndarray:
    """RGGB mosaic of an RGB image."""
    out = np.zeros(rgb.shape[:2], dtype=rgb.dtype)
    out[0::2, 0::2] = rgb[0::2, 0::2, 0]
    out[0::2, 1::2] = rgb[0::2, 1::2, 1]
    out[1::2, 0::2] = rgb[1::2, 0::2, 1]
    out[1::2, 1::2] = rgb[1::2, 1::2, 2]
    return out


def run(verbose: bool = True) -> int:
    """Returns 0 when every check passes."""
    from astropy.io import fits

    from .export.fits import FitsExporter, FitsExportOptions
    from .export.images import ImageExportOptions, ImageExporter
    from .imaging.pipeline import FrameProcessor, ProcessingOptions
    from .ser import ColourID, SerReader, SerWriter

    def report(message: str) -> None:
        if verbose:
            print(message)

    width, height, frames = 64, 48, 5
    start = datetime(2026, 3, 14, 21, 30, tzinfo=timezone.utc)
    with tempfile.TemporaryDirectory() as folder:
        ser_path = os.path.join(folder, "selftest.ser")
        originals = []
        with SerWriter(ser_path, width, height, ColourID.BAYER_RGGB, 16,
                       observer="selftest", instrument="synthetic",
                       telescope="none", start_time=start) as writer:
            for index in range(frames):
                frame = (_mosaic(_synthetic_rgb(height, width, index)) * 4095).astype(np.uint16)
                originals.append(frame)
                writer.add_frame(frame, timestamp=start + timedelta(seconds=index / 30))
        report(f"wrote {frames} frames to a temporary SER file")

        with SerReader(ser_path) as reader:
            assert reader.frame_count == frames, "frame count changed"
            assert reader.pixel_depth == 12, f"expected 12 bit, got {reader.pixel_depth}"
            for index, frame in enumerate(originals):
                assert np.array_equal(reader.frame(index), frame), f"frame {index} differs"
            assert reader.fps and abs(reader.fps - 30.0) < 0.1, "frame rate is wrong"
            report("read the file back: pixels, depth and timestamps all match")

            processor = FrameProcessor(reader.colour_id, reader.pixel_depth,
                                       ProcessingOptions(gamma=1.6))
            display = processor.to_display(reader.frame(0))
            assert display.shape == (height, width, 3), "debayering did not produce RGB"
            assert display.dtype == np.uint8 and display.max() > 0
            report("processing pipeline (OpenCV debayer + gamma) works")

            fits_path = os.path.join(folder, "selftest.fits")
            FitsExporter(reader, processor,
                         FitsExportOptions(colour_mode="raw")).export(
                             fits_path, range(frames))
            with fits.open(fits_path) as hdul:
                data = hdul[0].data
                assert data.shape == (frames, height, width), "unexpected cube shape"
                assert np.array_equal(data[0], originals[0]), "FITS pixels differ"
                assert hdul[0].header["BAYERPAT"] == "RGGB"
                assert hdul["FRAMETIME"].data["FRAME"][0] == 1
            report("FITS export (Astropy) round-trips exactly")

            png_path = os.path.join(folder, "selftest.png")
            written = ImageExporter(reader, processor,
                                    ImageExportOptions(".png", 16)).export(png_path, [0])
            assert os.path.getsize(written[0]) > 0, "PNG export produced nothing"
            report("image export works")

        _check_gui(ser_path, report)

    report("self-test passed")
    return 0


def _check_gui(ser_path: str, report) -> None:
    """Start the real window off-screen: this is what proves that Qt and its
    platform plugin survived packaging."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PySide6.QtWidgets import QApplication

    from .ui.main_window import MainWindow

    app = QApplication.instance() or QApplication([sys.argv[0]])
    window = MainWindow()
    try:
        window.load_file(ser_path)
        assert window.reader is not None, "the window did not open the SER file"
        assert window.frame_count == 5, "the window reports the wrong frame count"
        assert window.image_view.image_size == (64, 48), "nothing was drawn"
        window.show_frame(3)
        assert window.current_index == 3, "seeking failed"
        window.show_histogram()
        assert window.histogram_dialog.plot.histogram is not None, "histogram is empty"
        app.processEvents()
        report("the Qt user interface starts and renders a frame")
    finally:
        window.close_file()
        window.close()
        app.processEvents()


def main() -> int:
    try:
        return run()
    except Exception as error:  # noqa: BLE001 - the point is to report anything
        print(f"self-test FAILED: {type(error).__name__}: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

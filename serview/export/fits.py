"""FITS export.

Two layouts are supported:

``cube``
    One FITS file holding every exported frame.  Monochrome data becomes a
    3D cube ``(frames, height, width)``; colour data becomes a 4D cube
    ``(frames, 3, height, width)`` which collapses to the usual 3-plane RGB
    image when a single frame is exported.  Per frame timestamps are stored in
    a ``FRAMETIME`` binary table extension.

``sequence``
    One file per frame, numbered ``<name>_000001.fits``.

By default the pixel values are written **exactly as they are stored in the
SER file** - no stretching, no gain, no gamma - so the result is suitable for
stacking and photometry.  Enabling ``apply_processing`` writes what the player
displays instead, which is useful for quick looks but destroys the linearity.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Sequence

import numpy as np
from astropy.io import fits

from ..ser.format import ColourID
from ..ser.reader import SerReader
from ..imaging.pipeline import FrameProcessor, apply_mono, to_float

ProgressCallback = Callable[[int, int], bool]
"""Called as ``(done, total)``; return ``False`` to abort the export."""

CREATOR = "SER Viewer"


@dataclass
class FitsExportOptions:
    """Everything the FITS export dialog can set."""

    layout: str = "cube"            # "cube" | "sequence"
    colour_mode: str = "rgb"        # "rgb" | "mono" | "raw"
    bit_depth: str = "native"       # "native" | "uint16" | "float32"
    apply_processing: bool = False  # apply gain/gamma/saturation/...
    apply_crop: bool = True
    flip_vertical: bool = False     # write bottom-up instead of top-down
    overwrite: bool = True
    object_name: str = ""
    observer: str = ""
    telescope: str = ""
    instrument: str = ""
    exposure_seconds: float | None = None
    focal_length_mm: float | None = None
    pixel_size_um: float | None = None

    @property
    def row_order(self) -> str:
        return "BOTTOM-UP" if self.flip_vertical else "TOP-DOWN"


class FitsExporter:
    """Turns frames of a :class:`SerReader` into FITS files."""

    def __init__(self, reader: SerReader, processor: FrameProcessor,
                 options: FitsExportOptions | None = None):
        self.reader = reader
        self.processor = processor
        self.options = options or FitsExportOptions()

    # -- pixel preparation -------------------------------------------------
    def _prepare(self, index: int) -> np.ndarray:
        """Fetch one frame and bring it into the requested colour/bit layout."""
        opts = self.options
        proc = self.processor
        reader = self.reader
        frame = reader.raw_frame(index)
        if frame.shape[2] == 1:
            frame = frame[:, :, 0]
        elif reader.colour_id is ColourID.BGR:
            frame = frame[:, :, ::-1]

        if opts.apply_crop:
            frame = proc.crop_frame(frame)

        raw_bayer = opts.colour_mode == "raw"
        if not raw_bayer:
            frame = proc.demosaic(frame)

        if opts.apply_processing:
            work = proc.process_float(frame)          # 0..1 floats
            if opts.colour_mode == "mono" and work.ndim == 3:
                work = apply_mono(work, proc.options.mono_mode)
            data = self._scale_from_float(work)
        else:
            if opts.colour_mode == "mono" and frame.ndim == 3:
                # Keep the original value scale: mono-mix in floats, then map
                # straight back onto the source range instead of stretching.
                max_value = float((1 << reader.pixel_depth) - 1)
                work = apply_mono(to_float(frame, reader.pixel_depth),
                                  proc.options.mono_mode)
                frame = np.clip(work * max_value + 0.5, 0, max_value).astype(frame.dtype)
            data = self._cast_native(frame)

        if opts.flip_vertical:
            data = data[::-1]

        # FITS wants colour on its own axis: (h, w, 3) -> (3, h, w)
        if data.ndim == 3:
            data = np.moveaxis(data, -1, 0)
        return np.ascontiguousarray(data)

    def _scale_from_float(self, work: np.ndarray) -> np.ndarray:
        depth = self.options.bit_depth
        if depth == "float32":
            return work.astype(np.float32)
        dtype = np.uint8 if (depth == "native" and self.reader.bytes_per_sample == 1) else np.uint16
        max_value = float(np.iinfo(dtype).max)
        return np.clip(work * max_value + 0.5, 0, max_value).astype(dtype)

    def _cast_native(self, frame: np.ndarray) -> np.ndarray:
        depth = self.options.bit_depth
        if depth == "float32":
            return to_float(frame, self.reader.pixel_depth)
        if depth == "uint16":
            return frame.astype(np.uint16, copy=False)
        return frame

    # -- header ------------------------------------------------------------
    def _base_header(self, first_index: int, last_index: int,
                     frame_count: int) -> fits.Header:
        opts = self.options
        reader = self.reader
        head = reader.header
        hdr = fits.Header()
        hdr["CREATOR"] = (f"{CREATOR}", "software that wrote this file")
        hdr["DATE"] = (datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
                       "file creation date (UTC)")
        start = reader.frame_datetime(first_index)
        if start is not None:
            hdr["DATE-OBS"] = (start.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3],
                               "start of the first exported frame (UTC)")
            hdr["MJD-OBS"] = (_to_mjd(start), "MJD of DATE-OBS")
        end = reader.frame_datetime(last_index)
        if end is not None and frame_count > 1:
            hdr["DATE-END"] = (end.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3],
                               "start of the last exported frame (UTC)")
        if opts.exposure_seconds:
            hdr["EXPTIME"] = (float(opts.exposure_seconds), "[s] exposure time per frame")
        if opts.object_name:
            hdr["OBJECT"] = opts.object_name
        for key, value, comment in (
            ("OBSERVER", opts.observer or head.observer, "observer"),
            ("TELESCOP", opts.telescope or head.telescope, "telescope"),
            ("INSTRUME", opts.instrument or head.instrument, "camera"),
        ):
            if value:
                hdr[key] = (value, comment)
        if opts.focal_length_mm:
            hdr["FOCALLEN"] = (float(opts.focal_length_mm), "[mm] focal length")
        if opts.pixel_size_um:
            hdr["XPIXSZ"] = (float(opts.pixel_size_um), "[um] pixel size")
            hdr["YPIXSZ"] = (float(opts.pixel_size_um), "[um] pixel size")
        hdr["ROWORDER"] = (opts.row_order, "order the image rows are stored in")

        if opts.colour_mode == "raw" and reader.colour_id.is_bayer:
            pattern = self.processor.options.bayer_override or reader.colour_id.bayer_pattern
            hdr["BAYERPAT"] = (pattern, "Bayer colour filter array pattern")
            x_off, y_off = self._bayer_offsets()
            hdr["XBAYROFF"] = (x_off, "Bayer pattern X offset")
            hdr["YBAYROFF"] = (y_off, "Bayer pattern Y offset")

        # Provenance of the SER source, so the file can be traced back.
        hdr["SERFILE"] = (os.path.basename(reader.path)[:68], "source SER file")
        hdr["SERCOLID"] = (int(reader.colour_id), "SER ColorID of the source")
        hdr["SERDEPTH"] = (reader.pixel_depth, "[bit] measured depth of the SER data")
        hdr["SERFRAMS"] = (reader.frame_count, "frames in the source SER file")
        hdr.add_history(
            f"Exported from {os.path.basename(reader.path)} by {CREATOR}"
        )
        if opts.apply_processing:
            hdr.add_history(
                "Display processing (gain/gamma/colour) was applied: "
                "pixel values are NOT linear."
            )
        else:
            hdr.add_history("Pixel values are the unmodified SER data.")
        return hdr

    def _bayer_offsets(self) -> tuple[int, int]:
        """Bayer origin shift introduced by an odd crop."""
        crop = self.processor.options.crop
        if not (self.options.apply_crop and crop.valid):
            return 0, 0
        return crop.x % 2, crop.y % 2

    # -- public API ---------------------------------------------------------
    def export(self, path: str, indices: Sequence[int],
               progress: ProgressCallback | None = None) -> list[str]:
        """Write the frames in ``indices`` and return the files created."""
        indices = list(indices)
        if not indices:
            raise ValueError("no frames selected for export")
        if self.options.layout == "sequence":
            return self._export_sequence(path, indices, progress)
        return self._export_cube(path, indices, progress)

    def _export_cube(self, path: str, indices: Sequence[int],
                     progress: ProgressCallback | None) -> list[str]:
        """Stream the cube to disk so file size is limited by disk, not RAM."""
        total = len(indices)
        first = self._prepare(indices[0])
        shape = first.shape if total == 1 else (total, *first.shape)
        hdr = self._cube_header(first.dtype, shape, indices, total)

        if os.path.exists(path):
            if not self.options.overwrite:
                raise FileExistsError(path)
            os.remove(path)

        stream = fits.StreamingHDU(path, hdr)
        try:
            stream.write(_encode(first, first.dtype))
            if progress and not progress(1, total):
                raise ExportCancelled()
            for position, index in enumerate(indices[1:], start=1):
                frame = self._prepare(index)
                if frame.shape != first.shape:
                    raise ValueError(
                        "frames changed size during export; keep the crop fixed"
                    )
                stream.write(_encode(frame, first.dtype))
                if progress and not progress(position + 1, total):
                    raise ExportCancelled()
        except BaseException:
            stream.close()
            if os.path.exists(path):
                os.remove(path)
            raise
        stream.close()

        table = self._timestamp_table(indices)
        if table is not None:
            fits.append(path, table.data, table.header)
        return [path]

    def _cube_header(self, dtype: np.dtype, shape: tuple[int, ...],
                     indices: Sequence[int], total: int) -> fits.Header:
        """Mandatory FITS cards first, then all of our metadata."""
        hdr = fits.Header()
        hdr["SIMPLE"] = (True, "conforms to FITS standard")
        hdr["BITPIX"] = (_bitpix(dtype), "bits per pixel")
        hdr["NAXIS"] = (len(shape), "number of axes")
        for axis, length in enumerate(reversed(shape), start=1):
            hdr[f"NAXIS{axis}"] = length
        hdr["EXTEND"] = True
        if dtype == np.uint16:
            hdr["BZERO"] = (32768, "offset for unsigned 16 bit data")
            hdr["BSCALE"] = (1, "linear scaling factor")

        meta = self._base_header(indices[0], indices[-1], total)
        meta["SERFRAME"] = (indices[0] + 1, "1-based index of the first frame in the SER")
        if total > 1:
            meta["NFRAMES"] = (total, "number of exported frames")
            meta.add_comment(
                f"NAXIS{len(shape)} is the time axis (one plane per SER frame)"
            )
        if len(shape) >= 3 and shape[-3] == 3 and self.options.colour_mode != "raw":
            meta["CTYPE3"] = ("RGB", "colour axis: 1=red 2=green 3=blue")
        hdr.extend(meta, unique=True)
        return hdr

    def _export_sequence(self, path: str, indices: Sequence[int],
                         progress: ProgressCallback | None) -> list[str]:
        base, ext = os.path.splitext(path)
        if ext.lower() not in (".fits", ".fit", ".fts"):
            ext = ".fits"
        written: list[str] = []
        total = len(indices)
        digits = max(5, len(str(self.reader.frame_count)))
        for position, index in enumerate(indices):
            data = self._prepare(index)
            hdr = self._base_header(index, index, 1)
            hdr["SERFRAME"] = (index + 1, "1-based frame index in the source SER")
            if data.ndim == 3 and data.shape[0] == 3 and self.options.colour_mode != "raw":
                hdr["CTYPE3"] = ("RGB", "colour axis: 1=red 2=green 3=blue")
            out = f"{base}_{index + 1:0{digits}d}{ext}"
            fits.PrimaryHDU(data=data, header=hdr).writeto(
                out, overwrite=self.options.overwrite
            )
            written.append(out)
            if progress and not progress(position + 1, total):
                raise ExportCancelled()
        return written

    def _timestamp_table(self, indices: Sequence[int]) -> fits.BinTableHDU | None:
        stamps = [self.reader.timestamp(i) for i in indices]
        if not any(stamps):
            return None
        numbers = np.asarray([i + 1 for i in indices], dtype=np.int32)
        mjd = np.asarray([_to_mjd(s) if s else np.nan for s in stamps], dtype=np.float64)
        iso = np.asarray(
            [s.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] if s else "" for s in stamps]
        )
        table = fits.BinTableHDU.from_columns(
            [
                fits.Column(name="FRAME", format="J", array=numbers),
                fits.Column(name="MJD_UTC", format="D", unit="d", array=mjd),
                fits.Column(name="DATE_OBS", format="A23", array=iso),
            ],
            name="FRAMETIME",
        )
        table.header["COMMENT"] = "UTC time of each frame taken from the SER trailer"
        return table


class ExportCancelled(Exception):
    """Raised when a progress callback asks for the export to stop."""


def _bitpix(dtype: np.dtype) -> int:
    mapping = {np.dtype(np.uint8): 8, np.dtype(np.uint16): 16,
               np.dtype(np.int16): 16, np.dtype(np.float32): -32,
               np.dtype(np.float64): -64}
    try:
        return mapping[np.dtype(dtype)]
    except KeyError:
        raise ValueError(f"unsupported FITS data type {dtype}") from None


def _encode(data: np.ndarray, dtype: np.dtype) -> np.ndarray:
    """Encode unsigned 16 bit data the way FITS stores it (BZERO offset)."""
    if np.dtype(dtype) == np.uint16:
        return (data.astype(np.int32) - 32768).astype(np.int16)
    return data


def _to_mjd(value: datetime) -> float:
    """Modified Julian Date of a UTC datetime (no leap second handling)."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    unix = value.timestamp()
    return unix / 86400.0 + 40587.0


def frame_indices(count: int, start: int = 0, end: int | None = None,
                  step: int = 1, reverse: bool = False) -> list[int]:
    """Utility used by the dialogs to turn a range into a list of indices."""
    end = count - 1 if end is None else end
    indices = list(range(max(0, start), min(count - 1, end) + 1, max(1, step)))
    return list(reversed(indices)) if reverse else indices

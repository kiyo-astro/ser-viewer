"""Histogram and basic statistics for the histogram dialog."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class Histogram:
    """Per channel histogram of one frame, normalised to the 0..1 range."""

    bins: np.ndarray               # bin centres, 0..1
    counts: np.ndarray             # shape (channels, bins)
    channels: tuple[str, ...]
    minimum: np.ndarray            # per channel, 0..1
    maximum: np.ndarray
    mean: np.ndarray
    median: np.ndarray
    clipped_low: np.ndarray        # fraction of pixels at 0
    clipped_high: np.ndarray       # fraction of pixels at full scale

    @property
    def peak(self) -> int:
        return int(self.counts.max()) if self.counts.size else 0


def compute_histogram(image: np.ndarray, bin_count: int = 256) -> Histogram:
    """Histogram of an 8/16 bit or float image.

    Integer images are scaled by the full range of their dtype, so pass data
    that has already been mapped onto that range (what the display shows).
    """
    if image.dtype.kind == "u":
        scale = float(np.iinfo(image.dtype).max)
        data = image.astype(np.float32) / scale
    else:
        data = image.astype(np.float32)

    if data.ndim == 2:
        planes = [data]
        names = ("Mono",)
    else:
        planes = [data[..., i] for i in range(data.shape[2])]
        names = ("Red", "Green", "Blue")[: len(planes)]

    edges = np.linspace(0.0, 1.0, bin_count + 1, dtype=np.float32)
    counts = np.empty((len(planes), bin_count), dtype=np.int64)
    stats = {key: np.empty(len(planes), dtype=np.float64)
             for key in ("min", "max", "mean", "median", "low", "high")}
    for index, plane in enumerate(planes):
        flat = plane.reshape(-1)
        counts[index] = np.histogram(flat, bins=edges)[0]
        stats["min"][index] = float(flat.min())
        stats["max"][index] = float(flat.max())
        stats["mean"][index] = float(flat.mean())
        stats["median"][index] = float(np.median(flat))
        stats["low"][index] = float(np.count_nonzero(flat <= 0.0) / flat.size)
        stats["high"][index] = float(np.count_nonzero(flat >= 1.0) / flat.size)

    return Histogram(
        bins=(edges[:-1] + edges[1:]) / 2.0,
        counts=counts,
        channels=names,
        minimum=stats["min"],
        maximum=stats["max"],
        mean=stats["mean"],
        median=stats["median"],
        clipped_low=stats["low"],
        clipped_high=stats["high"],
    )

"""透明波段候选窗评分与自动选取。"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

_src = Path(__file__).resolve().parents[1]
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from data_io import Spectrum  # noqa: E402
from preprocess import preprocess  # noqa: E402
from two_beam import estimate_two_beam  # noqa: E402

MIN_EXTREMA = 15
MAX_FFT_EXTREMA_REL_DIFF_PCT = 2.0

CANDIDATE_BANDS_SIC = (
    (1500.0, 3000.0),
    (1100.0, 3500.0),
    (1200.0, 4000.0),
    (1100.0, 4000.0),
)
CANDIDATE_BANDS_SI = (
    (1500.0, 3000.0),
    (1000.0, 3500.0),
    (1200.0, 4000.0),
    (1000.0, 4000.0),
)


@dataclass
class BandScore:
    lo: float
    hi: float
    extrema_count: int
    spacing_mad_cm1: float
    fft_um: float
    extrema_um: float
    fft_extrema_rel_diff_pct: float
    passes_filters: bool
    selected: bool = False


def _extrema_um(peak_um: float, valley_um: float, fft_um: float) -> float:
    values = [v for v in (peak_um, valley_um) if np.isfinite(v)]
    return float(np.median(values)) if values else float(fft_um)


def _spacing_mad(wavenumber_cm1: np.ndarray, peak_indices: np.ndarray, valley_indices: np.ndarray) -> float:
    spacings: list[float] = []
    if len(peak_indices) >= 2:
        spacings.extend(np.diff(wavenumber_cm1[peak_indices]).tolist())
    if len(valley_indices) >= 2:
        spacings.extend(np.diff(wavenumber_cm1[valley_indices]).tolist())
    if len(spacings) < 2:
        return float("inf")
    arr = np.asarray(spacings, dtype=float)
    median = float(np.median(arr))
    return float(np.median(np.abs(arr - median)))


def _relative_diff(first: float, second: float) -> float:
    if not np.isfinite(first) or not np.isfinite(second):
        return float("inf")
    mean = (first + second) / 2.0
    if mean <= 0:
        return float("inf")
    return float(abs(first - second) / mean * 100.0)


def score_band(spectrum: Spectrum, band: tuple[float, float]) -> BandScore:
    lo, hi = band
    try:
        processed = preprocess(spectrum, fit_band_cm1=band)
        two = estimate_two_beam(processed)
    except ValueError:
        return BandScore(lo, hi, 0, float("inf"), float("nan"), float("nan"), float("inf"), False)

    extrema_count = len(two.peak_indices) + len(two.valley_indices)
    spacing_mad = _spacing_mad(processed.wavenumber_cm1, two.peak_indices, two.valley_indices)
    extrema_um = _extrema_um(two.thickness_peaks_um, two.thickness_valleys_um, two.thickness_fft_um)
    rel_diff = _relative_diff(two.thickness_fft_um, extrema_um)
    passes = extrema_count >= MIN_EXTREMA and rel_diff < MAX_FFT_EXTREMA_REL_DIFF_PCT
    return BandScore(lo, hi, extrema_count, spacing_mad, two.thickness_fft_um, extrema_um, rel_diff, passes)


def _candidate_bands(spectrum: Spectrum) -> tuple[tuple[float, float], ...]:
    if spectrum.spec.material == "SiC":
        return CANDIDATE_BANDS_SIC
    return CANDIDATE_BANDS_SI


def select_band(spectrum: Spectrum) -> tuple[tuple[float, float], list[BandScore]]:
    """对候选透明波段打分，返回最优窗及全部评分记录。"""
    scores = [score_band(spectrum, band) for band in _candidate_bands(spectrum)]
    passing = [item for item in scores if item.passes_filters]
    if passing:
        best = min(passing, key=lambda item: item.spacing_mad_cm1)
    else:
        viable = [item for item in scores if item.extrema_count >= MIN_EXTREMA]
        best = (
            min(viable, key=lambda item: item.spacing_mad_cm1)
            if viable
            else min(scores, key=lambda item: (item.spacing_mad_cm1, item.fft_extrema_rel_diff_pct))
        )
    for item in scores:
        item.selected = item.lo == best.lo and item.hi == best.hi
    return (best.lo, best.hi), scores


def build_sensitivity_rows(dataset_key: str, material: str, scores: list[BandScore]) -> list[dict]:
    rows: list[dict] = []
    for item in scores:
        rows.append(
            {
                "dataset": dataset_key,
                "material": material,
                "band_lo_cm1": item.lo,
                "band_hi_cm1": item.hi,
                "extrema_count": item.extrema_count,
                "spacing_mad_cm1": item.spacing_mad_cm1,
                "fft_um": item.fft_um,
                "extrema_um": item.extrema_um,
                "fft_extrema_rel_diff_pct": item.fft_extrema_rel_diff_pct,
                "passes_filters": item.passes_filters,
                "selected": item.selected,
            }
        )
    return rows

"""光谱平滑、基线分离和分析波段截取。"""

from dataclasses import dataclass

import numpy as np
from scipy.signal import savgol_filter

from config import BASELINE_WINDOW_CM1, NOISE_WINDOW_CM1
from data_io import Spectrum


@dataclass
class ProcessedSpectrum:
    wavenumber_cm1: np.ndarray
    reflectance_pct: np.ndarray
    smooth_pct: np.ndarray
    baseline_pct: np.ndarray
    residual_pct: np.ndarray
    spacing_cm1: float
    source: Spectrum


def _odd_window(width_cm1: float, spacing_cm1: float, n: int, polyorder: int) -> int:
    value = max(polyorder + 2, int(round(width_cm1 / spacing_cm1)))
    if value % 2 == 0:
        value += 1
    largest = n if n % 2 == 1 else n - 1
    return min(value, largest)


def preprocess(
    spectrum: Spectrum,
    noise_window_cm1: float = NOISE_WINDOW_CM1,
    baseline_window_cm1: float = BASELINE_WINDOW_CM1,
) -> ProcessedSpectrum:
    lo, hi = spectrum.spec.fit_band_cm1
    mask = (spectrum.wavenumber_cm1 >= lo) & (spectrum.wavenumber_cm1 <= hi)
    x = spectrum.wavenumber_cm1[mask]
    y = spectrum.reflectance_pct[mask]
    if len(x) < 100:
        raise ValueError(f"{spectrum.spec.key} 指定分析波段内数据不足")

    spacing = float(np.median(np.diff(x)))
    short = _odd_window(noise_window_cm1, spacing, len(x), 3)
    long = _odd_window(baseline_window_cm1, spacing, len(x), 3)
    smooth = savgol_filter(y, short, 3, mode="interp")
    baseline = savgol_filter(smooth, long, 3, mode="interp")
    residual = smooth - baseline
    return ProcessedSpectrum(x, y, smooth, baseline, residual, spacing, spectrum)

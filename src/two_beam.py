"""双光束条纹的周期、极值和全谱厚度估计。

流程：FFT 粗估 → 峰/谷间距 Theil–Sen → 相位模型精修。
thickness_refined_um 是后续多光束初值与谐波诊断的厚度锚点。
"""

from dataclasses import dataclass

import numpy as np
from scipy.optimize import minimize_scalar
from scipy.signal import find_peaks
from scipy.stats import theilslopes

from optics import phase_coordinate, round_trip_phase, thickness_from_fringe_spacing
from preprocess import ProcessedSpectrum


@dataclass
class TwoBeamResult:
    """双光束厚度估计与拟合质量指标。"""

    thickness_fft_um: float
    thickness_peaks_um: float
    thickness_valleys_um: float
    thickness_refined_um: float
    fringe_spacing_cm1: float
    peak_indices: np.ndarray
    valley_indices: np.ndarray
    fitted_residual: np.ndarray
    rmse_pct: float
    r2: float
    aicc: float


def _fft_thickness(processed: ProcessedSpectrum, n: float, angle_deg: float) -> float:
    """由残差条纹功率谱主峰对应频率换算厚度初值。"""
    x, residual = processed.wavenumber_cm1, processed.residual_pct
    window = np.hanning(len(residual))
    power = np.abs(np.fft.rfft((residual - residual.mean()) * window)) ** 2
    frequency = np.fft.rfftfreq(len(residual), processed.spacing_cm1)
    optical_factor = n * np.sqrt(1.0 - (np.sin(np.deg2rad(angle_deg)) / n) ** 2)
    d_um = frequency * 1e4 / (2.0 * optical_factor)
    valid = (d_um >= 1.0) & (d_um <= 20.0)
    if not np.any(valid):
        raise ValueError("FFT 搜索范围无有效频率")
    return float(d_um[valid][np.argmax(power[valid])])


def _extrema(
    processed: ProcessedSpectrum,
    approximate_period_cm1: float,
    sign: float,
) -> np.ndarray:
    """按预期周期与显著性寻找峰(+1)或谷(-1)索引，并裁掉边缘。"""
    residual = sign * processed.residual_pct
    distance = max(3, int(0.55 * approximate_period_cm1 / processed.spacing_cm1))
    prominence = max(0.03, 0.12 * float(np.std(residual)))
    indices, _ = find_peaks(residual, distance=distance, prominence=prominence)
    edge = int(round(70.0 / processed.spacing_cm1))
    return indices[(indices >= edge) & (indices < len(residual) - edge)]


def _spacing_from_indices(x: np.ndarray, indices: np.ndarray) -> float:
    """极值序号对波数的 Theil–Sen 斜率 ≈ 相邻同类极值间距。"""
    if len(indices) < 3:
        return float("nan")
    order = np.arange(len(indices), dtype=float)
    slope, _, _, _ = theilslopes(x[indices], order)
    return float(slope)


def _fit_at_thickness(
    processed: ProcessedSpectrum,
    thickness_um: float,
    n: float,
    angle_deg: float,
) -> tuple[np.ndarray, float, int]:
    x = processed.wavenumber_cm1
    z = (x - x.mean()) / np.ptp(x)
    phase = round_trip_phase(x, thickness_um, n, angle_deg)
    design = np.column_stack(
        [
            np.ones_like(z),
            z,
            np.cos(phase),
            np.sin(phase),
            z * np.cos(phase),
            z * np.sin(phase),
        ]
    )
    coefficients, *_ = np.linalg.lstsq(design, processed.residual_pct, rcond=None)
    fitted = design @ coefficients
    sse = float(np.sum((processed.residual_pct - fitted) ** 2))
    return fitted, sse, design.shape[1] + 1


def estimate_two_beam(processed: ProcessedSpectrum) -> TwoBeamResult:
    spec = processed.source.spec
    n, angle = spec.refractive_index, spec.angle_deg
    fft_um = _fft_thickness(processed, n, angle)
    optical_factor = n * np.sqrt(1.0 - (np.sin(np.deg2rad(angle)) / n) ** 2)
    approximate_period = 1e4 / (2.0 * optical_factor * fft_um)

    peaks = _extrema(processed, approximate_period, 1.0)
    valleys = _extrema(processed, approximate_period, -1.0)
    peak_spacing = _spacing_from_indices(processed.wavenumber_cm1, peaks)
    valley_spacing = _spacing_from_indices(processed.wavenumber_cm1, valleys)
    peak_um = (
        thickness_from_fringe_spacing(peak_spacing, n, angle)
        if np.isfinite(peak_spacing)
        else float("nan")
    )
    valley_um = (
        thickness_from_fringe_spacing(valley_spacing, n, angle)
        if np.isfinite(valley_spacing)
        else float("nan")
    )
    extrema_candidates = [v for v in (peak_um, valley_um) if np.isfinite(v)]
    candidates = extrema_candidates or [fft_um]
    initial = float(np.median(candidates))

    # 常折射率全谱拟合在宽波段会因真实色散发生相位漂移。只允许其在
    # 稳健极值回归附近作小幅精修，避免跳到相邻干涉级次。
    lower, upper = max(0.5, 0.97 * initial), min(30.0, 1.03 * initial)
    optimum = minimize_scalar(
        lambda d: _fit_at_thickness(processed, d, n, angle)[1],
        bounds=(lower, upper),
        method="bounded",
        options={"xatol": 1e-7},
    )
    refined = float(optimum.x)
    if abs(refined - initial) / initial > 0.01:
        refined = initial
    fitted, sse, parameters = _fit_at_thickness(processed, refined, n, angle)
    residual = processed.residual_pct
    rmse = float(np.sqrt(sse / len(residual)))
    total = float(np.sum((residual - residual.mean()) ** 2))
    r2 = float(1.0 - sse / total) if total > 0 else float("nan")
    count = len(residual)
    aic = count * np.log(max(sse / count, 1e-15)) + 2 * parameters
    aicc = float(aic + 2 * parameters * (parameters + 1) / max(1, count - parameters - 1))
    spacing = float(np.nanmedian([peak_spacing, valley_spacing]))
    return TwoBeamResult(
        fft_um,
        peak_um,
        valley_um,
        refined,
        spacing,
        peaks,
        valleys,
        fitted,
        rmse,
        r2,
        aicc,
    )

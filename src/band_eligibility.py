"""v8 厚度反演的透明波段物理资格检查。"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from dispersion import material_refractive_index
from preprocess import ProcessedSpectrum


@dataclass(frozen=True)
class BandEligibility:
    material: str
    scenario: str
    mask: np.ndarray
    n_real: np.ndarray
    extinction_k: np.ndarray
    phase_coordinate_cm1: np.ndarray
    eligible_width_cm1: float
    eligible_fraction: float
    monotonic: bool
    qualified: bool
    failure_reason: str


def evaluate_band_eligibility(
    processed: ProcessedSpectrum,
    material: str,
    scenario: str,
    mode: str,
    epi_carrier_cm3: float,
    max_extinction: float = 0.08,
) -> BandEligibility:
    """筛出弱吸收、相位坐标单调且远离边缘的厚度可用数据。"""
    x = np.asarray(processed.wavenumber_cm1, dtype=float)
    index = material_refractive_index(
        material,
        x,
        epi_carrier_cm3,
        mode=mode,
    )
    n_real = np.real(index)
    extinction = np.imag(index)
    sin0 = np.sin(np.deg2rad(processed.source.spec.angle_deg))
    radicand = n_real**2 - sin0**2
    coordinate = x * np.sqrt(np.maximum(radicand, 0.0))
    derivative = np.gradient(coordinate, x)

    mask = (
        np.isfinite(n_real)
        & np.isfinite(extinction)
        & np.isfinite(coordinate)
        & (n_real > sin0)
        & (extinction <= max_extinction)
        & (derivative > 0)
        & (x >= 1200.0)
        & (x <= 4000.0)
    )
    if material == "SiC":
        mask &= ~((x >= 1300.0) & (x <= 1600.0))
    edge = max(1, int(round(70.0 / processed.spacing_cm1)))
    mask[:edge] = False
    mask[-edge:] = False

    if np.any(mask):
        eligible_x = x[mask]
        width = float(np.ptp(eligible_x))
        monotonic = bool(np.all(np.diff(coordinate[mask]) > 0))
    else:
        width = 0.0
        monotonic = False
    fraction = float(np.mean(mask))
    reasons = []
    if width < 1000.0:
        reasons.append("共同透明区宽度不足 1000 cm^-1")
    if not monotonic:
        reasons.append("光学相位坐标不严格单调")
    if np.count_nonzero(mask) < 200:
        reasons.append("合格采样点不足")
    return BandEligibility(
        material=material,
        scenario=scenario,
        mask=mask,
        n_real=n_real,
        extinction_k=extinction,
        phase_coordinate_cm1=coordinate,
        eligible_width_cm1=width,
        eligible_fraction=fraction,
        monotonic=monotonic,
        qualified=not reasons,
        failure_reason="；".join(reasons),
    )

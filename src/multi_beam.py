"""Airy 多光束模型与有界全谱拟合。"""

from dataclasses import dataclass

import numpy as np
from scipy.optimize import differential_evolution, minimize

from optics import airy_normalized, round_trip_phase
from preprocess import ProcessedSpectrum
from two_beam import TwoBeamResult


@dataclass
class MultiBeamResult:
    thickness_um: float
    effective_reflectivity: float
    phase_offset_rad: float
    fitted_residual: np.ndarray
    rmse_pct: float
    r2: float
    aicc: float
    optimization_success: bool


def _fit_linear_part(
    processed: ProcessedSpectrum,
    thickness_um: float,
    reflectivity: float,
    phase_offset: float,
) -> tuple[np.ndarray, float, int]:
    spec = processed.source.spec
    x = processed.wavenumber_cm1
    z = (x - x.mean()) / np.ptp(x)
    phase = round_trip_phase(x, thickness_um, spec.refractive_index, spec.angle_deg)
    airy = airy_normalized(phase + phase_offset, reflectivity)
    airy = airy - airy.mean()
    design = np.column_stack([np.ones_like(z), z, airy, z * airy])
    coefficients, *_ = np.linalg.lstsq(design, processed.residual_pct, rcond=None)
    fitted = design @ coefficients
    sse = float(np.sum((processed.residual_pct - fitted) ** 2))
    return fitted, sse, design.shape[1] + 3


def fit_multi_beam(
    processed: ProcessedSpectrum,
    two_beam: TwoBeamResult,
    global_search: bool = True,
) -> MultiBeamResult:
    initial = two_beam.thickness_refined_um
    bounds = [
        (max(0.5, 0.92 * initial), min(30.0, 1.08 * initial)),
        (0.002, 0.92),
        (-np.pi, np.pi),
    ]

    objective = lambda p: _fit_linear_part(processed, p[0], p[1], p[2])[1]
    if global_search:
        coarse = differential_evolution(
            objective,
            bounds,
            seed=2025,
            popsize=7,
            maxiter=24,
            polish=False,
            updating="immediate",
        )
        start = coarse.x
    else:
        start = np.array([initial, 0.2, 0.0])

    refined = minimize(
        objective,
        start,
        method="L-BFGS-B",
        bounds=bounds,
        options={"maxiter": 1500, "ftol": 1e-12},
    )
    d, reflectivity, phase_offset = refined.x
    d = float(np.clip(d, bounds[0][0], bounds[0][1]))
    reflectivity = float(np.clip(reflectivity, bounds[1][0], bounds[1][1]))
    phase_offset = float((phase_offset + np.pi) % (2 * np.pi) - np.pi)
    fitted, sse, parameters = _fit_linear_part(
        processed, d, reflectivity, phase_offset
    )
    observed = processed.residual_pct
    count = len(observed)
    rmse = float(np.sqrt(sse / count))
    total = float(np.sum((observed - observed.mean()) ** 2))
    r2 = float(1.0 - sse / total) if total > 0 else float("nan")
    aic = count * np.log(max(sse / count, 1e-15)) + 2 * parameters
    aicc = float(aic + 2 * parameters * (parameters + 1) / max(1, count - parameters - 1))
    return MultiBeamResult(
        d,
        reflectivity,
        phase_offset,
        fitted,
        rmse,
        r2,
        aicc,
        bool(refined.success),
    )

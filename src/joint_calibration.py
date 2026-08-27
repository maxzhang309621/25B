"""双角度共享厚度与载流子参数的低维联合校准。"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
from scipy.optimize import least_squares, minimize_scalar

from dispersion import (
    CARRIER_BOUNDS_LOG10,
    CARRIER_PRIOR_LOG10,
    CARRIER_SCENARIOS_CM3,
    METADATA,
    material_epsilon,
    material_refractive_index,
)
from optics import thin_film_reflectance
from preprocess import ProcessedSpectrum


@dataclass
class ScenarioThickness:
    name: str
    epi_carrier_cm3: float
    substrate_carrier_cm3: float
    thickness_um: float
    rmse_pct: float


@dataclass
class JointCalibrationResult:
    material: str
    fitted_thickness_um: float
    adopted_thickness_um: float
    epi_carrier_cm3: float
    substrate_carrier_cm3: float
    rmse_pct: float
    jacobian_condition: float
    max_parameter_correlation: float
    concentration_identifiable: bool
    boundary_hit: bool
    adopted_basis: str
    systematic_low_um: float
    systematic_high_um: float
    band_thicknesses_um: list[float]
    band_cv_pct: float
    max_band_shift_pct: float
    band_stable: bool
    scenarios: list[ScenarioThickness]
    model: str
    references: tuple[str, ...]
    fallback_reason: str
    statistical_std_um: float = float("nan")
    statistical_ci95_low_um: float = float("nan")
    statistical_ci95_high_um: float = float("nan")

    def to_dict(self) -> dict:
        return asdict(self)


def _profiled_fit(
    processed: ProcessedSpectrum, physical_reflectance: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """用线性增益/基线吸收仪器标定，不改变物理相位参数。"""
    y = processed.smooth_pct
    z = (processed.wavenumber_cm1 - processed.wavenumber_cm1.mean()) / np.ptp(
        processed.wavenumber_cm1
    )
    physical_pct = 100.0 * physical_reflectance
    design = np.column_stack(
        [np.ones_like(z), z, physical_pct, z * physical_pct]
    )
    coefficients, *_ = np.linalg.lstsq(design, y, rcond=None)
    fitted = design @ coefficients
    return fitted, y - fitted


def _spectrum_residual(
    processed: ProcessedSpectrum,
    material: str,
    thickness_um: float,
    epi_carrier_cm3: float,
    substrate_carrier_cm3: float,
) -> tuple[np.ndarray, np.ndarray]:
    x = processed.wavenumber_cm1
    eps_epi = material_epsilon(material, x, epi_carrier_cm3)
    eps_sub = material_epsilon(material, x, substrate_carrier_cm3)
    physical = thin_film_reflectance(
        x, thickness_um, processed.source.spec.angle_deg, eps_epi, eps_sub
    )
    return _profiled_fit(processed, physical)


def _calibration_mask(processed: ProcessedSpectrum, material: str) -> np.ndarray:
    """排除当前简化介电函数未描述的 SiC 二声子吸收区。"""
    x = processed.wavenumber_cm1
    if material == "SiC":
        return ~((x >= 1300.0) & (x <= 1600.0))
    return np.ones_like(x, dtype=bool)


def _normalized_data_residual(
    params: np.ndarray,
    spectra: list[ProcessedSpectrum],
    material: str,
    stride: int,
) -> np.ndarray:
    thickness, log_epi, log_sub = params
    pieces = []
    for processed in spectra:
        _, residual = _spectrum_residual(
            processed,
            material,
            thickness,
            10.0**log_epi,
            10.0**log_sub,
        )
        residual = residual[_calibration_mask(processed, material)][::stride]
        noise = max(float(np.std(processed.residual_pct)), 0.05)
        pieces.append(residual / noise / np.sqrt(len(residual)))
    return np.concatenate(pieces)


def _objective_residual(
    params: np.ndarray,
    spectra: list[ProcessedSpectrum],
    material: str,
    stride: int,
    initial_thickness_um: float,
) -> np.ndarray:
    data = _normalized_data_residual(params, spectra, material, stride)
    prior = CARRIER_PRIOR_LOG10[material]
    regularization = np.array(
        [
            (params[0] - initial_thickness_um) / (0.2 * initial_thickness_um),
            (params[1] - prior["epi"]) / 1.5,
            (params[2] - prior["substrate"]) / 1.5,
        ]
    )
    return np.r_[data, regularization]


def _finite_difference_jacobian(
    params: np.ndarray,
    spectra: list[ProcessedSpectrum],
    material: str,
    stride: int,
) -> np.ndarray:
    columns = []
    steps = np.array([max(1e-4, params[0] * 1e-4), 1e-3, 1e-3])
    for index, step in enumerate(steps):
        plus, minus = params.copy(), params.copy()
        plus[index] += step
        minus[index] -= step
        columns.append(
            (
                _normalized_data_residual(plus, spectra, material, stride)
                - _normalized_data_residual(minus, spectra, material, stride)
            )
            / (2.0 * step)
        )
    return np.column_stack(columns)


def _identifiability(
    params: np.ndarray,
    spectra: list[ProcessedSpectrum],
    material: str,
    stride: int,
    lower: np.ndarray,
    upper: np.ndarray,
) -> tuple[float, float, bool, bool]:
    jacobian = _finite_difference_jacobian(params, spectra, material, stride)
    singular = np.linalg.svd(jacobian, compute_uv=False)
    condition = float(singular[0] / max(singular[-1], 1e-15))
    covariance = np.linalg.pinv(jacobian.T @ jacobian)
    scales = np.sqrt(np.maximum(np.diag(covariance), 0.0))
    denominator = np.outer(scales, scales)
    correlation = np.divide(
        covariance,
        denominator,
        out=np.zeros_like(covariance),
        where=denominator > 0,
    )
    off_diagonal = correlation - np.diag(np.diag(correlation))
    max_correlation = float(np.max(np.abs(off_diagonal)))
    tolerance = 2e-3 * np.maximum(upper - lower, 1.0)
    boundary_hit = bool(
        np.any(params - lower <= tolerance) or np.any(upper - params <= tolerance)
    )
    identifiable = bool(
        condition < 1e8 and max_correlation < 0.95 and not boundary_hit
    )
    return condition, max_correlation, boundary_hit, identifiable


def _scenario_fit(
    spectra: list[ProcessedSpectrum],
    material: str,
    name: str,
    epi_carrier_cm3: float,
    substrate_carrier_cm3: float,
    thickness_bounds: tuple[float, float],
    wavenumber_band: tuple[float, float] | None = None,
) -> ScenarioThickness:
    def mask_for(spectrum: ProcessedSpectrum) -> np.ndarray:
        mask = _calibration_mask(spectrum, material)
        if wavenumber_band is not None:
            lo, hi = wavenumber_band
            mask &= (spectrum.wavenumber_cm1 >= lo) & (
                spectrum.wavenumber_cm1 <= hi
            )
        return mask

    def objective(thickness: float) -> float:
        return float(
            sum(
                np.sum(
                    _spectrum_residual(
                        spectrum,
                        material,
                        thickness,
                        epi_carrier_cm3,
                        substrate_carrier_cm3,
                    )[1][mask_for(spectrum)]
                    ** 2
                )
                for spectrum in spectra
            )
        )

    optimum = minimize_scalar(objective, bounds=thickness_bounds, method="bounded")
    residuals = np.concatenate(
        [
            _spectrum_residual(
                spectrum,
                material,
                float(optimum.x),
                epi_carrier_cm3,
                substrate_carrier_cm3,
            )[1][mask_for(spectrum)]
            for spectrum in spectra
        ]
    )
    return ScenarioThickness(
        name,
        epi_carrier_cm3,
        substrate_carrier_cm3,
        float(optimum.x),
        float(np.sqrt(np.mean(residuals**2))),
    )


def _band_stability(
    spectra: list[ProcessedSpectrum],
    material: str,
    epi_carrier_cm3: float,
    substrate_carrier_cm3: float,
    thickness_um: float,
    thickness_bounds: tuple[float, float],
) -> tuple[list[float], float, float, bool]:
    lo = max(float(s.wavenumber_cm1.min()) for s in spectra)
    hi = min(float(s.wavenumber_cm1.max()) for s in spectra)
    edges = np.linspace(lo, hi, 4)
    values = [
        _scenario_fit(
            spectra,
            material,
            f"band_{index + 1}",
            epi_carrier_cm3,
            substrate_carrier_cm3,
            thickness_bounds,
            (float(edges[index]), float(edges[index + 1])),
        ).thickness_um
        for index in range(3)
    ]
    array = np.asarray(values)
    cv_pct = float(np.std(array, ddof=1) / np.mean(array) * 100.0)
    max_shift_pct = float(np.max(np.abs(array - thickness_um)) / thickness_um * 100.0)
    return values, cv_pct, max_shift_pct, bool(cv_pct <= 1.0 and max_shift_pct <= 2.0)


def fit_joint_calibration(
    spectra: list[ProcessedSpectrum],
    initial_thicknesses_um: list[float],
    material: str,
    max_points_per_spectrum: int = 1000,
) -> JointCalibrationResult:
    """联合同一材料的两个角度；浓度不可辨识时采用情景厚度。"""
    if len(spectra) < 2 or len(initial_thicknesses_um) != len(spectra):
        raise ValueError("联合校准至少需要两个角度及对应厚度初值")
    if material not in METADATA:
        raise ValueError(f"不支持的材料：{material}")
    initial = float(np.median(initial_thicknesses_um))
    thickness_bounds = (max(0.2, 0.88 * initial), 1.12 * initial)
    carrier_bounds = CARRIER_BOUNDS_LOG10[material]
    lower = np.array(
        [thickness_bounds[0], carrier_bounds["epi"][0], carrier_bounds["substrate"][0]]
    )
    upper = np.array(
        [thickness_bounds[1], carrier_bounds["epi"][1], carrier_bounds["substrate"][1]]
    )
    stride = max(
        1, max(int(np.ceil(len(s.wavenumber_cm1) / max_points_per_spectrum)) for s in spectra)
    )

    prior = CARRIER_PRIOR_LOG10[material]
    starts = [
        np.array([initial, prior["epi"], prior["substrate"]]),
        *[
            np.array([initial, np.log10(epi), np.log10(sub)])
            for epi, sub in CARRIER_SCENARIOS_CM3[material].values()
        ],
    ]
    fits = [
        least_squares(
            _objective_residual,
            np.clip(start, lower + 1e-8, upper - 1e-8),
            bounds=(lower, upper),
            args=(spectra, material, stride, initial),
            loss="soft_l1",
            x_scale="jac",
            max_nfev=350,
        )
        for start in starts
    ]
    best = min(fits, key=lambda fit: float(np.sum(fit.fun**2)))
    params = np.asarray(best.x, dtype=float)
    condition, max_correlation, boundary_hit, identifiable = _identifiability(
        params, spectra, material, stride, lower, upper
    )

    scenarios = [
        _scenario_fit(
            spectra,
            material,
            name,
            epi,
            substrate,
            thickness_bounds,
        )
        for name, (epi, substrate) in CARRIER_SCENARIOS_CM3[material].items()
    ]
    scenario_thickness = np.array([scenario.thickness_um for scenario in scenarios])
    best_scenario = min(scenarios, key=lambda scenario: scenario.rmse_pct)
    all_residuals = np.concatenate(
        [
            _spectrum_residual(
                spectrum,
                material,
                params[0],
                10.0 ** params[1],
                10.0 ** params[2],
            )[1][_calibration_mask(spectrum, material)]
            for spectrum in spectra
        ]
    )
    fitted_rmse = float(np.sqrt(np.mean(all_residuals**2)))
    scenario_dominates = fitted_rmse > 1.02 * best_scenario.rmse_pct
    if scenario_dominates:
        identifiable = False
    candidate_thickness = float(params[0] if identifiable else best_scenario.thickness_um)
    candidate_epi = float(10.0 ** params[1] if identifiable else best_scenario.epi_carrier_cm3)
    candidate_sub = float(
        10.0 ** params[2] if identifiable else best_scenario.substrate_carrier_cm3
    )
    band_values, band_cv, max_band_shift, band_stable = _band_stability(
        spectra,
        material,
        candidate_epi,
        candidate_sub,
        candidate_thickness,
        thickness_bounds,
    )
    if not band_stable:
        identifiable = False
    adopted = float(params[0] if identifiable else best_scenario.thickness_um)
    if not identifiable and candidate_thickness != adopted:
        band_values, band_cv, max_band_shift, band_stable = _band_stability(
            spectra,
            material,
            best_scenario.epi_carrier_cm3,
            best_scenario.substrate_carrier_cm3,
            adopted,
            thickness_bounds,
        )
    if not band_stable:
        adopted = initial
    if identifiable:
        adopted_basis = "双角度自由载流子联合拟合"
    elif band_stable:
        adopted_basis = f"固定掺杂情景：{best_scenario.name}"
    else:
        adopted_basis = "色散留段不稳定，回退常折射率基线"
    reasons = []
    if condition >= 1e8:
        reasons.append("Jacobian 病态")
    if max_correlation >= 0.95:
        reasons.append("厚度与载流子参数强相关")
    if boundary_hit:
        reasons.append("参数触及先验边界")
    if scenario_dominates:
        reasons.append("自由浓度拟合未优于固定掺杂情景")
    if not band_stable:
        reasons.append("连续波段厚度稳定性未通过")
    fallback_reason = "；".join(reasons) if reasons else ""
    metadata = METADATA[material]
    return JointCalibrationResult(
        material=material,
        fitted_thickness_um=float(params[0]),
        adopted_thickness_um=adopted,
        epi_carrier_cm3=float(10.0 ** params[1]),
        substrate_carrier_cm3=float(10.0 ** params[2]),
        rmse_pct=fitted_rmse,
        jacobian_condition=condition,
        max_parameter_correlation=max_correlation,
        concentration_identifiable=identifiable,
        boundary_hit=boundary_hit,
        adopted_basis=adopted_basis,
        systematic_low_um=float(np.min(scenario_thickness)),
        systematic_high_um=float(np.max(scenario_thickness)),
        band_thicknesses_um=[float(value) for value in band_values],
        band_cv_pct=band_cv,
        max_band_shift_pct=max_band_shift,
        band_stable=band_stable,
        scenarios=scenarios,
        model=metadata.model,
        references=metadata.references,
        fallback_reason=fallback_reason,
    )


def refractive_index_rows(
    material: str,
    result: JointCalibrationResult,
    wavenumber_cm1: np.ndarray,
) -> list[dict]:
    """生成外延层/衬底 n、k 可审计曲线。"""
    x = np.asarray(wavenumber_cm1, dtype=float)
    epi = material_refractive_index(material, x, result.epi_carrier_cm3)
    substrate = material_refractive_index(
        material, x, result.substrate_carrier_cm3
    )
    return [
        {
            "material": material,
            "wavenumber_cm1": float(nu),
            "wavelength_um": float(1e4 / nu),
            "n_epi": float(epi_value.real),
            "k_epi": float(epi_value.imag),
            "n_substrate": float(sub_value.real),
            "k_substrate": float(sub_value.imag),
        }
        for nu, epi_value, sub_value in zip(x, epi, substrate)
    ]

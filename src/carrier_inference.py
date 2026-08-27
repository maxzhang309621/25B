"""增强反射率模型：受约束仪器响应与载流子浓度轮廓区间。

参数向量布局（8 维）：
  [0] 厚度 d (µm)，锚定在稳健厚度 ±3%
  [1] log10(N_epi)
  [2] log10(N_sub)
  [3:5] 两角度增益
  [5:7] 两角度偏置 (%)
  [7] 共享斜率 (% / 归一化波数)

主表仅在门控通过时写 reported_*；候选值始终保留供诊断。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
from scipy.optimize import least_squares

from dispersion import (
    CARRIER_BOUNDS_LOG10,
    CARRIER_PRIOR_LOG10,
    CARRIER_SCENARIOS_CM3,
    material_epsilon,
)
from instrument_response import (
    ReflectanceQualification,
    carrier_spectral_weights,
    instrument_prediction,
    qualify_reflectance,
)
from optics import thin_film_reflectance
from preprocess import ProcessedSpectrum


@dataclass
class CarrierInferenceResult:
    """SiC 增强浓度反演结果；reported_* 可为 None 表示拒绝点估计。"""

    material: str
    measurement_mode: str
    qualification: dict
    identifiability_level: str
    candidate_thickness_um: float
    candidate_epi_carrier_cm3: float
    candidate_substrate_carrier_cm3: float
    reported_epi_carrier_cm3: float | None
    reported_substrate_carrier_cm3: float | None
    epi_log10_ci90: tuple[float, float] | None
    substrate_log10_ci90: tuple[float, float] | None
    epi_ci90_cm3: tuple[float, float] | None
    substrate_ci90_cm3: tuple[float, float] | None
    epi_interval_boundary_hit: bool
    substrate_interval_boundary_hit: bool
    thickness_boundary_hit: bool
    carrier_correlation: float
    fixed_scenario_improvement_pct: float
    gains: tuple[float, float]
    offsets_pct: tuple[float, float]
    shared_slope_pct: float
    objective: float
    fallback_reason: str
    informative_bands_cm1: tuple[tuple[float, float], ...]

    def to_dict(self) -> dict:
        return asdict(self)


def _noise_scale(spectrum: ProcessedSpectrum) -> float:
    """稳健噪声尺度（MAD→σ），下限 0.15% 防止过拟合噪声。"""
    noise = spectrum.reflectance_pct - spectrum.smooth_pct
    centered = noise - np.median(noise)
    return max(0.15, float(1.4826 * np.median(np.abs(centered))))


def _bounds(
    material: str, initial_thickness_um: float
) -> tuple[np.ndarray, np.ndarray]:
    """返回 8 维参数上下界；厚度收紧到初值 ±3% 以锚定厚度通道。"""
    carrier = CARRIER_BOUNDS_LOG10[material]
    lower = np.array(
        [
            0.97 * initial_thickness_um,
            carrier["epi"][0],
            carrier["substrate"][0],
            0.85,
            0.85,
            -8.0,
            -8.0,
            -5.0,
        ]
    )
    upper = np.array(
        [
            1.03 * initial_thickness_um,
            carrier["epi"][1],
            carrier["substrate"][1],
            1.15,
            1.15,
            8.0,
            8.0,
            5.0,
        ]
    )
    return lower, upper


def _subsampled_residual(
    params: np.ndarray,
    spectra: list[ProcessedSpectrum],
    material: str,
    stride: int,
) -> np.ndarray:
    """加权、按噪声归一化的残差；stride 降采样加速轮廓扫描。"""
    thickness, log_epi, log_sub = params[:3]
    gains = params[3:5]
    offsets = params[5:7]
    slope = params[7]
    pieces = []
    for index, spectrum in enumerate(spectra):
        x = spectrum.wavenumber_cm1[::stride]
        y = spectrum.smooth_pct[::stride]
        eps_epi = material_epsilon(material, x, 10.0**log_epi)
        eps_sub = material_epsilon(material, x, 10.0**log_sub)
        physical = thin_film_reflectance(
            x,
            thickness,
            spectrum.source.spec.angle_deg,
            eps_epi,
            eps_sub,
        )
        predicted = instrument_prediction(
            physical, x, gains[index], offsets[index], slope
        )
        weights = carrier_spectral_weights(material, x)
        pieces.append(
            (y - predicted) * np.sqrt(weights) / _noise_scale(spectrum)
        )
    return np.concatenate(pieces)


def _fit_with_fixed(
    start: np.ndarray,
    lower: np.ndarray,
    upper: np.ndarray,
    fixed: dict[int, float],
    spectra: list[ProcessedSpectrum],
    material: str,
    stride: int,
    max_nfev: int = 220,
):
    """固定若干参数（轮廓似然），仅优化其余自由参数。"""
    free_indices = [index for index in range(len(start)) if index not in fixed]
    free_start = np.clip(
        start[free_indices],
        lower[free_indices] + 1e-9,
        upper[free_indices] - 1e-9,
    )

    def residual(free_values: np.ndarray) -> np.ndarray:
        params = start.copy()
        params[free_indices] = free_values
        for index, value in fixed.items():
            params[index] = value
        return _subsampled_residual(params, spectra, material, stride)

    fit = least_squares(
        residual,
        free_start,
        bounds=(lower[free_indices], upper[free_indices]),
        loss="soft_l1",
        f_scale=2.0,
        x_scale="jac",
        max_nfev=max_nfev,
    )
    params = start.copy()
    params[free_indices] = fit.x
    for index, value in fixed.items():
        params[index] = value
    return fit, params


def _full_fit(
    spectra: list[ProcessedSpectrum],
    initial_thickness_um: float,
    material: str,
    stride: int,
) -> tuple[object, np.ndarray, np.ndarray, np.ndarray]:
    """多起点稳健最小二乘，降低局部最优风险。"""
    lower, upper = _bounds(material, initial_thickness_um)
    prior = CARRIER_PRIOR_LOG10[material]
    base_instrument = [1.0, 1.0, 0.0, 0.0, 0.0]
    starts = [
        np.array(
            [
                initial_thickness_um,
                prior["epi"],
                prior["substrate"],
                *base_instrument,
            ]
        ),
        *[
            np.array(
                [
                    initial_thickness_um,
                    np.log10(epi),
                    np.log10(substrate),
                    *base_instrument,
                ]
            )
            for epi, substrate in CARRIER_SCENARIOS_CM3[material].values()
        ],
    ]
    epi_grid = np.linspace(lower[1], upper[1], 5)[1:-1]
    sub_grid = np.linspace(lower[2], upper[2], 5)[1:-1]
    starts.extend(
        np.array(
            [
                initial_thickness_um,
                log_epi,
                log_sub,
                *base_instrument,
            ]
        )
        for log_epi in epi_grid
        for log_sub in sub_grid
    )
    fits = []
    for start in starts:
        fit = least_squares(
            _subsampled_residual,
            np.clip(start, lower + 1e-9, upper - 1e-9),
            bounds=(lower, upper),
            args=(spectra, material, stride),
            loss="soft_l1",
            f_scale=2.0,
            x_scale="jac",
            max_nfev=320,
        )
        fits.append(fit)
    best = min(fits, key=lambda value: float(2.0 * value.cost))
    return best, np.asarray(best.x, float), lower, upper


def _profile_parameter(
    target_index: int,
    best_params: np.ndarray,
    lower: np.ndarray,
    upper: np.ndarray,
    spectra: list[ProcessedSpectrum],
    material: str,
    stride: int,
    grid_points: int,
) -> tuple[tuple[float, float] | None, bool, list[dict], np.ndarray]:
    """对单个 log10(N) 做轮廓扫描，构造 90% 条件区间。

    Δχ² ≤ 2.706 对应 1 自由度约 90% 轮廓阈值；
    若接受区触到网格端点，标记为边界命中（区间单侧/无界）。
    """
    grid = np.linspace(lower[target_index], upper[target_index], grid_points)
    costs = []
    starts = best_params.copy()
    fitted_params = []
    for value in grid:
        fit, params = _fit_with_fixed(
            starts,
            lower,
            upper,
            {target_index: float(value)},
            spectra,
            material,
            stride,
            max_nfev=140,
        )
        costs.append(float(2.0 * fit.cost))
        fitted_params.append(params)
        starts = params  # 暖启动，加速相邻网格点
    costs_array = np.asarray(costs)
    delta = costs_array - float(np.min(costs_array))
    accepted = delta <= 2.706  # 约 90% 轮廓阈值
    best_profile_params = fitted_params[int(np.argmin(costs_array))]
    if not np.any(accepted):
        return None, True, [], best_profile_params
    accepted_grid = grid[accepted]
    spacing = float(grid[1] - grid[0])
    interval = (
        float(
            max(
                lower[target_index],
                min(best_params[target_index], accepted_grid.min() - 0.5 * spacing),
            )
        ),
        float(
            min(
                upper[target_index],
                max(best_params[target_index], accepted_grid.max() + 0.5 * spacing),
            )
        ),
    )
    boundary = bool(accepted[0] or accepted[-1])
    target = "epi" if target_index == 1 else "substrate"
    rows = [
        {
            "material": material,
            "target": target,
            "log10_carrier_cm3": float(value),
            "carrier_cm3": float(10.0**value),
            "objective": float(cost),
            "delta_objective": float(change),
            "inside_ci90": bool(flag),
            "optimized_thickness_um": float(params[0]),
        }
        for value, cost, change, flag, params in zip(
            grid, costs_array, delta, accepted, fitted_params
        )
    ]
    return interval, boundary, rows, best_profile_params


def _carrier_correlation(jacobian: np.ndarray) -> float:
    covariance = np.linalg.pinv(jacobian.T @ jacobian)
    scale = np.sqrt(np.maximum(np.diag(covariance), 0.0))
    denominator = scale[1] * scale[2]
    if denominator <= 0:
        return 1.0
    return float(covariance[1, 2] / denominator)


def infer_carrier_concentrations(
    spectra: list[ProcessedSpectrum],
    initial_thicknesses_um: list[float],
    material: str = "SiC",
    profile_grid_points: int = 21,
    max_points_per_spectrum: int = 450,
) -> tuple[CarrierInferenceResult, list[dict]]:
    """从双角度全反射谱反演候选浓度并给出条件轮廓区间。"""
    if len(spectra) != 2 or len(initial_thicknesses_um) != 2:
        raise ValueError("增强载流子反演需要同一材料的两个角度")
    if profile_grid_points < 7:
        raise ValueError("轮廓网格至少需要 7 个点")
    qualification: ReflectanceQualification = qualify_reflectance(spectra)
    initial = float(np.median(initial_thicknesses_um))
    stride = max(
        1,
        max(
            int(np.ceil(len(spectrum.wavenumber_cm1) / max_points_per_spectrum))
            for spectrum in spectra
        ),
    )
    fit, params, lower, upper = _full_fit(spectra, initial, material, stride)
    _, _, _, epi_seed = _profile_parameter(
        1,
        params,
        lower,
        upper,
        spectra,
        material,
        stride,
        max(9, profile_grid_points // 2),
    )
    _, _, _, sub_seed = _profile_parameter(
        2,
        params,
        lower,
        upper,
        spectra,
        material,
        stride,
        max(9, profile_grid_points // 2),
    )
    refinements = [(fit, params)]
    for seed in (epi_seed, sub_seed):
        refined_fit, refined_params = _fit_with_fixed(
            seed,
            lower,
            upper,
            {},
            spectra,
            material,
            stride,
            max_nfev=320,
        )
        refinements.append((refined_fit, refined_params))
    fit, params = min(refinements, key=lambda item: float(2.0 * item[0].cost))

    epi_interval, epi_boundary, epi_rows, _ = _profile_parameter(
        1,
        params,
        lower,
        upper,
        spectra,
        material,
        stride,
        profile_grid_points,
    )
    sub_interval, sub_boundary, sub_rows, _ = _profile_parameter(
        2,
        params,
        lower,
        upper,
        spectra,
        material,
        stride,
        profile_grid_points,
    )

    fixed_costs = []
    for epi, substrate in CARRIER_SCENARIOS_CM3[material].values():
        scenario_fit, _ = _fit_with_fixed(
            params,
            lower,
            upper,
            {1: np.log10(epi), 2: np.log10(substrate)},
            spectra,
            material,
            stride,
        )
        fixed_costs.append(float(2.0 * scenario_fit.cost))
    objective = float(2.0 * fit.cost)
    best_fixed = min(fixed_costs)
    improvement = float((best_fixed - objective) / max(best_fixed, 1e-12) * 100.0)
    correlation = _carrier_correlation(fit.jac)
    epi_width = (
        float(epi_interval[1] - epi_interval[0])
        if epi_interval is not None
        else float("inf")
    )
    sub_width = (
        float(sub_interval[1] - sub_interval[0])
        if sub_interval is not None
        else float("inf")
    )
    thickness_boundary = bool(
        params[0] - lower[0] <= 0.002 * (upper[0] - lower[0])
        or upper[0] - params[0] <= 0.002 * (upper[0] - lower[0])
    )
    dual_identifiable = bool(
        not epi_boundary
        and not sub_boundary
        and not thickness_boundary
        and epi_width <= 0.6
        and sub_width <= 0.6
        and abs(correlation) < 0.85
        and improvement >= 10.0
    )
    epi_conditionally_identifiable = bool(
        not epi_boundary and not thickness_boundary and epi_width <= 1.0
    )
    sub_conditionally_identifiable = bool(
        not sub_boundary and not thickness_boundary and sub_width <= 1.0
    )

    if dual_identifiable:
        level = (
            "dual_concentration"
            if qualification.absolute_concentration_allowed
            else "conditional_dual"
        )
    elif epi_conditionally_identifiable:
        level = "conditional_epi"
    elif sub_conditionally_identifiable:
        level = "conditional_substrate"
    elif epi_interval is not None or sub_interval is not None:
        level = "bounded_scenario"
    else:
        level = "unidentifiable"

    report_points = bool(
        dual_identifiable and qualification.absolute_concentration_allowed
    )
    reasons = []
    if not qualification.absolute_concentration_allowed:
        reasons.append(qualification.reason)
    if epi_boundary or sub_boundary:
        reasons.append("轮廓区间触及浓度边界")
    if abs(correlation) >= 0.85:
        reasons.append("两层浓度灵敏度高度相关")
    if improvement < 10.0:
        reasons.append("相对固定情景改善不足 10%")
    if thickness_boundary:
        reasons.append("厚度触及稳健锚定区间边界")
    result = CarrierInferenceResult(
        material=material,
        measurement_mode=qualification.mode,
        qualification=qualification.to_dict(),
        identifiability_level=level,
        candidate_thickness_um=float(params[0]),
        candidate_epi_carrier_cm3=float(10.0 ** params[1]),
        candidate_substrate_carrier_cm3=float(10.0 ** params[2]),
        reported_epi_carrier_cm3=(
            float(10.0 ** params[1]) if report_points else None
        ),
        reported_substrate_carrier_cm3=(
            float(10.0 ** params[2]) if report_points else None
        ),
        epi_log10_ci90=epi_interval,
        substrate_log10_ci90=sub_interval,
        epi_ci90_cm3=(
            (float(10.0 ** epi_interval[0]), float(10.0 ** epi_interval[1]))
            if epi_interval is not None
            else None
        ),
        substrate_ci90_cm3=(
            (float(10.0 ** sub_interval[0]), float(10.0 ** sub_interval[1]))
            if sub_interval is not None
            else None
        ),
        epi_interval_boundary_hit=epi_boundary,
        substrate_interval_boundary_hit=sub_boundary,
        thickness_boundary_hit=thickness_boundary,
        carrier_correlation=correlation,
        fixed_scenario_improvement_pct=improvement,
        gains=(float(params[3]), float(params[4])),
        offsets_pct=(float(params[5]), float(params[6])),
        shared_slope_pct=float(params[7]),
        objective=objective,
        fallback_reason="；".join(reasons),
        informative_bands_cm1=((700.0, 1200.0), (1200.0, 4000.0)),
    )
    return result, epi_rows + sub_rows

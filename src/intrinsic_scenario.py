"""v7 方案 B：本征色散与固定掺杂情景的厚度敏感性分析。

本模块不反演载流子浓度。每个情景的浓度均固定，只在双角度共享条件下
优化厚度；结果只用于折射率系统误差，不覆盖主测厚轨的最终值。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
from scipy.optimize import minimize_scalar

from dispersion import CARRIER_SCENARIOS_CM3, METADATA, material_refractive_index
from preprocess import ProcessedSpectrum


@dataclass(frozen=True)
class FixedDispersionScenario:
    """单个固定光学情景的共享厚度拟合结果。"""

    name: str
    mode: str
    epi_carrier_cm3: float
    substrate_carrier_cm3: float
    thickness_um: float
    rmse_pct: float


@dataclass(frozen=True)
class IntrinsicScenarioResult:
    """方案 B 的材料级结果。"""

    material: str
    primary_thickness_um: float
    intrinsic_thickness_um: float
    intrinsic_median_um: float
    intrinsic_systematic_low_um: float
    intrinsic_systematic_high_um: float
    intrinsic_vs_constant_delta_pct: float
    scenarios: tuple[FixedDispersionScenario, ...]
    model: str
    references: tuple[str, ...]
    adopted_for_paper: str = "systematic_only"

    def to_dict(self) -> dict:
        return asdict(self)


def _transparent_mask(spectrum: ProcessedSpectrum, material: str) -> np.ndarray:
    """只用透明相位区估计厚度，避开 SiC 强吸收与二声子区。"""
    x = spectrum.wavenumber_cm1
    mask = (x >= 1200.0) & (x <= 4000.0)
    if material == "SiC":
        mask &= ~((x >= 1300.0) & (x <= 1600.0))
    if np.count_nonzero(mask) < 100:
        raise ValueError(f"{material} 透明相位区数据不足")
    return mask


def _phase_profile_residual(
    spectrum: ProcessedSpectrum,
    material: str,
    thickness_um: float,
    epi_carrier_cm3: float,
    mode: str,
) -> np.ndarray:
    """固定色散下用正余弦变量投影拟合条纹相位。

    本征模式下外延层与衬底的介电函数相同，完整 Fresnel 模型会失去界面
    条纹振幅；因此方案 B 只用外延层色散修正相位，条纹幅度和相位偏置由
    线性正余弦系数吸收。该路径用于厚度敏感性，而非绝对反射率反演。
    """
    mask = _transparent_mask(spectrum, material)
    x = spectrum.wavenumber_cm1[mask]
    y = spectrum.residual_pct[mask]
    index = material_refractive_index(
        material,
        x,
        epi_carrier_cm3,
        mode=mode,
    )
    n_real = np.real(index)
    sin0 = np.sin(np.deg2rad(spectrum.source.spec.angle_deg))
    optical = np.sqrt(np.maximum(n_real**2 - sin0**2, 1e-12))
    phase = 4.0 * np.pi * thickness_um * 1e-4 * x * optical
    z = (x - np.mean(x)) / max(float(np.ptp(x)), 1.0)
    design = np.column_stack(
        [
            np.ones_like(x),
            z,
            np.cos(phase),
            np.sin(phase),
            z * np.cos(phase),
            z * np.sin(phase),
        ]
    )
    coefficients, *_ = np.linalg.lstsq(design, y, rcond=None)
    return y - design @ coefficients


def _fit_fixed_scenario(
    spectra: list[ProcessedSpectrum],
    material: str,
    name: str,
    mode: str,
    epi_carrier_cm3: float,
    substrate_carrier_cm3: float,
    bounds: tuple[float, float],
) -> FixedDispersionScenario:
    def objective(thickness_um: float) -> float:
        return float(
            sum(
                np.sum(
                    _phase_profile_residual(
                        spectrum,
                        material,
                        thickness_um,
                        epi_carrier_cm3,
                        mode,
                    )
                    ** 2
                )
                for spectrum in spectra
            )
        )

    # 相位目标随厚度多峰：先做确定性粗网格定位，再在相邻网格内有界精修。
    grid = np.linspace(bounds[0], bounds[1], 181)
    values = np.asarray([objective(float(value)) for value in grid])
    best_index = int(np.argmin(values))
    local_bounds = (
        float(grid[max(0, best_index - 1)]),
        float(grid[min(len(grid) - 1, best_index + 1)]),
    )
    if local_bounds[0] == local_bounds[1]:
        local_bounds = bounds
    optimum = minimize_scalar(
        objective,
        bounds=local_bounds,
        method="bounded",
        options={"xatol": 1e-6, "maxiter": 300},
    )
    if not optimum.success or not np.isfinite(optimum.x):
        raise RuntimeError(f"{material}/{name} 固定情景厚度优化失败")
    residual = np.concatenate(
        [
            _phase_profile_residual(
                spectrum,
                material,
                float(optimum.x),
                epi_carrier_cm3,
                mode,
            )
            for spectrum in spectra
        ]
    )
    return FixedDispersionScenario(
        name=name,
        mode=mode,
        epi_carrier_cm3=float(epi_carrier_cm3),
        substrate_carrier_cm3=float(substrate_carrier_cm3),
        thickness_um=float(optimum.x),
        rmse_pct=float(np.sqrt(np.mean(residual**2))),
    )


def fit_intrinsic_scenarios(
    spectra: list[ProcessedSpectrum],
    initial_thicknesses_um: list[float],
    material: str,
    constant_reference_um: float | None = None,
) -> IntrinsicScenarioResult:
    """执行本征 + 低/中/高固定情景分析，浓度始终不参与优化。"""
    if len(spectra) < 2 or len(initial_thicknesses_um) != len(spectra):
        raise ValueError("方案 B 至少需要同一材料两个角度及对应厚度初值")
    if material not in METADATA:
        raise ValueError(f"不支持的材料：{material}")
    initial_array = np.asarray(initial_thicknesses_um, dtype=float)
    primary = float(
        np.median(initial_array)
        if constant_reference_um is None
        else constant_reference_um
    )
    if not np.isfinite(primary) or primary <= 0:
        raise ValueError("常折射率参考厚度必须为有限正数")
    search_center = float(np.median(initial_array))
    bounds = (max(0.2, 0.88 * search_center), 1.12 * search_center)

    scenarios = [
        _fit_fixed_scenario(
            spectra,
            material,
            "intrinsic",
            "intrinsic",
            0.0,
            0.0,
            bounds,
        )
    ]
    scenarios.extend(
        _fit_fixed_scenario(
            spectra,
            material,
            name,
            "fixed_carrier",
            epi,
            substrate,
            bounds,
        )
        for name, (epi, substrate) in CARRIER_SCENARIOS_CM3[material].items()
    )

    thicknesses = np.asarray([item.thickness_um for item in scenarios], dtype=float)
    envelope = np.r_[thicknesses, primary]
    intrinsic = scenarios[0].thickness_um
    metadata = METADATA[material]
    return IntrinsicScenarioResult(
        material=material,
        primary_thickness_um=primary,
        intrinsic_thickness_um=intrinsic,
        intrinsic_median_um=float(np.median(thicknesses)),
        intrinsic_systematic_low_um=float(np.min(envelope)),
        intrinsic_systematic_high_um=float(np.max(envelope)),
        intrinsic_vs_constant_delta_pct=float((intrinsic - primary) / primary * 100.0),
        scenarios=tuple(scenarios),
        model=f"phase-only intrinsic dispersion sensitivity; {metadata.model}",
        references=metadata.references,
    )


def intrinsic_refractive_index_rows(
    material: str,
    result: IntrinsicScenarioResult,
    wavenumber_cm1: np.ndarray,
) -> list[dict]:
    """导出本征与固定情景的外延层/衬底复折射率曲线。"""
    x = np.asarray(wavenumber_cm1, dtype=float)
    rows: list[dict] = []
    for scenario in result.scenarios:
        epi = material_refractive_index(
            material,
            x,
            scenario.epi_carrier_cm3,
            mode=scenario.mode,
        )
        substrate = material_refractive_index(
            material,
            x,
            scenario.substrate_carrier_cm3,
            mode=scenario.mode,
        )
        rows.extend(
            {
                "material": material,
                "scenario": scenario.name,
                "mode": scenario.mode,
                "wavenumber_cm1": float(nu),
                "wavelength_um": float(1e4 / nu),
                "n_epi": float(epi_value.real),
                "k_epi": float(epi_value.imag),
                "n_substrate": float(sub_value.real),
                "k_substrate": float(sub_value.imag),
            }
            for nu, epi_value, sub_value in zip(x, epi, substrate)
        )
    return rows

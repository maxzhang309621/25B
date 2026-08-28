"""v7 三轨折射率结果的显式决策汇总。"""

from __future__ import annotations

import numpy as np
import pandas as pd

from intrinsic_scenario import IntrinsicScenarioResult


def build_refractive_index_comparison(
    summary: pd.DataFrame,
    intrinsic_results: dict[str, IntrinsicScenarioResult],
    audit: dict,
) -> dict:
    """合并主结论轨、方案 B 系统误差轨和自由浓度审计轨。"""
    required = {
        "material",
        "selected_model",
        "selected_thickness_um",
        "bootstrap_std_um",
    }
    if summary.empty or not required.issubset(summary.columns):
        raise ValueError("三轨汇总缺少主结果必要列")

    materials = {}
    for material, intrinsic in intrinsic_results.items():
        subset = summary[summary["material"] == material].sort_values("angle_deg")
        if subset.empty:
            raise ValueError(f"主结果缺少材料 {material}")
        values = subset["selected_thickness_um"].to_numpy(float)
        std = np.maximum(subset["bootstrap_std_um"].to_numpy(float), 1e-4)
        primary_combined = float(np.average(values, weights=1.0 / std**2))
        materials[material] = {
            "track0_primary": {
                "selected_models": subset["selected_model"].tolist(),
                "per_angle_thickness_um": values.tolist(),
                "combined_thickness_um": primary_combined,
                "adopted_for_paper": True,
            },
            "track1_intrinsic_systematic": {
                "intrinsic_thickness_um": intrinsic.intrinsic_thickness_um,
                "scenario_median_um": intrinsic.intrinsic_median_um,
                "systematic_interval_um": [
                    intrinsic.intrinsic_systematic_low_um,
                    intrinsic.intrinsic_systematic_high_um,
                ],
                "intrinsic_vs_constant_delta_pct": (
                    intrinsic.intrinsic_vs_constant_delta_pct
                ),
                "adopted_for_paper": "systematic_only",
            },
            "track2_carrier_audit": audit["materials"].get(material, {}),
            "decision": {
                "primary_track": "track0_primary",
                "dispersion_track_adopted_for_paper": (
                    "track1_intrinsic_systematic_only"
                ),
                "carrier_track_role": "evidence_only",
                "reason": (
                    "主厚度由稳健条纹与多光束门控确定；本征色散仅传播折射率"
                    "系统误差；自由浓度轨仅用于验证可辨识性。"
                ),
            },
        }
    return {
        "version": "v7",
        "policy": "explicit_tracks_no_rmse_auto_override",
        "materials": materials,
    }


def build_dispersion_extrema_comparison(
    summary: pd.DataFrame,
    v8_results: dict,
) -> dict:
    """汇总 v8 与 L0 主结果，并记录采用或回退原因。"""
    materials = {}
    for material, result in v8_results.items():
        subset = summary[summary["material"] == material].sort_values("angle_deg")
        std = np.maximum(subset["bootstrap_std_um"].to_numpy(float), 1e-4)
        primary = float(
            np.average(
                subset["selected_thickness_um"].to_numpy(float),
                weights=1.0 / std**2,
            )
        )
        materials[material] = {
            "l0_constant_index_thickness_um": primary,
            "v8_nominal_thickness_um": result["nominal_thickness_um"],
            "v8_statistical_ci95_um": [
                result["statistical_ci95_low_um"],
                result["statistical_ci95_high_um"],
            ],
            "v8_systematic_interval_um": [
                result["systematic_low_um"],
                result["systematic_high_um"],
            ],
            "peak_valley_diff_pct": result["peak_valley_diff_pct"],
            "angle_diff_pct": result["angle_diff_pct"],
            "band_cv_pct": result["band_cv_pct"],
            "multi_beam_consistency_pct": result["multi_beam_consistency_pct"],
            "v8_adopted": result["adopted"],
            "final_thickness_um": result["final_thickness_um"],
            "fallback_reason": result["fallback_reason"],
        }
    return {
        "version": "v8",
        "nominal_policy": (
            "adopt intrinsic-dispersion extrema fit only after stability and "
            "multi-beam consistency gates"
        ),
        "materials": materials,
    }

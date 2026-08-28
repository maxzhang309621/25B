"""聚合遗留自由载流子反演的不可辨识证据。

本模块不重新拟合，只把 joint_calibration 与 carrier_inference 已计算的
指标转成可审计的“数值—阈值—结论”结构，避免报告口径漂移。
"""

from __future__ import annotations

from typing import Any

from carrier_inference import CarrierInferenceResult
from joint_calibration import JointCalibrationResult


def _check(value: Any, threshold: Any, comparator: str, passed: bool) -> dict:
    return {
        "value": value,
        "threshold": threshold,
        "comparator": comparator,
        "passed": bool(passed),
    }


def _joint_evidence(result: JointCalibrationResult) -> dict:
    best_scenario_rmse = min(item.rmse_pct for item in result.scenarios)
    free_improvement = (
        (best_scenario_rmse - result.rmse_pct) / max(best_scenario_rmse, 1e-12) * 100.0
    )
    checks = {
        "jacobian_condition": _check(
            result.jacobian_condition,
            1e8,
            "<",
            result.jacobian_condition < 1e8,
        ),
        "max_parameter_correlation": _check(
            result.max_parameter_correlation,
            0.95,
            "<",
            result.max_parameter_correlation < 0.95,
        ),
        "parameter_boundary": _check(
            result.boundary_hit,
            False,
            "==",
            not result.boundary_hit,
        ),
        "band_cv_pct": _check(
            result.band_cv_pct,
            1.0,
            "<=",
            result.band_cv_pct <= 1.0,
        ),
        "max_band_shift_pct": _check(
            result.max_band_shift_pct,
            2.0,
            "<=",
            result.max_band_shift_pct <= 2.0,
        ),
        "free_fit_vs_best_fixed_pct": _check(
            free_improvement,
            -2.0,
            ">=",
            free_improvement >= -2.0,
        ),
    }
    reason_map = {
        "jacobian_condition": "Jacobian 条件数超过阈值",
        "max_parameter_correlation": "厚度与载流子参数强相关",
        "parameter_boundary": "自由参数触及先验边界",
        "band_cv_pct": "连续波段厚度变异系数过大",
        "max_band_shift_pct": "连续波段厚度最大偏移过大",
        "free_fit_vs_best_fixed_pct": "自由浓度拟合劣于固定掺杂情景",
    }
    reasons = [reason_map[name] for name, item in checks.items() if not item["passed"]]
    return {
        "candidate": {
            "thickness_um": result.fitted_thickness_um,
            "epi_carrier_cm3": result.epi_carrier_cm3,
            "substrate_carrier_cm3": result.substrate_carrier_cm3,
            "rmse_pct": result.rmse_pct,
        },
        "best_fixed_scenario_rmse_pct": best_scenario_rmse,
        "checks": checks,
        "concentration_identifiable": bool(result.concentration_identifiable),
        "failure_reasons": reasons,
        "fallback_reason": result.fallback_reason,
        "recommended_interpretation": (
            "identified_point_estimate"
            if result.concentration_identifiable
            else "scenario_envelope_only"
        ),
    }


def _enhanced_evidence(result: CarrierInferenceResult) -> dict:
    checks = {
        "absolute_reflectance_qualified": _check(
            result.qualification["absolute_concentration_allowed"],
            True,
            "==",
            bool(result.qualification["absolute_concentration_allowed"]),
        ),
        "epi_profile_boundary": _check(
            result.epi_interval_boundary_hit,
            False,
            "==",
            not result.epi_interval_boundary_hit,
        ),
        "substrate_profile_boundary": _check(
            result.substrate_interval_boundary_hit,
            False,
            "==",
            not result.substrate_interval_boundary_hit,
        ),
        "thickness_anchor_boundary": _check(
            result.thickness_boundary_hit,
            False,
            "==",
            not result.thickness_boundary_hit,
        ),
        "carrier_correlation": _check(
            abs(result.carrier_correlation),
            0.85,
            "<",
            abs(result.carrier_correlation) < 0.85,
        ),
        "fixed_scenario_improvement_pct": _check(
            result.fixed_scenario_improvement_pct,
            10.0,
            ">=",
            result.fixed_scenario_improvement_pct >= 10.0,
        ),
    }
    reason_map = {
        "absolute_reflectance_qualified": "绝对反射率资格未通过",
        "epi_profile_boundary": "外延层浓度轮廓区间触边",
        "substrate_profile_boundary": "衬底浓度轮廓区间触边",
        "thickness_anchor_boundary": "厚度触及稳健锚定边界",
        "carrier_correlation": "两层浓度灵敏度高度相关",
        "fixed_scenario_improvement_pct": "相对固定情景改善不足",
    }
    reasons = [reason_map[name] for name, item in checks.items() if not item["passed"]]
    return {
        "measurement_mode": result.measurement_mode,
        "identifiability_level": result.identifiability_level,
        "candidate": {
            "thickness_um": result.candidate_thickness_um,
            "epi_carrier_cm3": result.candidate_epi_carrier_cm3,
            "substrate_carrier_cm3": result.candidate_substrate_carrier_cm3,
        },
        "profile_intervals_cm3": {
            "epi": result.epi_ci90_cm3,
            "substrate": result.substrate_ci90_cm3,
        },
        "checks": checks,
        "point_estimate_reported": bool(
            result.reported_epi_carrier_cm3 is not None
            and result.reported_substrate_carrier_cm3 is not None
        ),
        "failure_reasons": reasons,
        "fallback_reason": result.fallback_reason,
        "recommended_interpretation": "scenario_envelope_only",
    }


def build_identifiability_audit(
    joint_results: dict[str, JointCalibrationResult],
    carrier_result: CarrierInferenceResult | None = None,
) -> dict:
    """构建全材料不可辨识证据包。"""
    if not joint_results:
        raise ValueError("不可辨识审计至少需要一个联合校准结果")
    materials = {
        material: {"joint_calibration": _joint_evidence(result)}
        for material, result in joint_results.items()
    }
    if carrier_result is not None:
        materials.setdefault(carrier_result.material, {})[
            "enhanced_carrier_inference"
        ] = _enhanced_evidence(carrier_result)
    return {
        "purpose": "evidence_only_not_primary_estimate",
        "threshold_policy": {
            "joint": {
                "jacobian_condition_max": 1e8,
                "parameter_correlation_max": 0.95,
                "band_cv_pct_max": 1.0,
                "max_band_shift_pct_max": 2.0,
            },
            "enhanced": {
                "carrier_correlation_max": 0.85,
                "fixed_scenario_improvement_pct_min": 10.0,
                "profile_interval_must_not_hit_boundary": True,
            },
        },
        "materials": materials,
    }

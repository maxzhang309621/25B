"""2025 B 题端到端求解入口。

主流程：读附件 → 选波段/预处理 → 双光束 → 多光束诊断 →
材料级色散联合校准 → SiC 增强浓度反演 → 导出表图与原始证据图。
"""

import argparse
import importlib.util
import json
import sys
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

from carrier_inference import infer_carrier_concentrations
from comparison_report import (
    build_dispersion_extrema_comparison,
    build_refractive_index_comparison,
)
from config import BOOTSTRAP_BLOCK_CM1, DATASETS, DATA_DIR, OUTPUT_DIR
from data_io import load_spectrum
from diagnostics import diagnose_multibeam
from dispersion import METADATA
from dispersion_extrema import fit_dispersion_extrema_scenarios
from evidence_plotting import plot_analysis_evidence
from identifiability_audit import build_identifiability_audit
from intrinsic_scenario import (
    fit_intrinsic_scenarios,
    intrinsic_refractive_index_rows,
)
from joint_calibration import fit_joint_calibration, refractive_index_rows
from model_flowchart import plot_model_flowchart
from multi_beam import fit_multi_beam
from plotting import plot_spectrum_fit, plot_summary_figures
from preprocess import preprocess
from raw_evidence_plotting import (
    plot_raw_dispersion_evidence,
    plot_raw_extrema_evidence,
    plot_raw_multibeam_evidence,
    plot_raw_v7_evidence,
)
from shared_thickness import V8_THRESHOLDS
from two_beam import estimate_two_beam
from uncertainty import bootstrap_two_beam, relative_angle_difference

# Candidate window 目录含空格，用动态导入避免包路径问题。
_BAND_SELECT_PATH = Path(__file__).resolve().parent / "Candidate window" / "band_select.py"
_band_spec = importlib.util.spec_from_file_location("band_select", _BAND_SELECT_PATH)
_band_select = importlib.util.module_from_spec(_band_spec)
sys.modules["band_select"] = _band_select
assert _band_spec.loader is not None
_band_spec.loader.exec_module(_band_select)
select_band = _band_select.select_band
build_sensitivity_rows = _band_select.build_sensitivity_rows


def _plain_dict(obj) -> dict:
    """dataclass → JSON 友好 dict，跳过 ndarray 大数组。"""
    result = {}
    for key, value in asdict(obj).items():
        if isinstance(value, np.ndarray):
            continue
        if isinstance(value, (np.floating, np.integer)):
            value = value.item()
        result[key] = value
    return result


def run_pipeline(bootstrap_repeats: int = 30, global_search: bool = True) -> pd.DataFrame:
    """完整求解四附件并写 output/；返回 thickness_summary 表。"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    audits = {}
    details = {}
    sensitivity_rows = []
    material_inputs = {"SiC": [], "Si": []}
    extrema_inputs = {"SiC": [], "Si": []}
    multibeam_plot_inputs = []  # 供独立谐波频谱原始图复用

    for index, spec in enumerate(DATASETS):
        spectrum = load_spectrum(DATA_DIR, spec)
        selected_band, band_scores = select_band(spectrum)
        sensitivity_rows.extend(build_sensitivity_rows(spec.key, spec.material, band_scores))
        processed = preprocess(spectrum, fit_band_cm1=selected_band)
        two = estimate_two_beam(processed)
        multi = fit_multi_beam(processed, two, global_search=global_search)
        diagnostic = diagnose_multibeam(processed, two, multi)
        uncertainty = bootstrap_two_beam(
            processed,
            two,
            repeats=bootstrap_repeats,
            block_cm1=BOOTSTRAP_BLOCK_CM1,
            seed=2025 + index,
        )
        # 四项证据全部通过才采用多光束厚度，否则回退双光束。
        selected = multi.thickness_um if diagnostic.observable_multibeam else two.thickness_refined_um
        selected_model = "multi-beam" if diagnostic.observable_multibeam else "two-beam"
        # 色散校准使用材料有效波段（可比条纹选带更宽）。
        calibration_spectrum = preprocess(
            spectrum, fit_band_cm1=METADATA[spec.material].valid_wavenumber_cm1
        )
        material_inputs[spec.material].append(
            (spec.key, calibration_spectrum, selected)
        )
        extrema_inputs[spec.material].append((processed, two))
        multibeam_plot_inputs.append((spec.key, processed, two))

        rows.append(
            {
                "dataset": spec.key,
                "material": spec.material,
                "angle_deg": spec.angle_deg,
                "refractive_index": spec.refractive_index,
                "fft_thickness_um": two.thickness_fft_um,
                "peak_thickness_um": two.thickness_peaks_um,
                "valley_thickness_um": two.thickness_valleys_um,
                "two_beam_thickness_um": two.thickness_refined_um,
                "two_beam_rmse_pct": two.rmse_pct,
                "multi_beam_thickness_um": multi.thickness_um,
                "multi_beam_rmse_pct": multi.rmse_pct,
                "effective_reflectivity": multi.effective_reflectivity,
                "harmonic_ratio": diagnostic.harmonic_ratio,
                "delta_aicc": diagnostic.delta_aicc,
                "rmse_improvement_pct": diagnostic.rmse_improvement_pct,
                "observable_multibeam": diagnostic.observable_multibeam,
                "selected_model": selected_model,
                "selected_thickness_um": selected,
                "bootstrap_std_um": uncertainty.std_um,
                "bootstrap_ci95_low_um": uncertainty.ci95_low_um,
                "bootstrap_ci95_high_um": uncertainty.ci95_high_um,
                "effective_extrema_count": len(two.peak_indices) + len(two.valley_indices),
                "fit_band_lo_cm1": selected_band[0],
                "fit_band_hi_cm1": selected_band[1],
            }
        )
        audits[spec.key] = spectrum.audit
        details[spec.key] = {
            "selected_band_cm1": list(selected_band),
            "band_scores": [asdict(score) for score in band_scores],
            "two_beam": _plain_dict(two),
            "multi_beam": _plain_dict(multi),
            "diagnostic": _plain_dict(diagnostic),
            "uncertainty": _plain_dict(uncertainty),
        }
        plot_spectrum_fit(
            processed,
            two,
            multi,
            diagnostic,
            uncertainty,
            OUTPUT_DIR,
            spec.key,
        )

    summary = pd.DataFrame(rows)
    # —— v8：透明波段 + 色散坐标多峰谷共享厚度反演 ——
    v8_results = {}
    v8_payload = {}
    v8_observation_rows = []
    v8_coordinate_rows = []
    v8_residual_rows = []
    for material, items in extrema_inputs.items():
        primary_subset = summary[summary["material"] == material]
        primary_values = primary_subset["selected_thickness_um"].to_numpy(float)
        primary_std = np.maximum(
            primary_subset["bootstrap_std_um"].to_numpy(float),
            1e-4,
        )
        primary_combined = float(
            np.average(primary_values, weights=1.0 / primary_std**2)
        )
        result = fit_dispersion_extrema_scenarios(
            [item[0] for item in items],
            [item[1] for item in items],
            material,
            primary_combined,
            bootstrap_repeats=max(20, min(80, 2 * bootstrap_repeats)),
        )
        v8_results[material] = result
        material_mask = summary["material"] == material
        selected_models = summary.loc[material_mask, "selected_model"].tolist()
        multi_consistency = (
            abs(result.nominal_thickness_um - primary_combined)
            / primary_combined
            * 100.0
        )
        multi_required = any(model == "multi-beam" for model in selected_models)
        adopted = bool(
            result.stable
            and (
                not multi_required
                or multi_consistency
                <= V8_THRESHOLDS["multi_beam_consistency_pct"]
            )
        )
        reasons = [result.fallback_reason] if result.fallback_reason else []
        if multi_required and multi_consistency > 2.0:
            reasons.append("与 Airy 主厚度相对差超过 2%")
        fallback_reason = "；".join(reasons)
        payload = result.to_dict(include_points=False)
        payload["adopted"] = adopted
        payload["fallback_reason"] = fallback_reason
        payload["multi_beam_consistency_pct"] = multi_consistency
        payload["final_thickness_um"] = (
            result.nominal_thickness_um if adopted else primary_combined
        )
        v8_payload[material] = payload

        summary.loc[material_mask, "v8_nominal_thickness_um"] = (
            result.nominal_thickness_um
        )
        summary.loc[material_mask, "v8_stat_ci95_low_um"] = (
            result.statistical_ci95_low_um
        )
        summary.loc[material_mask, "v8_stat_ci95_high_um"] = (
            result.statistical_ci95_high_um
        )
        summary.loc[material_mask, "v8_systematic_low_um"] = (
            result.systematic_low_um
        )
        summary.loc[material_mask, "v8_systematic_high_um"] = (
            result.systematic_high_um
        )
        summary.loc[material_mask, "v8_peak_valley_diff_pct"] = (
            result.peak_valley_diff_pct
        )
        summary.loc[material_mask, "v8_angle_diff_pct"] = result.angle_diff_pct
        summary.loc[material_mask, "v8_band_cv_pct"] = result.band_cv_pct
        summary.loc[material_mask, "v8_stable"] = result.stable
        summary.loc[material_mask, "v8_adopted"] = adopted
        summary.loc[material_mask, "v8_final_thickness_um"] = (
            result.nominal_thickness_um if adopted else primary_combined
        )
        summary.loc[material_mask, "v8_fallback_reason"] = fallback_reason

        v8_observation_rows.extend(
            observation.to_dict() for observation in result.observations
        )
        for scenario_result in result.scenario_results:
            for point in scenario_result.points:
                row = point.to_dict()
                v8_coordinate_rows.append(row)
                if point.eligible:
                    v8_residual_rows.append(row)

    # —— v7 轨 1：本征色散 + 固定浓度情景，只传播厚度系统误差 ——
    intrinsic_results = {}
    intrinsic_rows = []
    for material, items in material_inputs.items():
        primary_subset = summary[summary["material"] == material]
        primary_values = primary_subset["selected_thickness_um"].to_numpy(float)
        primary_std = np.maximum(
            primary_subset["bootstrap_std_um"].to_numpy(float),
            1e-4,
        )
        primary_combined = float(
            np.average(primary_values, weights=1.0 / primary_std**2)
        )
        intrinsic = fit_intrinsic_scenarios(
            [item[1] for item in items],
            [item[2] for item in items],
            material,
            constant_reference_um=primary_combined,
        )
        intrinsic_results[material] = intrinsic
        for key, _, _ in items:
            details[key]["intrinsic_dispersion_scenarios"] = intrinsic.to_dict()
        material_mask = summary["material"] == material
        summary.loc[material_mask, "intrinsic_thickness_um"] = (
            intrinsic.intrinsic_thickness_um
        )
        summary.loc[material_mask, "intrinsic_median_um"] = (
            intrinsic.intrinsic_median_um
        )
        summary.loc[material_mask, "intrinsic_systematic_low_um"] = (
            intrinsic.intrinsic_systematic_low_um
        )
        summary.loc[material_mask, "intrinsic_systematic_high_um"] = (
            intrinsic.intrinsic_systematic_high_um
        )
        summary.loc[material_mask, "intrinsic_vs_constant_delta_pct"] = (
            intrinsic.intrinsic_vs_constant_delta_pct
        )
        summary.loc[material_mask, "primary_track"] = "track0_primary"
        summary.loc[material_mask, "dispersion_track_adopted_for_paper"] = (
            "track1_intrinsic_systematic_only"
        )
        lo, hi = METADATA[material].valid_wavenumber_cm1
        intrinsic_rows.extend(
            intrinsic_refractive_index_rows(
                material,
                intrinsic,
                np.linspace(lo, hi, 300),
            )
        )

    # —— v7 轨 2：保留 v3–v6 自由载流子联合校准，作为可辨识性审计 ——
    joint_results = {}
    refractive_rows = []
    for material, items in material_inputs.items():
        joint = fit_joint_calibration(
            [item[1] for item in items],
            [item[2] for item in items],
            material,
        )
        material_mask = summary["material"] == material
        conditional_std = summary.loc[
            material_mask, "bootstrap_std_um"
        ].to_numpy(float)
        joint.statistical_std_um = float(
            1.0 / np.sqrt(np.sum(1.0 / np.maximum(conditional_std, 1e-4) ** 2))
        )
        joint.statistical_ci95_low_um = float(
            joint.adopted_thickness_um - 1.96 * joint.statistical_std_um
        )
        joint.statistical_ci95_high_um = float(
            joint.adopted_thickness_um + 1.96 * joint.statistical_std_um
        )
        joint_results[material] = joint
        summary.loc[material_mask, "dispersion_fitted_thickness_um"] = (
            joint.fitted_thickness_um
        )
        summary.loc[material_mask, "dispersion_adopted_thickness_um"] = (
            joint.adopted_thickness_um
        )
        summary.loc[material_mask, "dispersion_systematic_low_um"] = (
            joint.systematic_low_um
        )
        summary.loc[material_mask, "dispersion_systematic_high_um"] = (
            joint.systematic_high_um
        )
        summary.loc[material_mask, "dispersion_stat_ci95_low_um"] = (
            joint.statistical_ci95_low_um
        )
        summary.loc[material_mask, "dispersion_stat_ci95_high_um"] = (
            joint.statistical_ci95_high_um
        )
        summary.loc[material_mask, "candidate_epi_carrier_cm3"] = (
            joint.epi_carrier_cm3
        )
        summary.loc[material_mask, "candidate_substrate_carrier_cm3"] = (
            joint.substrate_carrier_cm3
        )
        summary.loc[material_mask, "dispersion_candidate_identifiable"] = (
            joint.concentration_identifiable
        )
        for key, _, _ in items:
            details[key]["dispersion_joint_calibration"] = joint.to_dict()
        lo, hi = METADATA[material].valid_wavenumber_cm1
        refractive_rows.extend(
            refractive_index_rows(material, joint, np.linspace(lo, hi, 300))
        )

    # —— SiC 增强浓度反演：门控未通过时主表浓度保持 NaN ——
    sic_items = material_inputs["SiC"]
    carrier_result, carrier_profile_rows = infer_carrier_concentrations(
        [item[1] for item in sic_items],
        [item[2] for item in sic_items],
        material="SiC",
    )
    carrier_payload = carrier_result.to_dict()
    sic_mask = summary["material"] == "SiC"
    summary["epi_carrier_cm3"] = np.nan
    summary["substrate_carrier_cm3"] = np.nan
    summary["carrier_identifiability_level"] = "not_run_v5"
    summary["carrier_measurement_mode"] = "not_run_v5"
    summary.loc[sic_mask, "carrier_identifiability_level"] = (
        carrier_result.identifiability_level
    )
    summary.loc[sic_mask, "carrier_measurement_mode"] = (
        carrier_result.measurement_mode
    )
    if carrier_result.reported_epi_carrier_cm3 is not None:
        summary.loc[sic_mask, "epi_carrier_cm3"] = (
            carrier_result.reported_epi_carrier_cm3
        )
    if carrier_result.reported_substrate_carrier_cm3 is not None:
        summary.loc[sic_mask, "substrate_carrier_cm3"] = (
            carrier_result.reported_substrate_carrier_cm3
        )
    for key, _, _ in sic_items:
        details[key]["enhanced_carrier_inference"] = carrier_payload

    identifiability_audit = build_identifiability_audit(
        joint_results,
        carrier_result,
    )
    for material in ("SiC", "Si"):
        material_mask = summary["material"] == material
        summary.loc[material_mask, "audit_identifiable"] = bool(
            joint_results[material].concentration_identifiable
        )
        summary.loc[material_mask, "audit_failure_reasons"] = (
            joint_results[material].fallback_reason
        )
        summary.loc[material_mask, "audit_free_fit_thickness_um"] = (
            joint_results[material].fitted_thickness_um
        )

    comparison_payload = build_refractive_index_comparison(
        summary,
        intrinsic_results,
        identifiability_audit,
    )
    v8_comparison_payload = build_dispersion_extrema_comparison(
        summary,
        v8_payload,
    )

    summary.to_csv(OUTPUT_DIR / "thickness_summary.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(sensitivity_rows).to_csv(
        OUTPUT_DIR / "band_sensitivity.csv",
        index=False,
        encoding="utf-8-sig",
    )
    with (OUTPUT_DIR / "data_audit.json").open("w", encoding="utf-8") as handle:
        json.dump(audits, handle, ensure_ascii=False, indent=2)
    with (OUTPUT_DIR / "fit_details.json").open("w", encoding="utf-8") as handle:
        json.dump(details, handle, ensure_ascii=False, indent=2)
    dispersion_payload = {
        material: result.to_dict() for material, result in joint_results.items()
    }
    refractive_frame = pd.DataFrame(refractive_rows)
    with (OUTPUT_DIR / "dispersion_fit.json").open("w", encoding="utf-8") as handle:
        json.dump(
            dispersion_payload,
            handle,
            ensure_ascii=False,
            indent=2,
        )
    refractive_frame.to_csv(
        OUTPUT_DIR / "refractive_index_curves.csv",
        index=False,
        encoding="utf-8-sig",
    )
    with (OUTPUT_DIR / "carrier_inference.json").open("w", encoding="utf-8") as handle:
        json.dump(carrier_payload, handle, ensure_ascii=False, indent=2)
    carrier_profile_frame = pd.DataFrame(carrier_profile_rows)
    carrier_profile_frame.to_csv(
        OUTPUT_DIR / "carrier_profile.csv",
        index=False,
        encoding="utf-8-sig",
    )
    intrinsic_payload = {
        material: result.to_dict() for material, result in intrinsic_results.items()
    }
    intrinsic_frame = pd.DataFrame(intrinsic_rows)
    with (OUTPUT_DIR / "intrinsic_dispersion_fit.json").open(
        "w", encoding="utf-8"
    ) as handle:
        json.dump(intrinsic_payload, handle, ensure_ascii=False, indent=2)
    intrinsic_frame.to_csv(
        OUTPUT_DIR / "intrinsic_n_curves.csv",
        index=False,
        encoding="utf-8-sig",
    )
    with (OUTPUT_DIR / "audit_identifiability.json").open(
        "w", encoding="utf-8"
    ) as handle:
        json.dump(identifiability_audit, handle, ensure_ascii=False, indent=2)
    with (OUTPUT_DIR / "refractive_index_comparison.json").open(
        "w", encoding="utf-8"
    ) as handle:
        json.dump(comparison_payload, handle, ensure_ascii=False, indent=2)
    with (OUTPUT_DIR / "dispersion_extrema_fit.json").open(
        "w", encoding="utf-8"
    ) as handle:
        json.dump(v8_payload, handle, ensure_ascii=False, indent=2)
    pd.DataFrame(v8_observation_rows).to_csv(
        OUTPUT_DIR / "extrema_observations.csv",
        index=False,
        encoding="utf-8-sig",
    )
    pd.DataFrame(v8_coordinate_rows).to_csv(
        OUTPUT_DIR / "dispersion_extrema_coordinates.csv",
        index=False,
        encoding="utf-8-sig",
    )
    pd.DataFrame(v8_residual_rows).to_csv(
        OUTPUT_DIR / "dispersion_extrema_residuals.csv",
        index=False,
        encoding="utf-8-sig",
    )
    with (OUTPUT_DIR / "dispersion_extrema_comparison.json").open(
        "w", encoding="utf-8"
    ) as handle:
        json.dump(v8_comparison_payload, handle, ensure_ascii=False, indent=2)

    consistency = {}
    for material in ("SiC", "Si"):
        subset = summary[summary["material"] == material].sort_values("angle_deg")
        values = subset["selected_thickness_um"].to_numpy(float)
        relative = relative_angle_difference(values[0], values[1])
        weights = 1.0 / np.maximum(subset["bootstrap_std_um"].to_numpy(float), 1e-4) ** 2
        combined = float(np.average(values, weights=weights))
        consistency[material] = {
            "angle_relative_difference_pct": relative,
            "weighted_combined_thickness_um": combined,
            "selected_models": subset["selected_model"].tolist(),
            "dispersion_adopted_thickness_um": joint_results[
                material
            ].adopted_thickness_um,
            "dispersion_systematic_interval_um": [
                joint_results[material].systematic_low_um,
                joint_results[material].systematic_high_um,
            ],
            "dispersion_candidate_identifiable": joint_results[
                material
            ].concentration_identifiable,
            "intrinsic_thickness_um": intrinsic_results[
                material
            ].intrinsic_thickness_um,
            "intrinsic_systematic_interval_um": [
                intrinsic_results[material].intrinsic_systematic_low_um,
                intrinsic_results[material].intrinsic_systematic_high_um,
            ],
            "carrier_audit_role": "evidence_only",
            "v8_nominal_thickness_um": v8_payload[material][
                "nominal_thickness_um"
            ],
            "v8_systematic_interval_um": [
                v8_payload[material]["systematic_low_um"],
                v8_payload[material]["systematic_high_um"],
            ],
            "v8_adopted": v8_payload[material]["adopted"],
            "v8_final_thickness_um": v8_payload[material][
                "final_thickness_um"
            ],
            "v8_fallback_reason": v8_payload[material]["fallback_reason"],
        }
    consistency["SiC"]["enhanced_carrier_inference"] = {
        "measurement_mode": carrier_result.measurement_mode,
        "identifiability_level": carrier_result.identifiability_level,
        "reported_epi_carrier_cm3": carrier_result.reported_epi_carrier_cm3,
        "reported_substrate_carrier_cm3": (
            carrier_result.reported_substrate_carrier_cm3
        ),
        "epi_ci90_cm3": carrier_result.epi_ci90_cm3,
        "substrate_ci90_cm3": carrier_result.substrate_ci90_cm3,
    }
    with (OUTPUT_DIR / "consistency.json").open("w", encoding="utf-8") as handle:
        json.dump(consistency, handle, ensure_ascii=False, indent=2)
    plot_summary_figures(
        summary,
        consistency,
        OUTPUT_DIR,
        dispersion_results=dispersion_payload,
        refractive_curves=refractive_frame,
        carrier_result=carrier_payload,
        carrier_profile=carrier_profile_frame,
    )
    # 独立原始证据图：仅标题/坐标/图例，不含判定与结论文字。
    plot_raw_multibeam_evidence(
        summary,
        multibeam_plot_inputs,
        OUTPUT_DIR / "raw_evidence" / "multibeam",
    )
    plot_raw_dispersion_evidence(
        refractive_frame,
        dispersion_payload,
        carrier_profile_frame,
        OUTPUT_DIR / "raw_evidence" / "dispersion",
    )
    plot_raw_v7_evidence(
        intrinsic_frame,
        intrinsic_payload,
        identifiability_audit,
        OUTPUT_DIR / "raw_evidence" / "dispersion",
        OUTPUT_DIR / "raw_evidence" / "audit",
    )
    plot_raw_extrema_evidence(
        v8_results,
        OUTPUT_DIR / "raw_evidence" / "extrema",
    )
    plot_analysis_evidence(
        summary,
        extrema_inputs,
        v8_results,
        v8_comparison_payload,
        identifiability_audit,
        OUTPUT_DIR / "analysis_evidence",
    )
    plot_model_flowchart(OUTPUT_DIR / "model_flowchart.png")

    print(summary.to_string(index=False, float_format=lambda value: f"{value:.6g}"))
    print("\n双角度一致性：")
    print(json.dumps(consistency, ensure_ascii=False, indent=2))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="2025 B 题外延层厚度求解")
    parser.add_argument("--bootstrap", type=int, default=30, help="区块重采样次数")
    parser.add_argument(
        "--fast",
        action="store_true",
        help="跳过差分进化全局搜索，仅用于快速冒烟测试",
    )
    args = parser.parse_args()
    run_pipeline(bootstrap_repeats=args.bootstrap, global_search=not args.fast)


if __name__ == "__main__":
    main()

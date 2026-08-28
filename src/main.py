"""2025 B 题端到端求解入口。"""

import argparse
import importlib.util
import json
import sys
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

from config import BOOTSTRAP_BLOCK_CM1, DATASETS, DATA_DIR, OUTPUT_DIR
from data_io import load_spectrum
from diagnostics import diagnose_multibeam
from multi_beam import fit_multi_beam
from plotting import plot_spectrum_fit, plot_summary_figures
from preprocess import preprocess
from two_beam import estimate_two_beam
from uncertainty import bootstrap_two_beam, relative_angle_difference

_BAND_SELECT_PATH = Path(__file__).resolve().parent / "Candidate window" / "band_select.py"
_band_spec = importlib.util.spec_from_file_location("band_select", _BAND_SELECT_PATH)
_band_select = importlib.util.module_from_spec(_band_spec)
sys.modules["band_select"] = _band_select
assert _band_spec.loader is not None
_band_spec.loader.exec_module(_band_select)
select_band = _band_select.select_band
build_sensitivity_rows = _band_select.build_sensitivity_rows


def _plain_dict(obj) -> dict:
    result = {}
    for key, value in asdict(obj).items():
        if isinstance(value, np.ndarray):
            continue
        if isinstance(value, (np.floating, np.integer)):
            value = value.item()
        result[key] = value
    return result


def run_pipeline(bootstrap_repeats: int = 30, global_search: bool = True) -> pd.DataFrame:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    audits = {}
    details = {}
    sensitivity_rows = []

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
        selected = multi.thickness_um if diagnostic.observable_multibeam else two.thickness_refined_um
        selected_model = "multi-beam" if diagnostic.observable_multibeam else "two-beam"

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
        }
    with (OUTPUT_DIR / "consistency.json").open("w", encoding="utf-8") as handle:
        json.dump(consistency, handle, ensure_ascii=False, indent=2)
    plot_summary_figures(summary, consistency, OUTPUT_DIR)

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

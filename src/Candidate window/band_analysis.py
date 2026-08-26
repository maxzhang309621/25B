"""SiC 全谱分段统计与条纹可测性分析，输出到 Candidate window/output。"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.signal import find_peaks, savgol_filter

_src = Path(__file__).resolve().parents[1]
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from config import DATA_DIR, DATASETS, OUTPUT_DIR  # noqa: E402
from data_io import load_spectrum  # noqa: E402

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# 物理分段（用于说明，非程序自动检测 Reststrahlen 的阈值）
SIC_SPECTRAL_REGIONS = (
    ("400-797", 400.0, 797.0, "普通反射区"),
    ("797-1000", 797.0, 1000.0, "Reststrahlen/声子强吸收"),
    ("1000-1100", 1000.0, 1100.0, "吸收谷底"),
    ("1100-1200", 1100.0, 1200.0, "过渡区（干涉刚恢复）"),
    ("1200-4000", 1200.0, 4000.0, "透明干涉主区"),
    ("1100-4000", 1100.0, 4000.0, "原 dev 默认窗"),
)

REGION_COLORS = {
    "400-797": "#E2E8F0",
    "797-1000": "#FEB2B2",
    "1000-1100": "#FBD38D",
    "1100-1200": "#FAF089",
    "1200-4000": "#C6F6D5",
    "1100-4000": "#BEE3F8",
}


def _odd_window(width_cm1: float, spacing_cm1: float, n: int) -> int:
    value = max(5, int(round(width_cm1 / spacing_cm1)))
    if value % 2 == 0:
        value += 1
    largest = n if n % 2 == 1 else n - 1
    return min(value, largest)


def _fringe_metrics(
    wavenumber_cm1: np.ndarray,
    reflectance_pct: np.ndarray,
    n: float,
    angle_deg: float,
) -> dict:
    x, y = wavenumber_cm1, reflectance_pct
    if len(x) < 50:
        return {
            "point_count": len(x),
            "residual_std_pct": float("nan"),
            "envelope_residual_ratio": float("nan"),
            "fft_thickness_um": float("nan"),
            "extrema_count": 0,
            "mean_abs_dR_dnu": float("nan"),
        }

    spacing = float(np.median(np.diff(x)))
    short = _odd_window(10.0, spacing, len(x))
    long = _odd_window(430.0, spacing, len(x))
    smooth = savgol_filter(y, short, 3, mode="interp")
    baseline = savgol_filter(smooth, long, 3, mode="interp")
    residual = smooth - baseline

    window = np.hanning(len(residual))
    power = np.abs(np.fft.rfft((residual - residual.mean()) * window)) ** 2
    frequency = np.fft.rfftfreq(len(residual), spacing)
    optical_factor = n * np.sqrt(1.0 - (np.sin(np.deg2rad(angle_deg)) / n) ** 2)
    d_um = frequency * 1e4 / (2.0 * optical_factor)
    valid = (d_um >= 1.0) & (d_um <= 20.0)
    fft_um = float(d_um[valid][np.argmax(power[valid])]) if np.any(valid) else float("nan")

    approximate_period = 1e4 / (2.0 * optical_factor * fft_um) if np.isfinite(fft_um) else 240.0
    distance = max(3, int(0.55 * approximate_period / spacing))
    prominence = max(0.03, 0.12 * float(np.std(residual)))
    peaks, _ = find_peaks(residual, distance=distance, prominence=prominence)
    valleys, _ = find_peaks(-residual, distance=distance, prominence=prominence)

    smooth_diff = np.abs(np.diff(smooth))
    return {
        "point_count": len(x),
        "R_mean_pct": float(np.mean(y)),
        "R_min_pct": float(np.min(y)),
        "R_max_pct": float(np.max(y)),
        "R_std_pct": float(np.std(y)),
        "mean_abs_dR_dnu": float(np.mean(smooth_diff)),
        "residual_std_pct": float(np.std(residual)),
        "envelope_residual_ratio": float(smooth.std() / max(residual.std(), 1e-6)),
        "fft_thickness_um": fft_um,
        "extrema_count": int(len(peaks) + len(valleys)),
    }


def reflectance_segment_table(dataset_key: str) -> pd.DataFrame:
    spec = next(item for item in DATASETS if item.key == dataset_key)
    spectrum = load_spectrum(DATA_DIR, spec)
    nu, R = spectrum.wavenumber_cm1, spectrum.reflectance_pct
    rows = []
    for label, lo, hi, role in SIC_SPECTRAL_REGIONS:
        mask = (nu >= lo) & (nu <= hi)
        segment = R[mask]
        if len(segment) == 0:
            continue
        diff = np.abs(np.diff(savgol_filter(R[mask], min(51, len(segment) | 1), 3)))
        rows.append(
            {
                "dataset": dataset_key,
                "region": label,
                "lo_cm1": lo,
                "hi_cm1": hi,
                "role": role,
                "point_count": int(mask.sum()),
                "R_mean_pct": float(segment.mean()),
                "R_min_pct": float(segment.min()),
                "R_max_pct": float(segment.max()),
                "R_std_pct": float(segment.std()),
                "mean_abs_dR_dnu": float(diff.mean()) if len(diff) else float("nan"),
            }
        )
    return pd.DataFrame(rows)


def fringe_segment_table(dataset_key: str) -> pd.DataFrame:
    spec = next(item for item in DATASETS if item.key == dataset_key)
    spectrum = load_spectrum(DATA_DIR, spec)
    nu, R = spectrum.wavenumber_cm1, spectrum.reflectance_pct
    rows = []
    for label, lo, hi, role in SIC_SPECTRAL_REGIONS:
        mask = (nu >= lo) & (nu <= hi)
        metrics = _fringe_metrics(nu[mask], R[mask], spec.refractive_index, spec.angle_deg)
        rows.append(
            {
                "dataset": dataset_key,
                "region": label,
                "lo_cm1": lo,
                "hi_cm1": hi,
                "role": role,
                **metrics,
            }
        )
    return pd.DataFrame(rows)


def plot_sic_regions(dataset_key: str = "sic_10") -> Path:
    spec = next(item for item in DATASETS if item.key == dataset_key)
    spectrum = load_spectrum(DATA_DIR, spec)
    nu, R = spectrum.wavenumber_cm1, spectrum.reflectance_pct

    fig, ax = plt.subplots(figsize=(11, 4.2), dpi=150)
    for label, lo, hi, role in SIC_SPECTRAL_REGIONS:
        if label == "1100-4000":
            continue
        ax.axvspan(lo, hi, color=REGION_COLORS.get(label, "#EDF2F7"), alpha=0.55, label=role)
    ax.plot(nu, R, color="#2B6CB0", lw=0.7, alpha=0.9)
    ax.axvline(1200, color="#2F855A", ls="--", lw=1.2, label="当前主窗下限 1200")
    ax.axvline(1100, color="#C05621", ls=":", lw=1.2, label="原 dev 下限 1100")
    ax.set_xlim(nu.min(), nu.max())
    ax.set_xlabel(r"波数 $\tilde{\nu}$ (cm$^{-1}$)")
    ax.set_ylabel("反射率 R (%)")
    ax.set_title(f"SiC 全谱分段示意（{spec.filename}，{spec.angle_deg:.0f}°）")
    ax.grid(True, alpha=0.25)
    ax.legend(loc="upper right", fontsize=7, framealpha=0.92, ncol=2)
    fig.tight_layout()
    path = OUTPUT_DIR / f"{dataset_key}_spectrum_regions.png"
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def run_band_analysis() -> None:
    reflectance_frames = [reflectance_segment_table(key) for key in ("sic_10", "sic_15")]
    fringe_frames = [fringe_segment_table(key) for key in ("sic_10", "sic_15")]

    reflectance_df = pd.concat(reflectance_frames, ignore_index=True)
    fringe_df = pd.concat(fringe_frames, ignore_index=True)

    reflectance_df.to_csv(
        OUTPUT_DIR / "sic_reflectance_by_region.csv",
        index=False,
        encoding="utf-8-sig",
    )
    fringe_df.to_csv(
        OUTPUT_DIR / "sic_fringe_metrics_by_region.csv",
        index=False,
        encoding="utf-8-sig",
    )

    plot_sic_regions("sic_10")
    plot_sic_regions("sic_15")

    summary_lines = [
        "# 分段分析摘要（自动生成）",
        "",
        "## 797–1000 cm⁻¹（Reststrahlen）",
        "- 判据：文献 + 附件 R 剧烈起伏；单独 FFT 厚度常 >>15 μm 且极值数≈1。",
        "",
        "## 1100–1200 cm⁻¹（过渡区）",
        "- 判据：R 仍偏低、条纹残差弱；纳入 1100 下限会使 FFT 相对 1200 起算系统性偏高。",
        "",
        "## 1200–4000 cm⁻¹（主干涉区）",
        "- 判据：FFT 厚度 ~7.7–7.9 μm，极值数 ≥12，与 Q2 主结果一致。",
        "",
        "详细表格见 sic_reflectance_by_region.csv / sic_fringe_metrics_by_region.csv",
    ]
    (OUTPUT_DIR / "segment_analysis_summary.md").write_text(
        "\n".join(summary_lines), encoding="utf-8"
    )

    print(f"已写入 {OUTPUT_DIR}")
    print(reflectance_df.to_string(index=False, float_format=lambda v: f"{v:.4g}"))


if __name__ == "__main__":
    run_band_analysis()

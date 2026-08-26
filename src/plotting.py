"""论文级单附件诊断图与跨附件证据汇总图。"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import ListedColormap

from diagnostics import MultiBeamDiagnostic, harmonic_spectrum
from multi_beam import MultiBeamResult
from preprocess import ProcessedSpectrum
from two_beam import TwoBeamResult
from uncertainty import UncertaintyResult


COLORS = {
    "measured": "#7A7A7A",
    "smooth": "#56B4E9",
    "baseline": "#009E73",
    "two": "#0072B2",
    "multi": "#E69F00",
    "peak": "#D55E00",
    "valley": "#009E73",
    "selected": "#CC79A7",
    "pass": "#0072B2",
    "fail": "#999999",
}
THRESHOLDS = {
    "harmonic_ratio": 0.08,
    "effective_reflectivity": 0.12,
    "rmse_improvement_pct": 2.0,
    "delta_aicc": 10.0,
}


def _apply_style() -> None:
    try:
        plt.style.use("tableau-colorblind10")
    except OSError:
        plt.style.use("default")
    plt.rcParams.update(
        {
            "font.sans-serif": ["Microsoft YaHei", "SimHei", "DejaVu Sans"],
            "axes.unicode_minus": False,
            "axes.titlesize": 11,
            "axes.labelsize": 9,
            "legend.fontsize": 8,
            "xtick.labelsize": 8,
            "ytick.labelsize": 8,
            "grid.alpha": 0.22,
            "lines.linewidth": 1.1,
        }
    )


def _panel_label(ax, label: str) -> None:
    ax.text(
        0.01,
        0.98,
        label,
        transform=ax.transAxes,
        va="top",
        ha="left",
        fontsize=11,
        fontweight="bold",
    )


def plot_spectrum_fit(
    processed: ProcessedSpectrum,
    two: TwoBeamResult,
    multi: MultiBeamResult,
    diagnostic: MultiBeamDiagnostic,
    uncertainty: UncertaintyResult,
    path: Path,
) -> None:
    """生成包含原始谱、预处理、拟合、残差、频谱和判据的证据图。"""
    _apply_style()
    spec = processed.source.spec
    x = processed.wavenumber_cm1
    source = processed.source
    selected_um = (
        multi.thickness_um
        if diagnostic.observable_multibeam
        else two.thickness_refined_um
    )
    selected_model = "Airy 多光束" if diagnostic.observable_multibeam else "双光束"

    fig = plt.figure(figsize=(16, 13), layout="constrained")
    axes = fig.subplot_mosaic(
        [
            ["raw", "raw", "evidence"],
            ["pre", "pre", "evidence"],
            ["fit", "fit", "fft"],
            ["resid", "resid", "fft"],
        ],
        width_ratios=[1.0, 1.0, 0.86],
        height_ratios=[1.0, 1.0, 1.15, 1.0],
    )

    ax = axes["raw"]
    ax.plot(
        source.wavenumber_cm1,
        source.reflectance_pct,
        color=COLORS["measured"],
        lw=0.75,
        label="原始反射率",
    )
    ax.axvspan(x[0], x[-1], color=COLORS["smooth"], alpha=0.14, label="实际拟合波段")
    ax.set(title="全波段数据与拟合区间", ylabel="反射率 (%)")
    ax.legend(loc="best")
    ax.grid(True)
    _panel_label(ax, "(a)")

    ax = axes["pre"]
    ax.plot(x, processed.reflectance_pct, color=COLORS["measured"], lw=0.7, label="测量")
    ax.plot(x, processed.smooth_pct, color=COLORS["smooth"], label="平滑")
    ax.plot(x, processed.baseline_pct, color=COLORS["baseline"], label="慢变基线")
    ax.set(title="光谱预处理与基线分解", ylabel="反射率 (%)")
    ax.legend(loc="best", ncol=3)
    ax.grid(True)
    _panel_label(ax, "(b)")

    ax = axes["fit"]
    ax.plot(x, processed.residual_pct, color=COLORS["measured"], lw=0.75, label="去基线条纹")
    ax.plot(x, two.fitted_residual, color=COLORS["two"], label=f"双光束 ({two.thickness_refined_um:.3f} µm)")
    ax.plot(x, multi.fitted_residual, color=COLORS["multi"], label=f"Airy ({multi.thickness_um:.3f} µm)")
    ax.scatter(
        x[two.peak_indices],
        processed.residual_pct[two.peak_indices],
        s=24,
        marker="^",
        color=COLORS["peak"],
        edgecolors="white",
        linewidths=0.4,
        label=f"峰 ({len(two.peak_indices)})",
        zorder=4,
    )
    ax.scatter(
        x[two.valley_indices],
        processed.residual_pct[two.valley_indices],
        s=24,
        marker="v",
        color=COLORS["valley"],
        edgecolors="white",
        linewidths=0.4,
        label=f"谷 ({len(two.valley_indices)})",
        zorder=4,
    )
    ax.set(title="条纹极值与双/多光束拟合", ylabel="去基线反射率 (%)")
    ax.legend(loc="best", ncol=3)
    ax.grid(True)
    _panel_label(ax, "(c)")

    ax = axes["resid"]
    two_error = processed.residual_pct - two.fitted_residual
    multi_error = processed.residual_pct - multi.fitted_residual
    ax.plot(x, two_error, color=COLORS["two"], label=f"双光束残差，RMSE={two.rmse_pct:.3f}%")
    ax.plot(x, multi_error, color=COLORS["multi"], label=f"Airy 残差，RMSE={multi.rmse_pct:.3f}%")
    ax.axhline(0, color="black", lw=0.7)
    ax.text(
        0.99,
        0.94,
        f"RMSE 改善：{diagnostic.rmse_improvement_pct:.1f}%",
        transform=ax.transAxes,
        ha="right",
        va="top",
        bbox={"boxstyle": "round", "fc": "white", "alpha": 0.85},
    )
    ax.set(
        title="模型残差比较",
        xlabel=r"波数 (cm$^{-1}$)",
        ylabel="拟合误差 (%)",
    )
    ax.legend(loc="best", ncol=2)
    ax.grid(True)
    _panel_label(ax, "(d)")

    ax = axes["fft"]
    frequency, amplitude, fundamental, harmonic_ratio = harmonic_spectrum(
        processed, two.thickness_refined_um
    )
    upper = 2.65 * fundamental
    mask = (frequency > 0) & (frequency <= upper)
    ax.plot(frequency[mask], amplitude[mask], color=COLORS["two"])
    ax.axvline(fundamental, color=COLORS["two"], ls="--", label=f"基频 $f_1$={fundamental:.5f}")
    ax.axvline(2 * fundamental, color=COLORS["multi"], ls="--", label=f"二次谐波 $2f_1$")
    ax.scatter(
        [2 * fundamental],
        [harmonic_ratio],
        color=COLORS["peak"],
        s=35,
        zorder=4,
        label=f"$A_2/A_1$={harmonic_ratio:.3f}",
    )
    visible = amplitude[mask]
    ymax = min(4.0, max(1.25, float(np.percentile(visible, 99.5)) * 1.15))
    ax.set_ylim(0, ymax)
    ax.set(
        title="去基线条纹的归一化频谱",
        xlabel=r"频率 (cycles / cm$^{-1}$)",
        ylabel="相对基频幅值",
    )
    ax.legend(loc="best")
    ax.grid(True)
    _panel_label(ax, "(e)")

    ax = axes["evidence"]
    metric_labels = ["谐波比", "有效反射率", "RMSE 改善", "ΔAICc"]
    values = np.array(
        [
            diagnostic.harmonic_ratio,
            multi.effective_reflectivity,
            diagnostic.rmse_improvement_pct,
            diagnostic.delta_aicc,
        ]
    )
    thresholds = np.array(list(THRESHOLDS.values()))
    passed = values >= thresholds
    normalized = values / thresholds
    shown = np.minimum(normalized, 3.0)
    positions = np.arange(len(metric_labels))
    ax.barh(
        positions,
        shown,
        color=[COLORS["pass"] if flag else COLORS["fail"] for flag in passed],
        alpha=0.85,
    )
    ax.axvline(1.0, color="black", ls="--", lw=1.0, label="判据阈值")
    for y, raw, threshold, flag, norm in zip(
        positions, values, thresholds, passed, normalized
    ):
        suffix = "PASS" if flag else "FAIL"
        clipped = " ≥3×" if norm >= 3 else f" {norm:.2f}×"
        ax.text(
            min(shown[y] + 0.06, 2.45),
            y,
            f"{raw:.3g} / {threshold:g}{clipped}  {suffix}",
            va="center",
            fontsize=8,
        )
    ax.set_yticks(positions, metric_labels)
    ax.invert_yaxis()
    ax.set_xlim(0, 3.05)
    ax.set_xlabel("指标值 / 判据阈值（3×以上截断显示）")
    ax.set_title("多光束四项证据")
    ax.legend(loc="lower right")
    ax.grid(True, axis="x")
    conclusion = "支持可观测多光束干涉" if diagnostic.observable_multibeam else "多光束证据不足"
    ax.text(
        0.5,
        -0.22,
        (
            f"最终判定：{conclusion}\n"
            f"采用模型：{selected_model}；厚度={selected_um:.3f} µm\n"
            f"双光束重采样 95% CI=[{uncertainty.ci95_low_um:.3f}, "
            f"{uncertainty.ci95_high_um:.3f}] µm"
        ),
        transform=ax.transAxes,
        ha="center",
        va="top",
        fontsize=10,
        fontweight="bold",
        bbox={
            "boxstyle": "round,pad=0.55",
            "fc": "#E8F4FA" if diagnostic.observable_multibeam else "#F1F1F1",
            "ec": COLORS["pass"] if diagnostic.observable_multibeam else COLORS["fail"],
        },
    )
    _panel_label(ax, "(f)")

    fig.suptitle(
        (
            f"{spec.material}，入射角 {spec.angle_deg:g}°："
            f"光谱处理—拟合—多光束判定完整证据链"
        ),
        fontsize=15,
        fontweight="bold",
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def plot_thickness_comparison(summary: pd.DataFrame, path: Path) -> None:
    """绘制四附件模型厚度、最终值及置信区间。"""
    _apply_style()
    fig, axes = plt.subplots(1, 2, figsize=(12, 5.5), layout="constrained")
    for ax, material in zip(axes, ("SiC", "Si")):
        subset = summary[summary["material"] == material].sort_values("angle_deg")
        labels = subset["dataset"].tolist()
        x = np.arange(len(subset))
        selected = subset["selected_thickness_um"].to_numpy(float)
        low = subset["bootstrap_ci95_low_um"].to_numpy(float)
        high = subset["bootstrap_ci95_high_um"].to_numpy(float)
        yerr = np.vstack([selected - low, high - selected])
        yerr = np.clip(yerr, 0.0, None)
        ax.scatter(
            x - 0.13,
            subset["two_beam_thickness_um"],
            marker="o",
            s=55,
            color=COLORS["two"],
            label="双光束",
        )
        ax.scatter(
            x + 0.13,
            subset["multi_beam_thickness_um"],
            marker="s",
            s=55,
            color=COLORS["multi"],
            label="Airy 多光束",
        )
        ax.errorbar(
            x,
            selected,
            yerr=yerr,
            fmt="D",
            ms=7,
            color=COLORS["selected"],
            ecolor=COLORS["selected"],
            capsize=5,
            lw=1.4,
            label="最终采用值及 95% CI",
        )
        for position, (_, row) in enumerate(subset.iterrows()):
            ax.annotate(
                f"{row['selected_thickness_um']:.3f}\n{row['selected_model']}",
                (position, row["selected_thickness_um"]),
                xytext=(0, 12),
                textcoords="offset points",
                ha="center",
                fontsize=8,
            )
        ax.set_xticks(x, labels)
        ax.set(title=material, ylabel="外延层厚度 (µm)")
        ax.legend(loc="best")
        ax.grid(True, axis="y")
    fig.suptitle("四附件厚度结果、模型差异与不确定度", fontsize=14, fontweight="bold")
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def plot_angle_consistency(
    summary: pd.DataFrame, consistency: dict, path: Path
) -> None:
    """绘制每种材料两个入射角的厚度一致性。"""
    _apply_style()
    fig, axes = plt.subplots(1, 2, figsize=(11, 5), layout="constrained")
    for ax, material in zip(axes, ("SiC", "Si")):
        subset = summary[summary["material"] == material].sort_values("angle_deg")
        angles = subset["angle_deg"].to_numpy(float)
        values = subset["selected_thickness_um"].to_numpy(float)
        info = consistency[material]
        combined = info["weighted_combined_thickness_um"]
        ax.plot(angles, values, "o-", color=COLORS["selected"], ms=7, label="分角度最终厚度")
        ax.axhline(combined, color=COLORS["baseline"], ls="--", label=f"加权联合={combined:.3f} µm")
        for angle, value in zip(angles, values):
            ax.annotate(f"{value:.3f}", (angle, value), xytext=(0, 8), textcoords="offset points", ha="center")
        ax.text(
            0.5,
            0.06,
            f"双角度相对差：{info['angle_relative_difference_pct']:.3f}%",
            transform=ax.transAxes,
            ha="center",
            bbox={"boxstyle": "round", "fc": "white", "alpha": 0.9},
        )
        ax.set_xticks(angles, [f"{angle:g}°" for angle in angles])
        ax.set(title=material, xlabel="入射角", ylabel="最终厚度 (µm)")
        ax.legend(loc="best")
        ax.grid(True)
    fig.suptitle("双入射角厚度一致性与联合估计", fontsize=14, fontweight="bold")
    fig.savefig(path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def plot_multibeam_evidence(summary: pd.DataFrame, path: Path) -> None:
    """绘制四项判据的 PASS/FAIL 证据矩阵。"""
    _apply_style()
    metric_columns = [
        "harmonic_ratio",
        "effective_reflectivity",
        "rmse_improvement_pct",
        "delta_aicc",
    ]
    metric_labels = ["谐波比 ≥0.08", "有效反射率 ≥0.12", "RMSE改善 ≥2%", "ΔAICc ≥10"]
    thresholds = np.array(list(THRESHOLDS.values()))[:, None]
    values = summary[metric_columns].to_numpy(float).T
    passed = (values >= thresholds).astype(int)
    cmap = ListedColormap(["#D9D9D9", "#56B4E9"])

    fig, ax = plt.subplots(figsize=(10, 5.6), layout="constrained")
    ax.imshow(passed, cmap=cmap, vmin=0, vmax=1, aspect="auto")
    for row in range(values.shape[0]):
        for column in range(values.shape[1]):
            ax.text(
                column,
                row,
                f"{values[row, column]:.3g}\n{'PASS' if passed[row, column] else 'FAIL'}",
                ha="center",
                va="center",
                fontweight="bold",
                color="black",
            )
    labels = summary["dataset"].tolist()
    conclusions = [
        "多光束" if value else "证据不足"
        for value in summary["observable_multibeam"].tolist()
    ]
    ax.set_xticks(np.arange(len(labels)), [f"{label}\n{result}" for label, result in zip(labels, conclusions)])
    ax.set_yticks(np.arange(len(metric_labels)), metric_labels)
    ax.set_title("多光束干涉判定证据矩阵（必须四项全部通过）", fontweight="bold")
    ax.set_xticks(np.arange(-0.5, len(labels), 1), minor=True)
    ax.set_yticks(np.arange(-0.5, len(metric_labels), 1), minor=True)
    ax.grid(which="minor", color="white", linewidth=2)
    ax.tick_params(which="minor", bottom=False, left=False)
    fig.savefig(path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def plot_model_quality(summary: pd.DataFrame, path: Path) -> None:
    """比较双光束和多光束拟合误差以及改善幅度。"""
    _apply_style()
    labels = summary["dataset"].tolist()
    x = np.arange(len(summary))
    width = 0.34
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), layout="constrained")

    axes[0].bar(x - width / 2, summary["two_beam_rmse_pct"], width, color=COLORS["two"], label="双光束")
    axes[0].bar(x + width / 2, summary["multi_beam_rmse_pct"], width, color=COLORS["multi"], label="Airy")
    axes[0].set_xticks(x, labels)
    axes[0].set(title="模型拟合误差", ylabel="RMSE (%)")
    axes[0].legend()
    axes[0].grid(True, axis="y")

    improvements = summary["rmse_improvement_pct"].to_numpy(float)
    bars = axes[1].bar(x, improvements, color=COLORS["selected"])
    axes[1].axhline(THRESHOLDS["rmse_improvement_pct"], color="black", ls="--", label="2% 判据")
    axes[1].bar_label(bars, labels=[f"{value:.1f}%" for value in improvements], padding=3)
    axes[1].set_xticks(x, labels)
    axes[1].set(title="Airy 相对双光束的 RMSE 改善", ylabel="改善率 (%)")
    axes[1].legend()
    axes[1].grid(True, axis="y")

    fig.suptitle("双光束与多光束模型质量对比", fontsize=14, fontweight="bold")
    fig.savefig(path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def plot_summary_figures(
    summary: pd.DataFrame,
    consistency: dict,
    output_dir: Path,
) -> None:
    """生成所有跨附件汇总图。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    plot_thickness_comparison(summary, output_dir / "thickness_comparison.png")
    plot_angle_consistency(summary, consistency, output_dir / "angle_consistency.png")
    plot_multibeam_evidence(summary, output_dir / "multibeam_evidence.png")
    plot_model_quality(summary, output_dir / "model_quality.png")

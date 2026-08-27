"""论文级单附件诊断图与跨附件证据汇总图。

综合图可含 PASS/FAIL、采用依据等分析文字；
论文引用的无分析原始数据图见 raw_evidence_plotting。
"""

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
# 与 diagnostics.diagnose_multibeam 硬编码阈值保持一致。
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
            "axes.titlepad": 10,
            "axes.labelsize": 10,
            "legend.fontsize": 9,
            "legend.framealpha": 1.0,
            "legend.facecolor": "white",
            "legend.edgecolor": "#B0B0B0",
            "xtick.labelsize": 9,
            "ytick.labelsize": 9,
            "grid.alpha": 0.22,
            "lines.linewidth": 1.1,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
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
        bbox={"boxstyle": "round,pad=0.15", "fc": "white", "ec": "none", "alpha": 0.92},
        zorder=20,
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

    fig = plt.figure(figsize=(17.5, 14.5), layout="constrained")
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
            shown[y] + 0.08,
            y,
            f"{raw:.3g} / {threshold:g}{clipped}  {suffix}",
            va="center",
            fontsize=8,
            bbox={"boxstyle": "round,pad=0.12", "fc": "white", "ec": "none", "alpha": 0.9},
        )
    ax.set_yticks(positions, metric_labels)
    ax.invert_yaxis()
    ax.set_xlim(0, 4.35)
    ax.set_xlabel("指标值 / 判据阈值（3×以上截断显示）")
    ax.set_title("多光束四项证据")
    ax.legend(loc="lower right")
    ax.grid(True, axis="x")
    conclusion = "支持可观测多光束干涉" if diagnostic.observable_multibeam else "多光束证据不足"
    ax.text(
        0.5,
        -0.18,
        (
            f"最终判定：{conclusion}\n"
            f"采用模型：{selected_model}；厚度={selected_um:.3f} µm\n"
            f"双光束重采样 95% CI=[{uncertainty.ci95_low_um:.3f}, "
            f"{uncertainty.ci95_high_um:.3f}] µm"
        ),
        transform=ax.transAxes,
        ha="center",
        va="top",
        fontsize=9,
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
    """比较分角度模型与材料级色散联合结果。"""
    _apply_style()
    has_dispersion = "dispersion_adopted_thickness_um" in summary.columns
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.8), layout="constrained")
    for ax, material in zip(axes, ("SiC", "Si")):
        subset = summary[summary["material"] == material].sort_values("angle_deg")
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
                xytext=(0, 14 if position % 2 == 0 else -30),
                textcoords="offset points",
                ha="center",
                fontsize=8,
                bbox={"boxstyle": "round,pad=0.15", "fc": "white", "ec": "none", "alpha": 0.9},
            )
        labels = [f"{angle:g}°" for angle in subset["angle_deg"]]
        if has_dispersion:
            joint_x = len(subset) + 0.25
            first = subset.iloc[0]
            adopted = float(first["dispersion_adopted_thickness_um"])
            fitted = float(first["dispersion_fitted_thickness_um"])
            stat_low = float(first["dispersion_stat_ci95_low_um"])
            stat_high = float(first["dispersion_stat_ci95_high_um"])
            system_low = float(first["dispersion_systematic_low_um"])
            system_high = float(first["dispersion_systematic_high_um"])
            ax.errorbar(
                [joint_x],
                [adopted],
                yerr=[[adopted - stat_low], [stat_high - adopted]],
                fmt="P",
                ms=9,
                color=COLORS["baseline"],
                ecolor=COLORS["baseline"],
                capsize=5,
                label="色散门控采用值及条件统计区间",
            )
            ax.errorbar(
                [joint_x],
                [adopted],
                yerr=[[adopted - system_low], [system_high - adopted]],
                fmt="none",
                ecolor=COLORS["fail"],
                elinewidth=7,
                alpha=0.28,
                capsize=7,
                label="掺杂情景系统范围",
            )
            ax.scatter(
                [joint_x],
                [fitted],
                marker="x",
                s=70,
                linewidths=2,
                color=COLORS["peak"],
                label="自由浓度拟合值",
                zorder=5,
            )
            ax.annotate(
                f"采用 {adopted:.3f}\n自由拟合 {fitted:.3f}",
                (joint_x, adopted),
                xytext=(0, 14),
                textcoords="offset points",
                ha="center",
                fontsize=8,
                bbox={"boxstyle": "round,pad=0.15", "fc": "white", "ec": "none", "alpha": 0.9},
            )
            x = np.r_[x, joint_x]
            labels.append("色散联合")
        ax.set_xticks(x, labels)
        ax.set(title=material, ylabel="外延层厚度 (µm)")
        ax.margins(y=0.24)
        ax.legend(loc="best")
        ax.grid(True, axis="y")
    fig.suptitle(
        "常折射率模型、色散联合反演与两类不确定度",
        fontsize=14,
        fontweight="bold",
    )
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
        if "dispersion_adopted_thickness_um" in info:
            dispersion = float(info["dispersion_adopted_thickness_um"])
            system_low, system_high = info["dispersion_systematic_interval_um"]
            ax.axhspan(
                system_low,
                system_high,
                color=COLORS["fail"],
                alpha=0.14,
                label="掺杂情景系统范围",
            )
            ax.axhline(
                dispersion,
                color=COLORS["peak"],
                ls="-.",
                label=f"色散门控采用={dispersion:.3f} µm",
            )
        for index, (angle, value) in enumerate(zip(angles, values)):
            ax.annotate(
                f"{value:.3f}",
                (angle, value),
                xytext=(0, 10 if index % 2 == 0 else -22),
                textcoords="offset points",
                ha="center",
                bbox={"boxstyle": "round,pad=0.15", "fc": "white", "ec": "none", "alpha": 0.9},
            )
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
        ax.margins(y=0.24)
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
    axes[1].bar_label(bars, labels=[f"{value:.1f}%" for value in improvements], padding=5)
    axes[1].set_xticks(x, labels)
    axes[1].set(title="Airy 相对双光束的 RMSE 改善", ylabel="改善率 (%)")
    axes[1].margins(y=0.18)
    axes[1].legend()
    axes[1].grid(True, axis="y")

    fig.suptitle("双光束与多光束模型质量对比", fontsize=14, fontweight="bold")
    fig.savefig(path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def plot_dispersion_curves(curves: pd.DataFrame, path: Path) -> None:
    """绘制外延层与衬底的复折射率曲线。"""
    _apply_style()
    required = {
        "material",
        "wavenumber_cm1",
        "n_epi",
        "k_epi",
        "n_substrate",
        "k_substrate",
    }
    if curves.empty or not required.issubset(curves.columns):
        raise ValueError("折射率曲线数据缺少必要列")
    fig, axes = plt.subplots(2, 2, figsize=(13, 9), layout="constrained")
    for row, material in enumerate(("SiC", "Si")):
        subset = curves[curves["material"] == material].sort_values("wavenumber_cm1")
        x = subset["wavenumber_cm1"].to_numpy(float)
        for column, component in enumerate(("n", "k")):
            ax = axes[row, column]
            ax.plot(
                x,
                subset[f"{component}_epi"],
                color=COLORS["two"],
                label="外延层",
            )
            ax.plot(
                x,
                subset[f"{component}_substrate"],
                color=COLORS["multi"],
                ls="--",
                label="衬底",
            )
            if material == "SiC":
                ax.axvspan(
                    797,
                    1000,
                    color=COLORS["peak"],
                    alpha=0.12,
                    label="强声子带" if column == 0 else None,
                )
                ax.axvspan(
                    1300,
                    1600,
                    color=COLORS["fail"],
                    alpha=0.12,
                    label="二声子排除区" if column == 0 else None,
                )
            ax.set(
                title=f"{material}：{'实部 n' if component == 'n' else '消光系数 k'}",
                xlabel=r"波数 (cm$^{-1}$)",
                ylabel=component,
            )
            ax.grid(True)
            ax.legend(loc="best")
            _panel_label(ax, f"({chr(97 + row * 2 + column)})")
    fig.suptitle(
        "波长—载流子浓度耦合的外延层/衬底复折射率",
        fontsize=14,
        fontweight="bold",
    )
    fig.text(
        0.5,
        0.005,
        "来源：dispersion_fit.json 与 refractive_index_curves.csv；曲线为当前先验/情景参数",
        ha="center",
        fontsize=8,
    )
    fig.savefig(path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def plot_carrier_scenarios(results: dict, path: Path) -> None:
    """比较低/中/高掺杂情景的厚度与拟合误差。"""
    _apply_style()
    fig, axes = plt.subplots(2, 2, figsize=(13, 8.5), layout="constrained")
    for row, material in enumerate(("SiC", "Si")):
        result = results[material]
        scenarios = result["scenarios"]
        labels = [item["name"] for item in scenarios]
        thickness = np.array([item["thickness_um"] for item in scenarios])
        rmse = np.array([item["rmse_pct"] for item in scenarios])
        positions = np.arange(len(labels))

        ax = axes[row, 0]
        ax.plot(
            positions,
            thickness,
            "o-",
            color=COLORS["two"],
            ms=7,
            label="固定掺杂情景厚度",
        )
        ax.axhline(
            result["adopted_thickness_um"],
            color=COLORS["selected"],
            ls="--",
            label=f"门控采用={result['adopted_thickness_um']:.3f} µm",
        )
        for position, item in zip(positions, scenarios):
            ax.annotate(
                f"{item['thickness_um']:.3f}",
                (position, item["thickness_um"]),
                xytext=(0, 11 if position % 2 == 0 else -24),
                textcoords="offset points",
                ha="center",
                fontsize=8,
                bbox={"boxstyle": "round,pad=0.15", "fc": "white", "ec": "none", "alpha": 0.9},
            )
        span = max(float(np.ptp(thickness)), 0.08 * float(np.mean(thickness)))
        ax.set_ylim(float(np.min(thickness) - 0.16 * span), float(np.max(thickness) + 0.32 * span))
        ax.set_xticks(positions, labels)
        ax.set(title=f"{material}：掺杂情景厚度", ylabel="厚度 (µm)")
        ax.grid(True, axis="y")
        ax.legend(loc="best")

        ax = axes[row, 1]
        bars = ax.bar(positions, rmse, color=COLORS["multi"], alpha=0.8)
        ax.bar_label(bars, labels=[f"{value:.2f}%" for value in rmse], padding=3)
        ax.axhline(
            result["rmse_pct"],
            color=COLORS["peak"],
            ls="--",
            label=f"自由拟合 RMSE={result['rmse_pct']:.2f}%",
        )
        ax.set_xticks(positions, labels)
        ax.set(title=f"{material}：情景拟合质量", ylabel="RMSE (%)")
        ax.margins(y=0.18)
        ax.grid(True, axis="y")
        ax.legend(loc="best")
    fig.suptitle(
        "载流子浓度情景对厚度与拟合质量的影响",
        fontsize=14,
        fontweight="bold",
    )
    fig.savefig(path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def plot_identifiability_diagnostics(results: dict, path: Path) -> None:
    """显示连续留段稳定性、参数门控及最终回退路径。"""
    _apply_style()
    fig, axes = plt.subplots(2, 2, figsize=(13, 8.5), layout="constrained")
    for row, material in enumerate(("SiC", "Si")):
        result = results[material]
        bands = np.asarray(result["band_thicknesses_um"], dtype=float)
        positions = np.arange(1, len(bands) + 1)
        ax = axes[row, 0]
        ax.plot(positions, bands, "o-", color=COLORS["two"], ms=7)
        ax.axhline(
            result["adopted_thickness_um"],
            color=COLORS["selected"],
            ls="--",
            label=f"最终采用={result['adopted_thickness_um']:.3f} µm",
        )
        ax.set_xticks(positions, [f"连续波段 {value}" for value in positions])
        ax.set(title=f"{material}：连续留段厚度", ylabel="厚度 (µm)")
        ax.grid(True)
        ax.legend(loc="best")

        normalized = np.array(
            [
                result["band_cv_pct"] / 1.0,
                result["max_band_shift_pct"] / 2.0,
            ]
        )
        metric_labels = ["厚度 CV / 1%", "最大偏移 / 2%"]
        ax = axes[row, 1]
        colors = [
            COLORS["pass"] if value <= 1.0 else COLORS["fail"]
            for value in normalized
        ]
        bars = ax.barh(np.arange(2), normalized, color=colors)
        ax.axvline(1.0, color="black", ls="--", label="门控阈值")
        ax.bar_label(bars, labels=[f"{value:.2f}×" for value in normalized], padding=3)
        ax.set_yticks(np.arange(2), metric_labels)
        ax.invert_yaxis()
        ax.set_xlim(0, max(1.0, float(np.max(normalized))) * 1.6)
        ax.set(
            title=f"{material}：可辨识性门控",
            xlabel="指标值 / 阈值（≤1 通过）",
        )
        status = "可辨识" if result["concentration_identifiable"] else "不可唯一辨识"
        ax.text(
            0.5,
            -0.22,
            (
                f"浓度：{status}\n"
                f"边界命中：{'是' if result['boundary_hit'] else '否'}\n"
                f"采用依据：{result['adopted_basis']}"
            ),
            transform=ax.transAxes,
            ha="center",
            va="top",
            fontsize=8,
            bbox={"boxstyle": "round", "fc": "white", "alpha": 0.9},
        )
        ax.legend(loc="best")
        ax.grid(True, axis="x")
    fig.suptitle(
        "色散反演的连续波段稳定性与参数可辨识性",
        fontsize=14,
        fontweight="bold",
    )
    fig.savefig(path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def plot_carrier_profiles(
    profile: pd.DataFrame, result: dict, path: Path
) -> None:
    """绘制 SiC 两层浓度的 90% 条件轮廓区间。"""
    _apply_style()
    required = {"target", "log10_carrier_cm3", "delta_objective"}
    if profile.empty or not required.issubset(profile.columns):
        raise ValueError("浓度轮廓数据缺少必要列")
    fig, axes = plt.subplots(1, 2, figsize=(12.5, 5.2), layout="constrained")
    settings = (
        ("epi", "外延层", result.get("epi_log10_ci90")),
        ("substrate", "衬底", result.get("substrate_log10_ci90")),
    )
    for ax, (target, label, interval) in zip(axes, settings):
        subset = profile[profile["target"] == target].sort_values(
            "log10_carrier_cm3"
        )
        x = subset["log10_carrier_cm3"].to_numpy(float)
        delta = subset["delta_objective"].to_numpy(float)
        ax.plot(x, delta, "o-", color=COLORS["two"], ms=4, label="条件轮廓")
        ax.axhline(2.706, color=COLORS["peak"], ls="--", label="90% 阈值 Δχ²=2.706")
        if interval is not None:
            ax.axvspan(
                interval[0],
                interval[1],
                color=COLORS["smooth"],
                alpha=0.18,
                label=f"条件区间 [{interval[0]:.2f}, {interval[1]:.2f}]",
            )
        ax.set(
            title=f"SiC {label}载流子浓度轮廓",
            xlabel=r"$\log_{10}(N/\mathrm{cm}^{-3})$",
            ylabel=r"$\Delta$目标函数",
        )
        ax.set_yscale("symlog", linthresh=2.706)
        ax.set_ylim(0, max(8.0, float(np.max(delta)) * 1.05))
        ax.grid(True)
        ax.legend(loc="best")
    fig.suptitle(
        (
            "受约束仪器响应下的载流子浓度条件区间\n"
            f"测量模式：{result['measurement_mode']}；"
            f"可辨识等级：{result['identifiability_level']}"
        ),
        fontsize=13,
        fontweight="bold",
    )
    fig.text(
        0.5,
        0.005,
        "附件2存在超出100%的反射率，区间属于仪器校正条件下结果，不是绝对浓度测量",
        ha="center",
        fontsize=8,
    )
    fig.savefig(path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def plot_summary_figures(
    summary: pd.DataFrame,
    consistency: dict,
    output_dir: Path,
    dispersion_results: dict | None = None,
    refractive_curves: pd.DataFrame | None = None,
    carrier_result: dict | None = None,
    carrier_profile: pd.DataFrame | None = None,
) -> None:
    """生成所有跨附件汇总图。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    plot_thickness_comparison(summary, output_dir / "thickness_comparison.png")
    plot_angle_consistency(summary, consistency, output_dir / "angle_consistency.png")
    plot_multibeam_evidence(summary, output_dir / "multibeam_evidence.png")
    plot_model_quality(summary, output_dir / "model_quality.png")
    if dispersion_results is not None and refractive_curves is not None:
        plot_dispersion_curves(
            refractive_curves, output_dir / "dispersion_curves.png"
        )
        plot_carrier_scenarios(
            dispersion_results, output_dir / "carrier_scenarios.png"
        )
        plot_identifiability_diagnostics(
            dispersion_results, output_dir / "identifiability_diagnostics.png"
        )
    if carrier_result is not None and carrier_profile is not None:
        plot_carrier_profiles(
            carrier_profile, carrier_result, output_dir / "carrier_profile.png"
        )

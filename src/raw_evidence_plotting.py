"""导出可直接用于论文排版的单指标原始数据图。

约定：单指标/单物理量单图；仅保留标题、坐标轴、单位与必要图例；
禁止 PASS/FAIL、阈值结论、回退原因与分析段落。
输出目录：output/raw_evidence/{multibeam,dispersion}/
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from diagnostics import harmonic_spectrum
from preprocess import ProcessedSpectrum
from two_beam import TwoBeamResult


COLORS = {
    "primary": "#0072B2",
    "secondary": "#E69F00",
    "epi": "#0072B2",
    "substrate": "#E69F00",
}


def _style() -> None:
    """统一中文字体与可读字号。"""
    try:
        plt.style.use("tableau-colorblind10")
    except OSError:
        plt.style.use("default")
    plt.rcParams.update(
        {
            "font.sans-serif": ["Microsoft YaHei", "SimHei", "DejaVu Sans"],
            "axes.unicode_minus": False,
            "axes.titlesize": 12,
            "axes.labelsize": 10,
            "legend.fontsize": 9,
            "xtick.labelsize": 9,
            "ytick.labelsize": 9,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "grid.alpha": 0.2,
            "lines.linewidth": 1.35,
        }
    )


def _save(fig: plt.Figure, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=240, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def _external_legend(ax: plt.Axes) -> None:
    """图例外置，避免遮挡数据线。"""
    ax.legend(
        loc="upper left",
        bbox_to_anchor=(1.01, 1.0),
        borderaxespad=0.0,
        frameon=True,
        framealpha=1.0,
    )


def _dataset_labels(summary: pd.DataFrame) -> list[str]:
    return [
        f"{material} {angle:g}°"
        for material, angle in zip(summary["material"], summary["angle_deg"])
    ]


def _plot_metric(
    summary: pd.DataFrame,
    column: str,
    title: str,
    ylabel: str,
    path: Path,
) -> None:
    labels = _dataset_labels(summary)
    x = np.arange(len(labels))
    values = summary[column].to_numpy(float)
    fig, ax = plt.subplots(figsize=(8.4, 5.2), layout="constrained")
    ax.plot(
        x,
        values,
        marker="o",
        ms=7,
        color=COLORS["primary"],
        label=column,
    )
    ax.set_xticks(x, labels)
    ax.set(title=title, xlabel="数据集", ylabel=ylabel)
    ax.margins(x=0.12, y=0.18)
    ax.grid(True, axis="y")
    _save(fig, path)


def plot_raw_multibeam_evidence(
    summary: pd.DataFrame,
    spectra: list[tuple[str, ProcessedSpectrum, TwoBeamResult]],
    output_dir: Path,
) -> None:
    """导出四项多光束指标及每个附件的归一化频谱。"""
    _style()
    output_dir.mkdir(parents=True, exist_ok=True)
    metrics = (
        ("harmonic_ratio", "二次谐波与基频幅值比", r"$A_2/A_1$", "harmonic_ratio_raw.png"),
        (
            "effective_reflectivity",
            "Airy 模型有效反射率",
            "有效反射率",
            "effective_reflectivity_raw.png",
        ),
        (
            "rmse_improvement_pct",
            "Airy 模型相对双光束模型的 RMSE 变化",
            "RMSE 变化率 (%)",
            "rmse_improvement_raw.png",
        ),
        ("delta_aicc", "双光束与 Airy 模型的 AICc 差值", "ΔAICc", "delta_aicc_raw.png"),
    )
    for column, title, ylabel, filename in metrics:
        _plot_metric(summary, column, title, ylabel, output_dir / filename)

    for dataset, processed, two in spectra:
        frequency, amplitude, fundamental, _ = harmonic_spectrum(
            processed, two.thickness_refined_um
        )
        mask = (frequency > 0) & (frequency <= 2.65 * fundamental)
        fig, ax = plt.subplots(figsize=(8.4, 5.2), layout="constrained")
        ax.plot(
            frequency[mask],
            amplitude[mask],
            color=COLORS["primary"],
            label="归一化频谱",
        )
        ax.set(
            title=f"{dataset} 去基线条纹频谱",
            xlabel=r"频率 (cycles / cm$^{-1}$)",
            ylabel="相对基频幅值",
        )
        visible = amplitude[mask]
        ymax = min(4.0, max(1.25, float(np.percentile(visible, 99.5)) * 1.15))
        ax.set_ylim(0, ymax)
        ax.grid(True)
        _external_legend(ax)
        _save(fig, output_dir / f"{dataset}_harmonic_spectrum_raw.png")


def _plot_refractive_component(
    curves: pd.DataFrame,
    material: str,
    component: str,
    path: Path,
) -> None:
    subset = curves[curves["material"] == material].sort_values("wavenumber_cm1")
    if subset.empty:
        raise ValueError(f"缺少 {material} 折射率曲线")
    x = subset["wavenumber_cm1"].to_numpy(float)
    fig, ax = plt.subplots(figsize=(8.4, 5.2), layout="constrained")
    ax.plot(x, subset[f"{component}_epi"], color=COLORS["epi"], label="外延层")
    ax.plot(
        x,
        subset[f"{component}_substrate"],
        color=COLORS["substrate"],
        ls="--",
        label="衬底",
    )
    symbol = "n" if component == "n" else "k"
    name = "折射率实部" if component == "n" else "消光系数"
    ax.set(
        title=f"{material} 外延层与衬底{name}",
        xlabel=r"波数 (cm$^{-1}$)",
        ylabel=symbol,
    )
    ax.grid(True)
    _external_legend(ax)
    _save(fig, path)


def _scenario_rows(results: dict) -> pd.DataFrame:
    rows = []
    for material, result in results.items():
        for scenario in result["scenarios"]:
            rows.append({"material": material, **scenario})
    return pd.DataFrame(rows)


def _plot_scenarios(results: dict, value: str, ylabel: str, title: str, path: Path) -> None:
    frame = _scenario_rows(results)
    names = list(dict.fromkeys(frame["name"].tolist()))
    x = np.arange(len(names))
    fig, ax = plt.subplots(figsize=(8.4, 5.2), layout="constrained")
    for material, color, marker in (
        ("SiC", COLORS["primary"], "o"),
        ("Si", COLORS["secondary"], "s"),
    ):
        subset = frame[frame["material"] == material].set_index("name").loc[names]
        ax.plot(
            x,
            subset[value].to_numpy(float),
            marker=marker,
            ms=7,
            color=color,
            label=material,
        )
    ax.set_xticks(x, names)
    ax.set(title=title, xlabel="载流子浓度情景", ylabel=ylabel)
    ax.margins(x=0.12, y=0.18)
    ax.grid(True, axis="y")
    _external_legend(ax)
    _save(fig, path)


def plot_raw_dispersion_evidence(
    curves: pd.DataFrame,
    results: dict,
    profile: pd.DataFrame,
    output_dir: Path,
) -> None:
    """导出色散反演各数据层的独立原始图。"""
    _style()
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
    output_dir.mkdir(parents=True, exist_ok=True)

    for material in ("SiC", "Si"):
        prefix = material.lower()
        _plot_refractive_component(
            curves, material, "n", output_dir / f"{prefix}_refractive_index_n_raw.png"
        )
        _plot_refractive_component(
            curves,
            material,
            "k",
            output_dir / f"{prefix}_extinction_coefficient_k_raw.png",
        )

    _plot_scenarios(
        results,
        "thickness_um",
        "厚度 (µm)",
        "固定载流子浓度情景下的外延层厚度",
        output_dir / "scenario_thickness_raw.png",
    )
    _plot_scenarios(
        results,
        "rmse_pct",
        "RMSE (%)",
        "固定载流子浓度情景下的拟合误差",
        output_dir / "scenario_rmse_raw.png",
    )

    fig, ax = plt.subplots(figsize=(8.4, 5.2), layout="constrained")
    for material, color, marker in (
        ("SiC", COLORS["primary"], "o"),
        ("Si", COLORS["secondary"], "s"),
    ):
        bands = np.asarray(results[material]["band_thicknesses_um"], dtype=float)
        ax.plot(
            np.arange(1, len(bands) + 1),
            bands,
            marker=marker,
            ms=7,
            color=color,
            label=material,
        )
    ax.set(
        title="连续留段反演厚度",
        xlabel="连续留段序号",
        ylabel="厚度 (µm)",
    )
    ax.margins(x=0.12, y=0.18)
    ax.grid(True)
    _external_legend(ax)
    _save(fig, output_dir / "band_thickness_raw.png")

    required_profile = {"target", "log10_carrier_cm3", "delta_objective"}
    if profile.empty or not required_profile.issubset(profile.columns):
        raise ValueError("浓度轮廓数据缺少必要列")
    for target, layer in (("epi", "外延层"), ("substrate", "衬底")):
        subset = profile[profile["target"] == target].sort_values(
            "log10_carrier_cm3"
        )
        fig, ax = plt.subplots(figsize=(8.4, 5.2), layout="constrained")
        ax.plot(
            subset["log10_carrier_cm3"],
            subset["delta_objective"],
            "o-",
            ms=5,
            color=COLORS["primary"],
            label="条件轮廓",
        )
        ax.set(
            title=f"SiC {layer}载流子浓度条件轮廓",
            xlabel=r"$\log_{10}(N/\mathrm{cm}^{-3})$",
            ylabel=r"$\Delta$目标函数",
        )
        ax.set_yscale("symlog", linthresh=2.706)
        ax.margins(x=0.08, y=0.12)
        ax.grid(True)
        _external_legend(ax)
        _save(fig, output_dir / f"{target}_carrier_profile_raw.png")

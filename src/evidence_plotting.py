"""生成带分析标识的论文级模型证据图。

与 raw_evidence_plotting 的纯数据图并存；本模块只消费既有结果，
不重新拟合或改变任何模型判据。
"""

from __future__ import annotations

from pathlib import Path
from textwrap import fill

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from shared_thickness import V8_THRESHOLDS


COLORS = {
    "measured": "#6F6F6F",
    "peak": "#D55E00",
    "valley": "#009E73",
    "angle10": "#0072B2",
    "angle15": "#E69F00",
    "adopt": "#0072B2",
    "fallback": "#999999",
    "pass": "#009E73",
    "fail": "#D55E00",
    "baseline": "#7A7A7A",
    "interval": "#56B4E9",
}


def _style() -> None:
    try:
        plt.style.use("tableau-colorblind10")
    except OSError:
        plt.style.use("default")
    plt.rcParams.update(
        {
            "font.sans-serif": ["Microsoft YaHei", "SimHei", "DejaVu Sans"],
            "axes.unicode_minus": False,
            "axes.titlesize": 13,
            "axes.labelsize": 10,
            "legend.fontsize": 8.5,
            "xtick.labelsize": 9,
            "ytick.labelsize": 9,
            "grid.alpha": 0.22,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "legend.framealpha": 1.0,
        }
    )


def _save(fig: plt.Figure, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=240, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def _box(ax: plt.Axes, text: str, *, status: bool | None = None) -> None:
    color = (
        COLORS["pass"]
        if status is True
        else COLORS["fail"] if status is False else "#555555"
    )
    ax.text(
        1.03,
        0.55,
        text,
        transform=ax.transAxes,
        ha="left",
        va="center",
        fontsize=8.8,
        linespacing=1.45,
        bbox={
            "boxstyle": "round,pad=0.55",
            "fc": "white",
            "ec": color,
            "lw": 1.4,
            "alpha": 0.98,
        },
    )


def _material_name(material: str) -> str:
    return "碳化硅" if material == "SiC" else "硅"


def _plot_band_analysis(
    material: str,
    inputs: list,
    material_result,
    path: Path,
) -> Path:
    fig, ax = plt.subplots(figsize=(10.5, 5.7), layout="constrained")
    intrinsic = material_result.scenario_results[0]
    eligible_count = 0
    excluded_count = 0
    for processed, _ in inputs:
        color = (
            COLORS["angle10"]
            if processed.source.spec.angle_deg == 10.0
            else COLORS["angle15"]
        )
        label = f"{processed.source.spec.angle_deg:g}° 去基线条纹"
        ax.plot(
            processed.wavenumber_cm1,
            processed.residual_pct,
            color=color,
            lw=0.85,
            alpha=0.85,
            label=label,
        )
        points = [
            point
            for point in intrinsic.points
            if point.dataset == processed.source.spec.key
        ]
        good = [point for point in points if point.eligible]
        bad = [point for point in points if not point.eligible]
        eligible_count += len(good)
        excluded_count += len(bad)
        for kind, marker, edgecolor in (
            ("peak", "^", COLORS["peak"]),
            ("valley", "v", COLORS["valley"]),
        ):
            selected = [point for point in good if point.kind == kind]
            if selected:
                indices = np.asarray([point.sample_index for point in selected])
                ax.scatter(
                    processed.wavenumber_cm1[indices],
                    processed.residual_pct[indices],
                    marker=marker,
                    s=35,
                    facecolors="white",
                    edgecolors=edgecolor,
                    linewidths=1.2,
                    zorder=5,
                )
        if bad:
            indices = np.asarray([point.sample_index for point in bad])
            ax.scatter(
                processed.wavenumber_cm1[indices],
                processed.residual_pct[indices],
                marker="x",
                s=38,
                color=COLORS["fail"],
                zorder=6,
            )
    if material == "SiC":
        ax.axvspan(
            1300,
            1600,
            color=COLORS["fail"],
            alpha=0.10,
            label="二声子影响区（排除）",
        )
    ax.axvline(1200, color="black", ls="--", lw=0.9, label="透明区下界")
    ax.set(
        title=f"{_material_name(material)}厚度反演波段与极值资格",
        xlabel=r"波数 (cm$^{-1}$)",
        ylabel="去基线反射率 (%)",
    )
    ax.grid(True)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.14), ncol=3)
    _box(
        ax,
        (
            f"分析区：1200–4000 cm^-1\n"
            f"合格极值：{eligible_count}\n"
            f"排除极值：{excluded_count}\n"
            "△ 峰；▽ 谷；× 不合格\n"
            "条件：弱吸收、g单调、远离边缘"
        ),
        status=eligible_count >= V8_THRESHOLDS["minimum_inliers"],
    )
    return _save(fig, path)


def _plot_order_analysis(material: str, material_result, path: Path) -> Path:
    result = material_result.scenario_results[0]
    points = [
        point
        for point in result.points
        if point.eligible and point.order_recovered >= 0
    ]
    fig, ax = plt.subplots(figsize=(10.5, 5.7), layout="constrained")
    sequence_colors = {
        "sic_10:peak": COLORS["angle10"],
        "sic_10:valley": COLORS["peak"],
        "sic_15:peak": COLORS["angle15"],
        "sic_15:valley": COLORS["valley"],
        "si_10:peak": COLORS["angle10"],
        "si_10:valley": COLORS["peak"],
        "si_15:peak": COLORS["angle15"],
        "si_15:valley": COLORS["valley"],
    }
    for sequence in sorted({point.sequence for point in points}):
        sequence_points = sorted(
            [point for point in points if point.sequence == sequence],
            key=lambda point: point.g_cm1,
        )
        x = np.asarray([point.g_cm1 for point in sequence_points])
        y = np.asarray([point.order_recovered for point in sequence_points])
        residual = np.asarray([point.residual_order for point in sequence_points])
        inlier = np.asarray([point.inlier for point in sequence_points])
        color = sequence_colors[sequence]
        ax.scatter(
            x[inlier],
            y[inlier],
            s=34,
            color=color,
            label=f"{sequence} 内点",
            zorder=5,
        )
        prediction = y[inlier] + residual[inlier]
        order = np.argsort(x[inlier])
        ax.plot(
            x[inlier][order],
            prediction[order],
            color=color,
            ls="--",
            alpha=0.85,
        )
        if np.any(~inlier):
            ax.scatter(
                x[~inlier],
                y[~inlier],
                marker="x",
                s=55,
                color=COLORS["fail"],
                label=f"{sequence} 异常点",
            )
    ax.set(
        title=f"{_material_name(material)}本征色散坐标多峰谷共享厚度回归",
        xlabel=r"光学相位坐标 $g$ (cm$^{-1}$)",
        ylabel="恢复后的局部干涉级次",
    )
    ax.grid(True)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.14), ncol=2)
    decision = "采用 v8" if material_result.adopted else "不采用 v8"
    _box(
        ax,
        (
            f"名义厚度：{material_result.nominal_thickness_um:.4f} µm\n"
            f"统计95%区间："
            f"[{material_result.statistical_ci95_low_um:.4f}, "
            f"{material_result.statistical_ci95_high_um:.4f}] µm\n"
            f"峰谷差：{material_result.peak_valley_diff_pct:.3f}%\n"
            f"双角度差：{material_result.angle_diff_pct:.3f}%\n"
            f"有效极值：{result.inlier_count}/{result.total_eligible}\n"
            f"结论：{decision}"
        ),
        status=material_result.adopted,
    )
    return _save(fig, path)


def _plot_residual_analysis(material: str, material_result, path: Path) -> Path:
    result = material_result.scenario_results[0]
    points = [point for point in result.points if point.eligible]
    finite = [point for point in points if np.isfinite(point.residual_order)]
    fig, ax = plt.subplots(figsize=(10.5, 5.7), layout="constrained")
    for kind, color, marker in (
        ("peak", COLORS["peak"], "^"),
        ("valley", COLORS["valley"], "v"),
    ):
        selected = [point for point in finite if point.kind == kind]
        ax.scatter(
            [point.g_cm1 for point in selected],
            [point.residual_order for point in selected],
            color=color,
            marker=marker,
            s=34,
            label=kind,
        )
    threshold = max(0.25, 3.0 * result.residual_scale_order)
    ax.axhline(0.0, color="black", lw=1.0, label="零残差")
    ax.axhspan(
        -threshold,
        threshold,
        color=COLORS["interval"],
        alpha=0.14,
        label=f"稳健内点带 ±{threshold:.3f}级",
    )
    max_point = (
        max(finite, key=lambda point: abs(point.residual_order)) if finite else None
    )
    if max_point is not None:
        ax.annotate(
            f"最大残差 {max_point.residual_order:+.3f}级",
            (max_point.g_cm1, max_point.residual_order),
            xytext=(12, 18),
            textcoords="offset points",
            arrowprops={"arrowstyle": "->", "color": COLORS["fail"]},
            bbox={"boxstyle": "round", "fc": "white", "alpha": 0.95},
        )
    ax.set(
        title=f"{_material_name(material)}色散坐标级次回归残差",
        xlabel=r"光学相位坐标 $g$ (cm$^{-1}$)",
        ylabel="级次残差",
    )
    ax.grid(True)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.14), ncol=3)
    _box(
        ax,
        (
            f"稳健尺度：{result.residual_scale_order:.4f}级\n"
            f"异常阈值：±{threshold:.3f}级\n"
            f"剔除比例：{result.rejected_fraction*100:.2f}%\n"
            f"门槛：≤"
            f"{V8_THRESHOLDS['maximum_rejected_fraction']*100:.0f}%"
        ),
        status=(
            result.rejected_fraction
            <= V8_THRESHOLDS["maximum_rejected_fraction"]
        ),
    )
    return _save(fig, path)


def _plot_gate_analysis(
    material: str,
    summary: pd.DataFrame,
    material_result,
    comparison: dict,
    path: Path,
) -> Path:
    result = material_result.scenario_results[0]
    selected_models = summary.loc[
        summary["material"] == material, "selected_model"
    ].tolist()
    multi_required = any(model == "multi-beam" for model in selected_models)
    metrics = [
        (
            "峰谷差",
            material_result.peak_valley_diff_pct,
            V8_THRESHOLDS["peak_valley_diff_pct"],
            "<=",
        ),
        (
            "双角度差",
            material_result.angle_diff_pct,
            V8_THRESHOLDS["angle_diff_pct"],
            "<=",
        ),
        (
            "留段CV",
            material_result.band_cv_pct,
            V8_THRESHOLDS["band_cv_pct"],
            "<=",
        ),
        (
            "最大偏移",
            material_result.max_band_shift_pct,
            V8_THRESHOLDS["max_band_shift_pct"],
            "<=",
        ),
        (
            "剔除比例",
            result.rejected_fraction * 100.0,
            V8_THRESHOLDS["maximum_rejected_fraction"] * 100.0,
            "<=",
        ),
    ]
    if multi_required:
        metrics.append(
            (
                "Airy差",
                comparison["multi_beam_consistency_pct"],
                V8_THRESHOLDS["multi_beam_consistency_pct"],
                "<=",
            )
        )
    values = np.asarray([actual / threshold for _, actual, threshold, _ in metrics])
    passed = values <= 1.0
    labels = [item[0] for item in metrics]
    fig, ax = plt.subplots(figsize=(10.5, 5.7), layout="constrained")
    bars = ax.barh(
        np.arange(len(labels)),
        values,
        color=[COLORS["pass"] if flag else COLORS["fail"] for flag in passed],
        alpha=0.85,
    )
    ax.axvline(1.0, color="black", ls="--", label="门控阈值")
    ax.set_yticks(np.arange(len(labels)), labels)
    ax.invert_yaxis()
    ax.set(
        title=f"{_material_name(material)}v8稳定性与模型一致性门控",
        xlabel="指标值 / 门控阈值（≤1通过）",
    )
    ax.set_xlim(0, max(1.15, float(np.max(values)) * 1.30))
    for bar, (_, actual, threshold, _), flag in zip(bars, metrics, passed):
        ax.text(
            bar.get_width() + 0.03,
            bar.get_y() + bar.get_height() / 2,
            f"{actual:.3f}/{threshold:g}  {'通过' if flag else '失败'}",
            va="center",
            fontsize=8.5,
        )
    ax.grid(True, axis="x")
    ax.legend(loc="lower right")
    reason = comparison["fallback_reason"] or "全部门控通过"
    _box(
        ax,
        (
            f"最终：{'采用v8' if comparison['v8_adopted'] else '回退原模型'}\n"
            f"厚度：{comparison['final_thickness_um']:.4f} µm\n"
            f"依据：{fill(reason, width=22)}"
        ),
        status=comparison["v8_adopted"],
    )
    return _save(fig, path)


def _plot_scenario_analysis(
    material: str,
    material_result,
    comparison: dict,
    path: Path,
) -> Path:
    scenarios = material_result.scenario_results
    labels = [result.scenario for result in scenarios]
    values = np.asarray([result.thickness_um for result in scenarios])
    lower = np.asarray([result.bootstrap_ci95_low_um for result in scenarios])
    upper = np.asarray([result.bootstrap_ci95_high_um for result in scenarios])
    positions = np.arange(len(labels))
    fig, ax = plt.subplots(figsize=(10.5, 5.7), layout="constrained")
    ax.axhspan(
        material_result.systematic_low_um,
        material_result.systematic_high_um,
        color=COLORS["interval"],
        alpha=0.14,
        label="固定情景与基线系统范围",
    )
    ax.axhline(
        comparison["l0_constant_index_thickness_um"],
        color=COLORS["baseline"],
        ls="--",
        label="常折射率基线",
    )
    errors = np.vstack([values - lower, upper - values])
    ax.errorbar(
        positions,
        values,
        yerr=errors,
        fmt="o-",
        capsize=5,
        color=COLORS["adopt"],
        label="情景厚度及条件95%区间",
    )
    for position, result in zip(positions, scenarios):
        ax.annotate(
            f"{result.thickness_um:.4f}\n{'稳定' if result.stable else '不稳定'}",
            (position, result.thickness_um),
            xytext=(0, 12 if position % 2 == 0 else -34),
            textcoords="offset points",
            ha="center",
            fontsize=8,
            bbox={"boxstyle": "round", "fc": "white", "alpha": 0.95},
        )
    ax.set_xticks(positions, labels)
    ax.set(
        title=f"{_material_name(material)}固定折射率情景厚度与系统范围",
        xlabel="折射率情景",
        ylabel="厚度 (µm)",
    )
    ax.margins(x=0.10, y=0.22)
    ax.grid(True, axis="y")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.14), ncol=2)
    _box(
        ax,
        (
            f"本征名义值：{material_result.nominal_thickness_um:.4f} µm\n"
            f"统计区间：[{material_result.statistical_ci95_low_um:.4f}, "
            f"{material_result.statistical_ci95_high_um:.4f}]\n"
            f"系统范围：[{material_result.systematic_low_um:.4f}, "
            f"{material_result.systematic_high_um:.4f}] µm\n"
            "统计区间与系统范围分别报告"
        ),
        status=material_result.adopted,
    )
    return _save(fig, path)


def _plot_decision_analysis(comparison: dict, path: Path) -> Path:
    materials = ("SiC", "Si")
    fig, ax = plt.subplots(figsize=(10.5, 5.7), layout="constrained")
    for row, material in enumerate(materials):
        item = comparison["materials"][material]
        baseline = item["l0_constant_index_thickness_um"]
        nominal_delta = (item["v8_nominal_thickness_um"] / baseline - 1.0) * 100.0
        final_delta = (item["final_thickness_um"] / baseline - 1.0) * 100.0
        low, high = item["v8_systematic_interval_um"]
        ax.hlines(
            row,
            (low / baseline - 1.0) * 100.0,
            (high / baseline - 1.0) * 100.0,
            color=COLORS["interval"],
            lw=8,
            alpha=0.55,
            label="系统范围" if row == 0 else None,
        )
        ax.scatter(0.0, row, color=COLORS["baseline"], s=70, label="L0基线" if row == 0 else None)
        ax.scatter(
            nominal_delta,
            row,
            marker="D",
            color=COLORS["adopt"] if item["v8_adopted"] else COLORS["fail"],
            s=70,
            label="v8候选" if row == 0 else None,
        )
        ax.scatter(
            final_delta,
            row,
            marker="*",
            color=COLORS["pass"],
            s=150,
            label="最终采用" if row == 0 else None,
        )
        ax.annotate(
            (
                f"最终 {item['final_thickness_um']:.4f} µm\n"
                f"{'采用v8' if item['v8_adopted'] else '回退Airy'}"
            ),
            (final_delta, row),
            xytext=(12, 12),
            textcoords="offset points",
            fontsize=8.5,
            bbox={"boxstyle": "round", "fc": "white", "alpha": 0.95},
        )
    ax.axvline(0.0, color="black", lw=0.9)
    ax.set_yticks(np.arange(len(materials)), [_material_name(value) for value in materials])
    ax.set(
        title="v8候选、常折射率基线与最终模型决策",
        xlabel="相对常折射率基线变化 (%)",
        ylabel="材料",
    )
    ax.grid(True, axis="x")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.14), ncol=4)
    _box(
        ax,
        (
            "决策链：\n"
            "SiC：内部稳定 → 采用v8\n"
            "Si：峰谷/留段/Airy冲突\n"
            "→ 回退多光束模型"
        ),
    )
    return _save(fig, path)


def _plot_audit_analysis(material: str, audit: dict, path: Path) -> Path:
    payload = audit["materials"][material]["joint_calibration"]
    checks = payload["checks"]
    selected = [
        "jacobian_condition",
        "max_parameter_correlation",
        "band_cv_pct",
        "max_band_shift_pct",
    ]
    labels = ["Jacobian条件数", "参数相关性", "留段CV", "最大偏移"]
    values = np.asarray(
        [
            float(checks[name]["value"]) / max(float(checks[name]["threshold"]), 1e-15)
            for name in selected
        ]
    )
    passed = np.asarray([bool(checks[name]["passed"]) for name in selected])
    fig, ax = plt.subplots(figsize=(10.5, 5.7), layout="constrained")
    bars = ax.barh(
        np.arange(len(labels)),
        values,
        color=[COLORS["pass"] if flag else COLORS["fail"] for flag in passed],
        alpha=0.85,
    )
    ax.axvline(1.0, color="black", ls="--", label="审计阈值")
    ax.set_yticks(np.arange(len(labels)), labels)
    ax.invert_yaxis()
    ax.set(
        title=f"{_material_name(material)}自由载流子反演可辨识性审计",
        xlabel="指标值 / 阈值",
    )
    ax.set_xscale("log")
    ax.grid(True, axis="x")
    ax.legend(loc="lower right")
    for bar, name, flag in zip(bars, selected, passed):
        item = checks[name]
        ax.text(
            bar.get_width() * 1.08,
            bar.get_y() + bar.get_height() / 2,
            f"{item['value']:.3g} {'通过' if flag else '失败'}",
            va="center",
            fontsize=8.5,
        )
    reasons = payload["failure_reasons"] or ["无失败项"]
    enhanced = audit["materials"][material].get("enhanced_carrier_inference")
    extra = ""
    if enhanced is not None:
        extra = (
            f"\n增强反演：{enhanced['identifiability_level']}"
            f"\n点估计报告：{'是' if enhanced['point_estimate_reported'] else '否'}"
        )
    _box(
        ax,
        (
            "用途：仅审计，不作为主厚度\n"
            f"候选厚度：{payload['candidate']['thickness_um']:.4f} µm\n"
            f"失败依据：{fill('；'.join(reasons), width=20)}"
            f"{extra}"
        ),
        status=payload["concentration_identifiable"],
    )
    return _save(fig, path)


def plot_analysis_evidence(
    summary: pd.DataFrame,
    extrema_inputs: dict,
    v8_results: dict,
    v8_comparison: dict,
    identifiability_audit: dict,
    output_dir: Path,
) -> list[Path]:
    """生成全部分析型证据图，返回文件路径。"""
    _style()
    required = {
        "material",
        "selected_model",
        "selected_thickness_um",
        "v8_nominal_thickness_um",
        "v8_adopted",
    }
    if summary.empty or not required.issubset(summary.columns):
        raise ValueError("分析型证据图缺少汇总字段")
    saved: list[Path] = []
    for material in ("SiC", "Si"):
        if material not in v8_results or material not in extrema_inputs:
            raise ValueError(f"分析型证据图缺少 {material} 输入")
        result = v8_results[material]
        comparison = v8_comparison["materials"][material]
        prefix = material.lower()
        saved.append(
            _plot_band_analysis(
                material,
                extrema_inputs[material],
                result,
                output_dir / f"{prefix}_band_eligibility_analysis.png",
            )
        )
        saved.append(
            _plot_order_analysis(
                material,
                result,
                output_dir / f"{prefix}_order_fit_analysis.png",
            )
        )
        saved.append(
            _plot_residual_analysis(
                material,
                result,
                output_dir / f"{prefix}_order_residual_analysis.png",
            )
        )
        saved.append(
            _plot_gate_analysis(
                material,
                summary,
                result,
                comparison,
                output_dir / f"{prefix}_stability_gates_analysis.png",
            )
        )
        saved.append(
            _plot_scenario_analysis(
                material,
                result,
                comparison,
                output_dir / f"{prefix}_scenario_thickness_analysis.png",
            )
        )
        saved.append(
            _plot_audit_analysis(
                material,
                identifiability_audit,
                output_dir / f"{prefix}_carrier_audit_analysis.png",
            )
        )
    saved.append(
        _plot_decision_analysis(
            v8_comparison,
            output_dir / "final_model_decision_analysis.png",
        )
    )
    return saved

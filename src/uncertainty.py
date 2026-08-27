"""厚度重采样区间和双角度一致性指标。

优先对峰/谷间距做 bootstrap；极值不足时回退残差区块重采样。
"""

from dataclasses import dataclass, replace

import numpy as np

from optics import thickness_from_fringe_spacing
from preprocess import ProcessedSpectrum
from two_beam import TwoBeamResult, estimate_two_beam


@dataclass
class UncertaintyResult:
    """双光束厚度的条件统计不确定度（不含掺杂系统误差）。"""

    samples_um: np.ndarray
    mean_um: float
    std_um: float
    ci95_low_um: float
    ci95_high_um: float


def _moving_block_sample(errors: np.ndarray, block_points: int, rng) -> np.ndarray:
    """移动区块重采样，保留残差局部相关结构。"""
    n = len(errors)
    block_points = max(2, min(block_points, n))
    starts = rng.integers(0, n - block_points + 1, size=int(np.ceil(n / block_points)))
    sampled = np.concatenate([errors[s : s + block_points] for s in starts])[:n]
    return sampled


def bootstrap_two_beam(
    processed: ProcessedSpectrum,
    result: TwoBeamResult,
    repeats: int = 40,
    block_cm1: float = 80.0,
    seed: int = 2025,
) -> UncertaintyResult:
    """估计双光束厚度的 95% 重采样区间。"""
    rng = np.random.default_rng(seed)
    x = processed.wavenumber_cm1
    interval_groups = [
        np.diff(x[result.peak_indices]),
        np.diff(x[result.valley_indices]),
    ]
    interval_groups = [group for group in interval_groups if len(group) >= 3]
    estimates: list[float] = []
    if interval_groups:
        spec = processed.source.spec
        for _ in range(repeats):
            group_means = [
                float(np.mean(rng.choice(group, size=len(group), replace=True)))
                for group in interval_groups
            ]
            spacing = float(np.median(group_means))
            estimates.append(
                thickness_from_fringe_spacing(
                    spacing, spec.refractive_index, spec.angle_deg
                )
            )
    else:
        errors = processed.residual_pct - result.fitted_residual
        block_points = int(round(block_cm1 / processed.spacing_cm1))
        for _ in range(repeats):
            synthetic = replace(
                processed,
                residual_pct=result.fitted_residual
                + _moving_block_sample(errors, block_points, rng),
            )
            estimate = estimate_two_beam(synthetic).thickness_refined_um
            if abs(estimate - result.thickness_refined_um) / result.thickness_refined_um <= 0.15:
                estimates.append(estimate)
    if len(estimates) < 5:
        raise RuntimeError("有效重采样次数不足")
    values = np.asarray(estimates)
    # 重采样的是平均间距，而点估计来自 Theil–Sen 斜率；将分布中心
    # 对齐点估计，只保留重采样反映的离散程度，避免方法差异造成伪偏差。
    values = values - values.mean() + result.thickness_refined_um
    low, high = np.percentile(values, [2.5, 97.5])
    return UncertaintyResult(
        values,
        float(values.mean()),
        float(values.std(ddof=1)),
        float(low),
        float(high),
    )


def relative_angle_difference(first_um: float, second_um: float) -> float:
    mean = (first_um + second_um) / 2.0
    return float(abs(first_um - second_um) / mean * 100.0)

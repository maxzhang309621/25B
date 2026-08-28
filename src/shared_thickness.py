"""v8 多角度峰谷序列的共享厚度稳健反演。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace

import numpy as np
from scipy.optimize import least_squares

from dispersion_extrema import MappedExtremum


V8_THRESHOLDS = {
    "peak_valley_diff_pct": 1.5,
    "angle_diff_pct": 2.0,
    "band_cv_pct": 2.0,
    "max_band_shift_pct": 3.0,
    "minimum_inliers": 12,
    "maximum_rejected_fraction": 0.2,
    "multi_beam_consistency_pct": 2.0,
}


@dataclass(frozen=True)
class SharedThicknessResult:
    material: str
    scenario: str
    thickness_um: float
    peak_only_um: float
    valley_only_um: float
    angle_10_um: float
    angle_15_um: float
    peak_valley_diff_pct: float
    angle_diff_pct: float
    residual_scale_order: float
    total_eligible: int
    inlier_count: int
    rejected_extrema: int
    rejected_fraction: float
    bootstrap_ci95_low_um: float
    bootstrap_ci95_high_um: float
    band_thicknesses_um: tuple[float, ...]
    band_cv_pct: float
    max_band_shift_pct: float
    stable: bool
    failure_reason: str
    points: tuple[MappedExtremum, ...]

    def to_dict(self, include_points: bool = False) -> dict:
        payload = asdict(self)
        if not include_points:
            payload.pop("points", None)
        return payload


def _relative_difference(first: float, second: float) -> float:
    if not np.isfinite(first) or not np.isfinite(second):
        return float("inf")
    mean = 0.5 * (first + second)
    return float(abs(first - second) / mean * 100.0) if mean > 0 else float("inf")


def _fit_points(
    points: list[MappedExtremum],
    robust: bool = True,
) -> tuple[float, np.ndarray, np.ndarray]:
    usable = [point for point in points if point.eligible and point.order_recovered >= 0]
    sequences = sorted({point.sequence for point in usable})
    if len(usable) < 4 or not sequences:
        raise ValueError("共享厚度回归的有效极值不足")
    x = np.asarray([point.g_cm1 for point in usable], dtype=float)
    y = np.asarray([point.order_recovered for point in usable], dtype=float)
    weights = np.sqrt(
        np.asarray([max(point.quality_weight, 0.05) for point in usable], dtype=float)
    )
    center = float(np.mean(x))
    design = np.zeros((len(usable), 1 + len(sequences)), dtype=float)
    design[:, 0] = x - center
    sequence_index = {name: index for index, name in enumerate(sequences)}
    for row, point in enumerate(usable):
        design[row, 1 + sequence_index[point.sequence]] = 1.0
    initial, *_ = np.linalg.lstsq(design * weights[:, None], y * weights, rcond=None)

    if robust:
        fit = least_squares(
            lambda params: (design @ params - y) * weights,
            initial,
            loss="soft_l1",
            f_scale=0.15,
            x_scale="jac",
            max_nfev=500,
        )
        params = fit.x
    else:
        params = initial
    slope = float(params[0])
    if not np.isfinite(slope) or slope <= 0:
        raise ValueError("共享厚度回归得到非正斜率")
    residual = design @ params - y
    return slope * 1e4 / 2.0, residual, np.asarray(usable, dtype=object)


def _fit_with_outlier_filter(
    points: list[MappedExtremum],
) -> tuple[float, np.ndarray, np.ndarray, np.ndarray]:
    thickness, residual, usable = _fit_points(points, robust=True)
    median = float(np.median(residual))
    mad = float(np.median(np.abs(residual - median)))
    scale = max(1.4826 * mad, 0.05)
    inlier = np.abs(residual - median) <= max(0.25, 3.0 * scale)
    if np.count_nonzero(inlier) >= 4 and not np.all(inlier):
        filtered = [point for point, keep in zip(usable, inlier) if keep]
        thickness, filtered_residual, filtered_usable = _fit_points(filtered, robust=True)
        residual_lookup = {
            (point.dataset, point.kind, point.sample_index): value
            for point, value in zip(filtered_usable, filtered_residual)
        }
        final_residual = np.asarray(
            [
                residual_lookup.get(
                    (point.dataset, point.kind, point.sample_index),
                    float("nan"),
                )
                for point in usable
            ],
            dtype=float,
        )
        return thickness, final_residual, usable, inlier
    return thickness, residual, usable, np.ones(len(usable), dtype=bool)


def _subset_thickness(
    points: list[MappedExtremum],
    *,
    kind: str | None = None,
    angle: float | None = None,
) -> float:
    subset = [
        point
        for point in points
        if (kind is None or point.kind == kind)
        and (angle is None or abs(point.angle_deg - angle) < 1e-9)
    ]
    try:
        return _fit_with_outlier_filter(subset)[0]
    except ValueError:
        return float("nan")


def _band_stability(
    points: list[MappedExtremum],
    full_thickness_um: float,
) -> tuple[tuple[float, ...], float, float]:
    usable = [point for point in points if point.eligible]
    if len(usable) < 9:
        return (), float("inf"), float("inf")
    x = np.asarray([point.wavenumber_cm1 for point in usable])
    edges = np.quantile(x, [0.0, 1 / 3, 2 / 3, 1.0])
    values = []
    for index in range(3):
        lo, hi = edges[index], edges[index + 1]
        subset = [
            point
            for point in usable
            if point.wavenumber_cm1 >= lo
            and (
                point.wavenumber_cm1 < hi
                if index < 2
                else point.wavenumber_cm1 <= hi
            )
        ]
        try:
            values.append(_fit_with_outlier_filter(subset)[0])
        except ValueError:
            values.append(float("nan"))
    array = np.asarray(values, dtype=float)
    finite = array[np.isfinite(array)]
    if len(finite) < 2:
        return tuple(float(value) for value in array), float("inf"), float("inf")
    cv = float(np.std(finite, ddof=1) / np.mean(finite) * 100.0)
    shift = float(
        np.max(np.abs(finite - full_thickness_um)) / full_thickness_um * 100.0
    )
    return tuple(float(value) for value in array), cv, shift


def _bootstrap_interval(
    points: list[MappedExtremum],
    repeats: int,
    seed: int,
) -> tuple[float, float]:
    if repeats < 2:
        return float("nan"), float("nan")
    usable = [point for point in points if point.eligible]
    groups: dict[str, list[MappedExtremum]] = {}
    for point in usable:
        groups.setdefault(point.sequence, []).append(point)
    rng = np.random.default_rng(seed)
    values = []
    for _ in range(repeats):
        sample = []
        for group in groups.values():
            indices = rng.integers(0, len(group), len(group))
            sample.extend(group[index] for index in indices)
        try:
            values.append(_fit_points(sample, robust=True)[0])
        except ValueError:
            continue
    if len(values) < max(10, repeats // 3):
        return float("nan"), float("nan")
    return tuple(float(value) for value in np.percentile(values, [2.5, 97.5]))


def fit_shared_thickness(
    mapped: list[MappedExtremum],
    bootstrap_repeats: int = 80,
    seed: int = 2025,
) -> SharedThicknessResult:
    """拟合共享厚度，并计算峰谷、角度、留段和重采样诊断。"""
    if not mapped:
        raise ValueError("色散坐标极值不能为空")
    materials = {point.material for point in mapped}
    scenarios = {point.scenario for point in mapped}
    if len(materials) != 1 or len(scenarios) != 1:
        raise ValueError("共享厚度拟合必须对应单一材料和单一情景")

    thickness, residual, usable, inlier = _fit_with_outlier_filter(mapped)
    residual_scale = float(
        1.4826
        * np.median(
            np.abs(residual[np.isfinite(residual)] - np.nanmedian(residual))
        )
    )
    updated_lookup = {
        (point.dataset, point.kind, point.sample_index): (
            bool(keep),
            float(value),
        )
        for point, keep, value in zip(usable, inlier, residual)
    }
    updated_points = tuple(
        replace(
            point,
            inlier=updated_lookup.get(
                (point.dataset, point.kind, point.sample_index),
                (False, float("nan")),
            )[0],
            residual_order=updated_lookup.get(
                (point.dataset, point.kind, point.sample_index),
                (False, float("nan")),
            )[1],
        )
        for point in mapped
    )

    peak = _subset_thickness(mapped, kind="peak")
    valley = _subset_thickness(mapped, kind="valley")
    angle_10 = _subset_thickness(mapped, angle=10.0)
    angle_15 = _subset_thickness(mapped, angle=15.0)
    peak_valley_diff = _relative_difference(peak, valley)
    angle_diff = _relative_difference(angle_10, angle_15)
    bands, band_cv, max_shift = _band_stability(mapped, thickness)
    ci_low, ci_high = _bootstrap_interval(mapped, bootstrap_repeats, seed)
    total = len(usable)
    inlier_count = int(np.count_nonzero(inlier))
    rejected = total - inlier_count
    rejected_fraction = float(rejected / total) if total else 1.0

    failures = []
    if peak_valley_diff > V8_THRESHOLDS["peak_valley_diff_pct"]:
        failures.append("峰谷厚度相对差超过 1.5%")
    if angle_diff > V8_THRESHOLDS["angle_diff_pct"]:
        failures.append("双角度厚度相对差超过 2%")
    if band_cv > V8_THRESHOLDS["band_cv_pct"]:
        failures.append("连续波段厚度 CV 超过 2%")
    if max_shift > V8_THRESHOLDS["max_band_shift_pct"]:
        failures.append("连续波段最大偏移超过 3%")
    if inlier_count < V8_THRESHOLDS["minimum_inliers"]:
        failures.append("有效极值少于 12")
    if rejected_fraction > V8_THRESHOLDS["maximum_rejected_fraction"]:
        failures.append("极值剔除比例超过 20%")

    return SharedThicknessResult(
        material=next(iter(materials)),
        scenario=next(iter(scenarios)),
        thickness_um=thickness,
        peak_only_um=peak,
        valley_only_um=valley,
        angle_10_um=angle_10,
        angle_15_um=angle_15,
        peak_valley_diff_pct=peak_valley_diff,
        angle_diff_pct=angle_diff,
        residual_scale_order=residual_scale,
        total_eligible=total,
        inlier_count=inlier_count,
        rejected_extrema=rejected,
        rejected_fraction=rejected_fraction,
        bootstrap_ci95_low_um=ci_low,
        bootstrap_ci95_high_um=ci_high,
        band_thicknesses_um=bands,
        band_cv_pct=band_cv,
        max_band_shift_pct=max_shift,
        stable=not failures,
        failure_reason="；".join(failures),
        points=updated_points,
    )

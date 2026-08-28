"""v8 极值波数到色散相位坐标的映射与漏级恢复。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace

import numpy as np

from band_eligibility import BandEligibility
from dispersion import CARRIER_SCENARIOS_CM3
from extrema_observation import ExtremumObservation
from preprocess import ProcessedSpectrum
from two_beam import TwoBeamResult


@dataclass(frozen=True)
class MappedExtremum:
    dataset: str
    material: str
    scenario: str
    angle_deg: float
    kind: str
    order_local: int
    order_recovered: int
    sample_index: int
    wavenumber_cm1: float
    g_cm1: float
    n_real: float
    extinction_k: float
    quality_weight: float
    eligible: bool
    inlier: bool = True
    residual_order: float = float("nan")

    @property
    def sequence(self) -> str:
        return f"{self.dataset}:{self.kind}"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class DispersionExtremaMaterialResult:
    material: str
    nominal_thickness_um: float
    statistical_ci95_low_um: float
    statistical_ci95_high_um: float
    systematic_low_um: float
    systematic_high_um: float
    peak_valley_diff_pct: float
    angle_diff_pct: float
    band_cv_pct: float
    max_band_shift_pct: float
    inlier_count: int
    stable: bool
    adopted: bool
    fallback_reason: str
    scenario_results: tuple[object, ...]
    observations: tuple[ExtremumObservation, ...]

    def to_dict(self, include_points: bool = False) -> dict:
        payload = asdict(self)
        payload["scenario_results"] = [
            result.to_dict(include_points=include_points)
            for result in self.scenario_results
        ]
        payload["observations"] = [
            observation.to_dict() for observation in self.observations
        ]
        return payload


def _recover_sequence_orders(
    points: list[MappedExtremum],
) -> list[MappedExtremum]:
    eligible = sorted(
        [point for point in points if point.eligible],
        key=lambda point: point.g_cm1,
    )
    if len(eligible) < 2:
        return points
    differences = np.diff([point.g_cm1 for point in eligible])
    positive = differences[differences > 0]
    if len(positive) == 0:
        return [replace(point, eligible=False, order_recovered=-1) for point in points]
    typical = float(np.median(positive))
    orders = [0]
    for difference in differences:
        gap = max(1, int(round(float(difference) / typical)))
        orders.append(orders[-1] + gap)
    lookup = {
        point.sample_index: order for point, order in zip(eligible, orders)
    }
    return [
        replace(point, order_recovered=lookup.get(point.sample_index, -1))
        for point in points
    ]


def map_extrema_to_scenario(
    observations: list[ExtremumObservation],
    eligibilities: dict[str, BandEligibility],
    scenario: str,
) -> list[MappedExtremum]:
    """映射极值到 g 坐标，并按数据集×峰谷恢复允许跳跃的局部级次。"""
    mapped = []
    for observation in observations:
        if observation.dataset not in eligibilities:
            raise ValueError(f"缺少 {observation.dataset} 的波段资格结果")
        eligibility = eligibilities[observation.dataset]
        index = observation.sample_index
        if index < 0 or index >= len(eligibility.mask):
            raise ValueError("极值样本索引超出色散坐标范围")
        mapped.append(
            MappedExtremum(
                dataset=observation.dataset,
                material=observation.material,
                scenario=scenario,
                angle_deg=observation.angle_deg,
                kind=observation.kind,
                order_local=observation.order_local,
                order_recovered=-1,
                sample_index=index,
                wavenumber_cm1=observation.wavenumber_cm1,
                g_cm1=float(eligibility.phase_coordinate_cm1[index]),
                n_real=float(eligibility.n_real[index]),
                extinction_k=float(eligibility.extinction_k[index]),
                quality_weight=float(observation.quality_weight),
                eligible=bool(
                    eligibility.qualified
                    and eligibility.mask[index]
                    and not observation.edge_flag
                ),
            )
        )

    result = []
    sequences = sorted({(point.dataset, point.kind) for point in mapped})
    for dataset, kind in sequences:
        sequence = [
            point
            for point in mapped
            if point.dataset == dataset and point.kind == kind
        ]
        result.extend(_recover_sequence_orders(sequence))
    return sorted(
        result,
        key=lambda point: (point.dataset, point.kind, point.wavenumber_cm1),
    )


def fit_dispersion_extrema_scenarios(
    spectra: list[ProcessedSpectrum],
    two_results: list[TwoBeamResult],
    material: str,
    constant_reference_um: float,
    bootstrap_repeats: int = 80,
) -> DispersionExtremaMaterialResult:
    """执行 intrinsic/low/medium/high 四情景的色散坐标极值反演。"""
    from band_eligibility import evaluate_band_eligibility
    from extrema_observation import observe_extrema
    from shared_thickness import fit_shared_thickness

    if len(spectra) < 2 or len(spectra) != len(two_results):
        raise ValueError("v8 每种材料至少需要两个角度及对应 L0 结果")
    observations = [
        observation
        for processed, two in zip(spectra, two_results)
        for observation in observe_extrema(processed, two)
    ]
    definitions = [("intrinsic", "intrinsic", 0.0, 0.0)]
    definitions.extend(
        (name, "fixed_carrier", epi, substrate)
        for name, (epi, substrate) in CARRIER_SCENARIOS_CM3[material].items()
    )
    results = []
    for scenario_index, (name, mode, epi, _) in enumerate(definitions):
        eligibilities = {
            processed.source.spec.key: evaluate_band_eligibility(
                processed,
                material,
                name,
                mode,
                epi,
            )
            for processed in spectra
        }
        mapped = map_extrema_to_scenario(observations, eligibilities, name)
        results.append(
            fit_shared_thickness(
                mapped,
                bootstrap_repeats=bootstrap_repeats,
                seed=2025 + scenario_index,
            )
        )
    nominal = results[0]
    stable_values = [result.thickness_um for result in results if result.stable]
    envelope = [constant_reference_um, *stable_values]
    fallback = nominal.failure_reason if not nominal.stable else ""
    return DispersionExtremaMaterialResult(
        material=material,
        nominal_thickness_um=nominal.thickness_um,
        statistical_ci95_low_um=nominal.bootstrap_ci95_low_um,
        statistical_ci95_high_um=nominal.bootstrap_ci95_high_um,
        systematic_low_um=float(np.min(envelope)),
        systematic_high_um=float(np.max(envelope)),
        peak_valley_diff_pct=nominal.peak_valley_diff_pct,
        angle_diff_pct=nominal.angle_diff_pct,
        band_cv_pct=nominal.band_cv_pct,
        max_band_shift_pct=nominal.max_band_shift_pct,
        inlier_count=nominal.inlier_count,
        stable=nominal.stable,
        adopted=nominal.stable,
        fallback_reason=fallback,
        scenario_results=tuple(results),
        observations=tuple(observations),
    )

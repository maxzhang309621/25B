"""将现有峰谷检测结果统一为 v8 可审计观测对象。"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
from scipy.signal import peak_prominences, peak_widths

from preprocess import ProcessedSpectrum
from two_beam import TwoBeamResult


@dataclass(frozen=True)
class ExtremumObservation:
    dataset: str
    material: str
    angle_deg: float
    kind: str
    order_local: int
    sample_index: int
    wavenumber_cm1: float
    prominence_pct: float
    width_cm1: float
    edge_flag: bool
    quality_weight: float

    def to_dict(self) -> dict:
        return asdict(self)


def _kind_observations(
    processed: ProcessedSpectrum,
    indices: np.ndarray,
    kind: str,
) -> list[ExtremumObservation]:
    indices = np.asarray(indices, dtype=int)
    if len(indices) == 0:
        return []
    signal = processed.residual_pct if kind == "peak" else -processed.residual_pct
    prominences = peak_prominences(signal, indices)[0]
    widths = peak_widths(signal, indices, rel_height=0.5)[0] * processed.spacing_cm1
    scale = max(float(np.median(prominences)), 1e-6)
    edge_samples = max(1, int(round(70.0 / processed.spacing_cm1)))
    result = []
    for order, (index, prominence, width) in enumerate(
        zip(indices, prominences, widths)
    ):
        edge = bool(
            index < edge_samples or index >= len(processed.wavenumber_cm1) - edge_samples
        )
        quality = float(np.clip(prominence / scale, 0.25, 4.0))
        if edge:
            quality *= 0.25
        result.append(
            ExtremumObservation(
                dataset=processed.source.spec.key,
                material=processed.source.spec.material,
                angle_deg=float(processed.source.spec.angle_deg),
                kind=kind,
                order_local=order,
                sample_index=int(index),
                wavenumber_cm1=float(processed.wavenumber_cm1[index]),
                prominence_pct=float(prominence),
                width_cm1=float(width),
                edge_flag=edge,
                quality_weight=quality,
            )
        )
    return result


def observe_extrema(
    processed: ProcessedSpectrum,
    two_result: TwoBeamResult,
) -> list[ExtremumObservation]:
    """复用 L0 峰谷位置并补充显著度、宽度和质量权重。"""
    observations = _kind_observations(
        processed,
        two_result.peak_indices,
        "peak",
    )
    observations.extend(
        _kind_observations(
            processed,
            two_result.valley_indices,
            "valley",
        )
    )
    return observations

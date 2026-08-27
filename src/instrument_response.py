"""反射率数据资格审查与受约束仪器响应。"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

from preprocess import ProcessedSpectrum


@dataclass
class ReflectanceQualification:
    mode: str
    out_of_range_fraction: float
    minimum_pct: float
    maximum_pct: float
    per_spectrum_out_of_range_fraction: dict[str, float]
    absolute_concentration_allowed: bool
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


def qualify_reflectance(
    spectra: list[ProcessedSpectrum],
    maximum_out_of_range_fraction: float = 0.005,
) -> ReflectanceQualification:
    """判断附件能否支持绝对反射率浓度解释。"""
    if not spectra:
        raise ValueError("反射率资格审查至少需要一条光谱")
    values = np.concatenate([spectrum.source.reflectance_pct for spectrum in spectra])
    if np.any(~np.isfinite(values)):
        raise ValueError("反射率必须为有限值")
    fractions = {
        spectrum.source.spec.key: float(
            np.mean(
                (spectrum.source.reflectance_pct < 0.0)
                | (spectrum.source.reflectance_pct > 100.0)
            )
        )
        for spectrum in spectra
    }
    fraction = max(fractions.values())
    absolute = fraction <= maximum_out_of_range_fraction
    reason = (
        ""
        if absolute
        else f"物理范围外反射率占比 {fraction:.2%}，超过 {maximum_out_of_range_fraction:.2%}"
    )
    return ReflectanceQualification(
        mode="absolute" if absolute else "relative_shape",
        out_of_range_fraction=fraction,
        minimum_pct=float(np.min(values)),
        maximum_pct=float(np.max(values)),
        per_spectrum_out_of_range_fraction=fractions,
        absolute_concentration_allowed=absolute,
        reason=reason,
    )


def carrier_spectral_weights(material: str, wavenumber_cm1: np.ndarray) -> np.ndarray:
    """厚度/浓度双通道权重；二声子区降权但不删除。"""
    x = np.asarray(wavenumber_cm1, dtype=float)
    if np.any(~np.isfinite(x)) or np.any(x <= 0):
        raise ValueError("波数必须为有限正数")
    weights = np.ones_like(x)
    if material == "SiC":
        weights[(x >= 700.0) & (x <= 1200.0)] = 2.5
        weights[(x >= 1300.0) & (x <= 1600.0)] = 0.35
    elif material == "Si":
        weights[x <= 1200.0] = 2.0
    else:
        raise ValueError(f"不支持的材料：{material}")
    return weights


def instrument_prediction(
    physical_reflectance: np.ndarray,
    wavenumber_cm1: np.ndarray,
    gain: float,
    offset_pct: float,
    shared_slope_pct: float,
) -> np.ndarray:
    """有界参数对应的仪器响应：角度增益/偏置 + 两角度共享漂移。"""
    physical = np.asarray(physical_reflectance, dtype=float)
    x = np.asarray(wavenumber_cm1, dtype=float)
    if physical.shape != x.shape:
        raise ValueError("物理反射率与波数数组形状必须一致")
    z = (x - x.mean()) / np.ptp(x)
    return offset_pct + 100.0 * gain * physical + shared_slope_pct * z

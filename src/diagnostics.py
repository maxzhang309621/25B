"""双光束与多光束模型的证据合并诊断。"""

from dataclasses import dataclass

import numpy as np

from multi_beam import MultiBeamResult
from optics import refracted_cosine
from preprocess import ProcessedSpectrum
from two_beam import TwoBeamResult


@dataclass
class MultiBeamDiagnostic:
    harmonic_ratio: float
    delta_aicc: float
    rmse_improvement_pct: float
    reflectivity_support: bool
    harmonic_support: bool
    model_support: bool
    observable_multibeam: bool


def _local_fft_amplitude(
    frequency: np.ndarray, spectrum: np.ndarray, target: float
) -> float:
    if target <= 0:
        return 0.0
    half_width = max(target * 0.08, frequency[1] - frequency[0])
    mask = np.abs(frequency - target) <= half_width
    return float(np.max(spectrum[mask])) if np.any(mask) else 0.0


def diagnose_multibeam(
    processed: ProcessedSpectrum,
    two: TwoBeamResult,
    multi: MultiBeamResult,
) -> MultiBeamDiagnostic:
    spec = processed.source.spec
    ncos = spec.refractive_index * float(
        refracted_cosine(spec.refractive_index, spec.angle_deg)
    )
    fundamental = 2.0 * ncos * two.thickness_refined_um * 1e-4
    tapered = (processed.residual_pct - processed.residual_pct.mean()) * np.hanning(
        len(processed.residual_pct)
    )
    amplitude = np.abs(np.fft.rfft(tapered))
    frequency = np.fft.rfftfreq(len(tapered), processed.spacing_cm1)
    first = _local_fft_amplitude(frequency, amplitude, fundamental)
    second = _local_fft_amplitude(frequency, amplitude, 2.0 * fundamental)
    harmonic_ratio = float(second / first) if first > 0 else 0.0

    delta_aicc = float(two.aicc - multi.aicc)
    improvement = float(100.0 * (two.rmse_pct - multi.rmse_pct) / two.rmse_pct)
    reflectivity_support = multi.effective_reflectivity >= 0.12
    harmonic_support = harmonic_ratio >= 0.08
    model_support = delta_aicc >= 10.0 and improvement >= 2.0
    # 有效反射率可被未建模基线“吸收”，不能单独作为多光束证据；
    # 必须同时观察到高次谐波和模型改善。
    observable = bool(model_support and reflectivity_support and harmonic_support)
    return MultiBeamDiagnostic(
        harmonic_ratio,
        delta_aicc,
        improvement,
        reflectivity_support,
        harmonic_support,
        model_support,
        observable,
    )

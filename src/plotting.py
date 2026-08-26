"""论文用诊断图。"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from multi_beam import MultiBeamResult
from preprocess import ProcessedSpectrum
from two_beam import TwoBeamResult


def plot_spectrum_fit(
    processed: ProcessedSpectrum,
    two: TwoBeamResult,
    multi: MultiBeamResult,
    path: Path,
) -> None:
    x = processed.wavenumber_cm1
    fig, axes = plt.subplots(3, 1, figsize=(11, 9), sharex=True)
    axes[0].plot(x, processed.reflectance_pct, color="0.55", lw=0.7, label="measured")
    axes[0].plot(x, processed.smooth_pct, color="tab:blue", lw=1.0, label="smoothed")
    axes[0].plot(x, processed.baseline_pct, color="tab:orange", lw=1.0, label="baseline")
    axes[0].set_ylabel("Reflectance (%)")
    axes[0].legend(loc="best")

    axes[1].plot(x, processed.residual_pct, color="0.65", lw=0.8, label="detrended")
    axes[1].plot(x, two.fitted_residual, lw=1.0, label="two-beam")
    axes[1].plot(x, multi.fitted_residual, lw=1.0, label="multi-beam")
    axes[1].scatter(
        x[two.peak_indices],
        processed.residual_pct[two.peak_indices],
        s=13,
        color="tab:red",
        label="peaks",
    )
    axes[1].set_ylabel("Residual (%)")
    axes[1].legend(loc="best", ncol=4)

    axes[2].plot(
        x,
        processed.residual_pct - two.fitted_residual,
        lw=0.7,
        label="two-beam residual",
    )
    axes[2].plot(
        x,
        processed.residual_pct - multi.fitted_residual,
        lw=0.7,
        label="multi-beam residual",
    )
    axes[2].axhline(0, color="black", lw=0.5)
    axes[2].set_xlabel(r"Wavenumber (cm$^{-1}$)")
    axes[2].set_ylabel("Fit error (%)")
    axes[2].legend(loc="best")
    fig.suptitle(
        f"{processed.source.spec.material}, {processed.source.spec.angle_deg:g} deg"
    )
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=180)
    plt.close(fig)

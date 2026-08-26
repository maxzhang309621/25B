"""核心公式、合成数据与附件读取测试。"""

import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from config import DATASETS, DATA_DIR
from data_io import Spectrum, load_spectrum
from optics import (
    airy_normalized,
    fresnel_reflectance_air_film,
    refracted_cosine,
    round_trip_phase,
    thickness_from_fringe_spacing,
)
from plotting import plot_summary_figures
from preprocess import ProcessedSpectrum
from two_beam import estimate_two_beam


class OpticsTests(unittest.TestCase):
    def test_snell_cosine_is_physical(self):
        cosine = float(refracted_cosine(2.55, 15.0))
        self.assertGreater(cosine, np.cos(np.deg2rad(15.0)))
        self.assertLessEqual(cosine, 1.0)

    def test_spacing_inverse_recovers_thickness(self):
        n, angle, thickness = 2.55, 10.0, 8.0
        ncos = n * float(refracted_cosine(n, angle))
        spacing = 1e4 / (2 * ncos * thickness)
        recovered = thickness_from_fringe_spacing(spacing, n, angle)
        self.assertAlmostEqual(recovered, thickness, places=10)

    def test_airy_bounds_and_fresnel(self):
        rs, rp = fresnel_reflectance_air_film(3.42, 10.0)
        self.assertTrue(0 < rs < 1 and 0 < rp < 1)
        values = airy_normalized(np.linspace(0, 4 * np.pi, 100), (rs + rp) / 2)
        self.assertTrue(np.all((values >= 0) & (values <= 1)))

    def test_invalid_physical_inputs_raise(self):
        with self.assertRaises(ValueError):
            thickness_from_fringe_spacing(0.0, 2.55, 10.0)
        with self.assertRaises(ValueError):
            refracted_cosine(-1.0, 10.0)
        with self.assertRaises(ValueError):
            round_trip_phase(np.array([1000.0]), -2.0, 2.55, 10.0)


class InversionTests(unittest.TestCase):
    def test_synthetic_two_beam_error_below_two_percent(self):
        spec = DATASETS[0]
        x = np.arange(1100.0, 4000.0, 0.5)
        true_um = 8.0
        phase = round_trip_phase(x, true_um, spec.refractive_index, spec.angle_deg)
        rng = np.random.default_rng(7)
        residual = (1.5 - 0.25 * (x - x.mean()) / np.ptp(x)) * np.cos(phase + 0.4)
        residual += rng.normal(0, 0.05, len(x))
        source = Spectrum(x, 18 + residual, spec, {})
        processed = ProcessedSpectrum(
            x,
            18 + residual,
            18 + residual,
            np.full_like(x, 18.0),
            residual,
            0.5,
            source,
        )
        result = estimate_two_beam(processed)
        self.assertLess(abs(result.thickness_refined_um - true_um) / true_um, 0.02)

    def test_all_attachments_load(self):
        for spec in DATASETS:
            spectrum = load_spectrum(DATA_DIR, spec)
            self.assertGreater(len(spectrum.wavenumber_cm1), 7000)
            self.assertTrue(np.all(np.diff(spectrum.wavenumber_cm1) > 0))


class VisualizationTests(unittest.TestCase):
    def test_all_summary_figures_are_created(self):
        summary = pd.DataFrame(
            {
                "dataset": ["sic_10", "sic_15", "si_10", "si_15"],
                "material": ["SiC", "SiC", "Si", "Si"],
                "angle_deg": [10.0, 15.0, 10.0, 15.0],
                "two_beam_thickness_um": [7.90, 7.83, 3.41, 3.44],
                "multi_beam_thickness_um": [8.47, 8.46, 3.58, 3.55],
                "selected_thickness_um": [7.90, 7.83, 3.58, 3.55],
                "bootstrap_ci95_low_um": [7.64, 7.46, 3.23, 3.11],
                "bootstrap_ci95_high_um": [8.19, 8.24, 3.73, 3.90],
                "selected_model": ["two-beam", "two-beam", "multi-beam", "multi-beam"],
                "harmonic_ratio": [0.024, 0.048, 0.247, 0.253],
                "effective_reflectivity": [0.172, 0.142, 0.458, 0.463],
                "rmse_improvement_pct": [13.9, 12.3, 20.0, 18.7],
                "delta_aicc": [1796.0, 1579.0, 2778.0, 2570.0],
                "observable_multibeam": [False, False, True, True],
                "two_beam_rmse_pct": [0.51, 0.55, 1.23, 1.30],
                "multi_beam_rmse_pct": [0.44, 0.48, 0.98, 1.05],
            }
        )
        consistency = {
            "SiC": {
                "angle_relative_difference_pct": 0.96,
                "weighted_combined_thickness_um": 7.88,
            },
            "Si": {
                "angle_relative_difference_pct": 0.84,
                "weighted_combined_thickness_um": 3.57,
            },
        }
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            plot_summary_figures(summary, consistency, output)
            expected = {
                "thickness_comparison.png",
                "angle_consistency.png",
                "multibeam_evidence.png",
                "model_quality.png",
            }
            self.assertEqual({path.name for path in output.glob("*.png")}, expected)
            self.assertTrue(all((output / name).stat().st_size > 1000 for name in expected))


if __name__ == "__main__":
    unittest.main()

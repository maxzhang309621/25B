"""核心公式、合成数据与附件读取测试。"""

import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

_src = Path(__file__).resolve().parent
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

import importlib.util

_band_path = _src / "Candidate window" / "band_select.py"
_band_spec = importlib.util.spec_from_file_location("band_select", _band_path)
_band_select = importlib.util.module_from_spec(_band_spec)
sys.modules["band_select"] = _band_select
assert _band_spec.loader is not None
_band_spec.loader.exec_module(_band_select)
select_band = _band_select.select_band
score_band = _band_select.score_band

from config import DATASETS, DATA_DIR
from data_io import Spectrum, load_spectrum
from dispersion import (
    epsilon_4h_sic,
    epsilon_si,
    material_epsilon,
    material_refractive_index,
    si_intrinsic_n,
)
from joint_calibration import fit_joint_calibration
from optics import (
    airy_normalized,
    fresnel_reflectance_air_film,
    refracted_cosine,
    round_trip_phase,
    thin_film_reflectance,
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

    def test_si_zero_carrier_recovers_edwards_background(self):
        x = np.array([400.0, 1000.0, 2000.0, 4000.0])
        expected = si_intrinsic_n(x)
        actual = material_refractive_index("Si", x, 0.0)
        np.testing.assert_allclose(actual.real, expected, rtol=1e-12, atol=1e-12)
        np.testing.assert_allclose(actual.imag, 0.0, atol=1e-12)

    def test_complex_models_are_passive(self):
        x = np.linspace(700.0, 4000.0, 500)
        for epsilon in (epsilon_si(x, 1e18), epsilon_4h_sic(x, 1e18)):
            self.assertTrue(np.all(np.imag(epsilon) >= -1e-12))
        index = material_refractive_index("SiC", x, 1e18)
        self.assertTrue(np.all(np.imag(index) >= -1e-12))

    def test_equal_film_and_substrate_removes_thickness_dependence(self):
        x = np.linspace(1200.0, 4000.0, 300)
        epsilon = material_epsilon("SiC", x, 1e17)
        first = thin_film_reflectance(x, 1.0, 10.0, epsilon, epsilon)
        second = thin_film_reflectance(x, 20.0, 10.0, epsilon, epsilon)
        np.testing.assert_allclose(first, second, rtol=1e-10, atol=1e-10)
        self.assertTrue(np.all((first >= 0) & (first <= 1)))

    def test_invalid_dispersion_inputs_raise(self):
        with self.assertRaises(ValueError):
            material_epsilon("Si", np.array([1000.0]), -1.0)
        with self.assertRaises(ValueError):
            material_epsilon("unknown", np.array([1000.0]), 1e17)
        with self.assertRaises(ValueError):
            thin_film_reflectance(
                np.array([1000.0, 1100.0]),
                5.0,
                10.0,
                np.array([4.0 + 0j]),
                np.array([4.0 + 0j]),
            )


class BandSelectTests(unittest.TestCase):
    def test_select_band_prefers_low_spacing_mad(self):
        spec = DATASETS[0]
        x = np.arange(1100.0, 4000.0, 0.5)
        true_um = 8.0
        phase = round_trip_phase(x, true_um, spec.refractive_index, spec.angle_deg)
        rng = np.random.default_rng(11)
        residual = np.cos(phase + 0.2) + rng.normal(0, 0.02, len(x))
        source = Spectrum(x, 20 + residual, spec, {})
        selected, scores = select_band(source)
        selected_rows = [row for row in scores if row.selected]
        self.assertEqual(len(selected_rows), 1)
        self.assertEqual(selected, (selected_rows[0].lo, selected_rows[0].hi))
        self.assertGreaterEqual(selected_rows[0].extrema_count, 15)


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

    def test_joint_dispersion_recovers_synthetic_thickness(self):
        material = "SiC"
        true_thickness = 8.0
        epi_carrier, substrate_carrier = 1e17, 7.1e18
        spectra = []
        for spec in DATASETS[:2]:
            x = np.linspace(1200.0, 4000.0, 900)
            eps_epi = material_epsilon(material, x, epi_carrier)
            eps_sub = material_epsilon(material, x, substrate_carrier)
            reflectance = thin_film_reflectance(
                x, true_thickness, spec.angle_deg, eps_epi, eps_sub
            )
            z = (x - x.mean()) / np.ptp(x)
            y = 8.0 + 82.0 * reflectance + 0.3 * z
            baseline = np.full_like(x, float(np.mean(y)))
            source = Spectrum(x, y, spec, {})
            spectra.append(
                ProcessedSpectrum(
                    x,
                    y,
                    y,
                    baseline,
                    y - baseline,
                    float(np.median(np.diff(x))),
                    source,
                )
            )
        result = fit_joint_calibration(
            spectra, [true_thickness * 0.99, true_thickness * 1.01], material, 350
        )
        self.assertLess(
            abs(result.adopted_thickness_um - true_thickness) / true_thickness,
            0.02,
        )
        self.assertLessEqual(result.systematic_low_um, result.systematic_high_um)
        self.assertTrue(result.band_stable)

    def test_joint_calibration_requires_two_angles(self):
        spec = DATASETS[0]
        x = np.linspace(1200.0, 2000.0, 200)
        source = Spectrum(x, np.ones_like(x), spec, {})
        processed = ProcessedSpectrum(
            x,
            np.ones_like(x),
            np.ones_like(x),
            np.ones_like(x),
            np.zeros_like(x),
            float(np.median(np.diff(x))),
            source,
        )
        with self.assertRaises(ValueError):
            fit_joint_calibration([processed], [8.0], "SiC")


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

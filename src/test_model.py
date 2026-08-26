"""核心公式、合成数据与附件读取测试。"""

import unittest

import numpy as np

from config import DATASETS, DATA_DIR
from data_io import Spectrum, load_spectrum
from optics import (
    airy_normalized,
    fresnel_reflectance_air_film,
    refracted_cosine,
    round_trip_phase,
    thickness_from_fringe_spacing,
)
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


if __name__ == "__main__":
    unittest.main()

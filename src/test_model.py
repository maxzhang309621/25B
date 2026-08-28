"""核心公式、合成数据与附件读取测试。"""

import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd
from matplotlib.image import imread

_src = Path(__file__).resolve().parent
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

import importlib.util
import inspect

_band_path = _src / "Candidate window" / "band_select.py"
_band_spec = importlib.util.spec_from_file_location("band_select", _band_path)
_band_select = importlib.util.module_from_spec(_band_spec)
sys.modules["band_select"] = _band_select
assert _band_spec.loader is not None
_band_spec.loader.exec_module(_band_select)
select_band = _band_select.select_band
score_band = _band_select.score_band

from carrier_inference import CarrierInferenceResult, infer_carrier_concentrations
from band_eligibility import BandEligibility, evaluate_band_eligibility
from comparison_report import (
    build_dispersion_extrema_comparison,
    build_refractive_index_comparison,
)
from config import DATASETS, DATA_DIR
from data_io import Spectrum, load_spectrum
from dispersion import (
    epsilon_4h_sic,
    epsilon_si,
    material_epsilon,
    material_refractive_index,
    si_intrinsic_n,
)
from dispersion_extrema import (
    MappedExtremum,
    fit_dispersion_extrema_scenarios,
    map_extrema_to_scenario,
)
from extrema_observation import ExtremumObservation, observe_extrema
import evidence_plotting
from evidence_plotting import plot_analysis_evidence
from identifiability_audit import build_identifiability_audit
from intrinsic_scenario import (
    fit_intrinsic_scenarios,
    intrinsic_refractive_index_rows,
)
from joint_calibration import (
    JointCalibrationResult,
    ScenarioThickness,
    fit_joint_calibration,
)
from instrument_response import (
    carrier_spectral_weights,
    instrument_prediction,
    qualify_reflectance,
)
from model_flowchart import plot_model_flowchart
from optics import (
    airy_normalized,
    fresnel_reflectance_air_film,
    refracted_cosine,
    round_trip_phase,
    thin_film_reflectance,
    thickness_from_fringe_spacing,
)
from plotting import (
    plot_carrier_scenarios,
    plot_carrier_profiles,
    plot_dispersion_curves,
    plot_identifiability_diagnostics,
    plot_summary_figures,
)
from preprocess import ProcessedSpectrum
from raw_evidence_plotting import (
    plot_raw_dispersion_evidence,
    plot_raw_extrema_evidence,
    plot_raw_multibeam_evidence,
    plot_raw_v7_evidence,
)
from shared_thickness import fit_shared_thickness
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


class CarrierInferenceTests(unittest.TestCase):
    def test_sic_band_weights_keep_but_downweight_two_phonon_region(self):
        x = np.array([800.0, 1400.0, 2500.0])
        weights = carrier_spectral_weights("SiC", x)
        np.testing.assert_allclose(weights, [2.5, 0.35, 1.0])
        self.assertTrue(np.all(weights > 0))

    def test_instrument_response_formula_and_shape_validation(self):
        x = np.array([700.0, 950.0, 1200.0])
        physical = np.array([0.2, 0.4, 0.6])
        predicted = instrument_prediction(physical, x, 1.05, -1.0, 2.0)
        np.testing.assert_allclose(predicted, [19.0, 41.0, 63.0])
        with self.assertRaises(ValueError):
            instrument_prediction(physical[:2], x, 1.0, 0.0, 0.0)

    def test_invalid_carrier_band_material_raises(self):
        with self.assertRaises(ValueError):
            carrier_spectral_weights("unknown", np.array([1000.0]))

    def test_out_of_range_reflectance_forces_relative_shape_mode(self):
        spectra = []
        for spec in DATASETS[:2]:
            x = np.linspace(700.0, 1200.0, 200)
            y = np.linspace(20.0, 103.0 if spec.angle_deg == 15 else 90.0, len(x))
            source = Spectrum(x, y, spec, {})
            spectra.append(
                ProcessedSpectrum(x, y, y, y, np.zeros_like(y), x[1] - x[0], source)
            )
        qualification = qualify_reflectance(spectra)
        self.assertEqual(qualification.mode, "relative_shape")
        self.assertFalse(qualification.absolute_concentration_allowed)
        self.assertGreater(qualification.out_of_range_fraction, 0.005)

    def test_enhanced_inference_validates_angle_and_profile_grid(self):
        spec = DATASETS[0]
        x = np.linspace(700.0, 1200.0, 100)
        y = np.full_like(x, 50.0)
        source = Spectrum(x, y, spec, {})
        processed = ProcessedSpectrum(x, y, y, y, y - y, x[1] - x[0], source)
        with self.assertRaises(ValueError):
            infer_carrier_concentrations([processed], [8.0])
        with self.assertRaises(ValueError):
            infer_carrier_concentrations(
                [processed, processed], [8.0, 8.0], profile_grid_points=5
            )

    def test_enhanced_synthetic_inference_recovers_thickness_and_profiles(self):
        true_thickness = 8.0
        true_epi, true_substrate = 3e17, 3e18
        spectra = []
        rng = np.random.default_rng(23)
        for index, spec in enumerate(DATASETS[:2]):
            x = np.linspace(700.0, 2000.0, 500)
            physical = thin_film_reflectance(
                x,
                true_thickness,
                spec.angle_deg,
                material_epsilon("SiC", x, true_epi),
                material_epsilon("SiC", x, true_substrate),
            )
            z = (x - x.mean()) / np.ptp(x)
            y = (0.96 + 0.03 * index) * 100.0 * physical + 0.2 * z
            y += rng.normal(0.0, 0.04, len(x))
            source = Spectrum(x, y, spec, {})
            spectra.append(
                ProcessedSpectrum(
                    x,
                    y,
                    y,
                    np.full_like(x, np.mean(y)),
                    y - np.mean(y),
                    float(np.median(np.diff(x))),
                    source,
                )
            )
        result, rows = infer_carrier_concentrations(
            spectra,
            [7.95, 8.05],
            material="SiC",
            profile_grid_points=9,
            max_points_per_spectrum=180,
        )
        self.assertLess(abs(result.candidate_thickness_um - true_thickness) / true_thickness, 0.02)
        self.assertIsNotNone(result.epi_log10_ci90)
        self.assertIsNotNone(result.substrate_log10_ci90)
        self.assertGreaterEqual(len(rows), 18)
        self.assertLess(
            abs(np.log10(result.candidate_epi_carrier_cm3) - np.log10(true_epi)),
            0.3,
        )
        self.assertLessEqual(
            result.epi_log10_ci90[0],
            np.log10(result.candidate_epi_carrier_cm3),
        )
        self.assertGreaterEqual(
            result.epi_log10_ci90[1],
            np.log10(result.candidate_epi_carrier_cm3),
        )


class VisualizationTests(unittest.TestCase):
    def test_summary_dispersion_outputs_use_explicit_file_paths(self):
        source = inspect.getsource(plot_summary_figures)
        for filename in (
            "dispersion_curves.png",
            "carrier_scenarios.png",
            "identifiability_diagnostics.png",
            "carrier_profiles.png",
        ):
            self.assertIn(filename, source)

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
                "thickness_comparison_sic.png",
                "thickness_comparison_si.png",
                "angle_consistency_sic.png",
                "angle_consistency_si.png",
                "multibeam_evidence.png",
                "multibeam_evidence_sic.png",
                "model_quality_rmse.png",
                "model_quality_improvement.png",
            }
            self.assertEqual({path.name for path in output.glob("*.png")}, expected)
            self.assertTrue(all((output / name).stat().st_size > 1000 for name in expected))
            x = np.linspace(1100.0, 4000.0, 1800)
            residual = np.cos(2 * np.pi * x / 75.0)
            source = Spectrum(
                x,
                20.0 + residual,
                DATASETS[0],
                {},
            )
            processed = ProcessedSpectrum(
                x,
                20.0 + residual,
                20.0 + residual,
                np.full_like(x, 20.0),
                residual,
                float(np.median(np.diff(x))),
                source,
            )
            two = estimate_two_beam(processed)
            raw_dir = output / "raw_evidence" / "multibeam"
            plot_raw_multibeam_evidence(
                summary,
                [
                    (dataset, processed, two)
                    for dataset in summary["dataset"].tolist()
                ],
                raw_dir,
            )
            raw_paths = list(raw_dir.glob("*.png"))
            self.assertEqual(len(raw_paths), 8)
            self.assertTrue(all(path.stat().st_size > 1000 for path in raw_paths))
            self.assertTrue(all(imread(path).shape[1] >= 1800 for path in raw_paths))

    def test_dispersion_and_flowchart_figures_are_created(self):
        x = np.linspace(700.0, 4000.0, 30)
        curves = pd.concat(
            [
                pd.DataFrame(
                    {
                        "material": material,
                        "wavenumber_cm1": x,
                        "n_epi": base + 0.03 * np.sin(x / 400),
                        "k_epi": 0.01 + 0.005 * np.cos(x / 500),
                        "n_substrate": base + 0.05 * np.sin(x / 450),
                        "k_substrate": 0.02 + 0.006 * np.cos(x / 550),
                    }
                )
                for material, base in (("SiC", 2.55), ("Si", 3.42))
            ],
            ignore_index=True,
        )
        results = {}
        for material, adopted, stable, boundary in (
            ("SiC", 7.84, False, False),
            ("Si", 3.41, True, True),
        ):
            results[material] = {
                "adopted_thickness_um": adopted,
                "fitted_thickness_um": adopted * 0.99,
                "rmse_pct": 1.5,
                "band_thicknesses_um": [
                    adopted * 0.99,
                    adopted,
                    adopted * 1.01,
                ],
                "band_cv_pct": 0.8 if stable else 8.7,
                "max_band_shift_pct": 1.0 if stable else 15.0,
                "band_stable": stable,
                "boundary_hit": boundary,
                "concentration_identifiable": False,
                "adopted_basis": "固定掺杂情景" if stable else "回退常折射率基线",
                "scenarios": [
                    {
                        "name": name,
                        "epi_carrier_cm3": epi,
                        "substrate_carrier_cm3": substrate,
                        "thickness_um": adopted * factor,
                        "rmse_pct": rmse,
                    }
                    for name, epi, substrate, factor, rmse in (
                        ("low", 1e15, 3e17, 0.95, 2.0),
                        ("medium", 1e17, 7e18, 1.0, 1.5),
                        ("high", 1e18, 2e19, 1.05, 2.5),
                    )
                ],
            }
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            paths = [
                output / "dispersion_curves.png",
                output / "carrier_scenarios.png",
                output / "identifiability_diagnostics.png",
                output / "model_flowchart.png",
                output / "carrier_profile.png",
            ]
            plot_dispersion_curves(curves, paths[0])
            plot_carrier_scenarios(results, paths[1])
            plot_identifiability_diagnostics(results, paths[2])
            plot_model_flowchart(paths[3])
            profile = pd.DataFrame(
                {
                    "target": ["epi"] * 9 + ["substrate"] * 9,
                    "log10_carrier_cm3": np.r_[
                        np.linspace(15, 18, 9), np.linspace(17, 19, 9)
                    ],
                    "delta_objective": np.r_[
                        (np.linspace(15, 18, 9) - 17) ** 2 * 6,
                        (np.linspace(17, 19, 9) - 18.5) ** 2 * 6,
                    ],
                }
            )
            plot_carrier_profiles(
                profile,
                {
                    "measurement_mode": "relative_shape",
                    "identifiability_level": "conditional_dual",
                    "epi_log10_ci90": [16.7, 17.3],
                    "substrate_log10_ci90": [18.2, 18.8],
                },
                paths[4],
            )
            raw_dir = output / "raw_evidence" / "dispersion"
            plot_raw_dispersion_evidence(curves, results, profile, raw_dir)
            raw_paths = list(raw_dir.glob("*.png"))
            self.assertEqual(len(raw_paths), 9)
            self.assertTrue(all(path.stat().st_size > 1000 for path in raw_paths))
            self.assertTrue(all(imread(path).shape[1] >= 1800 for path in raw_paths))
            self.assertTrue(all(path.stat().st_size > 1000 for path in paths))
            self.assertTrue(all(imread(path).shape[1] >= 1800 for path in paths))


class V7IntrinsicScenarioTests(unittest.TestCase):
    @staticmethod
    def _synthetic_sic_inputs():
        x = np.linspace(1200.0, 4000.0, 1200)
        spectra = []
        thickness = 8.0
        for spec in DATASETS[:2]:
            index = material_refractive_index("SiC", x, mode="intrinsic")
            sin0 = np.sin(np.deg2rad(spec.angle_deg))
            optical = np.sqrt(index.real**2 - sin0**2)
            phase = 4 * np.pi * thickness * 1e-4 * x * optical
            residual = 0.8 * np.cos(phase + 0.25)
            source = Spectrum(x, 20.0 + residual, spec, {})
            spectra.append(
                ProcessedSpectrum(
                    x,
                    20.0 + residual,
                    20.0 + residual,
                    np.full_like(x, 20.0),
                    residual,
                    float(np.median(np.diff(x))),
                    source,
                )
            )
        return spectra

    @staticmethod
    def _audit_objects():
        scenarios = [
            ScenarioThickness("low", 1e15, 3e17, 7.2, 1.3),
            ScenarioThickness("medium", 1e17, 7.1e18, 7.15, 2.7),
            ScenarioThickness("high", 3e18, 2e19, 8.33, 4.3),
        ]
        joint = JointCalibrationResult(
            material="SiC",
            fitted_thickness_um=7.72,
            adopted_thickness_um=7.83,
            epi_carrier_cm3=1.1e17,
            substrate_carrier_cm3=3.5e18,
            rmse_pct=1.52,
            jacobian_condition=9.9,
            max_parameter_correlation=0.38,
            concentration_identifiable=False,
            boundary_hit=False,
            adopted_basis="回退常折射率基线",
            systematic_low_um=7.15,
            systematic_high_um=8.33,
            band_thicknesses_um=[7.0, 8.28, 7.99],
            band_cv_pct=8.69,
            max_band_shift_pct=14.99,
            band_stable=False,
            scenarios=scenarios,
            model="test",
            references=("test",),
            fallback_reason="连续波段厚度稳定性未通过",
        )
        carrier = CarrierInferenceResult(
            material="SiC",
            measurement_mode="relative_shape",
            qualification={
                "absolute_concentration_allowed": False,
                "reason": "反射率超界",
            },
            identifiability_level="bounded_scenario",
            candidate_thickness_um=7.60,
            candidate_epi_carrier_cm3=6.5e17,
            candidate_substrate_carrier_cm3=2.1e18,
            reported_epi_carrier_cm3=None,
            reported_substrate_carrier_cm3=None,
            epi_log10_ci90=(17.69, 17.87),
            substrate_log10_ci90=(17.48, 18.32),
            epi_ci90_cm3=(4.9e17, 7.4e17),
            substrate_ci90_cm3=(3e17, 2.1e18),
            epi_interval_boundary_hit=False,
            substrate_interval_boundary_hit=True,
            thickness_boundary_hit=True,
            carrier_correlation=0.08,
            fixed_scenario_improvement_pct=2.76,
            gains=(0.97, 1.05),
            offsets_pct=(0.16, -0.44),
            shared_slope_pct=-0.18,
            objective=10603.0,
            fallback_reason="资格与轮廓门控未通过",
            informative_bands_cm1=((700.0, 1200.0), (1200.0, 4000.0)),
        )
        return joint, carrier

    def test_dispersion_modes_are_explicit_and_backward_compatible(self):
        x = np.array([1200.0, 2000.0, 3500.0])
        intrinsic = material_epsilon("SiC", x, 1e18, mode="intrinsic")
        zero = material_epsilon("SiC", x, 0.0)
        np.testing.assert_allclose(intrinsic, zero)
        fixed = material_epsilon("SiC", x, 1e18, mode="fixed_carrier")
        legacy = material_epsilon("SiC", x, 1e18)
        np.testing.assert_allclose(fixed, legacy)

    def test_invalid_dispersion_mode_raises(self):
        with self.assertRaises(ValueError):
            material_epsilon("SiC", np.array([1200.0]), mode="free")

    def test_intrinsic_scenarios_recover_synthetic_thickness(self):
        result = fit_intrinsic_scenarios(
            self._synthetic_sic_inputs(),
            [8.0, 8.0],
            "SiC",
        )
        self.assertEqual([item.name for item in result.scenarios], ["intrinsic", "low", "medium", "high"])
        self.assertAlmostEqual(result.intrinsic_thickness_um, 8.0, places=2)
        self.assertLessEqual(result.intrinsic_systematic_low_um, 8.0)
        self.assertGreaterEqual(result.intrinsic_systematic_high_um, 8.0)
        referenced = fit_intrinsic_scenarios(
            self._synthetic_sic_inputs(),
            [8.0, 8.0],
            "SiC",
            constant_reference_um=8.1,
        )
        self.assertEqual(referenced.primary_thickness_um, 8.1)
        self.assertGreaterEqual(referenced.intrinsic_systematic_high_um, 8.1)

    def test_intrinsic_curve_export_contains_all_scenarios(self):
        result = fit_intrinsic_scenarios(
            self._synthetic_sic_inputs(),
            [8.0, 8.0],
            "SiC",
        )
        rows = intrinsic_refractive_index_rows(
            "SiC",
            result,
            np.linspace(1200.0, 4000.0, 12),
        )
        self.assertEqual(len(rows), 48)
        self.assertEqual({row["scenario"] for row in rows}, {"intrinsic", "low", "medium", "high"})
        self.assertTrue(all(row["n_epi"] > 0 for row in rows))

    def test_audit_preserves_numeric_failure_evidence(self):
        joint, carrier = self._audit_objects()
        audit = build_identifiability_audit({"SiC": joint}, carrier)
        evidence = audit["materials"]["SiC"]["joint_calibration"]
        self.assertFalse(evidence["concentration_identifiable"])
        self.assertFalse(evidence["checks"]["band_cv_pct"]["passed"])
        self.assertFalse(evidence["checks"]["max_band_shift_pct"]["passed"])
        enhanced = audit["materials"]["SiC"]["enhanced_carrier_inference"]
        self.assertFalse(enhanced["point_estimate_reported"])
        self.assertGreaterEqual(len(enhanced["failure_reasons"]), 3)

    def test_comparison_never_overrides_primary_track(self):
        spectra = self._synthetic_sic_inputs()
        intrinsic = fit_intrinsic_scenarios(spectra, [8.0, 8.0], "SiC")
        joint, carrier = self._audit_objects()
        audit = build_identifiability_audit({"SiC": joint}, carrier)
        summary = pd.DataFrame(
            {
                "material": ["SiC", "SiC"],
                "angle_deg": [10.0, 15.0],
                "selected_model": ["two-beam", "two-beam"],
                "selected_thickness_um": [7.88, 7.79],
                "bootstrap_std_um": [0.15, 0.13],
            }
        )
        comparison = build_refractive_index_comparison(
            summary,
            {"SiC": intrinsic},
            audit,
        )
        material = comparison["materials"]["SiC"]
        self.assertEqual(material["decision"]["primary_track"], "track0_primary")
        self.assertTrue(material["track0_primary"]["adopted_for_paper"])
        self.assertEqual(
            material["track1_intrinsic_systematic"]["adopted_for_paper"],
            "systematic_only",
        )

    def test_v7_raw_evidence_figures_are_created(self):
        result = fit_intrinsic_scenarios(
            self._synthetic_sic_inputs(),
            [8.0, 8.0],
            "SiC",
        )
        # 绘图接口需要两种材料；复用同一结构只用于输出契约测试。
        payload = {"SiC": result.to_dict(), "Si": result.to_dict()}
        curves = pd.DataFrame(
            intrinsic_refractive_index_rows(
                "SiC", result, np.linspace(1200.0, 4000.0, 20)
            )
        )
        si_curves = curves.copy()
        si_curves["material"] = "Si"
        curves = pd.concat([curves, si_curves], ignore_index=True)
        joint, carrier = self._audit_objects()
        audit = build_identifiability_audit(
            {"SiC": joint, "Si": joint},
            carrier,
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plot_raw_v7_evidence(
                curves,
                payload,
                audit,
                root / "dispersion",
                root / "audit",
            )
            paths = list(root.rglob("*.png"))
            self.assertEqual(len(paths), 7)
            self.assertTrue(all(path.stat().st_size > 1000 for path in paths))


class V8DispersionExtremaTests(unittest.TestCase):
    @staticmethod
    def _mapped_points(thickness_um=8.0, with_outlier=False):
        slope = 2.0 * thickness_um * 1e-4
        points = []
        for dataset, angle in (("sic_10", 10.0), ("sic_15", 15.0)):
            for kind, offset in (("peak", 0.0), ("valley", 120.0)):
                base = 3000.0 + offset + (20.0 if angle == 15.0 else 0.0)
                for order in range(8):
                    g = base + order / slope
                    if with_outlier and dataset == "sic_10" and kind == "peak" and order == 4:
                        g += 180.0
                    points.append(
                        MappedExtremum(
                            dataset=dataset,
                            material="SiC",
                            scenario="intrinsic",
                            angle_deg=angle,
                            kind=kind,
                            order_local=order,
                            order_recovered=order,
                            sample_index=len(points),
                            wavenumber_cm1=1200.0 + order * 300.0,
                            g_cm1=g,
                            n_real=2.55,
                            extinction_k=0.0,
                            quality_weight=1.0,
                            eligible=True,
                        )
                    )
        return points

    def test_band_eligibility_excludes_sic_absorption_region(self):
        processed = V7IntrinsicScenarioTests._synthetic_sic_inputs()[0]
        eligibility = evaluate_band_eligibility(
            processed,
            "SiC",
            "intrinsic",
            "intrinsic",
            0.0,
        )
        x = processed.wavenumber_cm1
        self.assertTrue(eligibility.qualified)
        self.assertFalse(np.any(eligibility.mask[(x >= 1300) & (x <= 1600)]))
        self.assertTrue(eligibility.monotonic)

    def test_band_eligibility_rejects_empty_transparent_region(self):
        processed = V7IntrinsicScenarioTests._synthetic_sic_inputs()[0]
        eligibility = evaluate_band_eligibility(
            processed,
            "SiC",
            "intrinsic",
            "intrinsic",
            0.0,
            max_extinction=-1.0,
        )
        self.assertFalse(eligibility.qualified)
        self.assertEqual(np.count_nonzero(eligibility.mask), 0)

    def test_extrema_observation_contains_quality_metadata(self):
        processed = V7IntrinsicScenarioTests._synthetic_sic_inputs()[0]
        two = estimate_two_beam(processed)
        observations = observe_extrema(processed, two)
        self.assertGreaterEqual(len(observations), 12)
        self.assertEqual({item.kind for item in observations}, {"peak", "valley"})
        self.assertTrue(all(item.prominence_pct > 0 for item in observations))
        self.assertTrue(all(item.quality_weight > 0 for item in observations))

    def test_mapping_recovers_missing_fringe_order(self):
        x = np.arange(7.0)
        eligibility = BandEligibility(
            material="SiC",
            scenario="intrinsic",
            mask=np.ones(7, dtype=bool),
            n_real=np.full(7, 2.55),
            extinction_k=np.zeros(7),
            phase_coordinate_cm1=x * 100.0,
            eligible_width_cm1=600.0,
            eligible_fraction=1.0,
            monotonic=True,
            qualified=True,
            failure_reason="",
        )
        observations = [
            ExtremumObservation(
                "sic_10",
                "SiC",
                10.0,
                "peak",
                order,
                index,
                1200.0 + index,
                1.0,
                10.0,
                False,
                1.0,
            )
            for order, index in enumerate((1, 2, 3, 5, 6))
        ]
        mapped = map_extrema_to_scenario(
            observations,
            {"sic_10": eligibility},
            "intrinsic",
        )
        self.assertEqual(
            [point.order_recovered for point in mapped],
            [0, 1, 2, 4, 5],
        )

    def test_shared_slope_recovers_exact_thickness(self):
        result = fit_shared_thickness(
            self._mapped_points(),
            bootstrap_repeats=20,
        )
        self.assertAlmostEqual(result.thickness_um, 8.0, places=6)
        self.assertTrue(result.stable)
        self.assertEqual(result.inlier_count, 32)

    def test_shared_slope_limits_single_outlier(self):
        result = fit_shared_thickness(
            self._mapped_points(with_outlier=True),
            bootstrap_repeats=20,
        )
        self.assertLess(abs(result.thickness_um - 8.0) / 8.0, 0.01)
        self.assertLessEqual(result.rejected_fraction, 0.2)

    def test_shared_fit_rejects_insufficient_points(self):
        with self.assertRaises(ValueError):
            fit_shared_thickness(self._mapped_points()[:3])

    def test_material_scenarios_recover_synthetic_dispersion(self):
        spectra = V7IntrinsicScenarioTests._synthetic_sic_inputs()
        two = [estimate_two_beam(processed) for processed in spectra]
        result = fit_dispersion_extrema_scenarios(
            spectra,
            two,
            "SiC",
            8.0,
            bootstrap_repeats=20,
        )
        self.assertEqual(len(result.scenario_results), 4)
        self.assertAlmostEqual(result.nominal_thickness_um, 8.0, delta=0.1)
        self.assertLessEqual(result.systematic_low_um, 8.0)
        self.assertGreaterEqual(result.systematic_high_um, 8.0)

    def test_v8_comparison_uses_explicit_adoption_flag(self):
        summary = pd.DataFrame(
            {
                "material": ["SiC", "SiC"],
                "angle_deg": [10.0, 15.0],
                "selected_thickness_um": [7.9, 7.8],
                "bootstrap_std_um": [0.1, 0.1],
            }
        )
        payload = {
            "SiC": {
                "nominal_thickness_um": 7.5,
                "statistical_ci95_low_um": 7.4,
                "statistical_ci95_high_um": 7.6,
                "systematic_low_um": 7.3,
                "systematic_high_um": 7.85,
                "peak_valley_diff_pct": 0.4,
                "angle_diff_pct": 1.2,
                "band_cv_pct": 0.8,
                "multi_beam_consistency_pct": 4.0,
                "adopted": False,
                "final_thickness_um": 7.85,
                "fallback_reason": "测试回退",
            }
        }
        comparison = build_dispersion_extrema_comparison(summary, payload)
        self.assertFalse(comparison["materials"]["SiC"]["v8_adopted"])
        self.assertEqual(
            comparison["materials"]["SiC"]["final_thickness_um"],
            7.85,
        )

    def test_v8_raw_extrema_figures_are_created(self):
        spectra = V7IntrinsicScenarioTests._synthetic_sic_inputs()
        two = [estimate_two_beam(processed) for processed in spectra]
        result = fit_dispersion_extrema_scenarios(
            spectra,
            two,
            "SiC",
            8.0,
            bootstrap_repeats=20,
        )
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            plot_raw_extrema_evidence({"SiC": result}, output)
            paths = list(output.glob("*.png"))
            self.assertEqual(len(paths), 6)
            self.assertTrue(all(path.stat().st_size > 1000 for path in paths))


class V9AnalysisEvidenceTests(unittest.TestCase):
    @staticmethod
    def _material_inputs(material: str, thickness_um: float):
        specs = DATASETS[:2] if material == "SiC" else DATASETS[2:]
        x = np.linspace(1200.0, 4000.0, 1200)
        items = []
        for spec in specs:
            index = material_refractive_index(material, x, mode="intrinsic")
            optical = np.sqrt(
                index.real**2 - np.sin(np.deg2rad(spec.angle_deg)) ** 2
            )
            phase = 4 * np.pi * thickness_um * 1e-4 * x * optical
            residual = 0.8 * np.cos(phase + 0.2)
            source = Spectrum(x, 20.0 + residual, spec, {})
            processed = ProcessedSpectrum(
                x,
                20.0 + residual,
                20.0 + residual,
                np.full_like(x, 20.0),
                residual,
                float(np.median(np.diff(x))),
                source,
            )
            items.append((processed, estimate_two_beam(processed)))
        return items

    @classmethod
    def _inputs(cls):
        extrema_inputs = {
            "SiC": cls._material_inputs("SiC", 8.0),
            "Si": cls._material_inputs("Si", 3.6),
        }
        results = {
            material: fit_dispersion_extrema_scenarios(
                [item[0] for item in items],
                [item[1] for item in items],
                material,
                8.0 if material == "SiC" else 3.6,
                bootstrap_repeats=20,
            )
            for material, items in extrema_inputs.items()
        }
        summary = pd.DataFrame(
            {
                "material": ["SiC", "SiC", "Si", "Si"],
                "angle_deg": [10.0, 15.0, 10.0, 15.0],
                "selected_model": [
                    "two-beam",
                    "two-beam",
                    "multi-beam",
                    "multi-beam",
                ],
                "selected_thickness_um": [8.0, 8.0, 3.6, 3.6],
                "bootstrap_std_um": [0.1, 0.1, 0.05, 0.05],
                "v8_nominal_thickness_um": [
                    results["SiC"].nominal_thickness_um,
                    results["SiC"].nominal_thickness_um,
                    results["Si"].nominal_thickness_um,
                    results["Si"].nominal_thickness_um,
                ],
                "v8_adopted": [True, True, False, False],
            }
        )
        payload = {}
        for material, result in results.items():
            item = result.to_dict(False)
            adopted = material == "SiC"
            item["adopted"] = adopted
            item["fallback_reason"] = "" if adopted else "与Airy结果不一致"
            item["multi_beam_consistency_pct"] = (
                abs(result.nominal_thickness_um - (8.0 if material == "SiC" else 3.6))
                / (8.0 if material == "SiC" else 3.6)
                * 100.0
            )
            item["final_thickness_um"] = (
                result.nominal_thickness_um if adopted else 3.6
            )
            payload[material] = item
        comparison = build_dispersion_extrema_comparison(summary, payload)
        joint, carrier = V7IntrinsicScenarioTests._audit_objects()
        audit = build_identifiability_audit(
            {"SiC": joint, "Si": joint},
            carrier,
        )
        return summary, extrema_inputs, results, comparison, audit

    def test_analysis_evidence_creates_complete_figure_set(self):
        summary, extrema_inputs, results, comparison, audit = self._inputs()
        with tempfile.TemporaryDirectory() as temporary:
            paths = plot_analysis_evidence(
                summary,
                extrema_inputs,
                results,
                comparison,
                audit,
                Path(temporary),
            )
            self.assertEqual(len(paths), 13)
            self.assertTrue(all(path.exists() for path in paths))
            self.assertTrue(all(path.stat().st_size > 1000 for path in paths))
            self.assertTrue(all(imread(path).shape[1] >= 1800 for path in paths))

    def test_analysis_plotting_uses_shared_gate_constants(self):
        source = inspect.getsource(evidence_plotting)
        self.assertIn("V8_THRESHOLDS", source)
        self.assertNotIn("THRESHOLDS = {", source)

    def test_analysis_evidence_rejects_missing_summary_columns(self):
        _, extrema_inputs, results, comparison, audit = self._inputs()
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(ValueError):
                plot_analysis_evidence(
                    pd.DataFrame({"material": ["SiC"]}),
                    extrema_inputs,
                    results,
                    comparison,
                    audit,
                    Path(temporary),
                )


if __name__ == "__main__":
    unittest.main()

"""Si 与 4H-SiC 的波长—载流子浓度耦合复介电模型。"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


EPSILON_0 = 8.8541878128e-12
E_CHARGE = 1.602176634e-19
M_ELECTRON = 9.1093837015e-31
C_CM_S = 2.99792458e10


@dataclass(frozen=True)
class DispersionMetadata:
    model: str
    valid_wavenumber_cm1: tuple[float, float]
    references: tuple[str, ...]
    assumptions: tuple[str, ...]


METADATA = {
    "Si": DispersionMetadata(
        model="Edwards-Ochoa background + n-type Drude",
        valid_wavenumber_cm1=(400.0, 4000.0),
        references=(
            "https://doi.org/10.1364/AO.19.004130",
            "https://doi.org/10.1109/PROC.1967.6123",
        ),
        assumptions=(
            "300 K",
            "n-type carrier mobility engineering prior",
            "isotropic optical response",
        ),
    ),
    "SiC": DispersionMetadata(
        model="4H-SiC one-oscillator lattice + n-type Drude",
        valid_wavenumber_cm1=(700.0, 4000.0),
        references=(
            "https://doi.org/10.1103/PhysRevB.60.11464",
            "https://doi.org/10.1143/JJAP.45.L1226",
        ),
        assumptions=(
            "4H-SiC ordinary/isotropic approximation",
            "300 K",
            "phonon and mobility parameters are literature engineering priors",
        ),
    ),
}


CARRIER_BOUNDS_LOG10 = {
    "Si": {"epi": (14.0, 19.0), "substrate": (15.0, np.log10(3e19))},
    "SiC": {
        "epi": (15.0, np.log10(3e18)),
        "substrate": (np.log10(3e17), np.log10(2e19)),
    },
}


CARRIER_PRIOR_LOG10 = {
    "Si": {"epi": 16.0, "substrate": 18.0},
    "SiC": {"epi": 17.0, "substrate": np.log10(7.1e18)},
}


CARRIER_SCENARIOS_CM3 = {
    "Si": {
        "low": (1e14, 1e15),
        "medium": (1e16, 1e18),
        "high": (1e18, 3e19),
    },
    "SiC": {
        "low": (1e15, 3e17),
        "medium": (1e17, 7.1e18),
        "high": (3e18, 2e19),
    },
}


def _validate_inputs(wavenumber_cm1: np.ndarray, carrier_cm3: float) -> np.ndarray:
    nu = np.asarray(wavenumber_cm1, dtype=float)
    if np.any(~np.isfinite(nu)) or np.any(nu <= 0):
        raise ValueError("波数必须为有限正数")
    if not np.isfinite(carrier_cm3) or carrier_cm3 < 0:
        raise ValueError("载流子浓度必须为有限非负数")
    return nu


def si_intrinsic_n(wavenumber_cm1: np.ndarray) -> np.ndarray:
    """Edwards--Ochoa 26 °C 红外折射率，lambda 适用范围 2.5--25 um。"""
    nu = _validate_inputs(wavenumber_cm1, 0.0)
    wavelength_um = 1e4 / nu
    if np.any((wavelength_um < 2.5 - 1e-12) | (wavelength_um > 25.0 + 1e-12)):
        raise ValueError("Edwards--Ochoa 公式仅用于 2.5--25 um")
    denominator = wavelength_um**2 - 0.028
    return (
        3.41983
        + 0.159906 / denominator
        - 0.123109 / denominator**2
        + 1.26878e-6 * wavelength_um**2
        - 1.95104e-9 * wavelength_um**4
    )


def mobility_si_n(carrier_cm3: float) -> float:
    """300 K n-Si Caughey--Thomas 工程迁移率先验，cm^2/(V s)。"""
    if not np.isfinite(carrier_cm3) or carrier_cm3 < 0:
        raise ValueError("载流子浓度必须为有限非负数")
    return float(65.0 + 1265.0 / (1.0 + (carrier_cm3 / 8.5e16) ** 0.72))


def mobility_4h_sic(carrier_cm3: float) -> float:
    """300 K n-4H-SiC 浓度相关工程迁移率先验，cm^2/(V s)。"""
    if not np.isfinite(carrier_cm3) or carrier_cm3 < 0:
        raise ValueError("载流子浓度必须为有限非负数")
    return float(40.0 + 910.0 / (1.0 + (carrier_cm3 / 1.94e17) ** 0.61))


def _drude_term(
    wavenumber_cm1: np.ndarray,
    carrier_cm3: float,
    mass_for_density_m0: float,
    mobility_cm2_vs: float,
    mass_for_mobility_m0: float | None = None,
) -> np.ndarray:
    if carrier_cm3 == 0:
        return np.zeros_like(wavenumber_cm1, dtype=complex)
    omega = 2.0 * np.pi * C_CM_S * wavenumber_cm1
    carrier_m3 = carrier_cm3 * 1e6
    density_mass = mass_for_density_m0 * M_ELECTRON
    mobility_mass = (mass_for_mobility_m0 or mass_for_density_m0) * M_ELECTRON
    mobility_m2_vs = mobility_cm2_vs * 1e-4
    omega_p2 = carrier_m3 * E_CHARGE**2 / (EPSILON_0 * density_mass)
    gamma = E_CHARGE / (mobility_mass * mobility_m2_vs)
    return -omega_p2 / (omega**2 + 1j * gamma * omega)


def epsilon_si(wavenumber_cm1: np.ndarray, carrier_cm3: float) -> np.ndarray:
    """n 型 Si 的背景色散与自由载流子复介电函数。"""
    nu = _validate_inputs(wavenumber_cm1, carrier_cm3)
    background = si_intrinsic_n(nu) ** 2
    return background.astype(complex) + _drude_term(
        nu, carrier_cm3, 0.26, mobility_si_n(carrier_cm3)
    )


def epsilon_4h_sic(wavenumber_cm1: np.ndarray, carrier_cm3: float) -> np.ndarray:
    """4H-SiC 单振子晶格项与自由载流子项。"""
    nu = _validate_inputs(wavenumber_cm1, carrier_cm3)
    scale = 2.0 * np.pi * C_CM_S
    omega = scale * nu
    omega_to = scale * 798.0
    omega_lo = scale * 970.0
    gamma_ph = scale * 3.24
    lattice = 6.56 * (
        omega_lo**2 - omega**2 - 1j * gamma_ph * omega
    ) / (omega_to**2 - omega**2 - 1j * gamma_ph * omega)
    return lattice + _drude_term(
        nu,
        carrier_cm3,
        mass_for_density_m0=0.424,
        mobility_cm2_vs=mobility_4h_sic(carrier_cm3),
        mass_for_mobility_m0=0.386,
    )


def passive_complex_sqrt(values: np.ndarray) -> np.ndarray:
    """返回满足 Im(sqrt)>=0 的被动介质平方根分支。"""
    roots = np.sqrt(np.asarray(values, dtype=complex))
    roots = np.where(np.imag(roots) < 0, -roots, roots)
    roots = np.where(
        (np.abs(np.imag(roots)) < 1e-14) & (np.real(roots) < 0), -roots, roots
    )
    return roots


def material_epsilon(
    material: str, wavenumber_cm1: np.ndarray, carrier_cm3: float
) -> np.ndarray:
    if material == "Si":
        return epsilon_si(wavenumber_cm1, carrier_cm3)
    if material == "SiC":
        return epsilon_4h_sic(wavenumber_cm1, carrier_cm3)
    raise ValueError(f"不支持的材料：{material}")


def material_refractive_index(
    material: str, wavenumber_cm1: np.ndarray, carrier_cm3: float
) -> np.ndarray:
    return passive_complex_sqrt(
        material_epsilon(material, wavenumber_cm1, carrier_cm3)
    )

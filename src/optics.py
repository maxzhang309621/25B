"""斜入射薄膜干涉的物理公式。

含两类模型：
1) 常折射率双光束/Airy（条纹相位与有效反射率）；
2) 复介电空气—外延层—衬底 Fresnel–Airy（色散联合校准用）。
"""

from __future__ import annotations

import numpy as np

from dispersion import passive_complex_sqrt


def refracted_cosine(n: np.ndarray | float, angle_deg: float) -> np.ndarray:
    """返回膜内折射角余弦，入射介质折射率取 1。"""
    n_arr = np.asarray(n, dtype=float)
    if np.any(~np.isfinite(n_arr)) or np.any(n_arr <= 0):
        raise ValueError("折射率必须为有限正数")
    if not np.isfinite(angle_deg) or not 0 <= angle_deg < 90:
        raise ValueError("入射角必须位于 [0, 90) 度")
    sin0 = np.sin(np.deg2rad(angle_deg))
    if np.any(n_arr <= sin0):
        raise ValueError("当前折射率与入射角不产生实数折射角")
    return np.sqrt(1.0 - (sin0 / n_arr) ** 2)


def phase_coordinate(
    wavenumber_cm1: np.ndarray,
    n: np.ndarray | float,
    angle_deg: float,
) -> np.ndarray:
    """g=波数*n*cos(theta_1)，单位 cm^-1。"""
    n_arr = np.asarray(n, dtype=float)
    return np.asarray(wavenumber_cm1, float) * n_arr * refracted_cosine(n_arr, angle_deg)


def round_trip_phase(
    wavenumber_cm1: np.ndarray,
    thickness_um: float,
    n: np.ndarray | float,
    angle_deg: float,
) -> np.ndarray:
    """膜内一次往返相位差 4*pi*d*g。"""
    if not np.isfinite(thickness_um) or thickness_um <= 0:
        raise ValueError("厚度必须为有限正数")
    d_cm = thickness_um * 1e-4
    return 4.0 * np.pi * d_cm * phase_coordinate(wavenumber_cm1, n, angle_deg)


def thickness_from_fringe_spacing(
    spacing_cm1: float,
    n: float,
    angle_deg: float,
) -> float:
    """常折射率下由相邻同类极值波数间距计算厚度（微米）。"""
    if not np.isfinite(spacing_cm1) or spacing_cm1 <= 0:
        raise ValueError("条纹间距必须为有限正数")
    optical_factor = n * float(refracted_cosine(n, angle_deg))
    return 1e4 / (2.0 * optical_factor * spacing_cm1)


def fresnel_reflectance_air_film(n: float, angle_deg: float) -> tuple[float, float]:
    """空气到无吸收膜的 s/p 偏振界面反射率。"""
    theta0 = np.deg2rad(angle_deg)
    cos0 = np.cos(theta0)
    cos1 = float(refracted_cosine(n, angle_deg))
    rs = (cos0 - n * cos1) / (cos0 + n * cos1)
    rp = (n * cos0 - cos1) / (n * cos0 + cos1)
    return float(rs * rs), float(rp * rp)


def airy_normalized(phase: np.ndarray, reflectivity: float) -> np.ndarray:
    """对称、无吸收 Fabry–Pérot 腔的归一化反射率。"""
    r = float(np.clip(reflectivity, 1e-8, 0.999))
    f = 4.0 * r / (1.0 - r) ** 2
    transmission = 1.0 / (1.0 + f * np.sin(phase / 2.0) ** 2)
    return 1.0 - transmission


def _normal_wavevector(epsilon: np.ndarray, sin_angle: float) -> np.ndarray:
    """返回归一化法向波矢 q=sqrt(epsilon-sin(theta0)^2)。"""
    return passive_complex_sqrt(np.asarray(epsilon, complex) - sin_angle**2)


def thin_film_reflectance(
    wavenumber_cm1: np.ndarray,
    thickness_um: float,
    angle_deg: float,
    epsilon_film: np.ndarray,
    epsilon_substrate: np.ndarray,
) -> np.ndarray:
    """空气/外延层/半无限衬底的非偏振单层 Fresnel--Airy 反射率。

    先算 s/p 界面振幅反射系数，再叠加层内往返相位因子 exp(2iβ)。
    返回值落在 [0,1]，为物理反射率（非百分数）。
    """
    x = np.asarray(wavenumber_cm1, dtype=float)
    eps1 = np.asarray(epsilon_film, dtype=complex)
    eps2 = np.asarray(epsilon_substrate, dtype=complex)
    if x.shape != eps1.shape or x.shape != eps2.shape:
        raise ValueError("波数与两层介电函数数组形状必须一致")
    if np.any(~np.isfinite(x)) or np.any(x <= 0):
        raise ValueError("波数必须为有限正数")
    if not np.isfinite(thickness_um) or thickness_um < 0:
        raise ValueError("厚度必须为有限非负数")
    if not np.isfinite(angle_deg) or not 0 <= angle_deg < 90:
        raise ValueError("入射角必须位于 [0, 90) 度")

    theta0 = np.deg2rad(angle_deg)
    sin0 = float(np.sin(theta0))
    q0 = np.full_like(x, np.cos(theta0), dtype=complex)
    eps0 = np.ones_like(x, dtype=complex)
    q1 = _normal_wavevector(eps1, sin0)
    q2 = _normal_wavevector(eps2, sin0)

    # 0=空气, 1=外延层, 2=衬底
    r01_s = (q0 - q1) / (q0 + q1)
    r12_s = (q1 - q2) / (q1 + q2)
    r01_p = (eps0 * q1 - eps1 * q0) / (eps0 * q1 + eps1 * q0)
    r12_p = (eps1 * q2 - eps2 * q1) / (eps1 * q2 + eps2 * q1)

    beta = 2.0 * np.pi * (thickness_um * 1e-4) * x * q1
    propagation = np.exp(2j * beta)
    total_s = (r01_s + r12_s * propagation) / (
        1.0 + r01_s * r12_s * propagation
    )
    total_p = (r01_p + r12_p * propagation) / (
        1.0 + r01_p * r12_p * propagation
    )
    reflectance = 0.5 * (np.abs(total_s) ** 2 + np.abs(total_p) ** 2)
    return np.asarray(reflectance.real, dtype=float)

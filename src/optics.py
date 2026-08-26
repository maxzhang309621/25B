"""斜入射薄膜干涉的物理公式。"""

from __future__ import annotations

import numpy as np


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

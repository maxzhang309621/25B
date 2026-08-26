# -*- coding: utf-8 -*-
"""
多方程联立：双角度 + 多峰，估 d 与色散参数（不是每点一个自由 n）
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import openpyxl
from scipy.optimize import least_squares
from scipy.signal import find_peaks, savgol_filter

ROOT = Path(__file__).resolve().parent
ATTACH = ROOT.parent / "data"
OUT = ROOT
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


def load(name):
    wb = openpyxl.load_workbook(ATTACH / name, data_only=True)
    ws = wb.active
    nu, R = [], []
    for row in ws.iter_rows(min_row=2, values_only=True):
        if row[0] is None:
            continue
        nu.append(float(row[0]))
        R.append(float(row[1]))
    nu, R = np.array(nu), np.clip(np.array(R), 0, 100)
    if R[0] == 0:
        nu, R = nu[1:], R[1:]
    return nu, R


def detrend(y):
    x = np.linspace(-1, 1, len(y))
    return y - np.polyval(np.polyfit(x, y, 2), x)


def peaks(nu, R, lo=1500, hi=3000):
    m = (nu >= lo) & (nu <= hi)
    x, y = nu[m], R[m]
    yd = detrend(savgol_filter(y, 31, 3))
    idx, _ = find_peaks(yd, prominence=0.05, distance=22)
    if len(idx) < 5:
        idx, _ = find_peaks(yd, prominence=0.03, distance=18)
    return x[idx]


def n_disp(nu, eps_inf, B):
    """n^2 = eps_inf + B/nu^2 （B 可正可负，弱色散）"""
    return np.sqrt(np.maximum(eps_inf + B / nu**2, 0.5))


def beta(n, theta):
    return 2 * np.sqrt(np.maximum(n**2 - np.sin(np.deg2rad(theta)) ** 2, 1e-12))


def main():
    nu1, R1 = load("附件1.xlsx")
    nu2, R2 = load("附件2.xlsx")
    p1 = peaks(nu1, R1)
    p2 = peaks(nu2, R2)
    print("n_peaks", len(p1), len(p2))
    print("peaks10", np.round(p1, 1))
    print("peaks15", np.round(p2, 1))

    # ---------- 方案 A：假设 n 常数，双角度联立 ----------
    # 相邻峰： 2 n d cosθ' * Δν ≈ 1  →  d * beta(n)*Δν ≈ 1
    # 用中位间距
    def d_from_spacing(peaks_nu, theta, n):
        dnu = np.median(np.diff(peaks_nu))
        return 1.0 / (beta(n, theta) * dnu) * 1e4  # um

    # 两角度应给出同一 d：对 n 扫描，找使 |d10-d15| 最小的 n
    ns = np.linspace(2.40, 2.70, 61)
    best = None
    curve = []
    for n in ns:
        d10 = d_from_spacing(p1, 10, n)
        d15 = d_from_spacing(p2, 15, n)
        diff = abs(d10 - d15)
        mean = 0.5 * (d10 + d15)
        curve.append((n, d10, d15, diff, mean))
        if best is None or diff < best["diff"]:
            best = {"n": float(n), "d10": d10, "d15": d15, "diff": diff, "d": mean}
    print("A const-n dual-angle:", best)

    # ---------- 方案 B：多峰级数联立（色散两点参数 + d）----------
    # j = d_cm * beta(n(ν))*ν - m0
    # 参数 x = [d_um, eps_inf, B, m0_10, m0_15]
    j1 = np.arange(len(p1), dtype=float)
    j2 = np.arange(len(p2), dtype=float)

    def resid(x):
        d_um, eps_inf, B, m0a, m0b = x
        d_cm = d_um * 1e-4
        n1 = n_disp(p1, eps_inf, B)
        n2 = n_disp(p2, eps_inf, B)
        r1 = d_cm * beta(n1, 10) * p1 - m0a - j1
        r2 = d_cm * beta(n2, 15) * p2 - m0b - j2
        # 弱先验：eps_inf 靠近 6.55（n~2.56），B 不要过大
        prior = np.array([(eps_inf - 6.55) / 0.3, B / 5e6])
        return np.concatenate([r1, r2, 0.15 * prior])

    x0 = np.array([8.0, 6.55, 0.0, 6.0, 6.0])
    bounds = ([5.0, 5.5, -8e6, -30, -30], [12.0, 7.5, 8e6, 40, 40])
    sol = least_squares(resid, x0, bounds=bounds, max_nfev=8000)
    d_um, eps_inf, B, m0a, m0b = sol.x
    print(
        "B disp fit:",
        dict(d_um=d_um, eps_inf=eps_inf, B=B, n_at_2000=float(n_disp(2000, eps_inf, B)), cost=sol.cost, success=sol.success),
    )

    # 残差与逐峰 n
    n1 = n_disp(p1, eps_inf, B)
    n2 = n_disp(p2, eps_inf, B)
    pred1 = (d_um * 1e-4) * beta(n1, 10) * p1 - m0a
    pred2 = (d_um * 1e-4) * beta(n2, 15) * p2 - m0b

    # ---------- 方案 C：说明「每点自由 n」不可行 ----------
    # 未知：每峰一个 n，再加一个 d → 未知数 = n_peaks_total + 1
    # 方程：每峰一个级数条件，但级数绝对 m0 未知 → 实际有效方程更少
    n_unknown_free = len(p1) + len(p2) + 1 + 2  # n's + d + 2 m0
    n_eq = len(p1) + len(p2)
    print("C free-n count: unknowns", n_unknown_free, "equations", n_eq, "underdetermined", n_unknown_free > n_eq)

    # ---------- 图 ----------
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.3), dpi=150)
    arr = np.array(curve)
    axes[0].plot(arr[:, 0], arr[:, 1], label="d from 10°", color="#2B6CB0")
    axes[0].plot(arr[:, 0], arr[:, 2], label="d from 15°", color="#C05621")
    axes[0].axvline(best["n"], color="#38A169", ls="--", label=f"最佳 n={best['n']:.3f}")
    axes[0].set_xlabel("假设常数 n")
    axes[0].set_ylabel("d (μm)")
    axes[0].set_title("方案A：常数 n + 双角度间距联立")
    axes[0].legend(fontsize=8)
    axes[0].grid(True, alpha=0.3)

    nu_line = np.linspace(1500, 3000, 200)
    axes[1].plot(nu_line, n_disp(nu_line, eps_inf, B), color="#2B6CB0", lw=2, label="拟合 n(ν̃)")
    axes[1].plot(p1, n1, "o", color="#2B6CB0", ms=5, label="10° 峰位处 n")
    axes[1].plot(p2, n2, "s", color="#C05621", ms=5, label="15° 峰位处 n")
    axes[1].axhline(2.55, color="gray", ls="--", lw=1)
    axes[1].set_xlabel(r"$\tilde{\nu}$ (cm$^{-1}$)")
    axes[1].set_ylabel(r"$n(\tilde{\nu})$")
    axes[1].set_title(f"方案B：色散联立  d={d_um:.3f} μm")
    axes[1].legend(fontsize=8)
    axes[1].grid(True, alpha=0.3)
    fig.suptitle("多式子联立：能估参数化的 n(ν̃) 和一个 d", fontsize=12)
    fig.tight_layout()
    fig.savefig(OUT / "图_多方程联立.png", bbox_inches="tight", facecolor="white")
    plt.close()

    # 级数拟合图
    fig, ax = plt.subplots(figsize=(7.5, 4.2), dpi=150)
    ax.plot(j1, pred1, "o-", color="#2B6CB0", label="10° 预测级数")
    ax.plot(j1, j1, "k--", lw=1, label="理想 j")
    ax.plot(j2, pred2, "s-", color="#C05621", label="15° 预测级数")
    ax.set_xlabel("相对级数 j（数据）")
    ax.set_ylabel("模型预测")
    ax.set_title(f"联立拟合残差检验  RMSE10={np.sqrt(np.mean((pred1-j1)**2)):.3f}  RMSE15={np.sqrt(np.mean((pred2-j2)**2)):.3f}")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(OUT / "图_联立级数检验.png", bbox_inches="tight", facecolor="white")
    plt.close()

    summary = {
        "scheme_A_const_n": best,
        "scheme_B_dispersion": {
            "d_um": float(d_um),
            "eps_inf": float(eps_inf),
            "B": float(B),
            "n_1500": float(n_disp(1500, eps_inf, B)),
            "n_2000": float(n_disp(2000, eps_inf, B)),
            "n_3000": float(n_disp(3000, eps_inf, B)),
            "m0_10": float(m0a),
            "m0_15": float(m0b),
            "cost": float(sol.cost),
            "rmse_10": float(np.sqrt(np.mean((pred1 - j1) ** 2))),
            "rmse_15": float(np.sqrt(np.mean((pred2 - j2) ** 2))),
        },
        "scheme_C_free_n_per_peak": {
            "n_equations": n_eq,
            "n_unknowns": n_unknown_free,
            "feasible": False,
            "reason": "每个峰一个自由n + d + 两个绝对级数原点 → 未知数多于方程",
        },
        "takeaway": "联立可行，但必须把 n 写成少数参数的 n(ν̃)；双角度提供交叉约束。",
    }
    (OUT / "summary_联立.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

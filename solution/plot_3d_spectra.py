# -*- coding: utf-8 -*-
"""三维图：波数 × 角度/样品 × 反射率（曲面 + 瀑布）"""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401
import numpy as np
import openpyxl
from scipy.signal import savgol_filter

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
    nu, R = np.asarray(nu, float), np.clip(np.asarray(R, float), 0, 100)
    if R[0] == 0:
        nu, R = nu[1:], R[1:]
    return nu, R


def detrend(y):
    x = np.linspace(-1, 1, len(y))
    return y - np.polyval(np.polyfit(x, y, 2), x)


def main():
    # ---- 1) SiC：两角度原始 R 三维瀑布 ----
    fig = plt.figure(figsize=(12, 5.2), dpi=150)
    ax1 = fig.add_subplot(1, 2, 1, projection="3d")
    ax2 = fig.add_subplot(1, 2, 2, projection="3d")

    for ax, files, title, lo, hi, cmap in [
        (
            ax1,
            [("附件1.xlsx", 10), ("附件2.xlsx", 15)],
            "SiC 原始反射率",
            1200,
            3200,
            "Blues",
        ),
        (
            ax2,
            [("附件3.xlsx", 10), ("附件4.xlsx", 15)],
            "Si 原始反射率",
            600,
            2200,
            "Greens",
        ),
    ]:
        for fname, th in files:
            nu, R = load(fname)
            m = (nu >= lo) & (nu <= hi)
            # 降采样，三维图更清晰
            x = nu[m][::8]
            z = R[m][::8]
            y = np.full_like(x, th, dtype=float)
            ax.plot(x, y, z, lw=1.0)
        ax.set_xlabel(r"波数 $\tilde{\nu}$")
        ax.set_ylabel("入射角 (°)")
        ax.set_zlabel("R (%)")
        ax.set_title(title)
        ax.view_init(elev=22, azim=-60)

    fig.suptitle("三维瀑布图：波数–角度–反射率", fontsize=13)
    fig.tight_layout()
    fig.savefig(OUT / "图_三维_瀑布_原始R.png", bbox_inches="tight", facecolor="white")
    plt.close()

    # ---- 2) 去趋势振荡三维（更能看干涉）----
    fig = plt.figure(figsize=(12, 5.2), dpi=150)
    ax1 = fig.add_subplot(1, 2, 1, projection="3d")
    ax2 = fig.add_subplot(1, 2, 2, projection="3d")

    for ax, files, title, lo, hi, colors in [
        (
            ax1,
            [("附件1.xlsx", 10, "#2B6CB0"), ("附件2.xlsx", 15, "#C05621")],
            "SiC 去趋势振荡 ΔR",
            1400,
            3000,
            None,
        ),
        (
            ax2,
            [("附件3.xlsx", 10, "#2F855A"), ("附件4.xlsx", 15, "#6B46C1")],
            "Si 去趋势振荡 ΔR（振幅大→多光束）",
            700,
            2000,
            None,
        ),
    ]:
        for fname, th, c in files:
            nu, R = load(fname)
            m = (nu >= lo) & (nu <= hi)
            x = nu[m]
            yR = savgol_filter(R[m], 31, 3)
            z = detrend(yR)
            xs, zs = x[::6], z[::6]
            ys = np.full_like(xs, th, dtype=float)
            ax.plot(xs, ys, zs, color=c, lw=1.0, label=f"{th}°")
        ax.set_xlabel(r"波数 $\tilde{\nu}$")
        ax.set_ylabel("入射角 (°)")
        ax.set_zlabel("ΔR (%)")
        ax.set_title(title)
        ax.legend(fontsize=8)
        ax.view_init(elev=25, azim=-55)

    fig.suptitle("三维图：振荡关系（横轴波数，纵深角度，高度反射振荡）", fontsize=13)
    fig.tight_layout()
    fig.savefig(OUT / "图_三维_振荡.png", bbox_inches="tight", facecolor="white")
    plt.close()

    # ---- 3) SiC 单一角度：波数 × 假想连续角 的示意曲面（用10/15插值）----
    nu1, R1 = load("附件1.xlsx")
    nu2, R2 = load("附件2.xlsx")
    lo, hi = 1500, 2800
    m1 = (nu1 >= lo) & (nu1 <= hi)
    # 公共波数网格
    grid = np.linspace(lo, hi, 400)
    r10 = np.interp(grid, nu1[m1], savgol_filter(R1[m1], 31, 3))
    m2 = (nu2 >= lo) & (nu2 <= hi)
    r15 = np.interp(grid, nu2[m2], savgol_filter(R2[m2], 31, 3))
    # 在 10–15° 间线性插值成曲面（仅可视化）
    thetas = np.linspace(10, 15, 12)
    NU, TH = np.meshgrid(grid, thetas)
    Z = np.zeros_like(NU)
    for i, th in enumerate(thetas):
        w = (th - 10) / 5.0
        Z[i] = (1 - w) * r10 + w * r15

    fig = plt.figure(figsize=(9.5, 6.2), dpi=150)
    ax = fig.add_subplot(111, projection="3d")
    surf = ax.plot_surface(NU, TH, Z, cmap="viridis", linewidth=0, antialiased=True, alpha=0.92)
    fig.colorbar(surf, ax=ax, shrink=0.6, label="R (%)")
    ax.set_xlabel(r"波数 $\tilde{\nu}$ (cm$^{-1}$)")
    ax.set_ylabel("入射角 (°)")
    ax.set_zlabel("R (%)")
    ax.set_title("SiC 三维曲面（10°–15° 间插值示意）")
    ax.view_init(elev=28, azim=-58)
    fig.tight_layout()
    fig.savefig(OUT / "图_三维_SiC曲面.png", bbox_inches="tight", facecolor="white")
    plt.close()

    print("saved 3D figures")


if __name__ == "__main__":
    main()

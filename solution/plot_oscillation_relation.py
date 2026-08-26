# -*- coding: utf-8 -*-
"""振荡关系专用图：波数上的干涉条纹"""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
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


def detrend(y, deg=2):
    x = np.linspace(-1, 1, len(y))
    t = np.polyval(np.polyfit(x, y, deg), x)
    return y - t, t


def prep(nu, R, lo, hi):
    m = (nu >= lo) & (nu <= hi)
    x, y = nu[m], R[m]
    ys = savgol_filter(y, 31, 3)
    osc, trend = detrend(ys)
    return x, y, ys, osc, trend


def opd_fft(x, osc):
    dnu = float(np.median(np.diff(x)))
    xu = np.arange(x[0], x[-1], dnu)
    yu = np.interp(xu, x, osc)
    spec = np.abs(np.fft.rfft(yu * np.hanning(len(yu))))
    freq = np.fft.rfftfreq(len(yu), d=dnu)
    spec[0] = 0
    spec[freq < 0.0005] = 0
    f = float(freq[int(np.argmax(spec))])
    return f


def main():
    # ---- 图A：SiC / Si 振荡并排 ----
    fig, axes = plt.subplots(2, 1, figsize=(11, 7.2), dpi=160, sharex=False)

    # SiC
    nu, R = load("附件1.xlsx")
    x, y, ys, osc, trend = prep(nu, R, 1600, 2400)
    opd = opd_fft(x, osc)
    # 相位对齐的示意余弦
    # 拟合振幅与相位
    A = np.std(osc) * np.sqrt(2)
    # 粗配相位：最大化相关
    phis = np.linspace(0, 2 * np.pi, 180)
    best_phi, best_c = 0, -1
    for phi in phis:
        c = np.corrcoef(osc, A * np.cos(2 * np.pi * opd * x + phi))[0, 1]
        if c > best_c:
            best_c, best_phi = c, phi
    cos_fit = A * np.cos(2 * np.pi * opd * x + best_phi)

    ax = axes[0]
    ax.plot(x, osc, color="#2B6CB0", lw=1.3, label="实测去趋势振荡 ΔR")
    ax.plot(x, cos_fit, color="#E53E3E", lw=1.5, ls="--", label=rf"拟合 $\cos(2\pi\cdot OPD\cdot\tilde\nu+\varphi)$")
    ax.axhline(0, color="gray", lw=0.8)
    # 标一个周期
    if opd > 0:
        period = 1.0 / opd
        x0 = x[len(x) // 4]
        ax.annotate(
            "",
            xy=(x0 + period, 0.85 * np.max(np.abs(osc))),
            xytext=(x0, 0.85 * np.max(np.abs(osc))),
            arrowprops=dict(arrowstyle="<->", color="#D69E2E", lw=2),
        )
        ax.text(x0 + 0.5 * period, 0.95 * np.max(np.abs(osc)), r"$\Delta\tilde{\nu}=1/\mathrm{OPD}$", color="#D69E2E", ha="center", fontsize=11)
    ax.set_ylabel("ΔR (%)")
    ax.set_title(f"SiC 10° 振荡关系（局部窗）  OPD={opd:.5f} cm  与余弦相关={best_c:.3f}")
    ax.legend(loc="lower right", fontsize=9)
    ax.grid(True, alpha=0.3)

    # Si
    nu, R = load("附件3.xlsx")
    x, y, ys, osc, trend = prep(nu, R, 800, 1400)
    opd = opd_fft(x, osc)
    A = np.std(osc) * np.sqrt(2)
    best_phi, best_c = 0, -1
    for phi in np.linspace(0, 2 * np.pi, 180):
        c = np.corrcoef(osc, A * np.cos(2 * np.pi * opd * x + phi))[0, 1]
        if c > best_c:
            best_c, best_phi = c, phi
    cos_fit = A * np.cos(2 * np.pi * opd * x + best_phi)

    ax = axes[1]
    ax.plot(x, osc, color="#2F855A", lw=1.2, label="实测去趋势振荡 ΔR")
    ax.plot(x, cos_fit, color="#E53E3E", lw=1.5, ls="--", label=r"拟合余弦（双光束理想形）")
    ax.axhline(0, color="gray", lw=0.8)
    if opd > 0:
        period = 1.0 / opd
        x0 = x[len(x) // 5]
        ymax = 0.75 * np.max(np.abs(osc))
        ax.annotate(
            "",
            xy=(x0 + period, ymax),
            xytext=(x0, ymax),
            arrowprops=dict(arrowstyle="<->", color="#D69E2E", lw=2),
        )
        ax.text(x0 + 0.5 * period, ymax * 1.08, r"$\Delta\tilde{\nu}=1/\mathrm{OPD}$", color="#D69E2E", ha="center", fontsize=11)
    ax.set_xlabel(r"波数 $\tilde{\nu}$ (cm$^{-1}$)")
    ax.set_ylabel("ΔR (%)")
    ax.set_title(f"Si 10° 振荡关系（局部窗）  OPD={opd:.5f} cm  与余弦相关={best_c:.3f}（多光束时会偏离纯余弦）")
    ax.legend(loc="lower right", fontsize=9)
    ax.grid(True, alpha=0.3)

    fig.suptitle(
        r"振荡关系：反射率随波数近似按 $\cos(2\pi\cdot OPD\cdot\tilde{\nu})$ 周期起伏",
        fontsize=13,
        y=0.995,
    )
    fig.tight_layout()
    fig.savefig(OUT / "图_振荡关系_对照余弦.png", bbox_inches="tight", facecolor="white")
    plt.close()

    # ---- 图B：示意卡通：单调 vs 振荡 ----
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.0), dpi=160)
    nu = np.linspace(1500, 2800, 500)
    trend = 16 + 0.0012 * (nu - 1500)
    osc = 0.6 * np.cos(2 * np.pi * 0.004 * nu)
    axes[0].plot(nu, trend + osc, color="#2B6CB0", lw=1.5, label="R = 趋势 + 振荡")
    axes[0].plot(nu, trend, "k--", lw=1.3, label="慢变趋势")
    axes[0].set_title("完整光谱里看到的")
    axes[0].set_xlabel(r"波数 $\tilde{\nu}$")
    axes[0].set_ylabel("R")
    axes[0].legend(fontsize=9)
    axes[0].grid(True, alpha=0.3)

    axes[1].plot(nu, osc, color="#E53E3E", lw=1.6)
    axes[1].axhline(0, color="gray", lw=0.8)
    axes[1].set_title("抽出振荡后：周期关系（测厚用这个）")
    axes[1].set_xlabel(r"波数 $\tilde{\nu}$")
    axes[1].set_ylabel("ΔR")
    axes[1].grid(True, alpha=0.3)
    # mark period
    T = 1 / 0.004
    axes[1].annotate("", xy=(1800 + T, 0.45), xytext=(1800, 0.45), arrowprops=dict(arrowstyle="<->", color="#2B6CB0", lw=1.8))
    axes[1].text(1800 + T / 2, 0.55, r"周期 $\Delta\tilde{\nu}$", ha="center", color="#2B6CB0", fontsize=11)
    fig.suptitle("振荡关系在讲什么", fontsize=13)
    fig.tight_layout()
    fig.savefig(OUT / "图_振荡关系_示意.png", bbox_inches="tight", facecolor="white")
    plt.close()
    print("saved oscillation figures")


if __name__ == "__main__":
    main()

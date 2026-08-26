# -*- coding: utf-8 -*-
"""双光束 vs 多光束：FFT 对比图"""
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
    return y - np.polyval(np.polyfit(x, y, deg), x)


def prep_fft(nu, R, lo, hi):
    m = (nu >= lo) & (nu <= hi)
    x, y = nu[m], R[m]
    ys = savgol_filter(y, 31, 3)
    yo = detrend(ys)
    dnu = float(np.median(np.diff(x)))
    xu = np.arange(x[0], x[-1], dnu)
    yu = np.interp(xu, x, yo)
    win = np.hanning(len(yu))
    spec = np.abs(np.fft.rfft(yu * win))
    freq = np.fft.rfftfreq(len(yu), d=dnu)
    spec[0] = 0
    return xu, yu, freq, spec


def airy_R(delta, r01, r12):
    e = np.exp(-1j * delta)
    r = (r01 + r12 * e) / (1.0 + r01 * r12 * e)
    return np.abs(r) ** 2


def two_beam_R(delta, r01, r12):
    e = np.exp(-1j * delta)
    r = r01 + r12 * e
    return np.abs(r) ** 2


def theory_signals(OPD=0.004, n_pts=4000):
    """在波数轴上生成双光束/多光束反射振荡。"""
    nu = np.linspace(1400, 3200, n_pts)
    delta = 2 * np.pi * OPD * nu  # δ = 2π * OPD * ν̃
    r01, r12 = -0.55, 0.40
    R2 = two_beam_R(delta, r01, r12)
    Rm = airy_R(delta, r01, r12)
    # 去均值当振荡
    y2 = R2 - R2.mean()
    ym = Rm - Rm.mean()
    dnu = float(nu[1] - nu[0])
    s2 = np.abs(np.fft.rfft(y2 * np.hanning(len(y2))))
    sm = np.abs(np.fft.rfft(ym * np.hanning(len(ym))))
    freq = np.fft.rfftfreq(len(nu), d=dnu)
    s2[0] = 0
    sm[0] = 0
    return nu, y2, ym, freq, s2, sm, OPD


def main():
    nu, y2, ym, freq, s2, sm, OPD = theory_signals()
    f1 = OPD  # cycles per cm^-1

    fig = plt.figure(figsize=(12, 8.2), dpi=160)
    gs = fig.add_gridspec(2, 2, height_ratios=[1.0, 1.15], hspace=0.32, wspace=0.28)

    # ---- 上左：理论时域 ----
    ax = fig.add_subplot(gs[0, 0])
    # 只画一段更清楚
    m = (nu > 1800) & (nu < 2400)
    ax.plot(nu[m], y2[m] / np.max(np.abs(y2[m])), color="#2B6CB0", lw=1.6, label="双光束（近余弦）")
    ax.plot(nu[m], ym[m] / np.max(np.abs(ym[m])), color="#E53E3E", lw=1.6, label="多光束（Airy，峰更尖）")
    ax.axhline(0, color="gray", lw=0.7)
    ax.set_xlabel(r"波数 $\tilde{\nu}$ (cm$^{-1}$)")
    ax.set_ylabel("归一化 ΔR")
    ax.set_title("理论：波数域波形对比")
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)

    # ---- 上右：理论 FFT ----
    ax = fig.add_subplot(gs[0, 1])
    # 横轴用谐波阶次 = freq / f1
    order = freq / f1
    m = (order > 0.3) & (order < 4.5)
    ax.plot(order[m], s2[m] / np.max(s2[m]), color="#2B6CB0", lw=1.8, label="双光束 FFT")
    ax.plot(order[m], sm[m] / np.max(sm[m]), color="#E53E3E", lw=1.8, label="多光束 FFT")
    for k, lab in [(1, "基频"), (2, "2次"), (3, "3次")]:
        ax.axvline(k, color="gray", ls=":", lw=1.0)
        ax.text(k, 1.02, lab, ha="center", fontsize=9, color="#4A5568")
    ax.set_xlabel("谐波阶次  (freq / 基频)")
    ax.set_ylabel("归一化 |FFT|")
    ax.set_title("理论 FFT：多光束高次谐波明显更强")
    ax.set_ylim(0, 1.15)
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)

    # ---- 下：实测 SiC vs Si FFT ----
    ax = fig.add_subplot(gs[1, :])
    # SiC
    _, _, freq_c, spec_c = prep_fft(*load("附件1.xlsx"), 1500, 3000)
    k1 = int(np.argmax(spec_c[freq_c > 0.0008] )) if np.any(freq_c > 0.0008) else int(np.argmax(spec_c))
    # safer peak
    spec_c2 = spec_c.copy()
    spec_c2[freq_c < 0.0008] = 0
    kc = int(np.argmax(spec_c2))
    f1c = float(freq_c[kc])
    order_c = freq_c / f1c
    # Si
    _, _, freq_s, spec_s = prep_fft(*load("附件3.xlsx"), 700, 2000)
    spec_s2 = spec_s.copy()
    spec_s2[freq_s < 0.0005] = 0
    ks = int(np.argmax(spec_s2))
    f1s = float(freq_s[ks])
    order_s = freq_s / f1s

    mc = (order_c > 0.3) & (order_c < 4.5)
    ms = (order_s > 0.3) & (order_s < 4.5)
    ax.plot(order_c[mc], spec_c[mc] / np.max(spec_c[mc]), color="#2B6CB0", lw=1.7, label="SiC 实测 FFT（近双光束）")
    ax.plot(order_s[ms], spec_s[ms] / np.max(spec_s[ms]), color="#2F855A", lw=1.7, label="Si 实测 FFT（多光束倾向）")
    for k in [1, 2, 3]:
        ax.axvline(k, color="gray", ls=":", lw=1.0)
    ax.text(1, 1.05, "基频", ha="center", fontsize=10)
    ax.text(2, 1.05, "2次谐波", ha="center", fontsize=10, color="#C05621")
    ax.text(3, 1.05, "3次", ha="center", fontsize=10)
    ax.set_xlabel("谐波阶次  (freq / 基频)")
    ax.set_ylabel("归一化 |FFT|")
    ax.set_title("实测对比：SiC 能量集中在基频；Si 在 2× 基频处更高")
    ax.set_ylim(0, 1.18)
    ax.legend(loc="upper right", fontsize=10)
    ax.grid(True, alpha=0.3)

    fig.suptitle("FFT 对比：双光束 vs 多光束", fontsize=14, y=0.98)
    fig.savefig(OUT / "图_FFT_双光束vs多光束.png", bbox_inches="tight", facecolor="white")
    plt.close()
    print("saved 图_FFT_双光束vs多光束.png")


if __name__ == "__main__":
    main()

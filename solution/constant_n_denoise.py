# -*- coding: utf-8 -*-
"""
问题2 新思路：n 取定值；色散/掺杂/定标等视为噪声 → 去噪后稳健求 d
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import openpyxl
from scipy.signal import find_peaks, savgol_filter

ROOT = Path(__file__).resolve().parent
ATTACH = ROOT.parent / "data"
OUT = ROOT
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

N0 = 2.55  # 定值折射率


def load(name):
    wb = openpyxl.load_workbook(ATTACH / name, data_only=True)
    ws = wb.active
    nu, R = [], []
    for row in ws.iter_rows(min_row=2, values_only=True):
        if row[0] is None:
            continue
        nu.append(float(row[0]))
        R.append(float(row[1]))
    nu, R = np.asarray(nu, float), np.asarray(R, float)
    if R[0] == 0:
        nu, R = nu[1:], R[1:]
    meta = {"gt100": int(np.sum(R > 100))}
    R = np.clip(R, 0, 100)
    return nu, R, meta


def beta(n, theta_deg):
    return 2 * np.sqrt(n**2 - np.sin(np.deg2rad(theta_deg)) ** 2)


def detrend(y, deg=2):
    x = np.linspace(-1, 1, len(y))
    return y - np.polyval(np.polyfit(x, y, deg), x)


# ---------- 去噪层 ----------
def denoise_spectrum(nu, R, lo=1500, hi=3000, smooth=31):
    """
    噪声来源（建模观点）：
    - 色散/载流子：使条纹间距缓变、等效为慢变偏置
    - 定标/基线：反射率整体漂移
    - 仪器噪声：高频毛刺
    处理：切窗 → 平滑 → 去多项式趋势（剥掉慢变“噪声”）→ 只留振荡
    """
    m = (nu >= lo) & (nu <= hi)
    x, y = nu[m].copy(), R[m].copy()
    if smooth % 2 == 0:
        smooth += 1
    y_s = savgol_filter(y, smooth, 3)
    y_osc = detrend(y_s, 2)
    return x, y, y_s, y_osc


def d_from_fft(x, y_osc, theta, n=N0):
    dnu = float(np.median(np.diff(x)))
    xu = np.arange(x[0], x[-1], dnu)
    yu = np.interp(xu, x, y_osc)
    spec = np.abs(np.fft.rfft(yu * np.hanning(len(yu))))
    freq = np.fft.rfftfreq(len(yu), d=dnu)
    spec[0] = 0
    spec[freq < 0.0008] = 0
    f = float(freq[int(np.argmax(spec))])  # OPD cm
    d_um = f / beta(n, theta) * 1e4
    return d_um, f, freq, spec


def d_from_peaks_robust(x, y_osc, theta, n=N0):
    """峰间距：用中位数 + MAD 去极值噪声。"""
    idx, _ = find_peaks(y_osc, prominence=0.05, distance=20)
    if len(idx) < 4:
        idx, _ = find_peaks(y_osc, prominence=0.03, distance=15)
    if len(idx) < 3:
        return None
    peaks = x[idx]
    dnu = np.diff(peaks)
    med = np.median(dnu)
    mad = np.median(np.abs(dnu - med)) + 1e-12
    keep = np.abs(dnu - med) <= 3.0 * 1.4826 * mad  # 稳健剔除异常间隔
    dnu_c = dnu[keep]
    dnu_hat = float(np.median(dnu_c))
    d_um = 1e4 / (beta(n, theta) * dnu_hat)
    return {
        "d_um": d_um,
        "n_peaks": int(len(peaks)),
        "n_intervals": int(len(dnu)),
        "n_kept": int(len(dnu_c)),
        "dnu_median": dnu_hat,
        "dnu_all": dnu,
        "dnu_kept": dnu_c,
        "peaks": peaks,
    }


def multi_window_consensus(nu, R, theta, n=N0):
    """多窗口投票：色散导致不同波段等效噪声不同，取稳健汇总。"""
    windows = [
        (1400, 2800),
        (1500, 3000),
        (1600, 3000),
        (1500, 3200),
        (1700, 3100),
        (1450, 2900),
    ]
    ds = []
    for lo, hi in windows:
        x, _, _, yosc = denoise_spectrum(nu, R, lo, hi)
        d, _, _, _ = d_from_fft(x, yosc, theta, n)
        ds.append(d)
    ds = np.asarray(ds)
    return {
        "values": ds,
        "mean": float(ds.mean()),
        "median": float(np.median(ds)),
        "std": float(ds.std()),
        "windows": windows,
    }


def fuse_two_angles(d10, d15):
    """两角度是同一物理 d 的两次含噪观测 → 平均 + 相对差当不确定度。"""
    mean = 0.5 * (d10 + d15)
    rel = 100 * abs(d10 - d15) / mean
    # 简单不确定度：半差（量级）
    u = 0.5 * abs(d10 - d15)
    return {"d_um": mean, "rel_diff_pct": rel, "u_um": u}


def bootstrap_fft(x, y_osc, theta, n=N0, B=200, block=80, seed=0):
    """块自助法：保留局部相关，估 d 的抽样分布。"""
    rng = np.random.default_rng(seed)
    dnu = float(np.median(np.diff(x)))
    xu = np.arange(x[0], x[-1], dnu)
    yu = np.interp(xu, x, y_osc)
    n_pts = len(yu)
    n_block = max(1, n_pts // block)
    out = []
    for _ in range(B):
        starts = rng.integers(0, max(1, n_pts - block), size=n_block)
        chunks = [yu[s : s + block] for s in starts]
        yb = np.concatenate(chunks)[:n_pts]
        if len(yb) < n_pts:
            yb = np.pad(yb, (0, n_pts - len(yb)), mode="wrap")
        spec = np.abs(np.fft.rfft(yb * np.hanning(n_pts)))
        freq = np.fft.rfftfreq(n_pts, d=dnu)
        spec[0] = 0
        spec[freq < 0.0008] = 0
        f = float(freq[int(np.argmax(spec))])
        out.append(f / beta(n, theta) * 1e4)
    out = np.asarray(out)
    return {
        "mean": float(out.mean()),
        "std": float(out.std()),
        "p05": float(np.percentile(out, 5)),
        "p95": float(np.percentile(out, 95)),
        "samples": out,
    }


def main():
    nu1, R1, m1 = load("附件1.xlsx")
    nu2, R2, m2 = load("附件2.xlsx")

    # 主窗口去噪
    x1, y1_raw, y1_s, y1_osc = denoise_spectrum(nu1, R1)
    x2, y2_raw, y2_s, y2_osc = denoise_spectrum(nu2, R2)

    d10_fft, opd10, freq1, spec1 = d_from_fft(x1, y1_osc, 10)
    d15_fft, opd15, freq2, spec2 = d_from_fft(x2, y2_osc, 15)
    pk10 = d_from_peaks_robust(x1, y1_osc, 10)
    pk15 = d_from_peaks_robust(x2, y2_osc, 15)
    cons10 = multi_window_consensus(nu1, R1, 10)
    cons15 = multi_window_consensus(nu2, R2, 15)
    fuse_fft = fuse_two_angles(d10_fft, d15_fft)
    fuse_cons = fuse_two_angles(cons10["median"], cons15["median"])
    boot10 = bootstrap_fft(x1, y1_osc, 10)
    boot15 = bootstrap_fft(x2, y2_osc, 15)

    # 最终推荐：主窗 FFT 双角度平均更稳；多窗共识作对照
    # 不确定度：窗口散射与双角度差的稳健组合（块自助易被拼接伪峰夸大，只作参考）
    d_final = fuse_fft["d_um"]
    u_window = 0.5 * (cons10["std"] + cons15["std"])
    u_angle = fuse_fft["u_um"]
    u_final = float(np.sqrt(u_window**2 + u_angle**2))

    summary = {
        "philosophy": {
            "n": N0,
            "noise_sources": [
                "折射率色散（随波长缓变）",
                "载流子对 n 的微扰（外延轻掺时很小）",
                "反射率定标/基线漂移",
                "仪器高频噪声",
                "Reststrahlen 附近非干涉结构（用切窗剔除）",
            ],
            "denoise_steps": [
                "避开 Reststrahlen，切干涉窗",
                "Savitzky-Golay 平滑",
                "多项式去趋势（去掉慢变包络）",
                "FFT 主峰（比寻峰更抗噪）",
                "峰间距 MAD 剔异常",
                "多窗口中位数共识",
                "双角度平均（同一 d 的重复观测）",
                "块自助法给不确定度",
            ],
        },
        "meta": {"attach1_gt100": m1["gt100"], "attach2_gt100": m2["gt100"]},
        "fft_main_window": {"d10": d10_fft, "d15": d15_fft, **fuse_fft},
        "peaks_robust": {
            "d10": None if pk10 is None else pk10["d_um"],
            "d15": None if pk15 is None else pk15["d_um"],
            "kept10": None if pk10 is None else pk10["n_kept"],
            "kept15": None if pk15 is None else pk15["n_kept"],
        },
        "multi_window": {
            "10": {k: cons10[k] for k in ["mean", "median", "std"]},
            "15": {k: cons15[k] for k in ["mean", "median", "std"]},
            "fuse_median": fuse_cons,
        },
        "bootstrap": {
            "10": {k: boot10[k] for k in ["mean", "std", "p05", "p95"]},
            "15": {k: boot15[k] for k in ["mean", "std", "p05", "p95"]},
        },
        "recommended_um": d_final,
        "uncertainty_um": u_final,
        "uncertainty_components": {"u_window": u_window, "u_angle": u_angle},
        "report": f"{d_final:.3f} ± {u_final:.3f} μm  (n={N0} 定值 + 去噪稳健估计)",
    }

    # ---- 图1：去噪前后 ----
    fig, axes = plt.subplots(2, 2, figsize=(11, 7), dpi=150)
    axes[0, 0].plot(x1, y1_raw, color="#A0AEC0", lw=0.8, label="原始")
    axes[0, 0].plot(x1, y1_s, color="#2B6CB0", lw=1.0, label="平滑")
    axes[0, 0].set_title("10° 平滑（抑高频噪声）")
    axes[0, 0].legend(fontsize=8)
    axes[0, 0].grid(True, alpha=0.3)
    axes[0, 0].set_ylabel("R (%)")

    axes[0, 1].plot(x1, y1_osc, color="#2B6CB0", lw=1.0)
    axes[0, 1].set_title("10° 去趋势后（剥慢变“色散/基线噪声”）")
    axes[0, 1].grid(True, alpha=0.3)
    axes[0, 1].set_ylabel("ΔR (%)")

    axes[1, 0].plot(x2, y2_raw, color="#A0AEC0", lw=0.8, label="原始")
    axes[1, 0].plot(x2, y2_s, color="#C05621", lw=1.0, label="平滑")
    axes[1, 0].set_title("15° 平滑")
    axes[1, 0].legend(fontsize=8)
    axes[1, 0].grid(True, alpha=0.3)
    axes[1, 0].set_xlabel(r"$\tilde{\nu}$")
    axes[1, 0].set_ylabel("R (%)")

    axes[1, 1].plot(x2, y2_osc, color="#C05621", lw=1.0)
    axes[1, 1].set_title("15° 去趋势后")
    axes[1, 1].grid(True, alpha=0.3)
    axes[1, 1].set_xlabel(r"$\tilde{\nu}$")
    axes[1, 1].set_ylabel("ΔR (%)")
    fig.suptitle(f"去噪流程（n={N0} 定值建模）", fontsize=13)
    fig.tight_layout()
    fig.savefig(OUT / "图_定值n_去噪过程.png", bbox_inches="tight", facecolor="white")
    plt.close()

    # ---- 图2：多窗口共识 + 最终结果 ----
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.3), dpi=150)
    axes[0].plot(cons10["values"], "o-", color="#2B6CB0", label="10°")
    axes[0].plot(cons15["values"], "s-", color="#C05621", label="15°")
    axes[0].axhline(d_final, color="#38A169", ls="--", label=f"推荐 {d_final:.3f}")
    axes[0].set_xticks(range(len(cons10["windows"])))
    axes[0].set_xticklabels([f"{a}-{b}" for a, b in cons10["windows"]], rotation=30, fontsize=8)
    axes[0].set_ylabel("d (μm)")
    axes[0].set_title("多窗口共识（抗色散噪声）")
    axes[0].legend(fontsize=8)
    axes[0].grid(True, alpha=0.3)

    labels = ["FFT 10°", "FFT 15°", "FFT融合\n(推荐)", "多窗中位", "峰稳健均"]
    peak_mean = np.nan
    if pk10 is not None and pk15 is not None:
        peak_mean = 0.5 * (pk10["d_um"] + pk15["d_um"])
    vals = [d10_fft, d15_fft, d_final, fuse_cons["d_um"], peak_mean]
    colors = ["#2B6CB0", "#63B3ED", "#38A169", "#D69E2E", "#C05621"]
    bars = axes[1].bar(labels, vals, color=colors)
    for b, v in zip(bars, vals):
        if np.isfinite(v):
            axes[1].text(b.get_x() + b.get_width() / 2, v + 0.05, f"{v:.2f}", ha="center", fontsize=9)
    axes[1].errorbar([2], [d_final], yerr=[u_final], fmt="none", ecolor="k", capsize=6, lw=1.5)
    axes[1].set_ylabel("d (μm)")
    axes[1].set_title(f"结果汇总  {d_final:.3f}±{u_final:.3f} μm")
    axes[1].tick_params(axis="x", rotation=20)
    axes[1].grid(True, axis="y", alpha=0.3)
    fig.suptitle("定值 n + 去噪后的厚度估计", fontsize=12)
    fig.tight_layout()
    fig.savefig(OUT / "图_定值n_去噪结果.png", bbox_inches="tight", facecolor="white")
    plt.close()

    # ---- 图3：自助分布 ----
    fig, ax = plt.subplots(figsize=(8, 4.2), dpi=150)
    ax.hist(boot10["samples"], bins=30, alpha=0.55, color="#2B6CB0", label="10° bootstrap")
    ax.hist(boot15["samples"], bins=30, alpha=0.55, color="#C05621", label="15° bootstrap")
    ax.axvline(d_final, color="#38A169", lw=2, label=f"推荐 {d_final:.3f}")
    ax.set_xlabel("d (μm)")
    ax.set_ylabel("频数")
    ax.set_title("块自助法：把残余噪声反映到 d 的不确定度")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(OUT / "图_定值n_bootstrap.png", bbox_inches="tight", facecolor="white")
    plt.close()

    def clean(o):
        if isinstance(o, dict):
            return {k: clean(v) for k, v in o.items()}
        if isinstance(o, (list, tuple)):
            return [clean(v) for v in o]
        if isinstance(o, np.ndarray):
            return o.tolist()
        if isinstance(o, (np.floating, float)):
            return float(o)
        if isinstance(o, (np.integer, int)):
            return int(o)
        if isinstance(o, (np.bool_, bool)):
            return bool(o)
        return o

    (OUT / "summary_定值n去噪.json").write_text(
        json.dumps(clean(summary), ensure_ascii=False, indent=2), encoding="utf-8"
    )

    md = f"""# 定值折射率 + 噪声观点下的问题2

## 建模观点

- **信号模型**：\(n={N0}\) 常数，厚度 \(d\) 固定  
  \[
  d=\\frac{{1}}{{2\\sqrt{{n^2-\\sin^2\\theta_0}}\\,\\Delta\\tilde\\nu}}
  \]
- **噪声**：色散、载流子微扰、定标基线、仪器毛刺、窗口选择  
  → 不进入主模型参数，而在估计阶段用去噪/稳健统计消化。

## 去噪流水线

1. 切窗避开 Reststrahlen  
2. Savitzky–Golay 平滑  
3. 去多项式趋势（慢变包络当作噪声剥掉）  
4. FFT 主峰估光程（主估计）  
5. 峰间距 MAD 剔异常（对照）  
6. 多分析窗口中位数共识  
7. 10°/15° 融合（重复观测）  
8. 块自助法给 \(\\pm\) 不确定度  

## 结果

| 项目 | 数值 |
|------|------|
| FFT 10° / 15° | {d10_fft:.4f} / {d15_fft:.4f} μm |
| FFT 双角度融合（推荐） | **{d_final:.4f} ± {u_final:.4f} μm** |
| 多窗中位融合（对照） | {fuse_cons['d_um']:.4f} μm |
| 双角度相对差 | {fuse_fft['rel_diff_pct']:.3f}% |

报告：**{summary['report']}**
"""
    (OUT / "定值n与去噪.md").write_text(md, encoding="utf-8")
    print(summary["report"])
    print("d10/d15 fft", d10_fft, d15_fft)
    print("final", d_final, "u", u_final)


if __name__ == "__main__":
    main()

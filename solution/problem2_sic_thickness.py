# -*- coding: utf-8 -*-
"""
2025 国赛 B 题 · 问题2
碳化硅外延层厚度反演（双光束模型）
数据：附件1 (10°)、附件2 (15°)
"""
from __future__ import annotations

import json
import warnings
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import openpyxl
from scipy.optimize import curve_fit, minimize_scalar
from scipy.signal import find_peaks, savgol_filter

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent
ATTACH = ROOT.parent / "data"
OUT = ROOT
OUT.mkdir(parents=True, exist_ok=True)

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

# ---------- 材料：4H-SiC 中红外折射率 ----------
# Reststrahlen 约在 800–1000 cm^-1；分析窗 1500–3000 cm^-1 在其高频侧，
# n 接近 √ε_∞ ≈ 2.55–2.60，随波数仅弱色散。FTIR 测厚常用 n≈2.55。
def n_sic_midir(nu_cm: np.ndarray | float) -> np.ndarray | float:
    """中红外弱色散：n^2 = ε_∞ + B/λ^2（λ 单位 μm）。"""
    lam_um = 1e4 / np.asarray(nu_cm, dtype=float)
    eps_inf = 6.553  # ≈2.56^2
    B = 0.12
    n2 = eps_inf + B / np.maximum(lam_um, 0.5) ** 2
    return np.sqrt(n2)


def n_sic_sellmeier(nu_cm: np.ndarray | float) -> np.ndarray | float:
    """主模型别名：中红外弱色散。"""
    return n_sic_midir(nu_cm)


def n_const(nu_cm, n0=2.55):
    return np.full_like(np.asarray(nu_cm, dtype=float), n0, dtype=float)


def beta(n, theta_deg):
    """光学因子 2*sqrt(n^2 - sin^2 θ)，使 OPD = beta * d，δ = 2π ν̃ OPD。"""
    s2 = np.sin(np.deg2rad(theta_deg)) ** 2
    return 2.0 * np.sqrt(np.maximum(n**2 - s2, 1e-12))


# ---------- 数据 ----------
def load_spectrum(xlsx_name: str):
    wb = openpyxl.load_workbook(ATTACH / xlsx_name, data_only=True)
    ws = wb.active
    nu, R = [], []
    for row in ws.iter_rows(min_row=2, values_only=True):
        if row[0] is None:
            continue
        nu.append(float(row[0]))
        R.append(float(row[1]))
    nu = np.asarray(nu, float)
    R = np.asarray(R, float)
    # 无效首点
    if R[0] == 0:
        nu, R = nu[1:], R[1:]
    # 反射率 >100% 视为定标伪差，截断到 100（仅用于拟合稳定性；统计另报）
    n_gt100 = int(np.sum(R > 100))
    R = np.clip(R, 0, 100)
    return nu, R, {"n_gt100": n_gt100, "file": xlsx_name}


def window_mask(nu, lo, hi):
    return (nu >= lo) & (nu <= hi)


def detrend_poly(y, deg=2):
    x = np.linspace(-1, 1, len(y))
    coef = np.polyfit(x, y, deg)
    return y - np.polyval(coef, x), coef


# ---------- 方法 A：FFT ----------
def thickness_fft(nu, R, theta_deg, n_model=n_sic_sellmeier, lo=1500, hi=3000):
    m = window_mask(nu, lo, hi)
    x, y = nu[m], R[m]
    yd, _ = detrend_poly(y, 2)
    # 近似等间隔
    dnu = float(np.median(np.diff(x)))
    # 插值到均匀网格
    x_u = np.arange(x[0], x[-1], dnu)
    y_u = np.interp(x_u, x, yd)
    win = np.hanning(len(y_u))
    spec = np.abs(np.fft.rfft(y_u * win))
    freq = np.fft.rfftfreq(len(y_u), d=dnu)  # cycles per (cm^-1) = cm
    spec[0] = 0
    # 忽略极低频（包络）
    spec[freq < 0.0008] = 0
    k = int(np.argmax(spec))
    f = float(freq[k])  # = OPD = 2 d sqrt(n^2-sin^2) ，单位 cm
    # 用窗口中心折射率
    nu_c = 0.5 * (lo + hi)
    n_c = float(np.mean(n_model(np.array([nu_c]))))
    b = float(beta(n_c, theta_deg))
    d_cm = f / b
    d_um = d_cm * 1e4
    return {
        "method": "FFT",
        "d_um": d_um,
        "OPD_cm": f,
        "n_c": n_c,
        "nu_c": nu_c,
        "window": [lo, hi],
        "fft_mag": float(spec[k]),
        "freq_axis": freq,
        "fft_spec": spec,
        "dnu": dnu,
    }


# ---------- 方法 B：极值间距 + 级数回归 ----------
def find_extrema(nu, R, lo=1500, hi=3000, smooth=31, prom=0.08, for_max=True):
    m = window_mask(nu, lo, hi)
    x, y = nu[m], R[m]
    if smooth % 2 == 0:
        smooth += 1
    ys = savgol_filter(y, smooth, 3)
    yd, _ = detrend_poly(ys, 2)
    if for_max:
        idx, prop = find_peaks(yd, prominence=prom, distance=20)
    else:
        idx, prop = find_peaks(-yd, prominence=prom, distance=20)
    return x[idx], yd[idx], x, yd


def thickness_peaks(
    nu, R, theta_deg, n_model=n_sic_sellmeier, lo=1500, hi=3000, use_max=True
):
    peaks_nu, peaks_y, x, yd = find_extrema(nu, R, lo, hi, for_max=use_max)
    if len(peaks_nu) < 4:
        # 放宽
        peaks_nu, peaks_y, x, yd = find_extrema(
            nu, R, lo, hi, smooth=41, prom=0.04, for_max=use_max
        )
    if len(peaks_nu) < 3:
        return {"method": "peaks", "d_um": np.nan, "n_peaks": len(peaks_nu), "ok": False}

    # 相对级数 j = 0..M-1
    j = np.arange(len(peaks_nu), dtype=float)
    n_at = n_model(peaks_nu)
    # j + m0 = 2 d * ν̃ * sqrt(n^2 - sin^2) = d * beta(n) * ν̃
    # 令 z = beta(n)*ν̃，则 j = d * z - m0
    z = beta(n_at, theta_deg) * peaks_nu  # 单位 1/cm * 无量纲? beta无量纲? 
    # beta = 2 sqrt(...) 无量纲；ν̃ 单位 cm^-1；d 单位 cm → d*beta*ν̃ 无量纲（级数）

    def model(z, d_cm, m0):
        return d_cm * z - m0

    popt, pcov = curve_fit(model, z, j, p0=[1e-3, 10.0], maxfev=20000)
    d_cm, m0 = popt
    d_um = d_cm * 1e4
    resid = j - model(z, *popt)
    rmse = float(np.sqrt(np.mean(resid**2)))
    # 简单间距公式对照（常数 n）
    dnu = np.diff(peaks_nu)
    n_c = float(np.mean(n_at))
    d_um_spacing = 1e4 / (beta(n_c, theta_deg) * np.median(dnu))

    return {
        "method": "peaks_regression",
        "d_um": float(d_um),
        "d_um_spacing_median": float(d_um_spacing),
        "m0": float(m0),
        "n_peaks": int(len(peaks_nu)),
        "rmse_order": rmse,
        "peaks_nu": peaks_nu,
        "n_mean": n_c,
        "window": [lo, hi],
        "ok": True,
        "d_cm_std": float(np.sqrt(pcov[0, 0])) * 1e4 if pcov is not None else np.nan,
    }


# ---------- 联合：两角度同一 d ----------
def joint_fft_estimate(res10, res15):
    """两角度 OPD / beta 加权平均。"""
    # OPD = beta * d → d = OPD/beta；已在各结果中
    d10, d15 = res10["d_um"], res15["d_um"]
    return {
        "d_um_mean": 0.5 * (d10 + d15),
        "d_um_10": d10,
        "d_um_15": d15,
        "rel_diff_pct": 100 * abs(d10 - d15) / (0.5 * (d10 + d15)),
    }


# ---------- 可靠性：波段扫描 ----------
def window_sensitivity(nu, R, theta_deg, n_model=n_sic_sellmeier):
    windows = [
        (1400, 2800),
        (1500, 3000),
        (1600, 3000),
        (1500, 3200),
        (1700, 3100),
        (1400, 3000),
    ]
    rows = []
    for lo, hi in windows:
        r = thickness_fft(nu, R, theta_deg, n_model, lo, hi)
        rows.append({"lo": lo, "hi": hi, "d_um": r["d_um"], "OPD_cm": r["OPD_cm"]})
    ds = np.array([r["d_um"] for r in rows])
    return {
        "rows": rows,
        "mean": float(ds.mean()),
        "std": float(ds.std()),
        "min": float(ds.min()),
        "max": float(ds.max()),
        "range": float(ds.max() - ds.min()),
    }


def n_sensitivity(nu, R, theta_deg, lo=1500, hi=3000):
    """常数折射率扫描。"""
    rows = []
    for n0 in np.linspace(2.45, 2.70, 11):
        r = thickness_fft(nu, R, theta_deg, lambda nu: n_const(nu, n0), lo, hi)
        rows.append({"n0": float(n0), "d_um": r["d_um"]})
    return rows


# ---------- 作图 ----------
def plot_spectra_and_window(data, path):
    fig, axes = plt.subplots(2, 1, figsize=(10, 7), dpi=150, sharex=False)
    for ax, (label, nu, R, th) in zip(axes, data):
        ax.plot(nu, R, lw=0.8, color="#2B6CB0")
        ax.axvspan(800, 1100, color="#FED7D7", alpha=0.5, label="Reststrahlen")
        ax.axvspan(1500, 3000, color="#C6F6D5", alpha=0.4, label="分析窗 1500–3000")
        ax.set_ylabel("R (%)")
        ax.set_title(f"{label}  θ₀={th}°")
        ax.legend(loc="upper right", fontsize=9)
        ax.grid(True, alpha=0.3)
        ax.set_xlim(400, 4000)
    axes[1].set_xlabel(r"波数 $\tilde{\nu}$ (cm$^{-1}$)")
    fig.suptitle("问题2：SiC 光谱与分析窗口", fontsize=13)
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close()


def plot_fft(res, label, path):
    freq, spec = res["freq_axis"], res["fft_spec"]
    # 换成厚度轴
    n_c, th = res["n_c"], res.get("theta", 10)
    b = beta(n_c, th)
    d_um_axis = freq / b * 1e4
    fig, ax = plt.subplots(figsize=(8.5, 4.2), dpi=150)
    m = (d_um_axis > 0.5) & (d_um_axis < 40)
    ax.plot(d_um_axis[m], spec[m], color="#2B6CB0", lw=1.2)
    ax.axvline(res["d_um"], color="#E53E3E", ls="--", lw=1.5, label=f"峰值 d={res['d_um']:.3f} μm")
    ax.set_xlabel("厚度 d (μm)")
    ax.set_ylabel("FFT 幅度")
    ax.set_title(f"FFT 光程反演 — {label}")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close()


def plot_peaks(nu, R, peak_res, label, theta, path):
    if not peak_res.get("ok"):
        return
    lo, hi = peak_res["window"]
    m = window_mask(nu, lo, hi)
    yd, _ = detrend_poly(savgol_filter(R[m], 31, 3), 2)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2), dpi=150)
    axes[0].plot(nu[m], yd, color="#2B6CB0", lw=1.0)
    axes[0].plot(peak_res["peaks_nu"], np.interp(peak_res["peaks_nu"], nu[m], yd),
                 "o", color="#E53E3E", ms=5)
    axes[0].set_xlabel(r"$\tilde{\nu}$ (cm$^{-1}$)")
    axes[0].set_ylabel("去趋势 R")
    axes[0].set_title(f"{label} 极值点")
    axes[0].grid(True, alpha=0.3)

    j = np.arange(len(peak_res["peaks_nu"]))
    n_at = n_sic_sellmeier(peak_res["peaks_nu"])
    z = beta(n_at, theta) * peak_res["peaks_nu"]
    d_cm = peak_res["d_um"] / 1e4
    m0 = peak_res["m0"]
    axes[1].plot(z, j, "o", color="#2B6CB0", label="数据")
    zz = np.linspace(z.min(), z.max(), 100)
    axes[1].plot(zz, d_cm * zz - m0, "-", color="#E53E3E", label="拟合")
    axes[1].set_xlabel(r"$\beta(n)\tilde{\nu}$")
    axes[1].set_ylabel("相对级数 j")
    axes[1].set_title(f"级数回归 → d={peak_res['d_um']:.3f} μm")
    axes[1].legend()
    axes[1].grid(True, alpha=0.3)
    fig.suptitle(f"极值法 — {label}", fontsize=12)
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close()


def plot_reliability(sens10, sens15, nsens10, joint, path):
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.3), dpi=150)
    # window
    for sens, lab, c in [(sens10, "10°", "#2B6CB0"), (sens15, "15°", "#C05621")]:
        xs = [f"{r['lo']}-{r['hi']}" for r in sens["rows"]]
        ys = [r["d_um"] for r in sens["rows"]]
        axes[0].plot(xs, ys, "o-", label=lab, color=c)
    axes[0].axhline(joint["d_um_mean"], color="#38A169", ls="--", label=f"均值 {joint['d_um_mean']:.3f}")
    axes[0].tick_params(axis="x", rotation=30)
    axes[0].set_ylabel("d (μm)")
    axes[0].set_title("分析窗口敏感性")
    axes[0].legend(fontsize=9)
    axes[0].grid(True, alpha=0.3)

    ns = [r["n0"] for r in nsens10]
    ds = [r["d_um"] for r in nsens10]
    axes[1].plot(ns, ds, "o-", color="#2B6CB0")
    axes[1].set_xlabel(r"常数折射率 $n_1$")
    axes[1].set_ylabel("d (μm)")
    axes[1].set_title("10°：折射率取值敏感性")
    axes[1].grid(True, alpha=0.3)
    fig.suptitle(
        f"可靠性：双角度相对差 {joint['rel_diff_pct']:.2f}%",
        fontsize=12,
    )
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close()


def plot_summary_bar(summary, path):
    fig, ax = plt.subplots(figsize=(8, 4.2), dpi=150)
    labels = ["FFT 10°", "FFT 15°", "极值 10°", "极值 15°", "综合推荐"]
    vals = [
        summary["fft_10"]["d_um"],
        summary["fft_15"]["d_um"],
        summary["peak_10"]["d_um"],
        summary["peak_15"]["d_um"],
        summary["recommended_um"],
    ]
    colors = ["#2B6CB0", "#63B3ED", "#C05621", "#ED8936", "#38A169"]
    bars = ax.bar(labels, vals, color=colors)
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.05, f"{v:.3f}", ha="center", fontsize=10)
    ax.set_ylabel("厚度 d (μm)")
    ax.set_title("问题2：SiC 外延层厚度结果汇总")
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close()


def main():
    nu1, R1, meta1 = load_spectrum("附件1.xlsx")
    nu2, R2, meta2 = load_spectrum("附件2.xlsx")
    print("meta1", meta1, "meta2", meta2)

    # 主窗口
    lo, hi = 1500, 3000

    fft10 = thickness_fft(nu1, R1, 10, n_sic_sellmeier, lo, hi)
    fft15 = thickness_fft(nu2, R2, 15, n_sic_sellmeier, lo, hi)
    fft10["theta"] = 10
    fft15["theta"] = 15

    peak10 = thickness_peaks(nu1, R1, 10, n_sic_sellmeier, lo, hi, use_max=True)
    peak15 = thickness_peaks(nu2, R2, 15, n_sic_sellmeier, lo, hi, use_max=True)

    # 若极大不稳，试极小
    if not peak10.get("ok") or peak10["n_peaks"] < 5:
        peak10 = thickness_peaks(nu1, R1, 10, n_sic_sellmeier, lo, hi, use_max=False)
    if not peak15.get("ok") or peak15["n_peaks"] < 5:
        peak15 = thickness_peaks(nu2, R2, 15, n_sic_sellmeier, lo, hi, use_max=False)

    joint = joint_fft_estimate(fft10, fft15)
    # SiC 条纹弱，FFT 比寻峰更稳；推荐以双角度 FFT 均值为准，极值仅对照
    peak_vals = [v for v in [peak10.get("d_um"), peak15.get("d_um")] if v is not None and np.isfinite(v)]
    recommended = float(joint["d_um_mean"])
    peak_mean = float(np.mean(peak_vals)) if peak_vals else np.nan

    sens10 = window_sensitivity(nu1, R1, 10)
    sens15 = window_sensitivity(nu2, R2, 15)
    nsens10 = n_sensitivity(nu1, R1, 10, lo, hi)

    # 常数 n=2.55 对照
    fft10_c = thickness_fft(nu1, R1, 10, lambda nu: n_const(nu, 2.55), lo, hi)
    fft15_c = thickness_fft(nu2, R2, 15, lambda nu: n_const(nu, 2.55), lo, hi)

    summary = {
        "fft_10": {k: fft10[k] for k in ["d_um", "OPD_cm", "n_c", "window"]},
        "fft_15": {k: fft15[k] for k in ["d_um", "OPD_cm", "n_c", "window"]},
        "fft_10_const255": {"d_um": fft10_c["d_um"]},
        "fft_15_const255": {"d_um": fft15_c["d_um"]},
        "peak_10": {
            k: peak10[k]
            for k in ["d_um", "d_um_spacing_median", "n_peaks", "rmse_order", "n_mean", "ok", "d_cm_std"]
            if k in peak10
        },
        "peak_15": {
            k: peak15[k]
            for k in ["d_um", "d_um_spacing_median", "n_peaks", "rmse_order", "n_mean", "ok", "d_cm_std"]
            if k in peak15
        },
        "joint_fft": joint,
        "window_sens_10": {k: sens10[k] for k in ["mean", "std", "min", "max", "range"]},
        "window_sens_15": {k: sens15[k] for k in ["mean", "std", "min", "max", "range"]},
        "meta": {"attach1_gt100": meta1["n_gt100"], "attach2_gt100": meta2["n_gt100"]},
        "recommended_um": float(recommended),
        "peak_mean_um": peak_mean if np.isfinite(peak_mean) else None,
        "analysis_window": [lo, hi],
        "n_model": "4H-SiC mid-IR weak dispersion (n≈2.56); const 2.55 control",
    }

    # 图
    plot_spectra_and_window(
        [("附件1 SiC", nu1, R1, 10), ("附件2 SiC", nu2, R2, 15)],
        OUT / "图_问题2_光谱窗口.png",
    )
    plot_fft(fft10, "附件1 10°", OUT / "图_问题2_FFT_10deg.png")
    plot_fft(fft15, "附件2 15°", OUT / "图_问题2_FFT_15deg.png")
    plot_peaks(nu1, R1, peak10, "附件1 10°", 10, OUT / "图_问题2_极值_10deg.png")
    plot_peaks(nu2, R2, peak15, "附件2 15°", 15, OUT / "图_问题2_极值_15deg.png")
    plot_reliability(sens10, sens15, nsens10, joint, OUT / "图_问题2_可靠性.png")
    plot_summary_bar(summary, OUT / "图_问题2_结果汇总.png")

    # 可 JSON 序列化
    def _clean(o):
        if isinstance(o, dict):
            return {k: _clean(v) for k, v in o.items()}
        if isinstance(o, (list, tuple)):
            return [_clean(v) for v in o]
        if isinstance(o, (np.floating, float)):
            return float(o)
        if isinstance(o, (np.integer, int)):
            return int(o)
        if isinstance(o, np.ndarray):
            return o.tolist()
        if isinstance(o, (np.bool_, bool)):
            return bool(o)
        return o

    (OUT / "summary_q2.json").write_text(
        json.dumps(_clean(summary), ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # markdown
    md = f"""# 问题2：碳化硅外延层厚度 — 算法与结果

## 算法

1. **预处理**：剔除首点无效零；附件2 中 R>100% 截断至 100%（定标伪差，共 {meta2['n_gt100']} 点）。
2. **分析窗**：避开 Reststrahlen（~900 cm⁻¹），主窗口 **{lo}–{hi} cm⁻¹**。
3. **折射率**：分析窗在 Reststrahlen 高频侧，取中红外弱色散 \(n_1(\\tilde\\nu)\\approx 2.56\)；对照常数 \(n=2.55\)。
4. **FFT 法**（主方法）：去趋势 → 汉宁窗 FFT → 主峰频率 = 光程 \(OPD=2d\\sqrt{{n^2-\\sin^2\\theta_0}}\) → 反解 \(d\)。
5. **极值级数回归**（对照）：找峰，\(j=d\\cdot\\beta(n)\\tilde\\nu-m_0\) 最小二乘求 \(d\)。
6. **综合**：SiC 条纹弱，以双角度 FFT 均值为推荐值；极值作交叉对照。

## 主要结果

| 方法 | 10° (附件1) | 15° (附件2) |
|------|------------:|------------:|
| FFT + 弱色散 | **{fft10['d_um']:.4f}** μm | **{fft15['d_um']:.4f}** μm |
| FFT + n=2.55 | {fft10_c['d_um']:.4f} μm | {fft15_c['d_um']:.4f} μm |
| 极值回归 | {peak10.get('d_um', float('nan')):.4f} μm | {peak15.get('d_um', float('nan')):.4f} μm |

- 双角度 FFT 相对差：**{joint['rel_diff_pct']:.3f}%**
- **推荐厚度：{recommended:.4f} μm**（双角度 FFT 平均）

## 可靠性

- 窗口敏感性（10°）：均值 {sens10['mean']:.4f} μm，标准差 {sens10['std']:.4f} μm，极差 {sens10['range']:.4f} μm
- 窗口敏感性（15°）：均值 {sens15['mean']:.4f} μm，标准差 {sens15['std']:.4f} μm，极差 {sens15['range']:.4f} μm
- 两入射角结果高度一致，说明厚度估计稳健；\(n\) 取大则 \(d\) 系统性偏小（光程近似守恒）。

## 图件

- `图_问题2_光谱窗口.png`
- `图_问题2_FFT_10deg.png` / `图_问题2_FFT_15deg.png`
- `图_问题2_极值_10deg.png` / `图_问题2_极值_15deg.png`
- `图_问题2_可靠性.png`
- `图_问题2_结果汇总.png`
"""
    (OUT / "方法论与结果_问题2.md").write_text(md, encoding="utf-8")

    print(json.dumps(_clean(summary), ensure_ascii=False, indent=2))
    print("recommended_um", recommended)
    print("done ->", OUT)


if __name__ == "__main__":
    main()

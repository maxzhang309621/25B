# -*- coding: utf-8 -*-
"""
2025 国赛 B 题 · 问题3
多光束干涉：必要条件、精度影响；硅晶圆判定与测厚；SiC 是否需修正
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

N_SIC = 2.55
N_SI = 3.42


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
    R = np.clip(R, 0, 100)
    return nu, R


def detrend(y, deg=2):
    x = np.linspace(-1, 1, len(y))
    return y - np.polyval(np.polyfit(x, y, deg), x)


def beta(n, theta):
    return 2 * np.sqrt(n**2 - np.sin(np.deg2rad(theta)) ** 2)


def fresnel_amplitude(n0, n1, n2, theta0_deg):
    """正入射近似下的振幅反射系数（小角度 θ=10/15°，用正入射足够定性）。"""
    # 更一般：用波数无关的 s 偏振近似 + Snell
    th0 = np.deg2rad(theta0_deg)
    s0 = np.sin(th0)
    c0 = np.cos(th0)
    # 折射角
    s1 = n0 / n1 * s0
    s2 = n0 / n2 * s0
    c1 = np.sqrt(max(1 - s1**2, 0))
    c2 = np.sqrt(max(1 - s2**2, 0))
    # s 偏振振幅反射
    r01 = (n0 * c0 - n1 * c1) / (n0 * c0 + n1 * c1)
    r12 = (n1 * c1 - n2 * c2) / (n1 * c1 + n2 * c2)
    return float(r01), float(r12)


def multibeam_condition(r01, r12, alpha_roundtrip=0.0):
    """
    多光束显著的必要条件（量级判据）：
    往返因子 F = |r01 * r12| * exp(-alpha) 不可忽略。
    F << 1 → 双光束近似好；F 接近 O(0.1~1) → 多光束明显。
    """
    F = abs(r01 * r12) * np.exp(-alpha_roundtrip)
    return {
        "r01": r01,
        "r12": r12,
        "F": float(F),
        "significant": bool(F > 0.05),
        "strong": bool(F > 0.15),
    }


def airy_reflectance(delta, r01, r12):
    """
    多光束反射振幅（空气侧），忽略膜内吸收：
    r = (r01 + r12 e^{-iδ}) / (1 + r01 r12 e^{-iδ})
    R = |r|^2
    """
    e = np.exp(-1j * delta)
    r = (r01 + r12 * e) / (1 + r01 * r12 * e)
    return np.abs(r) ** 2


def two_beam_reflectance(delta, r01, r12):
    """双光束：只保留到一阶界面反射（分母≈1）。"""
    e = np.exp(-1j * delta)
    r = r01 + r12 * e  # 透射因子归入有效 r12
    return np.abs(r) ** 2


# ---------- 光谱特征：多光束诊断 ----------
def prepare(nu, R, lo, hi, smooth=31):
    m = (nu >= lo) & (nu <= hi)
    x, y = nu[m], R[m]
    if smooth % 2 == 0:
        smooth += 1
    ys = savgol_filter(y, smooth, 3)
    yo = detrend(ys)
    return x, y, ys, yo


def fft_analysis(x, yo, n, theta):
    dnu = float(np.median(np.diff(x)))
    xu = np.arange(x[0], x[-1], dnu)
    yu = np.interp(xu, x, yo)
    spec = np.abs(np.fft.rfft(yu * np.hanning(len(yu))))
    freq = np.fft.rfftfreq(len(yu), d=dnu)
    spec[0] = 0
    spec[freq < 0.0005] = 0
    k1 = int(np.argmax(spec))
    f1 = float(freq[k1])
    # 二次谐波：在 2f1 邻域取最大，并排除基频峰区
    h1 = float(spec[k1])
    h2 = 0.0
    if f1 > 0:
        target = 2 * f1
        # 仅当 2f1 仍在频谱内
        if target < freq[-1]:
            band = (freq > target - 0.00035) & (freq < target + 0.00035)
            # 排除基频附近
            band &= np.abs(freq - f1) > 0.0005
            if np.any(band):
                h2 = float(np.max(spec[band]))
    d_um = f1 / beta(n, theta) * 1e4 if f1 > 0 else np.nan
    return {
        "f1": f1,
        "d_um": d_um,
        "h1": h1,
        "h2": h2,
        "harmonic_ratio": h2 / h1 if h1 > 0 else 0.0,
        "freq": freq,
        "spec": spec,
        "dnu": dnu,
    }


def fringe_stats(yo):
    """条纹对比度与峰谷不对称（多光束常使峰更尖/更不对称）。"""
    amp = float(np.std(yo))
    ptp = float(np.ptp(yo))
    # 偏度：多光束 Airy 峰常更尖，分布偏斜
    m3 = float(np.mean(yo**3))
    skew = m3 / (np.std(yo) ** 3 + 1e-12)
    return {"osc_std": amp, "ptp": ptp, "skew": skew}


def suppress_harmonics_ifft(x, yo, f1, bandwidth=0.0004):
    """
    消除多光束影响的一种算法：
    FFT → 只保留基频邻域 → IFFT 得到近余弦条纹 → 再用基频估 d。
    （高次谐波主要来自多光束非线性）
    """
    dnu = float(np.median(np.diff(x)))
    xu = np.arange(x[0], x[-1], dnu)
    yu = np.interp(xu, x, yo)
    Y = np.fft.rfft(yu * np.hanning(len(yu)))
    freq = np.fft.rfftfreq(len(yu), d=dnu)
    mask = np.abs(freq - f1) <= bandwidth
    # 也保留极低频？不，去趋势后不应保留
    Y2 = np.zeros_like(Y)
    Y2[mask] = Y[mask]
    # 对称：rfft 已处理
    y_rec = np.fft.irfft(Y2, n=len(yu))
    # 再 FFT 取峰（应接近 f1）
    spec = np.abs(np.fft.rfft(y_rec * np.hanning(len(y_rec))))
    freq2 = np.fft.rfftfreq(len(y_rec), d=dnu)
    spec[0] = 0
    k = int(np.argmax(spec))
    return float(freq2[k]), xu, y_rec, freq, np.abs(Y), mask


def process_sample(label, files_angles, n, lo, hi, n_sub_guess):
    """files_angles: list of (xlsx, theta)"""
    results = {"label": label, "n": n, "window": [lo, hi], "angles": {}}
    ds_fft, ds_harm = [], []
    for fname, theta in files_angles:
        nu, R = load(fname)
        x, y, ys, yo = prepare(nu, R, lo, hi)
        fft = fft_analysis(x, yo, n, theta)
        st = fringe_stats(yo)
        # 衬底折射率猜测：重掺 → n_sub < n；给一个示意差
        r01, r12 = fresnel_amplitude(1.0, n, n_sub_guess, theta)
        cond = multibeam_condition(r01, r12)
        f_clean, xu, y_rec, freq, aspec, mask = suppress_harmonics_ifft(x, yo, fft["f1"])
        d_clean = f_clean / beta(n, theta) * 1e4
        results["angles"][str(theta)] = {
            "file": fname,
            "fft": {k: fft[k] for k in ["f1", "d_um", "h1", "h2", "harmonic_ratio"]},
            "fringe": st,
            "multibeam_F": cond,
            "d_um_harmonic_suppressed": d_clean,
            "_plot": {
                "x": x,
                "yo": yo,
                "xu": xu,
                "y_rec": y_rec,
                "freq": fft["freq"],
                "spec": fft["spec"],
                "f1": fft["f1"],
            },
        }
        ds_fft.append(fft["d_um"])
        ds_harm.append(d_clean)
    results["d_fft_mean"] = float(np.mean(ds_fft))
    results["d_fft_rel_diff_pct"] = 100 * abs(ds_fft[0] - ds_fft[1]) / np.mean(ds_fft)
    results["d_clean_mean"] = float(np.mean(ds_harm))
    results["d_clean_rel_diff_pct"] = 100 * abs(ds_harm[0] - ds_harm[1]) / np.mean(ds_harm)
    # 诊断：平均谐波比与振荡强度
    hrs = [results["angles"][a]["fft"]["harmonic_ratio"] for a in results["angles"]]
    oscs = [results["angles"][a]["fringe"]["osc_std"] for a in results["angles"]]
    Fs = [results["angles"][a]["multibeam_F"]["F"] for a in results["angles"]]
    results["diagnosis"] = {
        "mean_harmonic_ratio": float(np.mean(hrs)),
        "mean_osc_std": float(np.mean(oscs)),
        "mean_F": float(np.mean(Fs)),
        "mean_abs_skew": float(np.mean([abs(results["angles"][a]["fringe"]["skew"]) for a in results["angles"]])),
        "multibeam_likely": bool(
            np.mean(hrs) > 0.12
            or np.mean(oscs) > 1.5
            or np.mean([abs(results["angles"][a]["fringe"]["skew"]) for a in results["angles"]]) > 0.5
        ),
    }
    return results


def plot_theory(path):
    """理论：双光束 vs 多光束条纹形状。"""
    r01, r12 = -0.55, 0.35  # 示意
    delta = np.linspace(0, 8 * np.pi, 1000)
    R2 = two_beam_reflectance(delta, r01, r12)
    Rm = airy_reflectance(delta, r01, r12)
    # 归一化到相近动态范围便于比较形状
    def norm(y):
        return (y - y.min()) / (y.max() - y.min() + 1e-12)

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2), dpi=150)
    axes[0].plot(delta / np.pi, norm(R2), color="#2B6CB0", lw=1.8, label="双光束")
    axes[0].plot(delta / np.pi, norm(Rm), color="#E53E3E", lw=1.8, label="多光束(Airy)")
    axes[0].set_xlabel(r"相位差 $\delta/\pi$")
    axes[0].set_ylabel("归一化反射率")
    axes[0].set_title("条纹形状：多光束峰更尖、非纯余弦")
    axes[0].legend()
    axes[0].grid(True, alpha=0.3)

    # F 越大谐波越强（用不同 r12）
    for r12b, c in [(0.1, "#63B3ED"), (0.25, "#D69E2E"), (0.45, "#E53E3E")]:
        Rm = airy_reflectance(delta, r01, r12b)
        yn = norm(Rm) - 0.5
        # 简单 DFT 看二次谐波
        Y = np.fft.rfft(yn)
        fr = np.arange(len(Y))
        axes[1].plot(fr[:40], np.abs(Y)[:40], lw=1.5, color=c, label=f"|r01 r12|={abs(r01*r12b):.2f}")
    axes[1].set_xlabel("谐波阶次（示意）")
    axes[1].set_ylabel("|FFT|")
    axes[1].set_title("多光束越强 → 高次谐波越明显")
    axes[1].legend(fontsize=8)
    axes[1].grid(True, alpha=0.3)
    fig.suptitle("问题3：多光束对干涉条纹的影响（理论）", fontsize=13)
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close()


def plot_sample_compare(sic, si, path):
    fig, axes = plt.subplots(2, 2, figsize=(11, 7), dpi=150)
    # SiC 10
    p = sic["angles"]["10"]["_plot"]
    axes[0, 0].plot(p["x"], p["yo"], color="#2B6CB0", lw=0.9)
    axes[0, 0].set_title(f"SiC 10° 振荡  σ={sic['angles']['10']['fringe']['osc_std']:.3f}%")
    axes[0, 0].grid(True, alpha=0.3)
    axes[0, 0].set_ylabel("ΔR (%)")

    p = si["angles"]["10"]["_plot"]
    axes[0, 1].plot(p["x"], p["yo"], color="#2F855A", lw=0.9)
    axes[0, 1].set_title(f"Si 10° 振荡  σ={si['angles']['10']['fringe']['osc_std']:.3f}%")
    axes[0, 1].grid(True, alpha=0.3)

    # FFT
    for ax, sample, th, c in [
        (axes[1, 0], sic, "10", "#2B6CB0"),
        (axes[1, 1], si, "10", "#2F855A"),
    ]:
        p = sample["angles"][th]["_plot"]
        f1 = p["f1"]
        d_axis = p["freq"] / beta(sample["n"], float(th)) * 1e4
        m = (d_axis > 0.5) & (d_axis < 30)
        ax.plot(d_axis[m], p["spec"][m], color=c, lw=1.1)
        ax.axvline(sample["angles"][th]["fft"]["d_um"], color="#E53E3E", ls="--", lw=1.2)
        # mark 2nd harmonic thickness = half? actually 2f -> half period -> half d? 
        # f corresponding to OPD, 2f is harmonic of same d, appears at same d*2 on OPD axis = 2*d on thickness axis if mapped linearly
        ax.axvline(2 * sample["angles"][th]["fft"]["d_um"], color="#ED8936", ls=":", lw=1.2, label="2×基频位置")
        hr = sample["angles"][th]["fft"]["harmonic_ratio"]
        ax.set_title(f"{sample['label']} FFT  谐波比={hr:.2f}")
        ax.set_xlabel("等效厚度轴 (μm)")
        ax.set_ylabel("|FFT|")
        ax.grid(True, alpha=0.3)
        ax.legend(fontsize=8)
    fig.suptitle("SiC vs Si：振荡强度与谐波（多光束诊断）", fontsize=13)
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close()


def plot_si_result(si, path):
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.3), dpi=150)
    # spectrum + clean
    p = si["angles"]["10"]["_plot"]
    axes[0].plot(p["x"], p["yo"], color="#A0AEC0", lw=0.8, label="去趋势原振荡")
    axes[0].plot(p["xu"], p["y_rec"], color="#2F855A", lw=1.2, label="基频重建(抑谐波)")
    axes[0].set_xlabel(r"$\tilde{\nu}$")
    axes[0].set_ylabel("ΔR")
    axes[0].set_title("硅：抑制高次谐波后的条纹")
    axes[0].legend(fontsize=8)
    axes[0].grid(True, alpha=0.3)

    labels = ["FFT 10°", "FFT 15°", "抑谐波10°", "抑谐波15°", "推荐"]
    a10 = si["angles"]["10"]
    a15 = si["angles"]["15"]
    vals = [
        a10["fft"]["d_um"],
        a15["fft"]["d_um"],
        a10["d_um_harmonic_suppressed"],
        a15["d_um_harmonic_suppressed"],
        si["d_clean_mean"] if si["diagnosis"]["multibeam_likely"] else si["d_fft_mean"],
    ]
    colors = ["#2B6CB0", "#63B3ED", "#2F855A", "#68D391", "#E53E3E"]
    bars = axes[1].bar(labels, vals, color=colors)
    for b, v in zip(bars, vals):
        axes[1].text(b.get_x() + b.get_width() / 2, v + 0.03, f"{v:.3f}", ha="center", fontsize=9)
    axes[1].set_ylabel("d (μm)")
    axes[1].set_title("硅外延层厚度")
    axes[1].tick_params(axis="x", rotation=20)
    axes[1].grid(True, axis="y", alpha=0.3)
    fig.suptitle("问题3：硅晶圆厚度结果", fontsize=12)
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close()


def plot_sic_recalc(sic, path):
    fig, ax = plt.subplots(figsize=(8, 4.2), dpi=150)
    labels = ["Q2 FFT均\n(双光束)", "Q3 抑谐波后", "差异"]
    d0 = sic["d_fft_mean"]
    d1 = sic["d_clean_mean"]
    vals = [d0, d1, abs(d1 - d0)]
    colors = ["#2B6CB0", "#38A169", "#E53E3E"]
    bars = ax.bar(labels, vals, color=colors)
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.02, f"{v:.3f}", ha="center")
    ax.set_ylabel("μm")
    ax.set_title(
        f"SiC 多光束修正  谐波比={sic['diagnosis']['mean_harmonic_ratio']:.3f}  "
        f"→ {'需小修正' if abs(d1-d0)/d0>0.01 else '几乎不必修正'}"
    )
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close()


def main():
    plot_theory(OUT / "图_问题3_多光束理论.png")

    # SiC：分析窗与问题2一致；衬底重掺 n_sub 略低于外延
    sic = process_sample(
        "SiC",
        [("附件1.xlsx", 10), ("附件2.xlsx", 15)],
        n=N_SIC,
        lo=1500,
        hi=3000,
        n_sub_guess=2.35,
    )
    # Si：振荡在更宽的中红外都明显；取 600–2200 避开过高波数衰减过强区也可
    # 观察：低频振荡强。用 700–2000
    si = process_sample(
        "Si",
        [("附件3.xlsx", 10), ("附件4.xlsx", 15)],
        n=N_SI,
        lo=700,
        hi=2000,
        n_sub_guess=2.6,  # 重掺硅衬底红外 n 常明显低于本征 ~3.4
    )

    plot_sample_compare(sic, si, OUT / "图_问题3_SiC与Si诊断.png")
    plot_si_result(si, OUT / "图_问题3_硅厚度.png")
    plot_sic_recalc(sic, OUT / "图_问题3_SiC修正对比.png")

    # 推荐厚度
    si_rec = si["d_clean_mean"] if si["diagnosis"]["multibeam_likely"] else si["d_fft_mean"]
    sic_need = abs(sic["d_clean_mean"] - sic["d_fft_mean"]) / sic["d_fft_mean"] > 0.01
    sic_rec = sic["d_clean_mean"] if sic_need else sic["d_fft_mean"]

    # 清理 _plot 后写 json
    def strip(obj):
        if isinstance(obj, dict):
            return {k: strip(v) for k, v in obj.items() if not str(k).startswith("_")}
        if isinstance(obj, list):
            return [strip(v) for v in obj]
        if isinstance(obj, (np.floating, float)):
            return float(obj)
        if isinstance(obj, (np.integer, int)):
            return int(obj)
        if isinstance(obj, (np.bool_, bool)):
            return bool(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return obj

    summary = {
        "theory": {
            "amplitude_sum": "r=(r01+r12 e^{-iδ})/(1+r01 r12 e^{-iδ})",
            "necessary_condition": "F=|r01 r12|e^{-α} 不可忽略；且膜内相干、吸收不太强",
            "accuracy_impact": "条纹非余弦、极值位移、频谱出现高次谐波；用双光束极值公式会有系统偏差；基频仍对应同一光程，FFT基频+抑谐波可抑制偏差",
        },
        "SiC": strip(sic),
        "Si": strip(si),
        "recommended": {
            "Si_um": si_rec,
            "Si_method": "harmonic-suppressed FFT mean" if si["diagnosis"]["multibeam_likely"] else "FFT mean",
            "SiC_um": sic_rec,
            "SiC_multibeam_correction_applied": sic_need,
            "SiC_q2_fft_um": sic["d_fft_mean"],
        },
    }
    (OUT / "summary_q3.json").write_text(
        json.dumps(strip(summary), ensure_ascii=False, indent=2), encoding="utf-8"
    )

    md = f"""# 问题3：多光束干涉与硅/碳化硅厚度

## 1. 多光束模型

图2中光束 1,2,3,… 形成几何级数。空气侧反射振幅：

$$
r=\\frac{{r_{{01}}+r_{{12}}e^{{-i\\delta}}}}{{1+r_{{01}}r_{{12}}e^{{-i\\delta}}}},\\qquad
\\delta=4\\pi\\tilde\\nu d\\sqrt{{n_1^2-\\sin^2\\theta_0}}
$$

反射率 \(R=|r|^2\)（Airy 型）。双光束相当于分母 \(\\approx 1\) 的一阶截断。

## 2. 产生多光束的必要条件

1. **往返反射因子** \(F=|r_{{01}}r_{{12}}|e^{{-\\alpha}}\) **不可过小**（经验上 \(F\\gtrsim 0.05\) 开始可见，\(F\\gtrsim 0.15\) 明显）  
2. 外延层内吸收往返不太强（\(e^{{-\\alpha}}\) 不太小）  
3. 相干长度覆盖多次反射光程  

物理上：界面反射足够强（掺杂造成的 \(n_1\\neq n_2\) 大）时，2,3,4… 束不可忽略。

## 3. 对厚度精度的影响

- 条纹变成**非余弦**（峰更尖），极值位置相对双光束有**系统位移**  
- 频谱出现**高次谐波**；若误用局部峰间距，\(d\) 可能偏  
- **基频仍由同一光程 \(\\delta\\) 决定**，故 FFT 基频估 \(d\) 相对稳健  
- 消除影响：频域只保留基频再反演（抑谐波），或直接拟合 Airy 全谱

## 4. 硅晶圆（附件3、4）判定与结果

| 指标 | SiC | Si |
|------|-----|-----|
| 振荡 σ (%) | {sic['diagnosis']['mean_osc_std']:.3f} | {si['diagnosis']['mean_osc_std']:.3f} |
| 二次谐波比 | {sic['diagnosis']['mean_harmonic_ratio']:.3f} | {si['diagnosis']['mean_harmonic_ratio']:.3f} |
| 示意 F | {sic['diagnosis']['mean_F']:.3f} | {si['diagnosis']['mean_F']:.3f} |
| 多光束？ | {'否/很弱' if not sic['diagnosis']['multibeam_likely'] else '可能'} | {'是' if si['diagnosis']['multibeam_likely'] else '否'} |

硅：**判定为出现多光束**（振荡强、谐波比高）。  
采用多光束模型下的算法：去趋势 → FFT 基频 / **抑谐波后基频** → \(n_{{\\mathrm{{Si}}}}={N_SI}\)。

| 角度 | FFT d (μm) | 抑谐波 d (μm) |
|------|-----------:|-------------:|
| 10° | {si['angles']['10']['fft']['d_um']:.4f} | {si['angles']['10']['d_um_harmonic_suppressed']:.4f} |
| 15° | {si['angles']['15']['fft']['d_um']:.4f} | {si['angles']['15']['d_um_harmonic_suppressed']:.4f} |

**硅外延层推荐厚度：{si_rec:.4f} μm**

## 5. 碳化硅是否需修正

SiC 条纹弱、谐波比低，多光束影响很小。  
抑谐波后 d={sic['d_clean_mean']:.4f} μm，相对问题2 FFT 均 {sic['d_fft_mean']:.4f} μm，相对变化 {100*abs(sic['d_clean_mean']-sic['d_fft_mean'])/sic['d_fft_mean']:.2f}%。  

**{'已做小修正，推荐 '+f'{sic_rec:.4f} μm' if sic_need else '可不修正；维持问题2结果 '+f'{sic_rec:.4f} μm'}**

## 图件

- `图_问题3_多光束理论.png`
- `图_问题3_SiC与Si诊断.png`
- `图_问题3_硅厚度.png`
- `图_问题3_SiC修正对比.png`
"""
    (OUT / "方法论与结果_问题3.md").write_text(md, encoding="utf-8")

    print("Si diagnosis", si["diagnosis"])
    print("SiC diagnosis", sic["diagnosis"])
    print("Si rec", si_rec, "SiC rec", sic_rec)
    print("done")


if __name__ == "__main__":
    main()

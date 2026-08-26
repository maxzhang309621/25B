# -*- coding: utf-8 -*-
"""
折射率非常数建模：晶格色散 + 自由载流子(Drude)
并嵌入问题2厚度反演（双角度联合）。
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
from scipy.optimize import least_squares
from scipy.signal import find_peaks, savgol_filter

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent
ATTACH = ROOT.parent / "data"
OUT = ROOT

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

# ============================================================
# 1. 折射率模型 n = n(ν̃, N)
# ============================================================
# 4H-SiC 在 Reststrahlen(~800–1000 cm^-1) 高频侧：
#   ε(ν̃) ≈ ε_∞ + A_lat / (ν_TO^2 - ν̃^2)  -  ν_p(N)^2 / (ν̃^2 + γ^2)
# 分析窗 1500–3000 cm^-1 >> ν_TO，晶格项 ≈ ε_∞ - B/ν̃^2（弱色散）
# 载流子：ν_p^2 ∝ N/m* ，外延轻掺、衬底重掺 → n1 ≠ n2

EPS_INF = 6.553          # 高频介电常数，√ε_∞≈2.56
NU_TO = 797.0            # TO 声子波数 cm^-1（4H-SiC 量级）
EPS_S = 9.66             # 静态介电常数量级
# 晶格振子强度
A_LAT = (EPS_S - EPS_INF) * NU_TO**2

# Drude：ν_p^2 = K * N_cm3，K 取有效质量折合后的经验系数
# 对 SiC，N=1e18 cm^-3 时等离子体波数大约数百 cm^-1 量级
K_PLASMA = 1.5e-13       # ν_p^2 ≈ K*N  → N=1e18 → ν_p≈387 cm^-1
GAMMA = 50.0             # 散射阻尼 cm^-1


def epsilon_complex(nu_cm, N_cm3: float):
    """复介电函数 ε(ν̃; N)。nu_cm 可以是标量或数组。"""
    nu = np.asarray(nu_cm, dtype=float)
    # 晶格 Lorentz（避开精确极点）
    denom = NU_TO**2 - nu**2 - 1j * 20.0 * nu
    eps_lat = EPS_INF + A_LAT / denom
    # Drude
    nu_p2 = K_PLASMA * max(N_cm3, 0.0)
    eps_drude = -nu_p2 / (nu**2 + 1j * GAMMA * nu)
    return eps_lat + eps_drude


def n_from_eps(eps):
    """复折射率实部。"""
    return np.real(np.sqrt(eps))


def n_model(nu_cm, N_cm3: float):
    return n_from_eps(epsilon_complex(nu_cm, N_cm3))


def n_lattice_only(nu_cm):
    """仅晶格（N=0），用于对照。"""
    return n_model(nu_cm, 0.0)


# ============================================================
# 2. 数据与极值
# ============================================================
def load_spectrum(name):
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
    c = np.polyfit(x, y, deg)
    return y - np.polyval(c, x)


def extract_peaks(nu, R, lo=1500, hi=3000, prom=0.06):
    m = (nu >= lo) & (nu <= hi)
    x, y = nu[m], R[m]
    ys = savgol_filter(y, 31, 3)
    yd = detrend(ys)
    idx, _ = find_peaks(yd, prominence=prom, distance=25)
    if len(idx) < 5:
        idx, _ = find_peaks(yd, prominence=0.035, distance=18)
    return x[idx], x, yd


def beta(n, theta_deg):
    s2 = np.sin(np.deg2rad(theta_deg)) ** 2
    return 2.0 * np.sqrt(np.maximum(np.asarray(n) ** 2 - s2, 1e-12))


# ============================================================
# 3. 用 n(ν̃,N) 反演厚度
# ============================================================
def thickness_from_peaks(peaks_nu, theta_deg, N_epi):
    """级数回归：j = d * β(n(ν̃))*ν̃ - m0。"""
    if len(peaks_nu) < 3:
        return None
    j = np.arange(len(peaks_nu), dtype=float)
    n = n_model(peaks_nu, N_epi)
    z = beta(n, theta_deg) * peaks_nu  # 1/cm

    # 线性最小二乘 j = d_cm * z - m0
    A = np.column_stack([z, -np.ones_like(z)])
    coef, *_ = np.linalg.lstsq(A, j, rcond=None)
    d_cm, m0 = coef
    resid = j - (d_cm * z - m0)
    return {
        "d_um": float(d_cm * 1e4),
        "m0": float(m0),
        "rmse": float(np.sqrt(np.mean(resid**2))),
        "n_mean": float(np.mean(n)),
        "n_min": float(np.min(n)),
        "n_max": float(np.max(n)),
        "n_peaks": int(len(peaks_nu)),
    }


def fft_thickness(nu, R, theta_deg, N_epi, lo=1500, hi=3000):
    m = (nu >= lo) & (nu <= hi)
    x, y = nu[m], R[m]
    yd = detrend(y)
    dnu = float(np.median(np.diff(x)))
    xu = np.arange(x[0], x[-1], dnu)
    yu = np.interp(xu, x, yd)
    spec = np.abs(np.fft.rfft(yu * np.hanning(len(yu))))
    freq = np.fft.rfftfreq(len(yu), d=dnu)
    spec[0] = 0
    spec[freq < 0.0008] = 0
    f = float(freq[int(np.argmax(spec))])  # OPD cm
    # 用窗口内平均 n(ν̃,N)
    n_avg = float(np.mean(n_model(xu, N_epi)))
    d_cm = f / beta(n_avg, theta_deg)
    return {"d_um": d_cm * 1e4, "OPD_cm": f, "n_avg": n_avg}


def joint_fit_d_and_N(peaks10, peaks15, theta10=10.0, theta15=15.0):
    """
    联合拟合：同一 d、同一外延掺杂 N，使两角度级数残差最小。
    参数 x = [d_um, log10(N), m0_10, m0_15]
    """

    def pack_orders(peaks, theta, d_um, N, m0):
        n = n_model(peaks, N)
        pred = (d_um * 1e-4) * beta(n, theta) * peaks - m0
        j = np.arange(len(peaks), dtype=float)
        return pred - j

    def residual(x):
        d_um, logN, m0a, m0b = x
        N = 10**logN
        r1 = pack_orders(peaks10, theta10, d_um, N, m0a)
        r2 = pack_orders(peaks15, theta15, d_um, N, m0b)
        return np.concatenate([r1, r2])

    # 初值：N=1e15（轻掺），d≈7.8
    x0 = np.array([7.84, 15.0, 8.0, 8.0])
    bounds = ([5.0, 13.0, -20, -20], [12.0, 17.5, 40, 40])
    res = least_squares(residual, x0, bounds=bounds, max_nfev=5000)
    d_um, logN, m0a, m0b = res.x
    return {
        "d_um": float(d_um),
        "N_epi": float(10**logN),
        "log10_N": float(logN),
        "m0_10": float(m0a),
        "m0_15": float(m0b),
        "cost": float(res.cost),
        "success": bool(res.success),
    }


# ============================================================
# 4. 作图
# ============================================================
def plot_n_model(path):
    nu = np.linspace(1200, 3600, 500)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.3), dpi=150)

    for N, lab, c in [
        (0, "N=0（仅晶格）", "#2B6CB0"),
        (1e15, r"$N=10^{15}$（外延轻掺）", "#38A169"),
        (1e17, r"$N=10^{17}$", "#D69E2E"),
        (1e18, r"$N=10^{18}$（衬底量级）", "#E53E3E"),
        (5e18, r"$N=5\times10^{18}$", "#9B2C2C"),
    ]:
        axes[0].plot(nu, n_model(nu, N), lw=1.6, label=lab, color=c)
    axes[0].axhline(2.55, color="gray", ls="--", lw=1, label="常数 2.55")
    axes[0].set_xlabel(r"波数 $\tilde{\nu}$ (cm$^{-1}$)")
    axes[0].set_ylabel(r"折射率实部 $n$")
    axes[0].set_title(r"模型：$n=n(\tilde{\nu},N)$")
    axes[0].legend(fontsize=8)
    axes[0].grid(True, alpha=0.3)
    axes[0].set_xlim(1200, 3600)

    # 分解：晶格贡献 vs Drude 压低
    n0 = n_model(nu, 0)
    n_sub = n_model(nu, 1e18)
    axes[1].plot(nu, n0, color="#2B6CB0", lw=1.6, label="外延（近似 N=0）")
    axes[1].plot(nu, n_sub, color="#E53E3E", lw=1.6, label="衬底（N=1e18）")
    axes[1].fill_between(nu, n_sub, n0, color="#FED7D7", alpha=0.5, label="掺杂导致的 Δn")
    axes[1].set_xlabel(r"波数 $\tilde{\nu}$ (cm$^{-1}$)")
    axes[1].set_ylabel(r"$n$")
    axes[1].set_title("为何会有界面反射：外延 vs 衬底")
    axes[1].legend(fontsize=9)
    axes[1].grid(True, alpha=0.3)

    fig.suptitle("折射率非常数建模（晶格 Lorentz + 载流子 Drude）", fontsize=13)
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close()


def plot_n_in_window(path, N_epi, N_sub=1e18):
    nu = np.linspace(1500, 3000, 400)
    fig, ax = plt.subplots(figsize=(8.5, 4.2), dpi=150)
    ax.plot(nu, n_model(nu, N_epi), color="#2B6CB0", lw=2, label=fr"外延 $N={N_epi:.1e}$")
    ax.plot(nu, n_model(nu, N_sub), color="#E53E3E", lw=2, label=fr"衬底 $N={N_sub:.1e}$")
    ax.plot(nu, np.full_like(nu, 2.55), "k--", lw=1, label="常数 2.55")
    ax.set_xlabel(r"$\tilde{\nu}$ (cm$^{-1}$)")
    ax.set_ylabel(r"$n(\tilde{\nu})$")
    ax.set_title("分析窗内折射率随波数变化")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close()


def plot_compare_const_vs_disp(results, path):
    fig, ax = plt.subplots(figsize=(8.5, 4.3), dpi=150)
    labels = ["常数n=2.55\nFFT均", "弱色散N=0\nFFT均", "Drude联合拟合\n(推荐)"]
    vals = [
        results["fft_const_mean"],
        results["fft_N0_mean"],
        results["joint"]["d_um"],
    ]
    colors = ["#A0AEC0", "#63B3ED", "#38A169"]
    bars = ax.bar(labels, vals, color=colors)
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.03, f"{v:.3f}", ha="center", fontsize=11)
    ax.set_ylabel("d (μm)")
    ax.set_title("非常数 n 建模后的厚度对比")
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close()


# ============================================================
# 5. main
# ============================================================
def main():
    nu1, R1 = load_spectrum("附件1.xlsx")
    nu2, R2 = load_spectrum("附件2.xlsx")
    pk1, _, _ = extract_peaks(nu1, R1)
    pk2, _, _ = extract_peaks(nu2, R2)
    print("peaks10", len(pk1), pk1[:5], "...", "peaks15", len(pk2))

    # --- 常数 n ---
    def fft_const(nu, R, th, n0=2.55):
        m = (nu >= 1500) & (nu <= 3000)
        x, y = nu[m], R[m]
        yd = detrend(y)
        dnu = float(np.median(np.diff(x)))
        xu = np.arange(x[0], x[-1], dnu)
        yu = np.interp(xu, x, yd)
        spec = np.abs(np.fft.rfft(yu * np.hanning(len(yu))))
        freq = np.fft.rfftfreq(len(yu), d=dnu)
        spec[0] = 0
        spec[freq < 0.0008] = 0
        f = float(freq[int(np.argmax(spec))])
        return f / beta(n0, th) * 1e4

    d10_c = fft_const(nu1, R1, 10)
    d15_c = fft_const(nu2, R2, 15)

    # --- 仅晶格色散 N=0 ---
    f10_0 = fft_thickness(nu1, R1, 10, 0.0)
    f15_0 = fft_thickness(nu2, R2, 15, 0.0)
    p10_0 = thickness_from_peaks(pk1, 10, 0.0)
    p15_0 = thickness_from_peaks(pk2, 15, 0.0)

    # --- 联合拟合 d + N_epi ---
    joint = joint_fit_d_and_N(pk1, pk2)
    print("joint", joint)

    # 用联合 N 再算 FFT / 单角度极值
    N_hat = joint["N_epi"]
    f10_N = fft_thickness(nu1, R1, 10, N_hat)
    f15_N = fft_thickness(nu2, R2, 15, N_hat)
    p10_N = thickness_from_peaks(pk1, 10, N_hat)
    p15_N = thickness_from_peaks(pk2, 15, N_hat)

    # N 扫描：看厚度对掺杂敏感度
    N_grid = np.logspace(14, 17.5, 15)
    scan = []
    for N in N_grid:
        a = fft_thickness(nu1, R1, 10, N)["d_um"]
        b = fft_thickness(nu2, R2, 15, N)["d_um"]
        scan.append({"N": float(N), "d10": a, "d15": b, "mean": 0.5 * (a + b), "diff_pct": 100 * abs(a - b) / (0.5 * (a + b))})

    results = {
        "model": {
            "eps_inf": EPS_INF,
            "nu_TO": NU_TO,
            "eps_s": EPS_S,
            "K_plasma": K_PLASMA,
            "gamma": GAMMA,
            "formula": "eps = eps_inf + A_lat/(nu_TO^2 - nu^2 - i*..) - nu_p(N)^2/(nu^2 + i*gamma*nu); n=Re(sqrt(eps))",
        },
        "fft_const_10": d10_c,
        "fft_const_15": d15_c,
        "fft_const_mean": 0.5 * (d10_c + d15_c),
        "fft_N0_10": f10_0["d_um"],
        "fft_N0_15": f15_0["d_um"],
        "fft_N0_mean": 0.5 * (f10_0["d_um"] + f15_0["d_um"]),
        "peak_N0_10": p10_0,
        "peak_N0_15": p15_0,
        "joint": joint,
        "fft_jointN_10": f10_N,
        "fft_jointN_15": f15_N,
        "peak_jointN_10": p10_N,
        "peak_jointN_15": p15_N,
        "N_scan": scan,
        "recommended_um": joint["d_um"],
        "recommended_N_epi": N_hat,
    }

    plot_n_model(OUT / "图_折射率模型_n随波数掺杂.png")
    plot_n_in_window(OUT / "图_分析窗内n曲线.png", N_hat)
    plot_compare_const_vs_disp(results, OUT / "图_非常数n厚度对比.png")

    # N 扫描图
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2), dpi=150)
    Ns = [r["N"] for r in scan]
    axes[0].semilogx(Ns, [r["mean"] for r in scan], "o-", color="#2B6CB0")
    axes[0].axvline(N_hat, color="#E53E3E", ls="--", label=f"联合拟合 N={N_hat:.2e}")
    axes[0].axhline(joint["d_um"], color="#38A169", ls="--", label=f"联合 d={joint['d_um']:.3f}")
    axes[0].set_xlabel(r"外延掺杂 $N$ (cm$^{-3}$)")
    axes[0].set_ylabel("FFT 双角度平均 d (μm)")
    axes[0].set_title("厚度对外延掺杂的敏感性")
    axes[0].legend(fontsize=8)
    axes[0].grid(True, alpha=0.3)

    axes[1].semilogx(Ns, [r["diff_pct"] for r in scan], "o-", color="#C05621")
    axes[1].set_xlabel(r"$N$ (cm$^{-3}$)")
    axes[1].set_ylabel("10°/15° 相对差 (%)")
    axes[1].set_title("双角度一致性 vs N")
    axes[1].grid(True, alpha=0.3)
    fig.suptitle(r"把 $n=n(\tilde{\nu},N)$ 建进反演后的参数扫描", fontsize=12)
    fig.tight_layout()
    fig.savefig(OUT / "图_N扫描敏感性.png", bbox_inches="tight", facecolor="white")
    plt.close()

    def clean(o):
        if isinstance(o, dict):
            return {k: clean(v) for k, v in o.items()}
        if isinstance(o, (list, tuple)):
            return [clean(v) for v in o]
        if isinstance(o, (np.floating, float)):
            return float(o)
        if isinstance(o, (np.integer, int)):
            return int(o)
        if isinstance(o, (np.bool_, bool)):
            return bool(o)
        return o

    (OUT / "summary_n_model.json").write_text(
        json.dumps(clean(results), ensure_ascii=False, indent=2), encoding="utf-8"
    )

    md = f"""# 折射率非常数建模（嵌入问题2）

## 模型

复介电函数（波数 \(\\tilde\\nu\)，单位 cm⁻¹）：

$$
\\varepsilon(\\tilde\\nu,N)=\\varepsilon_\\infty+\\frac{{(\\varepsilon_s-\\varepsilon_\\infty)\\nu_{{\\mathrm{{TO}}}}^2}}{{\\nu_{{\\mathrm{{TO}}}}^2-\\tilde\\nu^2-i\\gamma_L\\tilde\\nu}}
-\\frac{{\\nu_p(N)^2}}{{\\tilde\\nu^2+i\\gamma\\tilde\\nu}}
$$

$$
n=\\mathrm{{Re}}\\sqrt{{\\varepsilon}},\\qquad \\nu_p^2 = K\\,N
$$

| 参数 | 取值 | 含义 |
|------|------|------|
| \(\\varepsilon_\\infty\) | {EPS_INF} | 高频介电常数 |
| \(\\nu_{{\\mathrm{{TO}}}}\) | {NU_TO} cm⁻¹ | 晶格振动 |
| \(\\varepsilon_s\) | {EPS_S} | 静态介电 |
| \(K\) | {K_PLASMA} | 等离子体强度系数 |
| \(\\gamma\) | {GAMMA} cm⁻¹ | 载流子阻尼 |

- **晶格项**：\(n\) 随波数缓变（分析窗内弱色散）
- **Drude 项**：掺杂越高，红外 \(n\) 越低 → 外延轻掺、衬底重掺，才有 \(n_1\\neq n_2\) 的界面反射

## 反演策略

1. 从光谱提取干涉峰
2. 相位条件用 **点态** \(n(\\tilde\\nu_k,N)\)，不再用单一常数
3. **联合拟合**同一物理厚度 \(d\) 与外延掺杂 \(N\)（两角度共享）

## 结果

| 方案 | d (μm) | 备注 |
|------|-------:|------|
| 常数 n=2.55 FFT | {0.5*(d10_c+d15_c):.4f} | 旧方案 |
| 仅晶格 N=0 FFT | {0.5*(f10_0['d_um']+f15_0['d_um']):.4f} | 弱色散 |
| **联合拟合 d+N** | **{joint['d_um']:.4f}** | N̂={N_hat:.3e} cm⁻³ |
| 联合 N 下 FFT 10°/15° | {f10_N['d_um']:.4f} / {f15_N['d_um']:.4f} | 相对差 {100*abs(f10_N['d_um']-f15_N['d_um'])/(0.5*(f10_N['d_um']+f15_N['d_um'])):.3f}% |

**推荐**：在色散+Drude 模型下，外延层厚度 **{joint['d_um']:.4f} μm**，外延掺杂约 **{N_hat:.2e} cm⁻³**（轻掺，与“外延层 n 接近本征晶格”一致）。

## 图

- `图_折射率模型_n随波数掺杂.png`
- `图_分析窗内n曲线.png`
- `图_非常数n厚度对比.png`
- `图_N扫描敏感性.png`
"""
    (OUT / "折射率非常数建模.md").write_text(md, encoding="utf-8")
    print(json.dumps(clean(results), ensure_ascii=False, indent=2)[:2000])
    print("recommended", joint["d_um"], "N", N_hat)


if __name__ == "__main__":
    main()

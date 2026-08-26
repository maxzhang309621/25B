# -*- coding: utf-8 -*-
"""波数 vs 反射率：相关、趋势、振荡关系诊断"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import openpyxl
from scipy.signal import savgol_filter
from scipy.stats import pearsonr, spearmanr

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
    nu, R = np.asarray(nu, float), np.asarray(R, float)
    if R[0] == 0:
        nu, R = nu[1:], R[1:]
    R = np.clip(R, 0, 100)
    return nu, R


def detrend(y, deg=2):
    x = np.linspace(-1, 1, len(y))
    coef = np.polyfit(x, y, deg)
    trend = np.polyval(coef, x)
    return y - trend, trend, coef


def analyze(nu, R, lo, hi):
    m = (nu >= lo) & (nu <= hi)
    x, y = nu[m], R[m]
    ys = savgol_filter(y, 31, 3)
    osc, trend, _ = detrend(ys, 2)
    # 相关：全谱/分析窗/去趋势后
    r_p, p_p = pearsonr(x, y)
    r_s, p_s = spearmanr(x, y)
    r_pt, p_pt = pearsonr(x, trend)
    r_po, p_po = pearsonr(x, osc)
    # 振荡强度
    return {
        "x": x,
        "y": y,
        "ys": ys,
        "trend": trend,
        "osc": osc,
        "pearson_raw": float(r_p),
        "pearson_raw_p": float(p_p),
        "spearman_raw": float(r_s),
        "pearson_trend": float(r_pt),
        "pearson_osc": float(r_po),
        "osc_std": float(np.std(osc)),
        "osc_ptp": float(np.ptp(osc)),
        "trend_range": float(trend.max() - trend.min()),
    }


def main():
    samples = [
        ("SiC 10°", "附件1.xlsx", 1500, 3000, "#2B6CB0"),
        ("SiC 15°", "附件2.xlsx", 1500, 3000, "#C05621"),
        ("Si 10°", "附件3.xlsx", 700, 2000, "#2F855A"),
        ("Si 15°", "附件4.xlsx", 700, 2000, "#6B46C1"),
    ]

    rows = []
    fig, axes = plt.subplots(2, 2, figsize=(11, 7.5), dpi=150)
    for ax, (lab, fname, lo, hi, c) in zip(axes.ravel(), samples):
        nu, R = load(fname)
        # 全谱散点密度太大，画线
        ax.plot(nu, R, color=c, lw=0.6, alpha=0.85)
        ax.axvspan(lo, hi, color="#C6F6D5", alpha=0.35, label="分析窗")
        a = analyze(nu, R, lo, hi)
        ax.plot(a["x"], a["trend"], "k--", lw=1.3, label="窗内慢变趋势")
        ax.set_title(
            f"{lab}\n窗内 Pearson(ν̃,R)={a['pearson_raw']:.3f}  "
            f"振荡σ={a['osc_std']:.2f}%"
        )
        ax.set_xlabel(r"波数 $\tilde{\nu}$ (cm$^{-1}$)")
        ax.set_ylabel("反射率 R (%)")
        ax.legend(fontsize=8, loc="upper right")
        ax.grid(True, alpha=0.3)
        rows.append({"label": lab, **{k: a[k] for k in a if k not in ("x", "y", "ys", "trend", "osc")}})
    fig.suptitle("波数–反射率关系总览（线=光谱，虚线=分析窗慢变趋势）", fontsize=13)
    fig.tight_layout()
    fig.savefig(OUT / "图_波数反射率_总览.png", bbox_inches="tight", facecolor="white")
    plt.close()

    # 分解：趋势 vs 振荡
    fig, axes = plt.subplots(2, 2, figsize=(11, 7.2), dpi=150)
    for ax, (lab, fname, lo, hi, c) in zip(axes.ravel(), samples):
        nu, R = load(fname)
        a = analyze(nu, R, lo, hi)
        ax.plot(a["x"], a["osc"], color=c, lw=0.9)
        ax.axhline(0, color="gray", lw=0.8)
        ax.set_title(
            f"{lab} 去趋势振荡\n"
            f"Pearson(ν̃, 振荡)={a['pearson_osc']:.3f}（应≈0）  "
            f"PTP={a['osc_ptp']:.2f}%"
        )
        ax.set_xlabel(r"$\tilde{\nu}$")
        ax.set_ylabel("ΔR (%)")
        ax.grid(True, alpha=0.3)
    fig.suptitle("关系的第二部分：干涉振荡（与波数近似周期相关，不是单调相关）", fontsize=12)
    fig.tight_layout()
    fig.savefig(OUT / "图_波数反射率_振荡.png", bbox_inches="tight", facecolor="white")
    plt.close()

    # 相关条形图
    fig, ax = plt.subplots(figsize=(9.5, 4.5), dpi=150)
    labels = [r["label"] for r in rows]
    x = np.arange(len(labels))
    w = 0.25
    b1 = ax.bar(x - w, [r["pearson_raw"] for r in rows], w, label="Pearson(ν̃, R) 原始", color="#2B6CB0")
    b2 = ax.bar(x, [r["pearson_trend"] for r in rows], w, label="Pearson(ν̃, 趋势)", color="#38A169")
    b3 = ax.bar(x + w, [r["pearson_osc"] for r in rows], w, label="Pearson(ν̃, 振荡)", color="#E53E3E")
    ax.axhline(0, color="k", lw=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylabel("相关系数")
    ax.set_title("波数与反射率：单调相关主要在“慢变趋势”，不在干涉振荡")
    ax.legend(fontsize=9)
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(OUT / "图_波数反射率_相关系数.png", bbox_inches="tight", facecolor="white")
    plt.close()

    # 文字结论
    lines = ["# 波数与反射率的关系\n"]
    lines.append("## 结论（先看这个）\n")
    lines.append(
        "有关系，但不是简单的“波数越大反射率越大/越小”这一种。\n\n"
        "反射率可以拆成两层：\n\n"
        "1. **慢变趋势**（材料色散、Reststrahlen、定标包络）→ 与波数有一定单调/缓变相关\n"
        "2. **快变振荡**（干涉条纹）→ 与波数是**周期关系** "
        r"（$\cos(2\pi\cdot OPD\cdot\tilde{\nu})$），"
        "Pearson 相关接近 0，但物理关系很强\n\n"
        "测厚度用的是第 2 层。\n"
    )
    lines.append("## 分析窗内数值\n\n")
    lines.append("| 样本 | Pearson(ν̃,R) | Spearman | Pearson(ν̃,趋势) | Pearson(ν̃,振荡) | 振荡σ(%) | 趋势峰峰值(%) |\n")
    lines.append("|------|-------------:|---------:|----------------:|----------------:|---------:|--------------:|\n")
    for r in rows:
        lines.append(
            f"| {r['label']} | {r['pearson_raw']:.3f} | {r['spearman_raw']:.3f} | "
            f"{r['pearson_trend']:.3f} | {r['pearson_osc']:.3f} | "
            f"{r['osc_std']:.3f} | {r['trend_range']:.3f} |\n"
        )
    lines.append("\n图：`图_波数反射率_总览.png` / `_振荡.png` / `_相关系数.png`\n")
    (OUT / "波数与反射率关系.md").write_text("".join(lines), encoding="utf-8")

    for r in rows:
        print(
            r["label"],
            "pearson",
            round(r["pearson_raw"], 3),
            "trend",
            round(r["pearson_trend"], 3),
            "osc",
            round(r["pearson_osc"], 3),
            "osc_std",
            round(r["osc_std"], 3),
        )


if __name__ == "__main__":
    main()

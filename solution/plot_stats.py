# -*- coding: utf-8 -*-
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import openpyxl
from pathlib import Path

out = Path(__file__).resolve().parent
DATA = out.parent / "data"
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


def load(name):
    wb = openpyxl.load_workbook((DATA / name) if (DATA / name).exists() else (out / name), data_only=True)
    ws = wb.active
    nu, R = [], []
    for row in ws.iter_rows(min_row=2, values_only=True):
        if row[0] is None:
            continue
        nu.append(float(row[0]))
        R.append(float(row[1]))
    nu, R = np.array(nu), np.array(R)
    if R[0] == 0:
        nu, R = nu[1:], R[1:]
    return nu, R


def detrend(y):
    x = np.linspace(-1, 1, len(y))
    coef = np.polyfit(x, y, 2)
    return y - np.polyval(coef, x)


datasets = {
    "SiC 10° (附件1)": load("附件1.xlsx"),
    "SiC 15° (附件2)": load("附件2.xlsx"),
    "Si 10° (附件3)": load("附件3.xlsx"),
    "Si 15° (附件4)": load("附件4.xlsx"),
}

# 图1: 四条光谱总览
fig, axes = plt.subplots(2, 2, figsize=(11, 7.5), dpi=150, sharex=True)
colors = ["#2B6CB0", "#C05621", "#2F855A", "#6B46C1"]
for ax, (label, (nu, R)), c in zip(axes.ravel(), datasets.items(), colors):
    ax.plot(nu, R, color=c, lw=0.7, alpha=0.9)
    ax.set_title(label, fontsize=12)
    ax.set_ylabel("反射率 R (%)")
    ax.grid(True, alpha=0.3)
    ax.axvspan(800, 1100, color="#FED7D7", alpha=0.45, label="Reststrahlen附近")
    ax.axvspan(1400, 3200, color="#C6F6D5", alpha=0.35, label="干涉分析窗(示意)")
    stats = f"N={len(R)}  mean={R.mean():.1f}%  max={R.max():.1f}%"
    ax.text(
        0.02,
        0.95,
        stats,
        transform=ax.transAxes,
        va="top",
        fontsize=9,
        bbox=dict(boxstyle="round", facecolor="white", alpha=0.85, edgecolor="#CBD5E0"),
    )
axes[0, 0].legend(loc="upper right", fontsize=8, framealpha=0.9)
axes[1, 0].set_xlabel(r"波数 $\tilde{\nu}$ (cm$^{-1}$)")
axes[1, 1].set_xlabel(r"波数 $\tilde{\nu}$ (cm$^{-1}$)")
fig.suptitle("图1  四组实测反射光谱总览", fontsize=14, y=0.995)
fig.tight_layout()
fig.savefig(out / "统计_光谱总览.png", bbox_inches="tight", facecolor="white")
plt.close()
print("fig1 ok")

# 图2: SiC 两角度
fig, axes = plt.subplots(1, 2, figsize=(11, 4.6), dpi=150)
nu1, R1 = datasets["SiC 10° (附件1)"]
nu2, R2 = datasets["SiC 15° (附件2)"]
axes[0].plot(nu1, R1, color="#2B6CB0", lw=0.8, label="10°", alpha=0.85)
axes[0].plot(nu2, R2, color="#C05621", lw=0.8, label="15°", alpha=0.75)
axes[0].set_xlabel(r"波数 $\tilde{\nu}$ (cm$^{-1}$)")
axes[0].set_ylabel("反射率 R (%)")
axes[0].set_title("SiC 全谱：10° vs 15°")
axes[0].legend()
axes[0].grid(True, alpha=0.3)

m1 = (nu1 > 1600) & (nu1 < 2400)
m2 = (nu2 > 1600) & (nu2 < 2400)
axes[1].plot(nu1[m1], detrend(R1[m1]), color="#2B6CB0", lw=1.0, label="10° (去趋势)")
axes[1].plot(nu2[m2], detrend(R2[m2]), color="#C05621", lw=1.0, label="15° (去趋势)", alpha=0.85)
axes[1].set_xlabel(r"波数 $\tilde{\nu}$ (cm$^{-1}$)")
axes[1].set_ylabel("去趋势后 ΔR (%)")
axes[1].set_title("SiC 干涉区放大 (1600–2400)")
axes[1].legend()
axes[1].grid(True, alpha=0.3)
fig.suptitle("图2  同一片 SiC：两入射角光谱对照", fontsize=13)
fig.tight_layout()
fig.savefig(out / "统计_SiC两角度对照.png", bbox_inches="tight", facecolor="white")
plt.close()
print("fig2 ok")

# 图3: 分波段箱线
bands = [
    (400, 800, "400-800"),
    (800, 1200, "800-1200"),
    (1200, 1600, "1200-1600"),
    (1600, 2400, "1600-2400"),
    (2400, 3200, "2400-3200"),
    (3200, 4000, "3200-4000"),
]
fig, axes = plt.subplots(1, 2, figsize=(11, 4.8), dpi=150)
for ax, key, c in zip(axes, ["SiC 10° (附件1)", "Si 10° (附件3)"], ["#2B6CB0", "#2F855A"]):
    nu, R = datasets[key]
    data, labels = [], []
    for a, b, lab in bands:
        m = (nu >= a) & (nu < b)
        data.append(R[m])
        labels.append(lab)
    bp = ax.boxplot(data, labels=labels, patch_artist=True, showfliers=False)
    for patch in bp["boxes"]:
        patch.set_facecolor(c)
        patch.set_alpha(0.45)
    ax.set_title(key)
    ax.set_ylabel("反射率 R (%)")
    ax.set_xlabel("波数区间 (cm$^{-1}$)")
    ax.tick_params(axis="x", rotation=25)
    ax.grid(True, axis="y", alpha=0.3)
fig.suptitle("图3  分波段反射率分布（箱线图）", fontsize=13)
fig.tight_layout()
fig.savefig(out / "统计_分波段箱线.png", bbox_inches="tight", facecolor="white")
plt.close()
print("fig3 ok")

# 描述统计
rows = []
for label, (nu, R) in datasets.items():
    m = (nu > 1400) & (nu < 3200)
    Rm = R[m]
    osc = detrend(Rm).std() if len(Rm) > 10 else Rm.std()
    rows.append(
        {
            "label": label,
            "N": len(R),
            "R_mean": R.mean(),
            "R_max": R.max(),
            "win_mean": Rm.mean(),
            "win_std": Rm.std(),
            "osc": osc,
            "gt100": int((R > 100).sum()),
        }
    )

fig, ax = plt.subplots(figsize=(11, 4.2), dpi=150)
ax.axis("off")
cols = [
    "样本",
    "点数",
    "全谱均值%",
    "全谱最大%",
    "干涉窗均值%\n(1400-3200)",
    "干涉窗标准差%",
    "去趋势振荡σ%",
    ">100%点数",
]
cell = []
for r in rows:
    cell.append(
        [
            r["label"],
            f"{r['N']}",
            f"{r['R_mean']:.2f}",
            f"{r['R_max']:.2f}",
            f"{r['win_mean']:.2f}",
            f"{r['win_std']:.3f}",
            f"{r['osc']:.3f}",
            str(r["gt100"]),
        ]
    )
table = ax.table(cellText=cell, colLabels=cols, loc="center", cellLoc="center")
table.auto_set_font_size(False)
table.set_fontsize(9)
table.scale(1.05, 1.75)
for (i, j), cell_obj in table.get_celld().items():
    if i == 0:
        cell_obj.set_facecolor("#2B6CB0")
        cell_obj.set_text_props(color="white", weight="bold")
    elif i % 2 == 0:
        cell_obj.set_facecolor("#EDF2F7")
ax.set_title("图4  四组光谱描述统计", fontsize=13, pad=12)
fig.tight_layout()
fig.savefig(out / "统计_描述统计表.png", bbox_inches="tight", facecolor="white")
plt.close()
print("fig4 ok")

# 图5: 振荡强度
fig, ax = plt.subplots(figsize=(8.5, 4.5), dpi=150)
labels_short = [r["label"].split(" (")[0] for r in rows]
osc_vals = [r["osc"] for r in rows]
bars = ax.bar(
    labels_short,
    osc_vals,
    color=["#2B6CB0", "#63B3ED", "#2F855A", "#68D391"],
    edgecolor="white",
)
for b, v in zip(bars, osc_vals):
    ax.text(b.get_x() + b.get_width() / 2, v + 0.01, f"{v:.3f}", ha="center", va="bottom", fontsize=10)
ax.set_ylabel("干涉窗去趋势后标准差 σ (%)")
ax.set_title("图5  条纹振荡强度对比（越大条纹越明显）")
ax.grid(True, axis="y", alpha=0.3)
ax.text(
    0.02,
    0.95,
    "SiC 条纹弱；Si 振荡强得多 → 第三问多光束嫌疑更大",
    transform=ax.transAxes,
    va="top",
    fontsize=10,
    bbox=dict(boxstyle="round", facecolor="#FFFBEB", edgecolor="#D69E2E"),
)
fig.tight_layout()
fig.savefig(out / "统计_振荡强度对比.png", bbox_inches="tight", facecolor="white")
plt.close()
print("fig5 ok")

for p in sorted(out.glob("统计_*.png")):
    print(p.name, p.stat().st_size)

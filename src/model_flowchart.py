"""生成当前数学模型的论文级流程图 PNG。"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Polygon


COLORS = {
    "input": "#D9EAF7",
    "process": "#E8F3EC",
    "physics": "#FFF0D5",
    "decision": "#F7E2E2",
    "output": "#E9E2F3",
    "edge": "#4D4D4D",
}


def _box(ax, center, width, height, text, color, fontsize=9):
    x, y = center
    patch = FancyBboxPatch(
        (x - width / 2, y - height / 2),
        width,
        height,
        boxstyle="round,pad=0.012,rounding_size=0.012",
        facecolor=color,
        edgecolor=COLORS["edge"],
        linewidth=1.2,
        zorder=3,
    )
    ax.add_patch(patch)
    ax.text(x, y, text, ha="center", va="center", fontsize=fontsize, zorder=4)


def _diamond(ax, center, width, height, text):
    x, y = center
    vertices = [
        (x, y + height / 2),
        (x + width / 2, y),
        (x, y - height / 2),
        (x - width / 2, y),
    ]
    patch = Polygon(
        vertices,
        closed=True,
        facecolor=COLORS["decision"],
        edgecolor=COLORS["edge"],
        linewidth=1.2,
        zorder=3,
    )
    ax.add_patch(patch)
    ax.text(x, y, text, ha="center", va="center", fontsize=8.5, zorder=4)


def _arrow(ax, start, end, label=None, connectionstyle="arc3"):
    patch = FancyArrowPatch(
        start,
        end,
        arrowstyle="-|>",
        mutation_scale=12,
        linewidth=1.15,
        color=COLORS["edge"],
        connectionstyle=connectionstyle,
        zorder=2,
    )
    ax.add_patch(patch)
    if label:
        x = (start[0] + end[0]) / 2
        y = (start[1] + end[1]) / 2
        ax.text(
            x,
            y,
            label,
            ha="center",
            va="center",
            fontsize=7.5,
            bbox={"boxstyle": "round,pad=0.15", "fc": "white", "ec": "none"},
            zorder=5,
        )


def plot_model_flowchart(path: Path) -> None:
    """输出输入、物理核、联合反演、门控与回退的完整流程图。"""
    plt.rcParams.update(
        {
            "font.sans-serif": ["Microsoft YaHei", "SimHei", "DejaVu Sans"],
            "axes.unicode_minus": False,
        }
    )
    fig, ax = plt.subplots(figsize=(17, 12), layout="constrained")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    _box(
        ax,
        (0.50, 0.94),
        0.34,
        0.065,
        "附件 1–4：波数 $\\tilde\\nu$、反射率 $R$、入射角 10°/15°",
        COLORS["input"],
        10,
    )
    _box(
        ax,
        (0.50, 0.84),
        0.36,
        0.07,
        "数据资格审查与双通道预处理\n绝对/相对谱模式 → 厚度波段 + 浓度敏感波段",
        COLORS["process"],
    )

    _box(
        ax,
        (0.22, 0.71),
        0.31,
        0.09,
        "常折射率稳健基线\nFFT 粗估 + 峰谷 Theil–Sen\n得到厚度级次 $d_0$",
        COLORS["process"],
    )
    _box(
        ax,
        (0.68, 0.73),
        0.37,
        0.12,
        "波长—载流子复介电函数\n"
        "$\\varepsilon=\\varepsilon_{\\rm intrinsic}(\\tilde\\nu)"
        "+\\varepsilon_{\\rm carrier}(\\tilde\\nu,N)$\n"
        "$\\tilde n_{epi}=\\sqrt{\\varepsilon(N_{epi})}$，"
        "$\\tilde n_{sub}=\\sqrt{\\varepsilon(N_{sub})}$",
        COLORS["physics"],
        8.5,
    )
    _box(
        ax,
        (0.68, 0.57),
        0.38,
        0.095,
        "外延层—衬底 Fresnel–Airy + 受约束仪器响应\n"
        "$\\beta=2\\pi d\\tilde\\nu q_{epi}$；分别计算 s/p 偏振\n"
        "$R=(|r_s|^2+|r_p|^2)/2$；共享漂移 + 有界增益/偏置",
        COLORS["physics"],
        8.5,
    )
    _box(
        ax,
        (0.47, 0.43),
        0.40,
        0.09,
        "双角度分阶段浓度反演\n厚度锚定 → 单浓度条件拟合 → 双浓度联合\n"
        "共享 $(d,\\log N_{epi},\\log N_{sub})$",
        COLORS["process"],
        8.7,
    )
    _diamond(
        ax,
        (0.47, 0.29),
        0.34,
        0.12,
        "轮廓区间与模型门控\n区间不触边、浓度相关性 < 0.85？\n"
        "相对固定情景改善 ≥ 10%？",
    )

    _box(
        ax,
        (0.16, 0.14),
        0.25,
        0.075,
        "自由浓度联合结果\n浓度与厚度可辨识",
        COLORS["output"],
        8.5,
    )
    _box(
        ax,
        (0.47, 0.14),
        0.25,
        0.075,
        "固定低/中/高掺杂情景\n浓度不可唯一辨识",
        COLORS["output"],
        8.5,
    )
    _box(
        ax,
        (0.78, 0.14),
        0.25,
        0.075,
        "回退常折射率稳健基线\n色散留段不稳定",
        COLORS["output"],
        8.5,
    )
    _box(
        ax,
        (0.47, 0.035),
        0.58,
        0.055,
        "最终输出：厚度 + 浓度条件区间/单侧界限 + 仪器模式 + $n,k$ 曲线 + 回退证据",
        COLORS["input"],
        9.2,
    )

    _arrow(ax, (0.50, 0.905), (0.50, 0.875))
    _arrow(ax, (0.42, 0.81), (0.28, 0.765))
    _arrow(ax, (0.58, 0.81), (0.65, 0.79))
    _arrow(ax, (0.68, 0.67), (0.68, 0.62))
    _arrow(ax, (0.29, 0.665), (0.39, 0.475), label="厚度初值/级次")
    _arrow(ax, (0.63, 0.522), (0.53, 0.475), label="物理反射率")
    _arrow(ax, (0.47, 0.385), (0.47, 0.35))
    _arrow(
        ax,
        (0.37, 0.245),
        (0.19, 0.18),
        label="全部通过",
        connectionstyle="arc3,rad=0.08",
    )
    _arrow(ax, (0.47, 0.23), (0.47, 0.18), label="浓度失败但留段稳定")
    _arrow(
        ax,
        (0.57, 0.245),
        (0.75, 0.18),
        label="留段不稳定",
        connectionstyle="arc3,rad=-0.08",
    )
    _arrow(ax, (0.16, 0.102), (0.35, 0.063))
    _arrow(ax, (0.47, 0.102), (0.47, 0.063))
    _arrow(ax, (0.78, 0.102), (0.59, 0.063))

    ax.text(
        0.02,
        0.98,
        "2025 B 题：波长—载流子浓度耦合的外延层厚度数学模型",
        ha="left",
        va="top",
        fontsize=16,
        fontweight="bold",
    )
    ax.text(
        0.98,
        0.98,
        "当前门控：SiC → relative_shape / conditional_dual（不报告绝对浓度点）",
        ha="right",
        va="top",
        fontsize=9,
        color=COLORS["edge"],
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=220, bbox_inches="tight")
    plt.close(fig)

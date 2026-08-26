# 透明波段候选窗（Candidate Window）

本目录负责 **Q2 可靠性** 中的「主分析波段选取」：在多个候选波数窗上重复双光束估计，自动选出条纹最可靠的一段，并给出 sensitivity 对照。

与 **Q3 多光束** 的关系：Q3 在同一选中窗上判断 Airy 是否必要；本模块不替代 Q3，只解决「在哪段波数上读条纹」。

---

## 目录结构

```text
Candidate window/
├── README.md                 # 本说明（原理 + 用法 + 结果解读）
├── band_select.py            # 候选窗评分与自动选取
├── band_analysis.py          # SiC 全谱分段统计（Reststrahlen / 过渡区证据）
├── __init__.py
└── output/                   # 全部数值与图（由脚本生成）
    ├── band_sensitivity.csv           # 各候选窗 FFT/极值/MAD（main.py）
    ├── thickness_summary.csv          # 最终厚度（main.py）
    ├── consistency.json
    ├── sic_reflectance_by_region.csv  # 分段反射率（band_analysis.py）
    ├── sic_fringe_metrics_by_region.csv
    ├── sic_*_spectrum_regions.png     # 全谱分段着色图
    └── segment_analysis_summary.md
```

---

## 为什么不使用全谱（400–4000 cm⁻¹）？

厚度公式 \(\delta = 4\pi\tilde\nu\, n\cos\theta_1\) 在 **弱吸收、\(n\) 近似常数** 的透明区成立。全谱中有多段不满足：

| 波数段 | 物理现象 | 对测厚的影响 |
|--------|----------|--------------|
| **797–1000** | SiC Reststrahlen / TO 声子，\(n,k\) 剧变 | 非干涉条纹；单独 FFT 给出非物理厚度（~19 μm） |
| **1000–1100** | 吸收谷底，\(R\approx 5\%\) | 对比度极低，无法稳定数条纹 |
| **1100–1200** | 吸收尾巴，干涉刚恢复 | 条纹弱；纳入后 FFT 与极值分歧变大 |
| **1200–4000** | 相对透明 | **主估计区**，FFT ~7.7–7.9 μm |

「797–1000」主要依据 **文献 + 附件光谱形态**；「1100–1200 过渡区」依据 **分段实验 + 含/不含该段时 FFT–极值对照**（见 `output/sic_fringe_metrics_by_region.csv`）。

---

## 候选窗与评分规则（`band_select.py`）

### SiC 候选窗

| 窗口 (cm⁻¹) | 说明 |
|-------------|------|
| 1500–3000 | 集训 canonical 窄窗 |
| 1100–3500 | 中间方案 |
| **1200–4000** | **当前自动选中** |
| 1100–4000 | 原 dev 默认窗（对照） |

Si 候选窗：`1500–3000`, `1000–3500`, `1200–4000`, `1000–4000`。

### 每个候选窗计算

1. 截窗 → SG 双尺度预处理 → `estimate_two_beam`（与主 pipeline 相同）
2. 指标：
   - **极值数** = 峰数 + 谷数
   - **FFT–极值相对差** = \(|d_\mathrm{FFT}-d_\mathrm{extrema}|/\bar d\)
   - **间距 MAD** = 相邻峰/谷 \(\Delta\tilde\nu\) 相对中位数的绝对偏差中位数

### 选取规则

1. **硬门槛**：极值数 ≥ 15，且 FFT–极值相对差 < 2%
2. 通过者在其中取 **MAD 最小**
3. 若无窗通过：降级为极值≥15 中 MAD 最小；再不行则比 (MAD, 相对差)

---

## 如何运行

在 `25B/src` 下（需 `25B/data/附件*.xlsx`）：

```bash
# 完整 pipeline（选窗 + Q2/Q3 + 输出到本目录 output/）
python main.py --bootstrap 100

# 仅生成分段光谱分析表与示意图
python "Candidate window/band_analysis.py"
```

Windows 示例：

```powershell
cd 25B\src
D:\perfect\python.exe main.py --bootstrap 100
D:\perfect\python.exe "Candidate window\band_analysis.py"
```

---

## 当前结果摘要（完整版，2025-08）

### 自动选窗

四份附件均选中 **1200–4000 cm⁻¹**。

### SiC 候选窗 sensitivity（附件 1，10°）

| 窗 | 极值数 | FFT (μm) | 极值 (μm) | FFT–极值差 | 选中 |
|----|--------|----------|-----------|------------|------|
| 1500–3000 | 11 | 7.864 | 7.979 | 1.45% | |
| 1100–4000 | 23 | 8.135 | 7.905 | **2.86%** | |
| **1200–4000** | 22 | 7.724 | 7.883 | 2.03% | **✓** |

1500–3000 虽接近 canonical FFT，但极值不足 15；1100–4000 极值多但 FFT 偏高（含 1100–1200 过渡段）。

### 厚度（选窗后）

| 材料 | 联合厚度 | 模型 | 相对改前 dev (1100–4000) |
|------|----------|------|--------------------------|
| SiC | **7.851 μm** | two-beam | −0.026 μm（7.877→7.851） |
| Si | **3.593 μm** | multi-beam | +0.024 μm |

SiC Q3 结论不变：**不作多光束修正**。

---

## 与原 dev 的差异

| 项目 | 原 dev | 本模块 |
|------|--------|--------|
| 分析窗 | `config.py` 固定 1100–4000 | 多候选打分，主结果 1200–4000 |
| Reststrahlen | `model.md` 文字排除 797–1000 | + 附件分段 CSV、示意图 |
| 1100–1200 | 未讨论 | 分窗对照 + README 说明 |
| sensitivity 表 | 无（仅在 algorithm-plan 规划） | `band_sensitivity.csv` |

若需复现原 dev 数值（SiC **7.877 μm**），在 `main.py` 中跳过 `select_band`，固定 `fit_band_cm1=(1100, 4000)` 即可。

---

## 论文可引用表述

> 主厚度在弱吸收透明波段估计。SiC 在 797–1000 cm⁻¹ 存在 Reststrahlen 吸收，不纳入主估计；对多个候选窗（含原 1100–4000 cm⁻¹ 与集训 1500–3000 cm⁻¹）重复双光束反演，以有效极值数、FFT–极值一致性及峰谷间距 MAD 选取 1200–4000 cm⁻¹ 为主窗。sensitivity 表明联合厚度相对 1100–4000 窗变化约 0.3%，主结论稳定。

---

## 参考文献与数据来源

- SiC 声子带：Ioffe NSM / `model.md` 假设 3
- 实测附件：`25B/data/附件1.xlsx`、`附件2.xlsx`
- 集训 canonical：1500–3000 窗 FFT 融合 **7.875 μm**（极值数较少，作对照）

---

## 依赖

与主项目相同：`numpy`, `pandas`, `scipy`, `openpyxl`, `matplotlib`（见 `25B/requirements.txt`）。

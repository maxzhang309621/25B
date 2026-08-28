# 2025 高教社杯数学建模竞赛 B 题

## 项目简介

本项目针对“碳化硅外延层厚度的确定”建立红外干涉测厚模型，并使用题目提供的四组实测光谱完成：

1. 双光束干涉厚度模型推导；
2. 碳化硅晶圆外延层厚度计算及可靠性分析；
3. 多光束干涉必要条件与可观测性判断；
4. 硅晶圆 Airy 多光束模型拟合；
5. 双入射角一致性、不确定度及可视化分析。

完整数学推导见 [`model.md`](model.md)。

## 主要结论

| 材料 | 最终模型 | 10° 厚度 | 15° 厚度 | 联合厚度 | 双角度相对差 |
|---|---|---:|---:|---:|---:|
| 碳化硅 | v8 色散坐标多峰谷模型 | 7.5000 µm | 7.4124 µm | **7.45 µm** | 1.175% |
| 硅 | Airy 多光束模型 | 3.5979 µm | 3.5843 µm | **3.59 µm** | 0.379% |

多光束判定同时检查：

- 二次谐波与基频幅值比；
- 有效反射率；
- Airy 模型相对双光束模型的 RMSE 改善；
- AICc 改善。

当前结果支持附件 3、4 的硅片存在可观测多光束干涉；附件 1、2 的碳化硅数据缺乏足够的高次谐波证据，因此仍采用双光束机理，但厚度由 v8 色散坐标多峰谷模型确定。

## v8 色散坐标多峰谷升级

v8 在透明波段内把峰、谷波数映射到
\(g=\tilde\nu\sqrt{n^2(\tilde\nu)-\sin^2\theta}\)，对10°/15°峰谷四条序列采用共享厚度、独立截距的稳健回归。

- SiC：名义厚度 **7.4516 µm**，条件统计95%区间 **7.4306–7.4827 µm**；峰谷差0.399%、双角度差1.175%、留段CV 0.738%，通过门控。固定色散情景与常折射率基线形成 **7.3679–7.8323 µm** 的模型系统范围。
- Si：v8候选约3.3995 µm，但峰谷差4.771%、留段CV 3.168%，且与Airy厚度相差5.419%，未通过门控，继续采用多光束结果 **3.5943 µm**。

完整结果见 `output/dispersion_extrema_comparison.json`。

## v9 分析型证据图

`output/analysis_evidence/` 在纯原始数据图之外提供13张带分析标识的论文证据图：

- `*_band_eligibility_analysis.png`：透明区、排除区、合格/不合格极值；
- `*_order_fit_analysis.png`：色散坐标级次回归、厚度、统计区间与采用状态；
- `*_order_residual_analysis.png`：稳健残差带、最大残差和剔除比例；
- `*_stability_gates_analysis.png`：峰谷、角度、留段、偏移、Airy一致性门控；
- `*_scenario_thickness_analysis.png`：固定折射率情景、误差棒与系统范围；
- `*_carrier_audit_analysis.png`：载流子不可辨识的数值证据；
- `final_model_decision_analysis.png`：SiC采用v8、Si回退Airy的最终决策链。

分析标识均直接读取模型输出及统一阈值，不在绘图阶段重新计算或改变结论。

## v7 折射率三轨架构

- **主结论轨**：常折射率双/多光束模型，继续给出上述最终厚度；
- **方案 B 系统误差轨**：本征色散与固定低/中/高掺杂情景，浓度不参与优化，只输出厚度系统范围；
- **自由浓度审计轨**：保留既有载流子复介电联合反演，并输出触边、相关性、连续留段与轮廓证据，不可辨识候选不进入主结论。

方案 B 得到的条件系统范围为：SiC 约 **7.334–7.832 µm**，Si 约 **3.584–3.605 µm**。详细采纳规则见 `output/refractive_index_comparison.json`。

## 项目结构

```text
25B/
├── data/                       # 题目附件 1–4
├── doc/B题.pdf                 # 赛题原文
├── docs/pipeline/              # 开发流水线方案、实现与测试记录
├── output/                     # 数值结果、审计文件和诊断图
├── src/
│   ├── config.py               # 数据集与参数配置
│   ├── data_io.py              # Excel 读取和数据审计
│   ├── preprocess.py           # 平滑与基线分离
│   ├── optics.py               # 折射、相位、Fresnel 和 Airy 公式
│   ├── two_beam.py             # 双光束厚度估计
│   ├── multi_beam.py           # 多光束模型拟合
│   ├── diagnostics.py          # 谐波和模型比较诊断
│   ├── uncertainty.py          # 重采样与双角度一致性
│   ├── plotting.py             # 单附件证据图和汇总图
│   ├── main.py                 # 命令行入口
│   └── test_model.py           # 单元与输出测试
├── model.md                    # 建模过程、公式和结果说明
├── requirements.txt
├── README.md
└── LICENSE
```

## 环境要求

- Python 3.10+
- NumPy
- SciPy
- Pandas
- OpenPyXL
- Matplotlib

安装依赖：

```bash
python -m pip install -r requirements.txt
```

## 运行方法

进入源码目录：

```bash
cd src
```

运行测试：

```bash
python test_model.py
```

执行完整求解：

```bash
python main.py --bootstrap 100
```

快速冒烟运行：

```bash
python main.py --fast --bootstrap 10
```

`--fast` 会跳过多光束差分进化全局搜索，仅建议用于检查程序能否运行，不应用于生成最终竞赛结果。

## 输出文件

主要数值文件：

- `output/thickness_summary.csv`：四组数据的厚度、误差及模型判定；
- `output/consistency.json`：双角度一致性和加权联合厚度；
- `output/data_audit.json`：输入数据质量审计；
- `output/fit_details.json`：拟合与诊断详细参数；
- `output/dispersion_fit.json`：波长—载流子浓度联合校准、可辨识性和掺杂情景；
- `output/refractive_index_curves.csv`：外延层与衬底的复折射率曲线；
- `output/carrier_inference.json`：SiC 增强反射率反演、仪器模式和条件浓度区间；
- `output/carrier_profile.csv`：外延层/衬底浓度轮廓目标函数。

主要图片：

- `output/*_fit.png`：四组光谱的六区域完整证据图；
- `output/thickness_comparison.png`：厚度、模型差异和置信区间；
- `output/angle_consistency.png`：双入射角一致性；
- `output/multibeam_evidence.png`：多光束四项判据矩阵；
- `output/model_quality.png`：双光束与 Airy 模型质量比较；
- `output/dispersion_curves.png`：SiC/Si 外延层与衬底的 \(n,k\) 曲线；
- `output/carrier_scenarios.png`：低、中、高掺杂情景的厚度及 RMSE；
- `output/identifiability_diagnostics.png`：连续波段稳定性与参数门控；
- `output/carrier_profile.png`：SiC 两层载流子浓度的条件轮廓区间；
- `output/model_flowchart.png`：当前完整数学模型流程图；
- `docs/model-flowchart.md`：可编辑 Mermaid 流程图及核心公式。

论文原始数据图（仅保留标题、坐标、单位和必要图例）：

- `output/raw_evidence/multibeam/`：多光束四项指标的独立图，以及四个附件各自的频率—幅值图，共 8 张；
- `output/raw_evidence/dispersion/`：SiC/Si 的 \(n,k\)、情景厚度、情景 RMSE、连续留段厚度和双层浓度轮廓，共 9 张。

## 使用的主要方法

- Savitzky–Golay 双尺度滤波；
- 波数域快速傅里叶变换；
- 峰谷显著性检测；
- Theil–Sen 稳健回归；
- 双光束干涉相位模型；
- Fresnel/Airy 多光束模型；
- Si/4H-SiC 本征色散与自由载流子复介电模型；
- 外延层—衬底物理界面反射及双角度共享厚度联合校准；
- 差分进化与有界局部优化；
- AICc、RMSE 和高次谐波联合诊断；
- 峰谷间距 Bootstrap 重采样。

## 注意事项

1. 色散模型采用论文物性与工程先验；题目未给出晶型、晶向、掺杂类型、浓度和温度，程序会另外报告掺杂情景系统区间。
2. 只有通过可辨识性门控时，拟合浓度才可解释为附件支持的估计；触边或强相关时只报告情景，不报告唯一浓度。
3. 统计置信区间与折射率/掺杂系统区间含义不同，不应直接混为同一个精确度数字。
4. 原有效 Airy 反射率仍只用于多光束证据；v3 物理模型则分别计算外延层和衬底介电函数。
5. 本项目用于数学建模研究与竞赛复现，不构成工业测量标准或产品质量认证。

## 许可证

本项目采用 [MIT License](LICENSE)。

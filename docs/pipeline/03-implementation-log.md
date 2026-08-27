# 实现记录：2025 B 题

## 完成内容

- T1：完成四附件 Excel 读取、首点异常识别、格式标准化和审计导出。
- T2：完成 Savitzky–Golay 双尺度预处理、物理波段截取、FFT 粗估和峰谷提取。
- T3：完成 Snell 定律、相位坐标、双光束厚度公式、Theil–Sen 峰谷回归与受限相位精修。
- T4：完成 Airy 多光束模型、有效反射率、差分进化全局搜索和有界局部精修。
- T5：完成谐波比、AICc、RMSE 改善联合判定，完成极值间距重采样和双角度一致性计算。
- T6：完成 `model.md`、CSV/JSON 导出和四份拟合诊断图。
- T7：完成公式、边界、合成反演及真实附件读取测试。

## 实际运行

### 单元测试

```text
命令：cd 25B/src && python test_model.py
结果：5 tests，全部通过，耗时约 0.82 s
```

### 快速冒烟测试

```text
命令：cd 25B/src && python main.py --fast --bootstrap 10
结果：四份附件均完成读取、拟合、绘图与导出
```

### 完整运行

```text
命令：cd 25B/src && python main.py --bootstrap 100
结果：成功；生成 thickness_summary.csv、data_audit.json、
      fit_details.json、consistency.json 及 4 张拟合图
```

关键结果：

- SiC：10° 为 7.9051 µm，15° 为 7.8296 µm；双角度加权结果约 7.88 µm。
- Si：Airy 模型 10° 为 3.5785 µm，15° 为 3.5487 µm；双角度加权结果约 3.57 µm。
- Si 数据高次谐波和模型改善均支持可观察多光束干涉。
- SiC 高次谐波证据不足，保留双光束主结果。

## 调试修正

1. 宽波段常折射率全谱余弦拟合会因真实色散跳到邻近干涉级次；将精修限制在峰谷稳健解附近，超出 1% 时回退稳健解。
2. 单独依赖 Airy 拟合改善会把色散/基线误差误判为多光束；改为必须同时满足有效反射率、二次谐波和 AICc/RMSE 改善。
3. 原残差区块重采样会偶发条纹级次别名；主统计区间改为峰、谷间距分组重采样，并保留残差区块法作为极值不足时的回退。

## 版本控制

工作区不是 Git 仓库（`git status` 返回 “not a git repository”），因此无法创建实现阶段提交；未初始化仓库，也未修改任何 Git 配置。

## 遗留风险

- 折射率是文献基线值；若获得晶型、晶向、掺杂和温度对应的复折射率，应重新运行。
- Airy 模型的有效反射率用于峰形诊断，不应解释为已唯一测得两个实际界面的独立反射率。

## v2 可视化增强实现（2026-08-26）

### 完成内容

- V1：将每个附件原三联图升级为六区完整证据图，包含全谱/拟合波段、基线分解、峰谷与两模型拟合、残差、归一化频谱和四项判据。
- V2：新增 `thickness_comparison.png`、`angle_consistency.png`、`multibeam_evidence.png`、`model_quality.png`。
- V3：统一色盲友好配色、线型、单位、面板编号、阈值标线和 220 dpi 导出。
- V4：将频谱计算重构为 `diagnostics.harmonic_spectrum`，诊断和绘图共享同一基频/谐波定义；增加汇总图生成测试。

### 实际运行

```text
python main.py --bootstrap 100
退出码：0；生成 8 张 PNG
四张单附件图：3543×2885，约 0.76–0.80 MB/张
四张汇总图：均成功生成

python test_model.py
结果：7 tests，全部通过
```

### 数值回归

v2 完整运行所得四附件厚度、谐波比、反射率、RMSE、AICc 和模型选择与 v1 一致；本次变更仅增强图形证据表达。

## v3 波长—载流子浓度耦合实现（2026-08-27）

### 完成内容

- D1：新增 `dispersion.py`，实现 Edwards–Ochoa Si 红外背景、Si/4H-SiC 自由载流子复介电函数、SiC 晶格振子、浓度相关迁移率先验和被动复平方根。
- D2：在 `optics.py` 新增空气/外延层/半无限衬底的斜入射 s/p Fresnel–Airy 反射率；外延层与衬底分别使用浓度相关介电函数。
- D3：新增 `joint_calibration.py`，实现双角度共享厚度与外延层/衬底浓度的稳健联合校准、线性仪器基线剖面消元、Jacobian 条件数/参数相关性/边界门控和低中高掺杂情景回退。
- D4：`main.py` 接入全波段物性校准，新增 `dispersion_fit.json`、`refractive_index_curves.csv` 及厚度汇总色散字段；统计区间与掺杂系统区间分开导出。
- D5：测试增加本征公式退化、复介电被动性、相同外延层/衬底时厚度消失和合成双角度厚度恢复。
- 更新 `model.md` 与 `README.md`，说明物理公式、论文来源、可辨识性限制和新输出。

### 实际运行

```text
python test_model.py
结果：12 tests，全部通过

python main.py --fast --bootstrap 10
结果：四附件、双角度联合校准及全部新输出成功生成

python main.py --bootstrap 100
结果：退出码 0；完整多光束搜索、100 次重采样和色散联合校准成功
```

### 结果与回退

- SiC：自由浓度拟合未优于固定掺杂情景，且连续留段厚度变异系数约 8.69%，未通过稳定性门控；最终回退约 7.84 µm 的常折射率基线，掺杂系统范围约 7.15–8.33 µm。
- Si：衬底浓度触及先验上界且自由拟合未优于固定情景，浓度不可辨识；情景推荐厚度约 3.41 µm，系统范围约 3.16–3.88 µm。
- 常折射率主流程和多光束判定保持兼容：SiC 仍选择双光束，Si 仍选择多光束。

### 版本控制

本次未创建 Git 提交：用户要求完成实现但未明确授权提交，保留工作区变更供审阅。

## v4 色散模型可视化与流程图实现（2026-08-27）

### 完成内容

- P1：更新 `thickness_comparison.png`，加入色散自由拟合、门控采用值、条件统计区间和掺杂系统范围；更新 `angle_consistency.png`，加入材料级色散采用值与系统范围。
- P2：新增 `dispersion_curves.png`、`carrier_scenarios.png` 和 `identifiability_diagnostics.png`，分别展示外延层/衬底 \(n,k\)、三档掺杂情景及连续留段门控。
- P3：新增 `src/model_flowchart.py` 生成高清数学模型流程图，并新增 `docs/model-flowchart.md` 保存可编辑 Mermaid 源图和核心公式。
- P4：`main.py` 接入所有新图自动生成；README 补充输出说明；测试增加新图非空与宽度检查。

### 实际运行

```text
python test_model.py
Ran 15 tests in 5.017s
OK

python main.py --bootstrap 100
退出码：0；全部新旧图像成功生成
```

新图尺寸：

- `dispersion_curves.png`：2885×2010
- `carrier_scenarios.png`：2885×1895
- `identifiability_diagnostics.png`：2885×1895
- `model_flowchart.png`：3765×2665

本次只改变结果表达与流程图，不修改 v3 数值模型、参数门控或最终厚度。

## v5 SiC 增强反射率与浓度区间实现（2026-08-27）

### 完成内容

- R1：新增 `instrument_response.py`，完成逐附件物理范围资格审查、SiC 浓度/厚度双通道权重及二声子区非零降权。
- R2：实现两角度共享漂移、每角度有界增益/偏置的仪器响应，替代会吸收 Drude 谱形的独立交互基线。
- R3：新增 `carrier_inference.py`，实现厚度 ±3% 锚定、多起点稳健双浓度拟合和固定情景比较。
- R4：实现外延层/衬底 \(\log_{10}N\) 轮廓重优化、90% 条件区间、边界/相关性/改善量门控。
- R5：主表将未通过门控的浓度点估计写为 `NaN`，候选值改名为 `candidate_*`；新增 `carrier_inference.json`、`carrier_profile.csv` 和 `carrier_profile.png`。
- 更新流程图、README 与 `model.md`，明确候选浓度、条件区间和绝对测量的区别。

### 冒烟与单元测试

```text
python test_model.py
Ran 21 tests in 7.466s
OK

python main.py --fast --bootstrap 10
退出码：0；增强反演及新输出成功生成
```

### 当前附件结果

- 附件 2 有 3.51% 点超过 100%，SiC 进入 `relative_shape` 模式。
- 内部候选约为 \(N_{\rm epi}=6.56\times10^{17}\)、\(N_{\rm sub}=2.07\times10^{18}\ \mathrm{cm^{-3}}\)。
- 诊断性 90% 条件范围约为 \(N_{\rm epi}=[4.95,7.39]\times10^{17}\)，\(N_{\rm sub}=[3.00\times10^{17},2.07\times10^{18}]\ \mathrm{cm^{-3}}\)。
- 衬底区间和厚度均触边，且相对固定情景改善仅约 2.76%；最终等级为 `bounded_scenario`，主表不输出浓度点估计。

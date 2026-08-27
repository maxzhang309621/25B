# 算法方案：2025 B 题碳化硅外延层厚度的确定

## 总体选型

采用“**物理公式主线 + 多种条纹估计交叉验证 + 双角度共享厚度拟合**”：

1. 用 Savitzky–Golay 双尺度滤波分离慢变基线和干涉振荡。
2. 用周期图获得厚度粗估，用显著性峰谷序列和稳健回归得到可解释的双光束厚度。
3. 用 Fresnel 系数与 Airy/单层传输矩阵建立多光束模型，先全局搜索厚度，再做有界稳健最小二乘精修。
4. 用谐波强度、峰形和 AICc/BIC 改善量共同判断多光束效应，不以肉眼或单一阈值下结论。
5. 用两个入射角共享同一厚度的联合拟合与区块自助法给出最终估计和不确定度。

该方案直接利用题目给出的等间隔波数轴。对常折射率，干涉在波数域近似等周期；对色散介质，则改用光学相位坐标
\[
g(\tilde\nu,\theta_0)=\tilde\nu\sqrt{n^2(\tilde\nu)-\sin^2\theta_0}.
\]
这样避免先转换到不等间距波长轴后再错误使用普通频谱分析。

## 步骤 1：数据读取与审计

- 选定算法：`pandas.read_excel` + 显式 schema 校验。
- 选型理由：四份附件都是规则双列表格，Pandas/OpenPyXL 对 Excel 支持成熟；显式检查递增性、有限值和首点异常比静默清洗更可审计。
- 参考资料：
  - Pandas Excel API：https://pandas.pydata.org/docs/reference/api/pandas.read_excel.html
  - OpenPyXL：https://openpyxl.readthedocs.io/
- 接口约定：附件路径、材料、角度 → 标准列 `wavenumber_cm1`、`reflectance_pct` 与审计记录。
- 依赖：`pandas>=2.0`，`openpyxl>=3.1`。

## 步骤 2：光谱预处理与条纹区域选择

- 选定算法：
  1. 首选：双尺度 Savitzky–Golay 滤波；短窗口抑制点噪声，长窗口估计慢变基线，二者之差作为条纹残差。
  2. 候选：不对称最小二乘基线，用于基线强烈偏斜时。
- 选型理由：Savitzky–Golay 能较好保持极值位置和局部峰形，且窗口长度可用波数单位配置；候选方法仅在稳定性检查显示基线泄漏时启用。
- 参考资料：
  - SciPy `savgol_filter`：https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.savgol_filter.html
- 关键参数：
  - 所有窗口先由目标波数宽度换算为奇数采样点。
  - 排除第一个反射率为 0 的明显测量/导出异常点。
  - SiC 的强声子吸收区约在 \(797\)–\(1000\ \mathrm{cm^{-1}}\)，不直接用于主厚度估计；只用于说明复折射率和吸收影响。
  - 主结果由程序扫描多个候选透明波段，以有效条纹数、周期稳定性和残差选择；固定区间只作为可重复的回退配置。
- 接口约定：标准光谱 → 平滑谱、基线、去基线残差、有效区间掩码和预处理参数。
- 依赖：`numpy>=1.24`，`scipy>=1.11`。

## 步骤 3：折射率与相位模型

- 选定算法：
  - SiC：主透明波段先采用文献红外折射率 \(n\approx2.55\) 的常数基线模型；声子区和敏感性分析采用 Drude–Lorentz 复介电函数候选。
  - Si：采用 Edwards–Ochoa 覆盖 \(2.5\)–\(25\,\mu\mathrm m\) 的红外色散数据/公式；与 Salzberg–Villa 在重叠波段交叉检查。
  - 斜入射：严格使用 Snell 定律和 \(n\cos\theta_1=\sqrt{n^2-\sin^2\theta_0}\)。
- 选型理由：赛题波数范围对应 \(2.5\)–\(25\,\mu\mathrm m\)，不能把只覆盖可见/近红外的折射率公式外推到全波段；SiC 在声子区必须允许复折射率。
- 参考资料：
  - SiC 红外光学性质与 \(n\approx2.55\)：https://www.ioffe.ru/SVA/NSM/Semicond/SiC/optic.html
  - SiC 700–4000 cm⁻¹ 的 Drude/声子模型：https://doi.org/10.1103/PhysRevB.60.11464
  - SiC 复光学常数数据：https://eepsc.wustl.edu/~hofmeist/spectra/IRSiC/
  - Si 2.5–25 µm 数据（Edwards–Ochoa）：https://refractiveindex.info/?book=Si&page=Edwards&shelf=main
  - Si 1.36–11 µm Sellmeier 交叉检查：https://refractiveindex.info/?book=Si&page=Salzberg&shelf=main
- 接口约定：材料、波数数组、模型参数 → 复折射率数组；波数、入射角、折射率、厚度 → 相位数组。
- 依赖：NumPy；折射率公式在项目内实现并注明来源与适用区间。

## 步骤 4：双光束厚度粗估与可解释估计

- 选定算法：
  1. **周期粗估**：去基线残差的实数 FFT；若清洗后采样不再等间距，则使用广义 Lomb–Scargle 周期图。
  2. **极值提取**：`scipy.signal.find_peaks`，以 prominence、distance、width 联合筛选；峰与谷分别估计。
  3. **厚度回归**：将峰/谷序号对相位坐标 \(g\) 做 Theil–Sen 稳健直线回归；斜率反演厚度。
  4. **相位精修**：以粗估厚度为中心，用有界稳健非线性最小二乘拟合“低阶基线 + 缓慢变化振幅 × 余弦相位”。
- 选型理由：FFT 提供不易受局部漏峰影响的全局初值；峰谷法能直接对应题目相邻条纹公式；Theil–Sen 对少量误检峰稳健；全谱精修利用了非极值点的信息。
- 参考资料：
  - SciPy 峰值检测：https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.find_peaks.html
  - SciPy Lomb–Scargle：https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.lombscargle.html
  - SciPy Theil–Sen：https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.theilslopes.html
  - 薄膜反射光谱包络/极值方法：https://www.sciencedirect.com/science/article/abs/pii/S0030402616316163
- 接口约定：处理后光谱、角度、折射率模型 → FFT/峰/谷/精修四组厚度、有效极值和拟合诊断。
- 依赖：SciPy。

## 步骤 5：多光束必要条件与诊断

- 选定算法：
  1. 物理条件：非零且足够大的两界面反射率、往返后振幅未被吸收显著衰减、光源相干长度大于往返光程差、仪器分辨率足以分辨自由光谱范围、层厚在光斑内足够均匀、参与光束偏振方向一致。
  2. 信号诊断：基频二次及以上谐波功率比、峰的锐度/半峰宽、双光束拟合残差的周期结构。
  3. 模型诊断：双光束与 Airy 模型的 AICc、BIC 和留段预测误差比较。
- 选型理由：高反射率会使 Airy 条纹变尖并产生高次谐波，但基线、吸收峰也可产生类似现象；将物理条件、信号形态和惩罚复杂度后的拟合改善联合使用更可靠。
- 参考资料：
  - Fabry–Pérot/Airy 公式：https://en.wikipedia.org/wiki/Fabry%E2%80%93P%C3%A9rot_interferometer
  - 多光束干涉测量条件：https://www.microscopyu.com/microscopy-basics/multiple-beam-interferometry
  - 全谱 Airy 模型用于外延层：https://beta.iopscience.iop.org/article/10.1088/1361-6641/ae5ac8
- 判定规则：仅当 Airy 模型在两个角度中均表现出稳定改善，且至少一个独立谐波/峰形指标支持时，判定“可观测多光束效应”；阈值由合成数据假阳性测试校准。
- 接口约定：实测谱、双光束拟合、Airy 拟合 → 指标字典、逐证据结论和总判定。
- 依赖：NumPy、SciPy。

## 步骤 6：多光束反射率拟合

- 选定算法：
  1. 物理核：s/p 偏振 Fresnel 振幅系数 + 单层 Airy 等比级数；非偏振反射率取 s/p 平均。实现同时保留等价的 \(2\times2\) 传输矩阵计算用于数值校验。
  2. 优化：先在双光束粗估附近做厚度网格/`differential_evolution` 全局搜索，再用 `least_squares(method="trf", loss="soft_l1")` 有界精修。
  3. 联合拟合：同一材料两个角度共享厚度与材料色散参数，各自保留基线和幅度校准参数。
- 选型理由：Airy 公式是单均匀外延层多次反射的解析解；厚度目标函数高度多峰，直接从任意初值做局部拟合容易落入错误干涉级次，因此使用“粗估/全局搜索 + 局部精修”。
- 参考资料：
  - Airy 公式及自由光谱范围：https://en.wikipedia.org/wiki/Fabry%E2%80%93P%C3%A9rot_interferometer
  - SciPy 全局优化：https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.differential_evolution.html
  - SciPy 有界稳健最小二乘：https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.least_squares.html
- 关键约束：
  - 厚度为正，并限制在周期粗估的合理倍数范围内。
  - Fresnel 系数由折射率决定，不允许以任意“反射率振幅”完全替代物理界面。
  - 强吸收区可用于复折射率诊断，但不强迫其主导厚度目标函数。
- 接口约定：两角度光谱、材料光学模型、粗估厚度 → 单角度及联合参数、预测反射率、残差和优化状态。
- 依赖：SciPy。

## 步骤 7：可靠性和不确定度

- 选定算法：
  1. 移动区块自助法：按连续波数块重采样残差，保留光谱相关性。
  2. 多窗口敏感性：改变平滑窗口、基线窗口、有效波段和峰显著性阈值。
  3. 光学常数敏感性：对 SiC 折射率及色散参数做合理范围扰动。
  4. 双角度一致性：报告相对差、标准化差异和共享厚度拟合的残差变化。
- 选型理由：普通独立点自助法会低估平滑光谱的误差；本题折射率模型误差通常大于纯采样误差，必须分开报告统计区间和系统敏感性。
- 参考资料：
  - SciPy Bootstrap：https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.bootstrap.html
- 接口约定：拟合结果、残差、参数配置 → 统计置信区间、系统误差区间、稳定性表和最终可靠性等级。
- 依赖：NumPy、SciPy。

## 步骤 8：可视化、导出与测试

- 选定算法：
  - Matplotlib 绘制原始/基线/残差、峰谷、周期图、双/多光束拟合、残差和参数稳定性图。
  - Pytest 风格断言结合 `unittest` 可直接运行的测试入口。
  - 合成光谱分别由双光束余弦模型和 Airy 模型生成，并叠加基线、相关噪声和漏峰场景。
- 选型理由：图片与 CSV/JSON 同时输出，方便论文引用和数值审计；合成数据拥有真实厚度，可验证反演误差与模型判定假阳性率。
- 接口约定：全流程结果 → `output/*.csv`、`output/*.json`、`output/*.png` 和终端摘要。
- 依赖：`matplotlib>=3.7`。

## 依赖兼容性

- Python `>=3.10`
- NumPy `>=1.24`
- SciPy `>=1.11`
- Pandas `>=2.0`
- OpenPyXL `>=3.1`
- Matplotlib `>=3.7`

全部依赖采用 BSD 或兼容的宽松许可证，可用于竞赛项目；不引入深度学习框架或在线服务。

## 候选尝试记录

| 步骤 | 候选算法 | 状态 | 失败原因 |
|---|---|---|---|
| 基线分离 | 双尺度 Savitzky–Golay | 采用 | — |
| 基线分离 | 不对称最小二乘 | 未试 | 仅在主方案出现基线泄漏时启用 |
| 双光束粗估 | FFT 周期图 | 采用 | — |
| 双光束粗估 | Lomb–Scargle | 备用 | 等间距原始数据无需优先使用 |
| 极值回归 | Theil–Sen | 采用 | — |
| 多光束物理核 | Airy + Fresnel | 采用 | — |
| 多光束数值校验 | 传输矩阵法 | 采用为校验 | 与 Airy 结果应数值等价 |
| 厚度优化 | 全局搜索 + 有界稳健最小二乘 | 采用 | — |

## 任务分配

| 任务 ID | 实现内容 | 关联步骤 | 参考资料 |
|---|---|---|---|
| T1 | 实现数据读取、审计、配置与项目入口 | 1 | Pandas/OpenPyXL 文档 |
| T2 | 实现预处理、透明波段评分、峰谷与周期粗估 | 2、4 | SciPy signal 文档 |
| T3 | 实现 Snell、折射率、双光束相位及厚度回归 | 3、4 | SiC/Si 光学常数资料 |
| T4 | 实现 Fresnel、Airy、传输矩阵校验和联合拟合 | 5、6 | Fabry–Pérot 与 SciPy optimize |
| T5 | 实现多光束诊断、AICc/BIC 和可靠性分析 | 5、7 | 模型比较与 Bootstrap |
| T6 | 实现绘图、结果导出和 `model.md` | 8 | Matplotlib |
| T7 | 编写合成数据、公式、边界和端到端测试并运行冒烟测试 | 全部 | 架构验收标准 |

## v2 可视化增强算法方案

### 步骤 V1：单附件六区诊断图

- 选定算法：Matplotlib `subplot_mosaic` 语义布局。
- 选型理由：允许原始谱、预处理、拟合、残差、频谱和证据卡采用不同面积，同时用命名轴减少布局与绘图逻辑耦合。
- 参考资料：https://matplotlib.org/stable/users/explain/axes/mosaic.html
- 具体实现：
  - 全谱区读取原始数据并用阴影标识实际拟合波段；
  - 预处理区叠加测量、平滑与基线；
  - 拟合区标记峰、谷，并叠加双光束与 Airy 曲线；
  - 残差区标注两个 RMSE 及改善率；
  - 频谱区复用 `diagnostics.py` 的同一基频定义，标注 \(f_1\)、\(2f_1\) 和谐波比；
  - 证据区直接消费 `MultiBeamDiagnostic`，不重复实现判断逻辑。
- 接口：`ProcessedSpectrum + TwoBeamResult + MultiBeamResult + MultiBeamDiagnostic + UncertaintyResult → PNG`。
- 依赖：现有 Matplotlib/NumPy，不增加第三方库。

### 步骤 V2：论文级汇总图

- 选定算法：
  - `errorbar` 绘制最终厚度与非对称 95% 置信区间；
  - 分组散点/连线绘制双角度一致性；
  - 归一化阈值证据矩阵绘制多光束四指标；
  - 分组柱状图比较双/多光束 RMSE。
- 参考资料：
  - 误差棒：https://matplotlib.org/stable/api/_as_gen/matplotlib.axes.Axes.errorbar.html
  - 图像矩阵：https://matplotlib.org/stable/api/_as_gen/matplotlib.pyplot.imshow.html
- 接口：`thickness_summary.csv` 等价内存表 + `consistency` → 4 张 PNG。

### 步骤 V3：统一样式

- 选定算法：Matplotlib 内置 `tableau-colorblind10` 样式并叠加项目级 `rcParams`。
- 选型理由：不新增依赖；颜色盲友好，同时通过线型、标记和文字避免只依赖颜色。
- 参考资料：https://matplotlib.org/stable/users/explain/customizing.html
- 导出参数：PNG，220 dpi，`bbox_inches="tight"`；统一字号、网格、单位和面板编号。

### v2 任务分配

| 任务 ID | 实现内容 | 关联步骤 | 参考资料 |
|---|---|---|---|
| V1 | 重构 `plot_spectrum_fit` 为六区证据图 | V1、V3 | subplot mosaic / rcParams |
| V2 | 实现厚度、角度一致性、证据矩阵和 RMSE 汇总图 | V2、V3 | errorbar / imshow |
| V3 | 更新 `main.py` 传递诊断与不确定度并触发汇总输出 | V1、V2 | 项目接口约定 |
| V4 | 新增可视化输出测试并完整运行，确认数值不变 | 全部 | v2 验收标准 |

## v3 波长—载流子浓度耦合算法方案

### 步骤 D1：Si 本征色散与自由载流子项

- 选定算法：Edwards–Ochoa 2.5–25 µm 红外经验式作为 Si 背景折射率，在复介电函数中叠加自由载流子 Drude 项。
- 选型理由：该经验式完整覆盖赛题 400–4000 cm⁻¹ 波段；自由载流子项显式包含浓度、有效质量和迁移率，能够把“波长与掺杂浓度共同影响折射率”落实为可计算模型。
- 关键参数：n 型 Si 电导有效质量取 \(0.26m_0\)；300 K 迁移率采用浓度相关 Caughey–Thomas 工程先验，不作为独立拟合参数。
- 参考资料：
  - Edwards & Ochoa, *Applied Optics* 19, 4130 (1980)：https://doi.org/10.1364/AO.19.004130
  - Caughey & Thomas, *Proceedings of the IEEE* 55 (1967)：https://doi.org/10.1109/PROC.1967.6123
  - Auslender & Hava, n-Si 自由载流子红外介电函数：https://doi.org/10.1002/pssb.2221740226
- 接口：波数数组、载流子浓度 → Si 复介电函数与被动分支复折射率。

### 步骤 D2：4H-SiC 声子—载流子耦合复介电函数

- 选定算法：单振子晶格介电函数叠加经典自由载流子项；透明区与 Reststrahlen 区使用同一物性关系。
- 选型理由：Tiwald 的测量覆盖 700–4000 cm⁻¹，Oishi 证明红外反射线型可同时约束 4H-SiC 外延层厚度和载流子性质，与赛题数据和目标直接对应。
- 固定基线参数：\(\varepsilon_\infty=6.56\)、TO=798 cm⁻¹、LO=970 cm⁻¹、声子阻尼=3.24 cm⁻¹、浓度有效质量 \(0.424m_0\)、迁移率质量 \(0.386m_0\)。阻尼与迁移率关系作为工程先验记录，不表述为当前晶圆实测值。
- 参考资料：
  - Tiwald et al., *Physical Review B* 60, 11464 (1999)：https://doi.org/10.1103/PhysRevB.60.11464
  - Oishi et al., *Japanese Journal of Applied Physics* 45, L1226 (2006)：https://doi.org/10.1143/JJAP.45.L1226
  - 4H-SiC 有效质量：https://doi.org/10.1103/PhysRevB.53.15409
- 接口：波数数组、载流子浓度 → 4H-SiC 复介电函数与复折射率。

### 步骤 D3：外延层—衬底物理反射模型

- 选定算法：分别计算空气、外延层和半无限衬底的复光学导纳，对 s/p 偏振使用斜入射单层 Fresnel–Airy 解析式，非偏振反射率取平均。
- 选型理由：外延层与衬底因掺杂不同而产生折射率差；物理界面系数能避免无约束“有效反射率”吸收色散误差。
- 数值约束：复平方根强制选择实部、虚部非负的被动介质分支；外延层与衬底介电函数相同时，层厚影响应消失。
- 接口：材料、波数、入射角、厚度、外延层/衬底浓度 → 物理反射率及两层 \(n,k\)。

### 步骤 D4：双角度低维联合校准

- 选定算法：受约束稳健最小二乘，主参数仅为共享厚度、\(\log_{10}N_{\rm epi}\)、\(\log_{10}N_{\rm sub}\)；每个角度的增益与低阶基线通过线性最小二乘剖面消元。
- 初值与边界：厚度以现有峰谷法为中心限制在合理区间；SiC 浓度情景覆盖外延层 \(10^{15}\)–\(3\times10^{18}\)、衬底 \(3\times10^{17}\)–\(2\times10^{19}\ \mathrm{cm^{-3}}\)；Si 覆盖 \(10^{14}\)–\(10^{19}\) 与 \(10^{15}\)–\(3\times10^{19}\ \mathrm{cm^{-3}}\)。
- 正则化：浓度采用宽对数先验；迁移率、有效质量、TO/LO 和声子阻尼固定。SiC 的 797–1000 cm⁻¹ 强声子区及 1300–1600 cm⁻¹ 二声子区不主导厚度目标。
- 可辨识性：报告缩放 Jacobian 条件数和参数相关系数；若条件数超过 \(10^8\)、相关系数绝对值超过 0.95 或参数持续触边，不把浓度标记为“测得值”，改用情景敏感性。
- 依赖：现有 NumPy/SciPy，不增加第三方依赖。

### 步骤 D5：情景不确定度与输出

- 选定算法：固定低/中/高掺杂情景分别反演厚度，并将情景跨度与已有区块自助统计区间分开报告。
- 输出：`dispersion_fit.json` 保存材料模型、论文来源、联合厚度、浓度参数、可辨识性和回退原因；`refractive_index_curves.csv` 保存两层 \(n,k\) 曲线；`thickness_summary.csv` 增加色散校正厚度和系统误差字段。
- 模型门控：只有连续留段预测、双角度一致性和可辨识性同时通过，才采用联合浓度点估计；否则最终厚度使用本征色散/情景稳健结果。

### v3 任务分配

| 任务 ID | 实现内容 | 关联步骤 | 参考资料 |
|---|---|---|---|
| D1 | 实现 Si/4H-SiC 复介电函数、迁移率先验和被动平方根 | D1、D2 | Edwards、Tiwald、Oishi |
| D2 | 实现外延层—衬底斜入射 Fresnel–Airy 反射率 | D3 | 薄膜光学解析式 |
| D3 | 实现双角度联合拟合、参数门控和掺杂情景分析 | D4、D5 | SciPy least_squares |
| D4 | 接入主流程与 CSV/JSON 输出，更新建模说明 | D5 | 现有输出接口 |
| D5 | 添加物理极限、合成恢复、回归和端到端测试 | 全部 | v3 架构验收标准 |

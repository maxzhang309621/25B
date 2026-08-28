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

## v4 色散模型可视化算法方案

### 步骤 P1：厚度与双角度图更新

- 选定算法：Matplotlib 分面散点、非对称 `errorbar` 和半透明系统区间。
- 选型理由：同一画面可区分原双/多光束结果、色散自由拟合、门控后采用值、条件统计区间及更宽的掺杂系统范围。
- 接口：`thickness_summary` 与 `consistency` → 更新后的厚度和角度一致性 PNG。
- 参考资料：https://matplotlib.org/stable/api/_as_gen/matplotlib.pyplot.errorbar.html

### 步骤 P2：折射率、情景与可辨识性图

- 选定算法：
  1. `dispersion_curves.png` 使用 2×2 分面折线，分别显示 SiC/Si 的 \(n\)、\(k\)，外延层与衬底共享颜色语义；
  2. `carrier_scenarios.png` 使用厚度点图和 RMSE 柱图，浓度标签采用科学计数法；
  3. `identifiability_diagnostics.png` 使用连续波段厚度折线与门控指标条形图，阈值归一为 1。
- 选型理由：将曲线、情景比较和“为何回退”拆成三张图，避免在一张图中混合不同单位与结论层级。
- 接口：`refractive_index_curves`、材料级联合结果 → 3 张 PNG。
- 参考资料：
  - Matplotlib `subplot_mosaic`：https://matplotlib.org/stable/users/explain/axes/mosaic.html
  - Matplotlib `fill_between`：https://matplotlib.org/stable/api/_as_gen/matplotlib.pyplot.fill_between.html

### 步骤 P3：数学模型流程图

- 选定算法：传统 Mermaid `flowchart TD` 语法保存可编辑源文件；Matplotlib `FancyBboxPatch`、菱形 `Polygon` 和 `FancyArrowPatch` 生成同逻辑高清 PNG。
- 选型理由：Mermaid 便于后续调整，Matplotlib PNG 无需 Graphviz/Node 依赖，可由现有 Python 环境稳定重现。
- 节点：附件输入 → 审计/预处理 → 常数粗估 → 本征色散与载流子项 → 外延层/衬底复折射率 → Fresnel–Airy → 双角度联合校准 → 可辨识性/留段门控 → 自由拟合、固定情景或基线回退 → 统计与系统误差 → 最终输出。
- 参考资料：https://mermaid.ai/docs/build-and-edit/write-diagram-syntax

### v4 任务分配

| 任务 ID | 实现内容 | 关联步骤 | 参考资料 |
|---|---|---|---|
| P1 | 更新厚度与角度一致性汇总图 | P1 | Matplotlib errorbar |
| P2 | 新增折射率曲线、掺杂情景和可辨识性图 | P2 | subplot_mosaic/fill_between |
| P3 | 新增 Mermaid 文档和 Matplotlib 流程图生成器 | P3 | Mermaid/Matplotlib patches |
| P4 | 接入主流程、更新 README/model 文档并增加图片测试 | 全部 | v4 架构验收标准 |

## v5 SiC 反射率浓度反演增强算法方案

### 步骤 R1：浓度信息波段与物理权重

- 选定算法：SiC 700–1200 cm⁻¹ 声子—等离子体区作为浓度主通道，1200–4000 cm⁻¹ 透明区作为厚度锚点；1300–1600 cm⁻¹ 二声子区降权而非硬删除。
- 选型理由：Oishi 的 80–2000 cm⁻¹ 全线形反演和 Tiwald 的 700–4000 cm⁻¹ 椭偏数据均表明 Reststrahlen/等离子体线形包含浓度信息；简单单振子模型不足以精确解释二声子区，稳健降权比任意新增振子自由度更适合当前无样品元数据场景。
- 参考资料：
  - https://doi.org/10.1143/JJAP.45.L1226
  - https://doi.org/10.1103/PhysRevB.60.11464

### 步骤 R2：受约束仪器响应

- 选定算法：多数据集变量投影/受约束仪器模型；两角度共享平滑线性响应，每角度只允许有界增益与偏置，不再使用独立 `z×R` 交互项。
- 选型理由：原四列线性剖面会吸收 Drude 慢变形状；共享响应减少仪器自由度，同时保留附件 2 超过 100% 所需的校正能力。
- 参数范围：角度增益限制在 0.85–1.15，偏置限制在 ±8 个百分点，共享线性漂移限制在 ±5 个百分点。
- 参考资料：
  - Golub–Pereyra 变量投影：https://doi.org/10.1137/0710036
  - 光谱变量投影综述：https://doi.org/10.1007/s11075-008-9235-2

### 步骤 R3：分阶段浓度反演

- 选定算法：
  1. 固定浓度先验，在透明区确定厚度窄区间；
  2. 分别固定衬底情景反演外延层浓度、固定外延层情景反演衬底浓度；
  3. 仅当灵敏度独立性通过时才开放双浓度联合拟合；
  4. 全部模型使用两个角度共享样品参数和稳健损失。
- 选型理由：优先得到单浓度条件区间，避免在数据不支持时直接同时开放两个高度相关的载流子参数。
- 输出：双浓度、单浓度条件、浓度等级、单侧界限或不可辨识五级结果。

### 步骤 R4：轮廓似然区间与可辨识性

- 选定算法：在 \(\log_{10}N\) 网格上固定目标参数、重新优化厚度及其余参数，以 \(\Delta\chi^2=2.706\) 构造 90% 轮廓区间；区间触边则标记单侧或无界。
- 选型理由：非线性厚度—浓度补偿下，局部协方差会低估不确定度；轮廓似然能直接检测平坦方向和参数边界。
- 参考资料：
  - Raue et al.：https://doi.org/10.1093/bioinformatics/btp358
  - Kreutz et al.：https://doi.org/10.1111/febs.12276
- 门控：双浓度相关系数绝对值 <0.85、区间宽度 ≤0.6 dex、相对固定情景预测改善 ≥10%；单浓度条件区间宽度 ≤1.0 dex。

### 步骤 R5：数据资格与条件输出

- 选定算法：原始反射率物理范围审计。超界点比例 >0.5% 时进入 `relative_shape` 模式；浓度候选值只进入诊断，主结果输出条件区间或 `null`。
- 当前数据：附件 2 约 3.51% 点超过 100%，因此 SiC 必须标记为相对谱形模式。
- 输出：新增 `carrier_inference.json` 和 `carrier_profile.csv`；`thickness_summary.csv` 仅在门控通过时写浓度点估计。

### v5 任务分配

| 任务 ID | 实现内容 | 关联步骤 | 参考资料 |
|---|---|---|---|
| R1 | 实现材料分波段权重和数据资格审查 | R1、R5 | Oishi/Tiwald |
| R2 | 实现共享且有界的仪器响应模型 | R2 | Variable Projection |
| R3 | 实现 SiC 单浓度条件、双浓度联合与层级回退 | R3 | SciPy 稳健最小二乘 |
| R4 | 实现 logN 轮廓扫描、90% 区间及可辨识性等级 | R4 | Profile likelihood |
| R5 | 接入主流程、条件输出、可视化和合成/异常测试 | 全部 | v5 架构验收标准 |

## v6 论文图防重叠与独立原始证据图算法方案

### 步骤 V6-1：全局布局和图例避让

- 选定算法：Matplotlib constrained layout，配合图级标题、轴级标题分层；多曲线图采用图外图例或 `bbox_to_anchor`，保存时使用 `bbox_inches="tight"` 与显式边距。
- 选型理由：项目已有 Matplotlib 依赖，官方布局引擎能让标题、坐标轴和图例参与边界计算，无需增加第三方依赖；固定图例区比在数据区自动寻找位置更稳定、可复现。
- 参考资料：
  - https://matplotlib.org/stable/users/explain/axes/legend_guide.html
  - https://matplotlib.org/stable/api/_as_gen/matplotlib.pyplot.savefig.html
- 接口约定：现有绘图函数输入保持不变，仅统一图布置、保存和字体参数。

### 步骤 V6-2：数据标签确定性避让

- 选定算法：按横坐标排序后进行一维间距检测；相邻标签不足最小显示距离时，采用上下交替的 `annotate(..., textcoords="offset points")` 偏移；绘图后按数据跨度扩展纵轴 10%–20%。柱图使用 `bar_label` 显式 padding 并预留标签坐标范围。
- 选型理由：当前标签数量少且顺序固定，确定性贪心避让轻量、稳定，并可限制标签移动方向以避开线条。
- 参考资料：
  - https://matplotlib.org/stable/api/_as_gen/matplotlib.axes.Axes.annotate.html
  - https://matplotlib.org/stable/api/_as_gen/matplotlib.pyplot.bar_label.html
- 依赖：无新增依赖。

### 步骤 V6-3：独立多光束原始证据导出

- 选定算法：单指标单坐标轴导出；四项标量证据分别读取现有汇总字段生成数据图，附件频谱直接复用已有频率—幅值诊断数组逐数据集导出。
- 选型理由：复用已有计算结果保证与主结论数值同源；每图只保留标题、轴、单位和图例，可直接作为论文证据素材。
- 接口约定：处理后频谱及汇总结果 → `output/raw_evidence/multibeam/*.png`。

### 步骤 V6-4：独立色散原始数据导出

- 选定算法：从折射率曲线表、情景拟合、留段厚度和载流子轮廓表分别生成单物理量单图；轮廓图只画目标函数曲线，不写阈值结论或区间说明。
- 选型理由：按数据层拆分后可独立引用；直接使用导出表可执行图—表一致性检查。
- 接口约定：色散表、材料 payload、轮廓表 → `output/raw_evidence/dispersion/*.png`。

### 步骤 V6-5：图像与文字约束回归

- 选定算法：文件清单、像素尺寸、PNG 非空校验；通过 Figure Artist 文本集合检查独立图不含禁止词；对渲染后边界框执行标题、图例和数值标签明显交集检测。
- 选型理由：文件存在检查不能防止布局回归，渲染后的 Artist 边界更接近最终 PNG。

### v6 任务分配

| 任务 ID | 实现内容 | 关联步骤 | 参考资料 |
|---|---|---|---|
| V6-A | 统一现有综合图布局、字体、边距、图例和标签避让 | V6-1、V6-2 | Matplotlib 官方文档 |
| V6-B | 新建独立多光束原始证据绘图模块并接入主流程 | V6-3 | 现有谐波与模型比较结果 |
| V6-C | 新建独立色散原始证据绘图并接入主流程 | V6-4 | 现有色散、情景和轮廓结果 |
| V6-D | 增加布局、输出清单和禁止文字回归测试，运行端到端程序 | V6-5 | Matplotlib Artist API |

## v7 方案 B 本征色散与不可辨识审计算法方案

### 步骤 B1：双模式复介电接口

- 选定算法：材料策略模式。`intrinsic` 模式令自由载流子浓度为零，仅保留 Si 的 Edwards–Ochoa 本征色散和 4H-SiC 的固定单振子晶格色散；`fixed_carrier` 模式只接受预先给定的浓度情景；原 `carrier_coupled` 路径保持兼容。
- 选型理由：现有物理核已经分别实现本征/晶格项与 Drude 项，模式隔离只改变参数开放方式，不重复实现介电函数，也不会改变 v6 主结果。
- 参考资料：
  - Edwards–Ochoa Si 红外折射率：https://doi.org/10.1364/AO.19.004130
  - Tiwald et al. 4H/6H-SiC 晶格与 Drude 响应：https://doi.org/10.1103/PhysRevB.60.11464
- 接口约定：`material_epsilon(material, x, carrier_cm3, mode=...) -> complex ndarray`；旧三参数调用保持原行为。
- 依赖：NumPy（现有）。

### 步骤 B2：本征色散固定情景厚度反演

- 选定算法：有界一维标量优化 + 变量投影。对 `intrinsic`、`low`、`medium`、`high` 四种固定光学情景，双角度共享厚度，仅对厚度做有界搜索；每个角度的慢变基线、增益由线性最小二乘剖面消元。
- 选型理由：浓度固定后只剩一个关键非线性变量，标量有界优化稳定、可复现；变量投影沿用现有仪器补偿方式，避免把基线参数加入非线性搜索。
- 参考资料：
  - Golub–Pereyra 变量投影：https://doi.org/10.1137/0710036
  - SciPy bounded scalar minimization：https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.minimize_scalar.html
- 接口约定：`fit_intrinsic_scenarios(spectra, initial_thicknesses, material) -> IntrinsicScenarioResult`；输出四情景厚度、RMSE、包络和相对常数主值偏差。
- 依赖：SciPy、NumPy（现有）。

### 步骤 B3：不可辨识证据聚合

- 选定算法：规则化证据审计。复用联合校准的 Jacobian 条件数、最大参数相关、先验触边、连续留段 CV/最大偏移，以及增强反演的轮廓区间触边、浓度相关和固定情景改善率；每项同时输出观测值、阈值和是否通过。
- 选型理由：这些指标来自两套现有可辨识性检查，聚合后能区分“拟合成功”和“参数可辨识”，且避免重新计算造成口径漂移。
- 参考资料：
  - Raue et al. profile likelihood practical identifiability：https://doi.org/10.1093/bioinformatics/btp358
- 接口约定：`build_identifiability_audit(joint_results, carrier_result) -> dict`；至少输出 `concentration_identifiable`、`failure_reasons`、`recommended_interpretation`。
- 依赖：无新增依赖。

### 步骤 B4：三轨结果汇总

- 选定算法：显式决策表聚合。轨 0 主结果、轨 1 系统误差、轨 2 审计证据分别命名，不通过数值排序自动选择。
- 选型理由：主结果采纳是架构规则而非经验最小 RMSE；显式字段能防止色散旁路覆盖 `selected_thickness_um`。
- 接口约定：`build_refractive_index_comparison(summary, intrinsic, audit) -> dict`。
- 输出：`intrinsic_dispersion_fit.json`、`intrinsic_n_curves.csv`、`audit_identifiability.json`、`refractive_index_comparison.json`，并扩展 `thickness_summary.csv`。

### 步骤 B5：回归与系统验收

- 选定算法：`unittest` 正常/边界/异常测试 + 四附件端到端回归。
- 验证重点：
  1. 本征模式与零载流子复介电严格一致；
  2. 固定情景不开放浓度优化；
  3. 四情景系统包络包含全部情景厚度；
  4. 审计 JSON 的失败原因与现有结果一致；
  5. v7 不覆盖轨 0 主厚度和模型选择；
  6. 原 21 项测试全部通过。

### v7 任务分配

| 任务 ID | 实现内容 | 关联步骤 | 参考资料 |
|---|---|---|---|
| B1 | 扩展 `dispersion.py` 双模式接口并补边界测试 | B1 | Edwards–Ochoa；Tiwald |
| B2 | 新建 `intrinsic_scenario.py`，实现四情景共享厚度反演与曲线导出 | B2 | bounded minimization；variable projection |
| B3 | 新建 `identifiability_audit.py`，聚合不可辨识证据 | B3 | profile likelihood |
| B4 | 新建 `comparison_report.py` 并接入 `main.py` 输出契约 | B4 | v7 架构采纳规则 |
| B5 | 更新 `test_model.py`、`model.md` 与流水线记录，运行完整回归 | B5 | v7 验收标准 |

## v8 色散坐标多峰谷稳健反演算法方案

### 步骤 E1：透明波段与极值资格

- 选定算法：连续透明区物理掩膜与现有候选窗评分联合筛选。先使用材料复折射率的消光系数、光学坐标单调性排除强吸收/折返区，再用条纹显著性、边缘距离和有效间隔数筛除低质量极值。
- 选型理由：波段资格决定极值公式是否成立；将物理掩膜放在统计评分之前，可避免强吸收区的大残差主导厚度结果。
- 接口：`evaluate_band_eligibility(processed, material, mode, carrier) -> BandEligibility`。
- 依赖：NumPy、SciPy（现有）。

### 步骤 E2：多峰谷观测

- 选定算法：复用现有双光束检测尺度，使用 SciPy 峰显著度与半高宽评估每个峰/谷，输出统一观测对象。
- 选型理由：保持与 L0 极值位置同源，同时补充质量权重和边缘标记，避免重新定义峰谷口径。
- 接口：`observe_extrema(processed, two_result) -> list[ExtremumObservation]`。
- 参考资料：SciPy peak prominence/width API。

### 步骤 E3：色散坐标与级次恢复

- 选定算法：按固定情景计算 \(g=\tilde\nu\sqrt{n^2-\sin^2\theta}\)；对每条峰/谷序列用相邻 \(g\) 差的稳健中位数估计漏级倍数，将局部顺序恢复为允许跳跃的级次。
- 选型理由：同类极值在 \(g\) 坐标中应近似等距，间距倍数可识别漏峰，而无需知道绝对干涉级次。
- 参考资料：Swanepoel 极值级次关系：https://doi.org/10.1088/0022-3735/16/12/023
- 接口：`map_extrema_to_scenario(...) -> list[MappedExtremum]`。

### 步骤 E4：共享厚度稳健回归

- 选定算法：共享斜率、序列独立截距的 Huber 型稳健最小二乘；初值由线性最小二乘给出，按 MAD 标记异常极值并复算。厚度由共享斜率换算。
- 选型理由：峰、谷和两个角度只共享厚度，不共享反射相位；Huber 损失保留轻微偏差点并降低异常点影响，适合当前几十个小样本极值。
- 候选：
  1. Huber 共享斜率（首选，确定性、无新增依赖）；
  2. Theil–Sen 分序列斜率后稳健融合（回退）；
  3. RANSAC（仅当离群比例明显升高时启用）。
- 接口：`fit_shared_thickness(mapped, ...) -> SharedThicknessResult`。
- 参考资料：SciPy robust least squares；Theil–Sen/Sen 稳健斜率。

### 步骤 E5：稳定性与误差

- 选定算法：峰/谷子集、角度子集独立拟合；连续三段留出；按极值重采样构造条件统计区间；固定情景结果形成系统包络。
- 选型理由：分别量化定位噪声与折射率情景不确定性，避免把系统范围误称为置信区间。
- 接口：结果对象直接包含 `peak_only_um`、`valley_only_um`、`angle_*_um`、`bootstrap_ci95`、`band_cv_pct`、`stable`。

### 步骤 E6：接入与决策

- 选定算法：显式状态机。只有本征情景通过峰谷、角度、留段、样本量和剔除率门控时，才将 v8 作为名义厚度；固定情景中通过门控的结果构成系统包络；否则回退 v7。
- 输出：`extrema_observations.csv`、`dispersion_extrema_coordinates.csv`、`dispersion_extrema_fit.json`、`dispersion_extrema_residuals.csv`、`dispersion_extrema_comparison.json`。

### v8 任务分配

| 任务 ID | 实现内容 | 关联步骤 | 参考资料 |
|---|---|---|---|
| E1 | 新建 `band_eligibility.py`，实现物理资格与共同掩膜 | E1 | 现有色散模型 |
| E2 | 新建 `extrema_observation.py`，统一峰谷观测和质量字段 | E2 | SciPy 峰属性 |
| E3 | 新建 `dispersion_extrema.py`，完成情景映射与漏级恢复 | E3 | Swanepoel 级次关系 |
| E4 | 新建 `shared_thickness.py`，实现共享斜率稳健反演 | E4 | robust least squares |
| E5 | 扩展主流程、误差、决策、表图和文档 | E5、E6 | v8 架构门控 |
| E6 | 新增不少于 10 项测试并完整运行四附件 | 全部 | v8 验收标准 |

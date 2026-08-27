# 波长—载流子浓度耦合的外延层厚度模型流程图

```mermaid
flowchart TD
    inputData[/"附件1–4：波数、反射率、入射角"/] --> audit["数据审计：排序、异常值、单位"]
    audit --> qualification{"物理范围外反射率≤0.5%？"}
    qualification -->|"是"| absoluteMode["绝对反射率模式"]
    qualification -->|"否"| relativeMode["相对谱形模式：禁止报告绝对浓度点"]
    absoluteMode --> preprocess["双通道预处理"]
    relativeMode --> preprocess
    preprocess --> thicknessBand["透明区：厚度相位通道"]
    preprocess --> carrierBand["700–1200 cm⁻¹：浓度敏感通道"]
    preprocess --> twoPhonon["1300–1600 cm⁻¹：降权而非硬删除"]

    thicknessBand --> constantBase["常折射率稳健基线：FFT粗估、峰谷回归"]
    constantBase --> initialThickness["厚度初值与干涉级次 d0"]

    literature[("论文物性与掺杂先验")] --> intrinsic["本征/晶格色散"]
    literature --> carrier["自由载流子响应"]
    intrinsic --> epiIndex["外延层复折射率 n_epi"]
    carrier --> epiIndex
    intrinsic --> subIndex["衬底复折射率 n_sub"]
    carrier --> subIndex

    epiIndex --> physicalReflectance["外延层—衬底 Fresnel–Airy 反射率"]
    subIndex --> physicalReflectance
    physicalReflectance --> instrument["共享漂移 + 分角度有界增益/偏置"]
    carrierBand --> instrument
    twoPhonon --> instrument
    initialThickness --> singleFit["单浓度条件反演"]
    instrument --> singleFit
    singleFit --> jointFit["灵敏度独立时开放双浓度联合反演"]

    jointFit --> profile["固定目标浓度并重优化其余参数：轮廓似然"]
    profile --> identifiability{"90%区间闭合、相关性<0.85、改善≥10%？"}
    identifiability -->|"是"| bandGate{"连续留段浓度稳定？"}
    identifiability -->|"否"| scenarioFit["固定低/中/高掺杂情景"]
    scenarioFit --> scenarioBandGate{"情景留段稳定？"}
    bandGate -->|"是"| freeFit["采用自由浓度联合结果"]
    bandGate -->|"否"| scenarioFit
    scenarioBandGate -->|"是"| fixedScenario["采用最佳固定掺杂情景"]
    scenarioBandGate -->|"否"| baselineFallback["回退常折射率稳健基线"]

    freeFit --> uncertainty["统计重采样 + 掺杂情景系统误差"]
    fixedScenario --> uncertainty
    baselineFallback --> uncertainty
    uncertainty --> output[/"厚度、浓度条件区间/单侧界限、仪器模式、n/k曲线"/]
```

## 核心数学关系

复折射率由本征色散和载流子响应共同决定：

$$
\tilde n_j(\tilde\nu,N_j)=\sqrt{\varepsilon_j(\tilde\nu,N_j)},
\qquad
\varepsilon_j=\varepsilon_{\mathrm{intrinsic}}+\varepsilon_{\mathrm{carrier}},
\qquad
j\in\{\mathrm{epi},\mathrm{sub}\}.
$$

外延层传播相位与非偏振反射率为：

$$
\beta=2\pi d\tilde\nu
\sqrt{\tilde n_{\mathrm{epi}}^2-\sin^2\theta_0},
\qquad
R=\frac{|r_s|^2+|r_p|^2}{2}.
$$

联合反演只开放共享厚度与两个载流子浓度参数：

$$
\Theta=
\left(d,\log_{10}N_{\mathrm{epi}},\log_{10}N_{\mathrm{sub}}\right).
$$

## 当前附件的门控结果

- SiC：附件 2 有约 3.51% 反射率超过 100%，因此进入 `relative_shape` 模式。
- 增强模型可给出仪器响应条件下的双浓度轮廓区间，但不输出绝对浓度点估计。
- 原厚度色散模型的连续波段稳定性仍未通过，厚度主结果继续回退常折射率稳健基线。
- Si：高掺杂固定情景留段稳定，但衬底浓度触及先验边界，因此不报告唯一浓度。
- 两种材料均分别报告条件统计区间和掺杂情景系统范围。

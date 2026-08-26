# 建模要点（Peterzhu）

## 问题1 — 双光束

光程差与相位：

\[
\Delta=2d\sqrt{n_1^2-\sin^2\theta_0},\qquad
\delta=4\pi\tilde\nu\,d\sqrt{n_1^2-\sin^2\theta_0}
\]

双光束反射率：

\[
R=A_1+A_2+2\sqrt{A_1A_2}\cos(\delta+\varphi)
\]

常数 \(n\) 时：

\[
d=\frac{1}{2\sqrt{n_1^2-\sin^2\theta_0}\,\Delta\tilde\nu}
\]

题目强调 \(n=n(\tilde\nu,N)\)，但附件不给 \(N\)；答卷可写色散+Drude 形式，计算可用定值 \(n\) + 去噪。

## 问题2 — SiC 算法

1. 预处理：去首点 0；R>100% 截断  
2. 分析窗：约 1500–3000 cm⁻¹  
3. 平滑 + 去趋势  
4. FFT 主峰 → OPD → \(d\)（\(n=2.55\)）  
5. 10°/15° 交叉；窗口敏感性；稳健峰间距对照  

推荐：**7.875 ± ~0.22 μm**（见 `solution/summary_定值n去噪.json`）。

## 问题3 — 多光束

\[
r=\frac{r_{01}+r_{12}e^{-i\delta}}{1+r_{01}r_{12}e^{-i\delta}}
\]

必要条件：\(F=|r_{01}r_{12}|e^{-\alpha}\) 不可忽略。

诊断：振荡 σ、偏度、FFT 谐波比。  
- Si：多光束明显 → 抑谐波/多光束模型，**d≈3.38 μm**  
- SiC：弱 → **不修正**，维持问题2  

## 关键脚本

| 脚本 | 作用 |
|------|------|
| `problem2_sic_thickness.py` | SiC FFT/极值/可靠性 |
| `constant_n_denoise.py` | 定值 n + 去噪主叙事 |
| `problem3_multibeam.py` | 多光束理论与 Si/SiC |
| `n_dispersion_model.py` | \(n(\tilde\nu,N)\) 可选建模 |
| `plot_fft_two_vs_multi.py` | 双/多光束 FFT 图 |
| `plot_oscillation_relation.py` | 振荡关系图 |

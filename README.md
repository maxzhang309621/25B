# 2025 高教社杯数学建模竞赛 B 题（Peterzhu 分支）

本分支为 **Peterzhu** 队/个人工作区，基于赛题「碳化硅外延层厚度的确定」，在本地完成问题 1–3 的建模、算法、图像与说明。

上游仓库参考：[maxzhang309621/25B](https://github.com/maxzhang309621/25B)（`dev`）。本分支内容为独立实现，不覆盖上游 `src/` 流水线；结果数值可与上游对照。

## 主要结论（本分支）

| 材料 | 主模型 | 推荐厚度 | 备注 |
|------|--------|----------|------|
| 碳化硅（附件1/2） | 定值 \(n=2.55\) + 去噪 + FFT 双角度 | **≈ 7.875 μm** | 多光束很弱，问题3不修正 |
| 硅（附件3/4） | 多光束判定 + FFT 基频 / 抑谐波 | **≈ 3.381 μm** | \(n_{\mathrm{Si}}=3.42\)，振荡强、偏度大 |

可靠性：SiC 10°/15° FFT 相对差约 **0.29%**。

## 仓库结构

```
CUMCM2025B/   (branch: Peterzhu)
├── README.md
├── model.md                          # 公式与建模要点
├── requirements.txt
├── .gitignore
├── .cursor/skills/2025b-sic-epi/     # 给其他 AI / Cursor Agent 用的 Skill
│   └── SKILL.md
├── data/                             # 题目附件与原理图
│   ├── B题.pdf
│   ├── 附件1.xlsx … 附件4.xlsx
│   └── Image40.png / Image48.png
├── solution/                         # 算法脚本、结果 JSON、结果图、方法论
└── figures_extra/                    # 示意/统计补充图
```

## 环境

```bash
python -m pip install -r requirements.txt
```

Python 3.10+ 推荐（3.9 亦可）。

## 运行

在仓库根目录或 `solution/` 下执行：

```bash
cd solution
python problem2_sic_thickness.py      # 问题2 SiC 厚度
python constant_n_denoise.py          # 定值 n + 去噪主结果
python problem3_multibeam.py          # 问题3 多光束 + Si
python n_dispersion_model.py          # 可选：色散/Drude 建模
python plot_fft_two_vs_multi.py       # 双/多光束 FFT 对比图
python plot_oscillation_relation.py   # 振荡关系图
```

数据路径：脚本默认读取 `../附件` 或同级 `data`——本仓库已将附件放在 `data/`。若报错找不到文件，把 `ATTACH` 改成仓库内 `data` 目录（见下方「给 AI 的提示」）。

> **路径适配**：当前部分脚本仍写死原路径 `B题/附件`。首次在本仓库运行时，请先执行：

```bash
python -c "from pathlib import Path; print('use fix_paths or edit ATTACH in scripts')"
```

或直接改各脚本中的 `ATTACH = ROOT.parent / "data"`（本仓库已按此约定整理，提交前会统一路径）。

## Git 工作流（本地可直接提交）

本地仓库路径：

`E:\课程\数模\模拟测试\第三次模拟\CUMCM2025B`

当前分支：**Peterzhu**（已有初始提交）。改完代码后：

```bash
cd E:\课程\数模\模拟测试\第三次模拟\CUMCM2025B
git add -A
git commit -m "说明本次改动"
```

### 推送到 GitHub

目标上游：`https://github.com/maxzhang309621/25B` 的 `Peterzhu` 分支。

当前账号 **没有该仓库写权限**（push 会 403）。任选其一：

1. **请仓库主人**把你的 GitHub 账号加成 Collaborator，然后：

```bash
git push -u origin Peterzhu
```

2. **先 Fork** [maxzhang309621/25B](https://github.com/maxzhang309621/25B) 到自己账号，再：

```bash
git remote set-url origin https://github.com/<你的用户名>/25B.git
git push -u origin Peterzhu
# 可选：在 GitHub 上向原仓库开 PR，目标分支选新建 Peterzhu
```

本地 `origin` 已指向 `https://github.com/maxzhang309621/25B.git`。

## Skill（给其他 AI）

见 [`.cursor/skills/2025b-sic-epi/SKILL.md`](.cursor/skills/2025b-sic-epi/SKILL.md)。在 Cursor 中打开本仓库后，Agent 应优先按该 Skill 理解题意、复现算法与结果口径。

## 许可证

题目数据版权归竞赛组委会；代码按仓库 LICENSE / 学习研究用途使用。

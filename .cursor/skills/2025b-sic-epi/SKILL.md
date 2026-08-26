---
name: 2025b-sic-epi
description: >-
  Solve and extend the 2025 CUMCM Problem B (SiC/Si epitaxial layer thickness
  from IR reflectance). Use when working in this repo, mentioning 2025B, 碳化硅
  外延层, NIPT-unrelated FTIR fringe thickness, attachments 附件1–4, two-beam vs
  multi-beam Airy, or Peterzhu branch results.
---

# 2025 CUMCM B — SiC / Si Epi Thickness (Peterzhu)

## When to use

- Editing or re-running code under `solution/`
- Explaining Q1–Q3 models, FFT, denoising, multi-beam diagnostics
- Regenerating figures or updating README / `model.md` numbers
- Comparing with upstream `maxzhang309621/25B` `dev` branch

## Problem map

| Q | Goal | Main artifacts |
|---|------|----------------|
| 1 | Two-beam model only (formulas) | `model.md`, `figures_extra/示意_*.png` |
| 2 | SiC thickness from 附件1/2 (10°/15°) | `problem2_sic_thickness.py`, `constant_n_denoise.py` |
| 3 | Multi-beam theory; Si 附件3/4; SiC correction check | `problem3_multibeam.py` |

Data: `data/附件1.xlsx` … `附件4.xlsx` (columns: wavenumber cm⁻¹, reflectance %). Drop first `(≈399.67, 0)` point; clip R>100% on 附件2.

## Physics essentials (do not invent)

- Optical path: \(\mathrm{OPD}=2d\sqrt{n^2-\sin^2\theta_0}\), \(\delta=2\pi\cdot\mathrm{OPD}\cdot\tilde\nu\)
- Constant-\(n\) thickness: \(d=1/(2\sqrt{n^2-\sin^2\theta_0}\,\Delta\tilde\nu)\) with \(\tilde\nu\) in cm⁻¹ → \(d\) in cm, then ×10⁴ → μm
- Defaults: \(n_{\mathrm{SiC}}=2.55\), \(n_{\mathrm{Si}}=3.42\)
- Multi-beam: \(r=(r_{01}+r_{12}e^{-i\delta})/(1+r_{01}r_{12}e^{-i\delta})\); diagnose via osc σ, skew, FFT harmonics; SiC weak → keep two-beam; Si strong → suppress harmonics / Airy

## Canonical results on this branch

- **SiC**: ≈ **7.875 μm** (FFT dual-angle, \(n=2.55\), denoise pipeline)
- **Si**: ≈ **3.381 μm** (multi-beam likely; harmonic-suppressed / FFT)
- Do not claim Kakeya / unrelated pure-math results solve this problem

## Workflow for agents

1. Read `README.md` + `model.md` + `solution/方法论与结果_问题2.md` / `_问题3.md`
2. Ensure scripts use `ATTACH = Path(__file__).resolve().parents[1] / "data"`
3. Re-run only the needed script; write figures/JSON into `solution/`
4. Update summary numbers in README/`model.md` if results change
5. Commit on branch **`Peterzhu`** with a short Chinese or English message focused on *why*

## Denoising philosophy (Q2 preferred narrative)

Treat \(n\) as fixed; treat dispersion/carrier/calibration/instrument as noise:

1. Window away Reststrahlen (~900 cm⁻¹ for SiC)
2. Savitzky–Golay smooth
3. Polynomial detrend → keep fringe oscillation
4. FFT fundamental (primary); peak MAD as check
5. Dual-angle fuse + window sensitivity for uncertainty

## Paths

- Repo root: folder containing `README.md` and `data/`
- Never commit `__pycache__/`, `~$*.xlsx`, large unrelated course folders

## Upstream note

Upstream `dev` may report SiC ≈7.88 μm, Si ≈3.57 μm with Airy fit — close but not identical; document method differences rather than silently overwriting.
